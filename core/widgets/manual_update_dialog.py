"""
[L5] ManualUpdateDialog — 手动更新数据教程对话框

继承: CyberWidgetMixin + QDialog
依赖: core.tokens.manager
职责: 展示数据源下载/放置教程(无网络/异常时引导用户手动操作)

赛博风格对话框，展示:
  - 数据源文件下载地址(可选中复制)
  - 文件放置路径说明
  - 操作步骤指南

## AI 硬约束 — 修改本文件前必读
归属层:    [L5] (core/widgets/) — 弹窗组件比 L4 多出"独立窗口"能力
允许依赖:  core.widgets.base.CyberWidgetMixin, core.tokens.manager, PySide6
禁止依赖:  core.services/*, core.pages/*, core.state/*, data/*
必读规范:  .trae/rules/开发规范.md §6.4

本文件相关红线:
- ✗ 禁止 __init__ 调 super().__init__() → 必须 QDialog.__init__(self, parent)
- ✗ 禁止 paintEvent 漏 super() → 边框/文字会失效
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 self.token() / self.space()
- ✗ 禁止 dialog.exec() 阻塞主线程超过 1s → 必须 exec() 或 show() 二选一,别混用
- ✗ 禁止 dialog 关闭后没释放资源 → __del__ 或 finished 信号里清理

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.4。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QApplication,
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from core.widgets.base import CyberWidgetMixin
from core.widgets.button import CyberButton
from core.tokens.manager import TokenManager


class _CopyableLabel(QLabel):
    """可选中复制的文本标签。"""

    def __init__(self, text: str = "", parent=None):
        QLabel.__init__(self, text, parent)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setWordWrap(True)


class ManualUpdateDialog(CyberWidgetMixin, QDialog):
    """手动更新数据教程对话框。

    展示数据源文件的下载地址、放置位置和操作步骤。
    链接和路径均可选中复制。
    """

    # ── 数据源定义 ──
    REPOS = [
        {
            "name": "warframe-items",
            "desc": "遗物 / 物品数据(旧 All.json 已拆分为 26 个分类文件)",
            "url": "https://github.com/WFCD/warframe-items/tree/develop/data/json",
            "files": ["分类文件 *.json(Warframes/Primary/Relics 等)", "i18n/zh.json → 重命名为 i18n.json"],
            "target": "external/warframe-items_sparse/data/json/",
        },
        {
            "name": "warframe-drop-data",
            "desc": "掉落数据",
            "url": "https://github.com/WFCD/warframe-drop-data",
            "files": ["all.json"],
            "target": "external/warframe-drop-data_sparse/data/",
        },
        {
            "name": "warframe-public-export-plus",
            "desc": "翻译数据",
            "url": "https://github.com/WFCD/warframe-public-export-plus",
            "files": ["dict.en.json", "dict.zh.json"],
            "target": "external/warframe-i18n_sparse/",
        },
    ]

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("手动更新数据 — 教程")
        self.setMinimumSize(580, 520)
        self.setModal(True)

        _tm = TokenManager.instance()
        _bg = _tm.get_qcolor("bg.base")
        _bg_raised = _tm.get_qcolor("bg.raised")
        _text_pri = _tm.get_qcolor("text.primary")
        _text_sec = _tm.get_qcolor("text.secondary")
        _text_ter = _tm.get_qcolor("text.tertiary")
        _border = _tm.get_qcolor("border.default")
        _accent = _tm.get_qcolor("accent.primary")
        _accent_sec = _tm.get_qcolor("accent.secondary")

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_bg.name()};
                color: {_text_pri.name()};
            }}
            QLabel {{
                color: {_text_sec.name()};
                font-size: 12px;
                background: transparent;
                border: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # ── 标题 ──
        title = QLabel("手动更新数据 — 教程")
        title.setFont(QFont("Iceberg", 15))
        title.setStyleSheet(f"color: {_accent.name()}; background: transparent; border: none;")
        layout.addWidget(title)

        # ── 说明文字 ──
        hint = QLabel(
            "自动更新流程: 先直连 GitHub 官方 → 失败后自动切换镜像 → 全部失败才需手动操作。\n"
            "若已进入手动教程，说明所有网络途径均不可用。请下载下方文件并放到对应目录，"
            "然后点击「手动构建数据库」完成更新。\n"
            "链接和路径均可鼠标选中后 Ctrl+C 复制。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_text_ter.name()}; background: transparent; border: none;")
        layout.addWidget(hint)

        # ── 各仓库信息卡片 ──
        for repo in self.REPOS:
            card = self._build_repo_card(repo)
            layout.addWidget(card)

        # ── 底部按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_close = CyberButton(text="关闭", variant="ghost")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _build_repo_card(self, repo: dict) -> QFrame:
        """构建单个仓库的信息卡片。"""
        _tm = TokenManager.instance()
        _bg_raised = _tm.get_qcolor("bg.raised")
        _text_pri = _tm.get_qcolor("text.primary")
        _text_sec = _tm.get_qcolor("text.secondary")
        _text_ter = _tm.get_qcolor("text.tertiary")
        _border = _tm.get_qcolor("border.default")
        _accent = _tm.get_qcolor("accent.primary")
        _accent_sec = _tm.get_qcolor("accent.secondary")

        card = QFrame()
        card.setObjectName(f"manualUpdateCard_{repo['name']}")
        _card_bg = _tm.get_qcolor("bg.base")
        _card_bg.setAlphaF(0.75)
        card.setStyleSheet(f"""
            QFrame#manualUpdateCard_{repo['name']} {{
                background-color: rgba({_card_bg.red()}, {_card_bg.green()}, {_card_bg.blue()}, 0.75);
                border: 1px solid {_border.name()}60;
                border-radius: {TokenManager.instance().space('corner.sm', 6)}px;
            }}
        """)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(6)

        # 仓库名 + 描述
        header = QHBoxLayout()
        name_lbl = QLabel(f"[{repo['name']}]")
        name_lbl.setFont(QFont("", 11))
        name_lbl.setStyleSheet(
            f"color: {_accent.name()}; background: transparent; border: none; font-weight: bold;"
        )
        header.addWidget(name_lbl)

        desc_lbl = QLabel(repo["desc"])
        desc_lbl.setStyleSheet(
            f"color: {_text_sec.name()}; background: transparent; border: none;"
        )
        header.addWidget(desc_lbl)
        header.addStretch()
        cl.addLayout(header)

        # GitHub 链接（可选中复制）
        url_lbl = _CopyableLabel(repo["url"])
        # alpha=0.08 与 _border.name()+"40"(≈25% 不透明) 风格一致
        url_lbl.setStyleSheet(
            f"color: {_accent_sec.name()}; "
            f"background: rgba({_accent_sec.red()}, {_accent_sec.green()}, {_accent_sec.blue()}, 0.08); "
            f"border: 1px solid {_border.name()}40; "
            f"border-radius: 4px; padding: 4px 8px; font-family: Consolas, monospace;"
        )
        cl.addWidget(url_lbl)

        # 所需文件
        files_text = "文件: " + ", ".join(repo["files"])
        files_lbl = _CopyableLabel(files_text)
        files_lbl.setStyleSheet(
            f"color: {_text_ter.name()}; background: transparent; border: none; "
            f"font-size: 11px;"
        )
        cl.addWidget(files_lbl)

        # 放置路径（可选中复制）
        target_lbl = _CopyableLabel(f"放置到: {repo['target']}")
        target_lbl.setStyleSheet(
            f"color: {_text_sec.name()}; background: transparent; border: none; "
            f"font-family: Consolas, monospace; font-size: 11px;"
        )
        cl.addWidget(target_lbl)

        return card