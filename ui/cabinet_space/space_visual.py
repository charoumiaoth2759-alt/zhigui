# -*- coding: utf-8 -*-
"""Space 的可视化表现：仅依赖 Space 几何，不包含业务规则。"""

from __future__ import annotations

import numpy as np

from core.space.models import Space

try:
    from pyqtgraph.opengl import GLMeshItem, GLLinePlotItem
    from pyqtgraph.opengl.MeshData import MeshData

    _HAS_PG = True
except ImportError:  # pragma: no cover
    GLMeshItem = GLLinePlotItem = MeshData = None  # type: ignore
    _HAS_PG = False


def _box_vertices_faces(
    x: float, y: float, z: float, w: float, h: float, d: float
) -> tuple[np.ndarray, np.ndarray]:
    """轴对齐盒：Y 为高度（与 View3D 挤出方向一致），返回 (8,3) 顶点与 (12,3) 三角形索引。"""
    v = np.array(
        [
            [x, y, z],
            [x + w, y, z],
            [x + w, y, z + d],
            [x, y, z + d],
            [x, y + h, z],
            [x + w, y + h, z],
            [x + w, y + h, z + d],
            [x, y + h, z + d],
        ],
        dtype=np.float32,
    )
    # 12 三角形，外法线朝外
    f = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],  # 底 y
            [4, 5, 6],
            [4, 6, 7],  # 顶 y+h
            [0, 1, 5],
            [0, 5, 4],  # 前 z
            [2, 3, 7],
            [2, 7, 6],  # 后 z+d
            [0, 4, 7],
            [0, 7, 3],  # 左 x
            [1, 2, 6],
            [1, 6, 5],  # 右 x+w
        ],
        dtype=np.uint32,
    )
    return v, f


def _box_edge_segments(
    x: float, y: float, z: float, w: float, h: float, d: float
) -> np.ndarray:
    """12 条棱，每段两个点 → (24, 3)。"""
    v = _box_vertices_faces(x, y, z, w, h, d)[0]
    pairs = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    pts = []
    for a, b in pairs:
        pts.append(v[a])
        pts.append(v[b])
    return np.array(pts, dtype=np.float32)


class SpaceVisual:
    """将单个 `Space` 转为 pyqtgraph GLMeshItem + GLLinePlotItem（非数据源）。"""

    # 与 View3D 逻辑空间盒一致：QColor(135,240,240,153) 约 60% 透明；棱线 QColor(0,255,255)
    _FACE_RGBA = (135 / 255.0, 240 / 255.0, 240 / 255.0, 153 / 255.0)
    _EDGE_RGBA = (0.0, 1.0, 1.0, 1.0)

    def __init__(self, space: Space):
        self.space = space
        self._mesh: object | None = None
        self._edges: object | None = None

    def attach(self, gl_view) -> None:
        if not _HAS_PG:
            return
        x, y, z = self.space.x, self.space.y, self.space.z
        w, h, d = self.space.width, self.space.height, self.space.depth
        verts, faces = _box_vertices_faces(x, y, z, w, h, d)
        md = MeshData(vertexes=verts, faces=faces)
        self._mesh = GLMeshItem(
            meshdata=md,
            smooth=False,
            drawFaces=True,
            drawEdges=False,
            shader="shaded",
            color=self._FACE_RGBA,
        )
        edge_pos = _box_edge_segments(x, y, z, w, h, d)
        self._edges = GLLinePlotItem(
            pos=edge_pos,
            color=self._EDGE_RGBA,
            width=1.0,
            mode="lines",
        )
        gl_view.addItem(self._mesh)
        gl_view.addItem(self._edges)

    def detach(self, gl_view) -> None:
        if self._mesh is not None:
            try:
                gl_view.removeItem(self._mesh)
            except Exception:
                pass
            self._mesh = None
        if self._edges is not None:
            try:
                gl_view.removeItem(self._edges)
            except Exception:
                pass
            self._edges = None


def is_pyqtgraph_gl_available() -> bool:
    return _HAS_PG
