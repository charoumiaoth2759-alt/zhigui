# -*- coding: utf-8 -*-
"""
锚定板件配置注册表 — **唯一** ``FaceType`` / ``PanelRole`` / 命令名映射来源。

新增板件：在此 ``_PANEL_ROLE_SPECS`` 增加一条 ``PanelRoleSpec``；
禁止复制 ``add_left_panel`` / ``add_right_panel`` 代码路径。

管线：Face → Space → Panel → Command → Solver → Topology → Occupancy → FaceRegistry → View3D
（见 ``core.panel.panel_pipeline`` / ``docs/PANEL_ADD_PIPELINE.md``）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..constants.enums import AnchorType, PanelRole
from ..space.space_face_occupancy import FaceType
from .panel_face_mapper import get_panel_role_by_face, try_get_face_by_panel_role


@dataclass(frozen=True)
class PanelRoleSpec:
    """单条锚定板件：面 → 角色 → 锚边 → 命令（配置驱动，无 left/right 分支）。"""

    face: FaceType
    role: PanelRole
    anchor: AnchorType
    command_name: str
    label: str


_PANEL_ROLE_SPECS: tuple[PanelRoleSpec, ...] = (
    PanelRoleSpec(
        face=FaceType.LEFT,
        role=PanelRole.LEFT_SIDE,
        anchor=AnchorType.LEFT,
        command_name="add_left_panel",
        label="左侧板",
    ),
    PanelRoleSpec(
        face=FaceType.RIGHT,
        role=PanelRole.RIGHT_SIDE,
        anchor=AnchorType.RIGHT,
        command_name="add_right_panel",
        label="右侧板",
    ),
)

_BY_FACE: dict[FaceType, PanelRoleSpec] = {s.face: s for s in _PANEL_ROLE_SPECS}
_BY_COMMAND: dict[str, PanelRoleSpec] = {s.command_name: s for s in _PANEL_ROLE_SPECS}
_BY_ROLE: dict[PanelRole, PanelRoleSpec] = {s.role: s for s in _PANEL_ROLE_SPECS}


def iter_panel_role_specs() -> tuple[PanelRoleSpec, ...]:
    return _PANEL_ROLE_SPECS


def iter_mount_panel_command_names() -> tuple[str, ...]:
    return tuple(s.command_name for s in _PANEL_ROLE_SPECS)


def is_mount_panel_command(command_name: str) -> bool:
    return spec_for_command(command_name) is not None


def spec_for_face(face: FaceType) -> PanelRoleSpec | None:
    sp = _BY_FACE.get(face)
    if sp is not None:
        return sp
    try:
        role = get_panel_role_by_face(face)
    except KeyError:
        return None
    return _BY_ROLE.get(role)


def spec_for_command(command_name: str) -> PanelRoleSpec | None:
    return _BY_COMMAND.get(str(command_name or "").strip())


def spec_for_role(role: PanelRole) -> PanelRoleSpec | None:
    return _BY_ROLE.get(role)


def spec_for_panel(panel: Any) -> PanelRoleSpec | None:
    from .anchor_placement import anchor_type_effective

    role = getattr(panel, "role", None)
    if isinstance(role, PanelRole):
        sp = spec_for_role(role)
        if sp is not None:
            return sp
        face = try_get_face_by_panel_role(role)
        if face is not None:
            return spec_for_face(face)
    at = anchor_type_effective(panel)
    for s in _PANEL_ROLE_SPECS:
        if s.anchor == at:
            return s
    return None


def face_from_payload(payload: Any) -> FaceType | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("face") or payload.get("face_type")
    if raw is None:
        cmd = payload.get("command_name")
        if cmd:
            sp = spec_for_command(str(cmd))
            return sp.face if sp else None
        return None
    if isinstance(raw, FaceType):
        return raw
    s = str(raw).strip().upper()
    try:
        return FaceType[s]
    except KeyError:
        return None


def resolve_face(*, face: FaceType | None = None, payload: Any | None = None) -> FaceType:
    if face is not None:
        return face
    ft = face_from_payload(payload)
    if ft is not None:
        return ft
  # 默认面仅用于无载荷程序化调用；UI 须显式传 face
    return FaceType.LEFT


__all__ = [
    "PanelRoleSpec",
    "face_from_payload",
    "is_mount_panel_command",
    "iter_mount_panel_command_names",
    "iter_panel_role_specs",
    "resolve_face",
    "spec_for_command",
    "spec_for_face",
    "spec_for_panel",
    "spec_for_role",
]
