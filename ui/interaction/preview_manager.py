# -*- coding: utf-8 -*-
"""
悬停预览：``InteractionMode`` + ``FaceType`` → ghost / 放置元数据（**UI 瞬态**）。

与命令管线解耦：``hit`` / ``session`` 仅供 Viewport 绘制与 metadata 着色；
点击确认时在 ``CabinetInteractionManager._capture_face_click_snapshot`` 复制为
``FaceSelectionSnapshot`` 后再调用命令，禁止共享可变 face 对象。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from view.interaction.hover_hit_result import HoverHitResult

from .hover_session import SpaceFaceHoverSession, clear_session, update_session_from_hit
from .interaction_log import (
    log_hover_clear,
    log_hover_face_detected,
    log_hover_face_occupancy,
    log_view3d_draw_preview_ghost,
)
from view.interaction.face_type import FaceType
from .interaction_mode import InteractionMode
from .preview_mesh_cache import get_preview_mesh_cache
from core.space.space_occupancy import leaf_topology_occupied
from .face_interaction import face_for_tool_mode, process_face_hover
from .preview_spec import (
    InteractionPreviewSpec,
    PreviewGhostMesh,
    effective_preview_mode,
    primary_hover_face_for_mode,
    resolve_preview_spec,
)


@dataclass(frozen=True)
class PreviewTickResult:
    """一次悬停刷新结果（供 Viewport 决定是否 ``update()``）。"""

    changed: bool = False
    entered: bool = False
    cleared: bool = False
    needs_repaint: bool = False


class PreviewManager:
    """``HoverHitResult`` + 动态 ``InteractionPreviewSpec`` → 预览 ghost / 盒体色。"""

    def __init__(self) -> None:
        _pf = primary_hover_face_for_mode(InteractionMode.ADD_PANEL)
        self._session = SpaceFaceHoverSession(target_face=_pf)
        self._interaction_mode: InteractionMode = InteractionMode.SELECT
        self._preview_mode: InteractionMode = InteractionMode.ADD_PANEL
        self._tool_mode: Any = None
        self._last_hover_face_key: tuple[str, object | None] | None = None

    @property
    def session(self) -> SpaceFaceHoverSession:
        return self._session

    @property
    def hit(self) -> HoverHitResult | None:
        """悬停瞬态命中（仅 UI）；命令层禁止读取。"""
        return self._session.hit

    @property
    def active(self) -> bool:
        return self._session.active and self.active_spec() is not None

    @property
    def stack_offset_mm(self) -> float | None:
        return self._session.stack_offset_mm

    @property
    def ghost_draw_logged(self) -> bool:
        return self._session.ghost_draw_logged

    @property
    def interaction_mode(self) -> InteractionMode:
        return self._interaction_mode

    def set_interaction_mode(self, mode: InteractionMode) -> None:
        self._interaction_mode = mode

    def configure_hover_context(
        self,
        interaction_mode: InteractionMode,
        tool_mode: Any,
    ) -> None:
        """根据 ``InteractionMode`` + ``ToolMode`` 设置拾取目标面与有效预览模式。"""
        self._interaction_mode = interaction_mode
        self._tool_mode = tool_mode
        self._preview_mode = effective_preview_mode(interaction_mode, tool_mode)
        from ui.cabinet_space.tool_modes import ToolMode

        face = face_for_tool_mode(tool_mode)
        if face is not None:
            self._session.target_face = face
        elif tool_mode == ToolMode.SELECT:
            self._session.target_face = None
        else:
            face = primary_hover_face_for_mode(self._preview_mode)
            if face is not None:
                self._session.target_face = face

    def hover_target_face(self) -> FaceType | None:
        return self._session.target_face

    def active_spec(self) -> InteractionPreviewSpec | None:
        if not self._session.active or self._session.hit is None:
            return None
        return resolve_preview_spec(self._preview_mode, self._session.hit.face)

    def default_thickness_mm(self) -> float:
        spec = self.active_spec()
        if spec is None:
            pf = primary_hover_face_for_mode(self._preview_mode)
            if pf is not None:
                s = resolve_preview_spec(self._preview_mode, pf)
                if s is not None:
                    return s.default_thickness_mm
            return 18.0
        return spec.default_thickness_mm

    def stack_offset_for_space(self, root: Any | None) -> float:
        spec = self.active_spec()
        if spec is None:
            pf = primary_hover_face_for_mode(self._preview_mode)
            if pf is not None:
                spec = resolve_preview_spec(self._preview_mode, pf)
        hit = self._session.hit
        sp = hit.space if hit is not None else None
        if sp is None:
            sp = root
        if sp is None or spec is None:
            return 0.0
        try:
            return float(spec.stack_offset_mm(sp))
        except Exception:
            return 0.0

    def build_active_ghost_mesh(self, root: Any | None) -> PreviewGhostMesh | None:
        """
        仅用于推导变换参数；绘制路径使用 ``PreviewMeshCache``，禁止每帧 new mesh。
        """
        spec = self.active_spec()
        hit = self._session.hit
        if spec is None or hit is None:
            return None
        sp = hit.space
        stack = float(self._session.stack_offset_mm or 0.0)
        return spec.build_ghost_mesh(sp, spec.default_thickness_mm, stack)

    def sync_preview_mesh_cache(self) -> bool:
        """
        悬停命中变化时：``update_transform`` + ``show``；禁止 rebuild mesh。
        """
        cache = get_preview_mesh_cache()
        if not self._session.active or self._session.hit is None:
            cache.hide()
            return False
        mesh = self.build_active_ghost_mesh(None)
        if mesh is None:
            cache.hide()
            return False
        cache.update_from_ghost_mesh(mesh)
        cache.show()
        return True

    def sync_preview_mesh_cache_for_root(self, root: Any | None) -> bool:
        cache = get_preview_mesh_cache()
        if not self._session.active or self._session.hit is None:
            cache.hide()
            return False
        mesh = self.build_active_ghost_mesh(root)
        if mesh is None:
            cache.hide()
            return False
        cache.update_from_ghost_mesh(mesh)
        cache.show()
        return True

    @staticmethod
    def hover_face_key(hit: HoverHitResult | None) -> tuple[str, object | None]:
        if hit is None:
            return "", None
        sid = str(getattr(getattr(hit, "space", None), "id", "") or "").strip()
        return sid, hit.face

    def _filter_hover_hit(self, hit: HoverHitResult | None) -> HoverHitResult | None:
        if hit is None:
            return None
        if resolve_preview_spec(self._preview_mode, hit.face) is None:
            return None
        filtered = process_face_hover(hit.face, hit)
        if filtered is not None:
            self._session.target_face = filtered.face
        return filtered

    def reset_hover_face_key(self) -> None:
        self._last_hover_face_key = None

    def clear_preview_visual(self) -> None:
        """隐藏 ghost；悬停面切换时先清旧预览。"""
        get_preview_mesh_cache().hide()
        self._session.ghost_draw_logged = False

    def show(
        self,
        hit: HoverHitResult | None,
        *,
        root: Any | None = None,
    ) -> PreviewTickResult:
        """悬停面已变化：清旧 ghost → 更新会话 → 显示新 ghost。"""
        self.clear_preview_visual()
        return self.draw_preview_for_hit(hit, root=root)

    def draw_preview_for_hit(
        self,
        hit: HoverHitResult | None,
        *,
        root: Any | None = None,
    ) -> PreviewTickResult:
        """悬停面已变化：更新会话并绘制新 ghost（调用方须先 ``clear_preview_visual``）。"""
        filtered = self._filter_hover_hit(hit)
        new_key = self.hover_face_key(filtered)
        prev_active = self._session.active
        if filtered is not None:
            self._session.hit = filtered
        stack = self.stack_offset_for_space(root) if filtered is not None else 0.0
        update_session_from_hit(
            self._session,
            filtered,
            stack_offset_mm=stack,
        )
        entered = not prev_active and self._session.active
        cleared = prev_active and not self._session.active
        drew = False
        if self._session.active:
            drew = self.sync_preview_mesh_cache_for_root(root)
        if entered and self._session.hit is not None:
            h = self._session.hit
            log_hover_face_detected(h.face)
            log_hover_face_occupancy(
                h.face,
                h.space,
                occupied=leaf_topology_occupied(h.space),
            )
        elif cleared:
            log_hover_clear()
        self._last_hover_face_key = new_key
        needs_repaint = entered or cleared or drew
        return PreviewTickResult(
            changed=True,
            entered=entered,
            cleared=cleared,
            needs_repaint=needs_repaint,
        )

    def apply_hover_hit(
        self,
        hit: HoverHitResult | None,
        *,
        root: Any | None = None,
        **_: Any,
    ) -> PreviewTickResult:
        """悬停面切换：先清旧预览，再绘新预览。"""
        filtered = self._filter_hover_hit(hit)
        new_key = self.hover_face_key(filtered)
        if new_key == self._last_hover_face_key:
            return PreviewTickResult()
        self.clear_preview_visual()
        return self.draw_preview_for_hit(hit, root=root)

    def _metadata_preview_spec(self, tool_mode: Any) -> InteractionPreviewSpec | None:
        from ui.cabinet_space.tool_modes import ADD_SIDE_PANEL_TOOL_MODES, ToolMode

        pf = face_for_tool_mode(tool_mode)
        if pf is not None:
            return resolve_preview_spec(self._preview_mode, pf)
        if tool_mode == ToolMode.SELECT and self._session.hit is not None:
            return resolve_preview_spec(self._preview_mode, self._session.hit.face)
        return None

    def sync_placement_metadata(
        self,
        root: Any | None,
        *,
        engine: Any,
        tool_mode: Any,
        select_tool_mode: Any = None,
        add_panel_tool_mode: Any = None,
    ) -> None:
        """刷新叶 ``Space.metadata``（由当前预览规格提供 ``board_for_validate``）。"""
        _ = select_tool_mode, add_panel_tool_mode
        if root is None:
            return
        from core.space.space_placement_sync import refresh_leaf_placement_ui_metadata
        from ui.cabinet_space.tool_modes import ADD_SIDE_PANEL_TOOL_MODES, ToolMode

        self.configure_hover_context(self._interaction_mode, tool_mode)
        spec = None
        if tool_mode in ADD_SIDE_PANEL_TOOL_MODES or tool_mode == ToolMode.SELECT:
            spec = self._metadata_preview_spec(tool_mode)

        if spec is None:
            refresh_leaf_placement_ui_metadata(root, board_for_space=None)
            return

        thickness = spec.default_thickness_mm
        refresh_leaf_placement_ui_metadata(
            root,
            engine=engine,
            board_for_space=lambda sp, _s=spec, _t=thickness: _s.board_for_validate(
                sp, _t
            ),
        )

    def mark_ghost_drawn(self) -> None:
        if self._session.ghost_draw_logged:
            return
        spec = self.active_spec()
        if spec is not None:
            log_view3d_draw_preview_ghost(spec.mode, spec.face)
        self._session.ghost_draw_logged = True

    def clear(self) -> bool:
        self.clear_preview_visual()
        was = clear_session(self._session)
        self.reset_hover_face_key()
        if was:
            log_hover_clear()
        return was

    def click_confirmed(self) -> bool:
        return self.active

    def absorb_detected_hit(
        self,
        hit: HoverHitResult | None,
        *,
        root: Any | None = None,
        **_: Any,
    ) -> None:
        if hit is None:
            return
        if resolve_preview_spec(self._preview_mode, hit.face) is None:
            return
        hit = process_face_hover(hit.face, hit)
        if hit is None:
            return
        stack = self.stack_offset_for_space(root)
        new_key = self.hover_face_key(hit)
        if new_key == self._last_hover_face_key:
            update_session_from_hit(self._session, hit, stack_offset_mm=stack)
            return
        self.clear_preview_visual()
        update_session_from_hit(self._session, hit, stack_offset_mm=stack)
        if self._session.active:
            self.sync_preview_mesh_cache_for_root(root)
        self._last_hover_face_key = new_key


__all__ = [
    "PreviewManager",
    "PreviewTickResult",
]
