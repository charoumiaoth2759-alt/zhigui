# -*- coding: utf-8 -*-
"""
锚定板件添加统一管线（配置驱动，禁止 per-type 复制 left_panel 代码）。

链路::

    FaceSelectionSnapshot → Space → Panel → Command → Solver → Topology → Occupancy → FaceRegistry → View3D

**命令入参**仅经 ``commands.cabinet.face_command_input``（immutable snapshot）。
**禁止**从 ``PreviewManager.hit`` / payload 悬停字段进入本模块。

扩展新板件：在 ``panel_role_spec._PANEL_ROLE_SPECS`` 注册。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from core.space.face_selection_snapshot import FaceSelectionSnapshot
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space
from .panel_role_spec import PanelRoleSpec, resolve_face, spec_for_face


class PanelAddStage(str, Enum):
    """管线阶段（与日志 / 文档一致）。"""

    FACE = "Face"
    SPACE = "Space"
    PANEL = "Panel"
    COMMAND = "Command"
    SOLVER = "Solver"
    TOPOLOGY = "Topology"
    OCCUPANCY = "Occupancy"
    FACE_REGISTRY = "FaceRegistry"
    VIEW3D = "View3D"


def log_stage(stage: PanelAddStage) -> None:
    try:
        from core.cabinet_pipeline_log import log_pipeline_stage

        log_pipeline_stage(stage.value)
    except Exception:
        pass


def resolve_spec(face: FaceType | None = None, *, payload: Any | None = None) -> PanelRoleSpec:
    """Face（+ 可选 payload 厚度等）→ ``PanelRoleSpec``。"""
    ft = resolve_face(face=face, payload=payload)
    log_stage(PanelAddStage.FACE)
    sp = spec_for_face(ft)
    if sp is None:
        raise ValueError(f"no PanelRoleSpec for face {ft!r}")
    return sp


def resolve_target_space_from_snapshot(
    cabinet: dict[str, Any],
    face_snapshot: FaceSelectionSnapshot,
) -> Space:
    """由不可变快照解析操作 ``Space``。"""
    from core.space.face_click_resolve import find_space

    space = find_space(cabinet, face_snapshot.space_id)
    if space is None:
        raise ValueError(
            f"no target space for face_snapshot space_id={face_snapshot.space_id!r}"
        )
    log_stage(PanelAddStage.SPACE)
    return space


def build_panel_for_spec(
    space: Space,
    spec: PanelRoleSpec,
    *,
    thickness_mm: float = 18.0,
) -> Any:
    """Space + Spec → ``Panel``（尚未 mount / undo）。"""
    from .cabinet_space_panel_cmd import build_side_panel

    log_stage(PanelAddStage.PANEL)
    return build_side_panel(space, spec, thickness=thickness_mm)


def create_add_panel_command(
    cabinet: dict[str, Any],
    payload: Any | None = None,
    *,
    face: FaceType | None = None,
    face_snapshot: FaceSelectionSnapshot | None = None,
    thickness_mm: float | None = None,
) -> Any:
    """
    ``FaceSelectionSnapshot`` → ``AddBoardCommand``。

    点击路径必须显式传入 ``face_snapshot``（由 UI 在点击瞬间复制，非 ``PreviewManager`` 引用）。
    """
    from commands.cabinet.face_command_input import (
        create_add_board_command,
        require_command_face_snapshot,
    )
    from commands.command_factory import _thickness_mm

    snap = require_command_face_snapshot(
        face_snapshot=face_snapshot,
        cabinet=cabinet,
        face=face,
        allow_programmatic_synthesis=face_snapshot is None and face is not None,
    )
    t = float(thickness_mm) if thickness_mm is not None else _thickness_mm(payload)
    log_stage(PanelAddStage.COMMAND)
    return create_add_board_command(cabinet, snap, thickness_mm=t)


__all__ = [
    "PanelAddStage",
    "build_panel_for_spec",
    "create_add_panel_command",
    "log_stage",
    "resolve_spec",
    "resolve_target_space_from_snapshot",
]
