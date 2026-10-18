"""
[L2] core.pages.placeholder_error_page — 页面初始化失败占位

═══════════════════════════════════════════════════════════════════════
归属层:    [L2] (core/pages/)
依赖:      core.pages.base_page, core.tokens
职责:      当 _create_page() 抛异常时,显示一个友好的错误占位页
═══════════════════════════════════════════════════════════════════════

设计动机:
  - 旧逻辑: _create_page 失败时 return None → register_pages 跳过此 nav_id
    → stack 里少了对应 scroll → 用户点导航 tab 报"页面未找到"
  - 新逻辑: 失败时返回本占位页 → stack 里有这个 page → 切到时能看到
    "为什么这个页面坏了",而不是"消失"在导航里
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QLabel, QFrame, QPushButton
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from core.pages.base_page import PageBase
from core.fonts import FONT_DISPLAY


class PlaceholderErrorPage(PageBase):
    """页面初始化失败占位。

    继承 PageBase 以便走完整的页面生命周期(on_enter/on_leave)
    和 stack 注册(page_id 可被 _page_index 找到)。
    """

    def __init__(self, nav_id: str, error: str, parent=None):
        # ── 在 super().__init__() 前声明 self.* 属性(基类会调 build_content)──
        self._nav_id = nav_id
        self._error = error
        # ★ 必须先设 page_id(基类的 page_id 是类属性 "" 默认值)
        #  否则 _page_index() 会因为 widget.page_id == '' 而匹配不上
        self.page_id = nav_id
        self.page_title = f"⚠ {nav_id} (错误)"
        self.page_icon = "nav_error"
        super().__init__(parent)

    def build_content(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName(f"placeholder_error_{self._nav_id}")
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(self._spacing("md", 12))

        # ── 标题:页面 ID ──
        title = QLabel(f"⚠ 页面 '{self._nav_id}' 初始化失败")
        title_font = QFont(FONT_DISPLAY, self._font_size("lg", 18), QFont.Weight.Bold)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._style(title, color="alias.semantic.danger")
        layout.addWidget(title)

        # ── 原因 ──
        err_label = QLabel(self._error)
        err_label.setWordWrap(True)
        err_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._style(err_label, color="text.secondary", font_size="sm")
        err_label.setMaximumWidth(640)
        layout.addWidget(err_label)

        # ── 提示 ──
        hint = QLabel("该页面已加入导航但无法正常显示。请检查:\n"
                      "  • 该页面的 import / 依赖是否完整\n"
                      "  • 该页面的 __init__ 是否缺 super().__init__()\n"
                      "  • 控制台堆栈可定位具体异常点")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        self._style(hint, color="text.tertiary", font_size="sm")
        hint.setMaximumWidth(640)
        layout.addWidget(hint)

        return frame
