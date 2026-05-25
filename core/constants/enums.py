# -*- coding: utf-8 -*-
"""
板件与工艺相关枚举。

`SpaceType` / `SplitDirection` 与 `core.space.enums` 中为同一套定义，在此再导出，
供 `core.panel` / `core.space.resolver` 等使用统一 import 路径 `core.constants.enums`。

``SplitDirection`` 的轴判断辅助函数一并从此包导出。
"""

from __future__ import annotations

from enum import Enum

from core.space.enums import (
    SpaceType,
    SplitDirection,
    is_split_along_x,
    is_split_along_y,
    is_split_along_z,
)


class PanelRole(str, Enum):
    """板件结构/开口角色。"""

    UNKNOWN = "unknown"
    LEFT = "left"
    LEFT_SIDE = "left_side"
    RIGHT = "right"
    RIGHT_SIDE = "right_side"  # 与 ``FaceType.RIGHT`` 侧板管道配对
    TOP = "top"
    BOTTOM = "bottom"
    BACK = "back"
    SHELF = "shelf"
    DIVIDER = "divider"
    DOOR_LEFT = "door_left"
    DOOR_RIGHT = "door_right"
    DOOR_DOUBLE = "door_double"
    DRAWER_FRONT = "drawer_front"


class EdgeBandFace(str, Enum):
    """板件暴露棱边（用于封边扣减）。"""

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class PanelOrientation(str, Enum):
    """板件主平面法向与 **厚度所在世界轴**（与 ``core.panel.panel_bounds`` 一致）。

    **VERTICAL_X**：法向 +X，板面在 YZ；**thickness 沿 X** →
    ``(Δx,Δy,Δz)=(thickness,height,width)``。

    **VERTICAL_Z**：法向 +Z，板面在 XY；**thickness 沿 Z** →
    ``(Δx,Δy,Δz)=(width,height,thickness)``。

    **HORIZONTAL**：法向 +Y，板面在 XZ；**thickness 沿 Y** →
    ``(Δx,Δy,Δz)=(width,thickness,height)``（``height`` 作沿 Z 的外观尺寸）。

    最小角均为 ``(panel.x, panel.y, panel.z)``。
    """

    HORIZONTAL = "horizontal"
    VERTICAL_X = "vertical_x"
    VERTICAL_Z = "vertical_z"


class PlacementMode(str, Enum):
    """板件与空间的相对关系：锚定贴边 vs 自动布局（层板/中隔板等）。"""

    ANCHOR_FIXED = "anchor_fixed"
    AUTO_PLACED = "auto_placed"


class AnchorType(str, Enum):
    """锚定到哪条空间外（内）边界（与柜体坐标系一致）。"""

    NONE = "none"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    FRONT = "front"
    BACK = "back"


# 空间六面方位（canonical 定义在 ``core.space.space_face_occupancy``）
from core.space.space_face_occupancy import FaceType  # noqa: E402

# LEFT / RIGHT 侧板：与 ``core.panel.panel_face_mapper.SIDE_PANEL_FACE_ROLES`` 同源
def __getattr__(name: str):
    if name == "SIDE_PANEL_FACE_ROLES":
        from core.panel.panel_face_mapper import SIDE_PANEL_FACE_ROLES as _m

        return _m
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SpaceType",
    "SplitDirection",
    "is_split_along_x",
    "is_split_along_y",
    "is_split_along_z",
    "PanelRole",
    "EdgeBandFace",
    "PanelOrientation",
    "PlacementMode",
    "AnchorType",
    "FaceType",
    "SIDE_PANEL_FACE_ROLES",
]
