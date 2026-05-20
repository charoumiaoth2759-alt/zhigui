# -*- coding: utf-8 -*-
"""柜体设计模式 —— 组件面板（通用组件 / 常用部件 / 隐藏选项）

主窗口中叠在画布右侧、紧靠属性面板左侧，与 `CabinetPropertyPanel` 无隙并排。
"""

from __future__ import annotations
import os, sys

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget, QGraphicsDropShadowEffect,
)

# ─── 路径 ───────────────────────────────────────────────────────────────────

def _project_root() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base: return base
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, ".."))

def _resolve_dir(name):
    p = os.path.join(_project_root(), name)
    return p if os.path.isdir(p) else os.path.abspath(name)

def _resolve_icon_dir():      return _resolve_dir("icons")
def _resolve_templates_dir(): return _resolve_dir("templates")

# 柜体设计 22 宫格：前若干格优先使用与主程序一致的 icons/panel/*.png
# 元组 (槽位索引 0-based, 文件名, 悬停/状态栏显示名)
_ICONS_PANEL_SUBDIR = "panel"
_PANEL_ICON_SLOTS: tuple[tuple[int, str, str], ...] = (
    (0, "左右侧板.png", "左右侧板"),
    (1, "顶底板.png", "顶底板"),
    (2, "左侧板.png", "左侧板"),
    (3, "顶板.png", "顶板"),
    (4, "右侧板.png", "右侧板"),
    (5, "底板.png", "底板"),
    (6, "中立板.png", "中立板"),
    (7, "固层.png", "固层"),
    (8, "挡风板.png", "挡风板"),
    (9, "活层.png", "活层"),
    (10, "收口条.png", "收口条"),
    (11, "见光板.png", "见光板"),
    (12, "薄背板.png", "薄背板"),
    (13, "厚背板.png", "厚背板"),
    (14, "开门.png", "开门"),
    (15, "移门.png", "移门"),
    (16, "抽屉.png", "抽屉"),
    (17, "酒架.png", "酒架"),
    (18, "加分割面.png", "加分割面"),
    (19, "柜子切角.png", "柜子切角"),
    (20, "工艺设置.png", "工艺设置"),
    (21, "取消切角.png", "取消切角"),
)


def _panel_icon_file_path(icon_dir: str, filename: str) -> str:
    """例如 icons/panel/左右侧板.png。"""
    p = os.path.join(icon_dir, _ICONS_PANEL_SUBDIR, filename)
    return p if os.path.isfile(p) else ""


def _panel_display_name_for_path(path: str) -> str | None:
    """若 path 为 panel 预设图则返回中文名，否则 None。"""
    if not path or not os.path.isfile(path):
        return None
    base = os.path.basename(path)
    for _slot, fname, disp in _PANEL_ICON_SLOTS:
        if base == fname:
            return disp
    return None


def assembler_icon_status_label(idx: int, path: str) -> str:
    """状态栏：panel 预设图显示中文名，其余显示文件名。"""
    disp = _panel_display_name_for_path(path) if path else None
    if disp:
        return disp
    return os.path.basename(path) if path else f"组件{idx + 1:02d}"

# ─── templates 扫描 ─────────────────────────────────────────────────────────

_MOD_EXTS = {".mod", ".json"}
_IMG_PREF = [".jpg", ".jpeg", ".png", ".bmp"]

def _find_thumb(mod_path):
    base = os.path.splitext(mod_path)[0]
    for ext in _IMG_PREF:
        p = base + ext
        if os.path.isfile(p): return p
    return ""

def _scan_templates(tpl_dir):
    if not os.path.isdir(tpl_dir): return []
    groups = []
    root_items = []
    for f in sorted(os.listdir(tpl_dir)):
        fp = os.path.join(tpl_dir, f)
        if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in _MOD_EXTS:
            root_items.append((os.path.splitext(f)[0], fp, _find_thumb(fp)))
    if root_items: groups.append(("常用部件", root_items))
    for entry in sorted(os.listdir(tpl_dir)):
        sub = os.path.join(tpl_dir, entry)
        if not os.path.isdir(sub): continue
        items = []
        for f in sorted(os.listdir(sub)):
            fp = os.path.join(sub, f)
            if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in _MOD_EXTS:
                items.append((os.path.splitext(f)[0], fp, _find_thumb(fp)))
        if items: groups.append((entry, items))
    return groups

