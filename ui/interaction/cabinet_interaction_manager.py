# -*- coding: utf-8 -*-
"""
CabinetInteractionManager — 统一交互入口（禁止 Viewport 内散乱 hover / 字符串 side）。

**悬停 + 提交**::

    Mouse Move
      → ``pick_face``（``pick_face_hover_at_screen`` + 面过滤）
      → ``HoverCache.update``（未变化则跳过）
      → ``current_hover`` / ``_hover_face_type``
      → ``preview_manager.show``（ghost / 盒体 metadata）

**确认加板 → 场景**::

    Click / Shortcut（``on_face_clicked``）
      → 瞬间 ``FaceSelectionSnapshot``（禁止读可变 ``hover``）
      → InteractionManager.confirm_viewport_hover_click
      → CommandFactory → UndoStack → AddBoardCommand
      → SOLVE_COMPLETED（incremental_add_panels）
      → Incremental Scene Update（View3D / ParamSpace append，非全量 rebuild）

轨道旋转、OCC 解锁、Ctrl 盒体切换仍在 Viewport 原路径，不经本管理器改写。

**解耦**::

    PreviewManager  = UI 瞬态（``HoverHitResult`` 可变）
    Command pipeline = ``FaceSelectionSnapshot`` 不可变

    二者禁止共享可变 face；点击确认时冻结 ``current_hover_result`` 的 ``space_id`` / ``face_type``。
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QTimer

from commands.command_factory import CommandFactory
from commands.command_result import CommandResult

from .cabinet_interaction_sources import CabinetInteractionSource
from core.space.enums import FaceType

from .hover_cache import HoverCache
from .hover_detector import (
    HoverDetector,
    Main3DHoverDetector,
    ParamSpaceHoverDetector,
    VIEWPORT_MAIN_3D,
    VIEWPORT_PARAM_SPACE,
)
from .hover_state import HoverState
from .interaction_mode import InteractionMode
from .face_interaction import process_face_click, process_face_hover
from .preview_manager import PreviewManager, PreviewTickResult
from .preview_spec import effective_preview_mode, resolve_preview_spec
from core.space.face_selection_snapshot import FaceSelectionSnapshot
from view.interaction.hover_hit_result import HoverHitResult
from core.space.space_picker import HoverResult

from core.space.cabinet_ops_lock import (
    CABINET_OPS_LOCKED_HINT,
    cabinet_command_should_respect_ops_lock,
    ctx_cabinet_ops_locked,
)

_SOURCES_SYNC_ADD_PANEL_TOOL_MODE = frozenset(
    {
        CabinetInteractionSource.UI_COMPONENT_LIBRARY_SLOT,
        CabinetInteractionSource.UI_COMPONENT_LIBRARY_ICON,
        CabinetInteractionSource.MAIN_3D_SHORTCUT,
        CabinetInteractionSource.TOOLBAR,
    }
)

_SOURCES_REQUIRE_FACE_SNAPSHOT = frozenset(
    {
        CabinetInteractionSource.MAIN_3D_HOVER_CLICK,
        CabinetInteractionSource.PARAM_SPACE_TOOL,
    }
)

class CabinetInteractionManager:
    """
    悬停控制器（HoverController）：持有一个 ``CabinetDesignView``（或等价宿主）。

    ``hover_cache`` 在 ``handle_viewport_hover_move`` 中判定目标是否变化，
    未变化时不刷新预览、不触发高频悬停日志。
    """

    # 离开 hover 后延迟清除预览（60~120ms，工业 CAD 防抖动）
    HOVER_CLEAR_DELAY_MS = 80

    def __init__(self, host: Any) -> None:
        self._host = host
        self._preview = PreviewManager()
        self._detectors: dict[str, HoverDetector] = {}
        self.current_hover: HoverHitResult | None = None
        self.current_hover_result: HoverResult | None = None
        self._hover_face_type: FaceType | None = None
        self.hover_cache = HoverCache()
        self.hover_state = HoverState()
        self.hover_clear_timer = QTimer(host)
        self.hover_clear_timer.setSingleShot(True)
        self.hover_clear_timer.timeout.connect(self.clear_hover_preview)

    @property
    def preview(self) -> PreviewManager:
        return self._preview

    @property
    def preview_manager(self) -> PreviewManager:
        return self._preview

    def register_main_3d_viewport(self, view3d: Any) -> None:
        self._detectors[VIEWPORT_MAIN_3D] = Main3DHoverDetector(view3d)

    def register_param_space_viewport(self, param_view: Any) -> None:
        self._detectors[VIEWPORT_PARAM_SPACE] = ParamSpaceHoverDetector(param_view)

    def unregister_viewport(self, viewport_id: str) -> None:
        self._detectors.pop(viewport_id, None)

    def _detector(self, viewport_id: str) -> HoverDetector | None:
        return self._detectors.get(viewport_id)

    def _reset_hover_tracking(self) -> None:
        self.hover_cache.clear()
        self.current_hover = None
        self._hover_face_type = None
        self.hover_state.hovered_space_id = None
        self.hover_state.hovered_face_type = None
        self.hover_state.preview_visible = False
        self._preview.reset_hover_face_key()

    def _stop_hover_clear_timer(self) -> None:
        if self.hover_clear_timer.isActive():
            self.hover_clear_timer.stop()

    def _schedule_hover_clear(self) -> None:
        self._stop_hover_clear_timer()
        self.hover_clear_timer.start(self.HOVER_CLEAR_DELAY_MS)

    def clear_hover_preview(self) -> None:
        """延迟到期：卸 ghost + 复位 hover 会话。"""
        self._stop_hover_clear_timer()
        self.preview_manager.clear()
        self.current_hover = None
        self.current_hover_result = None
        self._reset_hover_tracking()
        host = self._host
        if host is not None and hasattr(host, "update"):
            host.update()

    @staticmethod
    def _hover_identity(
        hover_face: HoverHitResult | None,
    ) -> tuple[str | None, FaceType | None]:
        if hover_face is None:
            return None, None
        sid = str(getattr(getattr(hover_face, "space", None), "id", "") or "").strip()
        return sid or None, hover_face.face if isinstance(hover_face.face, FaceType) else None

    def pick_face(
        self,
        viewport_id: str,
        screen_x: float,
        screen_y: float,
        *,
        host_mode: InteractionMode,
        tool_mode: Any,
    ) -> HoverHitResult | None:
        """屏幕拾取可预览悬停面（``pick_face_hover_at_screen`` + 面过滤）。"""
        det = self._detector(viewport_id)
        if det is None:
            return None
        raw = det.detect_hover(screen_x, screen_y)
        preview_mode = effective_preview_mode(host_mode, tool_mode)
        if raw is None:
            return None
        if resolve_preview_spec(preview_mode, raw.face) is None:
            return None
        return process_face_hover(raw.face, raw)

    def _hover_tool_allowed(self, tool_mode: Any) -> bool:
        from ui.cabinet_space.tool_modes import ToolMode

        return tool_mode in (
            ToolMode.SELECT,
            ToolMode.ADD_LEFT_PANEL,
            ToolMode.ADD_RIGHT_PANEL,
        )

    def handle_viewport_hover_move(
        self,
        viewport_id: str,
        screen_x: float,
        screen_y: float,
        *,
        viewport: Any,
        tool_mode: Any,
        drag_mode: str,
        mouse_pos: Any | None = None,
    ) -> PreviewTickResult:
        """
        Viewport → HoverDetector → PreviewManager（Viewport 不直接拾取/不维护会话）。
        """
        if drag_mode in ("orbit", "pan"):
            return PreviewTickResult()
        if not self._hover_tool_allowed(tool_mode):
            return PreviewTickResult()

        self._stop_hover_clear_timer()

        det = self._detector(viewport_id)
        if det is None:
            return PreviewTickResult()

        host_mode = getattr(self._host, "_interaction_mode", InteractionMode.SELECT)
        if not isinstance(host_mode, InteractionMode):
            host_mode = InteractionMode.SELECT

        hover_face = self.pick_face(
            viewport_id,
            screen_x,
            screen_y,
            host_mode=host_mode,
            tool_mode=tool_mode,
        )
        if hover_face is None:
            # 防止 OCC selection 抖动
            self.hover_cache.leave_pending_frames += 1
            # 允许短暂丢失 hover
            if self.hover_cache.leave_pending_frames < 6:  # 扩大防抖窗口覆盖面边缘间隙
                return PreviewTickResult()
            # 真正 leave
            if self.hover_cache.last_space_id is not None:
                print("[HOVER] leave")
            self.hover_cache.clear()
            self.current_hover = None
            self._schedule_hover_clear()
            _ = mouse_pos
            return PreviewTickResult()

        space_id = str(getattr(hover_face.space, "id", "") or "").strip() or None
        face_type = (
            hover_face.face if isinstance(hover_face.face, FaceType) else None
        )
        # 进入有效 hover：复位 leave 计数（须在 changed 判断之前）
        self.hover_cache.leave_pending_frames = 0

        changed = (
            self.hover_cache.last_space_id != space_id
            or self.hover_cache.last_face_type != face_type
        )
        if not changed:
            return PreviewTickResult()

        self.hover_cache.last_space_id = space_id
        self.hover_cache.last_face_type = face_type

        print(
            f"[HOVER] changed "
            f"space={space_id} "
            f"face={face_type}"
        )

        self.current_hover = hover_face
        self._hover_face_type = face_type

        root = getattr(viewport, "_cabinet_space", None) or getattr(
            viewport, "_root", None
        )
        engine = getattr(viewport, "_space_pick_engine", None)
        if engine is None and viewport_id == VIEWPORT_PARAM_SPACE:
            from core.space.cabinet_ops_lock import cabinet_space_constraint_engine

            engine = cabinet_space_constraint_engine()

        self.preview_manager.set_interaction_mode(host_mode)
        self.preview_manager.sync_placement_metadata(
            root,
            engine=engine,
            tool_mode=tool_mode,
        )

        tick = self.preview_manager.show(hover_face, root=root)
        self.hover_state.hovered_space_id = space_id
        self.hover_state.hovered_face_type = face_type
        self.hover_state.preview_visible = self.preview_manager.active
        _ = mouse_pos
        self._sync_current_hover_result()
        return tick

    def _sync_current_hover_result(self) -> None:
        """由 ``current_hover`` 冻结 ``space_id`` + ``face_type``（供点击/命令使用）。"""
        hover_face = self.current_hover
        if hover_face is None:
            self.current_hover_result = None
            return
        sid = str(getattr(getattr(hover_face, "space", None), "id", "") or "").strip()
        if not sid:
            self.current_hover_result = None
            return
        self.current_hover_result = HoverResult(
            space_id=sid,
            face_type=hover_face.face,
        )

    def handle_viewport_leave(self, viewport_id: str, *, viewport: Any) -> bool:
        """指针离开 Viewport：延迟清除预览（避免掠过边缘时 hover 闪断）。"""
        _ = viewport_id, viewport
        self._schedule_hover_clear()
        return False

    def handle_drag_release(
        self,
        viewport_id: str,
        screen_x: float,
        screen_y: float,
        *,
        viewport: Any,
        tool_mode: Any,
        mouse_pos: Any | None = None,
    ) -> None:
        """
        拖拽旋转结束后主动重触发 hover 检测。

        drag release 后 preview 被清空，但鼠标可能已静止在某个面上，
        若不主动检测则用户须再次移动才能恢复高亮。
        """
        self.hover_cache.leave_pending_frames = 0
        self.handle_viewport_hover_move(
            viewport_id,
            screen_x,
            screen_y,
            viewport=viewport,
            tool_mode=tool_mode,
            drag_mode="",          # 非 orbit/pan，允许 hover
            mouse_pos=mouse_pos,
        )

    def on_face_clicked(
        self,
        viewport_id: str,
        screen_x: float,
        screen_y: float,
        *,
        viewport: Any,
        source: CabinetInteractionSource,
        tool_mode: Any,
    ) -> bool:
        """``mousePressEvent`` 确认面点击：先冻结 ``FaceSelectionSnapshot``，再提交命令。"""
        return self.confirm_viewport_hover_click(
            viewport_id,
            screen_x,
            screen_y,
            viewport=viewport,
            source=source,
            tool_mode=tool_mode,
        )

    def confirm_viewport_hover_click(
        self,
        viewport_id: str,
        screen_x: float,
        screen_y: float,
        *,
        viewport: Any,
        source: CabinetInteractionSource,
        tool_mode: Any,
    ) -> bool:
        """悬停确认 → 加板；仅认 ``current_hover_result`` 冻结的 ``space_id`` / ``face_type``。"""
        _ = viewport_id, screen_x, screen_y
        hover = self.current_hover_result
        self.current_hover_result = None
        if hover is None:
            # space_id / face_type 为 None 时静默丢弃，不进入命令管线
            return False
        if hover.space_id is None or hover.face_type is None:
            # 点击落在空白区域（None None），静默丢弃
            return False

        clicked_space_id = hover.space_id
        clicked_face_type = hover.face_type

        host_mode = getattr(self._host, "_interaction_mode", InteractionMode.SELECT)
        if not isinstance(host_mode, InteractionMode):
            host_mode = InteractionMode.SELECT
        preview_mode = effective_preview_mode(host_mode, tool_mode)
        if resolve_preview_spec(preview_mode, clicked_face_type) is None:
            return False

        clicked = FaceSelectionSnapshot.from_pick(
            space_id=clicked_space_id,
            face_type=clicked_face_type,
        )

        from core.space.face_click_resolve import find_space
        from .face_interaction import block_occupied_space_target

        host = self._host
        dispatcher = getattr(host, "_cmd_dispatcher", None)
        cabinet_ctx = (
            getattr(dispatcher, "context", None)
            if dispatcher is not None
            else None
        )
        if isinstance(cabinet_ctx, dict):
            target_space = find_space(cabinet_ctx, clicked_space_id)
            if block_occupied_space_target(target_space):
                self.clear_preview()
                return False

        hit = self.current_hover or self.preview_manager.hit
        if hit is not None:
            root = getattr(viewport, "_cabinet_space", None) or getattr(
                viewport, "_root", None
            )
            self.preview_manager.absorb_detected_hit(
                hit,
                root=root,
                cabinet=cabinet_ctx if isinstance(cabinet_ctx, dict) else None,
            )

        return process_face_click(
            clicked,
            manager=self,
            source=source,
            payload={},
            frozen_hover=hover,
        )

    def confirm_face_click(
        self,
        viewport_id: str,
        screen_x: float,
        screen_y: float,
        *,
        viewport: Any,
        source: CabinetInteractionSource,
        tool_mode: Any,
    ) -> bool:
        """面点击确认（``confirm_viewport_hover_click`` 别名，含 occupied 最终校验）。"""
        return self.confirm_viewport_hover_click(
            viewport_id,
            screen_x,
            screen_y,
            viewport=viewport,
            source=source,
            tool_mode=tool_mode,
        )

    def clear_preview(self) -> bool:
        """立即清除（命令/工具切换等）；取消待执行的延迟清除。"""
        self._stop_hover_clear_timer()
        self.preview_manager.clear()
        self.current_hover = None
        self.current_hover_result = None
        self._reset_hover_tracking()
        return True

    def clear_preview_on_select_tool(self) -> None:
        self.preview_manager.clear()
        self.current_hover_result = None
        self._reset_hover_tracking()

    def _apply_interaction_mode_step(self, source: CabinetInteractionSource) -> None:
        if source in _SOURCES_SYNC_ADD_PANEL_TOOL_MODE:
            fn = getattr(self._host, "set_interaction_mode", None)
            if callable(fn):
                fn(InteractionMode.ADD_PANEL)

    def _submit_from_preview_spec(
        self,
        spec: Any,
        payload: Any | None,
        *,
        source: CabinetInteractionSource,
    ) -> CommandResult:
        """按 ``InteractionPreviewSpec`` 的 ``face`` / ``command_name`` 提交（无硬编码侧）。"""
        from core.panel.side_panel_spec import spec_for_command

        sp = spec_for_command(getattr(spec, "command_name", ""))
        face = getattr(spec, "face", None)
        if sp is not None:
            face = sp.face
        return self.submit_add_panel(payload, source=source, face=face)

    def submit_add_panel(
        self,
        payload: Any | None = None,
        *,
        source: CabinetInteractionSource,
        face: Any | None = None,
        face_snapshot: FaceSelectionSnapshot | None = None,
    ) -> CommandResult:
        """
        统一加侧板：仅 ``FaceSelectionSnapshot`` 进入命令管线。

        悬停点击源必须传入 ``face_snapshot``；组件库等路径在工厂层合成快照，不读 ``PreviewManager``。
        """
        from commands.cabinet.add_panel_debug import add_panel_print, verify_add_panel_pipeline
        from commands.cabinet.face_command_input import require_command_face_snapshot
        from core.panel.side_panel_spec import spec_for_face
        from core.space.face_click_resolve import find_space
        from core.space.space_face_occupancy import FaceType

        add_panel_print("[ADD_PANEL] start")

        host = self._host
        dispatcher = getattr(host, "_cmd_dispatcher", None)
        stack = getattr(host, "_cabinet_undo_stack", None)
        if dispatcher is None:
            return CommandResult(False, {"error": "no dispatcher"}, [])
        if stack is None:
            return CommandResult(
                False,
                {"error": "cabinet_undo_pipeline_inactive"},
                [],
            )

        ctx = dispatcher.context
        if source in _SOURCES_REQUIRE_FACE_SNAPSHOT and face_snapshot is None:
            return CommandResult(
                False,
                {"error": "face_snapshot required (decouple hover from command)"},
                [],
            )

        try:
            snap = require_command_face_snapshot(
                face_snapshot=face_snapshot,
                cabinet=ctx,
                face=face if isinstance(face, FaceType) else None,
                allow_programmatic_synthesis=source
                not in _SOURCES_REQUIRE_FACE_SNAPSHOT,
            )
        except (TypeError, ValueError) as e:
            return CommandResult(False, {"error": str(e)}, [])

        ft = snap.face_type
        add_panel_print(f"[ADD_PANEL] face_type={ft}")
        op_space = find_space(ctx, snap.space_id)
        if op_space is not None:
            add_panel_print(f"[ADD_PANEL] space.id={op_space.id}")
        else:
            add_panel_print("[ADD_PANEL] space.id=<unresolved>")

        from .face_interaction import block_occupied_space_target

        if block_occupied_space_target(op_space):
            return CommandResult(False, {"error": "occupied_space"}, [])

        sp = spec_for_face(ft)
        cmd_name = sp.command_name if sp else "add_left_panel"

        if cabinet_command_should_respect_ops_lock(
            cmd_name
        ) and ctx_cabinet_ops_locked(ctx, space_id=snap.space_id):
            return CommandResult(False, {"error": CABINET_OPS_LOCKED_HINT}, [])

        self._apply_interaction_mode_step(source)
        try:
            add_panel_print("[ADD_PANEL] create panel")
            cmd = CommandFactory.create_add_panel_command(
                ctx,
                payload,
                face_snapshot=snap,
            )
            add_panel_print("[ADD_PANEL] panel created")
        except (ValueError, RuntimeError) as e:
            add_panel_print(f"[ADD_PANEL] create panel failed: {e}")
            return CommandResult(False, {"error": str(e)}, [])
        if stack.push(cmd):
            self._inherit_active_leaf_after_panel(ctx, snap, cmd)
            verify_add_panel_pipeline(ctx, cmd)
            return cmd.last_result or CommandResult(True, {}, [])
        return cmd.last_result or CommandResult(
            False,
            {"error": "command failed"},
            [],
        )

    def _inherit_active_leaf_after_panel(
        self,
        ctx: dict[str, Any],
        snap: FaceSelectionSnapshot,
        cmd: Any,
    ) -> None:
        """
        加板成功后继承 ``active_leaf``::

            LEFT  → ``split_result.right_space``
            RIGHT → ``split_result.left_space``
        """
        split_record = getattr(cmd, "_split_record", None)
        if split_record is None:
            return
        from core.space.usable_space_resolver import (
            active_leaf_from_side_split,
            focus_ctx_operating_space,
        )

        active_leaf = active_leaf_from_side_split(snap.face_type, split_record)
        if active_leaf is not None:
            focus_ctx_operating_space(ctx, active_leaf)

    def submit_add_left_panel(
        self,
        payload: Any | None = None,
        *,
        source: CabinetInteractionSource,
    ) -> CommandResult:
        from core.space.space_face_occupancy import FaceType

        return self.submit_add_panel(payload, source=source, face=FaceType.LEFT)

    def submit_add_right_panel(
        self,
        payload: Any | None = None,
        *,
        source: CabinetInteractionSource,
    ) -> CommandResult:
        from core.space.space_face_occupancy import FaceType

        return self.submit_add_panel(payload, source=source, face=FaceType.RIGHT)


HoverController = CabinetInteractionManager

__all__ = ["CabinetInteractionManager", "HoverController"]