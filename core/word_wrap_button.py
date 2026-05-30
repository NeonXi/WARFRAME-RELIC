"""
WordWrapButton - 支持自动换行的 QPushButton 子类

PyQt6 的 QPushButton 不支持 setWordWrap，本子类通过重写 paintEvent，
用 QPainter.drawText + Qt.TextWordWrap 手动绘制文字来实现自动换行。

用法：直接替代 QPushButton，API 完全兼容。
"""

from PyQt6.QtWidgets import QPushButton, QStyleOptionButton, QStyle
from PyQt6.QtGui import QPainter, QPalette
from PyQt6.QtCore import Qt, QRect


class WordWrapButton(QPushButton):
    """支持自动换行的按钮。

    重写 paintEvent，在绘制背景和边框（由 QStyle 处理）之后，
    用 QPainter.drawText + TextWordWrap 手动绘制文字。
    这样长文案会自然折行，不会被截断。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._word_wrap = True

    def paintEvent(self, event):
        """自定义绘制：背景/边框交给 QStyle，文字手动换行绘制。"""
        if not self._word_wrap or not self.text():
            # 无文字或未启用换行时，回退到默认绘制
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ---- 绘制背景和边框（由 QStyle 处理，保持 QSS 兼容） ----
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        # 清除文字，让 QStyle 只画背景和边框，不画文字
        opt.text = ""
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, painter, self)

        # ---- 手动绘制换行文字 ----
        margin = 10  # 左右边距
        text_rect = QRect(
            self.rect().x() + margin,
            self.rect().y() + 4,
            self.rect().width() - 2 * margin,
            self.rect().height() - 8,
        )

        painter.setFont(self.font())
        # 使用当前按钮状态的颜色（通过 palette）
        if self.isEnabled():
            color = self.palette().color(QPalette.ColorRole.ButtonText)
        else:
            color = self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)
        painter.setPen(color)

        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.text(),
        )

        painter.end()

    def sizeHint(self):
        """返回默认推荐尺寸，配合 layout 使用。"""
        hint = super().sizeHint()
        # 至少 40px 高，保证两行文字 + padding
        if hint.height() < 40:
            hint.setHeight(40)
        return hint
