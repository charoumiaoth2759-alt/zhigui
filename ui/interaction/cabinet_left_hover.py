# -*- coding: utf-8 -*-
"""兼容 re-export → ``hover_session``（勿在新代码中引用本模块）。"""

from __future__ import annotations

from view.interaction.face_type import FaceType

from .hover_session import (
    SpaceFaceHoverSession,
    clear_session,
    update_session_from_hit,
)

# 已废弃：请用 ``preview_spec.primary_hover_face_for_mode``
ADD_PANEL_HOVER_FACE = FaceType.LEFT
LeftFaceHoverSession = SpaceFaceHoverSession

__all__ = [
    "ADD_PANEL_HOVER_FACE",
    "LeftFaceHoverSession",
    "SpaceFaceHoverSession",
    "clear_session",
    "update_session_from_hit",
]
