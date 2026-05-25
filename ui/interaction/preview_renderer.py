# -*- coding: utf-8 -*-

"""

预览绘制：唯一入口，从 ``PreviewMeshCache`` 读取状态（禁止 hover 时 new/rebuild mesh）。

"""



from __future__ import annotations



from typing import Any



from ui.cabinet_design_host import resolve_cabinet_interaction_manager



from .preview_draw import draw_preview_mesh_cache_gl

from .preview_mesh_cache import get_preview_mesh_cache





def draw_viewport_preview_ghost(viewport: Any, gl: Any) -> bool:

    """

    按 ``PreviewMeshCache`` 绘制预览（``show`` + 变换；不 ``build_active_ghost_mesh``）。



    :return: 是否绘制了 ghost

    """

    mgr = resolve_cabinet_interaction_manager(viewport)

    cache = get_preview_mesh_cache()

    if mgr is None or not mgr.preview.active or not cache.visible:

        return False



    if hasattr(gl, "GL_TRIANGLES"):

        mgr.preview.mark_ghost_drawn()

        draw_preview_mesh_cache_gl(gl, cache)

        return True



    cache.show(gl)

    mgr.preview.mark_ghost_drawn()

    return True





def clear_param_space_preview_ghost(gl: Any) -> None:

    get_preview_mesh_cache().hide()

    get_preview_mesh_cache().detach_pg(gl)





def hide_all_preview_meshes() -> None:

    get_preview_mesh_cache().hide()





__all__ = [

    "clear_param_space_preview_ghost",

    "draw_viewport_preview_ghost",

    "hide_all_preview_meshes",

]

