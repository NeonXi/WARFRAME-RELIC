"""
区域选择器 —— 独立的框选封装模块
====================================
职责：在屏幕上画一个矩形区域，记录位置信息，供任何需要"区域选择"的地方调用。

设计原则：
  - 不依赖 Overlay 的业务逻辑（标注、按钮等）
  - 不依赖 main.py 的截图逻辑
  - 仅负责：显示框选界面 → 用户拖拽 → 返回区域坐标
  - 坐标体系：同时记录逻辑坐标（Qt 坐标）和物理坐标（屏幕像素），调用方按需取用

典型用法：
    selector = RegionSelector(parent_widget)          # 创建（依附于一个全屏 QWidget）
    selector.set_callback(on_region_selected)          # 设置回调
    selector.start()                                    # 启启动框选

    def on_region_selected(region_info):
        # region_info = {
        #     'logical':  (left, top, right, bottom),  # Qt 逻辑坐标
        #     'physical': (left, top, right, bottom),  # 屏幕物理坐标（dxcam 用）
        #     'physical_xywh': {'x': int, 'y': int, 'w': int, 'h': int},  # 物理 xywh
        #     'dpi_scale': float,                      # DPI 缩放比例
        # }
        ...
"""
import time
import ctypes
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QCursor

from core.constants import (
    CYBER_YELLOW, CYBER_CYAN,
    OVERLAY_SELECTION_OVERLAY, OVERLAY_STATUS_BG,
    OVERLAY_CROSSHAIR_COLOR, OVERLAY_SELECTION_BORDER,
)
from data.ui_strings import S

# ========== Win32 辅助 ==========
_VK_LBUTTON = 0x01
_VK_RBUTTON = 0x02
_VK_ESCAPE  = 0x1B

MIN_SELECTION_SIZE = 20       # 最小有效框选尺寸（像素）
TRACK_INTERVAL_MS  = 16       # 鼠标追踪间隔（约 60fps）


