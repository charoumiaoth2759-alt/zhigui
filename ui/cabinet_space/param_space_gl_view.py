# -*- coding: utf-8 -*-
"""参数化根空间 3D 预览：pyqtgraph.opengl + 尺寸文字叠加。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.space.enums import SpaceType
from core.space.models import Space

from .scene_manager import SceneManager
from .space_visual import is_pyqtgraph_gl_available

try:
    import pyqtgraph as pg
    from pyqtgraph.opengl import GLViewWidget

    _HAS_PG = True
except ImportError:  # pragma: no cover
    pg = None  # type: ignore
    GLViewWidget = None  # type: ignore
    _HAS_PG = False


class ParamSpaceGLView(QWidget):
    """含 `GLViewWidget` 的柜体逻辑空间预览；无 pyqtgraph 时降级为提示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: Space | None = None
        self._scene: SceneManager | None = None
        self._gl: QWidget | None = None

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        if _HAS_PG:
            self._gl = GLViewWidget()
            self._gl.setBackgroundColor((0.92, 0.95, 0.99, 1.0))
            # 轨道旋转 / 平移 / 缩放：pyqtgraph 默认鼠标交互
            self._gl.opts["distance"] = 5200
            self._scene = SceneManager(self._gl)
            root_lay.addWidget(self._gl, 1)
        else:
            tip = QLabel(
                "未安装 pyqtgraph，无法显示参数化空间 3D 预览。\n"
                "请执行：pip install pyqtgraph"
            )
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip.setWordWrap(True)
            tip.setStyleSheet(
                "color:#606266; font-size:13px; padding:24px; background:#f5f7fa;"
            )
            root_lay.addWidget(tip, 1)
            self._gl = None

        self._dim_lbl = QLabel("")
        self._dim_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._dim_lbl.setStyleSheet(
            "QLabel {"
            "  background: rgba(255,255,255,0.88);"
            "  color: #303133;"
            "  font-size: 13px;"
            "  font-weight: bold;"
            "  padding: 6px 10px;"
            "  border: 1px solid #dcdfe6;"
            "  border-radius: 4px;"
            "}"
        )
        self._dim_lbl.setParent(self)
        self._dim_lbl.raise_()
        self._dim_lbl.move(12, 12)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._dim_lbl.move(12, 12)

    def set_root_space(self, space: Space) -> None:
        """绑定根空间并刷新 GL 与尺寸文案。"""
        self._root = space
        w, h, d = space.width, space.height, space.depth
        self._dim_lbl.setText(
            f"{space.name or 'Root'}   {w:.0f} × {h:.0f} × {d:.0f}  mm"
        )
        self._dim_lbl.adjustSize()

        if self._scene is not None and self._gl is not None:
            self._scene.clear()
            self._scene.add_space(space)
            self._frame_camera(space)

    def clear_scene(self) -> None:
        if self._scene is not None:
            self._scene.clear()
        self._root = None
        self._dim_lbl.setText("")

    def _frame_camera(self, space: Space) -> None:
        if not _HAS_PG or self._gl is None:
            return
        x, y, z = space.x, space.y, space.z
        w, h, d = space.width, space.height, space.depth
        cx = x + w * 0.5
        cy = y + h * 0.5
        cz = z + d * 0.5
        self._gl.opts["center"] = pg.Vector(cx, cy, cz)
        span = max(float(w), float(h), float(d), 1.0)
        dist = span * 2.4
        self._gl.opts["distance"] = dist
        # 类建筑透视：略低仰角 + 斜视
        elev = 22.0
        azim = 42.0
        self._gl.setCameraPosition(distance=dist, elevation=elev, azimuth=azim)


def make_root_cabinet_space(
    name: str, width: float, height: float, depth: float
) -> Space:
    """由新建柜子对话框尺寸生成根逻辑空间（纯数据）。"""
    return Space(
        name=name or "Root Cabinet",
        space_type=SpaceType.ROOT,
        x=0.0,
        y=0.0,
        z=0.0,
        width=float(width),
        height=float(height),
        depth=float(depth),
    )
