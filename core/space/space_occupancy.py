# -*- coding: utf-8 -*-
"""
空间占用语义（``FREE`` / ``OCCUPIED`` / ``LOCKED``）。

**查询**：实时从 ``panel_groups`` / ``panels`` / ``children`` 推导，不读陈旧缓存。
**同步**：``rebuild_tree_occupancy`` 仅刷新 ``metadata.topology_occupancy`` 与 ``is_locked``（日志/兜底）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .space_models import Space
from .tree import walk_dfs

METADATA_TOPOLOGY_OCCUPANCY = "topology_occupancy"


class SpaceOccupancyKind(Enum):
    """叶空间占用（与 ``enums.SpaceState`` 拾取语义配合）。"""

    FREE = "free"
    OCCUPIED = "occupied"
    LOCKED = "locked"


def _metadata_dict(space: Space) -> dict:
    md = getattr(space, "metadata", None)
    if not isinstance(md, dict):
        md = {}
        setattr(space, "metadata", md)
    return md


def _has_mounted_panels(space: Space) -> bool:
    flat = getattr(space, "panels", None) or []
    if flat:
        return True
    for grp in getattr(space, "panel_groups", None) or []:
        if getattr(grp, "panels", None):
            return True
    return False


def compute_space_occupancy_kind(space: Space) -> SpaceOccupancyKind:
    """
    由树结构与挂载板件实时推导占用。

    有子节点时返回 ``FREE``（结构占用由 ``infer_space_state`` → ``SPLIT`` 表达）。
    """
    children = getattr(space, "children", None) or []
    if len(children) > 0:
        return SpaceOccupancyKind.FREE

    if not _has_mounted_panels(space):
        return SpaceOccupancyKind.FREE

    from .cabinet_ops_lock import read_cabinet_ops_user_allow

    if read_cabinet_ops_user_allow(space):
        return SpaceOccupancyKind.OCCUPIED
    return SpaceOccupancyKind.LOCKED


def read_space_occupancy(space: Space) -> SpaceOccupancyKind:
    """实时占用查询（等同 ``compute_space_occupancy_kind``，结构节点恒 ``FREE``）。"""
    children = getattr(space, "children", None) or []
    if len(children) > 0:
        return SpaceOccupancyKind.FREE
    return compute_space_occupancy_kind(space)


def apply_space_occupancy_kind(space: Space, kind: SpaceOccupancyKind) -> None:
    """同步 ``metadata.topology_occupancy`` 与 ``is_locked``（非查询权威）。"""
    md = _metadata_dict(space)
    md[METADATA_TOPOLOGY_OCCUPANCY] = kind.value

    if kind is SpaceOccupancyKind.FREE:
        space.is_locked = False
    elif kind is SpaceOccupancyKind.OCCUPIED:
        space.is_locked = False
    elif kind is SpaceOccupancyKind.LOCKED:
        space.is_locked = True


def leaf_topology_occupied(space: Space) -> bool:
    """叶节点是否拓扑占用（实时）。"""
    children = getattr(space, "children", None) or []
    if len(children) > 0:
        return False
    kind = compute_space_occupancy_kind(space)
    return kind in (SpaceOccupancyKind.OCCUPIED, SpaceOccupancyKind.LOCKED)


def apply_occupancy_for_space(space: Space) -> SpaceOccupancyKind | None:
    """单节点占用同步（有子节点时清除 metadata）。"""
    children = getattr(space, "children", None) or []
    if len(children) > 0:
        space.is_locked = False
        md = _metadata_dict(space)
        md.pop(METADATA_TOPOLOGY_OCCUPANCY, None)
        clear_face_occupancy_on_space(space)
        return None
    kind = compute_space_occupancy_kind(space)
    apply_space_occupancy_kind(space, kind)
    return kind


def update_spaces_occupancy(spaces: list[Space] | tuple[Space, ...]) -> None:
    """刷新给定空间及其父节点的占用同步字段。"""
    seen: set[int] = set()
    queue: list[Space] = list(spaces)
    for space in spaces:
        parent = getattr(space, "parent", None)
        if parent is not None:
            queue.append(parent)
    for space in queue:
        sid = id(space)
        if sid in seen:
            continue
        seen.add(sid)
        apply_occupancy_for_space(space)


@dataclass(frozen=True)
class SpaceOccupancyView:
    """占用查询视图（实时推导，非 ``Space`` 冗余字段）。"""

    topology_occupied: bool
    child_count: int
    structure: str
    face_label: str | None = None

    @property
    def is_occupied(self) -> bool:
        return self.topology_occupied

    @property
    def is_split(self) -> bool:
        return self.child_count > 0 or self.structure == "split"

    @property
    def face_free(self) -> bool:
        return (self.face_label or "FREE").upper() == "FREE"

    @property
    def face_occupied(self) -> bool:
        return (self.face_label or "").upper() == "OCCUPIED"

    @property
    def face_blocked(self) -> bool:
        return (self.face_label or "").upper() == "BLOCKED"


def write_face_occupancy_to_space(
    space: Space,
    face_type: Any,
    state: Any,
) -> None:
    """将面状态写入 ``space.face_occupancy``（Manager 同步用，查询走实时 API）。"""
    name = getattr(face_type, "name", None) or str(face_type)
    st = getattr(state, "name", None) or str(state)
    if not hasattr(space, "face_occupancy") or space.face_occupancy is None:
        space.face_occupancy = {}
    space.face_occupancy[str(name)] = str(st)


def query_space_occupancy(
    space: Space,
    face: Any | None = None,
) -> SpaceOccupancyView:
    """占用查询：拓扑 + 面均实时推导。"""
    from .space_face_occupancy import SpaceFaceOccupancy, _resolve_face_type

    children = list(getattr(space, "children", None) or [])
    n = len(children)
    topo_occ = leaf_topology_occupied(space)

    if n > 0:
        structure = "split"
        topo_occ = False
    elif topo_occ:
        structure = (
            "locked" if bool(getattr(space, "is_locked", False)) else "occupied"
        )
    else:
        structure = "free"

    face_label: str | None = None
    if face is not None:
        ft = _resolve_face_type(face)
        if ft is not None and SpaceFaceOccupancy.is_face_available(space, ft):
            face_label = "FREE"
        else:
            face_label = "OCCUPIED"

    return SpaceOccupancyView(
        topology_occupied=topo_occ,
        child_count=n,
        structure=structure,
        face_label=face_label,
    )


def clear_face_occupancy_on_space(space: Space) -> None:
    fo = getattr(space, "face_occupancy", None)
    if isinstance(fo, dict):
        fo.clear()


def rebuild_tree_occupancy(root: Space) -> dict[str, int]:
    """全树同步 ``topology_occupancy`` / ``is_locked``（查询仍走实时 API）。"""
    counts = {k.name: 0 for k in SpaceOccupancyKind}
    for node in walk_dfs(root):
        children = getattr(node, "children", None) or []
        clear_face_occupancy_on_space(node)
        if len(children) > 0:
            node.is_locked = False
            md = _metadata_dict(node)
            md.pop(METADATA_TOPOLOGY_OCCUPANCY, None)
            continue
        kind = compute_space_occupancy_kind(node)
        apply_space_occupancy_kind(node, kind)
        counts[kind.name] = counts.get(kind.name, 0) + 1
    return counts


def repair_occupancy_field_drift(root: Space) -> int:
    """将 ``metadata`` / ``is_locked`` 与实时推导结果对齐。"""
    fixed = 0
    for node in walk_dfs(root):
        children = getattr(node, "children", None) or []
        if len(children) > 0:
            if bool(node.is_locked):
                node.is_locked = False
                fixed += 1
            continue
        kind = compute_space_occupancy_kind(node)
        expected_lock = kind is SpaceOccupancyKind.LOCKED
        md = getattr(node, "metadata", None)
        cached = None
        if isinstance(md, dict):
            cached = md.get(METADATA_TOPOLOGY_OCCUPANCY)
        if (
            cached != kind.value
            or bool(node.is_locked) != expected_lock
        ):
            apply_space_occupancy_kind(node, kind)
            fixed += 1
    return fixed


__all__ = [
    "METADATA_TOPOLOGY_OCCUPANCY",
    "SpaceOccupancyKind",
    "SpaceOccupancyView",
    "apply_occupancy_for_space",
    "apply_space_occupancy_kind",
    "clear_face_occupancy_on_space",
    "compute_space_occupancy_kind",
    "leaf_topology_occupied",
    "query_space_occupancy",
    "read_space_occupancy",
    "rebuild_tree_occupancy",
    "repair_occupancy_field_drift",
    "update_spaces_occupancy",
    "write_face_occupancy_to_space",
]
