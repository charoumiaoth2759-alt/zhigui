# -*- coding: utf-8 -*-
"""当前悬停会话态（space / face / 预览可见性）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class HoverState:
    hovered_space_id: Optional[str] = None
    hovered_face_type: Optional[object] = None
    preview_visible: bool = False


__all__ = ["HoverState"]
