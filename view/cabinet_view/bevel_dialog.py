# -*- coding: utf-8 -*-
"""切角参数编辑对话框 —— bevel_dialog.py

点击主面板「柜子切角」（槽位19）时弹出。

布局（严格参照参考图）：
  标题栏左侧 "切角参数编辑"，居中红字提示，右侧 X 关闭
  ┌────────────────────────────────────────┐
  │ [示意图区 ~360px宽]  │  [属性表]        │
  │                      │  类型    [下拉]  │
  │  icons/shiyitu/      │  位置    [□]    │
  │  横梁.png / 立柱.png │  尺寸A   [□]    │
  │  / 纵梁.png / 斜切.png│  尺寸B   [□]   │
  │                      │  距边C   [□]    │
  │                      │  自动补板 [☑]   │
  │                      │  补板厚度  18   │
  │                      │  板A收缩  [□]  │
  │                      │  板B收缩  [□]  │
  │                      │  端头A收  [□]  │
  │                      │  端头B收  [□]  │
  └──────────────────────┴─────────────────┘
  底部按钮行：[添加↑] [删除↑]          [保存应用]

类型下拉项：横梁 / 立柱 / 纵梁 / 斜切
切换类型时左侧示意图对应切换：
  横梁 → 横梁.png   立柱 → 立柱.png
  纵梁 → 纵梁.png   斜切 → 斜切.png
图片路径：icons/shiyitu/<类型>.png
图片不存在时显示灰色占位。
"""

from __future__ import annotations
import os, sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog,
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

# ── 颜色常量 ──────────────────────────────────────────────────────────────────
_TITLE_BG = "#2c3e50"
_BG       = "#f0f0f0"
_BORD     = "#b8b8b8"
_TEXT     = "#222222"
_HDR      = "#e0e0e0"
_CTRL_H   = 22
_LBL_W    = 68

_LE_SS = (
    "QLineEdit{font-size:12px;border:1px solid #aaa;border-radius:1px;"
    "padding:0 4px;background:#fff;height:22px;}"
    "QLineEdit:focus{border-color:#2c3e50;}"
)
_COMBO_SS = (
    "QComboBox{font-size:12px;border:1px solid #aaa;border-radius:1px;"
    "padding:0 3px;background:#fff;height:22px;}"
    "QComboBox:focus{border-color:#2c3e50;}"
    "QComboBox::drop-down{border:none;width:16px;}"
)
_CB_SS = (
    "QCheckBox{font-size:12px;color:#222;spacing:4px;}"
    "QCheckBox::indicator{width:13px;height:13px;"
    "border:1px solid #aaa;border-radius:2px;background:#fff;}"
    "QCheckBox::indicator:checked{background:#1a6fc4;border-color:#1a6fc4;}"
)
_BTN_SS = (
    "QPushButton{font-size:12px;border:1px solid #aaa;border-radius:2px;"
    "background:#e8e8e8;padding:0 14px;height:26px;}"
    "QPushButton:hover{background:#d0d0d0;}"
    "QPushButton:pressed{background:#c0c0c0;}"
)
_BTN_SAVE_SS = (
    "QPushButton{font-size:12px;border:1px solid #1a5fa0;border-radius:2px;"
    "background:#2c3e50;color:#fff;padding:0 14px;height:26px;}"
    "QPushButton:hover{background:#354f62;}"
)

# ── 类型与对应图片文件名 ─────────────────────────────────────────────────────
_TYPES = ["横梁", "立柱", "纵梁", "斜切"]
_TYPE_IMG = {t: f"{t}.png" for t in _TYPES}


# ── 辅助 ─────────────────────────────────────────────────────────────────────

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


def _lbl(text: str, w: int = 0) -> QLabel:
    l = QLabel(text)
    if w:
        l.setFixedWidth(w)
    l.setStyleSheet(f"font-size:12px;color:{_TEXT};background:transparent;")
    return l


def _le(text: str = "", w: int = 120) -> QLineEdit:
    e = QLineEdit(text)
    e.setFixedWidth(w)
    e.setFixedHeight(_CTRL_H)
    e.setStyleSheet(_LE_SS)
    return e


def _prop_row(label: str, widget: QWidget) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 2, 0, 2)
    lay.setSpacing(6)
    lay.addWidget(_lbl(label, _LBL_W))
    lay.addWidget(widget)
    lay.addStretch(1)
    return lay


