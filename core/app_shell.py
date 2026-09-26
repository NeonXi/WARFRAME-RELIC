"""
AppShell — 新 UI 主窗口框架 (L0 + L1)。

替代旧的 ManagementPanel，作为新架构的顶层容器：
  - L0: 窗口外壳（背景、尺寸、DPI）
  - L1: 导航栏 + 内容区（左侧导航 + 右侧页面栈）

结构::

  ┌──────────────────────────────────────────────┐
  │  AppShell (L0 窗口)                          │
  │ ┌────────┬───────────────────────────────────┐│
  │ │        │                                   ││
  │ │ NavBar │   Content Area (L2~L5 Pages)     ││
  │ │ (L1)   │   QStackedWidget                 ││
  │ │        │                                   ││
  │ │        │                                   ││
  │ └────────┴───────────────────────────────────┘│
  └──────────────────────────────────────────────┘

使用方式::

    from core.app_shell import AppShell
    shell = AppShell()
    shell.show()

## AI 硬约束 — 修改本文件前必读
归属层:    [L0/L1] (core/ 根目录,跨层桥接/全局管理器)
允许依赖:  视文件而定(本层可持有 widget 引用作桥接,但不实现绘制)
禁止依赖:  根目录 .py 不允许做业务实现 → 业务放 core/services/
必读规范:  .trae/rules/开发规范.md §6.7

本文件相关红线:
- 禁止根目录 .py 持有 widget 绘制逻辑 → 视觉交给 core/widgets/
- 禁止硬编码资源路径 → 必须 core.constants 取
- 禁止在根目录定义业务类 → 业务放对应层
- 禁止反向调用 UI(从 Service → Widget) → 单向数据流
- 禁止 try/except: pass 吞错 → 必须记录到日志或抛给上层

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.7,别走捷径。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QScrollArea, QFrame, QLabel, QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPainter

from core.tokens.manager import TokenManager
from core.widgets.base import CyberWidgetMixin


# ══════════════════════════════════════════════
#  导航项定义（与旧 panel_builder.py 保持一致）
# ══════════════════════════════════════════════

NAV_ITEMS = [
    ("toggles",     "功能开关"),
    ("worldstate",  "一线战报"),
    ("db_overview", "数据总览"),
    ("items",       "物品查询"),
    ("triggers",    "辅助触发器"),
    ("cd_assist",   "CD辅助显示"),
    ("eye_mask",    "护眼遮罩"),
    ("prices",      "价格数据"),
    ("theme",       "主题换肤"),
    ("about",       "关于作者"),
]

# 页面类映射（懒导入，避免循环依赖）
_PAGE_CLASS_MAP = {
    "toggles":     "core.pages.toggles_page:TogglesPage",
    "db_overview": "core.pages.status_page:StatusPage",
    "items":       "core.pages.items_page:ItemsPage",
    "triggers":    "core.pages.triggers_page:TriggersPage",
    "cd_assist":   "core.pages.cd_assist_page:CdAssistPage",
    "eye_mask":    "core.pages.eye_mask_page:EyeMaskPage",
    "prices":      "core.pages.prices_page:PricesPage",
    "worldstate":  "core.pages.worldstate_page:WorldstatePage",
    "theme":       "core.pages.theme_page:ThemePage",
    "about":       "core.pages.about_page:AboutPage",
}


# ══════════════════════════════════════════════
#  赛博朋克导航标签组件
# ══════════════════════════════════════════════

class NavTab(QFrame, CyberWidgetMixin):
    """赛博朋克风格导航标签。

    左侧装饰竖条 + 右下角切角主内容区。
    支持 hover / selected 态切换。
    """

    clicked = Signal(str)

    def __init__(self, nav_id: str, label: str, parent=None):
        super().__init__(parent)
        CyberWidgetMixin.__init__(self)
        self._nav_id = nav_id
        self._nav_label = label
        self._selected = False
        self._hover = False
        self.setMouseTracking(True)
        self.setFixedHeight(TokenManager.instance().space("nav.item_height", 36))

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    @property
    def nav_id(self) -> str:
        return self._nav_id

    # ---- 事件 ----

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._nav_id)

    # ---- 绘制 ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # hover 时视觉放大 1.08 倍，不改变实际布局大小
        if self._hover:
            cx, cy = self.width() / 2, self.height() / 2
            painter.translate(cx, cy)
            painter.scale(1.04, 1.04)
            painter.translate(-cx, -cy)
        self._draw_nav_tab(painter, text=self._nav_label, selected=self._selected, hover=self._hover)


# ══════════════════════════════════════════════
#  AppShell 主窗口
# ══════════════════════════════════════════════

class AppShell(QMainWindow):
    """新 UI 主窗口框架。

    职责：
    - 窗口管理（标题、尺寸、背景色）
    - 左侧导航栏构建与切换
    - 右侧内容区页面栈管理
    - 页面注册与生命周期调度
    """

    def __init__(self, *, show_splash: bool = True, app=None):
        super().__init__()
        self._tm = TokenManager.instance()
        self._qt_app = app

        # 页面缓存 {page_id: PageBase instance}
        self._pages: dict = {}
        # 当前页面 ID
        self._current_id: str = ""

        # ── 截图OCR管线服务 ──
        self._pipeline_svc = None

        # ── 自定义背景图绘制层（_build_ui 中创建）──
        self._bg_layer = None

        # ── 沉浸样式控制器（沉浸槽/底色/刷新职责,AppShell 只接线）──
        from core.immersive_controller import ImmersiveStyleController
        self._immersive_ctrl = ImmersiveStyleController(self, self._tm)

        # ── 辅助触发器引擎 ──
        self._trigger_manager = self._create_trigger_manager()

        self._setup_window()
        self._register_fonts()

        # ── 开启动画 ──
        if show_splash:
            self._show_splash_and_build()
        else:
            self._build_ui()
            self._register_pages()
            self._start_pipeline()
            # CD 辅助的低层键盘钩子(WH_KEYBOARD_LL,放行不拦截)
            self._start_cd_assist_hook()
            self._switch_to(NAV_ITEMS[0][0])

    # ══════════════════════════════════
    #  窗口设置
    # ══════════════════════════════════

    def _setup_window(self):
        """设置窗口属性。"""
        self.setWindowTitle("WARFRAME-RELIC")
        # 宽度在 860 基础上整体提升约 15% → 988,保证一线战报页
        # 9 个筛选按钮在默认尺寸下完整显示(约需 972)
        self.setMinimumSize(988, 640)

        # 主窗口底色:沉浸黑色模式开启时覆写为纯黑,alpha 不折减
        # (alpha 折减会让窗口本身变透明露出桌面,这里只覆写 RGB)
        # 启动时先按默认状态(沉浸关闭)设主题色;_build_ui 中 bg_svc.load_on_start()
        # 触发 immersive_changed 信号后,控制器会按已存配置覆写为黑色
        self._immersive_ctrl.apply_initial()

        # ── 应用主窗口初始透明度(从 ui_prefs.json 读) ──
        # 失败回 100%(不透明),不阻塞启动
        try:
            from core.services.ui_prefs import load_window_opacity
            self.setWindowOpacity(load_window_opacity() / 100.0)
        except Exception:
            pass

        # ── 恢复上次主题预设(从 ui_prefs.json 读) ──
        # 失败回 cyberpunk(默认),不阻塞启动
        try:
            from core.services.ui_prefs import load_theme_preset
            preset = load_theme_preset()
            if preset != "cyberpunk":
                from core.tokens.manager import TokenManager
                TokenManager.instance().load_preset(preset)
                print(f"[AppShell] 已恢复主题预设: {preset}", flush=True)
        except Exception:
            pass

    # ══════════════════════════════════
    #  主窗口透明度(供 ThemePage 调)
    # ══════════════════════════════════

    def apply_window_opacity(self, pct: int) -> None:
        """应用主窗口透明度(30-100)。

        调用方:
          - ThemePage 滑块拖动时调,实时改变主窗口透明度
          - _setup_window 启动时也会从 ui_prefs.json 读并应用
        限制:
          - 只影响主窗口,不影响任何独立 overlay(CD 辅助/护眼遮罩/截图浮窗)
          - 入参自动钳制 30-100,避免过低导致不可读
        """
        pct = max(30, min(100, int(pct)))
        self.setWindowOpacity(pct / 100.0)

    # ══════════════════════════════════
    #  字体注册
    # ══════════════════════════════════

    def _register_fonts(self):
        """注册内嵌字体（必须在创建任何 UI 之前调用）。"""
        from core import fonts
        registered = fonts.register_all()
        if registered:
            print(f"[AppShell] 内嵌字体已加载: {', '.join(registered)}", flush=True)

    # ══════════════════════════════════
    #  开启动画
    # ══════════════════════════════════

    def _show_splash_and_build(self) -> None:
        """先构建完整 UI，再显示窗口，最后覆盖启动动画。

        关键顺序：先构建 UI → 再 show() → 立即覆盖 splash。
        避免先 show() 再 build 导致的"空白小窗口闪烁"问题。
        """
        from core.widgets.splash_screen import CyberSplashScreen

        # 1. 构建完整 UI（窗口尚未显示，不会出现空白窗口）
        print("[Splash] 开始构建 UI...", flush=True)
        self._build_ui()
        self._start_pipeline()
        # CD 辅助的低层键盘钩子(WH_KEYBOARD_LL,放行不拦截)
        self._start_cd_assist_hook()
        self._register_pages()
        self._switch_to(NAV_ITEMS[0][0])
        print(f"[Splash] UI 构建完成, 页面数={len(self._pages)}", flush=True)

        # 2. 显示主窗口（此时 UI 已完整构建，窗口尺寸正确）
        self.show()

        # 3. 覆盖启动动画（父控件 = AppShell 自身，fill 整个窗口）
        self._splash = CyberSplashScreen(
            parent=self, enabled=True,
            on_finished=self._on_splash_finished)
        self._splash.setGeometry(0, 0, self.width(), self.height())
        # 窗口大小变化时同步 overlay
        _orig_resize = self.resizeEvent
        def _sync_resize(event):
            _orig_resize(event)
            if self._splash:
                self._splash.resize(event.size())
        self.resizeEvent = _sync_resize
        self._splash_orig_resize = _orig_resize
        self._splash.show()

    def _on_splash_finished(self) -> None:
        """动画结束回调：销毁 overlay，展示 UI。"""
        print(f"[AppShell] 动画结束, 销毁 overlay", flush=True)
        if self._splash:
            self._splash.close()
            self._splash.deleteLater()
        self._splash = None
        if hasattr(self, '_splash_orig_resize'):
            self.resizeEvent = self._splash_orig_resize

    def _create_trigger_manager(self):
        """创建辅助触发器引擎。"""
        import sys
        try:
            from core.trigger_manager import TriggerManager

            def _log(msg: str, log_type: str, source: str):
                sys.stderr.write(f"[{source}] [{log_type}] {msg}\n")
                sys.stderr.flush()

            mgr = TriggerManager(log_func=_log)
            mgr.set_ui_focus_check(self._has_ui_focus)
            mgr.start()
            sys.stderr.write(f"[AppShell] TriggerManager 创建成功 | running={mgr.is_running}\n")
            sys.stderr.flush()
            return mgr
        except Exception:
            import traceback
            sys.stderr.write(f"[AppShell] TriggerManager 创建失败:\n")
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            return None

    def _has_ui_focus(self) -> bool:
        """检查当前是否有 UI 控件拥有焦点（用于防误触）。"""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return False
        fw = app.focusWidget()
        return fw is not None

    def _start_pipeline(self) -> None:
        """启动截图OCR管线服务。"""
        try:
            if self._qt_app is None:
                from PySide6.QtWidgets import QApplication
                self._qt_app = QApplication.instance()
            if self._qt_app:
                from core.services.screenshot_pipeline import ScreenshotPipelineService
                self._pipeline_svc = ScreenshotPipelineService(self._qt_app)
                self._pipeline_svc.start()
                # 连接窗口置顶信号
                self._pipeline_svc.bring_to_front.connect(
                    self._bring_to_front
                )
                print(f"[AppShell] 截图管线已启动", flush=True)
        except Exception as e:
            print(f"[AppShell] 截图管线启动失败: {e}", flush=True)

    def _bring_to_front(self) -> None:
        """一次性把窗口拉到最前(非强制置顶)。

        若窗口最小化则先恢复,再用 Win32 API 置前;最后 Qt 方法兜底。

        关键修复:Windows 有前台锁定策略——用户在**其他应用**里按快捷键时,
        本进程是后台进程,直接调 SetForegroundWindow 会被系统拒绝
        (表现为任务栏图标闪烁,窗口不动)。标准解法是先模拟一次 Alt 键
        按下+释放,让系统认为存在用户输入交互,从而放行前台切换。
        失败不弹窗(快捷键场景),只打印 CMD 日志便于诊断。
        """
        try:
            import ctypes
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            # 最小化则先恢复(SW_RESTORE = 9)
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            # 前台锁定 hack:模拟 Alt 按下+释放(系统视为用户交互输入)
            ALT_VK = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(ALT_VK, 0, 0, 0)
            user32.keybd_event(ALT_VK, 0, KEYEVENTF_KEYUP, 0)
            ok = bool(user32.SetForegroundWindow(hwnd))
            if not ok:
                err = ctypes.get_last_error()
                print(
                    f"[AppShell] SetForegroundWindow 返回 False "
                    f"(GetLastError={err}),已用 Qt raise_/activateWindow 兜底",
                    flush=True,
                )
        except Exception as e:
            print(f"[AppShell] 窗口置顶 Win32 调用失败: {e}", flush=True)
        # Qt 兜底
        self.show()
        self.raise_()
        self.activateWindow()

    def _start_cd_assist_hook(self) -> None:
        """启动 CD 辅助的低层键盘钩子(WH_KEYBOARD_LL) + 注入 view(manager)。

        关键设计:
          - 用 WH_KEYBOARD_LL 而不是 RegisterHotKey,后者会全系统独占
            拦截 1/2/3/4,导致游戏/系统收不到这 4 个键
          - 钩子回调永远 CallNextHookEx 放行 → 游戏/系统/其它应用
            照常接收按键,本应用只是"观察者"
          - 装好后由 50ms QTimer 在主线程 drain queue → start_skill
          - **关键**: 同时把 CdAssistManager 单例注入到 service,
            让 service 的 countdown_tick 直驱 overlay,
            即使用户没进过「CD 辅助显示」页面也能正常显示
          - **默认屏幕**: 选主屏(更符合用户直觉),且 service/manager
            同步设置,避免 UI 显示"未选"但实际能显示的不一致
        """
        try:
            from PySide6.QtGui import QGuiApplication
            from core.services.cd_assist_service import CdAssistService
            from core.widgets.cd_assist_overlay import CdAssistManager
            from core.services.cd_debug_log import log as _dbg

            _dbg("shell", "=== _start_cd_assist_hook() 开始 ===")
            svc = CdAssistService.instance()
            _dbg("shell", f"service 单例: enabled={svc.is_enabled()}, state={svc.get_state()}")

            # 1. 创建 manager 单例(此时还没屏幕列表,后面 refresh)
            mgr = CdAssistManager.instance()
            mgr.refresh_screens()
            # ★ 默认选择主屏(用户在 cd_assist 页面可改成全选/副屏)
            screens = QGuiApplication.screens()
            primary = QGuiApplication.primaryScreen()
            try:
                primary_index = screens.index(primary)
            except ValueError:
                primary_index = 0
            default_indices = [primary_index]
            # ★ 关键: service 和 manager 都要设,否则 UI 读 service 状态会
            #   把按钮显示成"全未选",但 manager 实际全屏在显示 → 不一致
            mgr.set_enabled_screens(default_indices)
            svc.set_enabled_screens(default_indices)
            _dbg("shell", f"默认启用主屏: indices={default_indices}")

            # 2. 把 manager 注入到 service(关键: 不依赖页面是否被访问)
            svc.set_view(mgr)
            _dbg("shell", f"service.view 已绑: {type(mgr).__name__}")

            # 3. 启动钩子
            ok = svc.bind_to_app()
            _dbg("shell", f"svc.bind_to_app() → {ok}")
            if ok:
                print(
                    f"[AppShell] CD 辅助已就绪: 钩子+默认主屏 {default_indices} "
                    f"(1/2/3/4 键放行,游戏/系统正常接收)",
                    flush=True,
                )
            else:
                _dbg("shell", "钩子启动失败,详见 hook 子日志", level="ERR")
                print("[AppShell] CD 辅助低层键盘钩子启动失败", flush=True)
        except Exception as e:
            import traceback
            print(f"[AppShell] CD 辅助启动异常: {e}", flush=True)
            traceback.print_exc()

    # ══════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════

    def _build_ui(self):
        """构建整体布局：导航栏 + 内容区。"""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 左侧导航栏 ──
        self._nav_container = self._build_nav_bar()
        main_layout.addWidget(self._nav_container)

        # ── 右侧内容区 ──
        self._content_stack = QStackedWidget()
        self._content_stack.setStyleSheet("background-color: transparent;")
        main_layout.addWidget(self._content_stack, stretch=1)

        # ── 自定义背景图绘制层 ──
        # 作为 central 的子控件但不进布局；lower() 压到导航栏/内容区之下，
        # 几何在 resizeEvent 中跟随 central
        from core.widgets.background_layer import CyberBackgroundLayer
        from core.services.background_service import BackgroundService

        self._bg_layer = CyberBackgroundLayer(central)
        self._bg_layer.lower()
        bg_svc = BackgroundService.instance()
        # 沉浸信号必须在 load_on_start 前连接，启动恢复时才能收到
        # (槽/底色/刷新逻辑在 ImmersiveStyleController,AppShell 只接线)
        self._immersive_ctrl.attach(bg_svc)
        bg_svc.set_layer(self._bg_layer)
        bg_svc.load_on_start()
        # 应用当前沉浸底色预设到控件层(供懒创建的卡片继承)
        CyberWidgetMixin.set_immersive_color_mode(bg_svc.immersive_color)

    def resizeEvent(self, event):
        """窗口尺寸变化：让背景层铺满 central，并跟随正常缩放流程。"""
        super().resizeEvent(event)
        central = self.centralWidget()
        if central is not None and self._bg_layer is not None:
            self._bg_layer.setGeometry(central.rect())

    def _build_nav_bar(self) -> QWidget:
        """构建左侧导航栏。"""
        container = QWidget()
        self._nav_container = container
        container.setFixedWidth(self._tm.space("nav.bar_container_width", 148))
        container.setObjectName("navContainer")
        # 初始为非沉浸样式；沉浸状态恢复时由沉浸控制器重设
        self._immersive_ctrl.apply_nav_container_style(False, 70)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            self._tm.space("spacing.sm", 8),
            self._tm.space("spacing.lg", 16),
            self._tm.space("spacing.sm", 8),
            self._tm.space("spacing.sm", 8),
        )
        layout.setSpacing(self._tm.space("spacing.md", 12))
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 品牌标题
        brand_title = QLabel("WF RELIC")
        font_size = self._tm.space("font.lg", 16)
        title_font = QFont("Alibaba PuHuiTi 3", font_size, QFont.Weight.Normal)
        brand_title.setFont(title_font)
        accent_color = self._tm.get("alias.accent.primary")
        brand_title.setStyleSheet(f"""
            color: {accent_color};
            padding: {self._tm.space('spacing.sm', 8)}px 0;
            border: none;
        """)
        brand_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_title)

        # 分隔线
        border_str = self._tm.get("alias.border.subtle")
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {border_str};")
        layout.addWidget(divider)

        layout.addSpacing(self._tm.space("spacing.md", 12))

        # 导航标签列表
        self._nav_tabs: list[NavTab] = []
        for nav_id, label in NAV_ITEMS:
            tab = NavTab(nav_id, label)
            tab.clicked.connect(self._on_nav_clicked)
            layout.addWidget(tab)
            self._nav_tabs.append(tab)

        layout.addStretch()

        return container

    # ══════════════════════════════════
    #  页面注册与管理
    # ══════════════════════════════════

    def _register_pages(self):
        """注册所有页面到内容栈。"""
        print(f"[AppShell] 开始注册页面 (共 {len(NAV_ITEMS)} 个)...", flush=True)
        for nav_id, _label in NAV_ITEMS:
            page = self._create_page(nav_id)
            if page is not None:
                page.set_app_shell(self)
                self._pages[nav_id] = page
                print(f"[AppShell]   ✓ {nav_id} 创建成功", flush=True)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                accent = self._tm.get("alias.accent.secondary")
                sub = self._tm.get("alias.border.subtle")
                text_dim = self._tm.get("alias.text.tertiary")
                scroll.setStyleSheet(f"""
                    QScrollArea {{
                        border: none;
                        background-color: transparent;
                    }}
                    QScrollBar:vertical {{
                        background: transparent;
                        width: 8px;
                        margin: 0;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {sub};
                        border-radius: 4px;
                        min-height: 30px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {accent};
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
                scroll.setWidget(page)
                self._content_stack.addWidget(scroll)

        print(f"[AppShell] 页面注册完成: {list(self._pages.keys())}", flush=True)

    def _create_page(self, nav_id: str):
        """通过懒导入创建页面实例。

        失败处理:
          - 不抛异常(避免中断 register_pages)
          - 返回一个错误占位页(显示 nav_id + 错误原因),让用户能
            从导航 tab 看到是哪个页面坏了
          - 同时在 _pages 字典中存入原 nav_id → 占位实例,这样:
            · stack 里能切到这个错误页
            · on_enter 不会被跳过
            · 用户能看到"初始化失败"提示而不是"页面消失"
        """
        class_path = _PAGE_CLASS_MAP.get(nav_id)
        if not class_path:
            return None

        module_path, class_name = class_path.rsplit(":", 1)
        try:
            import importlib
            import traceback
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            instance = cls()
            print(f"[AppShell] 页面 '{nav_id}' 创建成功", flush=True)
            return instance
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            print(f"[AppShell] 创建页面 '{nav_id}' 失败: {err_msg}", flush=True)
            traceback.print_exc()
            # 返回错误占位页 — 保留 nav_id,避免导航失联
            from core.pages.placeholder_error_page import PlaceholderErrorPage
            return PlaceholderErrorPage(nav_id=nav_id, error=err_msg)

    # ══════════════════════════════════
    #  导航切换
    # ══════════════════════════════════

    def _on_nav_clicked(self, nav_id: str):
        """导航项被点击。"""
        self._switch_to(nav_id)

    def _switch_to(self, nav_id: str):
        """切换到指定页面。"""
        from core.services.cd_debug_log import log as _dbg
        if nav_id == self._current_id:
            return
        _dbg("shell", f"_switch_to: {self._current_id or '∅'} → {nav_id}")

        # 旧页面离开
        if self._current_id and self._current_id in self._pages:
            old_page = self._pages[self._current_id]
            old_page.on_leave()

        # 更新导航选中态
        for tab in self._nav_tabs:
            tab.set_selected(tab.nav_id == nav_id)

        # 切换内容栈
        page_idx = self._page_index(nav_id)
        if page_idx >= 0:
            self._content_stack.setCurrentIndex(page_idx)
        else:
            _dbg("shell", f"页面 '{nav_id}' 未找到", level="WARN")

        # 新页面进入
        self._current_id = nav_id
        if nav_id in self._pages:
            new_page = self._pages[nav_id]
            new_page.on_enter()

    def _page_index(self, nav_id: str) -> int:
        """获取页面在 stack 中的索引。"""
        for i in range(self._content_stack.count()):
            scroll = self._content_stack.widget(i)
            widget = scroll.widget() if hasattr(scroll, 'widget') else None
            if widget and hasattr(widget, 'page_id') and widget.page_id == nav_id:
                return i
        return -1

    @property
    def pipeline(self):
        """获取截图OCR管线服务实例。"""
        return self._pipeline_svc

    @property
    def trigger_manager(self):
        """获取辅助触发器引擎实例。"""
        return self._trigger_manager

    # ══════════════════════════════════
    #  主题刷新
    # ══════════════════════════════════

    def refresh_theme(self) -> None:
        """刷新整个应用的主题（切换 token 预设后调用）。

        触发所有控件重绘，使新 token 值生效。
        """
        # 刷新导航栏容器样式（玻璃模式/赛博朋克模式切换）
        if hasattr(self, '_immersive_ctrl'):
            # 获取当前沉浸状态
            from core.widgets.base import CyberWidgetMixin
            immersive = CyberWidgetMixin._cyber_immersive
            strength = CyberWidgetMixin._cyber_immersive_strength
            color_mode = CyberWidgetMixin._cyber_immersive_color_mode
            self._immersive_ctrl.apply_nav_container_style(immersive, strength, color_mode)

        # 刷新导航栏
        for tab in self._nav_tabs:
            tab.update()

        # 刷新所有页面
        for page in self._pages.values():
            page.update()

        # 刷新背景层
        if self._bg_layer is not None:
            self._bg_layer.update()

        # 刷新窗口本身
        self.update()

        print("[AppShell] 主题已刷新", flush=True)

    # ══════════════════════════════════
    #  关闭清理
    # ══════════════════════════════════

    def closeEvent(self, event) -> None:
        """窗口关闭:卸载 CD 辅助的低层键盘钩子(避免进程退出后钩子残留)。"""
        try:
            from core.services.cd_assist_service import CdAssistService
            svc = CdAssistService.instance()
            # 先解 view,再 shutdown(避免 shutdown 后还有 view 调用)
            svc.set_view(None)
            svc.shutdown()
            print("[AppShell] CD 辅助低层键盘钩子已卸载", flush=True)
        except Exception as e:
            print(f"[AppShell] CD 辅助钩子卸载异常: {e}", flush=True)
        super().closeEvent(event)
