# -*- coding: utf-8 -*-
"""
柜体可撤销命令工厂（commands 层，无 Qt）。

锚定板件：``panel_pipeline.create_add_panel_command``（``PanelRoleSpec`` 配置驱动）。
"""

from __future__ import annotations

from typing import Any

from commands.cabinet.add_board_command import AddBoardCommand
from commands.cabinet_edit_command import (
    CabinetEditEnvironment,
    DispatchCabinetEditCommand,
)
from core.panel.panel_pipeline import create_add_panel_command
from core.space.face_selection_snapshot import FaceSelectionSnapshot
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space


def _thickness_mm(payload: Any) -> float:
    if not isinstance(payload, dict):
        return 18.0
    raw = payload.get("thickness")
    if raw is None:
        return 18.0
    try:
        t = float(raw)
    except (TypeError, ValueError):
        return 18.0
    return max(6.0, min(t, 80.0))


def resolve_attachment_space(ctx: dict[str, Any]) -> Space | None:
    """
    遗留脚本入口：仅 ``root_space`` / ``project.root_space``（禁止 ``current_space`` 与 remain 重定向）。

    悬停点击须用 ``FaceSelectionSnapshot`` + ``cabinet.find_space(space_id)``。
    """
    rs = ctx.get("root_space")
    if isinstance(rs, Space):
        return rs
    proj = ctx.get("project")
    if proj is not None:
        rs = getattr(proj, "root_space", None)
        if isinstance(rs, Space):
            return rs
    return None


class CommandFactory:
    """可撤销柜体编辑命令的统一创建入口。"""

    @staticmethod
    def create_add_panel_command(
        ctx: dict[str, Any],
        payload: Any | None = None,
        *,
        face: FaceType | None = None,
        face_snapshot: FaceSelectionSnapshot | None = None,
    ) -> AddBoardCommand:
        """
        ``FaceSelectionSnapshot`` → ``AddBoardCommand``。

        悬停点击须传 ``face_snapshot``；脚本/组件库可传 ``face``（工厂层合成快照，不读 PreviewManager）。
        """
        return create_add_panel_command(
            ctx,
            payload,
            face=face,
            face_snapshot=face_snapshot,
        )

    @staticmethod
    def create_add_left_panel_command(
        ctx: dict[str, Any], payload: Any | None = None
    ) -> AddBoardCommand:
        return CommandFactory.create_add_panel_command(
            ctx, payload, face=FaceType.LEFT
        )

    @staticmethod
    def create_add_right_panel_command(
        ctx: dict[str, Any], payload: Any | None = None
    ) -> AddBoardCommand:
        return CommandFactory.create_add_panel_command(
            ctx, payload, face=FaceType.RIGHT
        )

    @staticmethod
    def create_add_door_command(
        env: CabinetEditEnvironment,
        payload: Any | None = None,
    ) -> DispatchCabinetEditCommand:
        return DispatchCabinetEditCommand(env, "add_door", payload)

    @staticmethod
    def create_add_drawer_command(
        env: CabinetEditEnvironment,
        payload: Any | None = None,
    ) -> DispatchCabinetEditCommand:
        return DispatchCabinetEditCommand(env, "add_drawer", payload)


__all__ = ["CommandFactory", "_thickness_mm", "resolve_attachment_space"]
