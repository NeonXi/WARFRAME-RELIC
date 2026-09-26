"""
[L4] CyberLogViewer — 赛博风格日志输出面板

依赖: PySide6, tokens/, mixins/cyber_widget_mixin.py
职责: 显示程序运行日志、支持清空操作

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须显式调用目标基类
- ✗ 禁止 paintEvent 漏 super() → 文字/光标会失效
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止在本控件内直接绑定 logging.Handler → 走 append_message() 接口
- ✗ 禁止调 Service / 发网络请求 / 写文件

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QScrollArea,
)
from PySide6.QtGui import QColor, QFont, QTextCursor, QPainter, QPen, QBrush
from PySide6.QtCore import Qt

from core.widgets.base import CyberWidgetMixin


# 日志级别配色映射（从 token 获取，此处为 fallback）
LOG_COLORS = {
    "ok":    "alias.log.ok",
    "warn":  "alias.log.warn",
    "error": "alias.log.error",
    "info":  "alias.log.info",
}

# 日志级别前缀
LOG_PREFIXES = {
    "ok":    "[OK]",
    "warn":  "[!]",
    "error": "[X]",
    "info":  "  ",
}


class CyberLogViewer(CyberWidgetMixin, QFrame):
    """赛博风格日志输出面板。

    Attributes:
        title: 面板标题
        max_lines: 最大保留行数（0=不限制）
        auto_scroll: 是否自动滚动到底部
    """

    def __init__(
        self,
        title: str = "操作日志",
        *,
        max_lines: int = 500,
        auto_scroll: bool = True,
        parent: Optional[QWidget] = None,
    ):
        QFrame.__init__(self, parent)
        CyberWidgetMixin.__init__(self)

        self._title = title
        self._max_lines = max_lines
        self._auto_scroll = auto_scroll
        self._log_count = 0

        # 布局
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 标题栏（含清空按钮）
        self._build_header()

        # 日志文本区
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._apply_text_style()
        self._layout.addWidget(self._text_edit, stretch=1)

        # 样式
        self.setObjectName("CyberLogViewer")

        # 订阅主题切换:重建 header 文字色/按钮样式 + 文本区 QSS
        self._cyber_subscribe_theme()
        self.cyber_refresh_style()

    def cyber_refresh_style(self) -> None:
        """重建标题栏文字色、清空按钮样式、日志文本区 QSS。"""
        self._apply_text_style()
        # 标题文字
        if getattr(self, "_title_lbl", None) is not None:
            title_color = self.token_color("alias.text.disabled")
            self._title_lbl.setStyleSheet(
                f"color: {title_color.name()}; background: transparent; border: none;"
            )
        # 计数标签
        if self._count_label is not None:
            self._count_label.setStyleSheet(
                f"color: {self.token_color('alias.text.disabled').name()}; "
                f"font-size: {self.space('font.micro', 10)}px; "
                f"background: transparent; border: none;"
            )
        # 清空按钮
        if getattr(self, "_clear_btn", None) is not None:
            btn_text = self.token_color("alias.text.disabled")
            btn_hover = self.token_color("alias.accent.secondary")
            _white = self.token_color("text.primary")
            self._clear_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {btn_text.name()};
                    background: transparent;
                    border: 1px solid {self.token_color('border.subtle').name()};
                    border-radius: {self.space('corner.xs', 4)}px;
                    font-size: {self.space('font.xs', 11)}px;
                    padding: {self.space('spacing.none', 2)}px {self.space('spacing.sm', 8)}px;
                }}
                QPushButton:hover {{
                    color: {btn_hover.name()};
                    border-color: {btn_hover.name()};
                }}
                QPushButton:pressed {{
                    background: rgba({_white.red()},{_white.green()},{_white.blue()},0.05);
                }}
            """)

    # ── 构建 ──

    def _build_header(self) -> None:
        """构建标题栏。"""
        header = QWidget()
        header.setFixedHeight(32)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(12, 0, 8, 0)
        hdr_layout.setSpacing(8)

        # 标题文字
        self._title_lbl = QLabel(self._title)
        title_font = self._title_lbl.font()
        title_font.setPointSize(self.space("font.xs", 11))
        title_font.setBold(True)
        self._title_lbl.setFont(title_font)
        title_color = self.token_color("alias.text.disabled")
        self._title_lbl.setStyleSheet(f"color: {title_color.name()}; background: transparent; border: none;")
        hdr_layout.addWidget(self._title_lbl)

        # 日志计数
        self._count_label = QLabel("0 条")
        self._count_label.setStyleSheet(f"color: {self.token_color('alias.text.disabled').name()}; font-size: {self.space('font.micro', 10)}px; background: transparent; border: none;")
        hdr_layout.addWidget(self._count_label)

        hdr_layout.addStretch()

        # 清空按钮
        self._clear_btn = QPushButton("清空")
        self._clear_btn.setFixedSize(48, self.space("height.btn_sm", 28))
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_text = self.token_color("alias.text.disabled")
        btn_hover = self.token_color("alias.accent.secondary")
        _white = self.token_color("text.primary")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                color: {btn_text.name()};
                background: transparent;
                border: 1px solid {self.token_color('border.subtle').name()};
                border-radius: {self.space('corner.xs', 4)}px;
                font-size: {self.space('font.xs', 11)}px;
                padding: {self.space('spacing.none', 2)}px {self.space('spacing.sm', 8)}px;
            }}
            QPushButton:hover {{
                color: {btn_hover.name()};
                border-color: {btn_hover.name()};
            }}
            QPushButton:pressed {{
                background: rgba({_white.red()},{_white.green()},{_white.blue()},0.05);
            }}
        """)
        self._clear_btn.clicked.connect(self.clear)
        hdr_layout.addWidget(self._clear_btn)

        self._layout.addWidget(header)

    def _apply_text_style(self) -> None:
        """应用日志文本区样式(沉浸黑色模式时背景覆写为纯黑)。"""
        # 背景:沉浸黑色模式时覆写为纯黑(QSS 字符串入口)
        bg = self._cyber_immersive_resolve_token_str("alias.bg.base", 1.0)
        text = self.token_color("alias.text.primary")
        border = self.token_color("alias.border.subtle")
        _accent = self.token_color("accent.secondary")
        _scroll_handle = self.token_color("border.subtle")
        _scroll_hover = self.token_color("neutral.dark")

        self._text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {bg};
                color: {text.name()};
                border: 1px solid {border.name()};
                border-radius: {self.space('corner.xs', 4)}px;
                font-family: "Consolas", "Microsoft YaHei", "Courier New", monospace;
                font-size: {self.space('font.sm', 12)}px;
                padding: {self.space('spacing.sm', 8)}px;
                selection-background-color: rgba({_accent.red()},{_accent.green()},{_accent.blue()},0.25);
                selection-color: {text.name()};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: {self.space('height.scrollbar', 8)}px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_scroll_handle.name()};
                border-radius: {self.space('corner.xs', 4)}px;
                min-height: {self.space('spacing.xxxl', 32)}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_scroll_hover.name()};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
                border: none;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

    # ── 公共接口 ──

    def add_log(
        self,
        level: str,
        message: str,
        source: str = "",
    ) -> None:
        """添加一条日志。

        Args:
            level: 日志级别 (ok / warn / error / info)
            message: 日志消息内容
            source: 来源标记（可选）
        """
        if level not in LOG_COLORS:
            level = "info"

        now = datetime.now().strftime("%H:%M:%S")
        color_token = LOG_COLORS[level]
        color = self.token_color(color_token).name()
        prefix = LOG_PREFIXES[level]

        # 来源标记
        dim_color = self.token_color("neutral.dark").name()
        src_html = f'<span style="color:{dim_color};">[{source}]</span>' if source else ""

        # 构建日志行 HTML
        html_line = (
            f'<span style="color:{dim_color};">[{now}]</span>'
            f'{src_html}'
            f' <span style="color:{color};font-weight:{"" if level == "info" else "bold"};">'
            f'{prefix} {self._escape_html(message)}</span>'
        )

        # 追加到文本区
        self._text_edit.append(html_line)
        self._log_count += 1
        self._update_count()

        # 自动滚动到底部
        if self._auto_scroll:
            scrollbar = self._text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        # 限制最大行数
        if self._max_lines > 0 and self._log_count > self._max_lines:
            self._trim_old_logs()

    def clear(self) -> None:
        """清空所有日志。"""
        self._text_edit.clear()
        self._log_count = 0
        self._update_count()

    def set_level_color(self, level: str, color_token: str) -> None:
        """自定义日志级别的颜色 token key。"""
        LOG_COLORS[level] = color_token

    @property
    def log_count(self) -> int:
        return self._log_count

    # ── 内部方法 ──

    def _update_count(self) -> None:
        """更新日志计数标签。"""
        self._count_label.setText(f"{self._log_count} 条")

    def _trim_old_logs(self) -> None:
        """裁剪超出限制的旧日志。"""
        doc = self._text_edit.document()
        while doc.blockCount() > self._max_lines:
            cursor = QTextCursor(doc.firstBlock())
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除换行符
            self._log_count -= 1
        self._update_count()

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符。"""
        return (
            text.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
        )

    # ── 绘制 ──

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        corner = self.space("components.panel.corner_size", 10)
        path = self._chamfered_path(self.rect(), corner, mode="all")

        # 背景(沉浸黑色模式时覆写 RGB,折减 alpha)
        opacity = float(self.token("components.panel.bg_opacity") or "0.92")
        bg_color = self._cyber_immersive_resolve_bg("components.panel.bg", opacity)
        painter.fillPath(path, QBrush(bg_color))

        # 边框
        border_color = self.token_color("components.panel.border")
        border_width = float(self.token("components.panel.border_width") or "1")
        painter.setPen(QPen(border_color, border_width))
        painter.drawPath(path)

        super().paintEvent(event)

    # ── 沉浸黑色模式 / 颜色预设切换刷新 ──

    def cyber_refresh_immersive_style(self) -> None:
        """沉浸模式 / 颜色预设变化时由 AppShell 调用,重设 QTextEdit 的 QSS。

        _apply_text_style 内的 background-color 走 helper,切换沉浸颜色模式
        后需要重新构造 QSS 才能应用新底色。
        """
        self._apply_text_style()