# ── 标题栏 ───────────────────────────────────────────────────────────────────

class _TitleBar(QWidget):
    def __init__(self, dlg: QDialog):
        super().__init__(dlg)
        self._dlg = dlg
        self.setFixedHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"_TitleBar{{background-color:{_TITLE_BG};}}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 6, 0)
        lay.setSpacing(0)

        # 左：标题
        title_lbl = QLabel("切角参数编辑")
        title_lbl.setStyleSheet(
            "color:#fff;font-size:13px;font-weight:bold;background:transparent;"
        )
        lay.addWidget(title_lbl)

        # 中：红字提示
        hint = QLabel("★★★ 建议柜子设计完整后再切角 ★★★")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color:#ff6b6b;font-size:12px;background:transparent;")
        lay.addWidget(hint, 1)

        # 右：关闭
        x = QPushButton("x")
        x.setFixedSize(20, 20)
        x.setStyleSheet(
            "QPushButton{background:#c0392b;border:1px solid #8e2019;"
            "border-radius:2px;color:#fff;font-size:11px;font-weight:bold;}"
            "QPushButton:hover{background:#e74c3c;}"
        )
        x.clicked.connect(dlg.reject)
        lay.addWidget(x)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._d = e.globalPosition().toPoint() - self._dlg.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_d"):
            self._dlg.move(e.globalPosition().toPoint() - self._d)

    def mouseReleaseEvent(self, e):
        self._d = None


# ── 示意图面板 ───────────────────────────────────────────────────────────────

