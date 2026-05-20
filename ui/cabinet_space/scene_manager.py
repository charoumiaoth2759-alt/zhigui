# -*- coding: utf-8 -*-
"""管理所有 `SpaceVisual` 与 GL 视图项的挂载/卸载。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.space.models import Space

from .space_visual import SpaceVisual, is_pyqtgraph_gl_available

if TYPE_CHECKING:
    pass


class SceneManager:
    """管理 `SpaceVisual` 集合；不持有 `Space` 业务逻辑。"""

    def __init__(self, gl_view):
        self._gl_view = gl_view
        self._visuals: dict[str, SpaceVisual] = {}

    def add_space(self, space: Space) -> SpaceVisual | None:
        if not is_pyqtgraph_gl_available():
            return None
        self.remove_space(space)
        vis = SpaceVisual(space)
        vis.attach(self._gl_view)
        self._visuals[space.id] = vis
        return vis

    def remove_space(self, space: Space) -> None:
        vis = self._visuals.pop(space.id, None)
        if vis is not None:
            vis.detach(self._gl_view)

    def clear(self) -> None:
        for vis in list(self._visuals.values()):
            vis.detach(self._gl_view)
        self._visuals.clear()
