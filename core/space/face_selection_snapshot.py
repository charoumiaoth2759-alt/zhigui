# -*- coding: utf-8 -*-
"""
点击面选择的不可变快照（mousePress / on_face_clicked 须在确认瞬间复制）。

存储 ``face_type_name``（字符串），**不**持有 ``SpaceFace`` / registry rebuild 后的面对象引用。
命令管线通过 ``face_type`` 属性按名解析 ``FaceType`` 枚举成员。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .space_face_occupancy import FaceType

# 历史 payload 键；命令管线不再从 payload 读取（须显式 ``face_snapshot`` 参数）。
FACE_SELECTION_PAYLOAD_KEY = "face_selection"


def normalize_command_face_type(face: Any) -> FaceType:
    """
    命令用面类型：仅接受 ``FaceType`` 或名称字符串，按 **枚举名** 重新绑定。

    禁止传入 ``SpaceFace``（``FaceRegistry.rebuild`` 后会重新生成实例）。
    """
    from .space_face_occupancy import SpaceFace

    if isinstance(face, SpaceFace):
        raise TypeError(
            "command pipeline must not use SpaceFace registry objects; "
            "snapshot FaceType at click time instead"
        )
    if isinstance(face, FaceType):
        return FaceType[face.name]
    if isinstance(face, str):
        key = face.strip().upper()
        try:
            return FaceType[key]
        except KeyError as e:
            raise ValueError(f"unknown face type name: {face!r}") from e
    raise TypeError(
        f"command face must be FaceType or str name, got {type(face).__name__}"
    )


@dataclass(frozen=True)
class FaceSelectionSnapshot:
    """
    一次确认的 ``(space_id, face_type_name)``。

    与 ``SpaceFaceOccupancyManager._faces``、悬停 ``HoverHitResult`` 生命周期解耦。
    """

    space_id: str
    face_type_name: str

    @property
    def face_type(self) -> FaceType:
        """按名解析；不缓存 registry 内 ``SpaceFace`` 引用。"""
        return FaceType[self.face_type_name]

    @classmethod
    def from_pick(
        cls,
        *,
        space_id: str,
        face_type: FaceType,
    ) -> FaceSelectionSnapshot:
        if not space_id:
            raise ValueError("space_id is required for FaceSelectionSnapshot")
        ft = normalize_command_face_type(face_type)
        return cls(space_id=str(space_id), face_type_name=ft.name)


def face_snapshot_from_payload(payload: object) -> FaceSelectionSnapshot | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get(FACE_SELECTION_PAYLOAD_KEY)
    if isinstance(raw, FaceSelectionSnapshot):
        return raw
    return None


__all__ = [
    "FACE_SELECTION_PAYLOAD_KEY",
    "FaceSelectionSnapshot",
    "face_snapshot_from_payload",
    "normalize_command_face_type",
]
