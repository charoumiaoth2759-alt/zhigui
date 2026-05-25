# -*- coding: utf-8 -*-

"""柜体交互日志（委托 ``core.cabinet_pipeline_log``，保持旧 import 路径）。"""



from __future__ import annotations



from typing import Any



from core.cabinet_pipeline_log import (

    log_command,

    log_display_panel_visual,

    log_hover_clear,

    log_hover_click_confirm,

    log_hover_detected,

    log_hover_direction,

    log_hover_direction_mismatch,

    log_hover_occupancy_from_space,

    log_preview_draw_ghost,

)

from view.interaction.face_type import FaceType





def log_view3d_add_panel_visual() -> None:

    log_display_panel_visual(add=True)





def log_view3d_remove_panel_visual() -> None:

    log_display_panel_visual(add=False)





def log_hover_face_detected(face: FaceType) -> None:

    log_hover_detected(face)





def log_hover_face_occupancy(face: FaceType, space: Any, *, occupied: bool) -> None:

    from core.space.space_occupancy import query_space_occupancy



    view = query_space_occupancy(space, face)

    log_hover_occupancy_from_space(face, space, view=view)





def log_view3d_draw_preview_ghost(mode: Any = None, face: FaceType | None = None) -> None:

    _ = mode

    log_preview_draw_ghost(face)





def log_hover_face_direction(face: FaceType, space: Any) -> None:

    sid = str(getattr(space, "id", "") or "")

    log_hover_direction(space_id=sid, face_type=face)





__all__ = [

    "log_command",

    "log_hover_clear",

    "log_hover_click_confirm",

    "log_hover_direction_mismatch",

    "log_hover_face_detected",

    "log_hover_face_direction",

    "log_hover_face_occupancy",

    "log_view3d_add_panel_visual",

    "log_view3d_draw_preview_ghost",

    "log_view3d_remove_panel_visual",

]