class RegionSelector:
    """区域框选器。

    嵌入到一个已有的全屏 QWidget 中工作，不创建独立窗口。
    在父控件的 paintEvent 中调用 self.paint(painter) 绘制框选 UI。
    """

    def __init__(self, parent_widget, dpi_scale: float = 1.0):
        """
        Args:
            parent_widget: 宿主 QWidget（必须是全屏窗口，如 Overlay）
            dpi_scale: DPI 缩放比例（物理像素 / 逻辑像素）
        """
        self._parent = parent_widget
        self._dpi_scale = dpi_scale

        # ---- 框选状态 ----
        self._active = False           # 是否处于框选模式
        self._start_pos = None         # 框选起点（QPoint，逻辑坐标）
        self._current_pos = None       # 当前鼠标位置（QPoint，逻辑坐标）
        self._left_was_down = False    # 上一帧左键是否按下
        self._status_text = ""         # 状态栏文字
        self._track_timer: QTimer | None = None

        # ---- 回调 ----
        self._callback = None          # callable(region_info) 或 None（取消时）
        self._on_cancelled = None      # 可选：取消框选时的回调

        # ---- 结果 ----
        self._last_region_info: dict | None = None   # 最近一次框选结果

    # ========== 公共 API ==========

    def set_callback(self, callback, on_cancelled=None):
        """设置框选完成回调。

        Args:
            callback:     框选成功时调用 callback(region_info)
            on_cancelled: 框选取消时调用 on_cancelled()（可选）
        """
        self._callback = callback
        self._on_cancelled = on_cancelled

    def start(self):
        """启启动框选模式。"""
        self._active = True
        self._start_pos = None
        self._current_pos = self._parent.mapFromGlobal(QCursor.pos())
        
        # ★ 修复：采样当前按键状态，避免启动时的残留状态导致误判
        # 如果左键或右键当前正按下，等待下一帧再开始检测
        self._left_was_down = self._is_key_down(_VK_LBUTTON)
        right_now = self._is_key_down(_VK_RBUTTON)
        
        # 如果右键正按下，设置一个短暂的保护期
        if right_now:
            print("[RegionSelector] 检测到右键按下，设置保护期...")
            # 不立即启动定时器，等待 100ms 后再开始
            QTimer.singleShot(100, self._delayed_start)
            return
        
        self._status_text = S("overlay", "selection_status_idle")

        # 修改父窗口属性
        self._parent.setCursor(Qt.CursorShape.CrossCursor)

        # 启启动鼠标追踪定时器
        self._track_timer = QTimer()
        self._track_timer.timeout.connect(self._tick)
        self._track_timer.start(TRACK_INTERVAL_MS)

        self._parent.update()
        print(f"[RegionSelector] 框选模式启动")
    
    def _delayed_start(self):
        """延迟启动（等待鼠标状态稳定后）。"""
        if not self._active:
            return
        
        # 重新采样按键状态
        self._left_was_down = self._is_key_down(_VK_LBUTTON)
        self._status_text = S("overlay", "selection_status_idle")
        
        self._parent.setCursor(Qt.CursorShape.CrossCursor)
        
        self._track_timer = QTimer()
        self._track_timer.timeout.connect(self._tick)
        self._track_timer.start(TRACK_INTERVAL_MS)
        
        self._parent.update()
        print(f"[RegionSelector] 延迟启动完成")

    def cancel(self):
        """取消当前框选（不触发 callback）。"""
        if not self._active:
            return
        self._cleanup()
        if self._on_cancelled:
            self._on_cancelled()
        print("[RegionSelector] 框选已取消")

    def stop(self):
        """强制停止框选（不触发任何回调）。"""
        if not self._active:
            return
        self._cleanup()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def last_region(self) -> dict | None:
        """最近一次有效的框选结果。"""
        return self._last_region_info

    # ========== 每帧 tick ==========

    def _tick(self):
        """鼠标追踪主循环（由 QTimer 每 16ms 调用一次）。"""
        if not self._active:
            return

        pos = self._parent.mapFromGlobal(QCursor.pos())
        self._current_pos = pos
        left_down = self._is_key_down(_VK_LBUTTON)

        # 右键取消
        if self._is_key_down(_VK_RBUTTON):
            print("[RegionSelector] 右键取消框选")
            self._finish(cancelled=True)
            return

        # ESC 取消
        if self._is_key_down(_VK_ESCAPE):
            print("[RegionSelector] ESC 取消框选")
            self._finish(cancelled=True)
            return

        # 左键按下（开始拖拽）
        if left_down and not self._left_was_down:
            self._start_pos = pos
            self._left_was_down = True
            self._status_text = S.format(
                "overlay", "selection_status_pressed", x=pos.x(), y=pos.y())
            print(f"[RegionSelector] 左键按下 @ ({pos.x()},{pos.y()})")

        # 左键拖拽中
        elif left_down and self._left_was_down:
            if self._start_pos:
                w = abs(pos.x() - self._start_pos.x())
                h = abs(pos.y() - self._start_pos.y())
                self._status_text = S.format(
                    "overlay", "selection_status_dragging", w=w, h=h)

        # 左键松开（完成框选）
        elif not left_down and self._left_was_down:
            self._left_was_down = False
            print(f"[RegionSelector] 左键松开 @ ({pos.x()},{pos.y()})")
            if self._start_pos:
                self._status_text = S("overlay", "selection_status_released")
                self._finish(cancelled=False)
                return
            else:
                self._status_text = S("overlay", "selection_status_idle")

        else:
            self._left_was_down = left_down
            self._status_text = S("overlay", "selection_status_idle")

        self._parent.update()

    # ========== 完成处理 ==========

    def _finish(self, cancelled: bool):
        """框选结束（成功或取消）。"""
        region_info = None

        if not cancelled and self._start_pos and self._current_pos:
            p1, p2 = self._start_pos, self._current_pos
            left   = min(p1.x(), p2.x())
            top    = min(p1.y(), p2.y())
            right  = max(p1.x(), p2.x())
            bottom = max(p1.y(), p2.y())
            w = right - left
            h = bottom - top

            print(f"[RegionSelector] 框选完成: logical=({left},{top},{right},{bottom}) w={w} h={h}")

            if w > MIN_SELECTION_SIZE and h > MIN_SELECTION_SIZE:
                dpi = self._dpi_scale
                region_info = {
                    'logical':  (left, top, right, bottom),
                    'physical': (int(left * dpi), int(top * dpi),
                                 int(right * dpi), int(bottom * dpi)),
                    'physical_xywh': {
                        'x': int(left * dpi),
                        'y': int(top * dpi),
                        'w': int(w * dpi),
                        'h': int(h * dpi),
                    },
                    'dpi_scale': dpi,
                }
                self._last_region_info = region_info
            else:
                print(f"[RegionSelector] 框选区域过小 ({w}x{h})，忽略")

        self._cleanup()

        # 触发回调
        if not cancelled and region_info and self._callback:
            self._callback(region_info)
        elif cancelled and self._on_cancelled:
            self._on_cancelled()

    def _cleanup(self):
        """清理框选状态。"""
        self._active = False
        self._start_pos = None
        self._current_pos = None
        self._left_was_down = False
        self._status_text = ""

        if self._track_timer:
            self._track_timer.stop()
            self._track_timer = None

        self._parent.setCursor(Qt.CursorShape.ArrowCursor)
        self._parent.update()
        print("[RegionSelector] 框选模式结束")

    # ========== 绘制 ==========

    def paint(self, painter: QPainter):
        """在父控件的 paintEvent 中调用，绘制框选 UI。

        调用方（如 Overlay.paintEvent）应在绘制完自己的内容后调用此方法。
        """
        if not self._active:
            return

        # 半透明遮罩
        painter.fillRect(self._parent.rect(), QColor(*OVERLAY_SELECTION_OVERLAY))

        # 顶部状态栏
        if self._status_text:
            painter.fillRect(0, 0, self._parent.width(), 36, QColor(*OVERLAY_STATUS_BG))
            painter.setPen(QColor(str(CYBER_YELLOW)))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(20, 24, self._status_text)

        if not self._current_pos:
            return

        cx, cy = self._current_pos.x(), self._current_pos.y()

        # 未开始拖拽 → 显示十字准星
        if not self._start_pos:
            self._draw_crosshair(painter, self._current_pos)
            return

        # 拖拽中 → 显示选择矩形
        sx, sy = self._start_pos.x(), self._start_pos.y()
        x = min(sx, cx)
        y = min(sy, cy)
        w = abs(cx - sx)
        h = abs(cy - sy)

        # 清除矩形区域（透过遮罩看到原始画面）
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(x, y, w, h, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # 边框
        pen = QPen(QColor(str(OVERLAY_SELECTION_BORDER)), 2)
        painter.setPen(pen)
        painter.drawRect(x, y, w, h)

        # 尺寸文字
        painter.setPen(QColor(str(CYBER_CYAN)))
        painter.setFont(QFont("Microsoft YaHei", 11))
        painter.drawText(x + 5, y - 8, f"{w} × {h}")

    @staticmethod
    def _draw_crosshair(painter: QPainter, pos):
        """绘制十字准星。"""
        pw = painter.device().width()
        ph = painter.device().height()
        px, py = pos.x(), pos.y()

        pen = QPen(QColor(str(OVERLAY_CROSSHAIR_COLOR)), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(0, py, pw, py)
        painter.drawLine(px, 0, px, ph)

        painter.setPen(QPen(QColor(str(OVERLAY_CROSSHAIR_COLOR)), 2))
        painter.drawLine(px - 12, py, px + 12, py)
        painter.drawLine(px, py - 12, px, py + 12)

    # ========== 工具 ==========

    @staticmethod
    def _is_key_down(vk_code: int) -> bool:
        return (ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

    # ========== 静态工具：DPI 缩放 ==========

    @staticmethod
    def get_dpi_scale() -> float:
        """获取主显示器 DPI 缩放比例（物理像素 / 逻辑像素）。"""
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                return screen.logicalDotsPerInch() / 96.0
        except Exception:
            pass
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return dpi_x / 96.0
        except Exception:
            return 1.0
