from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from ..panel.panel_models import Panel, PanelGroup
    from .space_face_occupancy import SpaceFace

from .constraints import SpaceConstraint
from .enums import (
    SpaceType,
    SplitDirection,
    is_split_along_x,
    is_split_along_y,
    is_split_along_z,
)
from ..dirty.dirty_flags import DirtyFlag


# ==========================================================
# Space
# ==========================================================

@dataclass
class Space:
    """
    柜体空间核心节点（Space Kernel Node）。

    核心原则：

        Space = Source Of Truth

    所有：
        - 板件
        - 门板
        - 抽屉
        - 五金
        - 分割

    都应基于 Space 推导。
    """

    # ======================================================
    # Identity
    # ======================================================

    id: str = field(default_factory=lambda: str(uuid4()))

    name: str = ""

    space_type: SpaceType = SpaceType.NORMAL

    # ======================================================
    # Transform
    # ======================================================

    x: float = 0.0

    y: float = 0.0

    z: float = 0.0

    # ======================================================
    # Size
    # ======================================================

    width: float = 0.0

    height: float = 0.0

    depth: float = 0.0

    # ======================================================
    # Tree Topology
    # ======================================================

    parent: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    children: list["Space"] = field(
        default_factory=list,
        repr=False,
    )

    # 二元切分后的方向性子空间（语义轴；``children`` 仅用于遍历）
    left_space: Optional["Space"] = field(default=None, repr=False)
    right_space: Optional["Space"] = field(default=None, repr=False)
    bottom_space: Optional["Space"] = field(default=None, repr=False)
    top_space: Optional["Space"] = field(default=None, repr=False)
    back_space: Optional["Space"] = field(default=None, repr=False)
    front_space: Optional["Space"] = field(default=None, repr=False)

    # ======================================================
    # Adjacency Topology
    # ======================================================

    left_neighbor: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    right_neighbor: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    top_neighbor: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    bottom_neighbor: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    front_neighbor: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    back_neighbor: Optional["Space"] = field(
        default=None,
        repr=False,
    )

    # ======================================================
    # Space State
    # ======================================================

    is_locked: bool = False

    is_visible: bool = True

    # 六面占用快照（``rebuild_faces`` / ``update_face_occupancy_cache`` 写入；键为 ``FaceType.name``）
    face_occupancy: dict[str, str] = field(
        default_factory=dict,
        repr=False,
    )

    # 侧板交互面（``FaceRegistry`` 绑定；禁止裸 ``FaceType`` 注册而无方向槽）
    left_face: Optional["SpaceFace"] = field(default=None, repr=False)
    right_face: Optional["SpaceFace"] = field(default=None, repr=False)

    # ======================================================
    # Mounted Panels
    # ======================================================

    panels: list["Panel"] = field(
        default_factory=list,
        repr=False,
    )

    panel_groups: list["PanelGroup"] = field(
        default_factory=list,
        repr=False,
    )

    # ======================================================
    # Split Info
    # ======================================================

    split_direction: SplitDirection = SplitDirection.NONE

    split_ratio: float = 0.0

    generated_by: str = ""

    # ======================================================
    # Constraints
    # ======================================================

    constraints: SpaceConstraint = field(
        default_factory=SpaceConstraint
    )

    # ======================================================
    # Dirty
    # ======================================================

    dirty_flag: DirtyFlag = field(
        default=DirtyFlag.CLEAN,
        compare=False,
    )

    # ======================================================
    # Metadata
    # ======================================================

    metadata: dict = field(
        default_factory=dict,
        repr=False,
    )

    # ======================================================
    # Tree Operations
    # ======================================================

    def add_child(self, child: "Space") -> None:

        child.parent = self

        self.children.append(child)

        self.mark_dirty()

    def remove_child(self, child: "Space") -> None:

        if child in self.children:

            self.children.remove(child)

            child.parent = None

            self.mark_dirty()

    def clear_side_face_slots(self) -> None:
        """清空侧板 ``SpaceFace`` 方向绑定。"""
        self.left_face = None
        self.right_face = None

    def clear_directional_child_slots(self) -> None:
        """清空切分方向槽（与 ``clear_children`` 一并调用）。"""
        self.left_space = None
        self.right_space = None
        self.bottom_space = None
        self.top_space = None
        self.back_space = None
        self.front_space = None

    def clear_children(self) -> None:

        for child in self.children:
            child.parent = None

        self.children.clear()
        self.clear_directional_child_slots()
        self.clear_side_face_slots()

        self.mark_dirty()

    def attach_directional_children(
        self,
        *,
        split_direction: SplitDirection,
        first: "Space",
        second: "Space",
    ) -> None:
        """
        挂载二元切分：写入方向槽并同步 ``children``（仅遍历用）。

        SPLIT_X: ``left_space`` + ``right_space``
        SPLIT_Y: ``bottom_space`` + ``top_space``
        SPLIT_Z: ``back_space`` + ``front_space``
        """
        self.clear_directional_child_slots()
        if split_direction == SplitDirection.SPLIT_X:
            self.left_space = first
            self.right_space = second
            ordered = [self.left_space, self.right_space]
        elif split_direction == SplitDirection.SPLIT_Y:
            self.bottom_space = first
            self.top_space = second
            ordered = [self.bottom_space, self.top_space]
        elif split_direction == SplitDirection.SPLIT_Z:
            self.back_space = first
            self.front_space = second
            ordered = [self.back_space, self.front_space]
        else:
            raise ValueError(f"binary split requires SPLIT_X/Y/Z, got {split_direction!r}")

        if self.children:
            for child in list(self.children):
                child.parent = None
            self.children.clear()

        for child in ordered:
            if child is None:
                raise ValueError("directional child slot must not be None")
            if child.parent is not None and child.parent is not self:
                child.detach()
            self.add_child(child)

        self.split_direction = split_direction
        self.mark_dirty()

    def ordered_directional_children(self) -> list["Space"] | None:
        """
        沿切分轴的有序方向子空间（仅用 ``left_space``/``right_space`` 等方向槽）。

        SPLIT_X → ``[left_space, right_space]`` 等。
        """
        if is_split_along_x(self.split_direction):
            if self.left_space is not None and self.right_space is not None:
                return [self.left_space, self.right_space]
        elif is_split_along_y(self.split_direction):
            if self.bottom_space is not None and self.top_space is not None:
                return [self.bottom_space, self.top_space]
        elif is_split_along_z(self.split_direction):
            if self.back_space is not None and self.front_space is not None:
                return [self.back_space, self.front_space]
        return None

    def trailing_directional_children(self) -> list["Space"]:
        """切分轴上第一段之后的子空间（中隔板/层板边界，不用 children 下标）。"""
        ordered = self.ordered_directional_children()
        if ordered is not None and len(ordered) >= 2:
            return list(ordered[1:])
        return []

    def has_directional_x_split(self) -> bool:
        return self.left_space is not None and self.right_space is not None

    def detach(self) -> None:

        if self.parent is not None:
            self.parent.remove_child(self)

    # ======================================================
    # Dirty
    # ======================================================

    def mark_dirty(self) -> None:
        from ..dirty.dirty_tracker import mark_space_dirty

        mark_space_dirty(self)

    def mark_clean(self) -> None:

        self.dirty_flag = DirtyFlag.CLEAN

    # ======================================================
    # Query
    # ======================================================

    @property
    def is_leaf(self) -> bool:

        return len(self.children) == 0

    @property
    def is_root(self) -> bool:

        return self.parent is None

    @property
    def is_dirty(self) -> bool:

        return self.dirty_flag != DirtyFlag.CLEAN

    @property
    def depth_in_tree(self) -> int:

        depth = 0

        node = self

        while node.parent is not None:

            depth += 1

            node = node.parent

        return depth

    @property
    def root(self) -> "Space":

        node = self

        while node.parent is not None:
            node = node.parent

        return node

    @property
    def volume(self) -> float:

        return self.width * self.height * self.depth

    @property
    def size(self) -> tuple[float, float, float]:

        return (
            self.width,
            self.height,
            self.depth,
        )

    @property
    def position(self) -> tuple[float, float, float]:

        return (
            self.x,
            self.y,
            self.z,
        )

    # ======================================================
    # Helpers
    # ======================================================

    def half_size(self) -> tuple[float, float, float]:

        return (
            self.width / 2,
            self.height / 2,
            self.depth / 2,
        )

    def contains_point(
        self,
        x: float,
        y: float,
        z: float,
    ) -> bool:

        return (
            self.x <= x <= self.x + self.width
            and
            self.y <= y <= self.y + self.height
            and
            self.z <= z <= self.z + self.depth
        )

    # ======================================================
    # Debug
    # ======================================================

    def print_tree(
        self,
        level: int = 0,
    ) -> None:

        indent = "    " * level

        dirty_mark = " ✦" if self.is_dirty else ""

        from .space_occupancy import leaf_topology_occupied

        occupied = " OCCUPIED" if leaf_topology_occupied(self) else ""

        print(
            f"{indent}"
            f"{self.name or self.space_type.value}"
            f" [{self.width:.1f} × {self.height:.1f} × {self.depth:.1f}]"
            f" id={self.id[:8]}"
            f"{occupied}"
            f"{dirty_mark}"
        )

        for child in self.children:
            child.print_tree(level + 1)

    # ======================================================
    # Repr
    # ======================================================

    def __repr__(self) -> str:
        from .space_occupancy import leaf_topology_occupied

        return (
            f"Space("
            f"id={self.id[:8]}, "
            f"type={self.space_type.value}, "
            f"size={self.width:.1f}×{self.height:.1f}×{self.depth:.1f}, "
            f"occupied={leaf_topology_occupied(self)}, "
            f"dirty={self.dirty_flag.name}"
            f")"
        )