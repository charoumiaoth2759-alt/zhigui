# -*- coding: utf-8 -*-
"""
脏标记传播：子节点变更 → 向父级标记 DIRTY；求解完成后由 ``solve_dirty_spaces`` 恢复 CLEAN。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .dirty_flags import DirtyFlag

if TYPE_CHECKING:
    from ..panel.panel_models import Panel
    from ..space.space_models import Space


def mark_space_dirty(space: Space, *, propagate_up: bool = True) -> None:
    """
    将 ``space`` 标为 DIRTY；``propagate_up=True`` 时沿父链向上传播（父级也需重算）。
    """
    node: Space | None = space
    while node is not None:
        if node.dirty_flag is DirtyFlag.DIRTY:
            break
        node.dirty_flag = DirtyFlag.DIRTY
        if not propagate_up:
            break
        node = node.parent


def mark_panel_dirty(panel: Panel, *, host_space: Space | None = None) -> None:
    """板件脏标记；若提供 ``host_space`` 则同时向父链传播空间脏标记。"""
    panel.dirty_flag = DirtyFlag.DIRTY
    if host_space is not None:
        mark_space_dirty(host_space)


def mark_spaces_clean(spaces: Iterable[Space]) -> None:
    for sp in spaces:
        sp.mark_clean()


def mark_panels_clean(panels: Iterable[Panel]) -> None:
    for p in panels:
        p.dirty_flag = DirtyFlag.CLEAN


__all__ = [
    "mark_panel_dirty",
    "mark_panels_clean",
    "mark_space_dirty",
    "mark_spaces_clean",
]
