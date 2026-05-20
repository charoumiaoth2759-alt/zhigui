# -*- coding: utf-8 -*-
"""柜体设计视图模块

包含：
    - CabinetDesignMenuBar   柜体设计模式专属菜单栏（保留兼容接口）
    - CabinetDesignView      柜体设计模式控制器
    - NavCube                3D 导航方块（ViewCube），跟随视图旋转

职责划分
--------
main_window.py 只负责：
    1. 创建 CabinetDesignView 实例
    2. 在"新建柜子确定"后调用 cabinet_view.enter(...)
    3. 连接 sig_finish → _exit_cabinet_mode（只做 side_tab 文字恢复）

本模块负责柜体设计模式下所有 UI 变化：
    - 菜单栏标题替换 / 追加专属项 / 退出时恢复
    - canvas 各控件（_cabinet_bar / _float_bar）显隐
    - 3D 视图切换
    - 资源面板切换
    - Tab 切换监听
    - NavCube 创建、显隐、旋转同步
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QEvent, QPointF, QSize
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QPainter, QPen, QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget, QDialog,
)


def _exec_new_cabinet_dialog_for_total_size(parent: QWidget | None, project) -> bool:
    """弹出 `ui.main_window.new_cabinet_dialog.NewCabinetDialog`；确认则写回 project。返回是否已接受。"""
    from ui.main_window.new_cabinet_dialog import NewCabinetDialog

    dn = str(getattr(project, "name", "空框架")) if project is not None else "空框架"
    dw = int(getattr(project, "cabinet_width", 2400)) if project is not None else 2400
    dh = int(getattr(project, "cabinet_height", 2200)) if project is not None else 2200
    dd = int(getattr(project, "cabinet_depth", 600)) if project is not None else 600

    dlg = NewCabinetDialog(
        parent=parent,
        default_name=dn,
        default_w=dw,
        default_h=dh,
        default_d=dd,
    )
    dlg.adjustSize()
    host = parent.window() if parent is not None else None
    if host is not None:
        geo = host.frameGeometry()
        hint = dlg.sizeHint()
        dlg.move(
            geo.x() + (geo.width() - hint.width()) // 2,
            geo.y() + (geo.height() - hint.height()) // 2,
        )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    if project is not None:
        if hasattr(project, "name"):
            project.name = dlg.product_name
        if hasattr(project, "cabinet_width"):
            project.cabinet_width = dlg.cabinet_width
        if hasattr(project, "cabinet_height"):
            project.cabinet_height = dlg.cabinet_height
        if hasattr(project, "cabinet_depth"):
            project.cabinet_depth = dlg.cabinet_depth
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 柜体设计模式专属菜单栏（保留，供独立使用扩展）
# ══════════════════════════════════════════════════════════════════════════════

class CabinetDesignMenuBar(QWidget):
    """柜体设计模式菜单栏。保留兼容接口，实际改名逻辑由 CabinetDesignView.enter() 完成。"""

    sig_exit_mode = Signal()
    sig_action    = Signal(str)

    _BAR_STYLE = """
        CabinetDesignMenuBar {
            background: #ffffff;
            border-bottom: 1px solid #d0d5dd;
        }
    """
    _MODE_BTN_STYLE = """
        QPushButton {
            background: transparent; border: none;
            color: #1a6fc4; font-size: 13px; font-weight: bold;
            padding: 0 10px; height: 32px;
        }
        QPushButton:hover { color: #0a5aaa; text-decoration: underline; }
    """
    _ACTION_BTN_STYLE = """
        QPushButton {
            background: transparent; border: none; border-radius: 3px;
            color: #303133; font-size: 13px; padding: 0 8px;
            height: 28px; min-width: 36px;
        }
        QPushButton:hover { background: #e8f0fe; color: #1a6fc4; }
        QPushButton:pressed { background: #d0e4fc; }
    """
    _EXPORT_BTN_STYLE = """
        QToolButton {
            background: transparent; border: none; border-radius: 3px;
            color: #303133; font-size: 13px; padding: 0 8px;
            height: 28px; min-width: 44px;
        }
        QToolButton:hover { background: #e8f0fe; color: #1a6fc4; }
        QToolButton::menu-indicator { image: none; }
    """
    _ACTIONS = [
        ("total_size",  "总尺寸",  "查看/修改总体尺寸"),
        ("material",    "材料",    "材料管理"),
        ("cut",         "剪切",    "剪切 (Ctrl+X)"),
        ("copy",        "复制",    "复制 (Ctrl+C)"),
        ("paste",       "粘贴",    "粘贴 (Ctrl+V)"),
        ("delete",      "删除",    "删除选中构件"),
        ("undo",        "撤消",    "撤消 (Ctrl+Z)"),
        ("hide",        "隐藏",    "隐藏选中构件"),
        ("show_all",    "全显示",  "显示全部构件"),
        ("show_dim",    "显尺寸",  "显示/隐藏尺寸标注"),
        ("measure",     "测量",    "测量工具"),
        ("hidden_line", "消隐",    "消隐线渲染"),
        ("settings",    "设置",    "柜体设计设置"),
        ("mark",        "标记",    "添加标记/注释"),
    ]
    _EXPORT_ITEMS = [
        ("export_pdf",   "导出 PDF"),
        ("export_dxf",   "导出 DXF"),
        ("export_excel", "导出 Excel 拆单表"),
        ("export_image", "导出图片"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._BAR_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(0)
        m = QPushButton("柜体设计模式")
        m.setStyleSheet(self._MODE_BTN_STYLE)
        m.setCursor(Qt.CursorShape.PointingHandCursor)
        m.setToolTip("点击退出柜体设计模式，返回主界面")
        m.clicked.connect(self.sig_exit_mode)
        lay.addWidget(m)
        lay.addWidget(self._vline())
        for key, label, tip in self._ACTIONS[:7]:
            lay.addWidget(self._btn(label, tip, key))
        lay.addWidget(self._vline())
        eb = QToolButton()
        eb.setText("导出 ▾")
        eb.setStyleSheet(self._EXPORT_BTN_STYLE)
        eb.setCursor(Qt.CursorShape.PointingHandCursor)
        eb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        em = QMenu(eb)
        em.setStyleSheet("""
            QMenu { background: #ffffff; border: 1px solid #d0d5dd;
                    border-radius: 4px; padding: 4px 0; font-size: 13px; }
            QMenu::item { padding: 5px 20px 5px 12px; }
            QMenu::item:selected { background: #e8f0fe; color: #1a6fc4; }
        """)
        for k, l in self._EXPORT_ITEMS:
            em.addAction(l).triggered.connect(
                lambda checked=False, _k=k: self.sig_action.emit(_k))
        eb.setMenu(em)
        lay.addWidget(eb)
        lay.addWidget(self._vline())
        for key, label, tip in self._ACTIONS[7:]:
            lay.addWidget(self._btn(label, tip, key))
        lay.addStretch(1)

    def _btn(self, label, tip, key):
        b = QPushButton(label)
        b.setStyleSheet(self._ACTION_BTN_STYLE)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if key == "total_size":
            b.clicked.connect(self._open_size_dialog)
        else:
            b.clicked.connect(lambda c=False, k=key: self.sig_action.emit(k))
        return b

    def _open_size_dialog(self):
        """弹出新建柜子同款对话框（new_cabinet_dialog），用于修改总尺寸。"""
        proj = getattr(self, "_project", None)
        if not _exec_new_cabinet_dialog_for_total_size(self, proj):
            return
        self.sig_action.emit("total_size_changed")

    def set_project(self, project):
        """绑定当前柜体项目，供总尺寸对话框读取初始值。
        
        在 CabinetDesignView.enter() 中调用：
            canvas._cabinet_design_menu_bar.set_project(project)
        """
        self._project = project

    def _vline(self):
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        f.setFixedWidth(1)
        f.setFixedHeight(20)
        f.setStyleSheet("QFrame { color: #d0d5dd; }")
        return f


# ══════════════════════════════════════════════════════════════════════════════
# 3D 导航方块（ViewCube）
# ══════════════════════════════════════════════════════════════════════════════


class NavCube(QWidget):
    """3D 导航方块（ViewCube）。

    投影变换与 View3D._paint_hud 的 mini_proj 公式相同；
    通过 sync_camera 对主视图角度取反，使方块相对空间旋转为相反方向。

    面定义（View3D 世界坐标系：X右，Y上，Z向屏幕外）：
        前 = 法线 (0,0,-1)  azimuth=0 时正对相机
        后 = 法线 (0,0, 1)
        右 = 法线 (1,0, 0)  屏幕右方
        左 = 法线(-1,0, 0)
        上 = 法线 (0,1, 0)  屏幕上方
        下 = 法线 (0,-1,0)

    sync_camera(azimuth, elevation) 接收 View3D.sig_camera_changed，
    内部对角度取反后驱动绘制。

    尺寸与字号：整体线性缩小 1/3（×2/3）；面标签在 8pt×4/3 后再放大 1/4（×5/4）。
    """

    # 原 100px，缩小三分之一 → 线性 ×2/3
    SIZE = int(round(100 * (2 / 3)))
    # 原 8pt×4/3≈11pt，再放大四分之一 → ×5/4
    LABEL_FONT_PT = int(round(round(8 * (4 / 3)) * (5 / 4)))

    # 六个面：(法线 xyz, 标签)；面填充为主题色（字色仍为白，见 paintEvent）
    _FACE_FILL = QColor("#2c3e50")
    _FACES = [
        ((0, 0, -1), "前"),
        ((0, 0, 1), "后"),
        ((1, 0, 0), "右"),
        ((-1, 0, 0), "左"),
        ((0, 1, 0), "上"),
        ((0, -1, 0), "下"),
    ]

    # 单位立方体 8 顶点（xyz ∈ {-1,+1}）
    # 索引: 0=(-1,-1,-1) 1=(+1,-1,-1) 2=(+1,+1,-1) 3=(-1,+1,-1)
    #       4=(-1,-1,+1) 5=(+1,-1,+1) 6=(+1,+1,+1) 7=(-1,+1,+1)
    _VERTS = [
        (-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),   # z=-1 面 (前)
        (-1,-1, 1),(1,-1, 1),(1,1, 1),(-1,1, 1),   # z=+1 面 (后)
    ]
    # 各面4顶点索引（外法线方向逆时针）
    _FACE_VERTS = [
        [0,1,2,3],  # 前 z=-1，法线(0,0,-1)
        [5,4,7,6],  # 后 z=+1，法线(0,0,+1)
        [1,5,6,2],  # 右 x=+1，法线(1,0,0)
        [4,0,3,7],  # 左 x=-1，法线(-1,0,0)
        [3,2,6,7],  # 上 y=+1，法线(0,1,0)
        [4,5,1,0],  # 下 y=-1，法线(0,-1,0)
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        self._azimuth   = 0.0    # 显示用：与 View3D 方位角反向对应
        self._elevation = 0.0    # 显示用：与 View3D 仰角反向对应
        self._drag_pos     = None
        self._hovered_face = -1
        self._proj_polys   = []

    # ── 公开接口：连接 View3D.sig_camera_changed ──────────────────────
    def sync_camera(self, azimuth: float, elevation: float):
        """接收主 3D 视图角度，以相反方向驱动导航块（水平/垂直均取反）。"""
        self._azimuth   = -azimuth
        self._elevation = -elevation
        self.update()

    # ── 投影：与 View3D._paint_hud.mini_proj 完全相同的变换 ───────────
    def _proj(self, dx, dy, dz):
        """将世界坐标 (dx,dy,dz) 投影到 widget 像素坐标。

        与 View3D._paint_hud mini_proj 公式完全一致：
            rx  = dx*cos_az - dz*sin_az
            rz  = dx*sin_az + dz*cos_az
            ry2 = dy*cos_el - rz*sin_el
            screen_x = cx + rx*scale
            screen_y = cy - ry2*scale
        """
        az     = math.radians(self._azimuth)
        el     = math.radians(self._elevation)
        cos_az = math.cos(az);  sin_az = math.sin(az)
        cos_el = math.cos(el);  sin_el = math.sin(el)
        rx  =  dx * cos_az - dz * sin_az
        rz  =  dx * sin_az + dz * cos_az
        ry2 =  dy * cos_el - rz * sin_el
        scale = self.SIZE * 0.36
        cx, cy = self.SIZE / 2.0, self.SIZE / 2.0
        return QPointF(cx + rx * scale, cy - ry2 * scale)

    def _cam_dot(self, nx, ny, nz) -> float:
        """法线与相机朝向的点积（> 0 表示面朝向相机，可见）。

        相机朝向向量 = normalize(target - eye)
                     = (-cos_el*sin_az, -sin_el, -cos_el*cos_az)
        """
        az     = math.radians(self._azimuth)
        el     = math.radians(self._elevation)
        cos_el = math.cos(el);  sin_el = math.sin(el)
        cx = -cos_el * math.sin(az)
        cy = -sin_el
        cz = -cos_el * math.cos(az)
        return nx * cx + ny * cy + nz * cz

    # ── 绘制 ──────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 投影所有顶点
        tv_2d = [self._proj(*v) for v in self._VERTS]
        # 深度：顶点 z 分量的平均（用于画家算法排序）
        # 深度用相机方向点积代替：沿相机方向的分量
        az     = math.radians(self._azimuth)
        el     = math.radians(self._elevation)
        cos_az = math.cos(az);  sin_az = math.sin(az)
        cos_el = math.cos(el);  sin_el = math.sin(el)

        def vert_depth(vx, vy, vz):
            # 顶点沿相机方向的投影分量（越小越近）
            rz = vx * sin_az + vz * cos_az
            return -(vy * sin_el - rz * cos_el)

        tv_depth = [vert_depth(*v) for v in self._VERTS]

        face_data = []
        for fi, ((nx, ny, nz), label) in enumerate(self._FACES):
            vis   = self._cam_dot(nx, ny, nz)
            idxs  = self._FACE_VERTS[fi]
            depth = sum(tv_depth[i] for i in idxs) / 4
            pts   = [tv_2d[i] for i in idxs]
            face_data.append((depth, vis, fi, QPolygonF(pts), label))

        # 由远到近绘制（画家算法）
        face_data.sort(key=lambda x: x[0], reverse=True)
        self._proj_polys = []

        for depth, vis, fi, poly, label in face_data:
            if vis < 0.02:
                self._proj_polys.append((fi, None))
                continue
            self._proj_polys.append((fi, poly))

            # 光照：面越正对相机越亮（底色 #2c3e50）
            base_color = self._FACE_FILL
            br    = 0.55 + 0.45 * min(1.0, max(0.0, vis))
            color = QColor(
                int(base_color.red()   * br),
                int(base_color.green() * br),
                int(base_color.blue()  * br),
            )
            if fi == self._hovered_face:
                color = color.lighter(140)

            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
            p.drawPolygon(poly)

            # 标签文字居中
            center = poly.boundingRect().center()
            font   = QFont("Microsoft YaHei", self.LABEL_FONT_PT, QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 230))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label)
            th = fm.ascent()
            p.drawText(
                int(center.x() - tw / 2),
                int(center.y() + th / 2 - 1),
                label,
            )

        p.end()

    # ── 命中检测 ──────────────────────────────────────────────────────
    def _face_at(self, pos: QPointF) -> int:
        for fi, poly in reversed(self._proj_polys):
            if poly is not None and poly.containsPoint(
                    pos, Qt.FillRule.OddEvenFill):
                return fi
        return -1

    # ── 鼠标事件（悬停高亮，自身拖拽不影响主视图）────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.pos()

    def mouseMoveEvent(self, event):
        pos = QPointF(event.pos())
        if self._drag_pos is not None:
            # NavCube 自身拖拽旋转（不联动主视图）
            dx = event.pos().x() - self._drag_pos.x()
            dy = event.pos().y() - self._drag_pos.y()
            self._azimuth   -= dx * 0.5
            self._elevation  = max(-89.0, min(89.0, self._elevation - dy * 0.5))
            self._drag_pos   = event.pos()
            self.update()
        else:
            fi = self._face_at(pos)
            if fi != self._hovered_face:
                self._hovered_face = fi
                self.update()

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None

    def leaveEvent(self, _event):
        self._hovered_face = -1
        self.update()


class CabinetDesignView(QWidget):
    """柜体设计模式控制器。

    负责进入/退出柜体设计模式时所有 UI 变化：
        - 菜单栏标题替换 + 追加/移除专属项
        - canvas 各控件显隐（_cabinet_bar / _float_bar）
        - 3D 视图切换
        - 资源面板切换
        - 侧栏 Tab 切换监听
        - NavCube 显隐 + 旋转同步

    对外接口
    --------
    enter(canvas, menu_bar, side_tab, resource_stack, status_bar, project)
        进入柜体设计模式，传入主窗口各组件引用。
    exit()
        退出柜体设计模式，由 sig_finish 或菜单"退出"触发。

    信号
    ----
    sig_finish   退出柜体设计模式时发射，主窗口监听后做侧栏 Tab 文字恢复。
    """

    sig_finish = Signal()

    # ── 柜体模式下左侧 Tab 的新标签 ──────────────────────────────────
    _CABINET_TABS = ["产品库", "材质", "图元", "孔位", "智能设计"]

    # ── 菜单栏顶级项替换标题（从左到右对应原菜单项）────────────────
    _CABINET_MENU_TITLES = [
        "柜体设计模式", "总尺寸", "材料", "剪切", "复制",
        "粘贴", "删除", "撤消", "导出▼", "隐藏",
        "全显示", "显尺寸", "测量", "消隐",
    ]

    # ── 消隐之后动态追加的专属菜单项 ─────────────────────────────────
    _CABINET_EXTRA_TITLES = ["设置", "标记", "退出"]

    # 资源面板映射：柜体模式 Tab idx → resource_stack idx
    # 0=产品库→画柜子面板(1)，1=材质→材质面板(2)，其余→画柜子面板(1)
    _CABINET_PANEL_MAP = {0: 1, 1: 2}

    def __init__(self, parent=None):
        super().__init__(parent)
        # 柜体设计模式下叠加在 3D 视图（View3D）左上角的导航方块
        self._nav_cube: NavCube | None = None
        # 保存进入时传入的各组件引用（退出时使用）
        self._canvas         = None
        self._menu_bar       = None
        self._side_tab       = None
        self._resource_stack = None
        self._status_bar     = None
        self._project        = None   # 当前柜体项目，enter() 时赋值
        # 菜单栏实例引用（用于连接 sig_action）
        self._design_menu_bar: CabinetDesignMenuBar | None = None
        # 状态保存
        self._orig_menu_titles:   list | None = None
        self._hidden_orig_actions: list | None = None
        self._cabinet_extra_actions: list | None = None
        self._cabinet_tab_handler = None
        # 柜体模式：将 menubar 第 2 项「打开」菜单替换为 QAction「总尺寸」，退出时还原
        self._cabinet_open_menu_bar_action: QAction | None = None
        self._cabinet_saved_insert_before: QAction | None = None
        self._cabinet_total_size_stub_action: QAction | None = None

    # ---------------------------------------------------------------- 公开 API

    def enter(self, canvas, menu_bar, side_tab, resource_stack,
              status_bar, project):
        """进入柜体设计模式。

        参数
        ----
        canvas         _Canvas2DWorkspace 实例
        menu_bar       主窗口 QMenuBar
        side_tab       SideTabBar
        resource_stack QStackedWidget
        status_bar     StatusBar
        project        CabinetProject / SimpleNamespace
        """
        self._canvas         = canvas
        self._menu_bar       = menu_bar
        self._side_tab       = side_tab
        self._resource_stack = resource_stack
        self._status_bar     = status_bar
        self._project        = project

        # ── 1. 左侧 Tab 文字替换 ──────────────────────────────────────
        btns = side_tab._buttons
        for i, new_name in enumerate(self._CABINET_TABS):
            if i < len(btns):
                btns[i].setText(
                    "\n".join(new_name) if "\n" not in new_name else new_name)
                btns[i].show()
        for i in range(len(self._CABINET_TABS), len(btns)):
            btns[i].hide()
        side_tab.set_current_index(0)

        # ── 2. 菜单栏标题替换 + 追加专属项 ───────────────────────────
        # 原第 2 项为「打开」顶级下拉菜单，仅 setText 无法改为「单击即弹窗」；
        # 先替换为 QAction「总尺寸」，triggered → new_cabinet_dialog.NewCabinetDialog。
        _actions = menu_bar.actions()
        self._orig_menu_titles = [a.text() for a in _actions]
        self._cabinet_open_menu_bar_action = None
        self._cabinet_saved_insert_before = None
        if self._cabinet_total_size_stub_action is not None:
            try:
                menu_bar.removeAction(self._cabinet_total_size_stub_action)
                self._cabinet_total_size_stub_action.deleteLater()
            except RuntimeError:
                pass
            self._cabinet_total_size_stub_action = None
        if len(_actions) > 2:
            self._cabinet_open_menu_bar_action = _actions[1]
            self._cabinet_saved_insert_before = _actions[2]
            menu_bar.removeAction(self._cabinet_open_menu_bar_action)
            stub = QAction(self._CABINET_MENU_TITLES[1], menu_bar)
            stub.triggered.connect(self._show_size_dialog)
            menu_bar.insertAction(self._cabinet_saved_insert_before, stub)
            self._cabinet_total_size_stub_action = stub
        _actions = menu_bar.actions()
        for i, title in enumerate(self._CABINET_MENU_TITLES):
            if i < len(_actions):
                _actions[i].setText(title)
        self._hidden_orig_actions = []
        for a in _actions[len(self._CABINET_MENU_TITLES):]:
            a.setVisible(False)
            self._hidden_orig_actions.append(a)

        self._cabinet_extra_actions = []
        for title in self._CABINET_EXTRA_TITLES:
            act = QAction(title, menu_bar)
            if title == "退出":
                act.triggered.connect(self.exit)
            elif title == "设置":
                # 柜体设计模式顶部菜单「设置」→ 与主窗口相同的系统参数对话框
                act.triggered.connect(self._open_system_param_dialog)
            menu_bar.addAction(act)
            self._cabinet_extra_actions.append(act)

        # ── 3. 切换到 3D 视图（画柜子 Tab index=1）───────────────────
        canvas.switch_view_by_tab(1)

        # ── 4. 隐藏左侧竖排工具栏 + 顶部悬浮按钮 ─────────────────────
        canvas._cabinet_bar.setVisible(False)
        canvas._float_bar.setVisible(False)

        # ── 4b. 连接菜单栏按钮信号（CabinetDesignMenuBar）──────────────
        # canvas._cabinet_design_menu_bar 为 CabinetDesignMenuBar 实例，
        # 若主窗口将其挂在 canvas 上则用此路径；否则按实际属性名调整。
        _dmb = getattr(canvas, '_cabinet_design_menu_bar', None)
        if _dmb is None:
            # 兼容：直接从 canvas 父窗口找
            _dmb = getattr(self.parent(), '_cabinet_design_menu_bar', None)
        self._design_menu_bar = _dmb
        if self._design_menu_bar is not None:
            try:
                self._design_menu_bar.sig_action.disconnect(self._on_menu_action)
            except RuntimeError:
                pass
            self._design_menu_bar.sig_action.connect(self._on_menu_action)

        # ── 5. 重置 View3D 到正前方，显示导航方块并连接信号 ─────────
        # 将 3D 视图重置为正前方（azimuth=0, elevation=0）
        view3d = canvas._3d_view
        view3d._azimuth   = 0.0
        view3d._elevation = 0.0
        view3d.update()
        view3d.sig_camera_changed.emit(0.0, 0.0)

        if self._nav_cube is None:
            self._nav_cube = NavCube(view3d)
        else:
            self._nav_cube.setParent(view3d)
        self._nav_cube.raise_()
        nc_sz = NavCube.SIZE
        self._nav_cube.setGeometry(12, 12, nc_sz, nc_sz)
        self._nav_cube.setVisible(True)
        self._nav_cube.raise_()
        # 初始同步为正前方（与 View3D 一致）
        self._nav_cube.sync_camera(0.0, 0.0)
        # 连接信号（先断开防重复）
        try:
            view3d.sig_camera_changed.disconnect(self._nav_cube.sync_camera)
        except RuntimeError:
            pass
        view3d.sig_camera_changed.connect(self._nav_cube.sync_camera)

        # ── 6. Tab 切换监听：始终 3D、工具栏隐藏、资源面板按映射切换 ──
        resource_stack.setCurrentIndex(self._CABINET_PANEL_MAP.get(0, 1))

        def _on_tab_changed(idx):
            canvas.switch_view("3d")
            canvas._cabinet_bar.setVisible(False)
            resource_stack.setCurrentIndex(self._CABINET_PANEL_MAP.get(idx, 1))
            # 导航方块始终置顶
            if self._nav_cube and self._nav_cube.isVisible():
                self._nav_cube.raise_()

        self._cabinet_tab_handler = _on_tab_changed
        side_tab.tab_changed.connect(self._cabinet_tab_handler)

        # ── 7. 状态栏提示 ─────────────────────────────────────────────
        status_bar.set_hint(
            f"已进入柜体设计：{getattr(project,'name','—')}  "
            f"{getattr(project,'cabinet_width','—')} × "
            f"{getattr(project,'cabinet_height','—')} × "
            f"{getattr(project,'cabinet_depth','—')} mm", 5000)

    def exit(self):
        """退出柜体设计模式，发射 sig_finish 通知主窗口。"""
        canvas         = self._canvas
        menu_bar       = self._menu_bar
        side_tab       = self._side_tab
        resource_stack = self._resource_stack
        status_bar     = self._status_bar

        if canvas is None:
            return   # 未进入过，安全退出

        if hasattr(canvas, "clear_cabinet_param_space"):
            canvas.clear_cabinet_param_space()

        # ── 1. 移除动态追加的专属菜单项 ──────────────────────────────
        if self._cabinet_extra_actions:
            for act in self._cabinet_extra_actions:
                menu_bar.removeAction(act)
            self._cabinet_extra_actions = None

        # ── 2. 恢复被隐藏的原菜单项 ──────────────────────────────────
        if self._hidden_orig_actions:
            for a in self._hidden_orig_actions:
                a.setVisible(True)
            self._hidden_orig_actions = None

        # ── 2b. 恢复「总尺寸」QAction 为原「打开」菜单（须在恢复标题前，保证索引一致）
        if self._cabinet_total_size_stub_action is not None:
            menu_bar.removeAction(self._cabinet_total_size_stub_action)
            self._cabinet_total_size_stub_action.deleteLater()
            self._cabinet_total_size_stub_action = None
        if (
            self._cabinet_open_menu_bar_action is not None
            and self._cabinet_saved_insert_before is not None
        ):
            menu_bar.insertAction(
                self._cabinet_saved_insert_before,
                self._cabinet_open_menu_bar_action,
            )
            self._cabinet_open_menu_bar_action = None
            self._cabinet_saved_insert_before = None

        # ── 3. 恢复原菜单标题 ─────────────────────────────────────────
        if self._orig_menu_titles:
            acts = menu_bar.actions()
            for i, orig in enumerate(self._orig_menu_titles):
                if i < len(acts):
                    acts[i].setText(orig)
            self._orig_menu_titles = None

        # ── 4. 断开 Tab 切换监听 ──────────────────────────────────────
        if self._cabinet_tab_handler:
            side_tab.tab_changed.disconnect(self._cabinet_tab_handler)
            self._cabinet_tab_handler = None

        # ── 4b. 断开菜单栏按钮信号 ────────────────────────────────────
        if self._design_menu_bar is not None:
            try:
                self._design_menu_bar.sig_action.disconnect(self._on_menu_action)
            except RuntimeError:
                pass
            self._design_menu_bar = None

        # ── 5. 断开信号，隐藏导航方块 ────────────────────────────────
        if self._nav_cube:
            try:
                canvas._3d_view.sig_camera_changed.disconnect(self._nav_cube.sync_camera)
            except RuntimeError:
                pass
            self._nav_cube.setVisible(False)

        # ── 6. 恢复 canvas 各控件 ─────────────────────────────────────
        canvas.switch_view_by_tab(1)          # 停在画柜子 Tab（3D + 工具栏）
        canvas._cabinet_bar.setVisible(True)
        canvas._cabinet_bar.raise_()
        canvas._float_bar.setVisible(True)

        # ── 7. 恢复资源面板到画柜子面板 ──────────────────────────────
        resource_stack.setCurrentIndex(1)
        resource_stack.show()

        # ── 8. 清空引用 ───────────────────────────────────────────────
        self._canvas = self._menu_bar = self._side_tab = None
        self._resource_stack = self._status_bar = None

        status_bar.set_hint("已退出柜体设计模式", 3000)

        # ── 9. 通知主窗口（做 side_tab 文字恢复）─────────────────────
        self.sig_finish.emit()

    def _on_menu_action(self, key: str) -> None:
        """处理 CabinetDesignMenuBar.sig_action（画布条上的按钮）。

        与 enter() 里主 QMenuBar 追加的「设置」一致：均打开系统参数对话框。
        """
        if key == "total_size":
            self._show_size_dialog()
        elif key == "settings":
            self._open_system_param_dialog()

    def _open_system_param_dialog(self) -> None:
        """弹出 `system_param_dialog.SystemParamDialog`，复用主窗口配置与保存逻辑。"""
        mw = self.window()
        fn = getattr(mw, "_open_system_param_dialog", None)
        if callable(fn):
            fn()
        elif self._status_bar is not None:
            self._status_bar.set_hint("系统设置不可用", 2000)

    def _show_size_dialog(self) -> None:
        """弹出 new_cabinet_dialog，确认后更新项目数据与状态栏。"""
        proj = self._project
        if not _exec_new_cabinet_dialog_for_total_size(self, proj):
            return
        if self._status_bar is not None and proj is not None:
            self._status_bar.set_hint(
                f"总尺寸已更新：{getattr(proj, 'name', '')}  "
                f"{getattr(proj, 'cabinet_width', '')} × "
                f"{getattr(proj, 'cabinet_height', '')} × "
                f"{getattr(proj, 'cabinet_depth', '')} mm",
                3000,
            )
        # 同步右侧属性面板尺寸（若主窗口已创建）
        mw = self.window()
        pp = getattr(mw, "_prop_panel", None)
        if pp is not None and proj is not None:
            pp.set_dimensions(
                float(getattr(proj, "cabinet_width", 2400)),
                float(getattr(proj, "cabinet_height", 2200)),
                float(getattr(proj, "cabinet_depth", 600)),
            )

    def on_canvas_resize(self, _canvas_width: int):
        """主窗口 canvas resizeEvent 时调用，保持导航方块在 3D 视图左上角。"""
        if self._nav_cube and self._nav_cube.isVisible():
            nc_sz = NavCube.SIZE
            self._nav_cube.setGeometry(12, 12, nc_sz, nc_sz)
            self._nav_cube.raise_()


# ══════════════════════════════════════════════════════════════════════════════
# 内部：柜体画布占位控件（保留，供将来替换为真实 3D 渲染器）
# ══════════════════════════════════════════════════════════════════════════════

class _CabinetCanvas(QWidget):
    """柜体设计画布占位。生产版本替换为真实 OpenGL / QPainter 3D 渲染器。"""

    _BG_COLOR = QColor("#1a2035")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self.setMinimumSize(400, 300)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        self._title_lbl = QLabel("柜体设计视图")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setPointSize(20); f.setBold(True)
        self._title_lbl.setFont(f)
        self._title_lbl.setStyleSheet("color: #7ea8d8;")
        lay.addWidget(self._title_lbl)
        self._info_lbl = QLabel("（尚未加载项目）")
        self._info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_lbl.setStyleSheet("color: #506070; font-size: 13px;")
        lay.addWidget(self._info_lbl)

    def set_project(self, project):
        self._project = project
        if project is None:
            self._info_lbl.setText("（尚未加载项目）")
            return
        self._info_lbl.setText(
            f"{getattr(project,'name','—')}    "
            f"{getattr(project,'cabinet_width','—')} × "
            f"{getattr(project,'cabinet_height','—')} × "
            f"{getattr(project,'cabinet_depth','—')} mm")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QBrush(self._BG_COLOR))
        p.end()
        super().paintEvent(_event)