# -*- coding: utf-8 -*-
"""柜体 ``Space`` 按 ``space_id`` 查找（命令链，不读悬停 / selection 可变状态）。"""

from __future__ import annotations

from typing import Any, Callable

from .face_selection_snapshot import FaceSelectionSnapshot
from .space_models import Space
from .tree import find_by_id, resolve_space_root


def _cabinet_root(cabinet: dict[str, Any]) -> Space | None:
    rs = cabinet.get("root_space")
    if isinstance(rs, Space):
        return rs
    proj = cabinet.get("project")
    if proj is not None:
        rs = getattr(proj, "root_space", None)
        if isinstance(rs, Space):
            return rs
    return None


def find_space(cabinet: dict[str, Any], space_id: str) -> Space | None:
    """
    ``cabinet.find_space(clicked_space_id)`` — 按 id 在柜体树上定位节点。

    禁止 ``find_active_remain_leaf`` / ``resolve_panel_operating_space`` /
    ``current_space`` / ``active_space`` / ``last_interactable`` 重定向。
    """
    root = _cabinet_root(cabinet)
    if root is None:
        return None
    sid = str(space_id or "").strip()
    if not sid:
        return None
    node = find_by_id(root, sid)
    if node is None:
        return None
    tree_root = resolve_space_root(node)
    if tree_root is not root:
        return None
    return node


def bind_cabinet_find_space(cabinet: dict[str, Any]) -> None:
    """在命令上下文字典上挂载 ``find_space(space_id)``（``cabinet[\"find_space\"](id)``）。"""
    cabinet["find_space"] = lambda space_id: find_space(cabinet, space_id)


def resolve_space_from_face_snapshot(
    cabinet: dict[str, Any],
    snapshot: FaceSelectionSnapshot,
) -> Space | None:
    """``FaceSelectionSnapshot`` → ``find_space(cabinet, snapshot.space_id)``。"""
    return find_space(cabinet, snapshot.space_id)


def cabinet_find_space_callable(
    cabinet: dict[str, Any],
) -> Callable[[str], Space | None]:
    fn = cabinet.get("find_space")
    if callable(fn):
        return fn
    return lambda space_id: find_space(cabinet, space_id)


__all__ = [
    "bind_cabinet_find_space",
    "cabinet_find_space_callable",
    "find_space",
    "resolve_space_from_face_snapshot",
]
