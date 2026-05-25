# -*- coding: utf-8 -*-
"""
悬停检测：Viewport 仅提供屏幕坐标，拾取由 ``HoverDetector`` 产出 ``HoverHitResult``。

禁止 Viewport 内直接拾取 / 维护悬停会话；仅 ``pick_face_hover_at_screen``。
"""

from __future__ import annotations

from typing import Any, Protocol

from view.interaction.face_type import FaceType
from view.interaction.hover_hit_result import HoverHitResult
from view.interaction.hover_pick import pick_face_hover_at_screen

from ui.cabinet_design_host import resolve_cabinet_interaction_manager

# 侧板悬停热区宽度见 ``view.interaction.face_hover_rect``（LEFT/RIGHT 各 14px）


def _resolve_hover_target_face(viewport: Any) -> FaceType | None:
    """工具钉定的面（如 ADD_RIGHT_PANEL）；``SELECT`` 为 ``None`` → 双侧板竞态拾取。"""
    mgr = resolve_cabinet_interaction_manager(viewport)
    if mgr is not None:
        return mgr.preview.hover_target_face()
    return None

VIEWPORT_MAIN_3D = "main_3d"
VIEWPORT_PARAM_SPACE = "param_space"


class HoverDetector(Protocol):
    """Viewport → ``HoverHitResult`` 检测器。"""

    @property
    def viewport_id(self) -> str:
        ...

    def detect_hover(self, screen_x: float, screen_y: float) -> HoverHitResult | None:
        ...


class Main3DHoverDetector:
    """主 ``View3D``：屏幕射线 + LEFT / RIGHT 侧板面叶空间拾取。"""

    viewport_id = VIEWPORT_MAIN_3D

    def __init__(self, view3d: Any) -> None:
        self._view = view3d

    def detect_hover(self, screen_x: float, screen_y: float) -> HoverHitResult | None:
        v = self._view
        ray_fn = getattr(v, "_cabinet_screen_ray_mm", None)
        if not callable(ray_fn):
            return None
        root = getattr(v, "_cabinet_space", None)
        engine = getattr(v, "_space_pick_engine", None)
        if root is None or engine is None:
            return None
        target_face = _resolve_hover_target_face(v)
        w2s = getattr(v, "_cabinet_world_to_screen_px", None)
        return pick_face_hover_at_screen(
            root,
            ray_fn,
            screen_x,
            screen_y,
            constraint_engine=engine,
            target_face=target_face,
            margin_mm=120.0,
            world_to_screen=w2s if callable(w2s) else None,
        )


class ParamSpaceHoverDetector:
    """参数空间 ``ParamSpaceGLView``：pyqtgraph 射线 + LEFT / RIGHT 侧板面拾取。"""

    viewport_id = VIEWPORT_PARAM_SPACE

    def __init__(self, param_view: Any) -> None:
        self._pv = param_view

    def detect_hover(self, screen_x: float, screen_y: float) -> HoverHitResult | None:
        from ui.cabinet_space.gl_ray_utils import gl_screen_ray

        root = getattr(self._pv, "_root", None)
        gl = getattr(self._pv, "_gl", None)
        if root is None or gl is None:
            return None
        from core.space.cabinet_ops_lock import cabinet_space_constraint_engine

        target_face = _resolve_hover_target_face(self._pv)
        from ui.cabinet_space.gl_ray_utils import gl_world_to_screen_px

        return pick_face_hover_at_screen(
            root,
            lambda x, y: gl_screen_ray(gl, x, y),
            screen_x,
            screen_y,
            constraint_engine=cabinet_space_constraint_engine(),
            target_face=target_face,
            margin_mm=120.0,
            world_to_screen=lambda wx, wy, wz: gl_world_to_screen_px(gl, wx, wy, wz),
        )


__all__ = [
    "HoverDetector",
    "Main3DHoverDetector",
    "ParamSpaceHoverDetector",
    "VIEWPORT_MAIN_3D",
    "VIEWPORT_PARAM_SPACE",
]
