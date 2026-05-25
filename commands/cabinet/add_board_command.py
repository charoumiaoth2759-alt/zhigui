# -*- coding: utf-8 -*-
"""
添加锚定侧板（``LEFT_SIDE`` / ``RIGHT_SIDE``）的可撤销命令。

- 构造：``AddBoardCommand(cabinet, face_snapshot)`` — 仅不可变点击快照
- ``execute``：``SpaceSplitter.split`` → ``mount_side_panel`` → 求解 → ``SOLVE_COMPLETED``
- ``undo``：``detach_side_panel`` → ``merge_children``（若本命令曾切分）同一 ``Panel`` 引用

禁止在命令内 raycast / pick / 读取 HoverManager 或 ``current_space`` 悬停状态。
"""

from __future__ import annotations

from typing import Any

from core.space.face_click_resolve import cabinet_find_space_callable
from core.space.face_selection_snapshot import (
    FaceSelectionSnapshot,
    normalize_command_face_type,
)
from core.space.splitter import SpaceSplitResult, split_space_by_face

from commands.cabinet_event_bridge import (
    clear_cabinet_hover_preview,
    resolve_view3d_from_ctx,
    run_attach_solver_and_publish,
)
from commands.command_result import CommandResult
from core.events.event_bus import publish as bus_publish
from core.events.event_types import BuiltinEventTopics, Event
from core.panel.cabinet_space_panel_cmd import (
    detach_side_panel,
    mount_side_panel,
)
from core.panel.panel_models import Panel
from core.panel.panel_role_spec import spec_for_face
from core.panel.side_panel_spec import spec_for_panel
from core.space.space_models import Space

from .add_panel_debug import (
    add_panel_print,
    verify_cabinet_boards_registered,
    verify_cabinet_boards_unregistered,
)
from .base_command import BaseCommand


def _publish_solve_completed_incremental_add(
    panel: Panel,
    target_space: Space,
    *,
    spec: Any | None = None,
) -> None:
    from core.space.space_face_occupancy import FaceType

    payload: dict[str, Any] = {
        "incremental_add_panels": [panel],
        "incremental_target_space": target_space,
    }
    if spec is not None:
        face = getattr(spec, "face", None)
        if face is FaceType.RIGHT:
            payload["stats_action"] = "add_right_panel"
        elif face is FaceType.LEFT:
            payload["stats_action"] = "add_left_panel"
    bus_publish(
        Event(
            BuiltinEventTopics.SOLVE_COMPLETED,
            payload,
            immediate=True,
        )
    )


def _publish_solve_completed_incremental_remove(
    panel_id: str,
    target_space: Space,
) -> None:
    bus_publish(
        Event(
            BuiltinEventTopics.SOLVE_COMPLETED,
            {
                "incremental_remove_panel_ids": [str(panel_id)],
                "incremental_target_space": target_space,
            },
            immediate=True,
        )
    )


def _resolve_root(cabinet: dict[str, Any], space: Space) -> Space:
    rs = cabinet.get("root_space")
    if isinstance(rs, Space):
        return rs
    proj = cabinet.get("project")
    if proj is not None:
        rs = getattr(proj, "root_space", None)
        if isinstance(rs, Space):
            return rs
    return space.root


def _rebuild_after_split(
    cabinet: dict[str, Any], space: Space, anchor: Space | None
) -> None:
    from core.space.space_consistency_manager import rebuild_after_solver

    root = _resolve_root(cabinet, space)
    rebuild_after_solver(root=root, ctx=cabinet)


def _resolve_mount_space(
    attachment: Space,
    split_result: SpaceSplitResult | None,
) -> Space:
    """侧板挂到切分窄条子空间（occupied zone）；无切分时仍挂 attachment。"""
    if split_result is not None and split_result.occupied_space is not None:
        return split_result.occupied_space
    return attachment


def _resolve_live_space_by_id(cabinet: dict[str, Any], space: Space) -> Space:
    """
    通过 ``space.id`` 重新解析当前树中的活体节点，避免切分/重建后写到旧对象。
    """
    sid = str(getattr(space, "id", "") or "")
    if not sid:
        return space
    finder = cabinet_find_space_callable(cabinet)
    if finder is None:
        return space
    found = finder(sid)
    return found if isinstance(found, Space) else space


def _prepare_panel_for_mount(
    panel: Panel,
    mount_space: Space,
    spec: Any,
) -> None:
    """切分后按挂载叶空间重算尺寸与落位。"""
    from core.panel.panel_calculator import calculate_side_panel
    from core.panel.side_panel_solver import solve_side_panel

    calculate_side_panel(panel, mount_space)
    solve_side_panel(panel, mount_space)
    panel.space_id = mount_space.id


