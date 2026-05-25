# -*- coding: utf-8 -*-
"""
锚点贴边 vs 自动布局：与 ``panel_placement.place`` 使用同一套空间坐标与包裹规则。

``LEFT_SIDE`` 多块堆叠时，板件已在 ``panel_groups`` 内，**不能**再用
``left_side_stack_offset_x``（会把自身厚度算进偏移）；改由本模块按序累加厚度重贴左缘。
"""

from __future__ import annotations

from typing import Any

from ..constants.enums import AnchorType, PanelRole, PlacementMode
from .panel_face_mapper import (
    get_face_by_panel_role,
    is_face_bound_role,
    is_side_panel_role,
)
from ..dirty.dirty_flags import DirtyFlag
from ..space.space_models import Space
from .panel_bounds import panel_extents_world_xyz
from .panel_models import Panel
from .panel_placement import place
from .side_panel_solver import (
    place_side_panel_stack_on_space,
    solve_side_panel,
)
_AUTO_ROLES: frozenset[PanelRole] = frozenset(
    {
        PanelRole.SHELF,
        PanelRole.DIVIDER,
        PanelRole.DOOR_LEFT,
        PanelRole.DOOR_RIGHT,
        PanelRole.DOOR_DOUBLE,
        PanelRole.DRAWER_FRONT,
        PanelRole.UNKNOWN,
    }
)


def placement_mode_effective(panel: Panel) -> PlacementMode:
    """未显式设置时：围合骨架类默认锚定，层板/中隔板/门扇等默认自动布局。"""
    m = getattr(panel, "placement_mode", None)
    if isinstance(m, PlacementMode):
        return m
    role = getattr(panel, "role", PanelRole.UNKNOWN)
    if role in _AUTO_ROLES:
        return PlacementMode.AUTO_PLACED
    return PlacementMode.ANCHOR_FIXED


def anchor_type_effective(panel: Panel) -> AnchorType:
    """未显式设置时：由 ``role`` 推断锚边（与 ``panel_placement`` 语义一致）。"""
    a = getattr(panel, "anchor_type", None)
    if isinstance(a, AnchorType) and a != AnchorType.NONE:
        return a
    role = getattr(panel, "role", PanelRole.UNKNOWN)
    if is_face_bound_role(role):
        face = get_face_by_panel_role(role)
        return AnchorType[face.name]
    return AnchorType.NONE


def _role_eq(panel: Any, role: PanelRole) -> bool:
    r = getattr(panel, "role", None)
    if r == role:
        return True
    v = getattr(r, "value", None)
    return v == role.value


def place_left_side_stack_on_space(space: Space, panels: list[Panel]) -> None:
    """兼容别名 → ``place_side_panel_stack_on_space(..., LEFT_SIDE)``。"""
    place_side_panel_stack_on_space(space, panels, PanelRole.LEFT_SIDE)


def _apply_edge_anchor(panel: Panel, space: Space, anchor: AnchorType) -> None:
    """
    按锚边写回最小角 ``(x,y,z)``（不删板件、不用比例位移）。

    与 ``panel_placement._calc_position`` 的围合语义对齐；``TOP`` 为贴 **顶**（大 ``y``），
    ``FRONT`` 为贴 **前**（大 ``z``）。
    """
    dx, dy, dz = panel_extents_world_xyz(panel)
    sx0, sy0, sz0 = float(space.x), float(space.y), float(space.z)
    sw, sh, sd = float(space.width), float(space.height), float(space.depth)

    if anchor == AnchorType.LEFT:
        panel.set_position(sx0, panel.y, panel.z)
        return
    if anchor == AnchorType.RIGHT:
        panel.set_position(sx0 + sw - dx, panel.y, panel.z)
        return
    if anchor == AnchorType.BOTTOM:
        panel.set_position(panel.x, sy0, panel.z)
        return
    if anchor == AnchorType.TOP:
        panel.set_position(panel.x, sy0 + sh - dy, panel.z)
        return
    if anchor == AnchorType.BACK:
        panel.set_position(panel.x, panel.y, sz0)
        return
    if anchor == AnchorType.FRONT:
        panel.set_position(panel.x, panel.y, sz0 + sd - dz)
        return


def apply_anchor_panel(panel: Panel, space: Space) -> None:
    """
    锚定板件：只做贴空间边界校正。

    对 ``LEFT`` / ``RIGHT`` / ``TOP`` / ``BOTTOM`` / ``BACK`` 等标准围合角色，
    调用 ``place()`` 以复用包裹规则与朝向写入；其它角色按 ``anchor_type`` 用 AABB 贴边。
    """
    mode = placement_mode_effective(panel)
    if mode != PlacementMode.ANCHOR_FIXED:
        return

    anchor = anchor_type_effective(panel)
    if is_side_panel_role(panel.role):
        solve_side_panel(panel, space)
        return
    if is_face_bound_role(panel.role) and not is_side_panel_role(panel.role):
        place(panel, space, apply_to_panel=True)
        return

    if anchor != AnchorType.NONE:
        _apply_edge_anchor(panel, space, anchor)
        panel.dirty_flag = DirtyFlag.DIRTY
        return

    place(panel, space, apply_to_panel=True)


def apply_mixed_placements(space_map: dict[str, Space], boards: list[Panel]) -> None:
    """
    按 Space 分组：先重排 ``LEFT_SIDE`` 堆叠，再处理其余 ``ANCHOR_FIXED``，最后 ``AUTO_PLACED``。

    不整表 ``place_all``，避免把锚定板当作普通列表统一重算导致 X 漂移。
    """
    by_space: dict[str, list[Panel]] = {}
    for b in boards:
        sid = getattr(b, "space_id", None)
        if not sid or sid not in space_map:
            continue
        by_space.setdefault(sid, []).append(b)

    for sid, plist in by_space.items():
        space = space_map[sid]

        for role in (PanelRole.LEFT_SIDE, PanelRole.RIGHT_SIDE):  # side stack order
            stack = [
                p
                for p in plist
                if placement_mode_effective(p) == PlacementMode.ANCHOR_FIXED
                and _role_eq(p, role)
            ]
            if stack:
                place_side_panel_stack_on_space(space, stack, role)

        for p in plist:
            if placement_mode_effective(p) != PlacementMode.ANCHOR_FIXED:
                continue
            if is_side_panel_role(getattr(p, "role", PanelRole.UNKNOWN)):
                continue
            apply_anchor_panel(p, space)

        for p in plist:
            if placement_mode_effective(p) != PlacementMode.AUTO_PLACED:
                continue
            place(p, space, apply_to_panel=True)