def _load_icon_files(icon_dir):
    if not os.path.isdir(icon_dir):
        return []
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    return [
        os.path.join(icon_dir, f)
        for f in sorted(os.listdir(icon_dir))
        if os.path.splitext(f)[1].lower() in exts
    ]


# ─── 颜色 / 尺寸 ────────────────────────────────────────────────────────────

_BG    = "#f5f7fa"
_WHITE = "#ffffff"
_BORD  = "#dcdfe6"
_BLUE  = "#1a6fc4"
_TEXT  = "#303133"
_GRAY  = "#606266"
_ODD   = "#f8f9fb"
_GRP   = "#e8edf5"
_RED   = "#e74c3c"
_RED_B = "#f0b4b4"

PANEL_W   = 100
_BTN_SZ   = 46
# 图标绘制裁剪区：按钮内去掉 1px 边框后铺满
_ICON_INNER = max(1, _BTN_SZ - 2)
_COLS     = 2
_THUMB_SZ = 46

# ─── 通用小部件 ─────────────────────────────────────────────────────────────

class _HLine(QFrame):
    def __init__(self, p=None):
        super().__init__(p)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(f"color:{_BORD};")

def _mk_scroll():
    s = QScrollArea(); s.setWidgetResizable(True)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    s.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    s.setStyleSheet("""QScrollArea{border:none;background:transparent;}
        QScrollBar:vertical{background:#f0f2f5;width:5px;border-radius:2px;}
        QScrollBar::handle:vertical{background:#c0c4cc;border-radius:2px;min-height:16px;}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}""")
    return s

def _sec_lbl(text):
    l = QLabel(text)
    l.setStyleSheet(f"QLabel{{background:{_GRP};color:{_BLUE};font-size:11px;"
                    f"padding:3px 5px;border-bottom:1px solid {_BORD};}}")
    l.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return l

# ─── 图标网格 ────────────────────────────────────────────────────────────────

