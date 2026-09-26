"""
[L2] AboutPage — 关于作者页面。

依赖: widgets/
职责: 显示项目信息、版本号、作者信息、社交媒体链接

## AI 硬约束 — 修改本文件前必读
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.constants, PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接), 任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

本文件相关红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止硬编码版本号 / 仓库地址 → 走 core.constants
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.5,别走捷径。
"""


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QDesktopServices

from core.pages.base_page import PageBase
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard


# ── 链接常量 ──
BILIBILI_URL = "https://space.bilibili.com/21001459"
GITHUB_URL = "https://github.com/WARFRAME-RELIC"


class AboutPage(PageBase):
    """「关于作者」页面。

    展示项目版本、作者信息、B站/GitHub 链接等。
    用于让用户快速了解项目来源和反馈渠道。
    """
    page_id = "about"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_about"

    def __init__(self):
        super().__init__()
        self.page_title = self._copy("nav.about", "关于作者")

    # ══════════════════════════════════
    #  工具方法
    # ══════════════════════════════════

    def _open_url(self, url: str):
        """在默认浏览器中打开链接。"""
        QDesktopServices.openUrl(QUrl(url))

    def _make_link_label(self, text: str, tooltip: str = "") -> QLabel:
        """创建可点击的超链接标签。"""
        accent = self._color("accent.primary")
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {accent}; "
            f"font-size: {self._font_size('sm', 12)}px; "
            f"text-decoration: underline;"
        )
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            lbl.setToolTip(tooltip)
        return lbl

    def _make_section_label(self, text: str) -> QLabel:
        """创建分区小标题。"""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {self._color('text.tertiary')}; "
            f"font-size: {self._font_size('xs', 11)}px; "
            f"font-weight: bold; "
            f"padding: 0 0 2px 0;"
        )
        return lbl

    def _make_info_row(self, label: str, value: str, label_width: int = 80) -> QHBoxLayout:
        """创建 标签: 值 的行布局。"""
        row = QHBoxLayout()
        row.setSpacing(12)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {self._color('text.tertiary')}; "
            f"font-size: {self._font_size('sm', 12)}px;"
        )
        lbl.setFixedWidth(label_width)
        row.addWidget(lbl)

        val = QLabel(value)
        val.setStyleSheet(
            f"color: {self._color('text.primary')}; "
            f"font-size: {self._font_size('sm', 12)}px; "
            f"font-family: monospace;"
        )
        val.setWordWrap(True)
        row.addWidget(val, stretch=1)
        return row

    # ══════════════════════════════════
    #  页面构建
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        """构建「关于」页主内容(版本号/作者/B站/GitHub 链接)。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # ══════════════════════════════════
        #  标题区
        # ══════════════════════════════════
        accent = self._color("accent.primary")
        text_tertiary = self._color("text.tertiary")
        text_secondary = self._color("text.secondary")

        title = QLabel("WARFRAME RELIC")
        title.setFont(QFont("Monoton", 28))
        self._style(title, color="accent.primary", padding=("8px", "0", "0", "0"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("遗物数据查询工具 · Cyberpunk UI")
        subtitle.setFont(QFont("Iceberg", 13))
        self._style(subtitle, color="text.tertiary", padding=("0", "0", "4px", "0"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # ══════════════════════════════════
        #  作者信息卡片
        # ══════════════════════════════════
        author_card = CyberCard(title="作者信息", clickable=False)
        author_layout = author_card.content_layout()
        author_layout.setContentsMargins(24, 28, 24, 20)
        author_layout.setSpacing(10)

        # 作者名
        author_name = QLabel("WARFRAME-RELIC Team")
        author_name.setStyleSheet(
            f"color: {self._color('text.primary')}; "
            f"font-size: {self._font_size('md', 15)}px; "
            f"font-weight: bold;"
        )
        author_layout.addWidget(author_name)

        # 简介
        author_bio = QLabel(
            "热爱 Warframe 的开发者，致力于为中文社区提供更好的遗物数据查询体验。"
        )
        author_bio.setStyleSheet(
            f"color: {text_secondary}; "
            f"font-size: {self._font_size('sm', 12)}px; "
            f"line-height: 1.5;"
        )
        author_bio.setWordWrap(True)
        author_layout.addWidget(author_bio)

        # 社交链接行
        social_row = QHBoxLayout()
        social_row.setSpacing(12)
        social_row.setContentsMargins(0, 8, 0, 0)

        # Bilibili 按钮（突出显示）
        bili_btn = CyberButton(text="Bilibili 主页", variant="solid")
        bili_btn.setToolTip(BILIBILI_URL)
        bili_btn.clicked.connect(lambda: self._open_url(BILIBILI_URL))
        social_row.addWidget(bili_btn)

        # GitHub 按钮
        github_btn = CyberButton(text="GitHub", variant="outlined")
        github_btn.setToolTip(GITHUB_URL)
        github_btn.clicked.connect(lambda: self._open_url(GITHUB_URL))
        social_row.addWidget(github_btn)

        social_row.addStretch()
        author_layout.addLayout(social_row)

        layout.addWidget(author_card)

        # ══════════════════════════════════
        #  版本信息卡片
        # ══════════════════════════════════
        ver_card = CyberCard(title="版本信息", clickable=False)
        ver_layout = ver_card.content_layout()
        ver_layout.setContentsMargins(24, 28, 24, 18)
        ver_layout.setSpacing(8)

        ver_layout.addLayout(
            self._make_info_row("版本号", "v3.2.1 (Build 20250609)"))
        ver_layout.addLayout(
            self._make_info_row("UI 架构", "Token 主题系统 + ThemeManager 信号驱动"))
        ver_layout.addLayout(
            self._make_info_row("运行环境", "Python 3.12 · PySide6 6.11 · Qt6"))
        ver_layout.addLayout(
            self._make_info_row("数据来源", "Warframe 官方 API + 社区贡献"))

        layout.addWidget(ver_card)

        # ══════════════════════════════════
        #  项目说明卡片
        # ══════════════════════════════════
        proj_card = CyberCard(title="项目说明", clickable=False)
        proj_layout = proj_card.content_layout()
        proj_layout.setContentsMargins(24, 28, 24, 18)
        proj_layout.setSpacing(10)

        desc = QLabel(
            "WARFRAME RELIC 是一款面向 Warframe 玩家的遗物数据查询工具。\n\n"
            "主要功能：\n"
            "• 遗物内含物品与掉落概率查询\n"
            "• Prime 部件市场价格参考\n"
            "• 掉落来源追踪（任务、赏金、突击等）\n"
            "• 游戏内截图 OCR 自动识别遗物\n"
            "• 拼音搜索\n"
            "• Token 驱动的多主题可换肤 UI（赛博朋克 / 玻璃拟态）"
        )
        desc.setStyleSheet(
            f"color: {text_secondary}; "
            f"font-size: {self._font_size('sm', 12)}px; "
            f"line-height: 1.6;"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignLeft)
        proj_layout.addWidget(desc)

        layout.addWidget(proj_card)

        # ══════════════════════════════════
        #  技术栈卡片
        # ══════════════════════════════════
        tech_card = CyberCard(title="技术栈", clickable=False)
        tech_layout = tech_card.content_layout()
        tech_layout.setContentsMargins(24, 28, 24, 18)
        tech_layout.setSpacing(6)

        accent_secondary = self._color("accent.secondary")

        # 技术栈按类别组织：每类一个标题行 + 若干条目
        tech_groups = [
            ("UI / 框架", [
                ("PySide6 6.11", "Qt6 Python 绑定，UI 渲染引擎"),
                ("ThemeManager", "统一主题切换架构，信号驱动全应用刷新"),
                ("Token 系统", "YAML 驱动的多主题配置（赛博朋克 / 玻璃拟态）"),
                ("自定义控件", "CyberButton / CyberCard / CyberLineEdit 等，\n继承原生 Qt + Mixin 自绘"),
                ("内嵌字体", "Iceberg / Monoton / 阿里巴巴普惠体"),
            ]),
            ("OCR / 图像", [
                ("RapidOCR", "ONNX Runtime 驱动的 OCR 识别引擎"),
                ("OpenCV", "图像预处理与裁剪"),
                ("dxcam", "基于 DirectX DDA 的高性能屏幕捕获"),
                ("Pillow", "图像加载与缩放"),
                ("NumPy", "矩阵运算与像素数据处理"),
            ]),
            ("数据 / 搜索", [
                ("SQLite", "本地数据库（遗物 / 物品 / 市场价格）"),
                ("pypinyin", "中文拼音模糊搜索"),
                ("PyYAML", "主题 Token 解析引擎"),
                ("requests", "Warframe 官方 API / 社区市场数据拉取"),
            ]),
            ("系统 / 打包", [
                ("Win32 API", "全局热键钩子、悬浮窗透明穿透（ctypes）"),
                ("PyInstaller", "EXE 一键打包分发（--windowed / --noupx）"),
            ]),
        ]

        for group_name, items in tech_groups:
            # 类别标题行
            group_lbl = QLabel(group_name)
            group_lbl.setStyleSheet(
                f"color: {accent}; "
                f"font-size: {self._font_size('sm', 12)}px; "
                f"font-weight: bold; "
                f"padding: 8px 0 2px 0;"
            )
            tech_layout.addWidget(group_lbl)

            for tech_name, tech_desc in items:
                trow = QHBoxLayout()
                trow.setSpacing(8)

                tname = QLabel(tech_name)
                tname.setStyleSheet(
                    f"color: {accent_secondary}; "
                    f"font-size: {self._font_size('sm', 12)}px; "
                    f"font-weight: bold;"
                )
                tname.setFixedWidth(116)
                trow.addWidget(tname)

                tdesc = QLabel(tech_desc)
                tdesc.setStyleSheet(
                    f"color: {text_tertiary}; "
                    f"font-size: {self._font_size('xs', 11)}px;"
                )
                tdesc.setWordWrap(True)
                trow.addWidget(tdesc, stretch=1)

                tech_layout.addLayout(trow)

        layout.addWidget(tech_card)

        # ══════════════════════════════════
        #  底部操作按钮
        # ══════════════════════════════════
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bili_link_btn = CyberButton(text="Bilibili", variant="outlined")
        bili_link_btn.setToolTip(BILIBILI_URL)
        bili_link_btn.clicked.connect(lambda: self._open_url(BILIBILI_URL))
        btn_row.addWidget(bili_link_btn)

        github_link_btn = CyberButton(text="GitHub", variant="outlined")
        github_link_btn.setToolTip(GITHUB_URL)
        github_link_btn.clicked.connect(lambda: self._open_url(GITHUB_URL))
        btn_row.addWidget(github_link_btn)

        layout.addLayout(btn_row)

        # ══════════════════════════════════
        #  版权信息
        # ══════════════════════════════════
        copyright_lbl = QLabel("© 2025 — 2026 WARFRAME-RELIC. All rights reserved.")
        copyright_lbl.setStyleSheet(
            f"color: {self._color('alias.text.disabled')}; "
            f"font-size: {self._font_size('micro', 10)}px;"
        )
        copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copyright_lbl)

        layout.addStretch()

        return container