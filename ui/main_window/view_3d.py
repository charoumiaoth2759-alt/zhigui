# -*- coding: utf-8 -*-
"""3D 画柜子视图模块

View3D —— 基于 QOpenGLWidget 的 3D 渲染视图，用于"画柜子"模式。

功能：
    - OpenGL：画布内默认 **天顶浅蓝→下白** 竖直渐变；室外地面 **径向渐变**（浅蓝白→浅灰蓝）+
      **蓝灰透视网格**（线段两端颜色插值呈渐变）；雾为淡蓝白且较弱，避免画面发白、网格消失
    - 接收 2D 户型 Room：墙体在 XZ 平面，沿 Y 挤出默认 2800 mm，线框显示房间
    - 鼠标左键拖拽：轨道旋转（Orbit）
    - 鼠标右键拖拽 / 中键拖拽：平移（Pan）
    - 滚轮：推进缩放（Dolly）
    - 坐标轴指示器（左下角 X/Y/Z 彩色轴线 + 箭头，随相机旋转）

用法：
    from ui.main_window.view_3d import View3D

    view = View3D(parent=self)
"""

import math
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QVector3D, QMatrix4x4, QOpenGLContext,
    QPalette, QPolygonF, QLinearGradient, QImage,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from space_engine.room import Room

# ── 尝试导入 OpenGL；若环境不支持则降级为 QPainter 软渲染占位 ────────
try:
    from OpenGL import GL
    _HAS_OPENGL = True
except ImportError:
    _HAS_OPENGL = False


def _diban_image_path() -> Path:
    """与主程序同级的 icons/diban.jpg（scene 单位 mm，2D/3D 地板共用）。"""
    return Path(__file__).resolve().parents[2] / "icons" / "diban.jpg"


