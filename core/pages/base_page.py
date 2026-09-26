"""
[L2] core.pages.base_page — 页面基类 PageBase

所有功能页面的公共接口和生命周期管理。
每个页面继承此类后自动注册到导航系统。

依赖: PySide6.QtWidgets + core.tokens (尺寸/颜色)
被谁用: core.pages 下的所有具体页面

使用方式::

    class TogglesPage(PageBase):
        page_id = "toggles"
        page_title = "功能开关"
        page_icon = "nav_toggles"

        def build_content(self) -> QWidget:
            # 返回页面的主内容 widget
            ...

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/) — 基类,所有具体页面继承自此
允许依赖:  core.widgets/*, core.sections/*, core.services/*(读), core.state/*(读), PySide6
禁止依赖:  core.tokens/* 直接调用(只通过 widget)
           任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止在 PageBase 中 setStyleSheet(f"...") → 必须用 Token
- ✗ 禁止 PageBase 重写 paintEvent → 视觉交给 Widget
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space
- ✗ 禁止子类忘记调用 super().__init__() 跳过导航注册

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.tokens.manager import TokenManager


class PageBase(QWidget):
    """页面基类。

    提供统一的页面生命周期：
      - on_enter: 页面被切换到（获得焦点）
      - on_leave: 页面被切走（失去焦点）
      - on_theme_change: 主题变更时刷新
      - build_content: 构建页面内容（子类必须实现）
    """

    # ── 子类必须定义的属性 ──
    page_id: str = ""           # 唯一标识，如 "toggles"
    page_title: str = ""        # 显示标题
    page_icon: str = ""         # 图标 key（对应 icon_loader 的 nav/xxx）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_shell = None   # 引用宿主 AppShell（由 AppShell 注入）

        tm = TokenManager.instance()
        self._tm = tm
        self._bg_color_str = tm.get("alias.bg.raised")
        self._text_primary_str = tm.get("alias.text.primary")

        self._setup_base_ui()

    # ── Token 辅助方法 ──

    def _color(self, key: str) -> str:
        """获取 token 颜色的 hex 字符串，供 stylesheet 使用。

        Token 必须存在于 YAML 预设文件中，否则抛出异常。
        """
        qcolor = self._tm.get_qcolor(key)
        return qcolor.name()

    def _resolve_immersive_bg_str(
        self,
        key: str,
        alpha: float = 1.0,
    ) -> str:
        """QSS 字符串入口:沉浸黑色模式时返回覆写后的颜色 hex 字符串。

        Page 不是 CyberWidgetMixin 子类,计算实现收敛在
        core/widgets/immersive.py(唯一实现,内部读 Mixin 类级状态),
        本方法只保留 Page API 形态,供 ``_apply_form_style`` /
        ``_apply_spin_style`` 等构造 QSS 时调用。

        Args:
            key: 颜色 token 路径(如 ``alias.bg.raised``)
            alpha: 非沉浸时的目标 alpha(如 1.0)

        Returns:
            QSS 可直接拼接的颜色字符串(``#AARRGGBB``)
        """
        from core.widgets import immersive

        return immersive.resolve_token_str(self._tm, key, alpha)

    def _font_size(self, key: str, fallback: int = 12) -> int:
        """获取 token 字号值。"""
        return self._tm.space(f"font.{key}", fallback)

    def _spacing(self, key: str, fallback: int = 8) -> int:
        """获取 token 间距值（space.spacing.*）。"""
        return self._tm.space(f"spacing.{key}", fallback)

    def _copy(self, key: str, default: str = "", **kwargs) -> str:
        """获取文案 token 字符串,支持模板变量替换。"""
        return self._tm.copy(key, default, **kwargs)

    # ── 样式辅助(集中 setStyleSheet,避免 f-string 散落) ──

    def _style(self, widget: QWidget, **props) -> None:
        """对 widget 应用样式属性(集中处理 setStyleSheet)。

        调用方式::

            self._style(title, color=token, padding=("4px", "0"))

        其中 color 既可以是 token key(如 "accent.primary"),
        也可以是字面量(以 # / rgba( / rgb( 开头)。

        支持的 key:
          - color / background:   token key(自动 _color() 解析)
                                  也支持 "#RRGGBB" / "rgba(...)" 字面量
          - font_size:            token key 或 int(自动 _font_size() 解析)
          - padding / margin:     字符串 或 tuple(各方向 4px 0 形式)
          - border:               字符串(完整 border 简写)
          - transparent:          bool,True 时附加 "background: transparent"
          - raw:                  任何额外 CSS 字符串(不解析)

        顺序固定: color → background → font_size → font_weight → padding →
                  margin → border → transparent → raw

        样式配方会保存到 widget 的 ``_cyber_style_props`` 属性,
        ``on_theme_change()`` 时用当前 token 值重放,避免切换预设后
        QSS 残留旧预设颜色(复选框/滑块等「颜色污染」的根因)。
        """
        # 保存样式配方到 widget 实例,供主题切换时重放(无副作用)
        widget.setProperty("_cyber_style_props", dict(props))
        self._apply_style_props(widget, props)

    def _apply_style_props(self, widget: QWidget, props: dict) -> None:
        """实际构造并应用 QSS(on_theme_change 重放时复用)。"""
        # ── 颜色解析:token key 走 _color(),其他(hex/rgba)字面量直传 ──
        def _resolve_color(value) -> str:
            if value is None:
                return ""
            if isinstance(value, str) and (
                value.startswith("#") or value.startswith("rgba(") or value.startswith("rgb(")
            ):
                # 已经是字面量
                return value
            return self._color(value)

        parts: list[str] = []
        # ── color ──
        if "color" in props:
            parts.append(f"color: {_resolve_color(props['color'])};")
        # ── background ──
        if "background" in props:
            parts.append(f"background: {_resolve_color(props['background'])};")
        if props.get("background_color") is not None:
            parts.append(f"background-color: {_resolve_color(props['background_color'])};")
        # ── font-size ──
        if "font_size" in props:
            fs = props["font_size"]
            if isinstance(fs, int):
                parts.append(f"font-size: {fs}px;")
            else:
                parts.append(f"font-size: {self._font_size(fs, 12)}px;")
        # ── font-weight ──
        if "font_weight" in props:
            parts.append(f"font-weight: {props['font_weight']};")
        # ── padding ──
        if "padding" in props:
            p = props["padding"]
            if isinstance(p, str):
                parts.append(f"padding: {p};")
            else:
                parts.append(f"padding: {' '.join(str(x) for x in p)};")
        # ── margin ──
        if "margin" in props:
            m = props["margin"]
            if isinstance(m, str):
                parts.append(f"margin: {m};")
            else:
                parts.append(f"margin: {' '.join(str(x) for x in m)};")
        # ── border ──
        if "border" in props:
            parts.append(f"border: {props['border']};")
        # ── transparent ──
        if props.get("transparent"):
            parts.append("background: transparent; border: none;")
        # ── raw CSS(支持 str 或零参 callable;callable 在重放时重新求值) ──
        if "raw" in props:
            raw_val = props["raw"]
            parts.append(raw_val() if callable(raw_val) else raw_val)

        if parts:
            widget.setStyleSheet(" ".join(parts))

    # ══════════════════════════════════
    #  基础布局
    # ══════════════════════════════════

    def _setup_base_ui(self):
        """构建基础容器布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        content = self.build_content()
        if content:
            layout.addWidget(content)

    # ══════════════════════════════════
    #  子类必须实现
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        """构建并返回页面的主内容 Widget。

        子类必须覆盖此方法。返回的 widget 将被放入内容区域。

        Returns:
            QWidget 实例
        """
        return self._build_placeholder()

    # ══════════════════════════════════
    #  生命周期钩子（子类可选覆盖）
    # ══════════════════════════════════

    def on_enter(self):
        """页面被切换到时调用。"""
        pass

    def on_leave(self):
        """页面被切走时调用。"""
        pass

    def on_theme_change(self):
        """主题变更时调用:重放所有通过 ``_style()`` 登记的样式配方。

        QSS 是构建期内联的静态字符串,``widget.update()`` 只触发重绘
        不会重新计算 QSS,因此切换预设后必须用新 token 值重建样式表。
        对页面内所有子控件查找 ``_cyber_style_props`` 配方并重新应用。
        """
        for w in self.findChildren(QWidget):
            props = w.property("_cyber_style_props")
            if props:
                self._apply_style_props(w, props)
        self.update()

    # ══════════════════════════════════
    #  内部工具
    # ══════════════════════════════════

    def _build_placeholder(self) -> QFrame:
        """默认占位页面(子类未覆盖 build_content 时使用)。"""
        frame = QFrame()
        self._style(frame, transparent=True)

        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"[ {self.page_id} ]")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_size = TokenManager.instance().space("font.xl", 20)
        title_font = QFont("Microsoft YaHei", font_size, QFont.Weight.Bold)
        title.setFont(title_font)
        self._style(title, color="alias.text.primary")

        subtitle = QLabel("Coming Soon...")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_font_size = TokenManager.instance().space("font.md", 14)
        sub_font = QFont("Microsoft YaHei", sub_font_size)
        sub_font.setItalic(True)
        subtitle.setFont(sub_font)
        self._style(subtitle, color="alias.text.tertiary")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        return frame

    def set_app_shell(self, shell):
        """注入宿主 AppShell 引用。"""
        self._app_shell = shell
