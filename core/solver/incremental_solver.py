# -*- coding: utf-8 -*-
"""
Dirty Incremental Solver — 仅重算脏 ``Space`` 子树，禁止全柜 ``generate(dirty_only=False)``。
"""

from __future__ import annotations

from typing import Any, Sequence

from ..dirty.dirty_flags import DirtyFlag
from ..dirty.dirty_tracker import (
    mark_panels_clean,
    mark_space_dirty,
    mark_spaces_clean,
)
from ..panel.panel_generator import (
    collect_space_panels,
    generate_incremental,
)
from ..space.resolver import ResolveStatus, resolve_incremental
from ..space.space_models import Space
from ..space.tree import find_dirty, walk_dfs
from .cabinet_solver import CabinetSolveRequest, SolveResult


def _panel_key(panel: Any) -> str:
    pid = getattr(panel, "id", None)
    if pid is not None and str(pid):
        return str(pid)
    return str(id(panel))


def _flatten_panel_groups(panel_groups: list[Any] | None) -> list[Any]:
    out: list[Any] = []
    for group in panel_groups or []:
        out.extend(getattr(group, "panels", []) or [])
    return out


def _merge_unique_panels(*sequences: list[Any] | None) -> list[Any]:
    seen: set[str] = set()
    ordered: list[Any] = []
    for seq in sequences:
        for p in seq or []:
            k = _panel_key(p)
            if k in seen:
                continue
            seen.add(k)
            ordered.append(p)
    return ordered


def _snapshot_dirty_nodes(root: Space) -> list[Space]:
    return list(find_dirty(root))


def _panels_on_spaces(root: Space, space_ids: set[str]) -> list[Any]:
    out: list[Any] = []
    for p in collect_space_panels(root):
        sid = getattr(p, "space_id", None) or getattr(p, "bound_space_id", None)
        if sid and str(sid) in space_ids:
            out.append(p)
    return out


def _collect_panel_groups_from_tree(root: Space) -> list[Any]:
    seen: set[int] = set()
    groups: list[Any] = []
    for node in walk_dfs(root):
        for grp in getattr(node, "panel_groups", None) or []:
            gid = id(grp)
            if gid in seen:
                continue
            seen.add(gid)
            groups.append(grp)
    return groups


def _merge_panel_groups_by_space(
    base: list[Any], incremental: list[Any]
) -> list[Any]:
    """按 ``space_id`` 用增量组覆盖同空间旧组，保留未脏空间的组。"""
    by_sid: dict[str, Any] = {}
    order: list[str] = []
    for g in base:
        sid = str(getattr(g, "space_id", "") or "")
        if sid not in by_sid:
            order.append(sid)
        by_sid[sid] = g
    for g in incremental:
        sid = str(getattr(g, "space_id", "") or "")
        if sid not in by_sid:
            order.append(sid)
        by_sid[sid] = g
    return [by_sid[sid] for sid in order if sid in by_sid]


def solve_dirty_spaces(
    space_tree: Space | None,
    *,
    request: CabinetSolveRequest | None = None,
    seed_spaces: Sequence[Space] | None = None,
) -> SolveResult:
    """
    脏空间增量求解（唯一允许的柜体求解路径）。

    流程：
      1. ``seed_spaces`` / 树上 ``find_dirty`` 收集脏节点
      2. ``resolve_incremental`` — 仅脏子树尺寸传播
      3. ``generate_incremental`` — 仅脏空间板件生成
      4. 脏空间挂载板件 ``recalculate`` / ``relocate``
      5. 脏节点与相关板件 ``mark_clean``
    """
    _ = request
    if space_tree is None:
        return SolveResult(
            success=True,
            spaces=[],
            panel_groups=[],
            panel_list=[],
            events=["SOLVE_COMPLETED"],
        )

    if seed_spaces:
        for sp in seed_spaces:
            mark_space_dirty(sp)

    from core.cabinet_pipeline_log import log_solver_solve_cabinet

    dirty_nodes = _snapshot_dirty_nodes(space_tree)
    log_solver_solve_cabinet(dirty_count=len(dirty_nodes))
    if not dirty_nodes:
        groups = _collect_panel_groups_from_tree(space_tree)
        panels = _merge_unique_panels(
            _flatten_panel_groups(groups),
            collect_space_panels(space_tree),
        )
        return SolveResult(
            success=True,
            spaces=[],
            panel_groups=groups,
            panel_list=panels,
            events=["SOLVE_COMPLETED"],
            message="no dirty spaces",
        )

    dirty_ids = {str(n.id) for n in dirty_nodes}

    resolve_result = resolve_incremental(space_tree, dirty_nodes)
    if resolve_result.status is ResolveStatus.FAILED:
        msg = "; ".join(resolve_result.errors[:3]) or "resolve_incremental failed"
        return SolveResult(
            success=False,
            errors=list(resolve_result.errors),
            message=msg,
        )

    try:
        gen = generate_incremental(space_tree, dirty_nodes)
    except Exception as exc:
        return SolveResult(
            success=False,
            errors=[str(exc)],
            message=str(exc),
        )

    space_map = {str(s.id): s for s in walk_dfs(space_tree)}
    dirty_panels = _panels_on_spaces(space_tree, dirty_ids)
    for p in dirty_panels:
        p.dirty_flag = DirtyFlag.DIRTY

    if dirty_panels:
        try:
            from ..panel.panel_calculator import recalculate_dirty
            from ..panel.panel_placement import relocate_dirty

            recalculate_dirty(dirty_panels, space_map)
            relocate_dirty(dirty_panels, space_map)
        except Exception as exc:
            return SolveResult(
                success=False,
                errors=[str(exc)],
                message=str(exc),
            )

    mark_spaces_clean(dirty_nodes)
    mark_panels_clean(dirty_panels)

    base_groups = _collect_panel_groups_from_tree(space_tree)
    merged_groups = _merge_panel_groups_by_space(base_groups, list(gen.groups))
    generator_flat = _flatten_panel_groups(list(gen.groups))
    tree_flat = collect_space_panels(space_tree)
    panels = _merge_unique_panels(generator_flat, tree_flat)

    solved_spaces = [
        n
        for n in walk_dfs(space_tree, order="pre")
        if str(n.id) in dirty_ids
    ]

    return SolveResult(
        success=len(gen.errors) == 0,
        spaces=solved_spaces,
        panel_groups=merged_groups,
        panel_list=panels,
        errors=list(gen.errors),
        events=["SOLVE_COMPLETED"],
        message=None if not gen.errors else gen.errors[0],
    )


__all__ = ["solve_dirty_spaces"]
