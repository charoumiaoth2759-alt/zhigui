# -*- coding: utf-8 -*-
"""
预览网格缓存 — 悬停时禁止 ``new mesh`` / ``rebuild mesh``。

仅 ``show()`` / ``hide()`` / ``update_transform``（平移 + 缩放）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .preview_spec import PreviewGhostMesh

# 单位轴对齐盒 (0,0,0)–(1,1,1)，与 ``PreviewGhostMesh`` 拓扑一致
_UNIT_CORNERS: tuple[tuple[float, float, float], ...] = (
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (1.0, 0.0, 1.0),
    (0.0, 0.0, 1.0),
    (0.0, 1.0, 0.0),
    (1.0, 1.0, 0.0),
    (1.0, 1.0, 1.0),
    (0.0, 1.0, 1.0),
)
_UNIT_TRIANGLES: tuple[tuple[int, int, int], ...] = (
    (0, 2, 1),
    (0, 3, 2),
    (4, 5, 6),
    (4, 6, 7),
    (0, 1, 5),
    (0, 5, 4),
    (2, 3, 7),
    (2, 7, 6),
    (0, 4, 7),
    (0, 7, 3),
    (1, 2, 6),
    (1, 6, 5),
)
from ui.theme_constants import PREVIEW_COLOR


@dataclass
class PreviewTransform:
    """世界 mm：原点 + 三轴长度。"""

    x0: float = 0.0
    y0: float = 0.0
    z0: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    sz: float = 1.0
    rgba: tuple[float, float, float, float] = PREVIEW_COLOR


class PreviewMeshCache:
    """
    单块预览 mesh 缓存（ParamSpace ``GLMeshItem`` + 主 View3D 单位盒绘制）。

    几何拓扑只构建一次；悬停仅改变换与可见性。
    """

    def __init__(self) -> None:
        self._visible = False
        self._transform = PreviewTransform()
        self._pg_item: Any = None
        self._pg_gl_parent: Any = None
        self._mesh_template: PreviewGhostMesh = PreviewGhostMesh(
            corners=_UNIT_CORNERS,
            triangles=_UNIT_TRIANGLES,
            rgba=PREVIEW_COLOR,
        )

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def transform(self) -> PreviewTransform:
        return self._transform

    @property
    def mesh_template(self) -> PreviewGhostMesh:
        """主 View3D 绘制用（单位盒 + 外部矩阵变换）。"""
        return PreviewGhostMesh(
            corners=_UNIT_CORNERS,
            triangles=_UNIT_TRIANGLES,
            rgba=self._transform.rgba,
        )

    def update_transform(
        self,
        *,
        x0: float,
        y0: float,
        z0: float,
        sx: float,
        sy: float,
        sz: float,
        rgba: tuple[float, float, float, float] | None = None,
    ) -> None:
        self._transform = PreviewTransform(
            x0=float(x0),
            y0=float(y0),
            z0=float(z0),
            sx=max(float(sx), 0.01),
            sy=max(float(sy), 0.01),
            sz=max(float(sz), 0.01),
            rgba=rgba or PREVIEW_COLOR,
        )
        if self._pg_item is not None:
            self._apply_pg_transform()

    def update_from_ghost_mesh(self, mesh: PreviewGhostMesh | None) -> bool:
        """由 ``PreviewGhostMesh`` 推导平移/缩放（不重建拓扑）。"""
        if mesh is None or len(mesh.corners) < 8:
            return False
        c = mesh.corners
        x0 = min(p[0] for p in c)
        y0 = min(p[1] for p in c)
        z0 = min(p[2] for p in c)
        x1 = max(p[0] for p in c)
        y1 = max(p[1] for p in c)
        z1 = max(p[2] for p in c)
        self.update_transform(
            x0=x0,
            y0=y0,
            z0=z0,
            sx=x1 - x0,
            sy=y1 - y0,
            sz=z1 - z0,
            rgba=PREVIEW_COLOR,
        )
        return True

    def show(self, gl_parent: Any | None = None) -> None:
        self._visible = True
        if gl_parent is not None and self._is_pg_gl(gl_parent):
            self._ensure_pg_item(gl_parent)
        if self._pg_item is not None:
            try:
                self._pg_item.setVisible(True)
            except Exception:
                pass

    def hide(self) -> None:
        self._visible = False
        if self._pg_item is not None:
            try:
                self._pg_item.setVisible(False)
            except Exception:
                pass

    def detach_pg(self, gl_parent: Any | None = None) -> None:
        """离开 GL 视图时卸下 item（不销毁单位 mesh 数据）。"""
        self.hide()
        parent = gl_parent or self._pg_gl_parent
        if self._pg_item is not None and parent is not None:
            try:
                parent.removeItem(self._pg_item)
            except Exception:
                pass
        self._pg_item = None
        self._pg_gl_parent = None

    def _is_pg_gl(self, gl: Any) -> bool:
        return gl is not None and hasattr(gl, "addItem") and not hasattr(gl, "GL_TRIANGLES")

    def _ensure_pg_item(self, gl: Any) -> None:
        if self._pg_item is not None and self._pg_gl_parent is gl:
            self._apply_pg_transform()
            return
        if self._pg_item is not None and self._pg_gl_parent is not None:
            try:
                self._pg_gl_parent.removeItem(self._pg_item)
            except Exception:
                pass
            self._pg_item = None
        try:
            from pyqtgraph.opengl import GLMeshItem
            from pyqtgraph.opengl.MeshData import MeshData
            import numpy as np
        except ImportError:
            return
        verts = np.array(_UNIT_CORNERS, dtype=np.float32)
        faces = np.array(_UNIT_TRIANGLES, dtype=np.uint32)
        md = MeshData(vertexes=verts, faces=faces)
        r, g, b, a = self._transform.rgba
        item = GLMeshItem(
            meshdata=md,
            smooth=False,
            drawFaces=True,
            drawEdges=False,
            shader="shaded",
            color=(r, g, b, a),
        )
        try:
            item.setGLOptions("translucent")
        except Exception:
            pass
        gl.addItem(item)
        self._pg_item = item
        self._pg_gl_parent = gl
        self._apply_pg_transform()
        if self._visible:
            try:
                item.setVisible(True)
            except Exception:
                pass
        else:
            try:
                item.setVisible(False)
            except Exception:
                pass

    def _apply_pg_transform(self) -> None:
        item = self._pg_item
        if item is None:
            return
        t = self._transform
        try:
            item.resetTransform()
            item.translate(t.x0, t.y0, t.z0)
            item.scale(t.sx, t.sy, t.sz)
        except Exception:
            pass
        try:
            r, g, b, a = t.rgba
            item.setColor((r, g, b, a))
        except Exception:
            pass


_preview_mesh_cache = PreviewMeshCache()


def get_preview_mesh_cache() -> PreviewMeshCache:
    return _preview_mesh_cache


__all__ = [
    "PreviewMeshCache",
    "PreviewTransform",
    "get_preview_mesh_cache",
]