# ================================================================ View3D
class View3D(QOpenGLWidget if _HAS_OPENGL else QWidget):
    """3D 柜体设计视图。

    运行时自动检测 OpenGL 可用性：
        - 可用：走 QOpenGLWidget 路径，用 GL 绘制网格与柜体线框。
        - 不可用：降级为 QPainter 软渲染，绘制透视示意图占位。
    """

    # ── 相机变化信号：(azimuth, elevation) 度 ─────────────────────────
    sig_camera_changed = Signal(float, float)

    # ── 软渲染背景（与 GL 渐变天空底部一致）──────────────────────────
    BG_COLOR = QColor("#ffffff")

    # ── 网格参数 ──────────────────────────────────────────────────
    GRID_COUNT  = 20          # 单侧格数（总 2×GRID_COUNT）
    GRID_STEP   = 100.0       # 每格 100mm
    GRID_COLOR  = (0.88, 0.88, 0.88, 1.0)
    AXIS_X_COLOR = (0.92, 0.18, 0.18)
    AXIS_Y_COLOR = (0.18, 0.78, 0.28)
    AXIS_Z_COLOR = (0.20, 0.42, 0.92)

    # ── 房间颜色 ─────────────────────────────────────────
    WALL_COLOR = (0.86, 0.86, 0.86, 1.0)
    FLOOR_COLOR = (0.82, 0.76, 0.68, 1.0)
    CEILING_COLOR = (0.92, 0.92, 0.92, 1.0)

    # ── 摄像机默认参数（低仰角 + 略宽 FOV，贴近建筑可视化参考图）──────────
    _DEFAULT_AZIMUTH   =   0.0     # 水平角（度），正对「景深」
    _DEFAULT_ELEVATION =  14.0     # 仰角（度），略低以强调地面透视
    _DEFAULT_DISTANCE  = 2500.0   # 距目标点距离（mm）
    _DEFAULT_TARGET    = QVector3D(0, 360, 0)  # 看向柜体中心

    # 2D 户型 (x,z) 映射到世界 XZ，Y 为高度；与画户型 scene 坐标一致
    DEFAULT_EXTRUDE_HEIGHT = 2800.0

    # 左上角「空间尺寸」提示：与左缘距离，避免与顶部 2D/3D 悬浮导航条重叠
    _CABINET_SPACE_HINT_X = 228

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 2D 同步：户型墙体挤出 ───────────────────────────────────
        self._room: Room | None = None
        self._extrude_height = self.DEFAULT_EXTRUDE_HEIGHT

        # ── 摄像机状态 ────────────────────────────────────────────
        self._azimuth   = self._DEFAULT_AZIMUTH
        self._elevation = self._DEFAULT_ELEVATION
        self._distance  = self._DEFAULT_DISTANCE
        self._target    = QVector3D(self._DEFAULT_TARGET)

        # ── 鼠标拖拽状态 ──────────────────────────────────────────
        self._last_pos: QPoint | None = None
        self._drag_mode: str = "none"   # "orbit" | "pan"
        self._floor_tex_id: int = 0     # OpenGL 地板纹理（diban.jpg），initializeGL 中加载

        # 柜体「逻辑空间」根盒（与画柜子主 3D 同一套背景/地面/网格，仅多画此盒）
        self._cabinet_space = None

        if not _HAS_OPENGL:
            # 软渲染模式：接受 QPainter 绘制
            self.setAutoFillBackground(True)
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.Window, self.BG_COLOR)
            self.setPalette(pal)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_room(self, room: Room | None, extrude_height: float | None = None) -> None:
        """绑定画户型中的房间数据；进入 3D 时调用以刷新挤出线框。

        Args:
            room: 与 2D 画布共用的 Room（含 StraightWall 列表）
            extrude_height: 层高 / 挤出高度（mm），默认 2800
        """
        self._room = room
        if extrude_height is not None:
            self._extrude_height = float(extrude_height)
        self._fit_camera_to_room()
        self.update()

    def _fit_camera_to_room(self) -> None:
        """根据墙体包围盒调整观察目标与距离（有墙时）。"""
        room = self._room
        if not room or not room.walls:
            return
        H = float(self._extrude_height)
        xs: list[float] = []
        zs: list[float] = []
        for w in room.walls:
            for px, pz in w.wall_polygon_points():
                xs.append(float(px))
                zs.append(float(pz))
        if not xs:
            return
        minx, maxx = min(xs), max(xs)
        minz, maxz = min(zs), max(zs)
        cx = (minx + maxx) * 0.5
        cz = (minz + maxz) * 0.5
        cy = H * 0.5
        span_x = max(maxx - minx, 500.0)
        span_z = max(maxz - minz, 500.0)
        span = max(span_x, span_z, H, 800.0)
        self._target = QVector3D(cx, cy, cz)
        self._distance = max(span * 1.35, 1500.0)

    def set_cabinet_space(self, space) -> None:
        """绑定柜体逻辑空间根盒（Space 或 None）；与主界面「画柜子」3D 共用本视图背景。"""
        self._cabinet_space = space
        if space is not None:
            self._fit_camera_to_cabinet_space()
        self.sig_camera_changed.emit(self._azimuth, self._elevation)
        self.update()

    def _fit_camera_to_cabinet_space(self) -> None:
        s = self._cabinet_space
        if s is None:
            return
        cx = float(s.x) + float(s.width) * 0.5
        cy = float(s.y) + float(s.height) * 0.5
        cz = float(s.z) + float(s.depth) * 0.5
        span = max(float(s.width), float(s.height), float(s.depth), 1.0)
        self._target = QVector3D(cx, cy, cz)
        self._distance = max(span * 2.2, 1500.0)
        self._azimuth = self._DEFAULT_AZIMUTH
        self._elevation = self._DEFAULT_ELEVATION

    # ================================================================ OpenGL 路径
    if _HAS_OPENGL:

        def initializeGL(self):
            GL.glClearColor(0.86, 0.93, 0.99, 1.0)
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glShadeModel(GL.GL_SMOOTH)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            # 淡蓝白雾：与天空底部衔接，强度较弱以免把渐变网格冲成一片白
            GL.glEnable(GL.GL_FOG)
            GL.glFogfv(GL.GL_FOG_COLOR, [0.93, 0.96, 1.0, 1.0])
            GL.glFogf(GL.GL_FOG_MODE, GL.GL_LINEAR)
            GL.glFogf(GL.GL_FOG_START, 14_000.0)
            GL.glFogf(GL.GL_FOG_END, 480_000.0)
            GL.glHint(GL.GL_FOG_HINT, GL.GL_NICEST)
            # 开启背面剔除：顺时针为背面，逆时针为正面（从室内看）
            GL.glEnable(GL.GL_CULL_FACE)
            GL.glCullFace(GL.GL_BACK)
            GL.glFrontFace(GL.GL_CCW)
            self._reload_floor_texture_gl()

        def _reload_floor_texture_gl(self) -> None:
            """从 icons/diban.jpg 上传 2D 纹理；失败则保持无纹理（房间地板走纯色）。"""
            if self._floor_tex_id:
                GL.glDeleteTextures([int(self._floor_tex_id)])
                self._floor_tex_id = 0
            path = _diban_image_path()
            if not path.is_file():
                return
            img = QImage(str(path))
            if img.isNull():
                return
            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()
            if w < 1 or h < 1:
                return
            raw = bytes(memoryview(img.constBits())[: img.sizeInBytes()])
            tid_ar = GL.glGenTextures(1)
            tid = int(tid_ar[0]) if isinstance(tid_ar, (list, tuple)) else int(tid_ar)
            self._floor_tex_id = tid
            GL.glBindTexture(GL.GL_TEXTURE_2D, tid)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
                w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, raw,
            )
            gen = getattr(GL, "glGenerateMipmap", None)
            if gen is not None:
                try:
                    gen(GL.GL_TEXTURE_2D)
                    GL.glTexParameteri(
                        GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR,
                    )
                except Exception:
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        def resizeGL(self, w: int, h: int):
            GL.glViewport(0, 0, w, max(h, 1))

        def paintGL(self):
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            w, h = self.width(), self.height()

            # ── 先用 QPainter 画渐变背景（天空 + 室外地面网格）──────
            self._draw_background_painter()

            # ── 投影矩阵 ──────────────────────────────────────────
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            aspect = w / max(h, 1)
            fov    = 58.0
            near   = 3.0
            far    = 800_000.0
            f = 1.0 / math.tan(math.radians(fov / 2))
            proj = [
                f / aspect, 0,  0,                               0,
                0,          f,  0,                               0,
                0,          0,  (far + near) / (near - far),    -1,
                0,          0,  (2 * far * near) / (near - far), 0,
            ]
            GL.glLoadMatrixf(proj)

            # ── 视图矩阵（轨道摄像机）────────────────────────────
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glLoadIdentity()
            eye = self._eye_pos()
            tx, ty, tz = (self._target.x(), self._target.y(), self._target.z())
            ex, ey, ez = eye
            self._gl_lookat(ex, ey, ez, tx, ty, tz, 0, 1, 0)

            # ── 室外：渐变地面 + 白色透视网格 ───────────────────────
            self._draw_outdoor_ground_and_grid_gl()

            # ── 世界坐标轴（原点处 X/Y/Z 彩色粗线，与网格区分）────
            self._draw_world_axes_gl()

            # ── 房间实体（背面剔除自动隐藏前墙）─────────────────
            self._draw_room_solid_gl()

            # ── 柜体逻辑空间根盒（浅青填充 + 纯青棱线）──
            self._draw_cabinet_space_gl()

            # ── 左下角坐标轴 HUD ──────────────────────────────────
            self._draw_overlay_painter()

        def _draw_background_painter(self):
            """画布内天顶明显浅蓝 → 下方渐变为白的竖直线性渐变（默认 3D 天空）。"""
            painter = QPainter(self)
            w, h = self.width(), self.height()
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(120, 188, 238))    # 天顶：清晰浅蓝
            grad.setColorAt(0.22, QColor(160, 210, 246))
            grad.setColorAt(0.45, QColor(198, 230, 252))
            grad.setColorAt(0.68, QColor(228, 244, 255))
            grad.setColorAt(0.88, QColor(248, 252, 255))
            grad.setColorAt(1.0, QColor(255, 255, 255))  # 地平线一带：白
            painter.fillRect(0, 0, w, h, grad)
            painter.end()
            # 重新激活 GL 上下文（QPainter 会暂时释放它）
            self.makeCurrent()
            GL.glClear(GL.GL_DEPTH_BUFFER_BIT)

        def _outdoor_plane_bounds(self) -> tuple[float, float, float, float, float, float, float]:
            """返回 (cx, cz, half, gx0, gx1, gz0, gz1) 室外大地面范围。"""
            room = getattr(self, "_room", None)
            if room and room.walls:
                xs = [float(px) for w in room.walls for px, _ in w.wall_polygon_points()]
                zs = [float(pz) for w in room.walls for _, pz in w.wall_polygon_points()]
                cx = (min(xs) + max(xs)) * 0.5
                cz = (min(zs) + max(zs)) * 0.5
                half = max(max(xs) - min(xs), max(zs) - min(zs)) * 0.5 + 80000.0
            else:
                cx, cz, half = 0.0, 0.0, 50000.0
            gx0 = cx - half
            gx1 = cx + half
            gz0 = cz - half
            gz1 = cz + half
            return cx, cz, half, gx0, gx1, gz0, gz1

        def _draw_outdoor_ground_and_grid_gl(self) -> None:
            """室外地面：中心浅蓝白 → 四周浅灰蓝的径向渐变片；网格线为蓝灰渐变（沿线插值），透视可见。"""
            cx, cz, half, gx0, gx1, gz0, gz1 = self._outdoor_plane_bounds()
            ex, ey, ez = self._eye_pos()
            dists: list[float] = []
            for vx, vz in ((gx0, gz0), (gx0, gz1), (gx1, gz0), (gx1, gz1)):
                dx, dy, dz = vx - ex, -ey, vz - ez
                dists.append(math.sqrt(dx * dx + dy * dy + dz * dz))
            dx, dy, dz = cx - ex, -ey, cz - ez
            dists.append(math.sqrt(dx * dx + dy * dy + dz * dz))
            d_min = min(dists)
            d_max = max(dists)
            d_span = max(d_max - d_min, 800.0)

            def _cam_t(vx: float, vz: float) -> float:
                dx, dy, dz = vx - ex, -ey, vz - ez
                d = math.sqrt(dx * dx + dy * dy + dz * dz)
                return max(0.0, min(1.0, (d - d_min) / d_span))

            def _radial_t(vx: float, vz: float) -> float:
                """相对 (cx,cz) 归一化距离，用于中心白、四周灰。"""
                span = max(half * 1.41421356, 1.0)
                t = math.hypot(vx - cx, vz - cz) / span
                return max(0.0, min(1.0, t))

            def _smooth01(t: float) -> float:
                t = max(0.0, min(1.0, t))
                return t * t * (3.0 - 2.0 * t)

            def _ground_vertex_color(vx: float, vz: float) -> None:
                t = _smooth01(_radial_t(vx, vz))
                # 中心：浅蓝白；边缘：略冷的浅灰蓝（对比足够，网格线才看得见）
                r0, g0, b0 = 0.94, 0.97, 1.0
                r1, g1, b1 = 0.80, 0.86, 0.93
                r = r0 * (1.0 - t) + r1 * t
                g = g0 * (1.0 - t) + g1 * t
                b = b0 * (1.0 - t) + b1 * t
                GL.glColor3f(r, g, b)

            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glDisable(GL.GL_CULL_FACE)
            gy = 0.02
            sub = 48
            GL.glShadeModel(GL.GL_SMOOTH)
            for ix in range(sub):
                fx0 = gx0 + (gx1 - gx0) * (ix / sub)
                fx1 = gx0 + (gx1 - gx0) * ((ix + 1) / sub)
                GL.glBegin(GL.GL_QUAD_STRIP)
                for jz in range(sub + 1):
                    fz = gz0 + (gz1 - gz0) * (jz / sub)
                    for fx in (fx0, fx1):
                        _ground_vertex_color(fx, fz)
                        GL.glVertex3f(fx, gy, fz)
                GL.glEnd()

            # 透视网格：每段线两端颜色不同 → 沿屏幕方向呈渐变；整体偏蓝灰、不透明度足够
            step = 200.0

            def _grid_vertex_rgba(vx: float, vz: float) -> None:
                tr = _smooth01(_radial_t(vx, vz))
                tc = _cam_t(vx, vz)
                # 近相机略亮，远处略深，与径向组合成渐变网格
                r = 0.62 + 0.18 * (1.0 - tc) + 0.12 * tr
                g = 0.74 + 0.14 * (1.0 - tc) + 0.10 * tr
                b = 0.88 + 0.08 * (1.0 - tc) + 0.04 * tr
                a = 0.52 + 0.32 * tr + 0.12 * (1.0 - tc)
                a = max(0.45, min(0.95, a))
                GL.glColor4f(r, g, b, a)

            GL.glLineWidth(1.0)
            GL.glBegin(GL.GL_LINES)
            x = gx0
            while x <= gx1 + 0.1:
                _grid_vertex_rgba(x, gz0)
                GL.glVertex3f(x, 0.04, gz0)
                _grid_vertex_rgba(x, gz1)
                GL.glVertex3f(x, 0.04, gz1)
                x += step
            z = gz0
            while z <= gz1 + 0.1:
                _grid_vertex_rgba(gx0, z)
                GL.glVertex3f(gx0, 0.04, z)
                _grid_vertex_rgba(gx1, z)
                GL.glVertex3f(gx1, 0.04, z)
                z += step
            GL.glEnd()

            # 过原点的 X/Z 地面参考线：加粗、纯色，避免与普通网格混淆
            ax_y = 0.06
            ax_span = min(max(half * 0.35, 4000.0), 80_000.0)
            GL.glLineWidth(2.8)
            GL.glBegin(GL.GL_LINES)
            GL.glColor4f(*self.AXIS_X_COLOR, 1.0)
            GL.glVertex3f(cx - ax_span, ax_y, cz)
            GL.glVertex3f(cx + ax_span, ax_y, cz)
            GL.glColor4f(*self.AXIS_Z_COLOR, 1.0)
            GL.glVertex3f(cx, ax_y, cz - ax_span)
            GL.glVertex3f(cx, ax_y, cz + ax_span)
            GL.glEnd()
            GL.glLineWidth(1.0)
            GL.glEnable(GL.GL_CULL_FACE)

        # ── GL 辅助 ───────────────────────────────────────────────
        def _eye_pos(self):
            az  = math.radians(self._azimuth)
            el  = math.radians(self._elevation)
            d   = self._distance
            x   = d * math.cos(el) * math.sin(az)
            y   = d * math.sin(el)
            z   = d * math.cos(el) * math.cos(az)
            return (
                self._target.x() + x,
                self._target.y() + y,
                self._target.z() + z,
            )

        def _gl_lookat(self, ex, ey, ez, tx, ty, tz, ux, uy, uz):
            fv = _norm3(tx - ex, ty - ey, tz - ez)
            rv = _norm3(
                fv[1]*uz - fv[2]*uy,
                fv[2]*ux - fv[0]*uz,
                fv[0]*uy - fv[1]*ux,
            )
            uv = (
                rv[1]*fv[2] - rv[2]*fv[1],
                rv[2]*fv[0] - rv[0]*fv[2],
                rv[0]*fv[1] - rv[1]*fv[0],
            )
            m = [
                rv[0], uv[0], -fv[0], 0,
                rv[1], uv[1], -fv[1], 0,
                rv[2], uv[2], -fv[2], 0,
                -(rv[0]*ex + rv[1]*ey + rv[2]*ez),
                -(uv[0]*ex + uv[1]*ey + uv[2]*ez),
                 (fv[0]*ex + fv[1]*ey + fv[2]*ez),
                1,
            ]
            GL.glLoadMatrixf(m)

        def _draw_world_axes_gl(self) -> None:
            """在观察目标附近绘制 X/Y/Z 世界坐标轴（粗线、高饱和，便于与淡色网格区分）。"""
            ox = float(self._target.x())
            oy = 0.0
            oz = float(self._target.z())
            span_h = max(
                float(self._distance) * 0.45,
                self.GRID_STEP * 10.0,
                1200.0,
            )
            span_h = min(span_h, 15_000.0)
            span_v = max(
                float(self._extrude_height) * 1.05,
                span_h * 0.35,
                800.0,
            )
            span_v = min(span_v, 12_000.0)

            GL.glDisable(GL.GL_CULL_FACE)
            GL.glDisable(GL.GL_BLEND)
            GL.glLineWidth(4.0)
            GL.glBegin(GL.GL_LINES)
            GL.glColor3f(*self.AXIS_X_COLOR)
            GL.glVertex3f(ox - span_h, oy, oz)
            GL.glVertex3f(ox + span_h, oy, oz)
            GL.glColor3f(*self.AXIS_Y_COLOR)
            GL.glVertex3f(ox, oy, oz)
            GL.glVertex3f(ox, oy + span_v, oz)
            GL.glColor3f(*self.AXIS_Z_COLOR)
            GL.glVertex3f(ox, oy, oz - span_h)
            GL.glVertex3f(ox, oy, oz + span_h)
            GL.glEnd()
            GL.glLineWidth(1.0)
            GL.glEnable(GL.GL_BLEND)

        def _draw_room_walls_gl(self):
            """仅线框绘制墙体轮廓（底边 / 顶边 / 竖边）。"""
            room = getattr(self, "_room", None)
            if room is None or not room.walls:
                return
            H = float(self._extrude_height)
            GL.glColor3f(0.72, 0.72, 0.72)
            GL.glLineWidth(1.0)
            GL.glBegin(GL.GL_LINES)
            for w in room.walls:
                poly = w.wall_polygon_points()
                if len(poly) < 4:
                    continue
                bottom = [(float(px), 0.0, float(pz)) for px, pz in poly]
                top = [(float(px), H, float(pz)) for px, pz in poly]
                for i in range(4):
                    b0 = bottom[i]
                    b1 = bottom[(i + 1) % 4]
                    GL.glVertex3f(*b0)
                    GL.glVertex3f(*b1)
                for i in range(4):
                    t0 = top[i]
                    t1 = top[(i + 1) % 4]
                    GL.glVertex3f(*t0)
                    GL.glVertex3f(*t1)
                for i in range(4):
                    b0 = bottom[i]
                    t0 = top[i]
                    GL.glVertex3f(*b0)
                    GL.glVertex3f(*t0)
            GL.glEnd()

        def _draw_room_solid_gl(self):
            """按真实墙体轮廓挤出实体房间：地板（icons/diban.jpg 贴图）+ 墙面（背面剔除隐藏前墙）。

            顶点绕序规则：
              - 从室内向外看，每个面的顶点为 **顺时针（CW）**，对应 GL_BACK；
                glCullFace(GL_BACK) 会剔除从室外（摄像机）能看到的面——
                即：朝向摄像机的墙面（前墙外表面）自动隐藏。
              - 室内面（后墙、左右墙内表面）正好是 CCW，正常可见。
            """
            room = getattr(self, "_room", None)
            if room is None or not room.walls:
                return

            H = float(self._extrude_height)

            # ── 墙体多边形包围盒（含墙厚，用于墙面渲染）
            poly_xs: list[float] = []
            poly_zs: list[float] = []
            for w in room.walls:
                for px, pz in w.wall_polygon_points():
                    poly_xs.append(float(px))
                    poly_zs.append(float(pz))
            if not poly_xs:
                return
            minx, maxx = min(poly_xs), max(poly_xs)
            minz, maxz = min(poly_zs), max(poly_zs)

            # ── 地板范围：完全用多边形包围盒（含墙厚），
            # 这样地板铺到外墙面，前墙隐藏后地板自然延伸出来
            floor_minx, floor_maxx = minx, maxx
            floor_minz, floor_maxz = minz, maxz

            # 地板和网格不受背面剔除影响，临时关闭
            GL.glDisable(GL.GL_CULL_FACE)

            # ─────────────────────────────────────────────────────
            # 1. 地板 —— diban.jpg 平铺；无纹理时退化为亮白
            # ─────────────────────────────────────────────────────
            floor_y = 0.5

            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(-1.0, -1.0)

            fw = max(floor_maxx - floor_minx, 1.0)
            fh = max(floor_maxz - floor_minz, 1.0)
            tile = 900.0
            u1, v1 = fw / tile, fh / tile

            if self._floor_tex_id:
                GL.glEnable(GL.GL_TEXTURE_2D)
                GL.glBindTexture(GL.GL_TEXTURE_2D, int(self._floor_tex_id))
                GL.glTexEnvi(GL.GL_TEXTURE_ENV, GL.GL_TEXTURE_ENV_MODE, GL.GL_MODULATE)
                GL.glColor3f(1.0, 1.0, 1.0)
                GL.glBegin(GL.GL_QUADS)
                GL.glTexCoord2f(0.0, 0.0)
                GL.glVertex3f(floor_minx, floor_y, floor_minz)
                GL.glTexCoord2f(u1, 0.0)
                GL.glVertex3f(floor_maxx, floor_y, floor_minz)
                GL.glTexCoord2f(u1, v1)
                GL.glVertex3f(floor_maxx, floor_y, floor_maxz)
                GL.glTexCoord2f(0.0, v1)
                GL.glVertex3f(floor_minx, floor_y, floor_maxz)
                GL.glEnd()
                GL.glDisable(GL.GL_TEXTURE_2D)
            else:
                GL.glColor3f(0.97, 0.98, 0.99)
                GL.glBegin(GL.GL_QUADS)
                GL.glVertex3f(floor_minx, floor_y, floor_minz)
                GL.glVertex3f(floor_maxx, floor_y, floor_minz)
                GL.glVertex3f(floor_maxx, floor_y, floor_maxz)
                GL.glVertex3f(floor_minx, floor_y, floor_maxz)
                GL.glEnd()

            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

            BASE_H = 80.0
            BASE_C = (0.82, 0.82, 0.83)

            # ─────────────────────────────────────────────────────
            # 2. 墙体渲染 —— 基于中心线法线的整墙剔除
            #
            # 每段 StraightWall 的中心线从 (x1,y1)→(x2,y2)，
            # 内法线（朝室内）= 垂直于中心线向右旋转 90°。
            # 若内法线与"墙中心→摄像机"向量点积 > 0，
            # 说明摄像机在墙的室内侧，绘制该面墙；否则跳过（前墙）。
            # ─────────────────────────────────────────────────────
            GL.glDisable(GL.GL_CULL_FACE)

            eye_x, eye_y, eye_z = self._eye_pos()

            for w in room.walls:
                poly = w.wall_polygon_points()
                if len(poly) < 4:
                    continue

                pts_b = [(float(px), 0.0, float(pz)) for px, pz in poly]
                pts_t = [(float(px), H,   float(pz)) for px, pz in poly]

                # 墙中心线方向向量（2D: x,y → 3D: x,z）
                dx = float(w.x2) - float(w.x1)
                dz = float(w.y2) - float(w.y1)
                wL = math.hypot(dx, dz)
                if wL < 1e-6:
                    continue

                # 内法线（中心线左旋 90° = (-dz, dx) 归一化）
                in_nx = -dz / wL
                in_nz =  dx / wL

                # 墙中心点（中心线中点）
                wcx = (float(w.x1) + float(w.x2)) * 0.5
                wcz = (float(w.y1) + float(w.y2)) * 0.5

                # 摄像机相对墙中心的方向
                vx = eye_x - wcx
                vz = eye_z - wcz

                # 点积：内法线 · 视线
                # > 0 → 摄像机在室内侧 → 绘制内表面
                # ≤ 0 → 摄像机在室外侧（前墙）→ 跳过
                dot = in_nx * vx + in_nz * vz
                if dot <= 0:
                    continue

                # 直接使用原始顶点，不作任何偏移（解决墙角白色竖线问题）
                # 内表面四边形（内侧两个顶点索引 2 和 3，按顺时针从底到顶）
                b_inner = [pts_b[3], pts_b[2], pts_t[2], pts_t[3]]

                shade = 0.88 + 0.06 * in_nx - 0.03 * in_nz
                shade = max(0.82, min(1.0, shade))
                c = shade * 0.96
                GL.glColor3f(c, c, c)

                GL.glBegin(GL.GL_QUADS)
                for pt in b_inner:
                    GL.glVertex3f(*pt)
                GL.glEnd()

                # 踢脚线（使用原始顶点）
                GL.glColor3f(*BASE_C)
                ib3, ib2 = pts_b[3], pts_b[2]
                GL.glBegin(GL.GL_QUADS)
                GL.glVertex3f(*ib3)
                GL.glVertex3f(*ib2)
                GL.glVertex3f(ib2[0], BASE_H, ib2[2])
                GL.glVertex3f(ib3[0], BASE_H, ib3[2])
                GL.glEnd()

                # 端盖：始终绘制（填补相邻墙角落缺口），颜色与内墙面一致避免白色竖杠
                for ba_i, bb_i in ((0, 3), (1, 2)):
                    ba = pts_b[ba_i]
                    bb = pts_b[bb_i]
                    ta = pts_t[ba_i]
                    tb = pts_t[bb_i]
                    if math.hypot(bb[0] - ba[0], bb[2] - ba[2]) < 1e-6:
                        continue
                    GL.glColor3f(c, c, c)
                    GL.glBegin(GL.GL_QUADS)
                    GL.glVertex3f(*ba)
                    GL.glVertex3f(*bb)
                    GL.glVertex3f(*tb)
                    GL.glVertex3f(*ta)
                    GL.glEnd()

        def _draw_cabinet_space_gl(self) -> None:
            """柜体根逻辑空间：浅青填充（QColor(135,240,240,153) 约 60% 透明）+ 纯青棱线 1px。"""
            cs = getattr(self, "_cabinet_space", None)
            if cs is None:
                return
            x, y, z = float(cs.x), float(cs.y), float(cs.z)
            w, h, d = float(cs.width), float(cs.height), float(cs.depth)
            corners = [
                (x, y, z),
                (x + w, y, z),
                (x + w, y, z + d),
                (x, y, z + d),
                (x, y + h, z),
                (x + w, y + h, z),
                (x + w, y + h, z + d),
                (x, y + h, z + d),
            ]
            tris = [
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
            ]
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(1.0, 1.0)
            GL.glDepthMask(GL.GL_FALSE)
            # 填充：浅青 + alpha 153（约 60% 透明，与 50%→128 同一换算：百分比×255）
            GL.glColor4f(135 / 255.0, 240 / 255.0, 240 / 255.0, 153 / 255.0)
            GL.glBegin(GL.GL_TRIANGLES)
            for a, b, c in tris:
                for i in (a, b, c):
                    GL.glVertex3f(*corners[i])
            GL.glEnd()
            GL.glDepthMask(GL.GL_TRUE)
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

            # 边框：纯青 QColor(0,255,255)，线宽 1px
            GL.glLineWidth(1.0)
            GL.glColor3f(0.0, 1.0, 1.0)
            GL.glBegin(GL.GL_LINES)
            for a, b in (
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
            ):
                GL.glVertex3f(*corners[a])
                GL.glVertex3f(*corners[b])
            GL.glEnd()
            GL.glLineWidth(1.0)
            GL.glEnable(GL.GL_CULL_FACE)

        def _draw_overlay_painter(self):
            """用 QPainter 在 GL 画面上叠加左下角坐标轴指示器和提示文字。"""
            # 混合/深度会影响 QPainter 在 FBO 上的绘制；叠加 HUD 前复位
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glDisable(GL.GL_BLEND)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_hud(painter)
            painter.end()
            GL.glEnable(GL.GL_BLEND)
            GL.glEnable(GL.GL_DEPTH_TEST)

    # ================================================================ 软渲染路径（无 OpenGL）
    def paintEvent(self, event):
        if _HAS_OPENGL:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(120, 188, 238))
        grad.setColorAt(0.22, QColor(160, 210, 246))
        grad.setColorAt(0.45, QColor(198, 230, 252))
        grad.setColorAt(0.68, QColor(228, 244, 255))
        grad.setColorAt(0.88, QColor(248, 252, 255))
        grad.setColorAt(1.0, QColor(255, 255, 255))
        painter.fillRect(self.rect(), grad)
        self._paint_soft_3d(painter)
        self._paint_hud(painter)
        painter.end()

    def _paint_soft_3d(self, painter: QPainter):
        """无 OpenGL 时：顶视平面线框示意户型（与 GL 模式同一套 Room 数据）。"""
        room = getattr(self, "_room", None)
        if not room or not room.walls:
            painter.setPen(QPen(QColor("#909399")))
            f = painter.font()
            f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(
                self.rect().adjusted(24, 24, -24, -24),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                "暂无墙体\n在「画户型」中用直墙绘制后，切换到 3D 查看挤出房间线框",
            )
            return

        xs: list[float] = []
        zs: list[float] = []
        for w in room.walls:
            for px, pz in w.wall_polygon_points():
                xs.append(float(px))
                zs.append(float(pz))
        minx, maxx = min(xs), max(xs)
        minz, maxz = min(zs), max(zs)
        margin = 56
        rect = self.rect().adjusted(margin, margin + 28, -margin, -margin)
        span_x = max(maxx - minx, 1.0)
        span_z = max(maxz - minz, 1.0)
        scale = min(rect.width() / span_x, rect.height() / span_z)
        ox = rect.left() + (rect.width() - span_x * scale) * 0.5
        oz = rect.top() + (rect.height() - span_z * scale) * 0.5

        def tf(px: float, pz: float) -> QPointF:
            return QPointF(ox + (px - minx) * scale, oz + (pz - minz) * scale)

        painter.setPen(QPen(QColor("#5a6578"), 1.2))
        painter.setBrush(QBrush(QColor(200, 205, 215, 100)))
        for w in room.walls:
            poly_pts = w.wall_polygon_points()
            if len(poly_pts) < 3:
                continue
            poly = QPolygonF([tf(float(px), float(pz)) for px, pz in poly_pts])
            painter.drawPolygon(poly)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#606266")))
        painter.drawText(
            rect.left(),
            max(8, rect.top() - 22),
            f"顶视示意（软渲染）  挤出高度 {self._extrude_height:.0f} mm",
        )

        cs = getattr(self, "_cabinet_space", None)
        if cs is not None:
            nm = (getattr(cs, "name", "") or "").strip()
            dims = f"{float(cs.width):.0f} × {float(cs.height):.0f} × {float(cs.depth):.0f} mm"
            line = f"{nm}  {dims}" if nm else dims
            painter.setPen(QPen(QColor("#303133")))
            f2 = painter.font()
            f2.setPointSize(10)
            f2.setBold(True)
            painter.setFont(f2)
            painter.drawText(self._CABINET_SPACE_HINT_X, max(8, rect.top() - 44), line)


    def _paint_axis_gizmo(self, painter: QPainter, ox: float, oy: float) -> None:
        """左下角世界坐标轴指示器（随相机旋转；RGB 对应 X/Y/Z，带轴线与箭头）。"""
        axis_len = 52.0
        head_len = 12.0
        line_w = 4.0

        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)
        cos_az, sin_az = math.cos(az), math.sin(az)
        cos_el, sin_el = math.cos(el), math.sin(el)

        def mini_proj(dx: float, dy: float, dz: float) -> QPointF:
            rx = dx * cos_az - dz * sin_az
            rz = dx * sin_az + dz * cos_az
            ry2 = dy * cos_el - rz * sin_el
            return QPointF(ox + rx * axis_len, oy - ry2 * axis_len)

        def axis_depth(dx: float, dy: float, dz: float) -> float:
            rz = dx * sin_az + dz * cos_az
            return dy * cos_el - rz * sin_el

        axes = [
            (1.0, 0.0, 0.0, QColor("#d93030"), "X"),
            (0.0, 1.0, 0.0, QColor("#2dad52"), "Y"),
            (0.0, 0.0, 1.0, QColor("#2b6fd4"), "Z"),
        ]
        origin = QPointF(ox, oy)

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 半透明底衬，提高在浅蓝渐变背景上的对比度
        pad = 14.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 245)))
        painter.drawRoundedRect(
            QRectF(ox - pad, oy - axis_len - pad, axis_len + pad * 2, axis_len + pad * 2),
            6.0,
            6.0,
        )

        # 原点：小圆点，便于辨认三轴交点
        painter.setPen(QPen(QColor(40, 40, 40), 1.2))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(origin, 4.0, 4.0)

        label_font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(label_font)

        for dx, dy, dz, color, lbl in sorted(axes, key=lambda a: axis_depth(a[0], a[1], a[2])):
            tip = mini_proj(dx, dy, dz)
            vx = tip.x() - origin.x()
            vy = tip.y() - origin.y()
            length = math.hypot(vx, vy)
            if length < 1.0:
                continue
            ux, uy = vx / length, vy / length
            px, py = -uy, ux
            base = QPointF(tip.x() - ux * head_len, tip.y() - uy * head_len)

            # 白描边 + 彩色粗线（不透明），避免 QOpenGLWidget 上半透明填充不显示
            outline_pen = QPen(QColor(255, 255, 255), line_w + 2.6)
            outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outline_pen)
            painter.drawLine(origin, base)

            axis_pen = QPen(color, line_w)
            axis_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            axis_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(axis_pen)
            painter.drawLine(origin, base)

            head = QPolygonF([
                tip,
                QPointF(base.x() + px * 6.0, base.y() + py * 6.0),
                QPointF(base.x() - px * 6.0, base.y() - py * 6.0),
            ])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawPolygon(head)

            painter.setPen(QPen(color.darker(115), 1.0))
            painter.drawText(
                QPointF(tip.x() + ux * 6.0 - uy * 2.0, tip.y() + uy * 6.0 + ux * 2.0),
                lbl,
            )

        painter.restore()

    def _paint_hud(self, painter: QPainter):
        """绘制左下角坐标轴指示器。"""
        cs = getattr(self, "_cabinet_space", None)
        if cs is not None:
            nm = (getattr(cs, "name", "") or "").strip()
            dims = f"{float(cs.width):.0f} × {float(cs.height):.0f} × {float(cs.depth):.0f} mm"
            line = f"{nm}  {dims}" if nm else dims
            painter.setPen(QPen(QColor("#303133")))
            f = painter.font()
            f.setPointSize(11)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(self._CABINET_SPACE_HINT_X, 22, line)
        self._paint_axis_gizmo(painter, 52.0, float(self.height()) - 52.0)

    # ================================================================ 鼠标 / 键盘
    def mousePressEvent(self, event):
        self._last_pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = "orbit"
        elif event.button() in (Qt.MouseButton.RightButton,
                                 Qt.MouseButton.MiddleButton):
            self._drag_mode = "pan"
        else:
            self._drag_mode = "none"

    def mouseReleaseEvent(self, event):
        self._drag_mode = "none"
        self._last_pos  = None

    def mouseDoubleClickEvent(self, event):
        """双击：重置到默认视角。"""
        self._azimuth   = self._DEFAULT_AZIMUTH
        self._elevation = self._DEFAULT_ELEVATION
        self._distance  = self._DEFAULT_DISTANCE
        self._target    = QVector3D(self._DEFAULT_TARGET)
        self.sig_camera_changed.emit(self._azimuth, self._elevation)
        self.update()

    def mouseMoveEvent(self, event):
        if self._last_pos is None:
            return
        curr = event.position().toPoint()
        dx   = curr.x() - self._last_pos.x()
        dy   = curr.y() - self._last_pos.y()
        self._last_pos = curr

        if self._drag_mode == "orbit":
            self._azimuth   -= dx * 0.5
            self._elevation  = max(-89.0, min(89.0, self._elevation + dy * 0.5))
            self.sig_camera_changed.emit(self._azimuth, self._elevation)

        elif self._drag_mode == "pan":
            # 在水平面内平移，方向随方位角
            az = math.radians(self._azimuth)
            speed = self._distance * 0.0015
            right = QVector3D( math.cos(az), 0, -math.sin(az))
            up    = QVector3D(0, 1, 0)
            self._target -= right * (dx * speed)
            self._target += up    * (dy * speed)

        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.88 if delta > 0 else 1.0 / 0.88
        self._distance = max(3.0, min(720_000.0, self._distance * factor))
        self.update()

    def keyPressEvent(self, event):
        """R 键：重置视角。"""
        if event.key() == Qt.Key.Key_R:
            self.mouseDoubleClickEvent(None)
        else:
            super().keyPressEvent(event)


# ================================================================ 工具函数
def _norm3(x, y, z):
    length = math.sqrt(x*x + y*y + z*z)
    if length < 1e-10:
        return (0.0, 1.0, 0.0)
    return (x/length, y/length, z/length)