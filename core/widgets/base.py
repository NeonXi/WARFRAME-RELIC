"""
[L4] core.widgets.base — Cyber Widget 基础设施 CyberWidgetMixin

继承: 无(Qt 原生控件的多重继承 Mixin)
依赖: core.tokens.manager (只此一个外部)
职责: 切角绘制 + 状态机 + Token 访问接口

赛博风格 UI 组件的混入基类,提供:
- Token 访问接口(token / space)
- 交互状态机(normal/hover/pressed/focused/disabled/selected)
- 切角路径生成(带缓存)
- 自绘背景方法(切角 + 外发光)

设计原则(Mixin 模式):
    本类不继承 QWidget,不能单独实例化。
    使用时通过多重继承与 Qt 原生控件组合::

        class CyberButton(CyberWidgetMixin, QPushButton):
            def __init__(self, text="", parent=None):
                QPushButton.__init__(self, text, parent)  # 显式调用目标基类
                # ... CyberWidgetMixin 无需 __init__

        class MyPanel(CyberWidgetMixin, QFrame):
            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self._draw_chamfered_bg(painter)
                # QFrame 无自身绘制内容,无需 super()

See Also:
    ui-framework-design.md §5.2 Cyber Widget 框架 — Mixin 设计模式
    ui-framework-design.md 附录 B: 多重继承注意事项

## AI 硬约束 — 修改本文件前必读
归属层:    [L4] (core/widgets/)
允许依赖:  core.tokens.manager (唯一外部依赖)
禁止依赖:  core.services/* / core.pages/* / core.state/* / data/*
           (Mixin 是 UI 基础设施,绝不调业务)
必读规范:  .trae/rules/开发规范.md §6.4 (L4/L5 控件层)

本文件相关红线(出自规范自查卡):
- ✗ 禁止: __init__ 用 super().__init__() → 必须显式 Qxxx.__init__(self, ...)
- ✗ 禁止: paintEvent 里忘记 super() → 文字/快捷键会失效
- ✗ 禁止: paintEvent 顺序写反 → 必须 QPainter → 自绘 → super()
- ✗ 禁止: 写死颜色 "#FF0000" / 尺寸 26 → 必须 self.token() / self.space()
- ✗ 禁止: 私有属性用 _xxx 命名 → 必须 _cyber_xxx 前缀(避免与 Qt 内部冲突)
- ✗ 禁止: 调 Service 或发网络请求 → Widget 只绘制和发信号

写入/修改前自检:
- [ ] 颜色/尺寸都从 token/space 取,无硬编码
- [ ] 私有属性加 _cyber_ 前缀
- [ ] paintEvent 顺序: QPainter → 自绘 → super()
- [ ] 事件处理函数末尾都 super()
- [ ] 没引入 services/ 或 data/ 的 import

OPTIONS:
如对 Mixin 多重继承有疑义,先读 ui-framework-design.md §5.2,
再开始改动,不要"走捷径"调 super()。
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from PySide6.QtGui import QPainter, QColor
    from PySide6.QtCore import QPointF, QRectF, Qt


# Widget 层统一日志器（token 缺失等降级场景告警用）
_cyber_logger = logging.getLogger("core.widgets")


class CyberWidgetMixin:
    """赛博风格混入类 — 提供切角绘制、状态机、Token 访问能力。

    不继承 QWidget，不能单独实例化。必须与一个 QWidget 子类通过多重继承组合使用。

    Attributes:
        _state: 当前交互状态，可选值见 VALID_STATES
        _path_cache: 切角路径缓存（避免 resize 时重复计算）
        _cache_rect_size: 缓存对应的矩形尺寸
    """

    # ── 合法状态列表 ──
    VALID_STATES = {"normal", "hover", "pressed", "focused", "disabled", "selected"}

    # ── 类级别属性（Mixin 共享）──
    _state: str = "normal"
    _path_cache: Optional[object] = None  # QPolygonF 实例
    _cache_rect_size: Optional[tuple] = None

    # ── 全局沉浸模式（类级；由 AppShell 经 set_immersive_global 设置）──
    # 类级保证：页面懒创建的新卡片也自动继承当前沉浸状态
    _cyber_immersive: bool = False
    _cyber_immersive_strength: int = 70  # 0-100，越大底色越透
    # 沉浸底色预设覆写色（None=沿用 token 当前主题底色；非 None=覆写 RGB）
    _cyber_immersive_color_override: Optional[object] = None  # QColor 实例

    @classmethod
    def set_immersive_global(cls, enabled: bool, strength: int = 70) -> None:
        """设置全局沉浸模式状态（控件层只存状态、不订阅业务）。

        Args:
            enabled: 是否开启沉浸
            strength: 沉浸强度 0-100（底色折减比例；100=底色全透）
        """
        cls._cyber_immersive = bool(enabled)
        cls._cyber_immersive_strength = max(0, min(100, int(strength)))

    @classmethod
    def set_immersive_color_mode(cls, mode: str) -> None:
        """设置沉浸模式卡片底色预设（控件层只存状态、不订阅业务）。

        Args:
            mode: "theme"=沿用 token 当前主题底色(默认,覆写为 None)
                  "black"=沉浸时覆写为纯黑(用 surface.overlay token,失败纯黑兜底)
        """
        if mode == "black":
            from PySide6.QtGui import QColor
            c = QColor(0, 0, 0)
            try:
                from core.tokens.manager import TokenManager
                v = TokenManager.instance().get("surface.overlay")
                if v:
                    tc = QColor(str(v))
                    if tc.isValid():
                        c = tc
            except Exception:
                pass
            cls._cyber_immersive_color_override = c
        else:
            cls._cyber_immersive_color_override = None

    def _cyber_immersive_alpha(self, normal_alpha: float) -> float:
        """底色 alpha 折减：非沉浸原值返回；沉浸时按强度保留剩余比例。

        例：normal=0.85、strength=70 → 0.85×0.3 ≈ 0.26。
        """
        if not self._cyber_immersive:
            return normal_alpha
        from core.widgets import immersive
        return immersive.alpha_factor(normal_alpha)

    def _cyber_immersive_resolve_bg(self, key: str, alpha: float) -> "QColor":
        """从 token 取底色 → 沉浸黑色模式时覆写 RGB(保留 alpha) → 折减 alpha。

        统一入口,供 CyberCard/CyberPanel 的 paintEvent 调用。
        计算实现收敛在 core/widgets/immersive.py(唯一实现),本方法
        只保留 Mixin API 形态,内部转发。

        Args:
            key: 颜色 token 路径(如 "components.card.bg")
            alpha: 非沉浸时的目标 alpha(如 0.85)

        Returns:
            最终 QColor(已应用覆写和 alpha 折减)
        """
        from core.widgets import immersive
        return immersive.resolve_qcolor(self.token_color(key), alpha)

    def _cyber_resolve_nav_bg_color(self, fallback_str: str) -> "QColor":
        """导航标签底色:沉浸黑色模式时覆写 RGB,保留默认 alpha=255。

        与 _cyber_immersive_resolve_bg 区别:nav.bg 取自字符串(可来自
        theme_proxy 兜底),不做 alpha 折减(折减由调用方后续 setAlphaF)。

        Args:
            fallback_str: 原始 token 解析出的颜色字符串

        Returns:
            QColor(沉浸黑色模式时为纯黑,否则为原色)
        """
        from PySide6.QtGui import QColor
        from core.widgets import immersive
        return immersive.override_rgb(QColor(fallback_str))

    def _cyber_immersive_resolve_token_str(
        self,
        key: str,
        alpha: float = 1.0,
    ) -> str:
        """QSS 字符串入口:沉浸黑色模式时返回覆写后的颜色 hex 字符串。

        与 ``_cyber_immersive_resolve_bg`` 对应(QColor 路径用于 paintEvent,
        本方法字符串路径用于 QSS setStyleSheet)。实现收敛在
        core/widgets/immersive.py,本方法只保留 Mixin API 形态。

        Args:
            key: 颜色 token 路径(如 ``alias.bg.base``)
            alpha: 非沉浸时的目标 alpha(如 0.85)

        Returns:
            QSS 可直接拼接的颜色字符串(``#AARRGGBB``)
        """
        from PySide6.QtGui import QColor
        from core.widgets import immersive
        # 走 token_color(带三级兜底,不抛异常),再进沉浸覆写
        return immersive.resolve_qcolor(
            self.token_color(key), alpha
        ).name(QColor.NameFormat.HexArgb)

    def _cyber_immersive_resolve_bg_qcolor(
        self,
        qcolor: "QColor",
        alpha: float,
    ) -> "QColor":
        """QColor 路径入口:沉浸黑色模式时覆写 RGB,折减 alpha。

        与 ``_cyber_immersive_resolve_bg`` 区别:本方法接受调用方已取好的
        QColor(适合有 try/except 兜底逻辑、或多 token 切换的场景,如
        CyberLineEdit / CyberComboBox / HotkeyEdit 的状态机)。
        实现收敛在 core/widgets/immersive.py。

        Args:
            qcolor: 调用方已用 token_color(...) 取好的 QColor
            alpha: 非沉浸时的目标 alpha(如 0.85)

        Returns:
            最终 QColor(已应用 RGB 覆写和 alpha 折减)
        """
        from core.widgets import immersive
        return immersive.resolve_qcolor(qcolor, alpha)

    # ════════════════════════════════════════════════
    #  Token 访问接口
    # ══════════════════════════════════════════════

    def token(self, key: str, default: Optional[str] = None) -> str:
        """获取颜色/样式 token 的字符串值。

        这是组件内部获取 token 的主要方式。
        返回字符串类型（hex 颜色或原始值），由调用方决定如何使用。

        Args:
            key: 点分路径，如 "bg.raised"、"accent.primary"、
                 "components.button.solid.fill"
            default: key 不存在时的兜底字符串（不给则按 TokenManager
                     默认行为抛出 TokenResolveError）

        Returns:
            解析后的字符串值（如 "#0E0E24"、"transparent"）

        Note:
            如果需要 QColor 对象，请使用 token_color() 方法
            （该方法内置完整降级保护，永不抛异常）。
        """
        from core.tokens.manager import TokenManager
        tm = TokenManager.instance()
        result = tm.get(key, default=default) if default is not None else tm.get(key)
        if isinstance(result, str):
            return result
        return str(result)

    def token_color(
        self,
        key: str,
        default: "Optional[QColor | str]" = None,
    ) -> "QColor":
        """获取颜色 token 并返回 QColor 对象（防御性，永不抛异常）。

        降级保证：key 不存在、解析失败或颜色串非法时，绘制不会中断
        （避免出现"控件整块不显示"），按以下顺序回退：

        1. 调用方提供的 ``default``（QColor 或颜色字符串）；
        2. 已知必然存在的安全 token ``alias.bg.raised``；
        3. 纯黑 ``QColor(0, 0, 0)``。

        每次降级都会通过 ``core.widgets`` 日志器输出 warning，
        便于在控制台发现 token 配置问题。

        Args:
            key: 颜色 token 路径
            default: 可选兜底色

        Returns:
            QColor 实例（始终有效）
        """
        from PySide6.QtGui import QColor
        from core.tokens.manager import TokenManager

        def _fallback(reason: str) -> "QColor":
            _cyber_logger.warning(
                "token_color 取色失败 key=%s (%s)，已使用兜底色", key, reason
            )
            if default is not None:
                try:
                    c = QColor(default) if isinstance(default, str) else QColor(default)
                    if c.isValid():
                        return c
                except Exception:
                    pass
            # 兜底链：已知存在的安全 token → 纯黑
            try:
                c = QColor(TokenManager.instance().get("alias.bg.raised"))
                if c.isValid():
                    return c
            except Exception:
                pass
            return QColor(0, 0, 0)

        try:
            value = TokenManager.instance().get(key)

            if isinstance(value, str):
                if value.lower() == "transparent":
                    return QColor(0, 0, 0, 0)
                c = QColor(value)
                return c if c.isValid() else _fallback("非法颜色字符串")

            if isinstance(value, (int, float)):
                v = max(0, min(255, int(value)))
                return QColor(v, v, v)

            c = QColor(value)
            return c if c.isValid() else _fallback("非法颜色值")
        except Exception as exc:
            return _fallback(str(exc))

    def space(self, key: str, default: int = 0) -> int:
        """获取空间尺寸 token 的整数值。

        Args:
            key: Space token 路径，如 "height.btn_md"、"spacing.lg"、"corner.md"
            default: 找不到时的默认值

        Returns:
            尺寸整数值（像素），默认 default
        """
        from core.tokens.manager import TokenManager
        return TokenManager.instance().space(key, default=default)

    def copy(self, key: str, default: str = "", **kwargs) -> str:
        """获取文案 token 字符串，支持模板变量替换。

        Args:
            key: 文案 token 路径（不含 "copy." 前缀）
            default: key 不存在时的默认返回值
            **kwargs: 模板变量

        Returns:
            解析后的文案字符串
        """
        from core.tokens.manager import TokenManager
        return TokenManager.instance().copy(key, default, **kwargs)

    # ══════════════════════════════════════════════
    #  主题切换响应(ThemeManager 统一入口)
    # ══════════════════════════════════════════════

    def _cyber_subscribe_theme(self) -> None:
        """订阅全局主题切换信号(供子类 __init__ 末尾调用)。

        自绘主背景在 paintEvent 里读 token,天然响应主题切换;
        但通过 setStyleSheet / QPalette 内联的颜色(token 内插字符串)
        会被固化,需要在 theme_changed 时重建。

        子类若有 QSS/palette 颜色,重写 cyber_refresh_style() 重建即可;
        若纯自绘无 QSS 颜色,无需重写(本方法仍会调 update() 触发重绘)。
        """
        try:
            from core.theme_manager import ThemeManager
            ThemeManager.instance().theme_changed.connect(self._cyber_on_theme_changed)
        except Exception:
            pass  # 测试环境无 ThemeManager 时跳过

    def _cyber_on_theme_changed(self, _preset_name: str) -> None:
        """theme_changed 信号槽:重建 QSS/palette + 触发重绘。"""
        try:
            self.cyber_refresh_style()
        except Exception:
            pass
        self.update()

    def cyber_refresh_style(self) -> None:
        """重建 QSS / QPalette 中的 token 颜色(子类按需重写)。

        默认空实现;只有用 setStyleSheet(f"...{token}...") 或
        palette.setColor(token) 内联颜色的控件需要重写。
        自绘背景无需重写(paintEvent 自动读新 token)。
        """
        pass

    # ══════════════════════════════════════════════
    #  状态机
    # ══════════════════════════════════════════════

    @property
    def state(self) -> str:
        """当前交互状态（只读）。"""
        return self._state

    def _set_state(self, new_state: str) -> None:
        """切换交互状态并触发重绘。

        Args:
            new_state: 目标状态，必须是 VALID_STATES 之一
        """
        if new_state not in self.VALID_STATES:
            raise ValueError(
                f"无效的状态 '{new_state}'，合法值: {self.VALID_STATES}"
            )
        old = self._state
        if old != new_state:
            self._state = new_state
            # 触发重绘（依赖 self 是 QWidget 子类的隐式契约）
            widget_self: "QWidget" = self  # type: ignore[assignment]
            widget_self.update()

    # ══════════════════════════════════════════════
    #  标准事件处理（子类应调用或覆盖）
    # ══════════════════════════════════════════════

    def cyber_enter_event(self, event) -> None:
        """鼠标进入 → hover 态。在 enterEvent 中调用。"""
        if self._state != "disabled":
            self._set_state("hover")

    def cyber_leave_event(self, event) -> None:
        """鼠标离开 → normal 态。在 leaveEvent 中调用。"""
        if self._state not in ("disabled", "pressed"):
            self._set_state("normal")

    def cyber_mouse_press_event(self, event) -> None:
        """鼠标按下 → pressed 态。在 mousePressEvent 中调用。"""
        from PySide6.QtCore import Qt
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._state != "disabled"
        ):
            self._set_state("pressed")

    def cyber_mouse_release_event(self, event) -> None:
        """鼠标释放 → hover 或 normal 态。在 mouseReleaseEvent 中调用。"""
        from PySide6.QtCore import Qt
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._state == "pressed"
        ):
            self._set_state("hover")

    def cyber_focus_in_event(self, event) -> None:
        """获得焦点 → focused 态。在 focusInEvent 中调用。"""
        self._set_state("focused")

    def cyber_focus_out_event(self, event) -> None:
        """失去焦点 → normal 态。在 focusOutEvent 中调用。"""
        self._set_state("normal")

    # ══════════════════════════════════════════════
    #  切角路径生成（带缓存）
    # ══════════════════════════════════════════════

    def _chamfered_path(
        self,
        rect: "QRectF",
        corner_size: float,
        mode: str = "all",
    ) -> "object":
        """生成切角矩形路径。

        支持两种切角模式：
        - ``"all"``   : 四角对称切角（传统赛博风）
        - ``"br"``    : 仅右下角切角（赛博朋克标志性风格）

        结果缓存到实例属性中，以 (width, height, mode) 为键。
        当窗口 size 不变时直接返回缓存，避免重复计算。

        Args:
            rect: 控件矩形区域
            corner_size: 切角大小（像素），从每个角切去的直角边长
            mode: 切角模式，"all" 或 "br"

        Returns:
            QPainterPath 实例
        """
        from PySide6.QtGui import QPainterPath
        from PySide6.QtCore import QPointF

        size = (rect.width(), rect.height(), mode)

        # 缓存命中
        if (
            hasattr(self, "_path_cache")
            and self._path_cache is not None
            and getattr(self, "_cache_rect_size", None) == size
        ):
            return self._path_cache  # type: ignore[return-value]

        c = corner_size
        path = QPainterPath()

        if mode == "br":
            # ── 赛博朋克风格：仅右下角切角 ──
            path.moveTo(QPointF(rect.left(), rect.top()))
            path.lineTo(QPointF(rect.right(), rect.top()))
            path.lineTo(QPointF(rect.right(), rect.bottom() - c))
            path.lineTo(QPointF(rect.right() - c, rect.bottom()))
            path.lineTo(QPointF(rect.left(), rect.bottom()))
            path.closeSubpath()
        else:
            # ── 四角对称切角（默认）──
            path.moveTo(QPointF(rect.left() + c, rect.top()))
            path.lineTo(QPointF(rect.right() - c, rect.top()))
            path.lineTo(QPointF(rect.right(), rect.top() + c))
            path.lineTo(QPointF(rect.right(), rect.bottom() - c))
            path.lineTo(QPointF(rect.right() - c, rect.bottom()))
            path.lineTo(QPointF(rect.left() + c, rect.bottom()))
            path.lineTo(QPointF(rect.left(), rect.bottom() - c))
            path.lineTo(QPointF(rect.left(), rect.top() + c))
            path.closeSubpath()

        self._path_cache = path
        self._cache_rect_size = size
        return path

    # ══════════════════════════════════
    #  玻璃效果绘制（毛玻璃风格）
    # ══════════════════════════════════

    def _is_glass_mode(self) -> bool:
        """检查当前是否为玻璃拟态模式。"""
        from core.tokens.manager import TokenManager
        return TokenManager.instance().current_preset == "glassmorphism"

    def _draw_glass_bg(
        self,
        painter: "QPainter",
        rect: "QRectF",
        corner: float,
        bg_color: "QColor",
        border_color: "QColor",
        border_width: int = 1,
    ) -> None:
        """绘制玻璃质感背景：半透明填充 + 细边框 + 微弱高光。

        在玻璃拟态模式下替代 _draw_chamfered_bg 使用。
        控件需设置 WA_TranslucentBackground 才能透出下层背景。

        Args:
            painter: 已初始化的 QPainter（需开启 Antialiasing）
            rect: 绘制区域
            corner: 切角大小
            bg_color: 背景色（QColor，建议带 alpha）
            border_color: 边框色（QColor）
            border_width: 边框宽度（默认 1）
        """
        from PySide6.QtGui import QBrush, QPen, QLinearGradient, QColor

        # 应用沉浸强度：折减 alpha
        if self._cyber_immersive:
            strength = max(0, min(100, int(self._cyber_immersive_strength)))
            alpha_factor = 1.0 - strength / 100.0
            bg_color = QColor(bg_color)
            bg_color.setAlphaF(bg_color.alphaF() * alpha_factor)

        path = self._chamfered_path(rect, corner)
        painter.setClipPath(path)

        # 1. 半透明填充（透出下层模糊背景）
        painter.fillPath(path, QBrush(bg_color))

        # 2. 微弱顶部高光（模拟玻璃反光）
        highlight = QLinearGradient(0, 0, 0, rect.height() * 0.3)
        highlight.setColorAt(0, QColor(255, 255, 255, 20))  # 微弱白色
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(highlight))

        # 3. 细边框
        if border_color.alpha() > 0:
            painter.setPen(QPen(border_color, border_width))
            painter.drawPath(path)

    def _draw_glass_bg_with_noise(
        self,
        painter: "QPainter",
        rect: "QRectF",
        corner: float,
        bg_color: "QColor",
        border_color: "QColor",
        noise_opacity: float = 0.03,
    ) -> None:
        """绘制带噪点的毛玻璃背景：半透明填充 + 噪点纹理 + 细边框。

        Args:
            painter: 已初始化的 QPainter（需开启 Antialiasing）
            rect: 绘制区域
            corner: 切角大小
            bg_color: 背景色（QColor，建议带 alpha）
            border_color: 边框色（QColor）
            noise_opacity: 噪点透明度 0-1（默认 0.03）
        """
        from PySide6.QtGui import QBrush, QPen, QLinearGradient, QColor
        import random

        path = self._chamfered_path(rect, corner)
        painter.setClipPath(path)

        # 1. 半透明填充
        painter.fillPath(path, QBrush(bg_color))

        # 2. 噪点纹理（模拟玻璃颗粒感）
        if noise_opacity > 0:
            noise_color = QColor(255, 255, 255, int(noise_opacity * 255))
            painter.setPen(QPen(noise_color, 1))
            # 在区域内随机画噪点（限制数量避免性能问题）
            noise_count = int(rect.width() * rect.height() * 0.0005)
            noise_count = min(noise_count, 200)  # 上限 200 个
            for _ in range(noise_count):
                x = random.randint(int(rect.left()), int(rect.right()))
                y = random.randint(int(rect.top()), int(rect.bottom()))
                painter.drawPoint(x, y)

        # 3. 微弱顶部高光
        highlight = QLinearGradient(0, 0, 0, rect.height() * 0.3)
        highlight.setColorAt(0, QColor(255, 255, 255, 25))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(highlight))

        # 4. 细边框
        if border_color.alpha() > 0:
            painter.setPen(QPen(border_color, 1))
            painter.drawPath(path)

    def _invalidate_path_cache(self) -> None:
        """使切角路径缓存失效（在 resizeEvent 中调用）。"""
        self._path_cache = None
        self._cache_rect_size = None

    # ══════════════════════════════════════════════
    #  自绘：切角背景 + 外发光
    # ══════════════════════════════════════════════

    def _draw_chamfered_bg(
        self,
        painter: "QPainter",
        corner_key: str = "corner.md",
        bg_key: str | None = None,
        glow_key: str | None = None,
        glow_opacity_map: dict[str, float] | None = None,
        mode: str = "all",
    ) -> None:
        """绘制切角背景 + 可选的外发光效果。

        在 paintEvent 中最先调用此方法，然后再调 super().paintEvent()。

        Args:
            painter: 已初始化的 QPainter（需开启 Antialiasing）
            corner_key: 切角大小的 space token 键名（默认 "corner.md"）
            bg_key: 背景颜色的 token 键名。
                    默认为 None，表示自动按 state 查找 semantic.state.{state}.bg
            glow_key: 外发光颜色的 token 键名。
                      默认为 None，表示使用 accent.secondary
            glow_opacity_map: 各状态的发光透明度映射。
                               如 {"hover": 0.15, "focused": 0.2}
                               未列出的状态不画发光
            mode: 切角模式，"all"(四角对称) 或 "br"(仅右下角，赛博朋克风格)
        """
        from PySide6.QtGui import QColor, QPen, QBrush
        from PySide6.QtCore import Qt

        # 取参数
        corner = self.space(corner_key)

        # 背景色
        if bg_key:
            bg_color = self.token_color(bg_key)
        else:
            bg_color = self.token_color("alias.bg.raised")

        # 生成切角路径并填充
        path = self._chamfered_path(self.rect(), corner, mode=mode)
        painter.fillPath(path, QBrush(bg_color))

        # 外发光（仅指定状态启用）
        if glow_opacity_map and self._state in glow_opacity_map:
            if glow_key:
                glow_color = self.token_color(glow_key)
            else:
                glow_color = self.token_color("alias.accent.secondary")

            alpha = glow_opacity_map[self._state]
            glow_color.setAlphaF(alpha)
            painter.setPen(QPen(glow_color, 1))
            painter.drawPath(path)

    def _draw_nav_tab(
        self,
        painter: "QPainter",
        text: str = "",
        selected: bool = False,
        hover: bool = False,
    ) -> None:
        """绘制赛博朋克风格导航标签。

        结构：左侧装饰竖条 + 间隙 + 主内容区（右下角切角）。
        参考：Cyberpunk 2077 UI 导航标签样式。

        Args:
            painter: 已初始化的 QPainter（需开启 Antialiasing）
            text: 标签文字（如 "历程"、"养成"）
            selected: 是否为选中态（选中时左侧竖条加宽高亮 + 反色虚影）
            hover: 是否为悬停态（hover 时背景提亮）
        """
        from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath
        from PySide6.QtCore import QPointF, QRectF, Qt
        from core.tokens.manager import TokenManager

        tm = TokenManager.instance()

        # ── Token 参数 ──
        bar_width = tm.space("nav.bar_width", 4)
        bar_width_selected = tm.space("nav.bar_width_selected", 10)
        bar_gap = tm.space("nav.bar_gap", 4)          # 竖条与主内容区间隙
        corner_br = tm.space("nav.corner_br", 6)
        inner_pad = tm.space("nav.inner_pad", 16)

        # 全部从 token 取;若 token 未配置则用 theme_proxy 常量兜底
        # theme_proxy 自身零硬编码,所以本段没有引入任何 F1 硬编码颜色
        # 兜底选择:
        #   - nav.border / nav.bar 默认用 CYBER_CYAN(青色,与品牌强调色区分)
        #   - nav.bg / nav.text 用 LIGHT_TEXT(主文字色,白系)
        # 这些兜底仅在 token 缺失时生效,正常 token 加载后会被覆盖
        from core.theme_proxy import LIGHT_TEXT, CYBER_CYAN
        border_color_str = tm.get("nav.border") or str(CYBER_CYAN)
        bg_color_str = tm.get("nav.bg") or str(LIGHT_TEXT)
        bar_color_str = tm.get("nav.bar") or str(CYBER_CYAN)
        bar_selected_color_str = tm.get("nav.bar_selected") or str(CYBER_CYAN)
        text_color_str = tm.get("nav.text") or str(LIGHT_TEXT)
        # 选中态反色虚影参数
        glow_enabled = bool(tm.get("space.nav.glow.enabled", True))
        glow_spread = int(tm.space("nav.glow.spread", 6))
        glow_alpha = float(tm.get("space.nav.glow.alpha", 0.25))

        border_color = QColor(border_color_str)
        bg_color = self._cyber_resolve_nav_bg_color(bg_color_str)
        bar_color = QColor(bar_color_str)
        bar_sel_color = QColor(bar_selected_color_str)
        text_color = QColor(text_color_str)

        r = QRectF(self.rect())
        # 装饰线宽度固定不变（选中态只改变颜色/透明度）
        current_bar = bar_width

        # 预先计算装饰线矩形（虚影和绘制都需要）
        bar_rect = QRectF(r.left(), r.top(), current_bar, r.height())

        # ── 0. 选中态反色虚影（分别沿竖条和主内容区轮廓绘制，不覆盖间隙）──
        if selected and glow_enabled:
            # 预先计算 main_path 的位置
            _main_left = r.left() + current_bar + bar_gap
            _main_rect = QRectF(_main_left, r.top(), r.width() - current_bar - bar_gap, r.height())
            _c = corner_br
            _pre_main_path = QPainterPath()
            _pre_main_path.moveTo(QPointF(_main_rect.left(), _main_rect.top()))
            _pre_main_path.lineTo(QPointF(_main_rect.right(), _main_rect.top()))
            _pre_main_path.lineTo(QPointF(_main_rect.right(), _main_rect.bottom() - _c))
            _pre_main_path.lineTo(QPointF(_main_rect.right() - _c, _main_rect.bottom()))
            _pre_main_path.lineTo(QPointF(_main_rect.left(), _main_rect.bottom()))
            _pre_main_path.closeSubpath()

            ghost_color = QColor(border_color)
            ghost_color.setAlphaF(glow_alpha)

            # 竖条虚影（仅向左/上/下扩展，不向右侵入间隙）
            bar_ghost = bar_rect.adjusted(-glow_spread, -glow_spread, 0, glow_spread)
            painter.fillRect(bar_ghost, QBrush(ghost_color))

            # 主内容区虚影（仅向右/上/下扩展，不向左侵入间隙）
            gc = corner_br + glow_spread * 0.5
            main_ghost = _main_rect.adjusted(0, -glow_spread, glow_spread, glow_spread)
            mgp = QPainterPath()
            mgp.moveTo(QPointF(main_ghost.left(), main_ghost.top()))
            mgp.lineTo(QPointF(main_ghost.right(), main_ghost.top()))
            mgp.lineTo(QPointF(main_ghost.right(), main_ghost.bottom() - gc))
            mgp.lineTo(QPointF(main_ghost.right() - gc, main_ghost.bottom()))
            mgp.lineTo(QPointF(main_ghost.left(), main_ghost.bottom()))
            mgp.closeSubpath()
            painter.fillPath(mgp, QBrush(ghost_color))

        # ── 1. 左侧装饰竖条（矩形，无切角）──
        bar_path = QPainterPath()
        bar_path.addRect(bar_rect)

        # 竖条填充色
        if selected:
            bar_fill = bar_sel_color
        elif hover:
            bar_fill = QColor(bar_color)
            bar_fill.setAlphaF(0.75)
        else:
            bar_fill = QColor(bar_color)
            bar_fill.setAlphaF(0.5)
        painter.fillPath(bar_path, QBrush(bar_fill))

        # ── 2. 主内容区背景（右下角切角，与竖条之间有间隙）──
        main_left = r.left() + current_bar + bar_gap  # ← 关键：加间隙
        main_rect = QRectF(
            main_left, r.top(),
            r.width() - current_bar - bar_gap, r.height()
        )
        main_path = QPainterPath()
        c = corner_br
        main_path.moveTo(QPointF(main_rect.left(), main_rect.top()))
        main_path.lineTo(QPointF(main_rect.right(), main_rect.top()))
        main_path.lineTo(QPointF(main_rect.right(), main_rect.bottom() - c))
        main_path.lineTo(QPointF(main_rect.right() - c, main_rect.bottom()))
        main_path.lineTo(QPointF(main_rect.left(), main_rect.bottom()))
        main_path.closeSubpath()

        # 玻璃拟态：使用半透明填充 + 细边框
        is_glass = self._is_glass_mode()
        if is_glass:
            # 玻璃模式下使用半透明背景，透出下层
            # 注意:此填充叠在导航容器 QSS(nav.bg)之上,两者 alpha 会复合,
            # 因此标签 alpha 必须偏低,否则浅色+浅色在亮壁纸上白成一片
            glass_bg = QColor(bg_color)
            # 降低饱和度，与页面控件协调（HSL 饱和度降低 40%）
            h, s, l = glass_bg.getHslF()[0], glass_bg.getHslF()[1], glass_bg.getHslF()[2]
            glass_bg.setHslF(h, max(s * 0.6, 0.05), l)  # 饱和度降低 40%，保留色相
            if selected and hover:
                glass_bg.setAlphaF(0.60)
            elif selected:
                glass_bg.setAlphaF(0.50)
            elif hover:
                glass_bg.setAlphaF(0.35)
            else:
                glass_bg.setAlphaF(0.20)
            # 应用沉浸强度折减
            glass_bg.setAlphaF(self._cyber_immersive_alpha(glass_bg.alphaF()))
            painter.fillPath(main_path, QBrush(glass_bg))
            # 细边框（玻璃模式）
            border_pen = QPen(border_color, 1.0)
            painter.setPen(border_pen)
            painter.drawPath(main_path)
        else:
            # 赛博朋克风格：纯色填充 + 发光边框
            if selected and hover:
                bg_color.setAlphaF(0.92)
                h, s, l = bg_color.getHslF()[0], bg_color.getHslF()[1], bg_color.getHslF()[2]
                bg_color.setHslF(h, s, min(l + 0.12, 1.0))
            elif selected:
                bg_color.setAlphaF(0.85)
            elif hover:
                bg_color.setAlphaF(0.82)
                h, s, l = bg_color.getHslF()[0], bg_color.getHslF()[1], bg_color.getHslF()[2]
                bg_color.setHslF(h, s, min(l + 0.08, 1.0))
            else:
                bg_color.setAlphaF(0.75)
            # 沉浸模式：按强度折减主内容区底色（装饰竖条/文字/边框不折减）
            bg_color.setAlphaF(self._cyber_immersive_alpha(bg_color.alphaF()))
            painter.fillPath(main_path, QBrush(bg_color))

            # ── 3. 边框描边（选中+hover 增强发光）──
            if selected and hover:
                glow_pen = QPen(QColor(border_color), 2.5)
                glow_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                painter.setPen(glow_pen)
            else:
                border_pen = QPen(border_color, 1.5)
                painter.setPen(border_pen)
            painter.drawPath(main_path)
            painter.drawPath(bar_path)

        # ── 4. 文字（不受外部 scale 影响，始终原始大小）──
        if text:
            painter.save()
            painter.resetTransform()  # 重置缩放，文字不随标签放大
            painter.setPen(text_color)
            font_size = tm.space("nav.font_size", 13)
            from PySide6.QtGui import QFont, QFontMetrics
            # 导航标签字体：Iceberg（英文），中文 fallback 到 YaHei UI
            font = QFont("Iceberg", font_size, QFont.Weight.Bold)
            painter.setFont(font)

            fm = QFontMetrics(font)
            text_x = main_rect.left() + inner_pad
            # 垂直居中：基线位置 = 矩形中心 + 字体上升高度的一半
            text_y = main_rect.center().y() + fm.ascent() / 2 - fm.descent() / 2
            painter.drawText(QPointF(text_x, text_y), text)
            painter.restore()

        # ── 5. 扫描线纹理叠加（传入复合裁剪区域）──
        combined_clip = QPainterPath()
        combined_clip.addPath(bar_path)
        combined_clip.addPath(main_path)
        self._draw_scanlines(painter, clip_path=combined_clip)

    def _draw_scanlines(
        self,
        painter: "QPainter",
        clip_path: "QPainterPath | None" = None,
    ) -> None:
        """绘制扫描线纹理（全局横纹叠加）。

        在组件背景之上、文字/边框之前调用，增加层次感。
        参考：Cyberpunk 2077 全局暗色水平横纹。

        Args:
            painter: 已初始化的 QPainter
            clip_path: 可选裁剪路径（如切角区域），仅在该区域内绘制横纹。
                       为 None 时使用控件完整矩形。
        """
        from PySide6.QtGui import QColor, QPen, QPainterPath
        from PySide6.QtCore import Qt, QPointF, QRectF
        from core.tokens.manager import TokenManager

        tm = TokenManager.instance()

        # Token 控制
        enabled = tm.get("scanline.enabled", True)
        if not enabled:
            return

        spacing = int(tm.space("scanline.spacing", 2))      # 横纹间距（像素）
        line_alpha = float(tm.get("scanline.alpha", 0.06))   # 横纹透明度 [0,1]
        # scanline.color 取自 token;若未配置则用 LIGHT_TEXT 兜底
        # 扫描线颜色一般取主文字色(浅色),与暗色背景形成对比
        # theme_proxy.LIGHT_TEXT 自身零硬编码,兜底不引入新 F1
        from core.theme_proxy import LIGHT_TEXT
        color_str = str(tm.get("scanline.color") or LIGHT_TEXT)

        if spacing < 1:
            return

        scan_color = QColor(color_str)
        scan_color.setAlphaF(line_alpha)
        pen = QPen(scan_color)
        pen.setWidth(1)
        painter.setPen(pen)

        # 裁剪到指定区域（切角等）
        if clip_path is not None:
            painter.save()
            painter.setClipPath(clip_path)
        else:
            painter.save()
            path = self._chamfered_path(QRectF(self.rect()), 0, mode="br")
            painter.setClipPath(path)

        r = self.rect()
        y = r.top()
        while y <= r.bottom():
            painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            y += spacing

        painter.restore()
