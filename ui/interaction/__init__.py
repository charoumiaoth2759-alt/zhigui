# -*- coding: utf-8 -*-
"""
柜体用户交互统一架构::

    Mouse Move → HoverDetector → HoverHitResult
    → InteractionManager → Preview System →（确认后）Incremental Scene Update

禁止：字符串 side、``left-side``、Viewport 内硬编码 ghost、散乱 ``hover_pick_fn``。
"""

from .cabinet_interaction_manager import CabinetInteractionManager, HoverController
from .space_hover_controller import SpaceHoverController
from .face_interaction import (
    face_for_tool_mode,
    is_side_panel_face,
    process_face_click,
    process_face_hover,
    side_panel_face_blocks_interaction,
    tool_mode_for_face,
)
from .cabinet_interaction_sources import CabinetInteractionSource
from .hover_detector import (
    HoverDetector,
    Main3DHoverDetector,
    ParamSpaceHoverDetector,
    VIEWPORT_MAIN_3D,
    VIEWPORT_PARAM_SPACE,
)
from .hover_cache import HoverCache
from .hover_session import SpaceFaceHoverSession, clear_session, update_session_from_hit
from .hover_state import HoverState
from .interaction_mode import InteractionMode
from .preview_draw import draw_preview_ghost_mesh_gl, draw_preview_mesh_cache_gl
from .preview_manager import PreviewManager, PreviewTickResult
from .preview_mesh_cache import PreviewMeshCache, get_preview_mesh_cache
from .preview_renderer import (
    clear_param_space_preview_ghost,
    draw_viewport_preview_ghost,
    hide_all_preview_meshes,
)
from .preview_spec import (
    InteractionPreviewSpec,
    PreviewGhostMesh,
    effective_preview_mode,
    primary_hover_face_for_mode,
    resolve_preview_spec,
)
from core.space.face_click_resolve import find_space, resolve_space_from_face_snapshot
from core.space.face_selection_snapshot import (
    FACE_SELECTION_PAYLOAD_KEY,
    FaceSelectionSnapshot,
    face_snapshot_from_payload,
)
from view.interaction.face_type import FaceType
from view.interaction.hover_hit_result import HoverHitResult, Vec3
from .interaction_log import (
    log_command,
    log_hover_clear,
    log_hover_click_confirm,
    log_hover_face_detected,
    log_view3d_add_panel_visual,
    log_view3d_draw_preview_ghost,
    log_view3d_remove_panel_visual,
)

__all__ = [
    "CabinetInteractionManager",
    "HoverController",
    "SpaceHoverController",
    "CabinetInteractionSource",
    "FACE_SELECTION_PAYLOAD_KEY",
    "FaceSelectionSnapshot",
    "face_for_tool_mode",
    "face_snapshot_from_payload",
    "find_space",
    "resolve_space_from_face_snapshot",
    "is_side_panel_face",
    "process_face_click",
    "process_face_hover",
    "side_panel_face_blocks_interaction",
    "tool_mode_for_face",
    "HoverCache",
    "HoverDetector",
    "HoverState",
    "InteractionMode",
    "Main3DHoverDetector",
    "ParamSpaceHoverDetector",
    "InteractionPreviewSpec",
    "PreviewGhostMesh",
    "PreviewManager",
    "PreviewTickResult",
    "SpaceFaceHoverSession",
    "clear_session",
    "update_session_from_hit",
    "PreviewMeshCache",
    "draw_preview_ghost_mesh_gl",
    "draw_preview_mesh_cache_gl",
    "draw_viewport_preview_ghost",
    "clear_param_space_preview_ghost",
    "get_preview_mesh_cache",
    "hide_all_preview_meshes",
    "effective_preview_mode",
    "primary_hover_face_for_mode",
    "resolve_preview_spec",
    "VIEWPORT_MAIN_3D",
    "VIEWPORT_PARAM_SPACE",
    "HoverHitResult",
    "FaceType",
    "Vec3",
    "log_command",
    "log_hover_clear",
    "log_hover_click_confirm",
    "log_hover_face_detected",
    "log_view3d_add_panel_visual",
    "log_view3d_draw_preview_ghost",
    "log_view3d_remove_panel_visual",
]
