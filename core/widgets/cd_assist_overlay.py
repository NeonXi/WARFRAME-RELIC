"""
[L4] core.widgets.cd_assist_overlay — CdAssistOverlay 多屏 4 数字横排悬浮窗

归属层:    [L4] (core/widgets/)
允许依赖:  PySide6, ctypes (用于 Win32 透明窗口), core.tokens.manager
禁止依赖:  core.services/*, core.pages/*, 任何 IO/JSON/网络

职责:
  - CdAssistOverlay(QWidget): 覆盖单个屏幕,横向 4 数字/圆点
  - CdAssistManager(QObject):  统一管理多屏 overlay(按 enabled_screens 集合)

视觉:
  - 4 个 cell 横排,每个 cell 120x160(可调)
  - 数字字号 80px,黄色 (accent.primary)
  - duration=0 的 cell 显示"·"圆点
  - 整体居中于屏幕中心
  - 完全鼠标穿透 + 不抢焦点(参考 EyeMaskOverlay)

数据流:
  - 上层(由 CdAssistPage 注入): CdAssistService.countdown_tick 信号
  - tick payload = {idx: remaining_sec}, 0 表示"·"状态
"""

from __future__ import annotations

import ctypes

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPaintEvent, QGuiApplication, QFont

from core.logging_utils import log as _dbg
from core.tokens.manager import TokenManager
from core.fonts import FONT_DISPLAY


# ── Win32 透明窗口常量 ──
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_GWL_EXSTYLE = -20


# ── 视觉常量(4 的倍数) ──
CELL_WIDTH = 120      # 每个数字格宽(要能放下"10.0"4 字符)
CELL_HEIGHT = 80      # 每个数字格高
CELL_SPACING = 16     # 格间距
PADDING = 12          # 窗口内边距
DIGIT_FONT_PT = 36    # 数字字号(简洁版)


# ═══════════════════════════════════════
#  CdAssistOverlay — 单屏浮窗
# ═══════════════════════════════════════