class _IconGrid(QWidget):
    icon_clicked = Signal(int, str)
    def __init__(self, icon_dir, parent=None):
        super().__init__(parent)
        self._icon_dir = icon_dir
        self._grp = QButtonGroup(self); self._grp.setExclusive(True)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(2,2,2,2); self._grid.setSpacing(2)
        self._build()

    def _build(self):
        paths = _load_icon_files(self._icon_dir)
        paths = paths[:22] if paths else [""] * 22
        while len(paths) < 22:
            paths.append("")
        for slot_idx, fname, _disp in _PANEL_ICON_SLOTS:
            pf = _panel_icon_file_path(self._icon_dir, fname)
            if pf and slot_idx < len(paths):
                paths[slot_idx] = pf
        for idx, path in enumerate(paths):
            btn = self._make_btn(idx, path)
            self._grid.addWidget(btn, *divmod(idx, _COLS))

    def _make_btn(self, idx, path):
        num = f"{idx+1:02d}"
        btn = QPushButton(); btn.setCheckable(True); btn.setFixedSize(_BTN_SZ,_BTN_SZ)
        disp = _panel_display_name_for_path(path) if path else None
        if disp:
            tip = disp
        elif path:
            tip = f"[{num}] {os.path.basename(path)}"
        else:
            tip = f"[{num}]"
        btn.setToolTip(tip)
        btn.setStyleSheet(f"""QPushButton{{background:{_WHITE};border:1px solid {_BORD};
            border-radius:3px;padding:0;}}
            QPushButton:hover{{background:#e8f4ff;border-color:{_BLUE};}}
            QPushButton:checked{{background:#d0e8ff;border:2px solid {_BLUE};}}""")
        btn.clicked.connect(lambda _=False,i=idx,p=path: self.icon_clicked.emit(i,p))
        inner = _ICON_INNER
        if path and os.path.isfile(path):
            raw = QPixmap(path).scaled(
                inner,
                inner,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            raw = self._placeholder(inner)
        btn.setIcon(QIcon(raw))
        btn.setIconSize(QSize(inner, inner))
        self._grp.addButton(btn, idx)
        return btn

    @staticmethod
    def _placeholder(side: int):
        pix = QPixmap(side, side)
        pix.fill(QColor("#e4e7ed"))
        return pix

    def reload(self):
        for btn in self._grp.buttons():
            self._grp.removeButton(btn); btn.deleteLater()
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._build()

# ─── 模型缩略图条目 ──────────────────────────────────────────────────────────

class _ModelItem(QWidget):
    clicked = Signal(str, str)
    def __init__(self, name, mod_path, thumb_path, even=True, parent=None):
        super().__init__(parent)
        self._name=name; self._mod=mod_path; self._selected=False; self._even=even
        self.setFixedHeight(_THUMB_SZ+10)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self._bg(False,False)
        lay = QHBoxLayout(self); lay.setContentsMargins(4,3,4,3); lay.setSpacing(6)
        t = QLabel(); t.setFixedSize(_THUMB_SZ,_THUMB_SZ)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if thumb_path and os.path.isfile(thumb_path):
            pix = QPixmap(thumb_path).scaled(_THUMB_SZ-2,_THUMB_SZ-2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            t.setPixmap(pix)
            t.setStyleSheet(f"border:1px solid {_BORD};border-radius:2px;background:#fff;")
        else:
            t.setText("□"); t.setStyleSheet(f"border:1px solid {_BORD};border-radius:2px;"
                f"background:#e4e7ed;color:{_GRAY};font-size:16px;")
        lay.addWidget(t)
        n = QLabel(name); n.setWordWrap(True)
        n.setStyleSheet(f"color:{_TEXT};font-size:10px;background:transparent;")
        n.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(n,1)

    def _bg(self,hover,sel):
        if sel:   bg="#d0e8ff"; ex=f"border-left:2px solid {_BLUE};"
        elif hover: bg="#e8f4ff"; ex=""
        else: bg=_WHITE if self._even else _ODD; ex=""
        self.setStyleSheet(f"_ModelItem{{background:{bg};{ex}border-bottom:1px solid #ebebeb;}}")

    def enterEvent(self,e):
        if not self._selected: self._bg(True,False)
    def leaveEvent(self,e): self._bg(False,self._selected)
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._selected=True; self._bg(False,True)
            self.clicked.emit(self._name,self._mod)

class _GroupSection(QWidget):
    item_clicked = Signal(str,str)
    def __init__(self,gname,items,parent=None):
        super().__init__(parent)
        self._expanded=True
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self._hdr = QPushButton(f"▼  {gname}")
        self._hdr.setStyleSheet(f"""QPushButton{{background:{_GRP};border:none;
            border-top:1px solid {_BORD};border-bottom:1px solid {_BORD};
            color:{_BLUE};font-size:11px;font-weight:bold;
            text-align:left;padding:3px 6px;min-height:22px;}}
            QPushButton:hover{{background:#d8e6f5;}}""")
        self._hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hdr.clicked.connect(self._toggle); lay.addWidget(self._hdr)
        self._body=QWidget(); bl=QVBoxLayout(self._body)
        bl.setContentsMargins(0,0,0,0); bl.setSpacing(0)
        for i,(name,mod,thumb) in enumerate(items):
            mi=_ModelItem(name,mod,thumb,even=(i%2==0))
            mi.clicked.connect(self.item_clicked); bl.addWidget(mi)
        lay.addWidget(self._body)

    def _toggle(self):
        self._expanded=not self._expanded
        self._body.setVisible(self._expanded)
        self._hdr.setText(("▼" if self._expanded else "▶")+self._hdr.text()[1:])

# ─── 主面板：CabinetAssembler ─────────────────────────────────────────────────

class CabinetAssembler(QWidget):
    """组件库面板：通用组件（22 宫格）+ 常用部件 + 隐藏选项。

    与 `CabinetPropertyPanel` 在画布右缘并排，中间无留白。
    """
    PANEL_WIDTH = PANEL_W

    sig_icon_clicked     = Signal(int, str)
    sig_template_clicked = Signal(str, str)

    def __init__(self, icon_dir="", parent=None):
        super().__init__(parent)
        self._icon_dir = icon_dir or _resolve_icon_dir()
        self._tpl_dir  = _resolve_templates_dir()
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"CabinetAssembler{{background:{_BG};"
            f"border-left:1px solid {_BORD};border-right:1px solid {_BORD};}}")
        sh = QGraphicsDropShadowEffect(self)
        # 仅用轻微下垂阴影，避免水平 offset 在贴邻属性面板时形成视觉缝隙
        sh.setBlurRadius(12)
        sh.setOffset(0, 3)
        sh.setColor(QColor(0, 0, 0, 36))
        self.setGraphicsEffect(sh)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # ── 可滚动区：通用组件 + 常用部件 ──
        scroll = _mk_scroll()
        inner = QWidget(); inner.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(inner); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        lay.addWidget(_sec_lbl("▼ 通用组件"))
        self._icon_grid = _IconGrid(self._icon_dir)
        self._icon_grid.icon_clicked.connect(lambda i,p: self.sig_icon_clicked.emit(i,p))
        lay.addWidget(self._icon_grid)

        lay.addWidget(_sec_lbl("▼ 常用部件"))
        groups = _scan_templates(self._tpl_dir)
        if groups:
            for gname, items in groups:
                sec = _GroupSection(gname, items)
                sec.item_clicked.connect(self._on_tpl)
                lay.addWidget(sec)
        else:
            tip = QLabel("（暂无模板）")
            tip.setStyleSheet(f"color:{_GRAY};font-size:10px;padding:8px;")
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(tip)

        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # ── 固定底部：复选框（不随内容滚动）──
        outer.addWidget(_HLine())
        cbw = QWidget(); cbw.setStyleSheet(f"background:{_BG};")
        cbl = QVBoxLayout(cbw); cbl.setContentsMargins(5,4,4,6); cbl.setSpacing(3)
        self._checkboxes: dict[str, QCheckBox] = {}
        for label in ["隐藏分割面","隐藏门板","隐藏柜体","六面设计"]:
            cb = QCheckBox(label); cb.setChecked(False)
            cb.setStyleSheet(f"""QCheckBox{{color:{_TEXT};font-size:11px;spacing:4px;}}
                QCheckBox::indicator{{width:12px;height:12px;
                    border:1px solid {_BORD};border-radius:2px;background:white;}}
                QCheckBox::indicator:checked{{background:{_BLUE};border-color:{_BLUE};}}""")
            cbl.addWidget(cb); self._checkboxes[label] = cb
        outer.addWidget(cbw)

    def _on_tpl(self, name, path):
        self.sig_template_clicked.emit(name, path)

    # ── 公开 API ──────────────────────────────────────────────────────────────

    def reload_icons(self, icon_dir=""):
        if icon_dir:
            self._icon_dir = icon_dir
            self._icon_grid._icon_dir = icon_dir
        self._icon_grid.reload()

    def get_visibility(self):
        return {k: cb.isChecked() for k, cb in self._checkboxes.items()}


# ─── 独立预览 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow, QHBoxLayout
    app = QApplication(sys.argv); app.setStyle("Fusion")
    win = QMainWindow(); win.setWindowTitle("CabinetAssembler 预览"); win.resize(200, 780)
    central = QWidget(); hl = QHBoxLayout(central)
    hl.setContentsMargins(0,0,0,0); hl.setSpacing(0)
    panel = CabinetAssembler()
    panel.sig_icon_clicked.connect(lambda i,p: print(f"[图标{i+1:02d}] {p}"))
    panel.sig_template_clicked.connect(lambda n,p: print(f"[模板] {n}"))
    hl.addWidget(panel)
    canvas = QWidget(); canvas.setStyleSheet("background:#2c3e50;")
    hl.addWidget(canvas, 1)
    win.setCentralWidget(central); win.show()
    import sys; sys.exit(app.exec())
