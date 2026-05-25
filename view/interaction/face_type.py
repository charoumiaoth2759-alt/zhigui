# -*- coding: utf-8 -*-
"""
交互 / 悬停面类型 — 与 core ``FaceType`` 同构（re-export）。

``INNER`` 为空间内侧面，无占用槽映射。
"""

from __future__ import annotations

from core.space.space_face_occupancy import FaceType


def face_type_to_space_face(face: FaceType) -> FaceType | None:
    """``FaceType`` → core 面键；``INNER`` 返回 ``None``。"""
    if face is FaceType.INNER:
        return None
    return face


def space_face_to_face_type(face: FaceType) -> FaceType | None:
    """core ``FaceType`` → 交互 ``FaceType``（同类型）。"""
    if isinstance(face, FaceType):
        return face
    return None


__all__ = [
    "FaceType",
    "face_type_to_space_face",
    "space_face_to_face_type",
]
