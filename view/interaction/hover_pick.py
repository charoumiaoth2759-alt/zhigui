# -*- coding: utf-8 -*-
"""
悬停拾取：屏幕 / 世界射线 → ``HoverHitResult``。

对外 API 仅 ``pick_face_hover_*``（``FaceType`` 分发）；禁止字符串侧面名。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from core.space.constraint_engine import ConstraintEngine
from core.space.space_models import Space
from core.space.space_picker import (
    SpacePicker,
    _leaf_eligible_for_panel_pick,
    ray_intersect_side_stack_outer_face_mm,
)

from .face_hover_rect import (
    FACE_HOVER_RECT_WIDTH_PX,
    screen_point_in_face_hover_rect,
)
from .face_type import FaceType
from .hover_hit_result import HoverHitResult, build_hover_hit_result

_SIDE_HOVER_FACES: tuple[FaceType, ...] = (FaceType.LEFT, FaceType.RIGHT)


def _normalize_dir(
    direction: tuple[float, float, float],
) -> tuple[float, float, float] | None:
    dx, dy, dz = (float(direction[0]), float(direction[1]), float(direction[2]))
    ln = math.sqrt(dx * dx + dy * dy + dz * dz)
    if ln < 1e-12:
        return None
    return (dx / ln, dy / ln, dz / ln)


def _pick_side_face_from_ray(
    root: Space,
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    *,
    face: FaceType,
    constraint_engine: ConstraintEngine,
    board_context: Any | None = None,
    margin_mm: float = 120.0,
) -> HoverHitResult | None:
    nd = _normalize_dir(direction)
    if nd is None:
        return None
    dx, dy, dz = nd
    ox, oy, oz = (float(origin[0]), float(origin[1]), float(origin[2]))

    space = SpacePicker.pick_leaf_for_side_face_ray(
        root,
        (ox, oy, oz),
        (dx, dy, dz),
        face=face,
        constraint_engine=constraint_engine,
        board_context=board_context,
        margin_mm=margin_mm,
    )
    if space is None:
        return None
    t_hit = ray_intersect_side_stack_outer_face_mm(
        space, ox, oy, oz, dx, dy, dz, face=face, margin_mm=margin_mm
    )
    if t_hit is None:
        return None
    return build_hover_hit_result(
        space=space,
        face=face,
        hit_point=(ox + dx * t_hit, oy + dy * t_hit, oz + dz * t_hit),
    )


def pick_face_hover_from_ray(
    root: Space,
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    *,
    target_face: FaceType,
    constraint_engine: ConstraintEngine,
    board_context: Any | None = None,
    margin_mm: float = 120.0,
) -> HoverHitResult | None:
    """世界射线按 ``FaceType`` 拾取叶空间并返回 ``HoverHitResult``。"""
    if target_face not in _SIDE_HOVER_FACES:
        return None
    return _pick_side_face_from_ray(
        root,
        origin,
        direction,
        face=target_face,
        constraint_engine=constraint_engine,
        board_context=board_context,
        margin_mm=margin_mm,
    )


def pick_side_panel_face_hover_from_ray(
    root: Space,
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    *,
    constraint_engine: ConstraintEngine,
    board_context: Any | None = None,
    margin_mm: float = 120.0,
) -> HoverHitResult | None:
    """LEFT / RIGHT 侧板面竞态：取射线参数 ``t`` 更近的命中。"""
    nd = _normalize_dir(direction)
    if nd is None:
        return None
    dx, dy, dz = nd
    ox, oy, oz = (float(origin[0]), float(origin[1]), float(origin[2]))
    best: HoverHitResult | None = None
    best_t = float("inf")
    for face in _SIDE_HOVER_FACES:
        hit = _pick_side_face_from_ray(
            root,
            (ox, oy, oz),
            (dx, dy, dz),
            face=face,
            constraint_engine=constraint_engine,
            board_context=board_context,
            margin_mm=margin_mm,
        )
        if hit is None:
            continue
        t_hit = ray_intersect_side_stack_outer_face_mm(
            hit.space, ox, oy, oz, dx, dy, dz, face=face, margin_mm=margin_mm
        )
        # abs(t_hit)：消除方向性不对称，RIGHT 面不再因 t 大而永远输给 LEFT
        t_cmp = abs(t_hit) if t_hit is not None else float("inf")
        if t_cmp >= best_t:
            continue
        best_t = t_cmp
        best = hit
    return best


def _ray_coords(ray: Any) -> tuple[
    tuple[float, float, float], tuple[float, float, float]
] | None:
    origin, direction = ray

    def _coord(v: Any, i: int) -> float:
        if hasattr(v, "x") and i == 0:
            return float(v.x())
        if hasattr(v, "y") and i == 1:
            return float(v.y())
        if hasattr(v, "z") and i == 2:
            return float(v.z())
        return float(v[i])

    return (
        (_coord(origin, 0), _coord(origin, 1), _coord(origin, 2)),
        (_coord(direction, 0), _coord(direction, 1), _coord(direction, 2)),
    )


def _pick_side_face_hover_from_ray_filtered(
    root: Space,
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    *,
    face: FaceType,
    constraint_engine: ConstraintEngine,
    board_context: Any | None,
    margin_mm: float,
    screen_x: float,
    screen_y: float,
    world_to_screen: Callable[[float, float, float], tuple[float, float] | None],
) -> HoverHitResult | None:
    """射线拾取 + Face Hover Rect 门控（鼠标须在对应侧面热区内）。"""
    from core.space.face_registry import is_face_registerable
    from core.space.space_metrics import SpaceMetrics
    from core.space.tree import iter_leaves

    ox, oy, oz = origin
    dx, dy, dz = direction
    width_px = FACE_HOVER_RECT_WIDTH_PX.get(face, 14.0)
    best: HoverHitResult | None = None
    best_score = float("-inf")
    for sp in iter_leaves(root):
        if not _leaf_eligible_for_panel_pick(sp):
            continue
        if not is_face_registerable(sp, face):
            continue
        if not screen_point_in_face_hover_rect(
            sp, face, screen_x, screen_y, world_to_screen, width_px=width_px
        ):
            continue
        t_hit = ray_intersect_side_stack_outer_face_mm(
            sp, ox, oy, oz, dx, dy, dz, face=face, margin_mm=margin_mm
        )
        if t_hit is None:
            # 热区已命中但射线 t 为 None（视角使射线方向与面平行或背向）
            # fallback：用空间中心到射线原点的距离，保证不因视角问题丢弃命中
            cx = float(sp.x) + float(sp.width) * 0.5
            cy = float(sp.y) + float(sp.height) * 0.5
            cz = float(sp.z) + float(sp.depth) * 0.5
            t_hit = math.sqrt((cx - ox) ** 2 + (cy - oy) ** 2 + (cz - oz) ** 2)
        if not constraint_engine.validate(sp, board_context):
            continue
        vol = float(sp.width) * float(sp.height) * float(sp.depth)
        # abs(t_hit)：消除 LEFT/RIGHT 方向性不对称，RIGHT 不再因 t 大而得分低
        score = SpaceMetrics.score_side_face_ray(sp, abs(t_hit), vol)
        if score <= best_score:
            continue
        best_score = score
        best = build_hover_hit_result(
            space=sp,
            face=face,
            hit_point=(ox + dx * t_hit, oy + dy * t_hit, oz + dz * t_hit),
        )
    return best


def pick_face_hover_at_screen(
    root: Space | None,
    screen_ray_fn: Callable[[float, float], Any],
    sx: float,
    sy: float,
    *,
    target_face: FaceType | None,
    constraint_engine: ConstraintEngine,
    board_context: Any | None = None,
    margin_mm: float = 120.0,
    world_to_screen: Callable[[float, float, float], tuple[float, float] | None]
    | None = None,
) -> HoverHitResult | None:
    """屏幕坐标 → ``HoverHitResult``（Face Hover Rect 门控 + 世界射线）。"""
    if root is None:
        return None

    ray = screen_ray_fn(sx, sy)
    if ray is None:
        return None
    coords = _ray_coords(ray)
    if coords is None:
        return None
    o, dr = coords

    if world_to_screen is not None:
        if target_face is not None:
            return _pick_side_face_hover_from_ray_filtered(
                root,
                o,
                dr,
                face=target_face,
                constraint_engine=constraint_engine,
                board_context=board_context,
                margin_mm=margin_mm,
                screen_x=sx,
                screen_y=sy,
                world_to_screen=world_to_screen,
            )
        best: HoverHitResult | None = None
        best_t = float("inf")
        ox, oy, oz = o
        dx, dy, dz = dr
        for face in _SIDE_HOVER_FACES:
            hit = _pick_side_face_hover_from_ray_filtered(
                root,
                o,
                dr,
                face=face,
                constraint_engine=constraint_engine,
                board_context=board_context,
                margin_mm=margin_mm,
                screen_x=sx,
                screen_y=sy,
                world_to_screen=world_to_screen,
            )
            if hit is None:
                continue
            t_hit = ray_intersect_side_stack_outer_face_mm(
                hit.space, ox, oy, oz, dx, dy, dz, face=face, margin_mm=margin_mm
            )
            # abs(t_hit)：RIGHT 面 t 可能为负或较大，用绝对值做距离比较
            t_cmp = abs(t_hit) if t_hit is not None else float("inf")
            if t_cmp >= best_t:
                continue
            best_t = t_cmp
            best = hit
        return best

    if target_face is not None:
        return pick_face_hover_from_ray(
            root,
            o,
            dr,
            target_face=target_face,
            constraint_engine=constraint_engine,
            board_context=board_context,
            margin_mm=margin_mm,
        )
    return pick_side_panel_face_hover_from_ray(
        root,
        o,
        dr,
        constraint_engine=constraint_engine,
        board_context=board_context,
        margin_mm=margin_mm,
    )


def pick_left_face_hover_from_ray(
    root: Space,
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    *,
    constraint_engine: ConstraintEngine,
    target_face: FaceType = FaceType.LEFT,
    board_context: Any | None = None,
    margin_mm: float = 120.0,
) -> HoverHitResult | None:
    """兼容别名 → ``pick_face_hover_from_ray``。"""
    return pick_face_hover_from_ray(
        root,
        origin,
        direction,
        target_face=target_face,
        constraint_engine=constraint_engine,
        board_context=board_context,
        margin_mm=margin_mm,
    )


def pick_left_face_hover_at_screen(
    root: Space | None,
    screen_ray_fn: Callable[[float, float], Any],
    sx: float,
    sy: float,
    *,
    constraint_engine: ConstraintEngine,
    target_face: FaceType = FaceType.LEFT,
    board_context: Any | None = None,
    margin_mm: float = 120.0,
    world_to_screen: Callable[[float, float, float], tuple[float, float] | None]
    | None = None,
) -> HoverHitResult | None:
    """兼容别名 → ``pick_face_hover_at_screen``。"""
    return pick_face_hover_at_screen(
        root,
        screen_ray_fn,
        sx,
        sy,
        target_face=target_face,
        constraint_engine=constraint_engine,
        board_context=board_context,
        margin_mm=margin_mm,
        world_to_screen=world_to_screen,
    )


__all__ = [
    "pick_face_hover_at_screen",
    "pick_face_hover_from_ray",
    "pick_left_face_hover_at_screen",
    "pick_left_face_hover_from_ray",
    "pick_side_panel_face_hover_from_ray",
]