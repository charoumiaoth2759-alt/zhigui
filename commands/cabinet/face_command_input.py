# -*- coding: utf-8 -*-
"""
柜体加板命令入参（immutable transactional state）。

与 ``PreviewManager`` / ``SpaceFaceHoverSession`` **完全解耦**：
悬停是 UI 瞬态；命令只接受 ``FaceSelectionSnapshot``，禁止从 payload / hover 会话透传可变 face。
"""

from __future__ import annotations

from typing import Any

from core.space.face_selection_snapshot import (
    FaceSelectionSnapshot,
    normalize_command_face_type,
)
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space

from .add_board_command import AddBoardCommand


def build_programmatic_face_snapshot(
    cabinet: dict[str, Any],
    face: FaceType,
) -> FaceSelectionSnapshot:
    """
    非点击路径（组件库 / 工具栏 / 脚本）在**工厂层**一次性合成快照。

    禁止在 ``AddBoardCommand.execute`` 内读取 ``current_space`` 悬停或 ``PreviewManager``。
    """
    from core.space.face_click_resolve import find_space

    root = cabinet.get("root_space")
    if root is None:
        proj = cabinet.get("project")
        if proj is not None:
            root = getattr(proj, "root_space", None)
    if root is None:
        raise ValueError("cannot build programmatic face_snapshot: no root_space")
    space = find_space(cabinet, str(root.id))
    if space is None:
        raise ValueError("cannot build programmatic face_snapshot: root not in tree")
    return FaceSelectionSnapshot.from_pick(
        space_id=str(space.id),
        face_type=normalize_command_face_type(face),
    )


def require_command_face_snapshot(
    *,
    face_snapshot: FaceSelectionSnapshot | None,
    cabinet: dict[str, Any] | None = None,
    face: FaceType | None = None,
    allow_programmatic_synthesis: bool = False,
) -> FaceSelectionSnapshot:
    """
    命令管线唯一面入参解析。

    ``allow_programmatic_synthesis=True`` 时允许用 ``face`` + ``cabinet`` 合成（仅非悬停入口）。
    """
    if face_snapshot is not None:
        if not isinstance(face_snapshot, FaceSelectionSnapshot):
            raise TypeError(
                "face_snapshot must be FaceSelectionSnapshot, "
                "not hover session / HoverHitResult"
            )
        return face_snapshot
    if allow_programmatic_synthesis and cabinet is not None and face is not None:
        return build_programmatic_face_snapshot(cabinet, face)
    raise ValueError(
        "command pipeline requires immutable FaceSelectionSnapshot; "
        "do not pass hover/preview mutable state"
    )


def create_add_board_command(
    cabinet: dict[str, Any],
    face_snapshot: FaceSelectionSnapshot,
    *,
    thickness_mm: float = 18.0,
) -> AddBoardCommand:
    """``FaceSelectionSnapshot`` → ``AddBoardCommand``（命令层唯一工厂）。"""
    snap = require_command_face_snapshot(face_snapshot=face_snapshot)
    return AddBoardCommand(cabinet, snap, thickness_mm=float(thickness_mm))


__all__ = [
    "build_programmatic_face_snapshot",
    "create_add_board_command",
    "require_command_face_snapshot",
]
