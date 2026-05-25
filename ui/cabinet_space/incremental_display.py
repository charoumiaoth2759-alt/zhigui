# -*- coding: utf-8 -*-

"""

加板 / 卸板后的**增量**场景展示（不重建整场景、不改相机 / 选择 / 交互模式）。

"""



from __future__ import annotations



from typing import Any



from core.space.space_models import Space

from core.space.tree import find_by_id, iter_subtree, resolve_space_root





def resolve_panel_target_space(

    panel: Any,

    *,

    root: Space | None = None,

    ctx: dict[str, Any] | None = None,

) -> Space | None:

    """由 ``panel.space_id`` 解析挂载目标 ``Space``。"""

    sid = getattr(panel, "space_id", None) or getattr(panel, "bound_space_id", None)

    if not sid:

        return None

    if root is not None:

        found = find_by_id(root, str(sid))

        if found is not None:

            return found

    if ctx is not None:

        proj = ctx.get("project")

        rs = getattr(proj, "root_space", None) if proj is not None else None

        if rs is not None:

            found = find_by_id(rs, str(sid))

            if found is not None:

                return found

        rs = ctx.get("root_space")

        if isinstance(rs, Space):

            return find_by_id(rs, str(sid))

    return None





def subtree_space_ids(anchor: Space, *, include_self: bool = True) -> set[str]:

    return {str(n.id) for n in iter_subtree(anchor, include_self=include_self)}





def apply_incremental_board_display(

    ctx: dict[str, Any],

    *,

    add_panels: list[Any] | None = None,

    remove_panel_ids: list[str] | None = None,

    target_space: Space | None = None,

    stats_action: str | None = None,

) -> None:

    """

    1. 追加 / 移除 board GL

    2. 仅刷新 ``target_space`` 子树空间盒样式

    3. 不 ``set_cabinet_space`` / ``set_root_space`` / ``_frame_camera``

    """

    canvas = ctx.get("canvas")

    project = ctx.get("project")

    root = getattr(project, "root_space", None) if project is not None else None

    if root is None:

        root = ctx.get("root_space")



    if target_space is None and add_panels:

        target_space = resolve_panel_target_space(

            add_panels[0], root=root if isinstance(root, Space) else None, ctx=ctx

        )



    # --- 主 3D（OpenGL paint 路径）---

    view = getattr(canvas, "_3d_view", None) if canvas is not None else None

    if view is not None:

        rm = [str(x) for x in (remove_panel_ids or []) if x]

        if rm and hasattr(view, "remove_display_panels_by_ids"):

            view.remove_display_panels_by_ids(rm)

        add = list(add_panels or [])

        if add and hasattr(view, "append_display_panels"):

            fn = getattr(view, "append_display_panels", None)

            if callable(fn):

                try:

                    view.append_display_panels(add, target_space=target_space)

                except TypeError:

                    view.append_display_panels(add)

        if target_space is not None and hasattr(view, "refresh_cabinet_spaces_incremental"):

            view.refresh_cabinet_spaces_incremental(target_space)

        elif (add or rm) and hasattr(view, "update"):

            view.update()



    try:

        if stats_action in ("add_left_panel", "add_right_panel", "add_shelf"):

            from ui.cabinet_debug_stats import print_cabinet_debug_stats



            print_cabinet_debug_stats(

                ctx,

                root=root if isinstance(root, Space) else None,

                action=stats_action,

                assert_visual_match=True,

            )

        elif add_panels or remove_panel_ids:

            from ui.cabinet_debug_stats import print_cabinet_debug_stats



            print_cabinet_debug_stats(

                ctx,

                root=root if isinstance(root, Space) else None,

                assert_visual_match=True,

            )

    except Exception as exc:

        print(f"[STATS] error: {exc}", flush=True)



    if canvas is None or not isinstance(root, Space):

        return

    mw = None

    win_fn = getattr(canvas, "window", None)

    if callable(win_fn):

        try:

            mw = win_fn()

        except Exception:

            mw = None

    if mw is None:

        return



    from ui.cabinet_space.param_space_gl_view import ParamSpaceGLView



    rm = [str(x) for x in (remove_panel_ids or []) if x]

    add = list(add_panels or [])

    anchor = target_space or root

    for pv in mw.findChildren(ParamSpaceGLView):

        r = getattr(pv, "_root", None)

        if r is None or id(r) != id(root):

            continue

        if rm:

            fn_rm = getattr(pv, "remove_panel_visuals_by_ids", None)

            if callable(fn_rm):

                fn_rm(rm)

        if add:

            fn_add = getattr(pv, "append_panel_visuals", None)

            if callable(fn_add):

                try:

                    fn_add(add, target_space=anchor)

                except TypeError:

                    fn_add(add)

        if anchor is not None:

            fn_sync = getattr(pv, "sync_spaces_tree_visuals", None)

            if callable(fn_sync):

                fn_sync(anchor)

            else:

                fn_sub = getattr(pv, "refresh_spaces_incremental", None)

                if callable(fn_sub):

                    fn_sub(anchor)

        elif add or rm:

            fn_refresh = getattr(pv, "_refresh_space_box_colors", None)

            if callable(fn_refresh):

                fn_refresh()

        fn_sync = getattr(pv, "_sync_add_left_preview", None)

        if callable(fn_sync):

            fn_sync()

        gl = getattr(pv, "_gl", None)

        if gl is not None and (add or rm or anchor is not None):

            gl.update()





__all__ = [

    "apply_incremental_board_display",

    "resolve_panel_target_space",

    "subtree_space_ids",

]

