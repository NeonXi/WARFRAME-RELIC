"""
遗物内容悬浮窗模块
- 在 overlay 上显示一个可拖动的悬浮窗，展示遗物部件详情
- 赛博朋克风格，半透明深色背景
"""

import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont, QColor, QPalette

from core.constants import (
    CYBER_YELLOW, CYBER_CYAN, CYBER_MAGENTA,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER,
    COLOR_VAULTED, COLOR_AVAILABLE,
)


class RelicTooltip(QWidget):
    """遗物内容悬浮窗 —— 显示识别到的遗物及其包含的部件。

    特点：
    - 无边框、置顶、半透明
    - 可拖动（拖标题栏）
    - 赛博朋克深色风格
    - 自动在屏幕右上角显示
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self._relic_data = []  # [{name, vaulted, parts: [{name, rarity, chance}]}, ...]
        self._part_labels = []
        self._setup_ui()
        self.hide()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(340)

        # 主容器
        self._container = QFrame(self)
        self._container.setObjectName("tooltipContainer")
        self._container.setStyleSheet(f"""
            QFrame#tooltipContainer {{
                background-color: rgba(10, 10, 30, 235);
                border: 2px solid {CYBER_YELLOW};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 标题栏（可拖动）----
        self._title_bar = QFrame()
        self._title_bar.setFixedHeight(36)
        self._title_bar.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 30, 60, 240);
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border-bottom: 1px solid {CYBER_YELLOW};
            }}
        """)
        title_layout = QVBoxLayout(self._title_bar)
        title_layout.setContentsMargins(12, 0, 12, 0)
        self._title_label = QLabel("◈ 核桃内容")
        self._title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {CYBER_YELLOW}; background: transparent; border: none;")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        title_layout.addWidget(self._title_label)
        layout.addWidget(self._title_bar)

        # ---- 内容滚动区域 ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: rgba(20, 20, 40, 200);
                width: 6px;
                border-radius: 3px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {CYBER_YELLOW};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(10, 8, 10, 8)
        self._content_layout.setSpacing(6)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content_widget)
        layout.addWidget(self._scroll, 1)

        # ---- 底部提示 ----
        self._hint_label = QLabel("右键点击覆盖层可关闭")
        self._hint_label.setFont(QFont("Microsoft YaHei", 9))
        self._hint_label.setStyleSheet(
            f"color: rgba(150, 150, 180, 180); background: transparent; "
            f"border-top: 1px solid rgba(100, 100, 150, 80); padding: 4px 12px;"
        )
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint_label)

        # 设置整体大小
        self._container.setGeometry(0, 0, 340, 100)
        self.setFixedSize(340, 100)

    # ========== 拖动支持 ==========

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 只在标题栏区域可拖动
            if event.position().y() <= self._title_bar.height():
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            event.accept()

    # ========== 数据填充 ==========

    def show_relics(self, relic_data: list[dict]):
        """显示遗物内容列表。

        Args:
            relic_data: [{name, vaulted, parts: [{name, rarity, chance}]}, ...]
                       不包含 parts 或 parts 为空的不显示内容区
        """
        self._relic_data = relic_data

        # 清除旧内容
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._part_labels = []

        total_parts = 0
        for relic in relic_data:
            parts = relic.get('parts', [])
            name = relic.get('name', '?')
            vaulted = relic.get('vaulted', False)

            # ---- 遗物标题行 ----
            status_color = COLOR_VAULTED if vaulted else COLOR_AVAILABLE
            status_text = "已入库" if not vaulted else "可获取"
            title_label = QLabel(f"◆ {name}  <span style='color:{status_color};font-size:10px;'>[{status_text}]</span>")
            title_label.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
            title_label.setStyleSheet(
                f"color: {CYBER_CYAN}; background: transparent; border: none; padding: 2px 0;"
            )
            title_label.setTextFormat(Qt.TextFormat.RichText)
            self._content_layout.addWidget(title_label)

            if parts:
                sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))
                chances = sorted(set(p.get('chance', 0) for p in sorted_parts))

                # 概率 → 颜色映射
                if len(chances) >= 3:
                    chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
                elif len(chances) == 2:
                    chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_COPPER}
                else:
                    chance_to_color = {chances[0]: COLOR_SILVER}

                for p in sorted_parts:
                    ch = p.get('chance', 0)
                    clr = chance_to_color.get(ch, COLOR_SILVER)
                    prefix = "●" if ch == chances[0] else ("○" if len(chances) > 1 and ch == chances[-1] else "◈")
                    rarity = p.get('rarity', '')

                    part_label = QLabel(
                        f"  {prefix} <span style='color:{clr};'>{self._escape(p['name'])}</span>"
                        f"  <span style='color:#6677AA; font-size:9px;'>{rarity} ({ch:.1f}%)</span>"
                    )
                    part_label.setFont(QFont("Microsoft YaHei", 10))
                    part_label.setStyleSheet("background: transparent; border: none; padding: 1px 0;")
                    part_label.setTextFormat(Qt.TextFormat.RichText)
                    self._content_layout.addWidget(part_label)
                    self._part_labels.append(part_label)
                    total_parts += 1
            else:
                no_part = QLabel("  (无部件数据)")
                no_part.setFont(QFont("Microsoft YaHei", 9))
                no_part.setStyleSheet(
                    f"color: rgba(150, 150, 180, 150); background: transparent; border: none; font-style: italic;"
                )
                self._content_layout.addWidget(no_part)

            # 分隔线
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"background-color: rgba(100, 100, 150, 60); max-height: 1px; margin: 2px 0;")
            self._content_layout.addWidget(sep)

        self._content_layout.addStretch()

        # 更新标题
        self._title_label.setText(f"◈ 核桃内容 ({len(relic_data)}个遗物, {total_parts}个部件)")

        # 计算合适的高度
        self._adjust_size()

        # 显示
        self.show()
        self.raise_()

    def _adjust_size(self):
        """根据内容调整窗口大小。"""
        # 计算内容高度
        content_hint = self._content_widget.sizeHint()
        content_height = max(content_hint.height(), 80)
        # 标题栏 + 内容 + 底部提示 + 边框
        total_height = 36 + content_height + 30 + 4
        # 限制最大高度（屏幕的 80%）
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            max_h = int(screen.geometry().height() * 0.7)
            total_height = min(total_height, max_h)

        self.setFixedSize(340, total_height)
        self._container.setGeometry(0, 0, 340, total_height)

        # 默认定位在屏幕右侧偏上
        if screen:
            screen_geom = screen.geometry()
            x = screen_geom.right() - 360  # 留 20px 边距
            y = screen_geom.top() + 80
            self.move(x, y)

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# ============================================================
# 全局单例
# ============================================================
_tooltip_instance: RelicTooltip | None = None


def get_tooltip() -> RelicTooltip:
    """获取全局悬浮窗单例。"""
    global _tooltip_instance
    if _tooltip_instance is None:
        _tooltip_instance = RelicTooltip()
    return _tooltip_instance


def hide_tooltip():
    """隐藏悬浮窗。"""
    global _tooltip_instance
    if _tooltip_instance:
        _tooltip_instance.hide()
