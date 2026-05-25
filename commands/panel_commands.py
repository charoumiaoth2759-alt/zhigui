# -*- coding: utf-8 -*-
"""
板件相关命令：经 ``core.panel`` 修改 Space / 挂载板件，不直接 import Qt。

**锚定板件**（LEFT/RIGHT/…）：统一 ``handle_add_panel`` + ``PanelRoleSpec`` 注册表；
禁止 ``handle_add_left_panel`` / ``handle_add_right_panel`` 并列实现。

用户交互须经 ``CabinetInteractionManager.submit_add_panel(face=)``。
"""

from __future__ import annotations

from typing import Any

from core.events.event_types import BuiltinEventTopics
from core.panel import cabinet_panel_tree_cmd as _pcmd
from core.panel.panel_role_spec import (
    is_mount_panel_command,
    iter_mount_panel_command_names,
    spec_for_command,
)

from .command_result import CommandResult
from .command_types import CommandHandler


def _invoke(cmd_label: str, fn, ctx: dict[str, Any], payload: Any) -> CommandResult:
    try:
        fn(ctx, payload)
        return CommandResult(True, {"handler": cmd_label}, [])
    except Exception as e:
        return CommandResult(False, {"handler": cmd_label, "error": str(e)}, [])


def handle_add_panel(
    ctx: dict[str, Any],
    payload: Any | None = None,
    *,
    face: Any | None = None,
) -> CommandResult:
    """程序化入口：``Face`` → InteractionManager 或 ``CommandFactory`` + UndoStack。"""
    mgr = ctx.get("cabinet_interaction_manager")
    if mgr is not None:
        from ui.interaction.cabinet_interaction_sources import CabinetInteractionSource

        return mgr.submit_add_panel(
            payload,
            source=CabinetInteractionSource.INTERNAL_LEGACY_DISPATCH,
            face=face,
        )

    stack = ctx.get("cabinet_undo_stack")
    from commands.command_factory import CommandFactory

    try:
        cmd = CommandFactory.create_add_panel_command(ctx, payload, face=face)
    except (ValueError, RuntimeError) as e:
        return CommandResult(
            False,
            {"handler": "handle_add_panel", "error": str(e)},
            [],
        )

    handler_tag = {"handler": "handle_add_panel", "suppress_default_space_changed": True}
    if stack is not None:
        if stack.push(cmd):
            return cmd.last_result or CommandResult(True, handler_tag, [])
        return cmd.last_result or CommandResult(
            False,
            {"handler": "handle_add_panel", "error": "command failed"},
            [],
        )

    if cmd.execute():
        return CommandResult(True, handler_tag, [])
    return cmd.last_result or CommandResult(
        False,
        {"handler": "handle_add_panel", "error": "command failed"},
        [],
    )


def handle_add_left_panel(ctx: dict[str, Any], payload: Any | None = None) -> CommandResult:
    """兼容别名 → ``handle_add_panel``（``FaceType.LEFT``）。"""
    from core.space.space_face_occupancy import FaceType

    return handle_add_panel(ctx, payload, face=FaceType.LEFT)


def handle_add_right_panel(ctx: dict[str, Any], payload: Any | None = None) -> CommandResult:
    """兼容别名 → ``handle_add_panel``（``FaceType.RIGHT``）。"""
    from core.space.space_face_occupancy import FaceType

    return handle_add_panel(ctx, payload, face=FaceType.RIGHT)


def add_top_panel(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("add_top_panel", _pcmd.add_top_panel, ctx, payload)


def add_bottom_panel(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("add_bottom_panel", _pcmd.add_bottom_panel, ctx, payload)


def add_back_panel(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("add_back_panel", _pcmd.add_back_panel, ctx, payload)


def add_door(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("add_door", _pcmd.add_door, ctx, payload)


def add_drawer(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("add_drawer", _pcmd.add_drawer, ctx, payload)


def apply_add_or_modify(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("apply_add_or_modify", _pcmd.apply_add_or_modify, ctx, payload)


def save_to_library(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("save_to_library", _pcmd.save_to_library, ctx, payload)


def finish_cabinet_design(ctx: dict[str, Any], payload: Any = None) -> CommandResult:
    return _invoke("finish_cabinet_design", _pcmd.finish_cabinet_design, ctx, payload)


def register_handlers() -> dict[str, CommandHandler]:
    """注册 command_name → 处理函数（锚定板件由 ``PanelRoleSpec`` 驱动）。"""
    handlers: dict[str, CommandHandler] = {
        "add_top_panel": add_top_panel,
        "add_bottom_panel": add_bottom_panel,
        "add_back_panel": add_back_panel,
        "add_door": add_door,
        "add_drawer": add_drawer,
        "apply_add_or_modify": apply_add_or_modify,
        "save_to_library": save_to_library,
        "finish_cabinet_design": finish_cabinet_design,
    }
    for cmd_name in iter_mount_panel_command_names():
        sp = spec_for_command(cmd_name)
        if sp is None:
            continue
        ft = sp.face

        def _handler(
            ctx: dict[str, Any],
            payload: Any = None,
            *,
            _face=ft,
        ) -> CommandResult:
            return handle_add_panel(ctx, payload, face=_face)

        handlers[cmd_name] = _handler
    return handlers


__all__ = [
    "handle_add_panel",
    "handle_add_left_panel",
    "handle_add_right_panel",
    "is_mount_panel_command",
    "register_handlers",
]