def _verify_execute_space_identity(
    cabinet: dict[str, Any],
    face_snapshot: FaceSelectionSnapshot,
    space: Space,
) -> None:
    """``execute`` 前校验：冻结 ``space_id`` 与 ``cabinet.find_space`` 解析结果必须一致。"""
    clicked_space_id = str(face_snapshot.space_id or "")
    resolved = cabinet_find_space_callable(cabinet)(clicked_space_id)
    resolved_id = str(getattr(resolved, "id", "") or "") if resolved is not None else ""
    bound_id = str(getattr(space, "id", "") or "")

    print("[EXECUTE VERIFY]")
    print("hover.space_id =", clicked_space_id)
    print("resolved.space.id =", resolved_id)

    if not clicked_space_id:
        raise RuntimeError(
            "AddBoardCommand execute: empty hover.space_id in face_snapshot"
        )
    if resolved is None:
        raise RuntimeError(
            "AddBoardCommand execute: cabinet.find_space returned None for "
            f"hover.space_id={clicked_space_id!r}"
        )
    if resolved_id != clicked_space_id:
        raise RuntimeError(
            "AddBoardCommand execute: hover.space_id mismatch resolved.space.id "
            f"({clicked_space_id!r} != {resolved_id!r})"
        )
    if bound_id != clicked_space_id:
        raise RuntimeError(
            "AddBoardCommand execute: command space.id mismatch hover.space_id "
            f"({bound_id!r} != {clicked_space_id!r})"
        )


def _panel_mounted_on_space(panel: Panel, space: Space) -> bool:
    from core.space.tree import walk_dfs

    for node in walk_dfs(space):
        groups = getattr(node, "panel_groups", None) or []
        for g in groups:
            pls = getattr(g, "panels", None) or []
            if panel in pls:
                return True
    return False


def _sync_cabinet_boards_with_space_tree(ctx: dict[str, Any], panel: Panel) -> None:
    """
    ``panel_groups``（挂载）→ ``register_board`` → ``sync_cabinet_boards`` 对齐 ``boards`` 与空间树。
    """
    from core.cabinet.cabinet_model import register_board, sync_cabinet_boards_from_ctx

    proj = ctx.get("project")
    if proj is not None:
        register_board(proj, panel)
    sync_cabinet_boards_from_ctx(ctx)
    verify_cabinet_boards_registered(ctx, panel)


def _unsync_cabinet_boards_with_space_tree(ctx: dict[str, Any], panel: Panel) -> None:
    """
    ``panel_groups``（卸下）→ ``unregister_board`` → ``sync_cabinet_boards`` 对齐 ``boards`` 与空间树。
    """
    from core.cabinet.cabinet_model import sync_cabinet_boards_from_ctx, unregister_board

    proj = ctx.get("project")
    if proj is not None:
        unregister_board(proj, panel)
    sync_cabinet_boards_from_ctx(ctx)
    verify_cabinet_boards_unregistered(ctx, panel)


