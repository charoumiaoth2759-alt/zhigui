# -*- coding: utf-8 -*-
"""
悬停拾取标准结果（view 层数据契约，无 Qt）。

冻结 ``Space`` + ``face`` + ``hit_point``，供悬停预览与点击快照复制。
"""

from __future__ import annotations

from dataclasses import dataclass

from core.space.space_models import Space

from .face_type import FaceType


@dataclass(frozen=True)
class Vec3:
    """世界坐标点（mm）。"""

    x: float
    y: float
    z: float

    @classmethod
    def from_tuple(cls, xyz: tuple[float, float, float]) -> Vec3:
        return cls(float(xyz[0]), float(xyz[1]), float(xyz[2]))

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class HoverHitResult:
    """一次有效悬停/拾取命中。"""

    space: Space
    face: FaceType
    hit_point: Vec3


def build_hover_hit_result(
    *,
    space: Space,
    face: FaceType,
    hit_point: Vec3 | tuple[float, float, float],
) -> HoverHitResult:
    """构造悬停命中。"""
    hp = hit_point if isinstance(hit_point, Vec3) else Vec3.from_tuple(hit_point)
    return HoverHitResult(space=space, face=face, hit_point=hp)


__all__ = [
    "FaceType",
    "HoverHitResult",
    "Vec3",
    "build_hover_hit_result",
]
