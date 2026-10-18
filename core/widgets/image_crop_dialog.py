"""
[L4] CyberImageCropDialog — 背景图裁剪对话框

继承:
  - CyberCropCanvas: CyberWidgetMixin + QLabel（QLabel 原生绘制图片，
    本控件只在其上叠加选区遮罩；非 QWidget 零开始）
  - CyberImageCropDialog: CyberWidgetMixin + QDialog
依赖: core.widgets.base, Pillow（PIL，加载中文路径图片）, PySide6
职责:
  - 全屏/自适应展示待裁剪图片
  - 鼠标拖选、移动、8 手柄调整选区
  - 支持「锁定窗口比例 / 自由比例」切换（默认锁定窗口比例）
信号: 无（exec() 返回后读 crop_rect）

paintEvent 说明:
  与按钮类「自绘背景→super 画文字」相反，本控件是「super 先由 QLabel
  画图片→再自绘选区遮罩」，视觉层级要求如此；图片显示能力完全由
  QLabel 提供，自绘只做 QSS 做不到的选区。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize
from PySide6.QtGui import (
    QColor, QImage, QFont, QPainter, QPen, QBrush, QPixmap, QPalette,
)
from PySide6.QtWidgets import (
    QDialog, QLabel, QHBoxLayout, QVBoxLayout, QWidget,
)

from PIL import Image

from core.widgets.base import CyberWidgetMixin
from core.widgets.button import CyberButton

# 图片四周留白
_MARGIN: int = 16
# 手柄边长（显示坐标；4 的倍数）
_HANDLE_SIZE: int = 8
# 手柄命中额外容差
_HIT_PAD: int = 4
# 选区最小边长（原图像素）
_MIN_CROP: int = 8

# 8 手柄标识与光标
_HANDLE_CURSORS: dict[str, Qt.CursorShape] = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
    "n":  Qt.CursorShape.SizeVerCursor,
    "s":  Qt.CursorShape.SizeVerCursor,
    "e":  Qt.CursorShape.SizeHorCursor,
    "w":  Qt.CursorShape.SizeHorCursor,
}

# 角手柄 → 拖动时固定的对角点
_OPPOSITE: dict[str, str] = {
    "nw": "se", "se": "nw", "ne": "sw", "sw": "ne",
    "n": "s", "s": "n", "e": "w", "w": "e",
}


def _load_qimage(path: str) -> tuple[QImage | None, int, int]:
    """PIL 加载图片（支持中文路径）→ QImage，返回 (qimg, w, h)。"""
    try:
        pil = Image.open(path)
        if pil.mode != "RGB":
            pil = pil.convert("RGB")
        w, h = pil.size
        data = pil.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888)
        return qimg.copy(), w, h
    except Exception as e:
        print(f"[ImageCropDialog] 图片加载失败 {path}: {e}", flush=True)
        return None, 0, 0


class CyberCropCanvas(CyberWidgetMixin, QLabel):
    """图片显示 + 选区交互画布。

    选区统一用「原图坐标 QRectF」存储；显示时按缩放比换算。
    """

    def __init__(self, qimg: QImage, img_w: int, img_h: int, parent=None):
        QLabel.__init__(self, parent)

        self._src_qimg = qimg
        self._img_w = img_w
        self._img_h = img_h

        # 显示缩放比与图片区（显示坐标），由 setup_scale 计算
        self._scale: float = 1.0
        self._img_rect = QRectF(0, 0, img_w, img_h)

        # 选区（原图坐标）
        self._crop = QRectF()
        # 比例锁定状态与目标比例（宽/高）
        self._locked: bool = True
        self._ratio: float = 1.0

        # 拖动状态
        self._mode: str = "none"        # none/draw/move/resize
        self._handle: str = ""          # resize 时的手柄
        self._start_disp = QPointF()    # 按下位置（显示坐标）
        self._orig_crop = QRectF()

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ════════════════════════════════════
    #  对外配置
    # ════════════════════════════════════

    def setup_scale(self, max_w: int, max_h: int) -> QSize:
        """按可用区域计算缩放比与控件固定尺寸。返回控件应有尺寸。"""
        avail_w = max(96, max_w - 2 * _MARGIN)
        avail_h = max(96, max_h - 2 * _MARGIN)
        self._scale = min(avail_w / self._img_w, avail_h / self._img_h)
        dw = max(1, round(self._img_w * self._scale))
        dh = max(1, round(self._img_h * self._scale))

        self._img_rect = QRectF(_MARGIN, _MARGIN, dw, dh)
        pix = QPixmap.fromImage(self._src_qimg).scaled(
            dw, dh,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pix)

        size = QSize(dw + 2 * _MARGIN, dh + 2 * _MARGIN)
        self.setFixedSize(size)
        return size

    def configure(self, locked: bool, ratio: float):
        """设置比例锁定模式与目标比例（宽/高），并初始化默认选区。"""
        self._locked = locked
        self._ratio = max(0.1, ratio)
        self._crop = self._default_crop()

    def reset_crop(self):
        """重置为当前模式下的默认选区。"""
        self._crop = self._default_crop()
        self.update()

    def set_locked(self, locked: bool):
        """切换比例锁定；自由→锁定时把当前选区外扩约束到目标比例。"""
        if locked == self._locked:
            return
        self._locked = locked
        if locked:
            self._crop = self._fit_ratio_around(self._crop, expand=True)
        self.update()

    @property
    def crop_rect(self) -> tuple[int, int, int, int] | None:
        """确认时调用：返回原图整数坐标 (x, y, w, h)。"""
        if self._crop.isEmpty():
            return None
        x = max(0, round(self._crop.x()))
        y = max(0, round(self._crop.y()))
        w = min(self._img_w - x, round(self._crop.width()))
        h = min(self._img_h - y, round(self._crop.height()))
        return (x, y, max(1, w), max(1, h))

    # ════════════════════════════════════
    #  默认选区
    # ════════════════════════════════════

    def _default_crop(self) -> QRectF:
        """图片内最大居中选区（锁定时按目标比例；自由时取 90%）。"""
        iw, ih = self._img_w, self._img_h
        if not self._locked:
            m = 0.05
            return QRectF(iw * m, ih * m, iw * (1 - 2 * m), ih * (1 - 2 * m))

        if iw / ih > self._ratio:
            h = ih
            w = ih * self._ratio
            return QRectF((iw - w) / 2, 0, w, h)
        w = iw
        h = iw / self._ratio
        return QRectF(0, (ih - h) / 2, w, h)

    # ════════════════════════════════════
    #  坐标换算
    # ════════════════════════════════════

    def _to_disp(self, p: QPointF) -> QPointF:
        return QPointF(
            self._img_rect.left() + p.x() * self._scale,
            self._img_rect.top() + p.y() * self._scale,
        )

    def _to_orig(self, p: QPointF) -> QPointF:
        qp = QPointF(
            (p.x() - self._img_rect.left()) / self._scale,
            (p.y() - self._img_rect.top()) / self._scale,
        )
        return self._clamp_orig(qp)

    def _clamp_orig(self, p: QPointF) -> QPointF:
        return QPointF(
            min(max(p.x(), 0.0), float(self._img_w)),
            min(max(p.y(), 0.0), float(self._img_h)),
        )

    # ════════════════════════════════════
    #  手柄（显示坐标）
    # ════════════════════════════════════

    def _handle_rects(self) -> dict[str, QRectF]:
        c_disp = self._crop_display()
        cx1, cy1 = c_disp.left(), c_disp.top()
        cx2, cy2 = c_disp.right(), c_disp.bottom()
        cxm, cym = c_disp.center().x(), c_disp.center().y()
        h = _HANDLE_SIZE
        pts = {
            "nw": (cx1, cy1), "n": (cxm, cy1), "ne": (cx2, cy1),
            "e":  (cx2, cym), "se": (cx2, cy2),
            "s":  (cxm, cy2), "sw": (cx1, cy2), "w": (cx1, cym),
        }
        return {
            k: QRectF(x - h / 2, y - h / 2, h, h) for k, (x, y) in pts.items()
        }

    def _hit_handle(self, pos: QPointF) -> str:
        pad = _HIT_PAD
        for name, r in self._handle_rects().items():
            if r.adjusted(-pad, -pad, pad, pad).contains(pos):
                return name
        return ""

    def _crop_display(self) -> QRectF:
        tl = self._to_disp(self._crop.topLeft())
        br = self._to_disp(self._crop.bottomRight())
        return QRectF(tl, br)

    # ════════════════════════════════════
    #  鼠标
    # ════════════════════════════════════

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = QPointF(event.position())
        self._start_disp = pos
        self._orig_crop = QRectF(self._crop)

        handle = self._hit_handle(pos)
        if handle:
            self._mode = "resize"
            self._handle = handle
        elif self._crop_display().contains(pos):
            self._mode = "move"
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self._mode = "draw"
        event.accept()

    def mouseMoveEvent(self, event):
        pos = QPointF(event.position())

        # 拖动中
        if self._mode == "draw":
            anchor = self._to_orig(self._start_disp)
            cur = self._to_orig(pos)
            self._crop = self._build_drag_rect(anchor, cur)
            self.update()
        elif self._mode == "move":
            delta_disp = pos - self._start_disp
            dx = delta_disp.x() / self._scale
            dy = delta_disp.y() / self._scale
            self._crop = self._clamp_move(QRectF(self._orig_crop), dx, dy)
            self.update()
        elif self._mode == "resize":
            self._crop = self._build_resize(self._to_orig(pos))
            self.update()
        else:
            # 悬停光标
            handle = self._hit_handle(pos)
            if handle:
                self.setCursor(_HANDLE_CURSORS[handle])
            elif self._crop_display().contains(pos):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        self._mode = "none"
        self._handle = ""
        self.setCursor(Qt.CursorShape.CrossCursor)
        event.accept()

    # ════════════════════════════════════
    #  选区构造
    # ════════════════════════════════════

    def _build_drag_rect(self, anchor: QPointF, cur: QPointF) -> QRectF:
        """从起点/当前点构造选区（锁定时按比例约束）。"""
        w = abs(cur.x() - anchor.x())
        h = abs(cur.y() - anchor.y())
        if self._locked:
            w, h = self._ratio_dims(w, h)
        x = anchor.x() if cur.x() >= anchor.x() else anchor.x() - w
        y = anchor.y() if cur.y() >= anchor.y() else anchor.y() - h
        return self._normalize(QRectF(x, y, w, h))

    def _clamp_move(self, rect: QRectF, dx: float, dy: float) -> QRectF:
        """平移选区并限制在图片范围内。"""
        dx = min(max(dx, -rect.left()), self._img_w - rect.right())
        dy = min(max(dy, -rect.top()), self._img_h - rect.bottom())
        rect.translate(dx, dy)
        return rect

    def _build_resize(self, mouse_orig: QPointF) -> QRectF:
        """手柄调整。

        - 角手柄：对角固定，取拖动主导维度，锁定时保持比例
        - 边手柄：对边固定，锁定时另一维度以中心对称变化
        """
        o = self._orig_crop
        hname = self._handle

        # ── 边手柄 ──
        if hname in ("e", "w", "n", "s"):
            x1, y1, x2, y2 = o.left(), o.top(), o.right(), o.bottom()
            if hname == "e":
                x2 = mouse_orig.x()
                if self._locked:
                    cx = (x1 + x2) / 2
                    hh = (x2 - x1) / self._ratio / 2
                    y1, y2 = (o.center().y() - hh), (o.center().y() + hh)
            elif hname == "w":
                x1 = mouse_orig.x()
                if self._locked:
                    hh = (x2 - x1) / self._ratio / 2
                    y1, y2 = (o.center().y() - hh), (o.center().y() + hh)
            elif hname == "s":
                y2 = mouse_orig.y()
                if self._locked:
                    cy = (y1 + y2) / 2
                    ww = (y2 - y1) * self._ratio / 2
                    x1, x2 = (o.center().x() - ww), (o.center().x() + ww)
            else:  # n
                y1 = mouse_orig.y()
                if self._locked:
                    ww = (y2 - y1) * self._ratio / 2
                    x1, x2 = (o.center().x() - ww), (o.center().x() + ww)
            return self._normalize(QRectF(x1, y1, x2 - x1, y2 - y1))

        # ── 角手柄：固定对角 ──
        fixed = {
            "nw": (o.right(), o.bottom()),
            "ne": (o.left(),  o.bottom()),
            "sw": (o.right(), o.top()),
            "se": (o.left(),  o.top()),
        }[hname]
        fx, fy = fixed

        if not self._locked:
            # 自由：固定点与鼠标点为两角
            x1, y1 = min(fx, mouse_orig.x()), min(fy, mouse_orig.y())
            w, h = abs(mouse_orig.x() - fx), abs(mouse_orig.y() - fy)
            return self._normalize(QRectF(x1, y1, w, h))

        # 锁定：固定点不动，按拖动主导维度定尺寸，方向跟随鼠标
        w, h = self._ratio_dims(
            abs(mouse_orig.x() - fx), abs(mouse_orig.y() - fy)
        )
        x1 = fx - w if mouse_orig.x() < fx else fx
        y1 = fy - h if mouse_orig.y() < fy else fy
        return self._normalize(QRectF(x1, y1, w, h))

    def _ratio_dims(self, w: float, h: float) -> tuple[float, float]:
        """按目标比例归一尺寸：以拖动量较大的维度为主。"""
        if w <= 0 and h <= 0:
            return 0.0, 0.0
        if w / self._ratio >= h:
            return max(w, 0.0), max(w / self._ratio, 0.0)
        return max(h * self._ratio, 0.0), max(h, 0.0)

    def _fit_ratio_around(self, rect: QRectF, expand: bool = True) -> QRectF:
        """把已有选区约束到目标比例（外扩包含原选区，再限制进图片范围）。"""
        w, h = rect.width(), rect.height()
        if w / self._ratio >= h:
            h = w / self._ratio
        else:
            w = h * self._ratio if expand else w
        r = QRectF(rect.center().x() - w / 2,
                   rect.center().y() - h / 2, w, h)
        return self._normalize(r)

    def _normalize(self, rect: QRectF) -> QRectF:
        """规则化：空/负值校正，平移进图片范围，保证最小边长。"""
        rect = rect.normalized()
        if rect.width() < _MIN_CROP:
            rect.setWidth(_MIN_CROP)
        if rect.height() < _MIN_CROP:
            rect.setHeight(_MIN_CROP)
        # 整体平移进范围
        if rect.left() < 0:
            rect.translate(-rect.left(), 0)
        if rect.top() < 0:
            rect.translate(0, -rect.top())
        if rect.right() > self._img_w:
            rect.translate(self._img_w - rect.right(), 0)
        if rect.bottom() > self._img_h:
            rect.translate(0, self._img_h - rect.bottom())
        return rect

    # ════════════════════════════════════
    #  绘制（super 画图片 → 自绘选区）
    # ════════════════════════════════════

    def paintEvent(self, event):
        super().paintEvent(event)  # QLabel 绘制 pixmap

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self._img_rect
        c = self._crop_display()

        # 选区外四块暗化遮罩（主题底色 + alpha，避开选区）
        mask = self.token_color("alias.bg.base")
        mask.setAlpha(150)
        brush = QBrush(mask)
        for xr, yr, ww, hh in (
            (r.left(), r.top(), r.width(), c.top() - r.top()),
            (r.left(), c.bottom(), r.width(), r.bottom() - c.bottom()),
            (r.left(), c.top(), c.left() - r.left(), c.height()),
            (c.right(), c.top(), r.right() - c.right(), c.height()),
        ):
            if ww > 0 and hh > 0:
                painter.fillRect(QRectF(xr, yr, ww, hh), brush)

        # 选区边框
        pen = QPen(self.token_color("alias.accent.primary"))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawRect(c)

        # 8 手柄（白底黄边）
        handle_pen = QPen(self.token_color("alias.accent.primary"))
        handle_pen.setWidthF(1.0)
        painter.setPen(handle_pen)
        painter.setBrush(QBrush(self.token_color("alias.text.primary")))
        for hr in self._handle_rects().values():
            painter.drawRect(hr)

        # 选区尺寸（原图坐标，便于判断）
        painter.setPen(self.token_color("alias.accent.primary"))
        f = QFont()
        f.setPointSize(9)
        painter.setFont(f)
        label = f"{round(self._crop.width())} × {round(self._crop.height())}"
        painter.drawText(
            QRectF(c.left(), c.bottom() + 4, 140, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            label,
        )

        painter.end()


# ══════════════════════════════════════════════
#  对话框
# ══════════════════════════════════════════════

class CyberImageCropDialog(CyberWidgetMixin, QDialog):
    """背景图裁剪对话框。

    Args:
        image_path: 原图路径
        window_ratio: 主窗口宽高比（锁定比例时使用）
        default_locked: 是否默认锁定窗口比例

    用法::

        dlg = CyberImageCropDialog(path, window_ratio=shell.width()/shell.height())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            crop = dlg.crop_rect   # (x, y, w, h)
    """

    def __init__(
        self,
        image_path: str,
        window_ratio: float = 1.4,
        default_locked: bool = True,
        parent: QWidget | None = None,
    ):
        QDialog.__init__(self, parent)

        qimg, iw, ih = _load_qimage(image_path)
        if qimg is None:
            self._valid = False
            return
        self._valid = True

        self.setWindowTitle("裁剪背景图片")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # 对话框背景（token 底色；走 palette，不用 stylesheet）
        pal = self.palette()
        pal.setColor(
            QPalette.ColorRole.Window, self.token_color("alias.bg.raised")
        )
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # ── 画布（按屏幕可用空间缩放） ──
        screen = self.screen().availableGeometry()
        self._canvas = CyberCropCanvas(qimg, iw, ih, self)
        self._canvas.setup_scale(
            int(screen.width() * 0.82),
            int(screen.height() * 0.72),
        )
        self._canvas.configure(default_locked, window_ratio)

        # ── 底部控制栏 ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(self.space("spacing.md", 12))
        layout.addWidget(self._canvas)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._btn_ratio = CyberButton(
            "窗口比例", variant="solid" if default_locked else "ghost"
        )
        self._btn_free = CyberButton(
            "自由比例", variant="ghost" if default_locked else "solid"
        )
        self._btn_ratio.setFixedWidth(96)
        self._btn_free.setFixedWidth(96)
        self._btn_ratio.clicked.connect(lambda: self._switch_locked(True))
        self._btn_free.clicked.connect(lambda: self._switch_locked(False))
        bottom.addWidget(self._btn_ratio)
        bottom.addWidget(self._btn_free)

        reset_btn = CyberButton("重置选区", variant="ghost")
        reset_btn.clicked.connect(self._canvas.reset_crop)
        bottom.addWidget(reset_btn)

        bottom.addStretch()

        ok_btn = CyberButton("确认裁剪", variant="solid")
        cancel_btn = CyberButton("取消", variant="ghost")
        ok_btn.setFixedWidth(96)
        cancel_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(ok_btn)
        bottom.addWidget(cancel_btn)

        layout.addLayout(bottom)
        self.setFixedSize(self.sizeHint())

    # ── 结果 ──

    @property
    def is_valid(self) -> bool:
        """图片是否成功加载。"""
        return self._valid

    @property
    def crop_rect(self) -> tuple[int, int, int, int] | None:
        """用户确认的选区（原图坐标 x,y,w,h）。"""
        return self._canvas.crop_rect

    # ── 内部 ──

    def _switch_locked(self, locked: bool) -> None:
        self._canvas.set_locked(locked)
        self._btn_ratio.variant = "solid" if locked else "ghost"
        self._btn_free.variant = "ghost" if locked else "solid"
