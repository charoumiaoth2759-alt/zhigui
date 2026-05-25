# -*- coding: utf-8 -*-
"""
柜体 3D 主题色（线性 RGBA 0~1）。

``PREVIEW_COLOR`` / ``PANEL_COLOR`` / ``HOVER_COLOR`` 为唯一来源；
禁止在 ``draw_preview``、``panel_visual``、``view_3d`` 内按 LEFT/RIGHT 写死颜色或透明度。
"""

from __future__ import annotations

# 悬停 ghost（所有 ``FaceType`` / ``PanelRole`` 相同）
PREVIEW_COLOR: tuple[float, float, float, float] = (0.25, 0.82, 0.42, 0.42)

# 已挂载板件实体（左/右/顶/底/背统一材质与不透明）
PANEL_COLOR: tuple[float, float, float, float] = (
    205 / 255.0,
    170 / 255.0,
    120 / 255.0,
    1.0,
)

# 逻辑空间盒悬停高亮
HOVER_COLOR: tuple[float, float, float, float] = (
    168 / 255.0,
    1.0,
    1.0,
    200 / 255.0,
)

# 辅助（非左右分叉；棱线 / 悬停棱线）
PANEL_EDGE_COLOR: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
HOVER_EDGE_COLOR: tuple[float, float, float, float] = (0.15, 1.0, 1.0, 1.0)


def panel_face_rgb(
    *,
    unplaced: bool = False,
    blocked: bool = False,
    needs_relayout: bool = False,
) -> tuple[float, float, float, float]:
    """放置状态色；正常已放置板件一律 ``PANEL_COLOR``（不按 role 分叉）。"""
    if unplaced:
        return (0.95, 0.45, 0.25, 1.0)
    if blocked:
        return (0.92, 0.22, 0.18, 1.0)
    if needs_relayout:
        return (0.55, 0.75, 0.95, 1.0)
    return PANEL_COLOR


__all__ = [
    "HOVER_COLOR",
    "HOVER_EDGE_COLOR",
    "PANEL_COLOR",
    "PANEL_EDGE_COLOR",
    "PREVIEW_COLOR",
    "panel_face_rgb",
]
