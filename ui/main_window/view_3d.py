# -*- coding: utf-8 -*-
"""3D 画柜子视图模块

View3D —— 基于 QOpenGLWidget 的 3D 渲染视图，用于"画柜子"模式。

功能：
    - OpenGL：画布内默认 **天顶浅蓝→下白** 竖直渐变；室外地面 **径向渐变**（浅蓝白→浅灰蓝）+
      **蓝灰透视网格**（线段两端颜色插值呈渐变）；雾为淡蓝白且较弱，避免画面发白、网格消失
    - 接收 2D 户型 Room：墙体在 XZ 平面，沿 Y 挤出默认 2800 mm，线框显示房间
    - 鼠标左键拖拽：轨道旋转（Orbit）；悬停时由 ``PreviewManager`` 按 ``FaceType``+``InteractionMode`` 绘制 ghost；
      左外侧面 **单击** / 快捷键 ``Z, Space`` 经 ``CabinetInteractionManager`` → ``UndoStack`` 提交加左侧板；    - 鼠标右键拖拽 / 中键拖拽：平移（Pan）
    - 滚轮：推进缩放（Dolly）
    - 坐标轴指示器（左下角 X/Y/Z 小箭头）

用法：
    from ui.main_window.view_3d import View3D

    view = View3D(parent=self)

调试：
    添加左侧板后 ``print(panel)`` 输出 ``Panel`` repr；主 3D 在 ``set_display_panels`` 刷新时
    对左侧板（或最后一块）打印一行 ``[View3D] draw panel`` + ``thickness height width``。
    ``paintGL`` 内不再打印，避免刷屏。
"""

import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QPoint, QPointF, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QPainter, QPen, QBrush,
    QVector3D, QMatrix4x4, QOpenGLContext,
    QPalette, QPolygonF, QLinearGradient, QImage,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from space_engine.room import Room

from core.debug_flags import DEBUG_VIEW3D
from ui.cabinet_design_host import (
    resolve_cabinet_design_view,
    resolve_cabinet_interaction_manager,
)
from ui.interaction import CabinetInteractionSource
from ui.interaction.hover_detector import VIEWPORT_MAIN_3D

from core.constants.enums import PanelOrientation, PanelRole
from core.panel.panel_face_mapper import try_get_face_by_panel_role
from core.space.enums import FaceType
from core.panel.panel_bounds import (
    panel_world_aabb as _panel_world_aabb,
    resolve_panel_orientation as _resolve_panel_orientation,
)
from core.space.enums import SpaceState as PickSpaceState
from core.space.cabinet_ops_lock import (
    cabinet_space_constraint_engine,
    pick_closest_structural_occupied_leaf_for_ray,
    read_cabinet_ops_user_allow,
    toggle_cabinet_ops_user_allow,
    unlock_closest_occ_leaf_if_locked,
)
from core.space.placement_state import BLOCKED, INVALID, NEEDS_RELAYOUT, UNPLACED, METADATA_KEY
from core.space.space_picker import HoverResult, SpacePicker
from core.space.space_placement_sync import refresh_leaf_placement_ui_metadata
from core.space.space_state import infer_space_state, read_ui_placement_for_space_display
from core.space.space_visual_mapper import space_box_face_edge_rgba
from ui.theme_constants import PANEL_COLOR, PANEL_EDGE_COLOR, panel_face_rgb

from ui.cabinet_space.tool_modes import ADD_SIDE_PANEL_TOOL_MODES, ToolMode
from ui.qt_lifecycle import safe_set_font_size

def _matrix4x4_mul_vector4(
    m: QMatrix4x4, x: float, y: float, z: float, w: float
) -> tuple[float, float, float, float]:
    """``QMatrix4x4`` × 齐次列向量。PySide6 对 ``inv * QVector4D`` 绑定不完整，用列主序显式相乘。"""
    d = m.data()
    if len(d) < 16:
        return (0.0, 0.0, 0.0, 0.0)
    rx = d[0] * x + d[4] * y + d[8] * z + d[12] * w
    ry = d[1] * x + d[5] * y + d[9] * z + d[13] * w
    rz = d[2] * x + d[6] * y + d[10] * z + d[14] * w
    rw = d[3] * x + d[7] * y + d[11] * z + d[15] * w
    return (rx, ry, rz, rw)


# ── 尝试导入 OpenGL；若环境不支持则降级为 QPainter 软渲染占位 ────────
try:
    from OpenGL import GL
    _HAS_OPENGL = True
except ImportError:
    _HAS_OPENGL = False

from core.debug_flags import DEBUG_VIEW3D


def _diban_image_path() -> Path:
    """与主程序同级的 icons/diban.jpg（scene 单位 mm，2D/3D 地板共用）。"""
    return Path(__file__).resolve().parents[2] / "icons" / "diban.jpg"


def _panel_box_vertices_xyz(
    x0: float, x1: float, y0: float, y1: float, z0: float, z1: float
) -> list[tuple[float, float, float]]:
    """
    轴对齐盒 8 顶点（仅由 AABB 最小/最大角点导出），顺序固定::

        z=min 面: (x0,y0,z0), (x1,y0,z0), (x1,y1,z0), (x0,y1,z0)
        z=max 面: (x0,y0,z1), (x1,y0,z1), (x1,y1,z1), (x0,y1,z1)

    其中 ``x0<=x1, y0<=y1, z0<=z1``（若入参颠倒则先规范化），供 ``GL_TRIANGLES``
    与 ``_PANEL_BOX_TRIANGLE_INDICES`` 使用；**不使用 GL_QUADS**。
    """
    xa, xb = (x0, x1) if x0 <= x1 else (x1, x0)
    ya, yb = (y0, y1) if y0 <= y1 else (y1, y0)
    za, zb = (z0, z1) if z0 <= z1 else (z1, z0)
    return [
        (xa, ya, za),
        (xb, ya, za),
        (xb, yb, za),
        (xa, yb, za),
        (xa, ya, zb),
        (xb, ya, zb),
        (xb, yb, zb),
        (xa, yb, zb),
    ]


