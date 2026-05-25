# -*- coding: utf-8 -*-
"""参数空间：仅转发左键确认；悬停 / ghost 由 InteractionManager → Preview System 统一处理。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt

from ui.cabinet_design_host import resolve_cabinet_interaction_manager
from ui.interaction import CabinetInteractionSource
from ui.interaction.hover_detector import VIEWPORT_PARAM_SPACE

from .base_tool import BaseTool


def _event_local_xy(event: Any) -> tuple[float, float]:
    pos = event.position() if hasattr(event, "position") else event.localPos()
    return float(pos.x()), float(pos.y())


class AddLeftPanelTool(BaseTool):
    """不拾取、不绘制 ghost；``paintGL`` 经 ``preview_renderer``。"""

    def __init__(self) -> None:
        self.preview_thickness = 18.0

    def reset(self, gl: Any | None = None) -> None:
        if gl is not None:
            from ui.interaction.preview_renderer import clear_param_space_preview_ghost

            clear_param_space_preview_ghost(gl)

    def on_mouse_move(self, event: Any, gl: Any, context: dict[str, Any] | None = None) -> bool:
        return False

    def on_mouse_press(self, event: Any, gl: Any, context: dict[str, Any] | None = None) -> bool:
        if context is None or gl is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pv = context.get("param_view")
        if pv is None or context.get("space") is None:
            return False

        sx, sy = _event_local_xy(event)
        mgr = resolve_cabinet_interaction_manager(pv)
        if mgr is None:
            return False
        from ui.cabinet_space.tool_modes import ToolMode

        if mgr.on_face_clicked(
            VIEWPORT_PARAM_SPACE,
            sx,
            sy,
            viewport=pv,
            source=CabinetInteractionSource.PARAM_SPACE_TOOL,
            tool_mode=ToolMode.ADD_LEFT_PANEL,
        ):
            self.preview_thickness = mgr.preview.default_thickness_mm()
            return True
        return False

    def on_mouse_release(self, event: Any, gl: Any, context: dict[str, Any] | None = None) -> bool:
        return False

    def draw_preview(self, gl: Any, context: dict[str, Any] | None = None) -> None:
        """遗留 ``BaseTool`` 接口；实际绘制在 ``preview_renderer.draw_viewport_preview_ghost``。"""
        pv = (context or {}).get("param_view")
        if pv is None:
            return
        from ui.interaction.preview_renderer import draw_viewport_preview_ghost

        draw_viewport_preview_ghost(pv, gl)
