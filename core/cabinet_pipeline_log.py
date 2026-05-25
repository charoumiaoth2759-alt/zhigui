# -*- coding: utf-8 -*-

"""

柜体加板管线统一日志（``FaceType`` / ``PanelRole``，禁止 left/right panel 字符串）。



典型序列::



    [Hover] FaceType.RIGHT detected

    [Preview] draw ghost FaceType.RIGHT

    [COMMAND] AddBoardCommand

    [SOLVER] solve cabinet

    [TOPOLOGY] rebuild

    [FACE_REGISTRY] rebuild



``ZHIGUI_PIPELINE_LOG=0`` 关闭；未设置时默认开启。

"""



from __future__ import annotations



import os

from typing import Any



_ENABLED = os.environ.get("ZHIGUI_PIPELINE_LOG", "1").strip() not in (

    "0",

    "false",

    "False",

    "no",

    "NO",

)



# ``log_hover_direction`` 去重：仅 ``space_id`` / ``face_type`` 变化时打印（``--verbose`` 时逐帧）

_LAST_HOVER_DIRECTION: tuple[str, str] | None = None





def pipeline_log_enabled() -> bool:

    return _ENABLED





def verbose_log_enabled() -> bool:

    """为真时悬停方向日志不去重（``--verbose`` / ``ZHIGUI_VERBOSE=1``）。"""

    return os.environ.get("ZHIGUI_VERBOSE", "").strip().lower() in (

        "1",

        "true",

        "yes",

        "on",

    )





def _emit(message: str) -> None:

    if _ENABLED:

        print(message, flush=True)





def face_type_label(face: Any) -> str:

    """``FaceType.RIGHT`` → ``FaceType.RIGHT``（禁止 ``right`` / ``right panel``）。"""

    name = getattr(face, "name", None)

    if name:

        return f"FaceType.{name}"

    return f"FaceType.{face!r}"





def panel_role_label(role: Any) -> str:

    """``PanelRole.RIGHT_SIDE`` 形式。"""

    name = getattr(role, "name", None)

    if name:

        return f"PanelRole.{name}"

    val = getattr(role, "value", None)

    if val:

        return f"PanelRole.{val}"

    return f"PanelRole.{role!r}"





def log_hover_direction(*, space_id: str, face_type: Any) -> None:
    """悬停方向快照；默认不打印（由 ``HoverCache`` 去重，``--verbose`` 时输出）。"""
    global _LAST_HOVER_DIRECTION
    ft = face_type_label(face_type)
    sid = str(space_id or "")
    key = (sid, ft)
    if not verbose_log_enabled():
        if _LAST_HOVER_DIRECTION == key:
            return
        _LAST_HOVER_DIRECTION = key
        return
    _emit(f"[HOVER]\nspace_id={sid}\nface_type={ft}")





def log_hover_direction_mismatch(

    *,

    clicked_face: Any,

    hovered_face: Any,

    space_id: str,

) -> None:

    _emit(

        f"[HOVER] direction mismatch\n"

        f"space_id={space_id}\n"

        f"clicked_face_type={face_type_label(clicked_face)}\n"

        f"hovered_face_type={face_type_label(hovered_face)}"

    )





def log_hover_detected(face: Any) -> None:
    """保留调用点；高频 ``detected`` 默认不打印。"""
    _ = face





def log_hover_occupancy(face: Any, *, free: bool) -> None:
    _ = face, free





def log_hover_occupancy_from_space(
    face: Any,
    space: Any,
    *,
    view: Any | None = None,
) -> None:
    """保留占用查询逻辑入口；默认不打印高频 ``[Hover] occupancy``。"""
    if view is None:
        from core.space.space_occupancy import query_space_occupancy

        view = query_space_occupancy(space, face)
    _ = face, space, view





def log_hover_clear() -> None:

    global _LAST_HOVER_DIRECTION

    _LAST_HOVER_DIRECTION = None

    _emit("[Hover] clear preview")





def log_hover_click_confirm(face: Any) -> None:

    _emit(f"[Hover] {face_type_label(face)} click confirm")





def log_preview_draw_ghost(face: Any | None = None) -> None:
    """保留调用点；高频 ``[Preview]`` 默认不打印。"""
    _ = face





def log_command(command_name: str, *, face: Any | None = None, role: Any | None = None) -> None:

    parts = [f"[COMMAND] {command_name}"]

    if face is not None:

        parts.append(face_type_label(face))

    if role is not None:

        parts.append(panel_role_label(role))

    _emit(" ".join(parts))





def log_solver_solve_cabinet(*, dirty_count: int | None = None) -> None:

    if dirty_count is not None and dirty_count > 0:

        _emit(f"[SOLVER] solve cabinet dirty={dirty_count}")

    else:

        _emit("[SOLVER] solve cabinet")





def log_topology(message: str) -> None:

    """``message`` 须以 ``[TOPOLOGY]`` 开头。"""

    if not message.startswith("[TOPOLOGY]"):

        message = f"[TOPOLOGY] {message}"

    _emit(message)





def log_face_registry(message: str) -> None:

    """``message`` 须以 ``[FACE_REGISTRY]`` 开头。"""

    if not message.startswith("[FACE_REGISTRY]"):

        message = f"[FACE_REGISTRY] {message}"

    _emit(message)





def log_interaction_mode(mode: str) -> None:

    _emit(f"[MODE] {mode}")





def log_pipeline_stage(stage: str) -> None:

    _emit(f"[Pipeline] {stage}")





def log_display_panel_visual(*, add: bool = True) -> None:

    _emit("[Display] add panel visual" if add else "[Display] remove panel visual")





__all__ = [

    "face_type_label",

    "log_command",

    "log_display_panel_visual",

    "log_face_registry",

    "log_hover_clear",

    "log_hover_click_confirm",

    "log_hover_direction",

    "log_hover_direction_mismatch",

    "log_hover_detected",

    "log_hover_occupancy",

    "log_hover_occupancy_from_space",

    "log_interaction_mode",

    "log_pipeline_stage",

    "log_preview_draw_ghost",

    "log_solver_solve_cabinet",

    "log_topology",

    "panel_role_label",

    "pipeline_log_enabled",

    "verbose_log_enabled",

]

