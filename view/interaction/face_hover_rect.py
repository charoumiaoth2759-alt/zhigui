# -*- coding: utf-8 -*-
"""
侧板面屏幕热区（Face Hover Rect）：LEFT / RIGHT 面片拾取，非边线距离。

专业 CAD 交互：在屏幕空间沿外法线方向扩展固定像素宽度的矩形热区。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from core.panel.panel_face_mapper import SIDE_PANEL_FACE_ROLES
from core.panel.panel_placement import side_stack_offset_mm
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space

WorldToScreenFn = Callable[[float, float, float], tuple[float, float] | None]

LEFT_FACE_HOVER_RECT_WIDTH_PX = 14.0
RIGHT_FACE_HOVER_RECT_WIDTH_PX = 20.0  # 右侧略宽，补偿视角不对称

FACE_HOVER_RECT_WIDTH_PX: dict[FaceType, float] = {
    FaceType.LEFT: LEFT_FACE_HOVER_RECT_WIDTH_PX,
    FaceType.RIGHT: RIGHT_FACE_HOVER_RECT_WIDTH_PX,
}


@dataclass(frozen=True)
class FaceHoverRect:
    """屏幕像素轴对齐热区（由侧面四顶点投影 + 外扩宽度构成）。"""

    face: FaceType
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    def contains(self, screen_x: float, screen_y: float) -> bool:
        return (
            self.min_x <= float(screen_x) <= self.max_x
            and self.min_y <= float(screen_y) <= self.max_y
        )


def _side_face_plane_x_mm(space: Space, face: FaceType) -> float | None:
    role = SIDE_PANEL_FACE_ROLES.get(face)
    if role is None:
        return None
    x0 = float(space.x)
    x1 = x0 + float(space.width)
    if face is FaceType.LEFT:
        stack = float(side_stack_offset_mm(space, role))
        return x0 + stack
    if face is FaceType.RIGHT:
        # 修复：RIGHT 面热区用空间右边缘 x1，不往里缩进
        # 原来 x1 - stack 导致热区平面偏内，被左侧板遮挡
        return x1
    return None


def _side_face_corners_mm(space: Space, face: FaceType) -> tuple[tuple[float, float, float], ...] | None:
    px = _side_face_plane_x_mm(space, face)
    if px is None:
        return None
    y0, y1 = float(space.y), float(space.y + space.height)
    z0, z1 = float(space.z), float(space.z + space.depth)
    return (
        (px, y0, z0),
        (px, y1, z0),
        (px, y1, z1),
        (px, y0, z1),
    )


def _outward_normal_mm(face: FaceType) -> tuple[float, float, float] | None:
    if face is FaceType.LEFT:
        return (-1.0, 0.0, 0.0)
    if face is FaceType.RIGHT:
        return (1.0, 0.0, 0.0)
    return None


def _screen_outward_dir(
    space: Space,
    face: FaceType,
    world_to_screen: WorldToScreenFn,
    *,
    normal_scale_mm: float = 80.0,
) -> tuple[float, float] | None:
    corners = _side_face_corners_mm(space, face)
    if corners is None:
        return None
    n = _outward_normal_mm(face)
    if n is None:
        return None
    cx = sum(c[0] for c in corners) * 0.25
    cy = sum(c[1] for c in corners) * 0.25
    cz = sum(c[2] for c in corners) * 0.25
    p0 = world_to_screen(cx, cy, cz)
    p1 = world_to_screen(
        cx + n[0] * normal_scale_mm,
        cy + n[1] * normal_scale_mm,
        cz + n[2] * normal_scale_mm,
    )
    if p0 is None or p1 is None:
        return None
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    if ln < 1e-6:
        return None
    return (dx / ln, dy / ln)


def build_face_hover_rect(
    space: Space,
    face: FaceType,
    world_to_screen: WorldToScreenFn,
    *,
    width_px: float | None = None,
) -> FaceHoverRect | None:
    """将侧面 YZ 四边形投影到屏幕，并沿外法线方向扩展 ``width_px`` 像素热区。"""
    corners = _side_face_corners_mm(space, face)
    if corners is None:
        return None
    screen_pts: list[tuple[float, float]] = []
    for wx, wy, wz in corners:
        sp = world_to_screen(wx, wy, wz)
        if sp is None:
            return None
        screen_pts.append(sp)
    xs = [p[0] for p in screen_pts]
    ys = [p[1] for p in screen_pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w_px = float(
        width_px
        if width_px is not None
        else FACE_HOVER_RECT_WIDTH_PX.get(face, LEFT_FACE_HOVER_RECT_WIDTH_PX)
    )
    out = _screen_outward_dir(space, face, world_to_screen)
    if out is not None and w_px > 0.0:
        ox, oy = out
        # 外法线方向扩展 w_px（主方向），内侧也扩展 w_px * 0.6 避免贴边 miss
        # 修复：原逻辑只往外扩，鼠标从内侧靠近时完全打不中（RIGHT 面尤为严重）
        if ox >= 0.0:
            max_x += ox * w_px
            min_x -= ox * w_px * 0.6
        else:
            min_x += ox * w_px
            max_x -= ox * w_px * 0.6
        if oy >= 0.0:
            max_y += oy * w_px
            min_y -= oy * w_px * 0.6
        else:
            min_y += oy * w_px
            max_y -= oy * w_px * 0.6
    return FaceHoverRect(face=face, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y)


def screen_point_in_face_hover_rect(
    space: Space,
    face: FaceType,
    screen_x: float,
    screen_y: float,
    world_to_screen: WorldToScreenFn,
    *,
    width_px: float | None = None,
) -> bool:
    rect = build_face_hover_rect(
        space, face, world_to_screen, width_px=width_px
    )
    if rect is None:
        return False
    return rect.contains(screen_x, screen_y)


__all__ = [
    "FACE_HOVER_RECT_WIDTH_PX",
    "FaceHoverRect",
    "LEFT_FACE_HOVER_RECT_WIDTH_PX",
    "RIGHT_FACE_HOVER_RECT_WIDTH_PX",
    "build_face_hover_rect",
    "screen_point_in_face_hover_rect",
]