class _ImagePanel(QWidget):
    """左侧示意图，随类型切换图片。"""

    _IMG_W = 360
    _IMG_H = 400

    def __init__(self, shiyitu_dir: str, parent=None):
        super().__init__(parent)
        self._dir = shiyitu_dir
        self.setFixedSize(self._IMG_W, self._IMG_H)
        self.setStyleSheet(f"background:#e8e8e8;border:none;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background:transparent;")
        lay.addWidget(self._img_lbl)

        self._load("横梁")

    def switch(self, type_name: str):
        self._load(type_name)

    def _load(self, type_name: str):
        fname  = _TYPE_IMG.get(type_name, f"{type_name}.png")
        path   = os.path.join(self._dir, fname) if self._dir else ""
        if path and os.path.isfile(path):
            pix = QPixmap(path).scaled(
                self._IMG_W - 4, self._IMG_H - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(pix)
            self._img_lbl.setText("")
        else:
            self._img_lbl.setPixmap(QPixmap())
            self._img_lbl.setText(f"[{type_name}]\n示意图")
            self._img_lbl.setStyleSheet(
                "background:transparent;color:#888;font-size:14px;"
            )


# ── 属性表面板 ───────────────────────────────────────────────────────────────

class _PropPanel(QWidget):
    """右侧属性表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{_BG};")
        self.setSizePolicy(
            __import__("PySide6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Policy.Expanding,
            __import__("PySide6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Policy.Expanding,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(2)

        # 类型下拉
        self._combo_type = QComboBox()
        self._combo_type.addItems(_TYPES)
        self._combo_type.setFixedWidth(130)
        self._combo_type.setStyleSheet(_COMBO_SS)
        root.addLayout(_prop_row("类型", self._combo_type))

        root.addWidget(_HLine())

        # 其他属性行
        self._le_pos   = _le()
        self._le_sizeA = _le()
        self._le_sizeB = _le()
        self._le_distC = _le()

        for label, widget in (
            ("位置",  self._le_pos),
            ("尺寸A", self._le_sizeA),
            ("尺寸B", self._le_sizeB),
            ("距边C", self._le_distC),
        ):
            root.addLayout(_prop_row(label, widget))

        root.addWidget(_HLine())

        # 自动补板（复选框）
        self._cb_auto = QCheckBox()
        self._cb_auto.setChecked(True)
        self._cb_auto.setStyleSheet(_CB_SS)
        root.addLayout(_prop_row("自动补板", self._cb_auto))

        # 补板厚度
        self._le_thick = _le("18", 60)
        root.addLayout(_prop_row("补板厚度", self._le_thick))

        root.addWidget(_HLine())

        # 收缩 / 端头
        self._le_shrinkA = _le()
        self._le_shrinkB = _le()
        self._le_endA    = _le()
        self._le_endB    = _le()

        for label, widget in (
            ("板A收缩",  self._le_shrinkA),
            ("板B收缩",  self._le_shrinkB),
            ("端头A收",  self._le_endA),
            ("端头B收",  self._le_endB),
        ):
            root.addLayout(_prop_row(label, widget))

        root.addStretch(1)

    def type_combo(self) -> QComboBox:
        return self._combo_type

    def get_values(self) -> dict:
        return {
            "type":    self._combo_type.currentText(),
            "pos":     self._le_pos.text(),
            "sizeA":   self._le_sizeA.text(),
            "sizeB":   self._le_sizeB.text(),
            "distC":   self._le_distC.text(),
            "auto":    self._cb_auto.isChecked(),
            "thick":   self._le_thick.text(),
            "shrinkA": self._le_shrinkA.text(),
            "shrinkB": self._le_shrinkB.text(),
            "endA":    self._le_endA.text(),
            "endB":    self._le_endB.text(),
        }


# ── 主对话框 ─────────────────────────────────────────────────────────────────

class BevelDialog(QDialog):
    """切角参数编辑对话框。

    参数
    ----
    icon_dir : str
        主程序 icons 目录，用于加载 icons/shiyitu/<类型>.png。
    """

    def __init__(self, icon_dir: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"BevelDialog{{background:{_BG};border:1px solid {_BORD};}}"
        )

        # shiyitu 目录
        shiyitu = os.path.join(icon_dir, "shiyitu") if icon_dir else ""

        self._build(shiyitu)
        self.setMinimumWidth(660)

    # ── 构建 UI ──────────────────────────────────────────────────────────────

    def _build(self, shiyitu_dir: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        root.addWidget(_TitleBar(self))

        # 主体：左图 + 竖线 + 右属性
        body = QWidget()
        body.setStyleSheet(f"background:{_BG};")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        self._img_panel  = _ImagePanel(shiyitu_dir)
        self._prop_panel = _PropPanel()

        bl.addWidget(self._img_panel)
        bl.addWidget(_VLine())
        bl.addWidget(self._prop_panel, 1)

        root.addWidget(body, 1)

        # 分隔线
        root.addWidget(_HLine())

        # 底部按钮行
        root.addWidget(self._build_footer())

        # 连接类型下拉 → 切换图片
        self._prop_panel.type_combo().currentTextChanged.connect(
            self._img_panel.switch
        )

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_HDR};")
        w.setFixedHeight(38)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(8)

        # 添加 / 删除
        add_btn = QPushButton("添加↑")
        add_btn.setStyleSheet(_BTN_SS)
        add_btn.clicked.connect(self._on_add)
        lay.addWidget(add_btn)

        del_btn = QPushButton("删除↑")
        del_btn.setStyleSheet(_BTN_SS)
        del_btn.clicked.connect(self._on_delete)
        lay.addWidget(del_btn)

        lay.addStretch(1)

        # 保存应用
        save_btn = QPushButton("保存应用")
        save_btn.setStyleSheet(_BTN_SAVE_SS)
        save_btn.clicked.connect(self._on_save)
        lay.addWidget(save_btn)

        return w

    # ── 按钮槽 ───────────────────────────────────────────────────────────────

    def _on_add(self):
        v = self._prop_panel.get_values()
        print(f"[切角] 添加：{v}")

    def _on_delete(self):
        print("[切角] 删除")

    def _on_save(self):
        v = self._prop_panel.get_values()
        print(f"[切角] 保存应用：{v}")
        self.accept()

    # ── 公开结果 ─────────────────────────────────────────────────────────────

    def get_result(self) -> dict:
        return self._prop_panel.get_values()


# ── 独立预览 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 自动查找项目 icons 目录
    here = os.path.dirname(os.path.abspath(__file__))
    icon_dir = ""
    cur = here
    for _ in range(8):
        c = os.path.join(cur, "icons")
        if os.path.isdir(c):
            icon_dir = c
            break
        cur = os.path.dirname(cur)

    dlg = BevelDialog(icon_dir=icon_dir)
    if dlg.exec():
        print("[切角] 结果：", dlg.get_result())
    sys.exit(0)