# 与 ``_panel_box_vertices_xyz`` 的 0..7 顶点顺序一致：12 三角 = 6 面 × 2
_PANEL_BOX_TRIANGLE_INDICES: tuple[tuple[int, int, int], ...] = (
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

# 12 棱（线框）
_PANEL_BOX_EDGE_INDICES: tuple[tuple[int, int], ...] = (
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
)


def _panel_role_value_str(panel) -> str:
    """板件 role 的稳定字符串（避免本模块依赖 core 枚举类型）。"""
    r = getattr(panel, "role", None)
    if r is None:
        return ""
    v = getattr(r, "value", None)
    if isinstance(v, str):
        return v
    return str(r)


# ================================================================ View3D
class View3D(QOpenGLWidget if _HAS_OPENGL else QWidget):
    """3D 柜体设计视图。

    本项目中 **唯一** 在 OpenGL 可用时继承 ``QOpenGLWidget`` 的 3D 视图类（无独立
    ``Cabinet3DView`` / ``GLView`` 别名）。鼠标与键盘交互 **必须** 实现在本类内，
    勿放到 ``MainWindow``。

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
    AXIS_X_COLOR = (0.85, 0.25, 0.25)
    AXIS_Y_COLOR = (0.25, 0.75, 0.30)
    AXIS_Z_COLOR = (0.25, 0.45, 0.85)

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

    # 线框 / 板件黑棱等边线线宽（≤2，避免部分 GPU 异常）
    _EDGE_LINE_WIDTH = 1.2
    _ENABLE_CAMERA_ORBIT = True  # 画柜子模式允许左键轨道旋转（拖拽超阈值触发）
    _SHOW_COORDINATE_AXES = False  # 隐藏 3D 视图中的坐标线（世界轴 + 左下角坐标轴 HUD）

    def __init__(self, parent=None):
        super().__init__(parent)

        # 使用 ``main.py`` 中 ``QSurfaceFormat.setDefaultFormat`` 的 MSAA 等设置，此处不 ``setFormat`` 覆盖

        # ── 2D 同步：户型墙体挤出 ───────────────────────────────────
        self._room: Room | None = None
        self._extrude_height = self.DEFAULT_EXTRUDE_HEIGHT

        # ── 摄像机状态 ────────────────────────────────────────────
        self._azimuth   = self._DEFAULT_AZIMUTH
        self._elevation = self._DEFAULT_ELEVATION
        self._distance  = self._DEFAULT_DISTANCE
        self._target    = QVector3D(self._DEFAULT_TARGET)

        # ── 鼠标：点击 vs 旋转（阈值 8~12px，勿低于 6）────────────────
        self._last_pos: QPoint | None = None
        self.mouse_press_pos: QPoint | None = None
        self.pending_click = False
        self.is_rotating = False
        self.rotate_threshold = 8
        self._pressed_hover_face = None
        self._pressed_hover_space_id: str | None = None
        self._drag_mode: str = "none"   # "orbit" | "pan"
        self._click_command_in_flight: bool = False  # 防双击/连点重复提交 ADD_PANEL
        self._suppress_incremental_update: bool = False  # solver 期间抑制中间 update
        self._floor_tex_id: int = 0     # OpenGL 地板纹理（diban.jpg），initializeGL 中加载

        # 柜体「逻辑空间」根盒（与画柜子主 3D 同一套背景/地面/网格，仅多画此盒）
        self._cabinet_space = None
        # 空间拾取：约束引擎（无 Qt 依赖，可复用）
        self._space_pick_engine = cabinet_space_constraint_engine()
        # 用户户型环境：室外地面+透视网格、房间内墙与地面；柜体设计模式下可关闭
        self._show_user_floorplan_environment = True
        # 由 `SOLVE_COMPLETED` 订阅回调写入的板件列表，供 OpenGL 叠加绘制
        self._display_panels: list | None = None
        # 与 ``SolveResult.panel_groups`` 同步，供日志与后续扩展（与展平 ``_display_panels`` 一致）
        self._display_panel_groups: list | None = None

        self.current_tool: ToolMode = ToolMode.SELECT
        # ``bind`` 注入 ``controller`` / ``dispatcher``（历史字段；加板不经 Dispatcher）
        self.controller: Any = None
        self.dispatcher: Any = None

        if not _HAS_OPENGL:
            # 软渲染模式：接受 QPainter 绘制
            self.setAutoFillBackground(True)
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.Window, self.BG_COLOR)
            self.setPalette(pal)

        # QOpenGLWidget / QWidget：鼠标跟踪与强焦点须在本控件上设置，否则无键 move 与快捷键无法送达
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

        # 与 ``from PyQt6.QtGui import QShortcut, QKeySequence`` 相同 API；本仓库绑定 PySide6。
        # 注意：``QKeySequence("Z+Space")`` 在 Qt Portable 下解析为空，快捷键永远不会触发；
        # 使用 ``Z, Space`` 表示「先按 Z、再按 Space」（与常见 Z+Space 操作习惯一致）。
        from PySide6.QtGui import QShortcut, QKeySequence

        _ks = QKeySequence.fromString(
            "Z, Space", QKeySequence.SequenceFormat.PortableText
        )
        self.shortcut_left_panel = QShortcut(_ks, self)
        self.shortcut_left_panel.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.shortcut_left_panel.setEnabled(False)
        self.shortcut_left_panel.activated.connect(
            self._shortcut_submit_add_left_panel
        )

    def showEvent(self, event):
        """显示后再次确认鼠标跟踪与焦点策略（栈切换后可能被重置）。"""
        super().showEvent(event)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def set_tool_mode(self, mode: ToolMode) -> None:
        """切换柜体设计工具状态（仅状态位，不派发命令）。"""
        if mode == ToolMode.SELECT:
            mgr = resolve_cabinet_interaction_manager(self)
            if mgr is not None:
                mgr.clear_preview_on_select_tool()
        self.current_tool = mode

    def _orbit_eye_qvector(self) -> QVector3D:
        """与 ``paintGL`` / ``_eye_pos`` 一致的轨道眼点（mm）。"""
        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)
        d = self._distance
        x = d * math.cos(el) * math.sin(az)
        y = d * math.sin(el)
        z = d * math.cos(el) * math.cos(az)
        return QVector3D(
            self._target.x() + x,
            self._target.y() + y,
            self._target.z() + z,
        )

    def _cabinet_screen_ray_mm(
        self, sx: float, sy: float
    ) -> tuple[QVector3D, QVector3D] | None:
        """与 ``paintGL`` 一致的透视 + lookAt，得到世界空间射线（mm）。"""
        if not _HAS_OPENGL:
            return None
        w, h = self.width(), self.height()
        if w < 1 or h < 1:
            return None
        aspect = w / max(h, 1)
        proj = QMatrix4x4()
        proj.perspective(58.0, aspect, 3.0, 800_000.0)
        eye = self._orbit_eye_qvector()
        view = QMatrix4x4()
        view.lookAt(eye, self._target, QVector3D(0, 1, 0))
        mvp = proj * view
        inv, ok = mvp.inverted()
        if not ok:
            return None
        nx = 2.0 * float(sx) / float(w) - 1.0
        ny = 1.0 - 2.0 * float(sy) / float(h)

        def _un(zc: float) -> QVector3D | None:
            rx, ry, rz, rw = _matrix4x4_mul_vector4(inv, nx, ny, zc, 1.0)
            if abs(rw) < 1e-9:
                return None
            return QVector3D(rx / rw, ry / rw, rz / rw)

        pn = _un(-1.0)
        pf = _un(1.0)
        if pn is None or pf is None:
            return None
        rd = pf - pn
        ln = rd.length()
        if ln < 1e-9:
            return None
        return pn, QVector3D(rd.x() / ln, rd.y() / ln, rd.z() / ln)

    def _cabinet_world_to_screen_px(
        self, wx: float, wy: float, wz: float
    ) -> tuple[float, float] | None:
        """世界坐标 (mm) → 主 3D 视图像素，与 ``_cabinet_screen_ray_mm`` 同一套 MVP。"""
        if not _HAS_OPENGL:
            return None
        w, h = self.width(), self.height()
        if w < 1 or h < 1:
            return None
        aspect = w / max(h, 1)
        proj = QMatrix4x4()
        proj.perspective(58.0, aspect, 3.0, 800_000.0)
        eye = self._orbit_eye_qvector()
        view = QMatrix4x4()
        view.lookAt(eye, self._target, QVector3D(0, 1, 0))
        mvp = proj * view
        rx, ry, rz, rw = _matrix4x4_mul_vector4(
            mvp, float(wx), float(wy), float(wz), 1.0
        )
        if abs(rw) < 1e-9:
            return None
        ndc_x = rx / rw
        ndc_y = ry / rw
        if ndc_x < -1.05 or ndc_x > 1.05 or ndc_y < -1.05 or ndc_y > 1.05:
            return None
        sx = (ndc_x + 1.0) * 0.5 * float(w)
        sy = (1.0 - ndc_y) * 0.5 * float(h)
        return (sx, sy)

    def _try_unlock_cabinet_occ_leaf_at_screen(self, sx: float, sy: float) -> bool:
        """锁定态 OCCUPIED 叶：普通单击盒体 AABB 解锁为 ALLOWED 配色。"""
        root = self._cabinet_space
        if root is None:
            return False
        ray = self._cabinet_screen_ray_mm(sx, sy)
        if ray is None:
            return False
        origin, direction = ray
        leaf = unlock_closest_occ_leaf_if_locked(
            root,
            (origin.x(), origin.y(), origin.z()),
            (direction.x(), direction.y(), direction.z()),
        )
        return leaf is not None

    def _try_toggle_cabinet_occ_leaf_at_screen(self, sx: float, sy: float) -> bool:
        """Ctrl+单击：命中 OCCUPIED 叶 AABB 时在允许/锁定间切换。"""
        root = self._cabinet_space
        if root is None:
            return False
        ray = self._cabinet_screen_ray_mm(sx, sy)
        if ray is None:
            return False
        origin, direction = ray
        leaf = pick_closest_structural_occupied_leaf_for_ray(
            root,
            (origin.x(), origin.y(), origin.z()),
            (direction.x(), direction.y(), direction.z()),
        )
        if leaf is None:
            return False
        toggle_cabinet_ops_user_allow(leaf)
        return True

    def cabinet_space_pick_at_world_point(self, wx: float, wy: float, wz: float) -> bool:
        """
        世界坐标点是否命中可放置叶空间（轴对齐包围盒 + 拾取管线）。

        供 UI 在具备世界点（如反投影）时使用；不在此处写状态/遍历细节。
        """
        root = self._cabinet_space
        if root is None:
            return False
        picked = SpacePicker.pick_leaf_for_world_point(
            root,
            float(wx),
            float(wy),
            float(wz),
            constraint_engine=self._space_pick_engine,
            board_context=None,
        )
        return picked is not None

    def _submit_main_3d_add_left_panel_interaction(
        self,
        *,
        payload: dict | None,
        source: CabinetInteractionSource,
    ) -> None:
        """主 3D：宿主 ``submit_add_left_panel_interaction``（统一编辑链路）。"""
        cdv = resolve_cabinet_design_view(self)
        if cdv is None:
            return
        pl: dict = payload if payload is not None else {}
        try:
            fn = getattr(cdv, "submit_add_left_panel_interaction", None)
            if not callable(fn):
                return
            fn(pl, source=source)
        except Exception:
            pass

    def _shortcut_submit_add_left_panel(self) -> None:
        """QShortcut「Z, Space」：经 ``CabinetInteractionManager`` 提交加左侧板。"""
        if self._cabinet_space is None:
            return
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._submit_main_3d_add_left_panel_interaction(
            payload={},
            source=CabinetInteractionSource.MAIN_3D_SHORTCUT,
        )

    def _sync_cabinet_space_placement_ui_metadata(self) -> None:
        """由 ``PreviewManager`` 规格刷新叶 ``Space.metadata``（非硬编码左板）。"""
        root = self._cabinet_space
        if root is None or not _HAS_OPENGL:
            return
        mgr = resolve_cabinet_interaction_manager(self)
        if mgr is not None:
            mgr.preview.sync_placement_metadata(
                root,
                engine=self._space_pick_engine,
                tool_mode=self.current_tool,
            )
            return
        refresh_leaf_placement_ui_metadata(root, board_for_space=None)

    def _interaction_hover_move(
        self, sx: float, sy: float, *, mouse_pos: Any | None = None
    ) -> None:
        """Viewport → ``InteractionManager`` → ``PreviewManager``（本控件不直接拾取）。"""
        if not _HAS_OPENGL or self._cabinet_space is None:
            return
        mgr = resolve_cabinet_interaction_manager(self)
        if mgr is None:
            return
        tick = mgr.handle_viewport_hover_move(
            VIEWPORT_MAIN_3D,
            sx,
            sy,
            viewport=self,
            tool_mode=self.current_tool,
            drag_mode=self._hover_drag_mode(),
            mouse_pos=mouse_pos,
        )
        if tick.needs_repaint:
            self.update()

    @property
    def current_hover_face(self):
        mgr = resolve_cabinet_interaction_manager(self)
        if mgr is None:
            return None
        hit = mgr.current_hover
        if hit is not None:
            return hit.face
        return mgr.hover_state.hovered_face_type or None

    @property
    def current_hover_space_id(self) -> str | None:
        mgr = resolve_cabinet_interaction_manager(self)
        if mgr is None:
            return None
        hit = mgr.current_hover
        if hit is not None:
            sid = str(getattr(getattr(hit, "space", None), "id", "") or "").strip()
            return sid or None
        sid = getattr(mgr.hover_state, "hovered_space_id", None)
        if sid:
            s = str(sid).strip()
            return s if s else None
        return None

    def _cabinet_preview_active(self) -> bool:
        mgr = resolve_cabinet_interaction_manager(self)
        return mgr is not None and mgr.preview.active

    def _hover_drag_mode(self) -> str:
        """悬停拾取用：旋转/平移进行时不更新 hover。"""
        if self.is_rotating:
            return "orbit"
        if self._drag_mode == "pan":
            return "pan"
        return "none"

    def _move_point(self, event) -> QPoint:
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def _update_hover(self, pos: QPoint) -> None:
        self._interaction_hover_move(float(pos.x()), float(pos.y()), mouse_pos=pos)

    def _rotate_camera(self, curr: QPoint) -> None:
        if self._last_pos is None:
            self._last_pos = curr
            return
        dx = curr.x() - self._last_pos.x()
        dy = curr.y() - self._last_pos.y()
        self._last_pos = curr
        self._azimuth -= dx * 0.5
        self._elevation = max(-89.0, min(89.0, self._elevation + dy * 0.5))
        self.sig_camera_changed.emit(self._azimuth, self._elevation)

    def _pan_camera(self, curr: QPoint) -> None:
        if self._last_pos is None:
            self._last_pos = curr
            return
        dx = curr.x() - self._last_pos.x()
        dy = curr.y() - self._last_pos.y()
        self._last_pos = curr
        az = math.radians(self._azimuth)
        speed = self._distance * 0.0015
        right = QVector3D(math.cos(az), 0, -math.sin(az))
        up = QVector3D(0, 1, 0)
        self._target -= right * (dx * speed)
        self._target += up * (dy * speed)

    def _confirm_pressed_hover_click(self, px: float, py: float) -> bool:
        """释放时用按下瞬间锁定的 space/face 确认点击（禁止读 current_hover_*）。"""
        face = self._pressed_hover_face
        space_id = self._pressed_hover_space_id
        if not space_id or face is None or not isinstance(face, FaceType):
            return False
        mgr = resolve_cabinet_interaction_manager(self)
        if mgr is None:
            return False
        mgr.current_hover_result = HoverResult(
            space_id=str(space_id).strip(),
            face_type=face,
        )
        return mgr.confirm_viewport_hover_click(
            VIEWPORT_MAIN_3D,
            px,
            py,
            viewport=self,
            source=CabinetInteractionSource.MAIN_3D_HOVER_CLICK,
            tool_mode=self.current_tool,
        )

    def rebuild_all_display_panels(self, panels: list | None) -> None:
        """
        全量重建板件绘制列表。

        仅允许：柜体尺寸变化、根布局重算、``SPACE_CHANGED`` 全量求解链调用。
        """
        plist: list = []
        seen: set[str] = set()
        for p in list(panels or []):
            pid = str(getattr(p, "id", "") or "")
            if pid:
                if pid in seen:
                    continue
                seen.add(pid)
            plist.append(p)
        self._display_panels = plist if plist else None
        print("[View3D] rebuild panels =", len(plist))
        if plist:
            draw_p = None
            for p in plist:
                role = getattr(p, "role", None)
                face = try_get_face_by_panel_role(role) if role is not None else None
                if face is FaceType.LEFT:
                    draw_p = p
                    break
            if draw_p is None:
                draw_p = plist[-1]
            print(
                f"[View3D] draw panel ... {float(draw_p.thickness)} {float(draw_p.height)} {float(draw_p.width)}"
            )
        if self._cabinet_space is not None and _HAS_OPENGL:
            self._sync_cabinet_space_placement_ui_metadata()
        self.update()

    def set_display_panels(
        self, panels: list | None, *, full_rebuild: bool = False
    ) -> None:
        """兼容入口；仅 ``full_rebuild=True`` 时全量重建，否则无操作。"""
        if full_rebuild:
            self.rebuild_all_display_panels(panels)

    @property
    def panel_visuals(self) -> list:
        """与真实板件 1:1 的绘制列表（``_display_panels``）。"""
        return list(self._display_panels or [])

    def _assert_panel_visual_invariant(self) -> None:
        panels = self._display_panels or []
        ids = [str(getattr(p, "id", "") or "") for p in panels]
        if len(ids) != len(set(i for i in ids if i)):
            raise RuntimeError(
                f"[View3D] duplicate panel visual ids: {ids}"
            )

    def add_panel_visual(
        self, panel: object, *, target_space: object | None = None
    ) -> bool:
        """增量追加单块板件；已存在同 ``id`` 时禁止重复 append。"""
        pid = str(getattr(panel, "id", "") or "")
        if not pid:
            return False
        known = {
            str(getattr(p, "id", "") or "") for p in (self._display_panels or [])
        }
        if pid in known:
            return False
        self.append_display_panels([panel], target_space=target_space)
        self._assert_panel_visual_invariant()
        return True

    def append_display_panels(
        self, panels: list, *, target_space: object | None = None
    ) -> None:
        """增量追加板件 GL（``AddBoardCommand``）；已存在同 ``id`` 时跳过。"""
        from ui.interaction.interaction_log import log_view3d_add_panel_visual

        incoming = list(panels or [])
        if not incoming:
            return
        existing = list(self._display_panels or [])
        known = {str(getattr(p, "id", "") or "") for p in existing}
        added: list = []
        for p in incoming:
            pid = str(getattr(p, "id", "") or "")
            if not pid or pid in known:
                continue
            existing.append(p)
            known.add(pid)
            added.append(p)
        if not added:
            return
        self._display_panels = existing
        log_view3d_add_panel_visual()
        if self._cabinet_space is not None and _HAS_OPENGL:
            if not self._suppress_incremental_update:
                if target_space is not None:
                    self.refresh_cabinet_spaces_incremental(target_space)
                else:
                    self._sync_cabinet_space_placement_ui_metadata()
                    self.update()

    def refresh_cabinet_spaces_incremental(self, anchor_space: object) -> None:
        """
        加板后仅刷新 ``anchor_space`` 及其子空间盒颜色（不重绑根、不 refit 相机）。
        """
        if self._cabinet_space is None or not _HAS_OPENGL:
            return
        self._sync_cabinet_space_placement_ui_metadata()
        self.update()

    def remove_panel_visual(self, panel_id: str) -> bool:
        """增量移除单块板件可视化。"""
        drop = str(panel_id or "")
        if not drop:
            return False
        before = len(self._display_panels or [])
        self.remove_display_panels_by_ids([drop])
        after = len(self._display_panels or [])
        if before != after:
            self._assert_panel_visual_invariant()
            return True
        return False

    def remove_display_panels_by_ids(self, panel_ids: list[str]) -> None:
        from ui.interaction.interaction_log import log_view3d_remove_panel_visual

        drop = {str(x) for x in (panel_ids or []) if x}
        if not drop or not self._display_panels:
            return
        remaining = [
            p
            for p in self._display_panels
            if str(getattr(p, "id", "") or "") not in drop
        ]
        if len(remaining) == len(self._display_panels):
            return
        self._display_panels = remaining if remaining else None
        log_view3d_remove_panel_visual()
        if self._cabinet_space is not None and _HAS_OPENGL:
            self._sync_cabinet_space_placement_ui_metadata()
        self.update()

    def rebuild_panels(self, panels: list | None) -> None:
        """
        全量同步板件绘制列表（``len(panel_visuals) == len(real_panels)``）。

        与 ``rebuild_all_display_panels`` 相同语义；``panel_groups`` 请展平为 ``Panel`` 列表传入。
        """
        flat: list = []
        for item in list(panels or []):
            if hasattr(item, "panels"):
                flat.extend(getattr(item, "panels", None) or [])
            else:
                flat.append(item)
        self.rebuild_all_display_panels(flat)
        self._assert_panel_visual_invariant()

    def set_display_panel_groups(self, panel_groups: list | None) -> None:
        """与 ``SolveResult.panel_groups`` 同步（仅缓存；板件绘制以 ``rebuild_all_display_panels`` 为准）。"""
        self.rebuild_panels(panel_groups)

    def set_show_user_floorplan_environment(self, visible: bool) -> None:
        """是否绘制用户户型环境（室外地面+透视网格、房间墙与地面）。

        柜体设计模式下传 ``False``：仅保留渐变天幕与柜体相关绘制（逻辑空间盒、板件、HUD），
        不绘制用户创建的墙/房间/地面及视图透视网格。
        """
        self._show_user_floorplan_environment = bool(visible)
        self.update()

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

    def set_cabinet_space(self, space, *, refit_camera: bool = True) -> None:
        """绑定柜体逻辑空间根盒（Space 或 None）；与主界面「画柜子」3D 共用本视图背景。

        Args:
            space: 根 ``Space`` 或 ``None``（退出柜体盒显示）。
            refit_camera: 为 ``False`` 时仅更新逻辑盒/拾取数据（如 ``SOLVE_COMPLETED`` 增量刷新），
                **不改变**方位角、仰角、距离与目标点（用户轨道视角保持不变）。
        """
        self._cabinet_space = space
        sc = getattr(self, "shortcut_left_panel", None)
        if sc is not None:
            if space is not None:
                sc.setEnabled(True)
                # 焦点常在属性/资源侧栏：应用级上下文才能在未点进 3D 时响应「Z, Space」
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            else:
                sc.setEnabled(False)
                sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                self._last_pos = None
                mgr = resolve_cabinet_interaction_manager(self)
                if mgr is not None:
                    mgr.clear_preview()
        if space is not None:
            self._sync_cabinet_space_placement_ui_metadata()
            if refit_camera:
                self._fit_camera_to_cabinet_space()
        if refit_camera:
            self.sig_camera_changed.emit(self._azimuth, self._elevation)
        self.update()

    def set_scene(self, space, *, refit_camera: bool = True) -> None:
        """与 ``set_cabinet_space`` 同义；供 ``CABINET_CREATED`` 等事件语义化调用。"""
        self.set_cabinet_space(space, refit_camera=refit_camera)

    def refresh(self) -> None:
        """柜体命令后轻量重绘（供 ``MainWindow.refresh_cabinet_view`` 调用）。"""
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
            GL.glEnable(GL.GL_MULTISAMPLE)
            GL.glEnable(GL.GL_LINE_SMOOTH)
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

            # QPainter 可能改变 GL 状态：每帧恢复深度测试与线平滑（禁止关闭深度测试，避免棱线穿透）
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_MULTISAMPLE)
            GL.glEnable(GL.GL_LINE_SMOOTH)

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

            # ── 室外：渐变地面 + 透视网格（用户「视图网格」）────────────────
            if self._show_user_floorplan_environment:
                self._draw_outdoor_ground_and_grid_gl()

            # ── 世界坐标轴 X/Y/Z（原点出发的三向线）──────────────
            if self._SHOW_COORDINATE_AXES:
                self._draw_world_axes_gl()

            # ── 房间实体：用户墙与地面（背面剔除自动隐藏前墙）─────────────
            if self._show_user_floorplan_environment:
                self._draw_room_solid_gl()

            # ── 柜体逻辑空间根盒（浅青半透明填充 + 纯青棱线）──
            self._draw_cabinet_space_gl()
            self._draw_hover_preview_ghost_gl()

            # ── 板件：实体盒 + 黑棱（数据由 SOLVE_COMPLETED 链写入）──
            self._draw_generated_panels_gl()

            # ── 左下角坐标轴 HUD ──────────────────────────────────
            if self._SHOW_COORDINATE_AXES:
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
                a = 0.42 + 0.38 * tr + 0.15 * (1.0 - tc)
                a = max(0.35, min(0.95, a))
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
            GL.glEnable(GL.GL_CULL_FACE)

        def _world_axis_length(self) -> float:
            """世界坐标轴长度（mm），随场景尺度自适应。"""
            span = 3000.0
            cs = getattr(self, "_cabinet_space", None)
            if cs is not None:
                span = max(
                    float(cs.width), float(cs.height), float(cs.depth), span,
                )
            room = getattr(self, "_room", None)
            if room and room.walls:
                xs: list[float] = []
                zs: list[float] = []
                for w in room.walls:
                    for px, pz in w.wall_polygon_points():
                        xs.append(float(px))
                        zs.append(float(pz))
                if xs:
                    span = max(max(xs) - min(xs), max(zs) - min(zs), span)
            return max(min(span * 0.45, 12_000.0), 1_800.0)

        def _draw_world_axes_gl(self) -> None:
            """在场景原点绘制 X/Y/Z 世界坐标轴线（红/绿/蓝）。"""
            length = self._world_axis_length()
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glLineWidth(2.5)
            axes = (
                (self.AXIS_X_COLOR, length, 0.0, 0.0),
                (self.AXIS_Y_COLOR, 0.0, length, 0.0),
                (self.AXIS_Z_COLOR, 0.0, 0.0, length),
            )
            for color, ex, ey, ez in axes:
                GL.glColor3f(*color[:3])
                GL.glBegin(GL.GL_LINES)
                GL.glVertex3f(0.0, 0.0, 0.0)
                GL.glVertex3f(ex, ey, ez)
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
            """柜体逻辑空间树：每个 ``Space`` 一盒（状态色由 mapper 决定）。"""
            root = getattr(self, "_cabinet_space", None)
            if root is None:
                return
            from core.space.tree import walk_dfs

            for node in walk_dfs(root):
                self._draw_cabinet_space_node_gl(node)

        def _draw_cabinet_space_node_gl(self, space: object) -> None:
            """绘制单个逻辑空间盒。"""
            pick = infer_space_state(space)
            placement = read_ui_placement_for_space_display(space)
            cab_allow = (
                read_cabinet_ops_user_allow(space)
                if pick is PickSpaceState.OCCUPIED
                else None
            )
            hovered = False
            mgr = resolve_cabinet_interaction_manager(self)
            if mgr is not None and mgr.preview.active:
                hit = mgr.preview.hit
                if hit is not None:
                    hovered = str(hit.space.id) == str(getattr(space, "id", ""))
            fr, er = space_box_face_edge_rgba(
                pick,
                placement,
                hovered=hovered or self._cabinet_preview_active(),
                cabinet_ops_user_allow=cab_allow,
            )
            x, y, z = float(space.x), float(space.y), float(space.z)
            w, h, d = float(space.width), float(space.height), float(space.depth)
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
            tris = (
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
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(1.0, 1.0)
            GL.glDepthMask(GL.GL_FALSE)
            GL.glColor4f(fr[0], fr[1], fr[2], fr[3])
            GL.glBegin(GL.GL_TRIANGLES)
            for a, b, c in tris:
                for i in (a, b, c):
                    GL.glVertex3f(*corners[i])
            GL.glEnd()
            GL.glDepthMask(GL.GL_TRUE)
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

            GL.glDepthMask(GL.GL_FALSE)
            GL.glLineWidth(self._EDGE_LINE_WIDTH)
            GL.glColor4f(er[0], er[1], er[2], er[3])
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
            GL.glDepthMask(GL.GL_TRUE)
            GL.glLineWidth(1.0)
            GL.glEnable(GL.GL_CULL_FACE)

        def _draw_hover_preview_ghost_gl(self) -> None:
            """Preview System 统一绘制（``preview_renderer.draw_viewport_preview_ghost``）。"""
            if self.current_tool not in (
                ToolMode.SELECT,
                *ADD_SIDE_PANEL_TOOL_MODES,
            ):
                return
            from ui.interaction.preview_renderer import draw_viewport_preview_ghost

            draw_viewport_preview_ghost(self, GL)

        def _gl_draw_panel(self, panel) -> None:
            """单块板件：轴对齐盒实体 + 黑棱（``paintGL`` 中按列表逐块调用）。"""
            try:
                if _resolve_panel_orientation(panel) == PanelOrientation.VERTICAL_X:
                    px = float(getattr(panel, "x", 0.0))
                    py = float(getattr(panel, "y", 0.0))
                    pz = float(getattr(panel, "z", 0.0))
                    sx = float(getattr(panel, "thickness", 0.0))
                    sy = float(getattr(panel, "height", 0.0))
                    sz = float(getattr(panel, "width", 0.0))
                    x0, x1 = px, px + sx
                    y0, y1 = py, py + sy
                    z0, z1 = pz, pz + sz
                else:
                    x0, x1, y0, y1, z0, z1 = _panel_world_aabb(panel)
            except Exception:
                return
            corners = _panel_box_vertices_xyz(x0, x1, y0, y1, z0, z1)
            md = getattr(panel, "metadata", None)
            st = md.get(METADATA_KEY) if isinstance(md, dict) else None
            fr, fg, fb, fa = panel_face_rgb(
                unplaced=st == UNPLACED or st == INVALID,
                blocked=st == BLOCKED,
                needs_relayout=st == NEEDS_RELAYOUT,
            )

            GL.glEnable(GL.GL_CULL_FACE)
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(1.0, 1.0)
            GL.glColor4f(fr, fg, fb, fa)
            GL.glBegin(GL.GL_TRIANGLES)
            for a, b, c in _PANEL_BOX_TRIANGLE_INDICES:
                for i in (a, b, c):
                    GL.glVertex3f(*corners[i])
            GL.glEnd()
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

            GL.glDisable(GL.GL_CULL_FACE)
            GL.glLineWidth(self._EDGE_LINE_WIDTH)
            er, eg, eb, _ = PANEL_EDGE_COLOR
            GL.glColor3f(er, eg, eb)
            GL.glBegin(GL.GL_LINES)
            for a, b in _PANEL_BOX_EDGE_INDICES:
                GL.glVertex3f(*corners[a])
                GL.glVertex3f(*corners[b])
            GL.glEnd()

        def _draw_generated_panels_gl(self) -> None:
            """板件：遍历 ``_display_panels``，对每块调用 ``_gl_draw_panel``（全量、不丢中间块）。"""
            panels = getattr(self, "_display_panels", None)
            if not panels:
                return
            GL.glDisable(GL.GL_BLEND)
            GL.glDepthMask(GL.GL_TRUE)
            for panel in panels:
                self._gl_draw_panel(panel)
            GL.glLineWidth(1.0)
            GL.glEnable(GL.GL_BLEND)
            GL.glEnable(GL.GL_CULL_FACE)

        def _draw_overlay_painter(self):
            """用 QPainter 在 GL 画面上叠加左下角坐标轴指示器和提示文字。"""
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_hud(painter)
            painter.end()

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
        show_env = getattr(self, "_show_user_floorplan_environment", True)
        rect = self.rect()
        margin = 56
        content_rect = rect.adjusted(margin, margin + 28, -margin, -margin)

        if show_env:
            if not room or not room.walls:
                painter.setPen(QPen(QColor("#909399")))
                f = painter.font()
                safe_set_font_size(f, 10)
                painter.setFont(f)
                painter.drawText(
                    rect.adjusted(24, 24, -24, -24),
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
            span_x = max(maxx - minx, 1.0)
            span_z = max(maxz - minz, 1.0)
            scale = min(content_rect.width() / span_x, content_rect.height() / span_z)
            ox = content_rect.left() + (content_rect.width() - span_x * scale) * 0.5
            oz = content_rect.top() + (content_rect.height() - span_z * scale) * 0.5

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
            _cap_font = QFont(painter.font())
            safe_set_font_size(_cap_font, 10)
            painter.setFont(_cap_font)
            painter.drawText(
                content_rect.left(),
                max(8, content_rect.top() - 22),
                f"顶视示意（软渲染）  挤出高度 {self._extrude_height:.0f} mm",
            )

        cs = getattr(self, "_cabinet_space", None)
        if cs is not None:
            nm = (getattr(cs, "name", "") or "").strip()
            dims = f"{float(cs.width):.0f} × {float(cs.height):.0f} × {float(cs.depth):.0f} mm"
            line = f"{nm}  {dims}" if nm else dims
            painter.setPen(QPen(QColor("#303133")))
            f2 = QFont(painter.font())
            safe_set_font_size(f2, 10)
            f2.setBold(True)
            painter.setFont(f2)
            top_ref = max(8, content_rect.top() - 44) if show_env else 28
            painter.drawText(self._CABINET_SPACE_HINT_X, top_ref, line)


    def _paint_hud(self, painter: QPainter):
        """绘制左下角坐标轴指示器。"""
        cs = getattr(self, "_cabinet_space", None)
        if cs is not None:
            nm = (getattr(cs, "name", "") or "").strip()
            dims = f"{float(cs.width):.0f} × {float(cs.height):.0f} × {float(cs.depth):.0f} mm"
            line = f"{nm}  {dims}" if nm else dims
            painter.setPen(QPen(QColor("#303133")))
            f = painter.font()
            safe_set_font_size(f, 11)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(self._CABINET_SPACE_HINT_X, 22, line)
        # ── 左下角迷你轴线指示器（X 红 / Y 绿 / Z 蓝，随相机旋转）──
        ox, oy = 52, self.height() - 52
        r = 36
        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)
        cos_az, sin_az = math.cos(az), math.sin(az)
        cos_el, sin_el = math.cos(el), math.sin(el)

        def mini_proj(dx, dy, dz):
            rx = dx * cos_az - dz * sin_az
            rz = dx * sin_az + dz * cos_az
            ry2 = dy * cos_el - rz * sin_el
            sx = ox + rx * r
            sy = oy - ry2 * r
            return QPointF(sx, sy)

        axes_def = [
            ((1, 0, 0), QColor("#e05050"), "X"),
            ((0, 1, 0), QColor("#50c070"), "Y"),
            ((0, 0, 1), QColor("#5080e0"), "Z"),
        ]
        origin_p = QPointF(ox, oy)
        _axis_lbl_font = QFont("Consolas")
        safe_set_font_size(_axis_lbl_font, 8)
        _axis_lbl_font.setWeight(QFont.Weight.Bold)
        painter.setFont(_axis_lbl_font)
        for (dx, dy, dz), color, lbl in axes_def:
            end_p = mini_proj(dx, dy, dz)
            pen2 = QPen(color)
            pen2.setWidthF(2.0)
            painter.setPen(pen2)
            painter.drawLine(origin_p, end_p)
            painter.drawText(QPointF(end_p.x() + 2, end_p.y() + 4), lbl)

    # ================================================================ 鼠标 / 键盘
    def mousePressEvent(self, event):
        if DEBUG_VIEW3D:
            print("[Mouse] press", flush=True)
        pos = event.position()

        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._last_pos = pos.toPoint()

        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press_pos = pos.toPoint()
            self._pressed_hover_face = self.current_hover_face
            self._pressed_hover_space_id = self.current_hover_space_id
            print(
                "[INPUT] mouse press",
                self._pressed_hover_space_id,
                self._pressed_hover_face,
                flush=True,
            )
            if not self._pressed_hover_space_id or self._pressed_hover_face is None:
                self.pending_click = False
                self.is_rotating = False
                self._pressed_hover_face = None
                self._pressed_hover_space_id = None
            else:
                self.pending_click = True
                self.is_rotating = False

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._cabinet_space is not None
            and _HAS_OPENGL
        ):
            px = float(pos.x())
            py = float(pos.y())
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                if self._try_unlock_cabinet_occ_leaf_at_screen(px, py):
                    self._sync_cabinet_space_placement_ui_metadata()
                    self._drag_mode = "none"
                    self._last_pos = None
                    event.accept()
                    self.update()
                    return
            if (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and self._try_toggle_cabinet_occ_leaf_at_screen(px, py)
            ):
                self._sync_cabinet_space_placement_ui_metadata()
                self._drag_mode = "none"
                self._last_pos = None
                event.accept()
                self.update()
                return
        if event.button() in (
            Qt.MouseButton.RightButton,
            Qt.MouseButton.MiddleButton,
        ):
            self._drag_mode = "pan"
        else:
            self._drag_mode = "none"

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if DEBUG_VIEW3D:
            print("[Mouse] release", flush=True)
        if event.button() == Qt.MouseButton.LeftButton:
            self.pending_click = False
            self.mouse_press_pos = None

            if self.is_rotating:
                print("[INPUT] drag release", flush=True)
                self.is_rotating = False
                self._drag_mode = "none"
                self._last_pos = None
                release_pos = self._move_point(event)
                self._update_hover(release_pos)
                super().mouseReleaseEvent(event)
                return

            print("[INPUT] click detected", flush=True)

            if (
                self._cabinet_space is not None
                and _HAS_OPENGL
            ):
                face = self._pressed_hover_face
                space_id = self._pressed_hover_space_id
                pos = event.position()
                px = float(pos.x())
                py = float(pos.y())
                if space_id and face is not None:
                    if self._click_command_in_flight:
                        pass
                    elif self.current_tool == ToolMode.SELECT:
                        self._click_command_in_flight = True
                        try:
                            self._confirm_pressed_hover_click(px, py)
                        finally:
                            self._click_command_in_flight = False
                    elif self.current_tool in ADD_SIDE_PANEL_TOOL_MODES:
                        self._click_command_in_flight = True
                        try:
                            self._confirm_pressed_hover_click(px, py)
                        finally:
                            self._click_command_in_flight = False

            self._drag_mode = "none"
            self._last_pos = None
            super().mouseReleaseEvent(event)
            return

        self._drag_mode = "none"
        self._last_pos = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        mgr = resolve_cabinet_interaction_manager(self)
        if mgr is not None:
            mgr.handle_viewport_leave(VIEWPORT_MAIN_3D, viewport=self)
        if self._cabinet_space is not None and _HAS_OPENGL:
            self._sync_cabinet_space_placement_ui_metadata()
        self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击：重置到默认视角。"""
        self._azimuth   = self._DEFAULT_AZIMUTH
        self._elevation = self._DEFAULT_ELEVATION
        self._distance  = self._DEFAULT_DISTANCE
        self._target    = QVector3D(self._DEFAULT_TARGET)
        self.sig_camera_changed.emit(self._azimuth, self._elevation)
        self.update()

    def mouseMoveEvent(self, event):
        curr = self._move_point(event)

        if self.pending_click and self.mouse_press_pos is not None:
            delta = (curr - self.mouse_press_pos).manhattanLength()
            if delta > self.rotate_threshold:
                self.pending_click = False
                if self._ENABLE_CAMERA_ORBIT:
                    self.is_rotating = True
                    self._drag_mode = "orbit"
                    self._last_pos = curr
                    print("[INPUT] drag rotate detected", flush=True)

        if self.is_rotating:
            self._rotate_camera(curr)
            self.update()
            super().mouseMoveEvent(event)
            return

        if self._drag_mode == "pan":
            self._pan_camera(curr)
            self.update()
            super().mouseMoveEvent(event)
            return

        self._update_hover(curr)
        self.update()
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.88 if delta > 0 else 1.0 / 0.88
        self._distance = max(3.0, min(720_000.0, self._distance * factor))
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_R:
            self.mouseDoubleClickEvent(None)
            super().keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)


# ================================================================ 工具函数
def _norm3(x, y, z):
    length = math.sqrt(x*x + y*y + z*z)
    if length < 1e-10:
        return (0.0, 1.0, 0.0)
    return (x/length, y/length, z/length)