class CdAssistOverlay(QWidget):
    """单屏 CD 倒计时浮窗。

    内部结构:
      [QLabel0] [QLabel1] [QLabel2] [QLabel3]   ← 横排
    4 个 cell 的文字由 countdown_tick 驱动:
      - remaining > 0:  显示 "4.5" / "8.2" (1 位小数)
      - remaining = 0:  显示 "·"
    """

    def __init__(self, screen_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._screen_index = screen_index

        # ── 显示位置偏移(相对屏幕中心,px) ──
        # 由 service.set_position_offset() 注入;默认 (0, 0) = 居中
        self._x_offset: int = 0
        self._y_offset: int = 0

        # ── 窗口属性:无边框 + 置顶 + 工具 + 鼠标穿透 + 不抢焦点 ──
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # ── 4 个 cell 横排 ──
        self._cells: list[QLabel] = []
        # 4 个 cell 的 opacity 效果器(用于闪烁)
        self._opacity_effects: list[QGraphicsOpacityEffect] = []
        # 各 cell 当前是否处于"提醒态"(变橙 + 闪烁)
        self._in_reminder: list[bool] = [False] * 4
        # 闪烁 timer 状态
        self._flash_visible: bool = True  # 当前是否"亮着"
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(150)  # 150ms 切一次(警示灯节奏,非常醒目)
        self._flash_timer.timeout.connect(self._on_flash_tick)

        # 缓存 token 颜色(刷新时复用,避免每 tick 都读 token)
        tm = TokenManager.instance()
        self._normal_color: str = tm.get("alias.text.primary")      # 白色
        self._remind_color: str = tm.get("alias.semantic.warning")  # 橙色

        layout = QHBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(CELL_SPACING)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for i in range(4):
            lbl = QLabel("·", self)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 不用 setFixedSize:用 setMinimumSize 让"10.0"超出时自动撑大
            lbl.setMinimumSize(CELL_WIDTH, CELL_HEIGHT)
            self._style_label(lbl, "·")
            # ★ 加 opacity 效果器,用于提醒态闪烁
            effect = QGraphicsOpacityEffect(lbl)
            effect.setOpacity(1.0)
            lbl.setGraphicsEffect(effect)
            self._opacity_effects.append(effect)
            self._cells.append(lbl)
            layout.addWidget(lbl)

        # ── 大小:用 minimum 让窗口能因内容(数字宽度)自动撑大 ──
        self.setMinimumSize(
            CELL_WIDTH * 4 + CELL_SPACING * 3 + PADDING * 2,
            CELL_HEIGHT + PADDING * 2,
        )
        self._apply_win32_transparent()
        self._center_on_target_screen()

    # ── 私有:样式 ──

    def _style_label(self, lbl: QLabel, text: str) -> None:
        """统一 4 个 cell 的样式(数字/圆点)。颜色/字号全走 token。

        简洁版: 纯数字,无背景无边框,只大字号粗体白字
        """
        tm = TokenManager.instance()
        color_hex = tm.get("alias.text.primary")
        f = QFont(FONT_DISPLAY)
        f.setPointSize(DIGIT_FONT_PT)
        f.setBold(True)
        lbl.setFont(f)
        # 简洁: 纯数字,透明背景,无边框
        self._apply_label_color(lbl, color_hex)
        lbl.setText(text)
        # ★ 关键: 设置 minimum width,保证"10.0"不被截断
        #   Qt 的 QLabel 默认按 hint 缩放,但 setFixedSize 后会强制裁剪
        #   这里给 label 一个 minimum size 兜底,内容超出时 widget 自动撑大
        lbl.setMinimumWidth(CELL_WIDTH)
        lbl.setSizePolicy(
            lbl.sizePolicy().horizontalPolicy(),
            lbl.sizePolicy().verticalPolicy(),
        )

    @staticmethod
    def _apply_label_color(lbl: QLabel, color: str) -> None:
        """设置 cell label 的颜色 + 透明背景 + 无边框。

        用 lbl.setProperty("_current_color", color) 记录上次颜色,
        调用前对比,只在颜色真变化时才 setStyleSheet,
        避免每个 tick 都重设样式(性能 + 减少无谓重绘)。
        """
        last = lbl.property("_current_color")
        if last == color:
            return
        lbl.setProperty("_current_color", color)
        lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    def _apply_win32_transparent(self) -> None:
        """Win32 加固透明属性(参考 EyeMaskOverlay._apply_win32_transparent)。"""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, _GWL_EXSTYLE,
                ex_style | _WS_EX_TRANSPARENT | _WS_EX_LAYERED
                | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE,
            )
        except Exception:
            # 非 Windows / 无 ctypes —— Qt 属性已能保证基本效果
            pass

    def showEvent(self, event) -> None:
        """每次显示都重新应用透明属性 + 重新居中(防屏幕拓扑变化)。"""
        super().showEvent(event)
        self._apply_win32_transparent()
        self._center_on_target_screen()
        _dbg("ovl", f"overlay[{self._screen_index}] showEvent, "
                f"geometry={self.geometry().getRect()}, isVisible={self.isVisible()}, "
                f"isWindow={self.isWindow()}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._center_on_target_screen()

    def _center_on_target_screen(self) -> None:
        """把窗口几何对齐到目标屏幕中心 + 用户设置的偏移。"""
        screens = QGuiApplication.screens()
        if not screens:
            self.setGeometry(0, 0, self.width(), self.height())
            return
        if 0 <= self._screen_index < len(screens):
            geo = screens[self._screen_index].availableGeometry()
        else:
            geo = screens[0].availableGeometry()
        # 屏幕中心 + 用户偏移
        x = geo.x() + (geo.width() - self.width()) // 2 + self._x_offset
        y = geo.y() + (geo.height() - self.height()) // 2 + self._y_offset
        self.setGeometry(x, y, self.width(), self.height())

    # ── 公开 API ──

    def set_offset(self, x: int, y: int) -> None:
        """设置位置偏移(相对屏幕中心,px)。立即重新居中。"""
        self._x_offset = int(x)
        self._y_offset = int(y)
        self._center_on_target_screen()  # 立即重算并移动窗口

    def update_cells(self, payload: dict) -> None:
        """根据 countdown_tick payload 刷新 4 个 cell。

        payload 格式 (service 新版发出):
          {"0": {"r": 4.5, "m": True}, "1": {"r": 7.0, "m": False}, ...}
            - r (float): 剩余秒数
            - m (bool):  是否处于"提醒态"(变橙 + 闪烁)

        显示规则:
          - payload 中有该 idx: r > 0 显示 "X.X",r = 0 显示 "·"
          - payload 中无该 idx: 显示 "·"  (常驻,user 要求)
        """
        for i, lbl in enumerate(self._cells):
            key = str(i)
            m = False
            if key in payload:
                entry = payload[key]
                v = float(entry.get("r", 0))
                m = bool(entry.get("m", False))
                if v > 0:
                    lbl.setText(f"{v:.1f}")
                else:
                    lbl.setText("·")
            else:
                # ★ 持久显示: 无 payload 时显示 "·",不再留空
                lbl.setText("·")
            # 记录提醒态(供闪烁 + 变色用)
            self._in_reminder[i] = m

        # 启停闪烁 timer
        any_reminding = any(self._in_reminder)
        if any_reminding and not self._flash_timer.isActive():
            self._flash_timer.start()
            self._flash_visible = True
        elif not any_reminding and self._flash_timer.isActive():
            self._flash_timer.stop()
            self._flash_visible = True
            # 复位: 所有 cell 恢复不透明 + 白色
            for i, effect in enumerate(self._opacity_effects):
                effect.setOpacity(1.0)
            for lbl in self._cells:
                self._apply_label_color(lbl, self._normal_color)
            return

        # 立即按当前 reminder 状态更新颜色(opacity 留给 _on_flash_tick 处理)
        self._refresh_cell_colors()

    def _refresh_cell_colors(self) -> None:
        """根据 _in_reminder 状态更新 4 个 cell 的颜色。

        提醒态: 橙色;非提醒态: 白色(默认)。
        闪烁(opacity 切换)由 _on_flash_tick 单独控制。
        """
        for i, lbl in enumerate(self._cells):
            color = self._remind_color if self._in_reminder[i] else self._normal_color
            self._apply_label_color(lbl, color)

    def _on_flash_tick(self) -> None:
        """闪烁 timer 回调(500ms 切一次):提醒态 cell 透明度 1.0 ↔ 0.3。"""
        self._flash_visible = not self._flash_visible
        for i, effect in enumerate(self._opacity_effects):
            if self._in_reminder[i]:
                effect.setOpacity(1.0 if self._flash_visible else 0.3)
            else:
                effect.setOpacity(1.0)

    def clear_cells(self) -> None:
        """清空所有 cell(用于总开关关闭时)。"""
        for lbl in self._cells:
            lbl.setText("")

    # ── 绘制 ──

    def paintEvent(self, event: QPaintEvent) -> None:
        """透明背景 + 文字由 QLabel 自绘。

        QWidget.paintEvent 默认会清背景,WA_TranslucentBackground + 空 fill
        保证整体透明;数字由 QLabel 内部画。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 不 fillRect:保持 WA_TranslucentBackground 透明
        # 不需要 super().paintEvent(): QWidget 默认 paintEvent 无副作用


# ═══════════════════════════════════════
#  CdAssistManager — 多屏统一管理
# ═══════════════════════════════════════

class CdAssistManager(QObject):
    """管理 N 个 CdAssistOverlay(按 enabled_screens 集合启停)。

    设计:
      - 始终为每屏创建一个 overlay(懒构造,on_enter 触发 refresh_screens)
      - enabled_screens 集合外的 overlay 不显示
      - 任何 overlay 在显示 → 整体 visible
      - service tick 时:对所有 enabled overlay 都 update_cells
      - service 关闭时:全部 hide + clear

    单例模式:
      - service 在主线程启动时(app_shell._start_cd_assist_hook)就创建并连接
        → 用户不需要先进 CD 辅助显示页面也能用
      - 页面 on_enter 复用同一个实例,只刷新屏幕列表 + 同步 UI

    信号:
      visibility_changed(bool)        整体显隐
      enabled_screens_changed(list)   启用屏幕集合
    """

    visibility_changed = Signal(bool)
    enabled_screens_changed = Signal(list)

    _instance: "CdAssistManager | None" = None

    @classmethod
    def instance(cls) -> "CdAssistManager":
        """单例访问(惰性创建)。"""
        if cls._instance is None:
            _dbg("mgr", f"CdAssistManager 单例首次创建 (id={id(cls)})")
            cls._instance = CdAssistManager()
        return cls._instance

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # screen_index -> CdAssistOverlay
        self._overlays: dict[int, CdAssistOverlay] = {}
        # 当前启用的屏幕索引集合
        self._enabled: set[int] = set()
        # 整体可见性
        self._visible: bool = False
        # 是否绑定 service(防止重复连接)
        self._bound: bool = False
        # 最后一次 tick payload(给新启用的屏用)
        self._last_payload: dict = {}

    # ── 屏幕集合管理 ──

    def refresh_screens(self) -> None:
        """按当前 QGuiApplication.screens() 同步 overlay 池(支持热插拔)。"""
        screens = QGuiApplication.screens()
        current_indices = set(range(len(screens)))
        _dbg("mgr", f"refresh_screens: 检测到 {len(screens)} 屏, indices={sorted(current_indices)}")

        for idx in list(self._overlays.keys()):
            if idx not in current_indices:
                old = self._overlays.pop(idx)
                old.hide()
                old.deleteLater()
                self._enabled.discard(idx)
                _dbg("mgr", f"屏 {idx} 已消失,删除 overlay")

        for idx in current_indices:
            if idx not in self._overlays:
                self._overlays[idx] = CdAssistOverlay(screen_index=idx)
                _dbg("mgr", f"屏 {idx} 新建 overlay")

    def available_screen_indices(self) -> list[int]:
        """当前所有可用屏幕索引(按 0..N-1 顺序)。"""
        return sorted(self._overlays.keys())

    def set_enabled_screens(self, indices: list[int]) -> None:
        """设置启用屏幕集合(替换式)。

        - 退出启用集合的屏: 立即 hide
        - 进入启用集合的屏: 若整体可见,立即 show 并用 last_payload 刷新
        """
        new_set = set(int(i) for i in indices) & set(self._overlays.keys())
        old_set = set(self._enabled)
        _dbg("mgr", f"set_enabled_screens: {sorted(old_set)} → {sorted(new_set)}")

        for idx in old_set - new_set:
            ov = self._overlays.get(idx)
            if ov is not None:
                ov.hide()

        for idx in new_set - old_set:
            ov = self._overlays.get(idx)
            if ov is not None and self._visible:
                ov.show()
                ov.update_cells(self._last_payload)

        self._enabled = new_set
        self.enabled_screens_changed.emit(sorted(new_set))

        # 维护整体可见性状态
        self._update_visibility()

    def get_enabled_screens(self) -> list[int]:
        return sorted(self._enabled)

    def set_position_offset(self, x: int, y: int) -> None:
        """设置所有 overlay 的位置偏移(由 service 调)。"""
        for ov in self._overlays.values():
            try:
                ov.set_offset(x, y)
            except Exception:
                pass

    # ── 显隐控制(由 service 驱动) ──

    def show(self, payload: dict | None = None) -> None:
        """显示所有 enabled overlay。

        高频调用(每个 100ms tick 都会调),所以内部**不打过程日志**,
        仅在 _set_visible 从 False→True 时由 _set_visible 打一条。
        """
        if payload is not None:
            self._last_payload = dict(payload)
        if not self._enabled:
            return
        any_shown = False
        for idx in self._enabled:
            ov = self._overlays.get(idx)
            if ov is not None:
                ov.show()
                if payload is not None:
                    ov.update_cells(payload)
                any_shown = True
        if any_shown:
            self._set_visible(True)

    def hide(self) -> None:
        """隐藏所有 enabled overlay(其他屏不受影响)。"""
        for idx in self._enabled:
            ov = self._overlays.get(idx)
            if ov is not None:
                ov.hide()
        self._set_visible(False)

    def update_cells(self, payload: dict) -> None:
        """更新所有 enabled overlay 的 cell 内容(不改变显隐)。"""
        self._last_payload = dict(payload)
        for idx in self._enabled:
            ov = self._overlays.get(idx)
            if ov is not None:
                ov.update_cells(payload)

    def clear_cells(self) -> None:
        """清空所有 overlay 的 cell(用于总开关关闭)。"""
        self._last_payload = {}
        for ov in self._overlays.values():
            ov.clear_cells()

    def is_visible(self) -> bool:
        return self._visible

    def _set_visible(self, v: bool) -> None:
        if self._visible != v:
            self._visible = v
            # 仅在状态真的变化时打一条日志(高频 show() 不再每 tick 打)
            _dbg("mgr", f"visibility {v} (enabled={sorted(self._enabled)})")
            self.visibility_changed.emit(v)

    def _update_visibility(self) -> None:
        """enabled_screens 变化后重新计算整体可见性。"""
        # 任何 enabled overlay 在显示中 = 整体可见
        # (我们保持简单:任何 enabled 且被 show 过的 = 可见)
        # 由于我们没追踪单个 overlay 状态,这里只看 _visible 标记
        # 实际逻辑由 show/hide 显式控制
        pass
