# -*- coding: utf-8 -*-

"""

交互预览规格：由 ``InteractionMode`` + ``FaceType`` 决定 ghost 几何、放置校验与命令。



禁止在 Viewport / PreviewManager 内硬编码「左侧板 ghost」。

"""



from __future__ import annotations



from dataclasses import dataclass

from typing import Any, Callable



from core.constants.enums import AnchorType

from core.panel.side_panel_spec import SidePanelSpec, iter_side_panel_specs, spec_for_face

from core.space.space_face_occupancy import FaceType



from ui.theme_constants import PREVIEW_COLOR

from .interaction_mode import InteractionMode



BoardForSpaceFn = Callable[[Any], Any | None]

StackOffsetFn = Callable[[Any], float]





@dataclass(frozen=True)

class PreviewGhostMesh:

    """OpenGL / pyqtgraph 共用的轴对齐盒预览（世界 mm）。"""



    corners: tuple[tuple[float, float, float], ...]

    triangles: tuple[tuple[int, int, int], ...]

    rgba: tuple[float, float, float, float] = PREVIEW_COLOR





@dataclass(frozen=True)

class InteractionPreviewSpec:

    """``(InteractionMode, FaceType)`` → 悬停预览与提交语义。"""



    mode: InteractionMode

    face: FaceType

    default_thickness_mm: float

    stack_offset_mm: StackOffsetFn

    board_for_validate: Callable[[Any, float], Any]

    build_ghost_mesh: Callable[[Any, float, float], PreviewGhostMesh | None]

    command_name: str





_GHOST_TRIS = (

    (0, 2, 1),

    (0, 3, 2),

    (4, 5, 6),

    (4, 6, 7),

    (0, 1, 5),

    (0, 5, 4),

    (2, 3, 7),

    (2, 7, 6),

    (0, 4, 7),

    (0, 7, 3),

    (1, 2, 6),

    (1, 6, 5),

)



def _build_add_panel_side_ghost(

    space: Any,

    thickness_mm: float,

    stack_offset_mm: float,

    *,

    anchor: AnchorType,

) -> PreviewGhostMesh | None:

    if space is None:

        return None

    t = max(float(thickness_mm), 0.01)

    stack = float(stack_offset_mm)

    y0, y1 = float(space.y), float(space.y + space.height)

    z0, z1 = float(space.z), float(space.z + space.depth)

    if anchor in (AnchorType.LEFT, AnchorType.RIGHT):

        if anchor == AnchorType.LEFT:

            x0 = float(space.x) + stack

            x1 = x0 + t

        else:

            x1 = float(space.x) + float(space.width) - stack

            x0 = x1 - t

        rgba = PREVIEW_COLOR

    else:

        return None

    corners = (

        (x0, y0, z0),

        (x1, y0, z0),

        (x1, y0, z1),

        (x0, y0, z1),

        (x0, y1, z0),

        (x1, y1, z0),

        (x1, y1, z1),

        (x0, y1, z1),

    )

    return PreviewGhostMesh(corners=corners, triangles=_GHOST_TRIS, rgba=rgba)





def _stack_offset_for_spec(spec: SidePanelSpec) -> StackOffsetFn:

    from core.panel.panel_placement import side_stack_offset_mm



    role = spec.role



    def _fn(space: Any) -> float:

        return float(side_stack_offset_mm(space, role))



    return _fn





def _board_for_validate_for_spec(spec: SidePanelSpec) -> Callable[[Any, float], Any]:

    from core.space.space_placement_sync import side_preview_board_for_validate



    face = spec.face



    def _fn(space: Any, thickness_mm: float) -> Any:

        return side_preview_board_for_validate(

            space, face=face, thickness=thickness_mm

        )



    return _fn





def _ghost_builder_for_spec(spec: SidePanelSpec) -> Callable[[Any, float, float], PreviewGhostMesh | None]:

    anchor = spec.anchor



    def _fn(space: Any, thickness_mm: float, stack_mm: float) -> PreviewGhostMesh | None:

        return _build_add_panel_side_ghost(

            space, thickness_mm, stack_mm, anchor=anchor

        )



    return _fn





def _register_side_panel_preview(spec: SidePanelSpec) -> InteractionPreviewSpec:

    return InteractionPreviewSpec(

        mode=InteractionMode.ADD_PANEL,

        face=spec.face,

        default_thickness_mm=18.0,

        stack_offset_mm=_stack_offset_for_spec(spec),

        board_for_validate=_board_for_validate_for_spec(spec),

        build_ghost_mesh=_ghost_builder_for_spec(spec),

        command_name=spec.command_name,

    )





_PREVIEW_SPECS: dict[tuple[InteractionMode, FaceType], InteractionPreviewSpec] = {

    (InteractionMode.ADD_PANEL, sp.face): _register_side_panel_preview(sp)

    for sp in iter_side_panel_specs()

}





def resolve_preview_spec(

    mode: InteractionMode, face: FaceType

) -> InteractionPreviewSpec | None:

    return _PREVIEW_SPECS.get((mode, face))





def primary_hover_face_for_mode(mode: InteractionMode) -> FaceType | None:

    """该交互模式下默认可拾取 / 预览的目标面（当前每模式一面）。"""

    for (m, f) in _PREVIEW_SPECS:

        if m == mode:

            return f

    return None





def effective_preview_mode(interaction_mode: InteractionMode, tool_mode: Any) -> InteractionMode:

    """

    选择 / 加侧板工具下，悬停预览按 ``ADD_PANEL`` + 工具对应 ``FaceType``。

    """

    from ui.cabinet_space.tool_modes import ToolMode



    from .face_interaction import face_for_tool_mode

    ft = face_for_tool_mode(tool_mode)

    if ft is not None and resolve_preview_spec(InteractionMode.ADD_PANEL, ft) is not None:

        return InteractionMode.ADD_PANEL

    if tool_mode == ToolMode.SELECT:

        for sp in iter_side_panel_specs():

            if resolve_preview_spec(InteractionMode.ADD_PANEL, sp.face) is not None:

                return InteractionMode.ADD_PANEL

    return interaction_mode





def preview_face_for_tool_mode(tool_mode: Any) -> FaceType | None:

    """兼容别名 → ``face_interaction.face_for_tool_mode``。"""

    from .face_interaction import face_for_tool_mode

    return face_for_tool_mode(tool_mode)





__all__ = [

    "InteractionPreviewSpec",

    "PreviewGhostMesh",

    "effective_preview_mode",

    "preview_face_for_tool_mode",

    "primary_hover_face_for_mode",

    "resolve_preview_spec",

]

