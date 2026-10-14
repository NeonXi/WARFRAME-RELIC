"""
[L2] SitesPage — 常用网站页面

依赖: widgets/(CyberCard/CyberButton/CyberSiteAddDialog),
      services/sites_service(纯数据层), PySide6
职责: 以卡片列表展示常用网站(名称/描述/网址)，
      提供「打开网站 / 添加 / 删除(二次确认) / 恢复默认」交互。
父类: BasePage (core/pages/base_page.py)

数据流（单向）:
    sites_service(JSON) → _reload_sites() 重建卡片；
    任何变更都由 service 落盘后再 _reload_sites()，页面不缓存数据。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from core.pages.base_page import PageBase
from core.services import sites_service
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.site_add_dialog import CyberSiteAddDialog

# 删除二次确认的等待时长（毫秒）
_DELETE_CONFIRM_MS = 3000
# 操作按钮固定宽（4 的倍数）
_BTN_OPEN_WIDTH = 96
_BTN_DELETE_WIDTH = 96
_BTN_ADD_WIDTH = 96
_BTN_RESET_WIDTH = 128


class SitesPage(PageBase):
    """「常用网站」页：网站卡片列表 + 添加/删除/恢复默认。"""

    page_id = "sites"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_about"

    def __init__(self):
        # UI 引用必须在 super().__init__() 之前声明：
        # PageBase.__init__ 内部会调 build_content（见 theme_page 同惯例）
        self._list_layout: QVBoxLayout | None = None  # 卡片列表容器
        self._empty_hint: QLabel | None = None        # 空列表占位提示

        super().__init__()
        self.page_title = self._copy("nav.sites", "常用网站")

    # ══════════════════════════════════
    #  生命周期
    # ══════════════════════════════════

    def on_enter(self):
        """每次进入都重新读盘，保证外部改动（如手动编辑 JSON）即时反映。"""
        self._reload_sites()

    # ══════════════════════════════════
    #  页面构建
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # ── 顶部操作行 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()

        reset_btn = CyberButton(
            self._copy("sites.reset_btn", "恢复默认"),
            variant="outlined",
        )
        reset_btn.setFixedWidth(_BTN_RESET_WIDTH)
        reset_btn.setToolTip(
            self._copy("sites.reset_tip", "还原内置的中文维基与 WM 交易网站")
        )
        reset_btn.clicked.connect(self._on_reset)
        action_row.addWidget(reset_btn)

        add_btn = CyberButton(
            self._copy("sites.add_btn", "+ 添加网站"),
            variant="solid",
        )
        add_btn.setFixedWidth(_BTN_ADD_WIDTH)
        add_btn.clicked.connect(self._on_add)
        action_row.addWidget(add_btn)
        layout.addLayout(action_row)

        # ── 网站卡片列表 ──
        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(self._spacing("sm", 8))
        layout.addLayout(self._list_layout)

        self._empty_hint = QLabel(
            self._copy(
                "sites.empty_hint",
                "还没有收藏的网站，点击右上角「添加网站」开始收藏。",
            )
        )
        self._style(self._empty_hint, color="text.tertiary", font_size="sm")
        self._empty_hint.setVisible(False)
        layout.addWidget(self._empty_hint)

        layout.addStretch()
        return container

    # ══════════════════════════════════
    #  列表渲染
    # ══════════════════════════════════

    def _reload_sites(self) -> None:
        """从 service 读全量数据并重建卡片（单一数据源，不做内存缓存）。"""
        if self._list_layout is None:
            return
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            old = item.widget()
            if old is not None:
                # setParent(None) 立即断开 QObject 父子关系（takeAt 只移出
                # 布局、不断父子），再延迟释放，避免重建瞬间旧卡片仍在子树
                old.setParent(None)
                old.deleteLater()

        sites = sites_service.load_sites()
        for index, site in enumerate(sites):
            self._list_layout.addWidget(self._make_site_card(index, site))

        if self._empty_hint is not None:
            self._empty_hint.setVisible(len(sites) == 0)

    def _make_site_card(self, index: int, site: dict) -> CyberCard:
        """构建单张网站卡片：标题(名称) + 描述 + 网址行 + 操作按钮。"""
        card = CyberCard(title=site["name"])
        cl = card.content_layout()
        cl.setContentsMargins(16, 12, 16, 16)
        cl.setSpacing(self._spacing("xs", 4) + 4)

        # 描述（仅预置网站有；用户添加的无此行）
        desc = site.get("desc", "")
        if desc:
            desc_lbl = QLabel(desc)
            self._style(desc_lbl, color="text.secondary", font_size="sm")
            desc_lbl.setWordWrap(True)
            cl.addWidget(desc_lbl)

        # 网址 + 按钮行
        bottom = QHBoxLayout()
        bottom.setSpacing(self._spacing("sm", 8))

        url_lbl = QLabel(site["url"])
        self._style(
            url_lbl,
            color="accent.primary",
            font_size="sm",
            raw="font-family: monospace;",
        )
        # 网址允许鼠标选中复制，实际打开走右侧按钮
        url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bottom.addWidget(url_lbl)
        bottom.addStretch()

        open_btn = CyberButton(
            self._copy("sites.open_btn", "打开网站"), variant="solid"
        )
        open_btn.setFixedWidth(_BTN_OPEN_WIDTH)
        open_btn.setToolTip(site["url"])
        open_btn.clicked.connect(lambda: self._open_url(site["url"]))
        bottom.addWidget(open_btn)

        del_btn = CyberButton(
            self._copy("sites.delete_btn", "删 除"),
            variant="semantic.danger",
        )
        del_btn.setFixedWidth(_BTN_DELETE_WIDTH)
        del_btn.clicked.connect(lambda: self._on_delete_clicked(index, del_btn))
        bottom.addWidget(del_btn)

        cl.addLayout(bottom)
        return card

    # ══════════════════════════════════
    #  交互
    # ══════════════════════════════════

    def _open_url(self, url: str) -> None:
        """调用系统默认浏览器打开（URL 已在 service 层限定为 http/https）。"""
        QDesktopServices.openUrl(QUrl(url))

    def _on_add(self) -> None:
        """打开添加对话框；校验与落盘由 service 完成（经 validator 注入）。"""
        dlg = CyberSiteAddDialog(
            validator=self._validate_and_add,
            parent=self,
        )
        if dlg.exec() == CyberSiteAddDialog.DialogCode.Accepted:
            self._reload_sites()

    def _validate_and_add(self, name: str, url: str) -> tuple[bool, str]:
        """供对话框调用：调 service 校验+落盘，原因码映射为中文文案。

        Returns:
            (True, "") 成功；(False, 可展示文案) 失败，对话框保持打开。
        """
        ok, reason = sites_service.add_site(name, url)
        if ok:
            return True, ""
        message_map = {
            sites_service.REASON_EMPTY_NAME:
                self._copy("sites.err_name_empty", "请填写网站名称"),
            sites_service.REASON_BAD_URL:
                self._copy(
                    "sites.err_bad_url",
                    "网址无效，请输入可访问的 http/https 网址",
                ),
            sites_service.REASON_DUP_URL:
                self._copy("sites.err_dup_url", "该网址已在收藏列表中"),
        }
        return False, message_map.get(reason, str(reason))

    def _on_delete_clicked(self, index: int, btn: CyberButton) -> None:
        """删除二次确认：首次点击按钮变红提示，3 秒内再点才真正删除。

        QTimer 的 parent 设为按钮本身——卡片重建时按钮销毁，
        定时器随之自动停止，避免回调操作已销毁控件。
        """
        if not getattr(btn, "_cyber_confirming", False):
            btn._cyber_confirming = True
            btn.setText(self._copy("sites.confirm_delete", "确认删除？"))
            timer = QTimer(btn)
            timer.setSingleShot(True)
            timer.timeout.connect(
                lambda b=btn: self._cancel_delete_confirm(b)
            )
            timer.start(_DELETE_CONFIRM_MS)
            return

        sites_service.remove_site(index)
        self._reload_sites()

    def _cancel_delete_confirm(self, btn: CyberButton) -> None:
        """3 秒内未二次点击：按钮还原为普通删除态。"""
        btn._cyber_confirming = False
        btn.setText(self._copy("sites.delete_btn", "删 除"))

    def _on_reset(self) -> None:
        """恢复内置默认网站。"""
        sites_service.reset_sites()
        self._reload_sites()
