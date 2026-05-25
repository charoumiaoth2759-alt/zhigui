# -*- coding: utf-8 -*-
"""
``PanelRole`` ↔ ``FaceType`` 唯一映射表。

围合板件（左/右/顶/底/背）的空间面由本模块解析，禁止在项目各处 ``if role == LEFT_SIDE`` 分叉。
"""

from __future__ import annotations

from core.panel.enums import PanelRole
from core.space.enums import FaceType

PANEL_ROLE_TO_FACE: dict[PanelRole, FaceType] = {
    PanelRole.LEFT_SIDE: FaceType.LEFT,
    PanelRole.RIGHT_SIDE: FaceType.RIGHT,
    PanelRole.TOP: FaceType.TOP,
    PanelRole.BOTTOM: FaceType.BOTTOM,
    PanelRole.BACK: FaceType.BACK,
}

_ROLE_ALIASES: dict[PanelRole, PanelRole] = {
    PanelRole.LEFT: PanelRole.LEFT_SIDE,
    PanelRole.RIGHT: PanelRole.RIGHT_SIDE,
}

FACE_TO_PANEL_ROLE: dict[FaceType, PanelRole] = {
    face: role for role, face in PANEL_ROLE_TO_FACE.items()
}

_SIDE_FACES: frozenset[FaceType] = frozenset((FaceType.LEFT, FaceType.RIGHT))

SIDE_PANEL_FACE_ROLES: dict[FaceType, PanelRole] = {
    ft: FACE_TO_PANEL_ROLE[ft] for ft in _SIDE_FACES
}


def normalize_panel_role(role: PanelRole) -> PanelRole:
    """废弃别名 ``LEFT`` / ``RIGHT`` → ``LEFT_SIDE`` / ``RIGHT_SIDE``。"""
    return _ROLE_ALIASES.get(role, role)


def get_face_by_panel_role(role: PanelRole) -> FaceType:
    """由板件角色取对应空间外表面；无映射时 ``KeyError``。"""
    role = normalize_panel_role(role)
    return PANEL_ROLE_TO_FACE[role]


def get_panel_role_by_face(face: FaceType) -> PanelRole:
    """由空间面取围合板件角色；无映射时 ``KeyError``。"""
    return FACE_TO_PANEL_ROLE[face]


def try_get_face_by_panel_role(role: PanelRole) -> FaceType | None:
    role = normalize_panel_role(role)
    return PANEL_ROLE_TO_FACE.get(role)


def is_face_bound_role(role: PanelRole) -> bool:
    """是否为已注册围合面角色（含 ``LEFT`` / ``RIGHT`` 别名）。"""
    return try_get_face_by_panel_role(role) is not None


def is_side_panel_role(role: PanelRole) -> bool:
    """左/右侧板角色（含别名）。"""
    face = try_get_face_by_panel_role(role)
    return face is not None and face in _SIDE_FACES


def iter_face_bound_roles() -> tuple[PanelRole, ...]:
    return tuple(PANEL_ROLE_TO_FACE.keys())


__all__ = [
    "FACE_TO_PANEL_ROLE",
    "PANEL_ROLE_TO_FACE",
    "SIDE_PANEL_FACE_ROLES",
    "get_face_by_panel_role",
    "get_panel_role_by_face",
    "is_face_bound_role",
    "is_side_panel_role",
    "iter_face_bound_roles",
    "normalize_panel_role",
    "try_get_face_by_panel_role",
]
