"""
[L2] LicensePage — 加密验证（离线机器绑定激活页）

依赖: widgets/, services/license_service, core.paths
职责:
  - 展示本机机器码，支持一键复制
  - 接收用户粘贴的激活码并调用 LicenseService 验签激活
  - 未激活 / 已授权两态切换
  - 激活成功后通知 AppShell 解锁全部导航页面

父类: PageBase (core/pages/base_page.py)

说明:
  是否强制锁定导航由 AppShell 依据「frozen 打包环境 + 授权状态」决定，
  本页面只负责展示与激活；开发模式下显示旁路提示横幅但不影响使用。
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
)

from core.pages.base_page import PageBase
from core.paths import is_frozen
from core.services.license_service import (
    LicenseService,
    REASON_BAD_FORMAT,
    REASON_FP_UNAVAILABLE,
    REASON_INVALID,
)
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.line_edit import CyberLineEdit


class LicensePage(PageBase):
    """加密验证页：机器码展示 + 激活码输入 + 授权状态展示。"""

    page_id = "license"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_license"

    def __init__(self):
        # 注意：PageBase.__init__ 内部即调用 build_content()，
        # 所有被它读取的字段必须在 super().__init__() 之前就位
        self._svc = LicenseService.instance()
        self._machine_edit_unact: CyberLineEdit | None = None
        self._machine_edit_done: CyberLineEdit | None = None
        self._code_input: CyberLineEdit | None = None
        self._error_label: QLabel | None = None
        self._stack: QStackedWidget | None = None

        super().__init__()
        self.page_title = self._copy("nav.license", "加密验证")

    # ══════════════════════════════════
    #  页面构建
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        _sp = self._spacing
        _fs = self._font_size

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            _sp("lg", 20), _sp("sm", 8), _sp("lg", 20), _sp("lg", 20)
        )
        layout.setSpacing(_sp("xs", 4))

        # ── 标题 ──
        title = QLabel(self._copy("license.title", "加密验证"))
        title.setFont(QFont("Iceberg", _fs("lg_xl", 18)))
        self._style(title, color="accent.primary", padding=("4px", "0"))
        layout.addWidget(title)

        # ── 开发模式旁路提示（仅开发环境显示） ──
        if not is_frozen():
            dev_banner = QLabel(self._copy(
                "license.dev_banner",
                "开发模式：授权门控已旁路，其他页面可正常访问（打包后才会锁定）",
            ))
            self._style(
                dev_banner, color="brand.yellow", font_size="xs",
                background_color="bg.raised",
                padding=(f"{_sp('xs', 4)}px", f"{_sp('sm', 8)}px",
                         f"{_sp('xs', 4)}px", f"{_sp('sm', 8)}px"),
            )
            dev_banner.setWordWrap(True)
            layout.addWidget(dev_banner)

        # ── 主卡片：未激活 / 已授权 两态栈 ──
        # 注意：CyberCard 内部已自带布局，内容必须挂到 content_layout()，
        # 绝不能再 QVBoxLayout(card)（Qt 会拒绝二次安装布局，内容将塌缩不可见）
        card = CyberCard()
        card_layout = card.content_layout()
        margin = _sp("lg", 20)
        card_layout.setContentsMargins(margin, margin, margin, margin)
        card_layout.setSpacing(_sp("sm", 10))

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_unactivated_page())
        self._stack.addWidget(self._build_activated_page())
        card_layout.addWidget(self._stack)

        layout.addWidget(card)
        layout.addStretch()

        self._refresh_state()
        return container

    def _build_unactivated_page(self) -> QWidget:
        """未激活态：操作说明 + 机器码 + 激活码输入 + 激活按钮。"""
        _sp = self._spacing

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_sp("sm", 10))

        # ── 说明（操作步骤） ──
        desc = QLabel(self._copy(
            "license.unact_desc",
            "本软件已绑定本机使用，请按以下步骤完成激活（无需联网）：\n"
            "1. 复制下方「本机机器码」发送给软件作者；\n"
            "2. 将作者回复的激活码整段粘贴到输入框；\n"
            "3. 点击「激活」，通过后全部功能自动解锁。",
        ))
        self._style(desc, color="text.secondary", font_size="sm_md")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(_sp("xs", 4))

        # ── 机器码行（与已授权态共用工厂）──
        layout.addWidget(self._make_caption(
            self._copy("license.machine_label", "本机机器码")))
        self._machine_edit_unact, machine_row = self._build_machine_row(centered=False)
        layout.addLayout(machine_row)

        layout.addSpacing(_sp("xs", 4))

        # ── 激活码行 ──
        layout.addWidget(self._make_caption(
            self._copy("license.code_label", "激活码")))

        self._code_input = CyberLineEdit(
            placeholder=self._copy(
                "license.code_placeholder", "粘贴作者回复的激活码（整段，含横杠也可）"
            )
        )
        code_font = QFont("Consolas", self._font_size("sm", 12))
        code_font.setStyleHint(QFont.StyleHint.Monospace)
        self._code_input.setFont(code_font)
        self._code_input.returnPressed.connect(self._on_activate_clicked)
        layout.addWidget(self._code_input)

        # ── 错误提示（默认隐藏） ──
        self._error_label = QLabel("")
        self._style(self._error_label, color="brand.red", font_size="xs")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # ── 激活按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_activate = CyberButton(
            text=self._copy("license.btn_activate", "激 活"), variant="solid"
        )
        # spacing token 最大档只有 32px，不适合做按钮宽度；
        # 按项目惯例（toggles/hotkeys 页）用 4 倍数固定宽度 128
        btn_activate.setFixedWidth(128)
        btn_activate.clicked.connect(self._on_activate_clicked)
        btn_row.addWidget(btn_activate)
        layout.addLayout(btn_row)

        # ── 底部锁定提示 ──
        locked_hint = QLabel(self._copy(
            "license.locked_hint",
            "激活通过前，其他功能页面处于锁定状态。",
        ))
        self._style(locked_hint, color="text.tertiary", font_size="xs")
        locked_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(_sp("xs", 4))
        layout.addWidget(locked_hint)

        layout.addStretch()
        return page

    def _build_activated_page(self) -> QWidget:
        """已授权态：成功标识 + 机器码备查 + 注意事项。"""
        _sp = self._spacing

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_sp("sm", 10))

        done_title = QLabel(self._copy("license.done_title", "✓ 已授权，软件已激活"))
        done_title.setFont(QFont("Iceberg", self._font_size("xl", 20)))
        self._style(done_title, color="brand.green", padding=("8px", "0"))
        done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(done_title)

        done_desc = QLabel(self._copy(
            "license.done_desc",
            "全部功能已解锁，可正常使用。激活信息已保存在本机。",
        ))
        self._style(done_desc, color="text.secondary", font_size="sm_md")
        done_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        done_desc.setWordWrap(True)
        layout.addWidget(done_desc)

        layout.addSpacing(_sp("sm", 8))

        # 机器码备查（换硬件联系作者时使用；与未激活态共用工厂）
        layout.addWidget(self._make_caption(
            self._copy("license.machine_label", "本机机器码"), centered=True))
        self._machine_edit_done, machine_row = self._build_machine_row(centered=True)
        layout.addLayout(machine_row)

        notice = QLabel(self._copy(
            "license.done_notice",
            "提示：重装系统或更换系统硬盘后机器码会变化，届时需重新联系作者获取激活码。",
        ))
        self._style(notice, color="text.tertiary", font_size="xs")
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.setWordWrap(True)
        layout.addSpacing(_sp("xs", 4))
        layout.addWidget(notice)

        layout.addStretch()
        return page

    def _make_caption(self, text: str, centered: bool = False) -> QLabel:
        """创建字段小标题（机器码/激活码上方的说明文字，两态共用）。"""
        lbl = QLabel(text)
        self._style(lbl, color="text.tertiary", font_size="xs")
        if centered:
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    def _build_machine_row(
        self, centered: bool
    ) -> tuple[CyberLineEdit, QHBoxLayout]:
        """构建「只读机器码框 + 复制按钮」行（未激活/已授权两态共用）。

        Args:
            centered: True=已授权态，整行居中、码框占 2 份宽；
                      False=未激活态，码框撑满、按钮靠右。
        Returns:
            (机器码输入框, 行布局)；文本填充与复制动作均已接好。
        """
        row = QHBoxLayout()
        row.setSpacing(self._spacing("sm", 8))

        edit = CyberLineEdit()
        edit.setReadOnly(True)
        mono = QFont("Consolas", self._font_size("md", 13))
        mono.setStyleHint(QFont.StyleHint.Monospace)
        edit.setFont(mono)

        btn = CyberButton(
            text=self._copy("license.btn_copy", "复制"), variant="outlined"
        )
        btn.clicked.connect(lambda: self._copy_machine_code(btn))

        if centered:
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addStretch()
            row.addWidget(edit, stretch=2)
            row.addWidget(btn)
            row.addStretch()
        else:
            row.addWidget(edit, stretch=1)
            row.addWidget(btn)
        return edit, row

    # ══════════════════════════════════
    #  交互
    # ══════════════════════════════════

    def on_enter(self):
        """进入页面：重读授权状态并刷新视图。"""
        self._svc.reload()
        self._refresh_state()

    def _on_activate_clicked(self):
        """点击激活：校验输入并驱动状态切换。"""
        if self._code_input is None:
            return
        code = self._code_input.text()
        ok, reason = self._svc.activate(code)
        if ok:
            self._show_error("")
            self._refresh_state()
            shell = self._app_shell
            if shell is not None and hasattr(shell, "on_license_activated"):
                shell.on_license_activated()
            return

        reason_text = {
            REASON_BAD_FORMAT: self._copy(
                "license.err_bad_format",
                "激活码格式不正确（应为 103 位字符），请确认整段复制、无遗漏。",
            ),
            REASON_INVALID: self._copy(
                "license.err_invalid",
                "激活码无效，或与本机机器码不匹配。请核对机器码后重新向作者索取。",
            ),
            REASON_FP_UNAVAILABLE: self._copy(
                "license.err_fp",
                "无法读取本机硬件信息（系统 ID / 硬盘序列号），请在本机直接运行本软件。",
            ),
        }.get(reason, str(reason))
        self._show_error(reason_text)

    def _copy_machine_code(self, btn: CyberButton):
        """复制机器码到剪贴板，按钮短暂显示「已复制」。"""
        code = self._svc.machine_code_plain
        if not code:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(code)

        original = self._copy("license.btn_copy", "复制")
        copied = self._copy("license.copied", "已复制")
        btn.setText(copied)
        # 定时器以按钮为 parent：按钮销毁时定时器随之销毁，避免回调
        # 触碰已释放的 C++ 对象（RuntimeError: Internal C++ object already deleted）
        timer = QTimer(btn)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: btn.setText(original))
        timer.start(1500)

    # ══════════════════════════════════
    #  视图刷新
    # ══════════════════════════════════

    def _show_error(self, text: str):
        if self._error_label is None:
            return
        self._error_label.setText(text)
        self._error_label.setVisible(bool(text))

    def _refresh_state(self):
        """按当前授权状态切换两态栈并填充机器码。"""
        if self._stack is None:
            return
        code_grouped = self._svc.machine_code

        if self._machine_edit_unact is not None:
            self._machine_edit_unact.setText(code_grouped)
        if self._machine_edit_done is not None:
            self._machine_edit_done.setText(code_grouped)

        idx = 1 if self._svc.licensed else 0
        self._stack.setCurrentIndex(idx)
