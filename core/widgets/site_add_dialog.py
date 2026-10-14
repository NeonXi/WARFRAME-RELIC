"""
[L5] CyberSiteAddDialog — 添加常用网站对话框

继承: CyberWidgetMixin + QDialog
依赖: core.tokens(经 mixin), core.widgets.button/line_edit, PySide6
职责: 采集"网站名称 + 网址"两项输入，点击确定时回调注入的校验器；
      校验失败在框内红字提示且不关闭，成功才 accept。
信号: 无（exec() 返回 Accepted 后由调用方自行刷新列表）

分层说明:
    本控件不 import 任何 service。校验逻辑以 Callable 形式由页面注入，
    签名 (name, url) -> (ok, 可直接展示的错误文案)，因此 widgets 层
    不需要知道原因码/持久化细节。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from core.widgets.base import CyberWidgetMixin
from core.widgets.button import CyberButton
from core.widgets.line_edit import CyberLineEdit

# 对话框固定宽度（4 的倍数）
_DIALOG_WIDTH = 400
# 输入框高度（与全站 md 输入一致）
_INPUT_HEIGHT = 36
# 底部操作按钮宽
_BTN_OK_WIDTH = 96
_BTN_CANCEL_WIDTH = 80

# 校验器签名：(名称, 网址) -> (是否通过, 失败时的展示文案)
SiteValidator = Callable[[str, str], tuple[bool, str]]


class CyberSiteAddDialog(CyberWidgetMixin, QDialog):
    """添加网站模态对话框。

    Args:
        validator: 可选校验/落盘回调。返回 (False, 文案) 时对话框保持
            打开并显示文案；返回 (True, "") 时关闭并接受。
                     为 None 时仅做非空形态的最小校验。
        parent: 父窗口。
    """

    def __init__(
        self,
        validator: SiteValidator | None = None,
        parent: QWidget | None = None,
    ):
        QDialog.__init__(self, parent)
        self._validator = validator
        self._name = ""
        self._url = ""

        self.setWindowTitle(self.copy("sites.dlg_title", "添加网站"))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # 对话框底色（走 palette，不用 stylesheet，参照图片裁剪对话框）
        pal = self.palette()
        pal.setColor(
            QPalette.ColorRole.Window, self.token_color("alias.bg.raised")
        )
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        text_dim = self.token_color("text.tertiary")
        danger = self.token_color("semantic.danger", "brand.red")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── 名称 ──
        name_lbl = QLabel(self.copy("sites.dlg_name_label", "网站名称"))
        name_lbl.setStyleSheet(
            f"color: {text_dim.name()}; font-size: {self.space('font.xs', 11)}px;"
            " background: transparent; border: none;"
        )
        root.addWidget(name_lbl)

        self._name_edit = CyberLineEdit(
            placeholder=self.copy(
                "sites.dlg_name_ph", "例如：中文维基"
            )
        )
        self._name_edit.setFixedHeight(_INPUT_HEIGHT)
        root.addWidget(self._name_edit)

        # ── 网址 ──
        url_lbl = QLabel(self.copy("sites.dlg_url_label", "网址"))
        url_lbl.setStyleSheet(
            f"color: {text_dim.name()}; font-size: {self.space('font.xs', 11)}px;"
            " background: transparent; border: none;"
        )
        root.addWidget(url_lbl)

        self._url_edit = CyberLineEdit(
            placeholder=self.copy(
                "sites.dlg_url_ph", "例如：warframe.market（可省略 https://）"
            )
        )
        self._url_edit.setFixedHeight(_INPUT_HEIGHT)
        # 网址框回车 = 点确定；名称框回车跳到网址框
        self._name_edit.returnPressed.connect(self._url_edit.setFocus)
        self._url_edit.returnPressed.connect(self._try_accept)
        root.addWidget(self._url_edit)

        # ── 错误提示（平时隐藏，保留占位避免按钮跳动） ──
        self._error_lbl = QLabel("")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            f"color: {danger.name()}; font-size: {self.space('font.xs', 11)}px;"
            " background: transparent; border: none;"
        )
        self._error_lbl.setVisible(False)
        root.addWidget(self._error_lbl)

        # ── 底部操作 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        hint = QLabel(self.copy("sites.dlg_security_hint", "仅支持 http/https 链接"))
        hint.setStyleSheet(
            f"color: {text_dim.name()}; font-size: {self.space('font.micro', 10)}px;"
            " background: transparent; border: none;"
        )
        bottom.addWidget(hint)
        bottom.addStretch()

        ok_btn = CyberButton(self.copy("sites.dlg_ok", "添 加"), variant="solid")
        cancel_btn = CyberButton(
            self.copy("sites.dlg_cancel", "取 消"), variant="ghost"
        )
        ok_btn.setFixedWidth(_BTN_OK_WIDTH)
        cancel_btn.setFixedWidth(_BTN_CANCEL_WIDTH)
        ok_btn.clicked.connect(self._try_accept)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(ok_btn)
        bottom.addWidget(cancel_btn)
        root.addLayout(bottom)

        self.setFixedWidth(_DIALOG_WIDTH)
        self.adjustSize()
        self._name_edit.setFocus()

    # ════════════════════════════════════
    #  对外
    # ════════════════════════════════════

    def get_data(self) -> tuple[str, str]:
        """accept 后读取用户输入 (名称原文, 网址原文)。"""
        return self._name, self._url

    # ════════════════════════════════════
    #  内部
    # ════════════════════════════════════

    def _try_accept(self) -> None:
        """点确定/网址框回车：校验通过才关闭，否则就地显示错误。"""
        name = self._name_edit.text().strip()
        url = self._url_edit.text().strip()

        if not name:
            self._show_error(self.copy("sites.err_name_empty", "请填写网站名称"))
            self._name_edit.setFocus()
            return
        if not url:
            self._show_error(self.copy("sites.err_url_empty", "请填写网址"))
            self._url_edit.setFocus()
            return

        if self._validator is not None:
            ok, message = self._validator(name, url)
            if not ok:
                self._show_error(message)
                return

        self._name, self._url = name, url
        self.accept()

    def _show_error(self, text: str) -> None:
        self._error_lbl.setText(text)
        self._error_lbl.setVisible(True)
        self.adjustSize()
