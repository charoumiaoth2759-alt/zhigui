# -*- coding: utf-8 -*-
"""
空间切分器：仅负责 **split** 与 **create child spaces**。

侧板 ``SPLIT_X`` 绝对规则（``left_space`` / ``right_space`` 语义，非 ``children`` 下标）::

    FaceType.LEFT  → ``[BOARD][FREE]``
        ``left_space`` = occupied 窄条
        ``right_space`` = remain 内腔
        下次 ``active_leaf`` = ``right_space``

    FaceType.RIGHT → ``[FREE][BOARD]``
        ``left_space`` = remain 内腔
        ``right_space`` = occupied 窄条
        下次 ``active_leaf`` = ``left_space``

禁止在本模块内::

    rebuild adjacency / rebuild occupancy / rebuild faces / validate

切分完成后由调用方对根节点执行::

    SpaceConsistencyManager().rebuild_topology(root)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .enums import (
    SpaceType,
    SplitDirection,
    is_split_along_x,
    is_split_along_y,
    is_split_along_z,
)
from .face_selection_snapshot import FaceSelectionSnapshot
from .space_models import Space

if TYPE_CHECKING:
    from ..panel.panel_models import Panel
    from ..panel.panel_role_spec import PanelRoleSpec

_FORBIDDEN_SPACE_FACE_ATTRS = frozenset(
    ("active_face", "hover_face", "last_face"),
)

_MIN_STRIP_MM = 6.0

METADATA_ZONE_ROLE = "zone_role"
ZONE_OCCUPIED = "occupied_space"
ZONE_REMAIN = "remain_space"
# 兼容旧 metadata 值
ZONE_PANEL_STRIP = ZONE_OCCUPIED
ZONE_USABLE = ZONE_REMAIN
ZONE_SHELF_STRIP = "shelf_strip"

_OCCUPIED_ZONE_ROLES = frozenset((ZONE_OCCUPIED, "panel_strip", ZONE_SHELF_STRIP))
_REMAIN_ZONE_ROLES = frozenset((ZONE_REMAIN, "usable"))


def _reject_space_mutable_face_state(space: Space) -> None:
    """禁止从 ``Space`` 上读取悬停/会话面态（须用 ``FaceSelectionSnapshot``）。"""
    for name in _FORBIDDEN_SPACE_FACE_ATTRS:
        if getattr(space, name, None) is not None:
            raise RuntimeError(
                f"split_space_by_face must not read space.{name}; "
                "use face_snapshot.face_type"
            )


class SplitAxis(Enum):
    """切分轴（内部几何语义，写入父节点 ``split_direction``）。"""

    VERTICAL = "vertical"    # 沿 X：左右子空间
    HORIZONTAL = "horizontal"  # 沿 Y：上下子空间
    DEPTH = "depth"          # 沿 Z：前后子空间


_AXIS_TO_SPLIT_DIRECTION: dict[SplitAxis, SplitDirection] = {
    SplitAxis.VERTICAL: SplitDirection.SPLIT_X,
    SplitAxis.HORIZONTAL: SplitDirection.SPLIT_Y,
    SplitAxis.DEPTH: SplitDirection.SPLIT_Z,
}


@dataclass
class SpaceSplitResult:
    """一次二元切分：``parent`` → ``occupied_space`` + ``remain_space``。"""

    first: Space
    second: Space
    axis: SplitAxis
    occupied_space: Space | None = None
    remain_space: Space | None = None
    split_parent: Space | None = None

    @property
    def panel_strip(self) -> Space | None:
        return self.occupied_space

    @property
    def inner(self) -> Space | None:
        return self.remain_space

    @property
    def left_space(self) -> Space | None:
        """切分父节点 ``left_space``（禁止用 ``first``/``second`` 推断方向）。"""
        parent = self.split_parent
        return None if parent is None else parent.left_space

    @property
    def right_space(self) -> Space | None:
        """切分父节点 ``right_space``。"""
        parent = self.split_parent
        return None if parent is None else parent.right_space


class SpaceSplitter:
    """
    空间切分：生成子 ``Space`` 并挂到父节点 ``children``。

    不维护 ``*_neighbor``、``is_occupied``、面占用；见 ``SpaceConsistencyManager``。
    """

    def _create_vertical_pair(
        self,
        space: Space,
        split_x: float,
    ) -> tuple[Space, Space]:
        """几何左右子空间（未挂载）；``split_x`` 为左子空间宽度（mm）。"""
        left = self._create_space(
            x=space.x,
            y=space.y,
            z=space.z,
            width=split_x,
            height=space.height,
            depth=space.depth,
        )
        right = self._create_space(
            x=space.x + split_x,
            y=space.y,
            z=space.z,
            width=space.width - split_x,
            height=space.height,
            depth=space.depth,
        )
        return left, right

    def split_vertical(
        self,
        space: Space,
        split_x: float,
    ) -> SpaceSplitResult:
        """几何左右切分（层板等）；默认 ``left``=occupied、``right``=remain。"""
        left, right = self._create_vertical_pair(space, split_x)
        self._apply_children(
            parent=space,
            first=left,
            second=right,
            axis=SplitAxis.VERTICAL,
        )
        return SpaceSplitResult(
            first=left,
            second=right,
            axis=SplitAxis.VERTICAL,
            occupied_space=left,
            remain_space=right,
            split_parent=space,
        )

    def _apply_x_split_face_zones(
        self,
        parent: Space,
        *,
        occupied: Space,
        remain: Space,
        anchor: object,
    ) -> None:
        """
        按 FaceType.LEFT / RIGHT 写入方向槽（绝对规则）::

            LEFT:  ``left_space``=occupied, ``right_space``=remain
            RIGHT: ``left_space``=remain, ``right_space``=occupied
        """
        from ..constants.enums import AnchorType as AT

        if anchor == AT.LEFT:
            parent.attach_directional_children(
                split_direction=SplitDirection.SPLIT_X,
                first=occupied,
                second=remain,
            )
        elif anchor == AT.RIGHT:
            parent.attach_directional_children(
                split_direction=SplitDirection.SPLIT_X,
                first=remain,
                second=occupied,
            )
        else:
            raise ValueError(f"side panel split requires LEFT/RIGHT anchor, got {anchor!r}")
        verify_split_tree(parent)

    def split_horizontal(
        self,
        space: Space,
        split_y: float,
    ) -> SpaceSplitResult:
        """上下切分。"""
        bottom = self._create_space(
            x=space.x,
            y=space.y,
            z=space.z,
            width=space.width,
            height=split_y,
            depth=space.depth,
        )
        top = self._create_space(
            x=space.x,
            y=space.y + split_y,
            z=space.z,
            width=space.width,
            height=space.height - split_y,
            depth=space.depth,
        )
        self._apply_children(
            parent=space,
            first=bottom,
            second=top,
            axis=SplitAxis.HORIZONTAL,
        )
        return SpaceSplitResult(
            first=bottom,
            second=top,
            axis=SplitAxis.HORIZONTAL,
            occupied_space=bottom,
            remain_space=top,
            split_parent=space,
        )

    def split_depth(
        self,
        space: Space,
        split_z: float,
    ) -> SpaceSplitResult:
        """前后切分。"""
        back = self._create_space(
            x=space.x,
            y=space.y,
            z=space.z,
            width=space.width,
            height=space.height,
            depth=split_z,
        )
        front = self._create_space(
            x=space.x,
            y=space.y,
            z=space.z + split_z,
            width=space.width,
            height=space.height,
            depth=space.depth - split_z,
        )
        self._apply_children(
            parent=space,
            first=back,
            second=front,
            axis=SplitAxis.DEPTH,
        )
        return SpaceSplitResult(
            first=back,
            second=front,
            axis=SplitAxis.DEPTH,
            occupied_space=back,
            remain_space=front,
            split_parent=space,
        )

    def split(self, space: Space, panel: "Panel") -> SpaceSplitResult | None:
        """
        兼容入口：由板件 spec 合成 ``FaceSelectionSnapshot`` 后委托 ``split_space_by_face``。
        """
        from ..panel.side_panel_spec import spec_for_panel

        spec = spec_for_panel(panel)
        if spec is None:
            return None
        snap = FaceSelectionSnapshot.from_pick(
            space_id=str(getattr(space, "id", "") or ""),
            face_type=spec.face,
        )
        return split_space_by_face(space, snap, panel, splitter=self)

    def _split_side_panel_space(
        self,
        space: Space,
        panel: "Panel",
        spec: "PanelRoleSpec",
    ) -> SpaceSplitResult | None:
        """
        按 ``PanelRoleSpec``（来自 ``face_snapshot.face_type``）切分侧板窄条 + remain。

        禁止读取 ``space.active_face`` / ``hover_face`` / ``last_face``。
        """
        _reject_space_mutable_face_state(space)

        from ..constants.enums import AnchorType
        from ..panel.panel_placement import side_stack_offset_mm

        t = max(
            _MIN_STRIP_MM,
            min(float(getattr(panel, "thickness", 18.0)), 80.0),
        )
        stack = side_stack_offset_mm(space, spec.role)
        target, split_x = self._resolve_side_split_target(
            space, spec.anchor, stack, t
        )
        if target is None:
            return None
        w = float(target.width)
        if split_x <= _MIN_STRIP_MM or split_x >= w - _MIN_STRIP_MM:
            return None
        if not target.is_leaf:
            return None

        left_geom, right_geom = self._create_vertical_pair(target, split_x)
        if spec.anchor == AnchorType.LEFT:
            occupied, remain = left_geom, right_geom
        elif spec.anchor == AnchorType.RIGHT:
            occupied, remain = right_geom, left_geom
        else:
            return None
        self._apply_x_split_face_zones(
            target,
            occupied=occupied,
            remain=remain,
            anchor=spec.anchor,
        )
        result = SpaceSplitResult(
            first=left_geom,
            second=right_geom,
            axis=SplitAxis.VERTICAL,
            occupied_space=occupied,
            remain_space=remain,
            split_parent=target,
        )
        self._pin_vertical_strip(
            result.occupied_space,
            split_x
            if spec.anchor == AnchorType.LEFT
            else float(target.width) - split_x,
        )
        self._tag_split_children(result, spec)
        verify_x_split_face_zones(target)
        return result

    def split_shelf(self, attachment: Space, panel: "Panel") -> list[SpaceSplitResult]:
        """
        在 usable 叶空间沿 Y 二次切分：bottom + shelf strip + top（+2 叶空间）。

        用于 ``add shelf`` 后 ``spaces`` 自 3 → 5。
        """
        target = self._find_shelf_target(attachment)
        if target is None or not target.is_leaf:
            return []
        t = max(
            _MIN_STRIP_MM,
            min(float(getattr(panel, "thickness", 18.0)), 80.0),
        )
        h = float(target.height)
        y = (h - t) * 0.5
        y = max(_MIN_STRIP_MM, min(y, h - t - _MIN_STRIP_MM))

        r1 = self.split_horizontal(target, y)
        rest = r1.second
        r2 = self.split_horizontal(rest, t)

        self._pin_horizontal_strip(r2.first, t)
        self._tag_shelf_children(r1.first, r2.first, r2.second)

        r1.occupied_space = None
        r1.remain_space = r1.second
        r1.split_parent = target
        r2.occupied_space = r2.first
        r2.remain_space = r2.second
        r2.split_parent = rest
        return [r1, r2]

    def _find_shelf_target(self, attachment: Space) -> Space | None:
        """取 attachment 子树内最内 remain usable 叶（层板切分目标）。"""
        from .usable_space_resolver import (
            find_primary_remain_usable_leaf,
            resolve_panel_operating_space,
        )

        op = resolve_panel_operating_space(attachment)
        found = find_primary_remain_usable_leaf(op)
        if found is not None:
            return found
        if op.is_leaf:
            return op
        return None

    def _tag_shelf_children(
        self,
        bottom: Space,
        shelf_strip: Space,
        top: Space,
    ) -> None:
        bottom.name = "shelf bottom usable"
        top.name = "shelf top usable"
        shelf_strip.name = "shelf occupied zone"
        for node, role in (
            (bottom, ZONE_REMAIN),
            (top, ZONE_REMAIN),
            (shelf_strip, ZONE_SHELF_STRIP),
        ):
            md = getattr(node, "metadata", None)
            if not isinstance(md, dict):
                node.metadata = {}
                md = node.metadata
            md[METADATA_ZONE_ROLE] = role

    def _pin_horizontal_strip(self, strip: Space | None, height: float) -> None:
        if strip is None:
            return
        ht = max(_MIN_STRIP_MM, float(height))
        strip.height = ht
        c = strip.constraints
        c.min_height = ht
        c.max_height = ht

    def _tag_split_children(self, result: SpaceSplitResult, spec: object) -> None:
        """标记 ``occupied_space`` / ``remain_space`` 子节点 metadata。"""
        occupied = result.occupied_space
        remain = result.remain_space
        label = getattr(spec, "label", "侧板")
        if occupied is not None:
            occupied.name = f"{label} occupied space"
            md = getattr(occupied, "metadata", None)
            if not isinstance(md, dict):
                occupied.metadata = {}
                md = occupied.metadata
            md[METADATA_ZONE_ROLE] = ZONE_OCCUPIED
            role = getattr(spec, "role", None)
            if role is not None:
                md["panel_role"] = getattr(role, "value", str(role))
        if remain is not None:
            remain.name = "remain space"
            md = getattr(remain, "metadata", None)
            if not isinstance(md, dict):
                remain.metadata = {}
                md = remain.metadata
            md[METADATA_ZONE_ROLE] = ZONE_REMAIN

    def _pin_vertical_strip(self, strip: Space | None, width: float) -> None:
        """侧板窄条固定宽度，避免求解器均分子空间。"""
        if strip is None:
            return
        w = max(_MIN_STRIP_MM, float(width))
        strip.width = w
        c = strip.constraints
        c.min_width = w
        c.max_width = w

    def merge_children(self, parent: Space) -> bool:
        """撤销切分：``clear_children`` 恢复为叶节点，并断开方向槽与 ``child.parent``。"""
        children = list(parent.children)
        if len(children) != 2:
            return False
        parent.clear_children()
        parent.split_direction = SplitDirection.NONE
        try:
            from core.cabinet_pipeline_log import log_pipeline_stage

            log_pipeline_stage(
                f"SPLIT merge children parent={getattr(parent, 'id', None)!r}"
            )
        except Exception:
            pass
        return True

    def _zone_role(self, space: Space | None) -> str | None:
        if space is None:
            return None
        md = getattr(space, "metadata", None)
        if not isinstance(md, dict):
            return None
        role = md.get(METADATA_ZONE_ROLE)
        return str(role) if role is not None else None

    def _is_remain_zone_space(self, space: Space | None) -> bool:
        role = self._zone_role(space)
        return role in _REMAIN_ZONE_ROLES if role is not None else False

    def _usable_child_for_x_split(self, parent: Space) -> Space | None:
        """
        已 ``SPLIT_X`` 父节点上的 remain 方向槽。

        LEFT 切分 → ``right_space``；RIGHT 切分 → ``left_space``（见模块顶注释）。
        """
        remain_slot = x_split_remain_directional_child(parent)
        if remain_slot is not None:
            return remain_slot
        for node in (parent.left_space, parent.right_space):
            if self._is_remain_zone_space(node):
                return node
        return None

    def _resolve_side_split_target(
        self,
        space: Space,
        anchor: object,
        stack: float,
        thickness: float,
    ) -> tuple[Space | None, float]:
        from ..constants.enums import AnchorType as AT

        if anchor == AT.LEFT:
            if space.is_leaf:
                return space, float(stack) + float(thickness)
            if is_split_along_x(space.split_direction) and space.has_directional_x_split():
                inner = self._usable_child_for_x_split(space)
                if inner is not None and inner.is_leaf:
                    return inner, float(thickness)
            return None, 0.0

        if anchor == AT.RIGHT:
            if space.is_leaf:
                return space, float(space.width) - float(stack) - float(thickness)
            if is_split_along_x(space.split_direction) and space.has_directional_x_split():
                inner = self._usable_child_for_x_split(space)
                if inner is not None and inner.is_leaf:
                    return inner, float(inner.width) - float(thickness)
            return None, 0.0

        return None, 0.0

    def _apply_children(
        self,
        parent: Space,
        *,
        first: Space,
        second: Space,
        axis: SplitAxis,
    ) -> None:
        """
        挂载二元子空间：写入 ``left_space``/``right_space``（或 Y/Z 方向槽），
        ``children`` 仅作遍历列表 ``[方向槽…]``。
        """
        split_dir = _AXIS_TO_SPLIT_DIRECTION.get(axis, SplitDirection.NONE)
        parent.attach_directional_children(
            split_direction=split_dir,
            first=first,
            second=second,
        )
        verify_split_tree(parent)

        try:
            from core.cabinet_pipeline_log import log_pipeline_stage

            if axis is SplitAxis.VERTICAL:
                log_pipeline_stage(
                    f"SPLIT parent={getattr(parent, 'id', None)!r} "
                    f"left={getattr(parent.left_space, 'id', None)!r} "
                    f"right={getattr(parent.right_space, 'id', None)!r}"
                )
            elif axis is SplitAxis.HORIZONTAL:
                log_pipeline_stage(
                    f"SPLIT parent={getattr(parent, 'id', None)!r} "
                    f"bottom={getattr(parent.bottom_space, 'id', None)!r} "
                    f"top={getattr(parent.top_space, 'id', None)!r}"
                )
            else:
                log_pipeline_stage(
                    f"SPLIT parent={getattr(parent, 'id', None)!r} "
                    f"back={getattr(parent.back_space, 'id', None)!r} "
                    f"front={getattr(parent.front_space, 'id', None)!r}"
                )
        except Exception:
            pass

    def _create_space(
        self,
        x: float,
        y: float,
        z: float,
        width: float,
        height: float,
        depth: float,
    ) -> Space:
        return Space(
            x=x,
            y=y,
            z=z,
            width=width,
            height=height,
            depth=depth,
            parent=None,
            children=[],
            space_type=SpaceType.NORMAL,
        )


def split_space_by_face(
    space: Space,
    face_snapshot: FaceSelectionSnapshot,
    panel: "Panel",
    *,
    splitter: SpaceSplitter | None = None,
) -> SpaceSplitResult | None:
    """
    按不可变 ``face_snapshot.face_type`` 切分 ``space``（侧板 LEFT / RIGHT）。

    面语义**仅**来自 ``face_snapshot``；禁止 ``space.active_face``、
    ``space.hover_face``、``space.last_face`` 及 registry 悬停态。
    """
    _reject_space_mutable_face_state(space)
    from ..panel.panel_role_spec import spec_for_face

    spec = spec_for_face(face_snapshot.face_type)
    if spec is None:
        return None
    sp = splitter if splitter is not None else SpaceSplitter()
    return sp._split_side_panel_space(space, panel, spec)


def _zone_role_on_space(space: Space | None) -> str | None:
    if space is None:
        return None
    md = getattr(space, "metadata", None)
    if not isinstance(md, dict):
        return None
    role = md.get(METADATA_ZONE_ROLE)
    return str(role) if role is not None else None


def x_split_remain_directional_child(parent: Space) -> Space | None:
    """
    ``SPLIT_X`` 父节点上 remain 的方向槽（侧板绝对规则）::

        ``left=occupied, right=remain`` → ``right_space``
        ``left=remain, right=occupied`` → ``left_space``
    """
    ls = parent.left_space
    rs = parent.right_space
    if ls is None or rs is None:
        return None
    l_role = _zone_role_on_space(ls)
    r_role = _zone_role_on_space(rs)
    if l_role in _OCCUPIED_ZONE_ROLES and r_role in _REMAIN_ZONE_ROLES:
        return rs
    if l_role in _REMAIN_ZONE_ROLES and r_role in _OCCUPIED_ZONE_ROLES:
        return ls
    return None


def verify_x_split_face_zones(parent: Space) -> None:
    """断言 SPLIT_X 侧板方向槽满足 LEFT/RIGHT 绝对规则。"""
    if not is_split_along_x(parent.split_direction):
        return
    ls = parent.left_space
    rs = parent.right_space
    if ls is None or rs is None:
        return
    l_role = _zone_role_on_space(ls)
    r_role = _zone_role_on_space(rs)
    left_ok = l_role in _OCCUPIED_ZONE_ROLES and r_role in _REMAIN_ZONE_ROLES
    right_ok = l_role in _REMAIN_ZONE_ROLES and r_role in _OCCUPIED_ZONE_ROLES
    if not (left_ok or right_ok):
        raise RuntimeError(
            f"x-split zone invariant: parent {getattr(parent, 'id', None)!r} "
            f"left_role={l_role!r} right_role={r_role!r}; "
            "expected (occupied,remain) for LEFT or (remain,occupied) for RIGHT"
        )


def verify_split_tree(parent: Space) -> None:
    """
    断言切分后父子双向引用与方向槽::

        SPLIT_X: ``left_space`` + ``right_space``，``children`` 仅遍历
        child.parent is parent
    """
    if len(parent.children) != 2:
        raise RuntimeError(
            f"split tree invariant: parent {getattr(parent, 'id', None)!r} "
            f"must have exactly 2 children, got {len(parent.children)}"
        )
    direction = parent.split_direction
    if is_split_along_x(direction):
        if parent.left_space is None or parent.right_space is None:
            raise RuntimeError(
                f"split tree invariant: SPLIT_X parent {getattr(parent, 'id', None)!r} "
                "requires left_space and right_space"
            )
        if parent.children != [parent.left_space, parent.right_space]:
            raise RuntimeError(
                f"split tree invariant: children must be "
                f"[left_space, right_space] for SPLIT_X"
            )
    elif is_split_along_y(direction):
        if parent.bottom_space is None or parent.top_space is None:
            raise RuntimeError(
                f"split tree invariant: SPLIT_Y parent requires bottom_space and top_space"
            )
        if parent.children != [parent.bottom_space, parent.top_space]:
            raise RuntimeError(
                f"split tree invariant: children must be [bottom_space, top_space]"
            )
    elif is_split_along_z(direction):
        if parent.back_space is None or parent.front_space is None:
            raise RuntimeError(
                f"split tree invariant: SPLIT_Z parent requires back_space and front_space"
            )
        if parent.children != [parent.back_space, parent.front_space]:
            raise RuntimeError(
                f"split tree invariant: children must be [back_space, front_space]"
            )

    for child in parent.children:
        if child.parent is not parent:
            raise RuntimeError(
                f"split tree invariant: child {getattr(child, 'id', None)!r} "
                f".parent must be {getattr(parent, 'id', None)!r}, "
                f"got {getattr(child.parent, 'id', None)!r}"
            )
        if child not in parent.children:
            raise RuntimeError(
                f"split tree invariant: child {getattr(child, 'id', None)!r} "
                f"not in parent.children"
            )


__all__ = [
    "METADATA_ZONE_ROLE",
    "SpaceSplitter",
    "SpaceSplitResult",
    "SplitAxis",
    "ZONE_OCCUPIED",
    "ZONE_PANEL_STRIP",
    "ZONE_REMAIN",
    "ZONE_SHELF_STRIP",
    "ZONE_USABLE",
    "split_space_by_face",
    "verify_split_tree",
    "verify_x_split_face_zones",
    "x_split_remain_directional_child",
]
