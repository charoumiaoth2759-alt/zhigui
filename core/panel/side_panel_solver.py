# -*- coding: utf-8 -*-
"""
侧板求解：由 ``panel.role``（``LEFT_SIDE`` / ``RIGHT_SIDE``）驱动落位。

禁止 ``solve_left_panel`` / ``solve_right_panel``；统一 ``solve_side_panel(panel, space)``。
"""

from __future__ import annotations

from ..constants.enums import AnchorType, PanelRole
from ..space.enums import FaceType
from .panel_face_mapper import get_face_by_panel_role
from ..dirty.dirty_flags import DirtyFlag
from ..space.space_models import Space
from .panel_models import Panel
from .panel_placement import place_side_panel
from .rules.panel_defaults import get_panel_defaults
from .rules.panel_wrap_rules import get_wrap_rule
from .side_panel_spec import spec_for_role

_SIDE_ROLES: frozenset[PanelRole] = frozenset(
    (PanelRole.LEFT_SIDE, PanelRole.RIGHT_SIDE)
)  # 与 ``SIDE_PANEL_FACE_ROLES`` 值集一致


def _role_eq(panel: Panel, role: PanelRole) -> bool:
    r = getattr(panel, "role", None)
    if r == role:
        return True
    v = getattr(r, "value", None)
    return v == role.value


def _stack_yz(space: Space) -> tuple[float, float]:
    defaults = get_panel_defaults(space.space_type)
    wrap = get_wrap_rule(space.space_type)
    y = float(space.y) + (
        0.0 if wrap.side_wraps_bottom else float(defaults.bottom_thickness)
    )
    z = float(space.z)
    return y, z


def solve_side_panel(panel: Panel, space: Space) -> None:
    """
    按 ``panel.role`` 将单块侧板贴到 ``space`` 对应外缘（相对空间原点，非世界写死）。

    ``LEFT_SIDE``：``x = space.x + stack``；``RIGHT_SIDE``：``x = space.x + width - stack - t``。
    """
    role = getattr(panel, "role", None)
    if role not in _SIDE_ROLES:
        raise ValueError(f"solve_side_panel: unsupported role {role!r}")
    spec = spec_for_role(role)
    if spec is None:
        raise ValueError(f"solve_side_panel: no SidePanelSpec for {role!r}")
    place_side_panel(panel, space, spec.anchor)
    panel.dirty_flag = DirtyFlag.CLEAN


def place_side_panel_stack_on_space(
    space: Space, panels: list[Panel], role: PanelRole
) -> None:
    """同一 ``Space`` 上同角色侧板堆叠重排（LEFT 沿 +X，RIGHT 沿 -X）。"""
    if role not in _SIDE_ROLES:
        return
    sides = [p for p in panels if _role_eq(p, role)]
    if not sides:
        return
    y, z = _stack_yz(space)
    if get_face_by_panel_role(role) is FaceType.LEFT:
        sides.sort(
            key=lambda p: (
                float(getattr(p, "x", 0.0)),
                float(getattr(p, "z", 0.0)),
                float(getattr(p, "y", 0.0)),
            )
        )
        off = 0.0
        sx = float(space.x)
        for p in sides:
            p.set_position(sx + off, y, z)
            off += float(getattr(p, "thickness", 18.0))
            p.dirty_flag = DirtyFlag.DIRTY
        return
    sides.sort(
        key=lambda p: (
            -float(getattr(p, "x", 0.0)),
            float(getattr(p, "z", 0.0)),
            float(getattr(p, "y", 0.0)),
        )
    )
    x1 = float(space.x) + float(space.width)
    off = 0.0
    for p in sides:
        t = float(getattr(p, "thickness", 18.0))
        p.set_position(x1 - off - t, y, z)
        off += t
        p.dirty_flag = DirtyFlag.DIRTY


def place_left_side_stack_on_space(space: Space, panels: list[Panel]) -> None:
    """兼容别名 → ``place_side_panel_stack_on_space(..., LEFT_SIDE)``。"""
    place_side_panel_stack_on_space(space, panels, PanelRole.LEFT_SIDE)


def place_right_side_stack_on_space(space: Space, panels: list[Panel]) -> None:
    """``RIGHT_SIDE`` 堆叠重排。"""
    place_side_panel_stack_on_space(space, panels, PanelRole.RIGHT_SIDE)


__all__ = [
    "place_left_side_stack_on_space",
    "place_right_side_stack_on_space",
    "place_side_panel_stack_on_space",
    "solve_side_panel",
]
