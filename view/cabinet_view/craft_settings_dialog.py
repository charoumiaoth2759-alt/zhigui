# -*- coding: utf-8 -*-
"""工艺设置对话框 —— craft_settings_dialog.py

收起态（参考图2）:
  标题栏
  三Tab（左栏=分布数量+单选  |  右栏=组件名称/材料/厚度/旋转）
  分隔线
  底部行: [▽] [工字图] 后缩□ 前缩□   □添加为空间分割面  □允许跨界碰撞出孔   [添 加]
           ↑折叠按钮紧贴在后缩左边（工字图和后缩之间）

展开态（参考图1）:
  在底部行下方追加展开区:
    封边减尺  前□ 后□ 左□ 右□  （四个下拉）
    孔槽模板  [下拉]  [选择*.kw]
    孔位方向  ○朝上 ●朝下 ○默认    宽度收缩 □
    孔槽连接  □前 □后 ☑左 ☑右     长度收缩 □
    组件条件变化  [空白文本区]
    产品附加参数  [+][-]
      参数名称 | 选项(选项1/选项2/...)
      [空白区]
    底部灰条: □展开常驻   [清除默认设置] [存为默认设置]
"""

from __future__ import annotations
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox,
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QTabWidget,
    QVBoxLayout, QWidget,
)

# ─── 颜色 ────────────────────────────────────────────────────────────────────
_TITLE_BG = "#2c3e50"
_BG       = "#f0f0f0"
_BORD     = "#b0b0b0"
_TEXT     = "#222222"
_HDR      = "#e0e0e0"
_H        = 22   # 控件标准高

_COMBO_SS = (
    "QComboBox{font-size:12px;border:1px solid #aaa;border-radius:1px;"
    "padding:0 3px;background:#fff;height:22px;}"
    "QComboBox:focus{border-color:#2c3e50;}"
    "QComboBox::drop-down{border:none;width:14px;}"
)
_LE_SS = (
    "QLineEdit{font-size:12px;border:1px solid #aaa;border-radius:1px;"
    "padding:0 4px;background:#fff;height:22px;}"
    "QLineEdit:focus{border-color:#2c3e50;}"
)
_CB_SS = (
    "QCheckBox{font-size:12px;color:#222;spacing:4px;}"
    "QCheckBox::indicator{width:12px;height:12px;"
    "border:1px solid #aaa;border-radius:2px;background:#fff;}"
    "QCheckBox::indicator:checked{background:#1a6fc4;border-color:#1a6fc4;}"
)
_RB_SS  = "QRadioButton{font-size:12px;color:#222;spacing:4px;}"
_BTN_SS = (
    "QPushButton{font-size:12px;border:1px solid #aaa;border-radius:2px;"
    "background:#e8e8e8;padding:0 8px;}"
    "QPushButton:hover{background:#d0d0d0;}"
)

# ─── 工厂 ────────────────────────────────────────────────────────────────────

class _HLine(QFrame):
    def __init__(self, p=None):
        super().__init__(p)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setFixedHeight(1)
        self.setStyleSheet(f"color:{_BORD};")

class _VLine(QFrame):
    def __init__(self, p=None):
        super().__init__(p)
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setFixedWidth(1)
        self.setStyleSheet(f"color:{_BORD};")

def L(text, w=0, color=_TEXT, bold=False):
    l = QLabel(text)
    if w: l.setFixedWidth(w)
    b = "font-weight:bold;" if bold else ""
    l.setStyleSheet(f"font-size:12px;color:{color};background:transparent;{b}")
    return l

def C(items, w=80):
    c = QComboBox(); c.addItems(items); c.setFixedWidth(w)
    c.setStyleSheet(_COMBO_SS); return c

def E(text="", w=50):
    e = QLineEdit(text); e.setFixedWidth(w); e.setFixedHeight(_H)
    e.setStyleSheet(_LE_SS); return e

def CB(text, checked=False):
    c = QCheckBox(text); c.setChecked(checked)
    c.setStyleSheet(_CB_SS); return c