class AddBoardCommand(BaseCommand):
    """
    在快照指定的操作 ``Space`` 上挂载锚定侧板；撤销时卸下 **同一** ``Panel`` 实例。

    ``face_snapshot`` 在构造时冻结；``execute`` / ``undo`` 不得 pick / raycast / 读悬停态。
    """

    def __init__(
        self,
        cabinet: dict[str, Any],
        face_snapshot: FaceSelectionSnapshot,
        *,
        thickness_mm: float = 18.0,
    ) -> None:
        if not isinstance(cabinet, dict):
            raise TypeError("AddBoardCommand requires a cabinet context dict")
        if not isinstance(face_snapshot, FaceSelectionSnapshot):
            raise TypeError("AddBoardCommand requires a FaceSelectionSnapshot")

        self._command_face = normalize_command_face_type(
            face_snapshot.face_type_name
        )

        clicked_space_id = face_snapshot.space_id
        space = cabinet_find_space_callable(cabinet)(clicked_space_id)
        if space is None:
            raise ValueError(
                "AddBoardCommand: cabinet.find_space failed for "
                f"space_id={clicked_space_id!r}"
            )

        spec = spec_for_face(self._command_face)
        if spec is None:
            raise ValueError(
                f"AddBoardCommand: no panel spec for face {self._command_face!r}"
            )

        from core.panel.cabinet_space_panel_cmd import build_side_panel

        panel = build_side_panel(space, spec, thickness=float(thickness_mm))

        self._cabinet = cabinet
        self._face_snapshot = face_snapshot
        self._ctx = cabinet
        # 命令面语义冻结为 face_type_name；execute 禁止读 registry / hover 面对象
        self._space = space
        self._panel = panel
        self._spec = spec_for_panel(panel)
        self._split_record: SpaceSplitResult | None = None
        self._mount_space: Space | None = None
        self.last_result: CommandResult | None = None

    @property
    def face_snapshot(self) -> FaceSelectionSnapshot:
        return self._face_snapshot

    def __repr__(self) -> str:
        return (
            f"<AddBoardCommand space_id={self._face_snapshot.space_id!r} "
            f"face={self._command_face!r} "
            f"panel={getattr(self._panel, 'id', None)!r}>"
        )

    def execute(self) -> bool:
        space = self._space
        panel = self._panel
        spec = self._spec
        _verify_execute_space_identity(
            self._cabinet, self._face_snapshot, space
        )
        from core.space.space_occupancy import leaf_topology_occupied

        if leaf_topology_occupied(space):
            print("[BLOCK] occupied space")
            self.last_result = CommandResult(
                False,
                {"handler": "AddBoardCommand", "error": "occupied_space"},
                [],
            )
            return False
        if spec is None:
            self.last_result = CommandResult(
                False,
                {"handler": "AddBoardCommand", "error": "unknown panel side spec"},
                [],
            )
            return False
        try:
            from core.space.cabinet_ops_lock import (
                reset_cabinet_ops_visual_to_locked_after_panel_added,
            )

            if not _panel_mounted_on_space(panel, space):
                add_panel_print("[ADD_PANEL] execute: split space")
                split_result = split_space_by_face(
                    space, self._face_snapshot, panel
                )
                if split_result is None:
                    raise RuntimeError(
                        f"{spec.label}添加失败：目标空间无法按板厚切分（space={getattr(space, 'id', None)!r}）"
                    )
                self._split_record = split_result
                mount_space = _resolve_mount_space(space, split_result)
                self._mount_space = mount_space
                add_panel_print("[ADD_PANEL] execute: rebuild topology")
                _rebuild_after_split(
                    self._cabinet,
                    space,
                    split_result.split_parent,
                )
                _prepare_panel_for_mount(panel, mount_space, spec)
                add_panel_print("[ADD_PANEL] execute: mount panel")
                mount_side_panel(mount_space, panel, spec)
                from core.space.usable_space_resolver import (
                    active_leaf_from_side_split,
                    focus_ctx_operating_space,
                )

                active_leaf = active_leaf_from_side_split(
                    self._command_face, split_result
                )
                if active_leaf is not None:
                    focus_ctx_operating_space(self._cabinet, active_leaf)
            elif self._mount_space is None:
                self._mount_space = space
            _sync_cabinet_boards_with_space_tree(self._cabinet, panel)
            lock_target = self._mount_space or space
            lock_target = _resolve_live_space_by_id(self._cabinet, lock_target)
            reset_cabinet_ops_visual_to_locked_after_panel_added(lock_target)
            from ui.interaction.interaction_log import log_command

            log_command(
                "AddBoardCommand",
                face=self._command_face,
                role=spec.role,
            )
            view3d = resolve_view3d_from_ctx(self._cabinet)
            if view3d is not None and self._split_record is not None:
                view3d._suppress_incremental_update = True
            add_panel_print("[ADD_PANEL] execute: solver")
            try:
                run_attach_solver_and_publish(
                    self._cabinet,
                    space,
                    face=self._command_face,
                )
            finally:
                if view3d is not None:
                    view3d._suppress_incremental_update = False
            add_panel_print("[ADD_PANEL] execute: solver done")
            if view3d is not None:
                proj = self._cabinet.get("project")
                panels = list(
                    getattr(proj, "_cabinet_display_panels", None) or []
                )
                view3d.rebuild_all_display_panels(panels)
            visual_anchor = lock_target
            if self._split_record is not None:
                split_parent = self._split_record.split_parent
                if split_parent is not None:
                    visual_anchor = split_parent
            add_panel_print("[ADD_PANEL] execute: rebuild view (SOLVE_COMPLETED)")
            _publish_solve_completed_incremental_add(
                panel, visual_anchor, spec=spec
            )
            add_panel_print("[ADD_PANEL] execute: view event published")
        except Exception as e:
            self.last_result = CommandResult(
                False, {"handler": "AddBoardCommand", "error": str(e)}, []
            )
            return False
        self.last_result = CommandResult(
            True,
            {"handler": "AddBoardCommand", "suppress_default_space_changed": True},
            [],
        )
        return True

    def undo(self) -> None:
        if self._panel is None or self._space is None:
            return
        spec = self._spec
        panel = self._panel
        detach_space = self._mount_space or self._space
        split_record = self._split_record
        visual_anchor = self._space
        if split_record is not None and split_record.split_parent is not None:
            visual_anchor = split_record.split_parent

        detach_side_panel(panel, detach_space, spec)
        if split_record is not None and split_record.split_parent is not None:
            from core.space.splitter import SpaceSplitter

            SpaceSplitter().merge_children(split_record.split_parent)
            _rebuild_after_split(
                self._cabinet,
                self._space,
                split_record.split_parent,
            )
            self._split_record = None
            self._mount_space = None
        _unsync_cabinet_boards_with_space_tree(self._cabinet, panel)
        run_attach_solver_and_publish(
            self._cabinet,
            self._space,
            face=self._command_face,
        )
        _publish_solve_completed_incremental_remove(panel.id, visual_anchor)
        clear_cabinet_hover_preview(self._cabinet)


__all__ = ["AddBoardCommand"]
