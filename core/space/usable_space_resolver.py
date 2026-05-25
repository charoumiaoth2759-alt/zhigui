# -*- coding: utf-8 -*-
"""
板件 / 切分命令的**操作空间**解析。

侧板 ``SPLIT_X`` 绝对规则（与 ``splitter`` 一致）::

    FaceType.LEFT:  ``left_space``=occupied, ``right_space``=remain → ``active_leaf``=``right_space``
    FaceType.RIGHT: ``left_space``=remain, ``right_space``=occupied → ``active_leaf``=``left_space``

原则::

    - 左侧板：在叶空间上切掉贴边窄条 → ``occupied`` + ``remain``（首次可为 root 叶）。
    - 右侧板、层板、中竖板等：只作用于 **remaining usable** 叶空间，禁止把 SPLIT 父节点（含 root）当作挂载/切分目标。

与 ``SpaceSplitter._resolve_side_split_target`` / ``x_split_remain_directional_child`` 语义一致。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .space_models import Space
from .splitter import METADATA_ZONE_ROLE, ZONE_REMAIN, _REMAIN_ZONE_ROLES
from .tree import iter_leaves

if TYPE_CHECKING:
    from .splitter import SpaceSplitResult

_REMAIN_ROLES = _REMAIN_ZONE_ROLES


def is_remain_usable_leaf(space: Space) -> bool:
    """叶节点且 ``zone_role`` 为 remain / usable（或尚未标注 zone 的初始叶）。"""
    if not space.is_leaf:
        return False
    md = getattr(space, "metadata", None)
    if not isinstance(md, dict):
        return True
    role = md.get(METADATA_ZONE_ROLE)
    if role is None:
        return True
    return role in _REMAIN_ROLES


def find_remain_usable_leaves(attachment: Space) -> list[Space]:
    """``attachment`` 子树内全部 remain usable 叶（按体积降序）。"""
    out: list[Space] = []
    for leaf in iter_leaves(attachment):
        if is_remain_usable_leaf(leaf):
            out.append(leaf)
    out.sort(key=lambda c: float(c.volume), reverse=True)
    return out


def _depth_in_subtree(subtree_root: Space, node: Space) -> int:
    """``node`` 相对 ``subtree_root`` 的父子链深度（``node==subtree_root`` → 0）。"""
    depth = 0
    cur: Space | None = node
    while cur is not None and cur is not subtree_root:
        depth += 1
        cur = cur.parent
    return depth if cur is subtree_root else -1


def find_active_remain_leaf(attachment: Space) -> Space | None:
    """
    唯一可操作的 **最新** remain 叶（FACE_REGISTRY / 侧板命令共用）。

    在 ``remain ∩ interactable`` 候选中取相对 ``attachment`` 最深者，同深取最大体积。
    连续 LEFT / RIGHT 始终命中切分链末端内腔，而非旧 occupied 窄条或上层 remain 父节点。
    """
    from .space_face_occupancy import is_interactable_space

    best_depth = -1
    best_vol = -1.0
    best: Space | None = None
    for leaf in iter_leaves(attachment):
        if not is_remain_usable_leaf(leaf):
            continue
        if not is_interactable_space(leaf):
            continue
        d = _depth_in_subtree(attachment, leaf)
        if d < 0:
            continue
        vol = float(leaf.volume)
        if d > best_depth or (d == best_depth and vol > best_vol):
            best_depth = d
            best_vol = vol
            best = leaf
    return best


def find_primary_remain_usable_leaf(attachment: Space) -> Space | None:
    """兼容别名 → ``find_active_remain_leaf``。"""
    return find_active_remain_leaf(attachment)


def active_leaf_from_side_split(
    face: Any,
    split_result: "SpaceSplitResult | None",
) -> Space | None:
    """
    侧板切分后继承的下一 ``active_leaf``（绝对规则）::

        FaceType.LEFT  → ``split_result.right_space``（父 ``right_space``）
        FaceType.RIGHT → ``split_result.left_space``（父 ``left_space``）

    禁止 ``remain_space``≈几何 ``second``、``children[1]``、``child1``。
    """
    if split_result is None:
        return None
    from .space_face_occupancy import FaceType

    if face == FaceType.LEFT:
        return split_result.right_space or split_result.remain_space
    if face == FaceType.RIGHT:
        return split_result.left_space or split_result.remain_space
    return split_result.remain_space


def resolve_panel_operating_space(space: Space) -> Space:
    """
    解析为柜体上 **当前唯一可操作的 remain 叶**（拓扑入口，非 UI）。

    禁止回落到 occupied 窄条或已变为 SPLIT 的旧 remain 父节点。
    """
    root = space.root
    active = find_active_remain_leaf(root)
    if active is not None:
        return active
    if space.is_leaf:
        return space
    return space


def focus_ctx_operating_space(ctx: dict[str, Any], space: Space | None) -> None:
    """命令成功后把 ``selection.current_space`` 设为后续板件的操作空间。"""
    if space is None:
        return
    sel = ctx.get("selection")
    if sel is not None:
        setattr(sel, "current_space", space)


__all__ = [
    "active_leaf_from_side_split",
    "find_active_remain_leaf",
    "find_primary_remain_usable_leaf",
    "find_remain_usable_leaves",
    "focus_ctx_operating_space",
    "is_remain_usable_leaf",
    "resolve_panel_operating_space",
]