def RB(text, checked=False):
    r = QRadioButton(text); r.setChecked(checked)
    r.setStyleSheet(_RB_SS); return r

def HR(*ws, sp=5, m=(0,2,0,2)):
    lay = QHBoxLayout(); lay.setContentsMargins(*m); lay.setSpacing(sp)
    for w in ws:
        if w is None: lay.addStretch(1)
        elif isinstance(w, int): lay.addSpacing(w)
        else: lay.addWidget(w)
    return lay

# ─── 标题栏 ──────────────────────────────────────────────────────────────────

class _TitleBar(QWidget):
    def __init__(self, title, dlg):
        super().__init__(dlg); self._dlg = dlg
        self.setFixedHeight(26)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"_TitleBar{{background-color:{_TITLE_BG};}}")
        lay = QHBoxLayout(self); lay.setContentsMargins(8,0,4,0); lay.setSpacing(0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color:#fff;font-size:12px;font-weight:bold;background:transparent;")
        lay.addWidget(lbl); lay.addStretch(1)
        x = QPushButton("✕"); x.setFixedSize(18,18)
        x.setStyleSheet(
            "QPushButton{background:#c0392b;border:1px solid #8e2019;"
            "border-radius:2px;color:#fff;font-size:10px;}"
            "QPushButton:hover{background:#e74c3c;}")
        x.clicked.connect(dlg.reject); lay.addWidget(x)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._d = e.globalPosition().toPoint() - self._dlg.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and hasattr(self,"_d"):
            self._dlg.move(e.globalPosition().toPoint() - self._d)
    def mouseReleaseEvent(self, e): self._d = None

# ─── Tab 左栏：分布控件 ───────────────────────────────────────────────────────

def _left_col(mode) -> QWidget:
    w = QWidget(); w.setStyleSheet(f"background:{_BG};")
    v = QVBoxLayout(w); v.setContentsMargins(8,8,6,6); v.setSpacing(4)

    r = QHBoxLayout(); r.setSpacing(4); r.setContentsMargins(0,0,0,0)
    r.addWidget(L("分布数量",52)); r.addWidget(C(["1","2","3","4","5"],76)); r.addStretch(1)
    v.addLayout(r)

    rg = QButtonGroup(w)
    rb0 = RB("分布", True); rg.addButton(rb0)
    ratio = L("1:1", color="#666")
    dr = QHBoxLayout(); dr.setSpacing(4); dr.setContentsMargins(0,0,0,0)
    dr.addWidget(rb0); dr.addWidget(ratio); dr.addStretch(1); v.addLayout(dr)

    ab = ("靠下","靠上") if mode=="pingban" else ("靠前","靠后")
    for t in ab:
        rb = RB(t); rg.addButton(rb)
        rr = QHBoxLayout(); rr.setSpacing(4); rr.setContentsMargins(0,0,0,0)
        rr.addWidget(rb); rr.addStretch(1); v.addLayout(rr)

    v.addStretch(1)
    return w

# ─── Tab 右栏：组件属性 ──────────────────────────────────────────────────────

def _right_col(mode) -> QWidget:
    w = QWidget(); w.setStyleSheet(f"background:{_BG};")
    v = QVBoxLayout(w); v.setContentsMargins(6,8,8,6); v.setSpacing(5)

    nm = "封板挡板" if mode=="beiban" else "固层"
    v.addLayout(HR(L("组件名称",52), C([nm,"固层","活层","背板"],118)))
    v.addLayout(HR(L("组件材料",52), C(["柜体颜色","白色","黑色","原木"],118)))

    tr = QHBoxLayout(); tr.setSpacing(4); tr.setContentsMargins(0,0,0,0)
    tr.addWidget(L("板材厚度",52)); tr.addWidget(C(["S","M","L","18","25"],44))
    tr.addWidget(CB("纹理翻转")); tr.addStretch(1); v.addLayout(tr)

    rr = QHBoxLayout(); rr.setSpacing(4); rr.setContentsMargins(0,0,0,0)
    rr.addWidget(L("旋转角度",52)); rr.addWidget(E("",44))
    rr.addWidget(L("轴向",24)); rr.addWidget(C(["Z","X","Y"],38))
    rr.addStretch(1); v.addLayout(rr)

    v.addStretch(1)
    return w

# ─── Tab 页 ──────────────────────────────────────────────────────────────────

class _TabPage(QWidget):
    def __init__(self, mode, on_toggle, parent=None):
        super().__init__(parent)
        self._on_toggle = on_toggle
        self._expanded  = False
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # 上半：左右两栏
        cols = QHBoxLayout(); cols.setContentsMargins(0,0,0,0); cols.setSpacing(0)
        cols.addWidget(_left_col(mode), 42)
        cols.addWidget(_VLine())
        cols.addWidget(_right_col(mode), 58)
        root.addLayout(cols)
        root.addWidget(_HLine())

        # ── 底部行 ──────────────────────────────────────────────────────────
        # 布局: [工字图] [▽折叠] 后缩[E] 前缩[E]   [□添加空间] [□允许碰撞]  stretch  [添加]
        bot = QWidget(); bot.setStyleSheet(f"background:{_BG};")
        bl  = QHBoxLayout(bot); bl.setContentsMargins(8,5,8,6); bl.setSpacing(5)

        # 工字图（灰色方块）
        icon_w = QWidget(); icon_w.setFixedSize(30,30)
        icon_w.setStyleSheet("background:#c8c8c8;border:1px solid #aaa;border-radius:2px;")
        il = QLabel("工\n艺", icon_w)
        il.setAlignment(Qt.AlignmentFlag.AlignCenter)
        il.setGeometry(0,0,30,30)
        il.setStyleSheet("font-size:8px;color:#555;background:transparent;")
        bl.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignVCenter)

        # ▽ 折叠按钮（在工字图右侧、后缩左侧）
        self._fold_btn = QPushButton("▽")
        self._fold_btn.setFixedSize(14, 30)
        self._fold_btn.setStyleSheet(
            "QPushButton{font-size:8px;border:1px solid #bbb;border-radius:2px;"
            "background:#dce8f0;color:#2c3e50;padding:0;}"
            "QPushButton:hover{background:#aac8e0;}"
            "QPushButton:pressed{background:#2c3e50;color:#fff;}"
        )
        self._fold_btn.clicked.connect(self._toggle)
        bl.addWidget(self._fold_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        # 后缩 / 前缩
        sc = QVBoxLayout(); sc.setSpacing(3); sc.setContentsMargins(0,0,0,0)
        sc.addLayout(HR(L("后缩",28), E("",44)))
        sc.addLayout(HR(L("前缩",28), E("1",44)))
        bl.addLayout(sc)

        bl.addSpacing(8)

        # 两个复选框
        cc = QVBoxLayout(); cc.setSpacing(3); cc.setContentsMargins(0,0,0,0)
        cc.addWidget(CB("添加为空间分割面"))
        cc.addWidget(CB("允许跨界碰撞出孔"))
        bl.addLayout(cc)
        bl.addStretch(1)

        # 添加按钮
        self.add_btn = QPushButton("添 加")
        self.add_btn.setFixedSize(56,24)
        self.add_btn.setStyleSheet(
            "QPushButton{font-size:12px;border:1px solid #1a5fa0;"
            "border-radius:2px;background:#2c3e50;color:#fff;}"
            "QPushButton:hover{background:#354f62;}"
        )
        bl.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(bot)

    def _toggle(self):
        self._expanded = not self._expanded
        self._fold_btn.setText("△" if self._expanded else "▽")
        self._on_toggle(self._expanded)

    def sync(self, v: bool):
        self._expanded = v
        self._fold_btn.setText("△" if v else "▽")

# ─── 展开区（参考图1 下方内容）──────────────────────────────────────────────

def _make_expand() -> QWidget:
    w = QWidget(); w.setStyleSheet(f"background:{_BG};")
    root = QVBoxLayout(w); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

    # ── 封边减尺（前 后 左 右）────────────────────────────────────────────────
    s1 = QWidget()
    l1 = QVBoxLayout(s1); l1.setContentsMargins(10,6,10,5); l1.setSpacing(3)

    # 列标题
    hdr = QHBoxLayout(); hdr.setSpacing(2); hdr.setContentsMargins(0,0,0,0)
    hdr.addSpacing(64)
    for t in ("前","后","左","右"):
        lh = QLabel(t); lh.setFixedWidth(44)
        lh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lh.setStyleSheet("font-size:12px;color:#555;background:transparent;")
        hdr.addWidget(lh)
    hdr.addStretch(1); l1.addLayout(hdr)

    # 数值行（四个下拉）
    vr = QHBoxLayout(); vr.setSpacing(2); vr.setContentsMargins(0,0,0,0)
    vr.addWidget(L("封边减尺",64))
    for d in ("M","N","N","N"):
        cb = C(["M","N","0","1","2","3"], 44); cb.setCurrentText(d)
        vr.addWidget(cb)
    # 参考图1右侧还有几个小数值框
    for v in ("0","M","N","G"):
        vr.addWidget(E(v, 22))
    vr.addStretch(1); l1.addLayout(vr)
    root.addWidget(s1); root.addWidget(_HLine())

    # ── 孔槽模板 ──────────────────────────────────────────────────────────────
    s2 = QWidget()
    l2 = QVBoxLayout(s2); l2.setContentsMargins(10,6,10,5); l2.setSpacing(5)

    # 孔槽模板 下拉 + 选择*.kw
    tr = QHBoxLayout(); tr.setSpacing(6); tr.setContentsMargins(0,0,0,0)
    tr.addWidget(L("孔槽模板",56))
    tr.addWidget(C(["常规三合一","四合一","定制"],130))
    sel = QPushButton("选择 *.kw"); sel.setFixedHeight(_H); sel.setStyleSheet(_BTN_SS)
    tr.addWidget(sel); tr.addStretch(1); l2.addLayout(tr)

    # 孔位方向 + 宽度收缩
    dr = QHBoxLayout(); dr.setSpacing(6); dr.setContentsMargins(0,0,0,0)
    dr.addWidget(L("孔位方向",56))
    rg1 = QButtonGroup(s2)
    for t in ("朝上","朝下","默认"):
        rb = RB(t, t=="朝下"); rg1.addButton(rb); dr.addWidget(rb)
    dr.addStretch(1)
    dr.addWidget(L("宽度收缩",52)); dr.addWidget(E("0",36)); l2.addLayout(dr)

    # 孔槽连接 + 长度收缩
    lr = QHBoxLayout(); lr.setSpacing(6); lr.setContentsMargins(0,0,0,0)
    lr.addWidget(L("孔槽连接",56))
    for t,ck in (("前",False),("后",False),("左",True),("右",True)):
        lr.addWidget(CB(t,ck))
    lr.addStretch(1)
    lr.addWidget(L("长度收缩",52)); lr.addWidget(E("",36)); l2.addLayout(lr)
    root.addWidget(s2); root.addWidget(_HLine())

    # ── 组件条件变化 ──────────────────────────────────────────────────────────
    s3 = QWidget()
    l3 = QVBoxLayout(s3); l3.setContentsMargins(10,4,10,4); l3.setSpacing(3)
    l3.addWidget(L("组件条件变化", bold=True))
    area = QWidget(); area.setFixedHeight(52)
    area.setStyleSheet("background:#fff;border:1px solid #ccc;border-radius:2px;")
    l3.addWidget(area)
    root.addWidget(s3); root.addWidget(_HLine())

    # ── 产品附加参数 ──────────────────────────────────────────────────────────
    s4 = QWidget()
    l4 = QVBoxLayout(s4); l4.setContentsMargins(10,4,10,4); l4.setSpacing(3)

    eh = QHBoxLayout(); eh.setSpacing(4); eh.setContentsMargins(0,0,0,0)
    eh.addWidget(L("产品附加参数", bold=True))
    for sym in ("+","−"):
        b = QPushButton(sym); b.setFixedSize(18,18)
        b.setStyleSheet(
            "QPushButton{font-size:12px;border:1px solid #aaa;"
            "border-radius:2px;background:#e8e8e8;}"
            "QPushButton:hover{background:#d0d0d0;}")
        eh.addWidget(b)
    eh.addStretch(1); l4.addLayout(eh)

    # 表头
    th = QHBoxLayout(); th.setSpacing(0); th.setContentsMargins(0,0,0,0)
    for txt,tw in (("参数名称",110),("选项（选项1/选项2/…）",200)):
        t = QLabel(txt); t.setFixedWidth(tw); t.setFixedHeight(20)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(
            "font-size:11px;color:#555;background:#e0e0e0;border:1px solid #ccc;")
        th.addWidget(t)
    th.addStretch(1); l4.addLayout(th)

    blank = QWidget(); blank.setFixedHeight(38)
    blank.setStyleSheet("background:#fff;border:1px solid #ccc;")
    l4.addWidget(blank)
    root.addWidget(s4); root.addWidget(_HLine())

    # ── 底部灰条：展开常驻 / 清除默认设置 / 存为默认设置 ─────────────────────
    foot = QWidget(); foot.setStyleSheet(f"background:{_HDR};")
    foot.setFixedHeight(34)
    fl = QHBoxLayout(foot); fl.setContentsMargins(8,4,8,4); fl.setSpacing(6)
    fl.addWidget(CB("展开常驻"))
    fl.addStretch(1)
    for txt in ("清除默认设置","存为默认设置"):
        b = QPushButton(txt); b.setFixedHeight(24); b.setStyleSheet(_BTN_SS)
        fl.addWidget(b)
    root.addWidget(foot)
    return w

# ─── 主对话框 ────────────────────────────────────────────────────────────────

class CraftSettingsDialog(QDialog):
    """通用板件参数对话框。

    收起态 = 参考图2（左右两栏 + 底部行）
    展开态 = 参考图1（追加封边减尺/孔槽/条件/附加参数区）
    折叠按钮在底部行工字图右侧（后缩左侧）
    底部无「工艺设置」按钮
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"CraftSettingsDialog{{background:{_BG};border:1px solid {_BORD};}}"
        )
        self._expanded = False
        self._pages: list[_TabPage] = []
        self._build()
        self.setFixedWidth(420)

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        root.addWidget(_TitleBar("通用板件参数", self))

        # Tab
        tab = QTabWidget()
        tab.setStyleSheet(
            "QTabWidget::pane{border:none;background:#f0f0f0;}"
            "QTabBar::tab{background:#d8d8d8;color:#333;font-size:12px;"
            "padding:3px 12px;border:1px solid #b0b0b0;border-bottom:none;"
            "border-radius:3px 3px 0 0;margin-right:2px;}"
            "QTabBar::tab:selected{background:#f0f0f0;color:#2c3e50;font-weight:bold;}"
            "QTabBar::tab:hover:!selected{background:#e8e8e8;}"
        )
        for mode, label in (("pingban","平板类"),("celi","侧立类"),("beiban","背板类")):
            page = _TabPage(mode=mode, on_toggle=self._on_toggle)
            page.add_btn.clicked.connect(self.accept)
            self._pages.append(page)
            tab.addTab(page, label)
        tab.setCurrentIndex(2)
        root.addWidget(tab)

        # 展开区（默认隐藏）
        self._exp = _make_expand()
        self._exp.setVisible(False)
        root.addWidget(self._exp)

    def _on_toggle(self, expanded: bool):
        self._expanded = expanded
        for p in self._pages:
            p.sync(expanded)
        self._exp.setVisible(expanded)
        self.adjustSize()
        self.setFixedWidth(420)


# ─── 独立预览 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    dlg = CraftSettingsDialog()
    dlg.exec()
    sys.exit(0)