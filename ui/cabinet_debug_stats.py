# -*- coding: utf-8 -*-
"""柜体设计调试统计（验证 panel visual / space / dirty 一致性）。"""

from __future__ import annotations

import os
from typing import Any

_STATS_ENABLED = os.environ.get("ZHIGUI_STATS", "1").strip() not in (
    "0",
    "false",
    "False",
    "no",
    "NO",
)


def _count_real_panels(root: Any | None, cabinet: Any | None) -> int:
    if root is not None:
        from core.space.space_consistency_manager import collect_panels_from_space_tree

        return len(collect_panels_from_space_tree(root))
    panels = getattr(cabinet, "panels", None)
    if panels is not None:
        return len(list(panels))
    return 0


def _count_spaces(root: Any | None) -> tuple[int, int]:
    """
    统计叶空间数量（柜格 / 可放置容积单元）。

    切分后父节点 ``SPLIT`` 不计入；仅 ``iter_leaves``，与
    ``add left panel → 2`` / ``add right → 3`` / ``add shelf → 5`` 一致。
    """
    if root is None:
        return 0, 0
    from core.dirty.dirty_flags import DirtyFlag
    from core.space.tree import iter_leaves

    total = 0
    dirty = 0
    for node in iter_leaves(root):
        total += 1
        if getattr(node, "dirty_flag", DirtyFlag.CLEAN) is not DirtyFlag.CLEAN:
            dirty += 1
    return total, dirty


def _count_view3d_panel_visuals(ctx: dict[str, Any] | None) -> int:
    if not ctx:
        return 0
    canvas = ctx.get("canvas")
    if canvas is None:
        return 0
    view = getattr(canvas, "_3d_view", None)
    if view is None:
        return 0
    pv = getattr(view, "panel_visuals", None)
    if callable(pv):
        return len(pv())
    return 0


def _count_param_panel_visuals(ctx: dict[str, Any] | None, root: Any | None) -> int:
    if not ctx or root is None:
        return 0
    canvas = ctx.get("canvas")
    if canvas is None:
        return 0
    mw = None
    win_fn = getattr(canvas, "window", None)
    if callable(win_fn):
        try:
            mw = win_fn()
        except Exception:
            mw = None
    if mw is None:
        return 0
    try:
        from ui.cabinet_space.param_space_gl_view import ParamSpaceGLView
    except ImportError:
        return 0
    total = 0
    for pv in mw.findChildren(ParamSpaceGLView):
        r = getattr(pv, "_root", None)
        if r is None or id(r) != id(root):
            continue
        scene = getattr(pv, "_scene", None)
        if scene is not None:
            total += int(getattr(scene, "panel_visual_count", lambda: 0)())
    return total


def _resolve_view3d(ctx: dict[str, Any] | None, view3d: Any | None) -> Any | None:
    if view3d is not None:
        return view3d
    if not ctx:
        return None
    canvas = ctx.get("canvas")
    if canvas is None:
        return None
    return getattr(canvas, "_3d_view", None)


def print_cabinet_debug_stats(
    ctx: dict[str, Any] | None = None,
    *,
    root: Any | None = None,
    cabinet: Any | None = None,
    view3d: Any | None = None,
    action: str | None = None,
    assert_visual_match: bool = True,
) -> bool:
    """
    打印稳定性统计（主 3D ``panel_visuals`` 与空间树真实板件 1:1）::

        [STATS]
        real panels = N
        panel visuals = M
        spaces = T

    ``action`` 例如 ``add_right_panel``；``assert_visual_match`` 为真且不一致时打印 ``invariant FAIL``。
    返回是否满足 ``panel visuals == real panels``（仅计 View3D 绘制列表）。
    """
    if not _STATS_ENABLED:
        return True
    if root is None and ctx is not None:
        proj = ctx.get("project")
        root = getattr(proj, "root_space", None) if proj is not None else None
        if root is None:
            root = ctx.get("root_space")
    if cabinet is None and ctx is not None:
        cabinet = ctx.get("project") or ctx.get("cabinet")

    real = _count_real_panels(root, cabinet)
    total_spaces, dirty_count = _count_spaces(root)

    v3d = _resolve_view3d(ctx, view3d)
    if v3d is not None:
        pv = getattr(v3d, "panel_visuals", None)
        view3d_visual = len(pv()) if callable(pv) else len(pv or [])
    else:
        view3d_visual = _count_view3d_panel_visuals(ctx)

    param_visual = _count_param_panel_visuals(ctx, root)

    _ACTION_LABELS = {
        "add_left_panel": "add left panel",
        "add_right_panel": "add right panel",
        "add_shelf": "add shelf",
    }

    print("[STATS]", flush=True)
    if action:
        print(_ACTION_LABELS.get(action, action), flush=True)
    print(f"real panels = {real}", flush=True)
    print(f"panel visuals = {view3d_visual}", flush=True)
    print(f"spaces = {total_spaces}", flush=True)
    if dirty_count:
        print(f"dirty spaces = {dirty_count}", flush=True)
    if param_visual and param_visual != view3d_visual:
        print(f"param panel visuals = {param_visual}", flush=True)

    ok = view3d_visual == real
    if assert_visual_match and not ok:
        print(
            f"[STATS] invariant FAIL: panel visuals ({view3d_visual}) != real panels ({real})",
            flush=True,
        )
    return ok


def print_stats_after_right_panel_add(ctx: dict[str, Any] | None) -> bool:
    """每次添加 ``RIGHT_PANEL`` 后调用（``ZHIGUI_STATS=0`` 可关闭）。"""
    return print_cabinet_debug_stats(
        ctx, action="add_right_panel", assert_visual_match=True
    )


__all__ = [
    "print_cabinet_debug_stats",
    "print_stats_after_right_panel_add",
]
