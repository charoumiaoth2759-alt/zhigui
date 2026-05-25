# -*- coding: utf-8 -*-
"""
空间悬停控制器（HoverController）。

主 3D / 参数空间共用：拾取 → ``HoverCache`` → 预览 ghost。
"""

from __future__ import annotations

from typing import Any

from .cabinet_interaction_manager import CabinetInteractionManager
from .hover_cache import HoverCache


class SpaceHoverController(CabinetInteractionManager):
    """柜体空间面悬停：``pick_face`` → ``current_hover`` → ``preview_manager.show``。"""

    def __init__(self, host: Any) -> None:
        super().__init__(host)
        self.hover_cache = HoverCache()


HoverController = SpaceHoverController

__all__ = ["HoverController", "SpaceHoverController"]
