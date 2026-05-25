# -*- coding: utf-8 -*-
"""``[ADD_PANEL]`` 调试打印（submit / execute 管线验证）。"""

from __future__ import annotations

from typing import Any


def add_panel_print(message: str) -> None:
    print(message, flush=True)


def _cabinet_boards_list(cabinet: Any) -> list[Any]:
    boards = getattr(cabinet, "boards", None)
    return list(boards) if isinstance(boards, list) else []


def verify_cabinet_boards_registered(ctx: dict[str, Any], panel: Any) -> None:
    """``register_board`` + ``sync`` 后：``panel in cabinet.boards`` 且与空间树板件数一致。"""
    from core.panel.panel_models import Panel
    from core.space.space_consistency_manager import collect_panels_from_space_tree

    if not isinstance(panel, Panel):
        return
    cabinet = ctx.get("project")
    if cabinet is None:
        return
    boards = _cabinet_boards_list(cabinet)
    n = len(boards)
    pid = str(getattr(panel, "id", "") or "")
    add_panel_print(
        f"[ADD_PANEL] cabinet.boards len={n} panel_id={pid!r} "
        f"panel_in_boards={panel in boards}"
    )
    assert panel in boards, (
        f"cabinet.boards missing panel after register/sync "
        f"(panel_id={pid!r} len={n})"
    )
    root = ctx.get("root_space")
    if root is None:
        root = getattr(cabinet, "root_space", None)
    if root is not None:
        tree_panels = collect_panels_from_space_tree(root)
        assert n == len(tree_panels), (
            f"cabinet.boards len={n} != space_tree panels len={len(tree_panels)}"
        )


def verify_cabinet_boards_unregistered(ctx: dict[str, Any], panel: Any) -> None:
    """``unregister_board`` + ``sync`` 后：板件不在 ``cabinet.boards``。"""
    from core.panel.panel_models import Panel

    if not isinstance(panel, Panel):
        return
    cabinet = ctx.get("project")
    if cabinet is None:
        return
    boards = _cabinet_boards_list(cabinet)
    n = len(boards)
    pid = str(getattr(panel, "id", "") or "")
    add_panel_print(
        f"[ADD_PANEL] cabinet.boards len={n} panel_id={pid!r} "
        f"panel_in_boards={panel in boards}"
    )
    assert panel not in boards, (
        f"cabinet.boards still contains panel after unregister/sync "
        f"(panel_id={pid!r} len={n})"
    )


def verify_add_panel_pipeline(ctx: dict[str, Any], cmd: Any) -> None:
    """execute + push 成功后验证 Panel / boards / solver / view / topology。"""
    from core.panel.panel_models import Panel
    from core.space.space_consistency_manager import collect_panels_from_space_tree
    from core.space.space_models import Space

    panel = getattr(cmd, "_panel", None)
    is_panel = isinstance(panel, Panel)
    add_panel_print(
        f"[ADD_PANEL] verify Panel(model)={is_panel} "
        f"panel_id={getattr(panel, 'id', None)!r}"
    )

    proj = ctx.get("project")
    boards = getattr(proj, "boards", None) if proj is not None else None
    boards_len = len(boards) if isinstance(boards, list) else 0
    add_panel_print(
        f"[ADD_PANEL] verify cabinet.boards "
        f"attr_exists={boards is not None} count={boards_len}"
    )

    root = ctx.get("root_space")
    if root is None and proj is not None:
        root = getattr(proj, "root_space", None)
    in_tree = False
    if isinstance(root, Space) and is_panel:
        in_tree = panel in collect_panels_from_space_tree(root)
    add_panel_print(f"[ADD_PANEL] verify panel_in_space_tree={in_tree}")

    mount = getattr(cmd, "_mount_space", None)
    in_groups = False
    if mount is not None and is_panel:
        for g in getattr(mount, "panel_groups", None) or []:
            pls = getattr(g, "panels", None) or []
            if panel in pls:
                in_groups = True
                break
    add_panel_print(f"[ADD_PANEL] verify panel_in_panel_groups={in_groups}")

    solve = ctx.get("last_solve_result")
    add_panel_print(
        f"[ADD_PANEL] verify solver_triggered={solve is not None} "
        f"success={getattr(solve, 'success', None)} "
        f"panel_list_len={len(getattr(solve, 'panel_list', None) or [])}"
    )

    display = (
        list(getattr(proj, "_cabinet_display_panels", None) or [])
        if proj is not None
        else []
    )
    in_display = is_panel and panel in display
    add_panel_print(
        f"[ADD_PANEL] verify view_rebuild_cache "
        f"in_display={in_display} display_count={len(display)}"
    )

    split_record = getattr(cmd, "_split_record", None)
    add_panel_print(
        f"[ADD_PANEL] verify topology_split="
        f"{split_record is not None and getattr(split_record, 'split_parent', None) is not None}"
    )
