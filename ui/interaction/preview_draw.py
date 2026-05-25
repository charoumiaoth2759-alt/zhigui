# -*- coding: utf-8 -*-
"""将 ``PreviewGhostMesh`` 绘制到主 ``View3D`` OpenGL（无板件侧面硬编码）。"""

from __future__ import annotations

from typing import Any

from .preview_spec import PreviewGhostMesh


def draw_preview_ghost_mesh_gl(gl_module: Any, mesh: PreviewGhostMesh) -> None:
    """在已设置模型视图矩阵的 GL 上下文中绘制半透明预览盒。"""
    GL = gl_module
    corners = mesh.corners
    tris = mesh.triangles
    r, g, b, a = mesh.rgba

    GL.glDisable(GL.GL_CULL_FACE)
    GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
    GL.glPolygonOffset(1.0, 1.0)
    GL.glDepthMask(GL.GL_FALSE)
    GL.glColor4f(r, g, b, a)
    GL.glBegin(GL.GL_TRIANGLES)
    for ia, ib, ic in tris:
        for i in (ia, ib, ic):
            GL.glVertex3f(*corners[i])
    GL.glEnd()
    GL.glDepthMask(GL.GL_TRUE)
    GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
    GL.glEnable(GL.GL_CULL_FACE)


def draw_preview_mesh_cache_gl(gl_module: Any, cache: Any) -> None:
    """
    使用缓存单位盒 + 仅变换绘制（禁止 hover 时 new/rebuild mesh）。

    ``cache`` 为 ``PreviewMeshCache``，须 ``visible`` 且已 ``update_transform``。
    """
    if not getattr(cache, "visible", False):
        return
    t = cache.transform
    mesh = cache.mesh_template
    GL = gl_module
    tris = mesh.triangles
    r, g, b, a = t.rgba

    GL.glDisable(GL.GL_CULL_FACE)
    GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
    GL.glPolygonOffset(1.0, 1.0)
    GL.glDepthMask(GL.GL_FALSE)
    GL.glColor4f(r, g, b, a)
    GL.glPushMatrix()
    try:
        GL.glTranslatef(t.x0, t.y0, t.z0)
        GL.glScalef(t.sx, t.sy, t.sz)
        GL.glBegin(GL.GL_TRIANGLES)
        for ia, ib, ic in tris:
            for i in (ia, ib, ic):
                c = mesh.corners[i]
                GL.glVertex3f(c[0], c[1], c[2])
        GL.glEnd()
    finally:
        GL.glPopMatrix()
    GL.glDepthMask(GL.GL_TRUE)
    GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
    GL.glEnable(GL.GL_CULL_FACE)


__all__ = ["draw_preview_ghost_mesh_gl", "draw_preview_mesh_cache_gl"]
