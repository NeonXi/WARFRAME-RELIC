"""
ImmersiveStyleController — 沉浸黑色模式样式控制器 (L0/L1)

从 AppShell 拆出的沉浸样式管理职责,AppShell 只保留接线:
  - 监听 BackgroundService 的沉浸信号 → 更新控件层类级状态
  - 应用 navContainer / QMainWindow 底色 QSS
  - 全量/可见刷新所有现存控件

归属层:    [L0/L1] (core/ 根目录,跨层桥接/全局管理器)
允许依赖:  PySide6, core.widgets.base (CyberWidgetMixin / immersive 模块),
           core.services.background_service (读单例), core.tokens.manager
禁止依赖:  业务实现(本类只做样式编排,不做绘制/业务计算)
必读规范:  .trae/rules/开发规范.md §6.7

本文件相关红线:
- ✗ 禁止实现颜色计算 → 全部走 core/widgets/immersive.py(唯一实现)
- ✗ 禁止持有页面/控件引用 → 只遍历 QApplication.allWidgets()
- ✗ 禁止 try/except: pass 吞错(刷新处除外,需注释说明)
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

from core.widgets.base import CyberWidgetMixin


class ImmersiveStyleController:
    """沉浸黑色模式样式控制器。

    职责(全部从 AppShell 迁入):
      - on_immersive_changed:   沉浸开关/强度变化 → 类级状态 + 底色 + 刷新
      - on_immersive_color_changed: 底色预设切换 → 覆写色 + 底色 + 全量刷新
      - apply_initial:          启动时先按「非沉浸」设好窗口底色
      - apply_nav_container_style: 导航容器底色(折减 alpha 让壁纸透出)
      - apply_window_bg_style:  窗口自身底色(只覆写 RGB,alpha 不折减)
      - refresh_for_all / refresh_for_visible: 控件重绘 + QSS 重设
    """

    def __init__(self, shell, tm):
        """
        Args:
            shell: AppShell 实例(操作 setStyleSheet / _nav_container)
            tm: TokenManager 实例
        """
        self._shell = shell
        self._tm = tm

        # ── 沉浸状态参数缓存(避免重复 setStyleSheet 触发样式重算) ──
        # QMainWindow 底色只依赖 (immersive, color_mode),不依赖 strength;
        # strength 变化时跳过 setStyleSheet 调用,大幅降低卡顿
        self._window_bg_cache: tuple | None = None
        # 沉浸开关上次值(区分「开关切换」要全量刷新 / 「强度拖动」只刷新可见)
        self._enabled_cache: bool | None = None

    # ══════════════════════════════════
    #  接线
    # ══════════════════════════════════

    def attach(self, bg_svc) -> None:
        """连接 BackgroundService 的沉浸信号(必须在 load_on_start 前调)。

        Args:
            bg_svc: BackgroundService 单例
        """
        bg_svc.immersive_changed.connect(self.on_immersive_changed)
        bg_svc.immersive_color_changed.connect(self.on_immersive_color_changed)

    # ══════════════════════════════════
    #  启动初始化
    # ══════════════════════════════════

    def apply_initial(self) -> None:
        """启动时按默认状态(沉浸关闭)设窗口底色。

        _build_ui 中 bg_svc.load_on_start() 触发沉浸信号后,
        on_immersive_changed 会按已存配置覆写为黑色。
        """
        self.apply_window_bg_style(False, "theme")

    # ══════════════════════════════════
    #  底色应用
    # ══════════════════════════════════

    def apply_nav_container_style(
        self, immersive: bool, strength: int, color_mode: str = "theme"
    ) -> None:
        """设置导航栏容器底色(沉浸时按强度折减 alpha;右侧分隔边框保留)。

        沉浸底色用 #AARRGGBB 八位色(Qt QSS 支持),颜色计算走 immersive 模块。
        color_mode="black" 时:沉浸开启 → 底色 RGB 覆写为纯黑;关闭 → 沿用原色。
        玻璃拟态模式下使用极浅冰蓝半透明。
        """
        # 玻璃拟态模式使用 nav.bg token（极浅冰蓝半透明）
        is_glass = self._tm.current_preset == "glassmorphism"
        if is_glass:
            nav_bg_str = self._tm.get("nav.bg") or "rgba(227, 242, 253, 0.40)"
        else:
            nav_bg_str = self._tm.get("alias.bg.base")

        if immersive:
            c = QColor(nav_bg_str)
            if color_mode == "black":
                # 纯黑底色计算收敛在 core/widgets/immersive.py
                from core.widgets import immersive as _immersive
                c = _immersive.black_rgb(self._tm)
            c.setAlphaF(1.0 - strength / 100.0)
            nav_bg_str = c.name(QColor.NameFormat.HexArgb)
        border_str = self._tm.get("alias.border.subtle")
        self._shell._nav_container.setStyleSheet(f"""
            QWidget#navContainer {{
                background-color: {nav_bg_str};
                border-right: 1px solid {border_str};
            }}
        """)

    def apply_window_bg_style(
        self, immersive: bool, color_mode: str = "theme"
    ) -> None:
        """设置 QMainWindow 自身底色(沉浸黑色模式时覆写 RGB,alpha 不折减)。

        与 apply_nav_container_style 互补:
          - navContainer 折减 alpha 让壁纸透出;
          - QMainWindow 是窗口最底层,不能折减 alpha(否则会透明露出桌面)。

        因此这里只覆写 RGB,alpha 永远 1.0:
          - immersive=True 且 color_mode="black" → 纯黑(immersive.black_rgb)
          - 其他情况 → alias.bg.base token 主题色

        这样调「背景图片透明度」时透出来的颜色 = 沉浸底色预设。

        性能优化:QMainWindow 底色只依赖 (immersive, color_mode),不依赖
        strength。沉浸强度滑块拖动时(每 60ms tick 一次 immersive_changed
        信号),本方法会被重复调用但参数不变 → 命中缓存直接 return,
        避免重复 setStyleSheet 触发整个窗口样式重算。
        """
        cache_key = (immersive, color_mode)
        if self._window_bg_cache == cache_key:
            return
        self._window_bg_cache = cache_key

        bg_str = self._tm.get("alias.bg.base")
        if immersive and color_mode == "black":
            # 纯黑底色计算收敛在 core/widgets/immersive.py
            from core.widgets import immersive as _immersive
            c = _immersive.black_rgb(self._tm)
            # alpha 不折减 → 用 #RRGGBB 即可(QSS 可解析)
            bg_str = c.name(QColor.NameFormat.HexRgb)
        self._shell.setStyleSheet(f"""
            QMainWindow {{
                background-color: {bg_str};
            }}
        """)

    # ══════════════════════════════════
    #  信号槽
    # ══════════════════════════════════

    def on_immersive_changed(
        self, enabled: bool, strength: int, color_mode: str
    ) -> None:
        """沉浸状态变化:更新控件层全局标志、底色 QSS,并统一重绘。

        类级标志本身不会触发重绘,因此遍历所有现存 Cyber 控件刷新;
        懒创建的新卡片会直接读取类级标志,无需额外处理。
        同时调用控件的 cyber_refresh_immersive_style 重设依赖 token 的 QSS
        (如 QSpinBox / QTextEdit 等通过 setStyleSheet 设底色的控件)。

        Args:
            enabled: 沉浸开关
            strength: 沉浸强度 0-100
            color_mode: 沉浸底色预设("theme" / "black",随信号携带,
                        槽内不再反向拉 BackgroundService 单例)
        """
        CyberWidgetMixin.set_immersive_global(enabled, strength)
        # 导航容器 + 窗口底色
        # _apply_window_bg_style 内部带缓存:strength 变化时直接 return,
        # 避免滑块拖动(60ms/tick)触发整个窗口样式重算
        self.apply_nav_container_style(enabled, strength, color_mode)
        self.apply_window_bg_style(enabled, color_mode)
        # 区分「开关切换」(全量)与「强度拖动」(只可见)
        last_enabled = self._enabled_cache
        self._enabled_cache = enabled
        if last_enabled is None or last_enabled != enabled:
            # 开关切换或首次:全量刷新
            self.refresh_for_all()
        else:
            # 仅 strength 变化:只刷新可见 widget
            self.refresh_for_visible()

    def on_immersive_color_changed(self, mode: str) -> None:
        """沉浸底色预设变化:更新控件层覆写色、底色 QSS,并统一重绘。

        与 on_immersive_changed 互补:开关没变但预设切换时也要刷新 UI。
        低频操作(用户点选主题色/纯黑按钮),全量刷新无性能问题。
        """
        CyberWidgetMixin.set_immersive_color_mode(mode)
        from core.services.background_service import BackgroundService
        bg_svc = BackgroundService.instance()
        self.apply_nav_container_style(
            bg_svc.immersive, bg_svc.immersive_strength, mode
        )
        # 同步 QMainWindow 自身底色(只覆写 RGB,不折减 alpha)
        self.apply_window_bg_style(bg_svc.immersive, mode)
        self.refresh_for_all()

    # ══════════════════════════════════
    #  刷新
    # ══════════════════════════════════

    def refresh_for_all(self) -> None:
        """统一刷新所有 Cyber 控件:重绘 + 重设依赖 token 的 QSS。

        - CyberWidgetMixin 子类:调 update() 触发 paintEvent(沉浸覆写在
          paintEvent 里实时取色,自动应用);
        - 实现了 ``cyber_refresh_immersive_style`` 的控件(Page / 原生
          QSpinBox / QTextEdit 等):额外调用一次以重新构造 QSS
          (QSS 字符串只在 __init__ / _apply_xxx_style 设一次,需手动刷新)。
        """
        for w in QApplication.allWidgets():
            if isinstance(w, CyberWidgetMixin):
                w.update()
            if hasattr(w, "cyber_refresh_immersive_style"):
                try:
                    w.cyber_refresh_immersive_style()
                except Exception:
                    # 刷新失败不能影响其他控件或主流程
                    pass

    def refresh_for_visible(self) -> None:
        """只刷新当前可见 Cyber 控件(沉浸强度拖动专用,性能优化版)。

        与 refresh_for_all 的区别:
          - 用 ``isVisible()`` 过滤,跳过 QStackedWidget 中切走的隐藏页面
            及其子控件(隐藏 widget 的 update() / setStyleSheet 是浪费);
          - 隐藏页面切回时,PageBase.on_enter() 会自然触发重绘,
            不会有视觉空洞。

        沉浸强度滑块拖动时,每 60ms tick 一次 immersive_changed 信号,
        若遍历全量 widget(数百个,含切走但还存在的页面)会显著卡顿;
        实测可见 widget 通常只占总量 1/5~1/4。
        """
        for w in QApplication.allWidgets():
            # 跳过隐藏 widget:isVisible() 对 QStackedWidget 切走的页面
            # 及其子控件返回 False(因为父 widget 未 show)
            if not w.isVisible():
                continue
            if isinstance(w, CyberWidgetMixin):
                w.update()
            if hasattr(w, "cyber_refresh_immersive_style"):
                try:
                    w.cyber_refresh_immersive_style()
                except Exception:
                    # 刷新失败不能影响其他控件或主流程
                    pass
