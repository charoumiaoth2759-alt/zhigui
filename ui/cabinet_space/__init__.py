# -*- coding: utf-8 -*-
"""柜体参数化空间 —— 3D 可视化（与 `core.space.models.Space` 解耦）。

UI → Space（逻辑数据）→ SpaceVisual → GLView（pyqtgraph.opengl）
"""

from .scene_manager import SceneManager
from .param_space_gl_view import ParamSpaceGLView, make_root_cabinet_space

__all__ = ["SceneManager", "ParamSpaceGLView", "make_root_cabinet_space"]
