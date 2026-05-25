# -*- coding: utf-8 -*-
"""视图层交互拾取契约（``FaceType`` / ``HoverHitResult`` / ``pick_face_hover_*``）。"""

from .face_type import FaceType, face_type_to_space_face, space_face_to_face_type
from .face_selection_snapshot import FaceSelectionSnapshot, snapshot_from_hover
from .hover_hit_result import HoverHitResult, Vec3, build_hover_hit_result
from .hover_result import HoverResult
from .face_hover_rect import (
    FACE_HOVER_RECT_WIDTH_PX,
    FaceHoverRect,
    LEFT_FACE_HOVER_RECT_WIDTH_PX,
    RIGHT_FACE_HOVER_RECT_WIDTH_PX,
)
from .hover_pick import (
    pick_face_hover_at_screen,
    pick_face_hover_from_ray,
    pick_left_face_hover_at_screen,
    pick_left_face_hover_from_ray,
)

__all__ = [
    "FACE_HOVER_RECT_WIDTH_PX",
    "FaceHoverRect",
    "LEFT_FACE_HOVER_RECT_WIDTH_PX",
    "RIGHT_FACE_HOVER_RECT_WIDTH_PX",
    "FaceSelectionSnapshot",
    "FaceType",
    "snapshot_from_hover",
    "HoverHitResult",
    "HoverResult",
    "Vec3",
    "build_hover_hit_result",
    "face_type_to_space_face",
    "pick_face_hover_at_screen",
    "pick_face_hover_from_ray",
    "pick_left_face_hover_at_screen",
    "pick_left_face_hover_from_ray",
    "space_face_to_face_type",
]
