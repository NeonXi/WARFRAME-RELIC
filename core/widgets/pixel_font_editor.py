"""
[L4] PixelFontEditor — 像素字体可视化编辑器(主题页内嵌 Panel)

归属层:    [L4] (core/widgets/)
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
           core.state.pixel_font (只读消费 + 调 save/reload,不直接读写 JSON)
           core.widgets.splash_screen (只读 _PIXEL_FONT 兼容层代理)
禁止依赖:  core.services/*, core.pages/*, data/
必读规范:  .trae/rules/开发规范.md §6.4

类清单:
  - _GridCell           单个可点击/拖拽的像素格
  - _GridContainer      鼠标拖拽绘制容器
  - _PreviewLabel       预览渲染(画当前 splash_text)
  - LetterPickerDialog  字母选择 + 插入位置弹窗
  - PixelFontEditorPanel 嵌入主题页的内嵌 Panel

数据流(2026-07-27 重构为 splash_text 驱动):
  启动:  state.pixel_font.get_pixel_font() -> 深拷贝到 self._font_data
        + state.get_splash_text() -> 字母按钮栏来源
  编辑:  self._font_data[row][col] = 0/1
  添加:  弹 LetterPickerDialog(字母 + 位置) -> 插入到 splash_text
  删除:  从 splash_text 移除当前字符(至少留 1 个)
  保存:  save_pixel_font(self._font_data, splash_text) + reload
  重置:  _DEFAULT_FONT[ch] -> 恢复 26 字母默认 art

设计:
  - 字母按钮栏只显示当前 splash_text 中的字符(按字串顺序),不展示 26 字母全表
  - "+" 按钮 = 在 splash_text 中插入新字母(弹 dialog 选字母 + 位置)
  - "-" 按钮 = 从 splash_text 删除当前字母(留至少 1 个)
  - 预览 = 画当前 splash_text
  - splash_screen 启动时读 splash_text 渲染开屏动画

本文件相关红线:
- 禁止 __init__ 调 super().__init__() -> 必须显式调用目标基类
- 禁止 paintEvent 漏 super() -> 网格/光标会失效
- 禁止硬编码颜色 -> 必须 self.token() (本文件用 _tc())
- 禁止 widgets/ 直接写 JSON -> 写盘走 state.pixel_font
- 禁止调 Service / 发网络请求

重写记录:
  2026-07-27 第二轮整理:
    - 字母按钮栏从"26 字母全表"改为"splash_text 中字符"(用户要求)
    - "+" 弹 LetterPickerDialog: 选字母 + 选插入位置(用户要求弹 dialog 选位置)
    - "-" 从 splash_text 删除当前字符(留至少 1 个)
    - 预览从"双视图"改为"单视图",画当前 splash_text
    - 新增 state.pixel_font.get_splash_text() / set_splash_text() API
    - splash_screen 改用 get_splash_text() 替代硬编码 "RELIC"
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel,
    QFrame, QMessageBox,
)
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtCore import Qt

from core.widgets.button import CyberButton
from core.tokens.manager import TokenManager
from core.state.pixel_font import (
    get_pixel_font as _get_state_font,
    save_pixel_font as _save_font_to_json,
    get_json_path as _get_json_path,
    get_splash_text as _get_splash_text,
    set_splash_text as _set_splash_text,
    get_default_splash_text as _get_default_splash_text,
    _DEFAULT_FONT,
    reload as _reload_state_font,
)
# splash_screen 的兼容层,内部会调 state.reload + 刷新 _PIXEL_FONT 引用
from core.widgets.splash_screen import reload_pixel_font

# JSON 文件路径(用于保存成功提示)
_PIXEL_FONT_JSON_PATH = _get_json_path()


# ── 颜色解析(带 theme_proxy 兜底,无硬编码) ──

def _tc(key: str) -> str:
    """从 token 解析颜色 hex 字符串,失败时走 theme_proxy 兜底。

    返回: hex 字符串(失败时返回空串)。
    注意: 兜底代理常量在 token 加载前可能是 None,此时返回空串让调用方
    走自己的 `or "#XXXXXX"` 兜底。绝不返回 "None" 这种非法值。
    """
    try:
        return TokenManager.instance().get_qcolor(key).name()
    except Exception:
        from core.theme_proxy import (
            PANEL_BG, CARD_BG, LIGHT_TEXT, LABEL_DEFAULT,
            SUBTLE_BORDER, CYBER_BORDER, CYBER_YELLOW,
            CYBER_CYAN, MUTED_TEXT,
        )
        _fallback = {
            "bg.base": PANEL_BG, "bg.raised": CARD_BG,
            "text.primary": LIGHT_TEXT, "text.secondary": LABEL_DEFAULT,
            "text.disabled": MUTED_TEXT,
            "text.tertiary": LABEL_DEFAULT,
            "border.subtle": SUBTLE_BORDER, "border.default": CYBER_BORDER,
            "accent.primary": CYBER_YELLOW, "accent.secondary": CYBER_CYAN,
            "semantic.warning": CYBER_YELLOW,
            "neutral.dark": MUTED_TEXT,
        }
        proxy = _fallback.get(key)
        if proxy is None:
            return ""
        try:
            s = str(proxy)
            return s if s and s != "None" else ""
        except Exception:
            return ""


_TM = TokenManager.instance()


# ── 像素字体固定尺寸(所有字母统一) ──────────────────────────
# 26 字母 ASCII art 全部统一为 14 行字形 + 6 行装饰 = 20 行,
# 列宽统一 16。统一尺寸让开屏画面字符间距一致,不能调整。
_GRID_ROWS: int = 20
_GRID_COLS: int = 16


# ── 内部小组件 ──────────────────────────────────────────


class _GridCell(QFrame):
    """单个可点击/拖拽的像素格。颜色从 token 解析,无硬编码。"""

    def __init__(self, row: int, col: int, parent=None):
        QFrame.__init__(self, parent)
        self.row = row
        self.col = col
        self._on = False
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def on(self) -> bool:
        return self._on

    @on.setter
    def on(self, value: bool):
        if self._on != value:
            self._on = value
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        on_color = QColor(_tc("accent.secondary") or "#00C8FF")
        off_color = QColor(_tc("bg.raised") or "#1E1E2D")
        border_color = QColor(_tc("border.subtle") or "#3C3C50")
        painter.fillRect(self.rect(), on_color if self._on else off_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        super().paintEvent(event)


class _GridContainer(QFrame):
    """网格容器: 处理鼠标拖拽绘制,通知父组件单元格切换。"""

    def __init__(self, parent=None):
        QFrame.__init__(self, parent)
        self._cells: list[_GridCell] = []
        self._dragging = False
        self._drag_value: bool | None = None
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def add_cell(self, cell: _GridCell) -> None:
        self._cells.append(cell)

    def clear_cells(self) -> None:
        self._cells.clear()

    def _cell_at_pos(self, pos) -> _GridCell | None:
        for c in self._cells:
            if c.geometry().contains(pos):
                return c
        return None

    def _notify_toggle(self, cell: _GridCell) -> None:
        """向上冒泡到有 _on_cell_toggled 方法的祖先(通常是 Panel)。"""
        p = self.parent()
        while p and not hasattr(p, '_on_cell_toggled'):
            p = p.parent()
        if p and hasattr(p, '_on_cell_toggled'):
            p._on_cell_toggled(cell.row, cell.col, cell.on)

    def _set_cell(self, cell: _GridCell, value: bool) -> None:
        if cell.on != value:
            cell.on = value
            self._notify_toggle(cell)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            cell = self._cell_at_pos(event.pos())
            if cell:
                self._dragging = True
                self._drag_value = not cell.on
                self._set_cell(cell, self._drag_value)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            cell = self._cell_at_pos(event.pos())
            if cell and self._drag_value is not None:
                self._set_cell(cell, self._drag_value)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_value = None


class _PreviewLabel(QLabel):
    """预览: 单视图,画当前 splash_text(用户在编辑时会实时看到效果)。"""

    def __init__(self, parent=None):
        QLabel.__init__(self, parent)
        self._data: dict[str, list[list[int]]] = {}
        self._text: str = ""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(280, 120)

    def set_text(self, text: str, data: dict[str, list[list[int]]]) -> None:
        self._text = text
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint(0), False)

        # 背景
        painter.fillRect(self.rect(), QColor(_tc("bg.base") or "#0F0F19"))

        # 画 splash_text(整段字串自适应居中)
        if self._text and self._data:
            self._draw_text(
                painter, self._text,
                x=0, y=0, w=self.width(), h=self.height(),
                color=QColor(_tc("accent.secondary") or "#00C8FF"),
            )

        super().paintEvent(event)

    def _draw_text(
        self, painter: QPainter, text: str,
        x: int, y: int, w: int, h: int, color: QColor,
    ) -> None:
        """画一段字符(自适应缩放,居中于 (x, y, w, h) 矩形内)。"""
        if not text:
            return
        gap = 2
        char_dims: dict[str, tuple[int, int]] = {}
        raw_w = 0
        max_h = 0
        for ch in text:
            grid = self._data.get(ch, [])
            cw = len(grid[0]) if grid else 0
            ch_h = len(grid) if grid else 0
            char_dims[ch] = (cw, ch_h)
            raw_w += cw + gap
            max_h = max(max_h, ch_h)
        raw_w -= gap
        if raw_w <= 0 or max_h <= 0:
            return

        margin = 8
        scale = min((w - margin * 2) / raw_w, (h - margin * 2) / max_h)
        ps = max(1, int(scale))
        lg_px = gap * ps

        total_w = sum(char_dims[ch][0] * ps + lg_px for ch in text) - lg_px
        render_h = max_h * ps
        ox = x + (w - total_w) // 2
        oy = y + (h - render_h) // 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        cx = ox
        for ch in text:
            grid = self._data.get(ch, [])
            if not grid:
                continue
            cw, ch_h = char_dims[ch]
            for r in range(ch_h):
                if r >= len(grid):
                    break
                row = grid[r]
                for c in range(cw):
                    if c >= len(row):
                        break
                    if row[c] == 1:
                        painter.drawRect(cx + c * ps, oy + r * ps, ps, ps)
            cx += cw * ps + lg_px


class LetterPickerDialog(QDialog):
    """字母选择 + 插入位置弹窗。

    两步式:
      步骤 1: 从 A-Z 中选一个字母(允许重复 — splash_text 中已有
              的字母同样可选,用于叠加/重复展示效果)
      步骤 2: 选插入位置(在当前 splash_text 的 N+1 个位置之一: 头 / 各字符间 / 尾)

    用户选完两步后,确定按钮才 enable。两步都选才能关闭(返回 Accepted)。
    取消: reject。
    """

    def __init__(self, current_splash: str, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("添加字母到 splash 动画")
        self.setModal(True)
        self.setMinimumSize(480, 480)
        self._current_splash = current_splash
        self._selected_letter: str | None = None
        self._selected_position: int = -1  # 0..len(current_splash)
        self._position_buttons: list[QPushButton] = []
        self._ok_btn: QPushButton | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── 步骤 1: 选字母(允许重复) ──
        step1 = QLabel("步骤 1: 选择要添加的字母(允许重复, 如 \"RRRELIC\")")
        step1.setStyleSheet(
            f"color: {_tc('text.primary')};"
            f" font-size: {_TM.space('font.body_md', 13)}px;"
            f" font-weight: bold;"
        )
        layout.addWidget(step1)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            btn = QPushButton(ch)
            btn.setFixedSize(48, 48)
            btn.setFont(QFont("Iceberg", 18, QFont.Weight.Bold))
            btn.setStyleSheet(self._letter_style(active=False))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"选择字母 {ch}(可重复)")
            btn.clicked.connect(lambda checked, c=ch: self._on_pick_letter(c))
            grid.addWidget(btn, i // 7, i % 7)
        layout.addLayout(grid)

        # ── 步骤 2: 选位置 ──
        step2 = QLabel(
            f"步骤 2: 选择插入位置(当前 splash: \"{self._current_splash or '(空)'}\")"
        )
        step2.setStyleSheet(
            f"color: {_tc('text.primary')};"
            f" font-size: {_TM.space('font.body_md', 13)}px;"
            f" font-weight: bold;"
        )
        layout.addWidget(step2)

        # 位置按钮: N+1 个槽位(头 + N-1 字符间 + 尾)
        pos_layout = QHBoxLayout()
        pos_layout.setSpacing(4)
        # "头" 位置
        head_btn = QPushButton("前")
        head_btn.setFixedSize(56, 32)
        head_btn.setEnabled(False)
        head_btn.setToolTip("插入到最前面")
        head_btn.clicked.connect(lambda: self._on_pick_position(0))
        pos_layout.addWidget(head_btn)
        self._position_buttons.append(head_btn)

        # 各字符间位置
        for i, ch in enumerate(self._current_splash):
            btn = QPushButton(f"{ch} 后")
            btn.setFixedSize(56, 32)
            btn.setEnabled(False)
            btn.setToolTip(f"插入到 {ch} 之后")
            btn.clicked.connect(lambda checked, p=i + 1: self._on_pick_position(p))
            pos_layout.addWidget(btn)
            self._position_buttons.append(btn)

        # "尾" 位置
        tail_btn = QPushButton("后")
        tail_btn.setFixedSize(56, 32)
        tail_btn.setEnabled(False)
        tail_btn.setToolTip("插入到最后面")
        tail_btn.clicked.connect(lambda: self._on_pick_position(len(self._current_splash)))
        pos_layout.addWidget(tail_btn)
        self._position_buttons.append(tail_btn)

        pos_layout.addStretch()
        layout.addLayout(pos_layout)

        layout.addStretch()

        # ── 确定 / 取消 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = CyberButton("取消", variant="outlined")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self._ok_btn = CyberButton("确定", variant="solid")
        self._ok_btn.setFixedWidth(80)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)
        layout.addLayout(btn_row)

    def _letter_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{"
                f"  background-color: {_tc('accent.primary')};"
                f"  color: {_tc('bg.base')};"
                f"  border: 1px solid {_tc('accent.primary')};"
                f"  border-radius: {_TM.space('corner.xs', 4)}px;"
                f"  font-weight: bold;"
                f"}}"
            )
        return (
            f"QPushButton {{"
            f"  background-color: {_tc('bg.raised')};"
            f"  color: {_tc('accent.primary')};"
            f"  border: 1px solid {_tc('border.default')};"
            f"  border-radius: {_TM.space('corner.xs', 4)}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {_tc('accent.primary')};"
            f"  color: {_tc('bg.base')};"
            f"  border-color: {_tc('accent.primary')};"
            f"}}"
        )

    def _position_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{"
                f"  background-color: {_tc('accent.primary')};"
                f"  color: {_tc('bg.base')};"
                f"  border: 1px solid {_tc('accent.primary')};"
                f"  border-radius: {_TM.space('corner.xs', 4)}px;"
                f"  font-weight: bold;"
                f"}}"
            )
        return (
            f"QPushButton {{"
            f"  background-color: {_tc('bg.raised')};"
            f"  color: {_tc('text.primary')};"
            f"  border: 1px solid {_tc('border.default')};"
            f"  border-radius: {_TM.space('corner.xs', 4)}px;"
            f"}}"
            f"QPushButton:hover {{"
                f"  background-color: {_tc('accent.secondary')};"
                f"  border-color: {_tc('accent.primary')};"
                f"}}"
        )

    def _on_pick_letter(self, ch: str) -> None:
        """字母被选中: 启用所有位置按钮,高亮字母按钮。"""
        self._selected_letter = ch
        # 重画字母按钮高亮(简单方案: 重新设 stylesheet 全部按钮,留作后续改进)
        for btn in self.findChildren(QPushButton):
            if btn in self._position_buttons or btn is self._ok_btn or btn.text() == "取消":
                continue
            text = btn.text()
            if len(text) == 1 and text in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                btn.setStyleSheet(self._letter_style(active=(text == ch)))
        # 启用位置按钮
        for pbtn in self._position_buttons:
            pbtn.setEnabled(True)
            pbtn.setStyleSheet(self._position_style(active=False))
        # 更新确定按钮 enable
        self._refresh_ok_enabled()

    def _on_pick_position(self, pos: int) -> None:
        """位置被选中: 高亮位置按钮。"""
        self._selected_position = pos
        for i, pbtn in enumerate(self._position_buttons):
            pbtn.setStyleSheet(self._position_style(active=(i == pos)))
        self._refresh_ok_enabled()

    def _refresh_ok_enabled(self) -> None:
        if self._ok_btn is not None:
            self._ok_btn.setEnabled(
                self._selected_letter is not None and self._selected_position >= 0
            )

    def selected_result(self) -> tuple[str, int] | None:
        """返回 (字母, 插入位置),若未完成两步则返回 None。"""
        if self._selected_letter is None or self._selected_position < 0:
            return None
        return (self._selected_letter, self._selected_position)


# ── 嵌入主题页的 Panel ──────────────────────────────────


class PixelFontEditorPanel(QFrame):
    """像素字体编辑器内嵌面板(主题页用)。"""

    def __init__(self, parent=None):
        QFrame.__init__(self, parent)

        # 数据起点: state 层缓存的当前字型(可能是 26 字母默认,也可能是用户保存的)
        self._font_data: dict[str, list[list[int]]] = {
            ch: [row[:] for row in grid]
            for ch, grid in _get_state_font().items()
        }

        # 当前 splash_text(从 state 读;字母按钮栏按这个字串渲染)
        self._splash_text: str = _get_splash_text() or _get_default_splash_text()
        # 当前选中的字母 = splash_text 的第一个字符
        self._current_char: str = self._splash_text[0] if self._splash_text else "R"

        self._cells: list[_GridCell] = []
        self._char_buttons: dict[str, QPushButton] = {}
        self._char_btn_layout: QHBoxLayout | None = None
        self._info_label: QLabel | None = None
        self._preview_label: _PreviewLabel | None = None
        self._grid_container: _GridContainer | None = None
        self._grid_layout: QGridLayout | None = None

        self._setup_ui()
        self._load_letter(self._current_char)

        # 订阅主题切换:重建含 token 的 QSS(字母/位置按钮、frame、label)
        try:
            from core.theme_manager import ThemeManager
            ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _on_theme_changed(self, _preset_name: str) -> None:
        """主题切换:重建所有含 token 颜色的 QSS。"""
        # frame 边框/底色
        for w in self.findChildren(QFrame):
            obj = w.objectName()
            # grid_frame / preview_group 无 objectName,用样式特征判断
            ss = w.styleSheet()
            if "background-color:" in ss and "border:" in ss:
                w.setStyleSheet(self._frame_style())
        # info_label / preview_title 等文字色
        for lbl in self.findChildren(QLabel):
            ss = lbl.styleSheet()
            if "color:" in ss:
                if lbl is self._info_label:
                    lbl.setStyleSheet(
                        f"color: {_tc('text.tertiary')}; font-size: 11px;"
                    )
                elif "预览" in lbl.text() or lbl is self._preview_label:
                    continue
                else:
                    # 其它含 color 的 label 按通用规则重建(保留 font-size)
                    parts = [p.strip() for p in ss.split(";") if p.strip()]
                    font_part = next((p for p in parts if p.startswith("font-size")), "")
                    weight_part = next((p for p in parts if p.startswith("font-weight")), "")
                    lbl.setStyleSheet(
                        f"color: {_tc('text.disabled')};"
                        f" {font_part};"
                        f" {weight_part};"
                    )
        # 字母按钮 + 位置按钮:按当前选中态重建
        self._refresh_button_styles()

    def _refresh_button_styles(self) -> None:
        """重建字母按钮和位置按钮的 QSS(按当前选中态)。"""
        selected = getattr(self, "_selected_letter", self._current_char)
        for btn in self.findChildren(QPushButton):
            text = btn.text()
            if len(text) == 1 and text in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                btn.setStyleSheet(self._letter_style(active=(text == selected)))
        # 位置按钮(若存在)
        pos_btns = getattr(self, "_position_buttons", [])
        selected_pos = getattr(self, "_selected_position", -1)
        for i, btn in enumerate(pos_btns):
            btn.setStyleSheet(self._position_style(active=(i == selected_pos)))

    # ── UI 构建 ──

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        # 字母按钮栏 + 操作按钮
        char_row = QHBoxLayout()
        char_row.setSpacing(4)
        self._char_btn_layout = QHBoxLayout()
        self._char_btn_layout.setSpacing(3)
        char_row.addLayout(self._char_btn_layout)

        btn_add = CyberButton("+", variant="ghost")
        btn_add.setFixedSize(28, 24)
        btn_add.setToolTip("添加字母到 splash 动画(从 26 字母中选)")
        btn_add.clicked.connect(self._add_letter)
        char_row.addWidget(btn_add)

        btn_del = CyberButton("-", variant="ghost")
        btn_del.setFixedSize(28, 24)
        btn_del.setToolTip("从 splash 动画中删除当前字母(至少留 1 个)")
        btn_del.clicked.connect(self._del_letter)
        char_row.addWidget(btn_del)

        btn_reset_all = CyberButton("重置全部", variant="outlined")
        btn_reset_all.setFixedHeight(24)
        btn_reset_all.setToolTip("splash 字符恢复为默认 \"RELIC\",字母 art 恢复为 26 字母默认")
        btn_reset_all.clicked.connect(self._reset_all)
        char_row.addWidget(btn_reset_all)

        char_row.addStretch()
        layout.addLayout(char_row)
        self._rebuild_char_buttons()

        # 像素编辑网格
        grid_frame = QFrame()
        grid_frame.setStyleSheet(self._frame_style())
        grid_outer = QVBoxLayout(grid_frame)
        grid_outer.setContentsMargins(2, 2, 2, 2)
        grid_outer.setSpacing(0)

        self._grid_container = _GridContainer()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(1)
        self._grid_layout.setContentsMargins(2, 2, 2, 2)
        grid_outer.addWidget(self._grid_container)
        layout.addWidget(grid_frame)

        # 控件行(尺寸固定 + 操作按钮 + 信息)
        # 像素字体所有字母统一 20 行 × 16 列,故行列不可调整(去掉 spin 控件)
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        size_tag = QLabel("尺寸: 固定 20×16")
        size_tag.setStyleSheet(
            f"color: {_tc('text.tertiary')};"
            f" font-size: {_TM.space('font.xs', 11)}px;"
        )
        ctrl_row.addWidget(size_tag)

        ctrl_row.addSpacing(8)

        btn_save = CyberButton("保存", variant="solid")
        btn_save.setFixedWidth(52)
        btn_save.clicked.connect(self._save)
        ctrl_row.addWidget(btn_save)

        btn_reset = CyberButton("重置", variant="outlined")
        btn_reset.setFixedWidth(52)
        btn_reset.clicked.connect(self._reset_current)
        ctrl_row.addWidget(btn_reset)

        ctrl_row.addStretch()
        self._info_label = QLabel()
        self._info_label.setStyleSheet(
            f"color: {_tc('text.tertiary')}; font-size: 11px;"
        )
        ctrl_row.addWidget(self._info_label)
        layout.addLayout(ctrl_row)

        # 预览
        preview_group = QFrame()
        preview_group.setStyleSheet(self._frame_style())
        preview_outer = QVBoxLayout(preview_group)
        preview_outer.setContentsMargins(4, 4, 4, 4)
        preview_outer.setSpacing(2)
        preview_title = QLabel("预览(开屏动画当前字符组合)")
        preview_title.setStyleSheet(
            f"color: {_tc('text.disabled')};"
            f" font-size: {_TM.space('font.xs', 11)}px;"
            f" font-weight: bold;"
        )
        preview_outer.addWidget(preview_title)
        self._preview_label = _PreviewLabel()
        self._preview_label.setMinimumHeight(120)
        self._preview_label.setMaximumHeight(200)
        preview_outer.addWidget(self._preview_label)
        layout.addWidget(preview_group)

    def _frame_style(self) -> str:
        return (
            f"QFrame {{"
            f"  background-color: {_tc('bg.base')};"
            f"  border: 1px solid {_tc('border.default')};"
            f"  border-radius: {_TM.space('corner.xs', 4)}px;"
            f"}}"
        )

    # ── 字母按钮栏(按 splash_text 顺序) ──

    def _rebuild_char_buttons(self) -> None:
        """根据 self._splash_text 重建字符按钮栏(按字串顺序,不是 A-Z 排序)。"""
        for btn in self._char_buttons.values():
            btn.deleteLater()
        self._char_buttons.clear()
        if self._char_btn_layout is not None:
            while self._char_btn_layout.count():
                item = self._char_btn_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        for ch in self._splash_text:
            btn = QPushButton(ch)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(28, 24)
            btn.setToolTip(f"编辑字母 {ch}")
            btn.clicked.connect(lambda checked, c=ch: self._load_letter(c))
            self._char_buttons[ch] = btn
            if self._char_btn_layout is not None:
                self._char_btn_layout.addWidget(btn)

        self._highlight_active_button()

    def _highlight_active_button(self) -> None:
        """高亮当前选中的字母按钮。"""
        for ch, btn in self._char_buttons.items():
            is_active = (ch == self._current_char)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: "
                f"    {_tc('accent.secondary') if is_active else _tc('bg.base')};"
                f"  color: {_tc('text.primary')};"
                f"  border: 1px solid "
                f"    {_tc('accent.primary') if is_active else _tc('border.default')};"
                f"  border-radius: {_TM.space('corner.xs', 4)}px;"
                f"  font-size: {_TM.space('font.body_md', 13)}px;"
                f"  font-weight: {'bold' if is_active else 'normal'};"
                f"  padding: 2px 6px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {_tc('accent.secondary')};"
                f"  border-color: {_tc('accent.primary')};"
                f"}}"
            )

    # ── 字母增删(操作 splash_text) ──

    def _add_letter(self) -> None:
        """弹 dialog: 选字母 + 选插入位置 → 插入 splash_text。

        允许添加已经在 splash_text 中的字母(用于"RRR"、"LLL" 这种
        强调重复效果,或灵活组合如 "WARFRAME")。
        字母 art 如果 _font_data 没有,从 _DEFAULT_FONT 加载默认 art。
        """
        dlg = LetterPickerDialog(self._splash_text, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = dlg.selected_result()
        if result is None:
            return
        ch, pos = result
        # 允许重复:不再拦截"已在 splash_text 中"的字母。
        # 插入到 splash_text(支持任意位置,包括头/中/尾)
        new_text = self._splash_text[:pos] + ch + self._splash_text[pos:]
        self._splash_text = new_text
        _set_splash_text(new_text)
        # 字母 art: 如果没有,从 _DEFAULT_FONT 加载;已有则保留用户编辑
        if ch not in self._font_data:
            default = _DEFAULT_FONT.get(ch)
            if default:
                self._font_data[ch] = [row[:] for row in default]
            else:
                self._font_data[ch] = [[0] * _GRID_COLS for _ in range(_GRID_ROWS)]
        # 重建按钮栏 + 选中新字母
        self._rebuild_char_buttons()
        self._load_letter(ch)

    def _del_letter(self) -> None:
        """从 splash_text 移除当前字母(至少保留 1 个)。

        联动清理:
          - 若 splash_text 中已经不再有该字母,也从 font_data 移除
          - 这样用户重新"+"添加该字母时,会从 _DEFAULT_FONT 重新加载,
            而不是沿用之前编辑过的 art
        """
        if len(self._splash_text) <= 1:
            QMessageBox.information(
                self, "无法删除", "splash 动画至少需要 1 个字符。"
            )
            return
        ch = self._current_char
        # 删第一个出现的 ch
        idx = self._splash_text.find(ch)
        if idx < 0:
            return
        new_text = self._splash_text[:idx] + self._splash_text[idx + 1:]
        self._splash_text = new_text
        _set_splash_text(new_text)
        # 联动清理 font_data: splash_text 中已无此字母时移除其 art
        if ch not in new_text:
            self._font_data.pop(ch, None)
        # 重建按钮栏
        self._rebuild_char_buttons()
        # 选中剩下第一个字符
        if new_text:
            self._load_letter(new_text[0])
        else:
            self._update_preview()

    # ── 加载/构建/重置 ──

    def _load_letter(self, ch: str) -> None:
        """加载指定字母的数据到编辑网格。"""
        self._current_char = ch
        grid = self._font_data.get(ch, [])
        rows = len(grid) if grid else _GRID_ROWS
        cols = len(grid[0]) if (grid and grid[0]) else _GRID_COLS

        self._build_grid(rows, cols, grid)
        self._highlight_active_button()
        self._update_preview()
        self._update_info()

    def _build_grid(self, rows: int, cols: int, data: list[list[int]]) -> None:
        """构建编辑网格(清理旧的 cell)。"""
        for cell in self._cells:
            cell.deleteLater()
        self._cells.clear()
        if self._grid_container is not None:
            self._grid_container.clear_cells()
        if self._grid_layout is not None:
            while self._grid_layout.count():
                item = self._grid_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        for r in range(rows):
            for c in range(cols):
                cell = _GridCell(r, c, self._grid_container)
                val = data[r][c] if (r < len(data) and c < len(data[r])) else 0
                cell.on = bool(val)
                self._cells.append(cell)
                if self._grid_container is not None:
                    self._grid_container.add_cell(cell)
                if self._grid_layout is not None:
                    self._grid_layout.addWidget(cell, r, c)

        if self._cells and self._grid_container is not None:
            cell_w = self._cells[0].width() + 1
            cell_h = self._cells[0].height() + 1
            self._grid_container.setFixedSize(cols * cell_w + 4, rows * cell_h + 4)

    def _on_cell_toggled(self, row: int, col: int, on: bool) -> None:
        """单元格被切换时更新数据 + 刷新预览/信息。"""
        ch = self._current_char
        if ch in self._font_data and row < len(self._font_data[ch]):
            if col < len(self._font_data[ch][row]):
                self._font_data[ch][row][col] = 1 if on else 0
        self._update_preview()
        self._update_info()

    def _reset_current(self) -> None:
        """重置当前字母为 _DEFAULT_FONT 中的默认 art。"""
        ch = self._current_char
        original = _DEFAULT_FONT.get(ch)
        if original:
            self._font_data[ch] = [row[:] for row in original]
        self._load_letter(ch)

    def _reset_all(self) -> None:
        """重置 splash_text = 默认 + 字母 art 全部恢复 26 字母默认。"""
        self._font_data.clear()
        for ch, grid in _DEFAULT_FONT.items():
            self._font_data[ch] = [row[:] for row in grid]
        self._splash_text = _get_default_splash_text()
        _set_splash_text(self._splash_text)
        self._rebuild_char_buttons()
        self._load_letter(self._splash_text[0])

    # ── 预览 & 信息 ──

    def _update_preview(self) -> None:
        if self._preview_label is not None:
            self._preview_label.set_text(self._splash_text, self._font_data)

    def _update_info(self) -> None:
        if self._info_label is None:
            return
        ch = self._current_char
        grid = self._font_data.get(ch, [])
        rows = len(grid)
        cols = len(grid[0]) if grid else 0
        total = sum(sum(row) for row in grid)
        tc = rows * cols
        self._info_label.setText(
            f"splash: \"{self._splash_text}\" | 当前 {ch} | {rows}x{cols} | 像素 {total}/{tc}"
        )

    # ── 保存 ──

    def _save(self) -> None:
        """保存字体数据 + splash_text 到 JSON(走 state.pixel_font),刷新缓存。"""
        ok, err_msg = _save_font_to_json(self._font_data, self._splash_text)
        if ok:
            # 同步刷新 state 层缓存 + splash_screen 兼容层 _PIXEL_FONT
            _reload_state_font()
            reload_pixel_font()
            QMessageBox.information(
                self, "保存成功",
                f"已保存到 pixel_font.json!\n路径: {_PIXEL_FONT_JSON_PATH}",
            )
        else:
            QMessageBox.warning(
                self, "保存失败",
                f"无法保存像素字体数据:\n{err_msg}",
            )


# ── 独立运行入口(供开发调试) ──

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    panel = PixelFontEditorPanel()
    panel.resize(720, 720)
    panel.show()
    app.exec()
