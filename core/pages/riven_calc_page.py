"""
[L2] RivenCalcPage — 紫卡数值计算器页面

依赖: widgets/(CyberCard/CyberComboBox/CyberButton/CyberLineEdit/CyberRivenResultTable),
      services/riven_calc_service(纯逻辑层), PySide6
职责: 武器类型 + 倾向值 + 布局 → 实时计算并展示全部词条的最低/最高值。

数据流（单向）:
    用户操作控件 → _recompute() → riven_calc_service.compute() → 表格 set_rows()

布局:
    页面由 QScrollArea 承载（整体可能超出窗口，保证在小屏也完整可见）；
    内部含「控制栏」+「正面词条表格」+「负面词条表格（含负面时显示）」。
    每张结果表独立限定可视行数并自带纵向滚动，因此表头冻结在各自表格顶部。
    所有结果卡片统一走 _make_section_card() 构造，内层布局 margins 归零
    （CyberCard.content_layout() 自身已带 padding token，再套一层会双倍）。

健壮性:
    riven_base.json 缺失/损坏时保留上次结果并在页面底部显示红色提示，
    不清空表格、不让页面构造失败（上层兜底成错误占位页）。

生命周期:
    on_enter: 立即按当前控件状态计算一次（用户无需先交互即可看到结果）。
    on_leave: 无定时器/心跳，无需清理。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QDoubleValidator
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget, QScrollArea, QFrame,
)

from core.pages.base_page import PageBase
from core.services import riven_calc_service, riven_wiki_service
from core.widgets.button import CyberButton
from core.widgets.card import CyberCard
from core.widgets.combo_box import CyberComboBox
from core.widgets.line_edit import CyberLineEdit
from core.widgets.riven_table import CyberRivenResultTable

# 操作按钮（布局切换）固定宽（4 的倍数）
_LAYOUT_BTN_WIDTH = 96
# 倾向值输入框固定宽（4 的倍数）
_DISP_EDIT_WIDTH = 120
# 武器类型下拉固定宽
_WEAPON_COMBO_WIDTH = 120
# 清空输入按钮固定宽（4 的倍数）
_CLEAR_BTN_WIDTH = 88
# 倾向反查下拉固定宽（中英文武器名较长）
_WIKI_COMBO_WIDTH = 280
# 倾向反查候选数量上限（下拉弹窗展示用）
_WIKI_MAX_CANDIDATES = 15
# 输入防抖间隔（毫秒）：避免每个字符都查一次 sqlite
_WIKI_DEBOUNCE_MS = 250
# 倾向值输入框默认值（倾向 1.0 为基准中性值）
_DEFAULT_DISPOSITION = "1.00"
# 首次进入时的默认布局（选「3正1负」可同时展示两组表格，功能一览）
_DEFAULT_LAYOUT = "3正1负"
# 布局按钮选中态前缀（与 solid 变体配合，避免选中态与主操作按钮混淆）
_LAYOUT_SELECTED_PREFIX = "● "


class RivenCalcPage(PageBase):
    """「紫卡数值计算器」页：倾向、布局 → 实时词条范围表格。"""

    page_id = "riven_calc"
    page_title = ""
    page_icon = "nav_about"  # 复用既有导航图标资产，不新增图片资源

    def __init__(self):
        # UI 引用须在 super().__init__() 之前声明（PageBase.__init__ 会调 build_content）
        self._weapon_combo: CyberComboBox | None = None
        self._disposition_edit: CyberLineEdit | None = None
        self._layout_buttons: dict[str, CyberButton] = {}
        self._layout_labels: dict[str, str] = {}
        self._selected_layout: str = _DEFAULT_LAYOUT
        self._positive_table: CyberRivenResultTable | None = None
        self._negative_table: CyberRivenResultTable | None = None
        self._negative_card: CyberCard | None = None
        self._error_lbl: QLabel | None = None
        # 倾向反查控件
        self._wiki_combo: CyberComboBox | None = None
        self._wiki_hint_lbl: QLabel | None = None
        self._wiki_link_lbl: QLabel | None = None
        self._wiki_error_lbl: QLabel | None = None
        self._wiki_debounce: QTimer | None = None

        super().__init__()
        self.page_title = self._copy("nav.riven_calc", "紫卡数值计算器")

    # ══════════════════════════════
    #  生命周期
    # ══════════════════════════════

    def on_enter(self):
        """进入页面时立即按当前控件状态计算一次（用户无需先交互）。"""
        self._recompute()

    def on_leave(self):
        """离开页面：停掉输入防抖定时器（页面不可见时无意义）。"""
        if self._wiki_debounce is not None:
            self._wiki_debounce.stop()

    # ══════════════════════════════
    #  页面构建
    # ══════════════════════════════

    def build_content(self) -> QWidget:
        """构建并返回页面的主内容 Widget（QScrollArea 包裹的容器）。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(self._spacing("md", 12))

        # ── 顶部说明 ──
        desc = QLabel(
            self._copy(
                "riven_calc.desc",
                "选择武器类型，填写倾向值并切换布局，即可查看各词条在对应布局下的最低值与最高值。",
            )
        )
        self._style(desc, color="text.secondary", font_size="sm")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── 公式提示（小号、次要色，不占主导）──
        formula_lbl = QLabel(
            self._copy(
                "riven_calc.formula",
                "公式：最终数值 = 基础数值 × 倾向值 × 修正系数 × 浮动系数（0.9 ~ 1.1）",
            )
        )
        self._style(formula_lbl, color="text.tertiary", font_size="xs")
        layout.addWidget(formula_lbl)

        # ── 控制栏 + 结果表格 ──
        layout.addWidget(self._build_control_card())
        layout.addWidget(self._build_positive_section())
        layout.addWidget(self._build_negative_section())

        # ── 数据文件错误提示（默认隐藏，_recompute 出错时显示）──
        self._error_lbl = QLabel(
            self._copy(
                "riven_calc.data_error",
                "紫卡数据文件缺失或损坏（riven_base.json），请从安装包恢复该文件。",
            )
        )
        self._style(self._error_lbl, color="alias.semantic.danger", font_size="sm")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ══════════════════════════════
    #  卡片构造（统一模式，避免三处复制粘贴）
    # ══════════════════════════════

    def _make_section_card(
        self,
        title: str = "",
        title_color: str = "accent.primary",
    ) -> tuple[CyberCard, QVBoxLayout]:
        """构造「可选标题 + 内容」卡片，返回 (card, 内容布局)。

        CyberCard.content_layout() 自带 padding（components.card.padding_*），
        因此内层布局 margins 归零，避免双重 padding 让内容离边框过宽；
        间隔走 spacing token，不硬编码。
        """
        card = CyberCard()
        vl = QVBoxLayout()
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(self._spacing("sm", 8))

        if title:
            header = QLabel(title)
            self._style(header, color=title_color, font_size="md")
            vl.addWidget(header)

        card.content_layout().addLayout(vl)
        return card, vl

    def _build_control_card(self) -> CyberCard:
        """构建控制栏：武器类型 / 倾向值 / 布局按钮。"""
        card, vl = self._make_section_card()

        # Row 1: 武器类型 + 倾向值
        row1 = QHBoxLayout()
        row1.setSpacing(self._spacing("sm", 8))

        lbl_weapon = QLabel(self._copy("riven_calc.weapon_label", "武器类型"))
        self._style(lbl_weapon, color="text.secondary", font_size="sm")
        row1.addWidget(lbl_weapon)

        self._weapon_combo = CyberComboBox()
        self._weapon_combo.setFixedWidth(_WEAPON_COMBO_WIDTH)
        self._weapon_combo.addItems(riven_calc_service.list_weapon_types())
        self._weapon_combo.currentTextChanged.connect(self._recompute)
        row1.addWidget(self._weapon_combo)

        row1.addSpacing(self._spacing("md", 12))

        lbl_disp = QLabel(self._copy("riven_calc.disposition_label", "倾向值"))
        self._style(lbl_disp, color="text.secondary", font_size="sm")
        row1.addWidget(lbl_disp)

        self._disposition_edit = CyberLineEdit(
            placeholder=self._copy("riven_calc.disposition_ph", "例如 1.35"),
        )
        self._disposition_edit.setFixedWidth(_DISP_EDIT_WIDTH)
        self._disposition_edit.setText(_DEFAULT_DISPOSITION)
        # 倾向值范围 0.00 ~ 2.00，最多两位小数（与游戏内实际倾向区间一致）
        validator = QDoubleValidator(0.0, 2.0, 2, self._disposition_edit)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self._disposition_edit.setValidator(validator)
        self._disposition_edit.textChanged.connect(self._recompute)
        row1.addWidget(self._disposition_edit)

        row1.addStretch()
        vl.addLayout(row1)

        # Row 2: 布局切换按钮组（单选互斥；选中 = solid + 圆点前缀，未选 = outlined）
        row2 = QHBoxLayout()
        row2.setSpacing(self._spacing("sm", 8))

        lbl_layout = QLabel(self._copy("riven_calc.layout_label", "词条布局"))
        self._style(lbl_layout, color="text.secondary", font_size="sm")
        row2.addWidget(lbl_layout)

        for layout_key in riven_calc_service.list_layouts():
            btn = CyberButton(layout_key, variant="outlined")
            btn.setFixedWidth(_LAYOUT_BTN_WIDTH)
            btn.clicked.connect(
                lambda _checked=False, k=layout_key: self._on_layout_clicked(k)
            )
            self._layout_buttons[layout_key] = btn
            self._layout_labels[layout_key] = layout_key
            row2.addWidget(btn)

        row2.addStretch()
        vl.addLayout(row2)

        # Row 3: 倾向反查（Wiki 页面直达，绕开 program 抓取被反爬拦截的问题）
        row3 = QHBoxLayout()
        row3.setSpacing(self._spacing("sm", 8))

        lbl_wiki = QLabel(self._copy("riven_calc.wiki_label", "倾向反查"))
        self._style(lbl_wiki, color="text.secondary", font_size="sm")
        row3.addWidget(lbl_wiki)

        self._wiki_combo = CyberComboBox()
        self._wiki_combo.setEditable(True)
        self._wiki_combo.setFixedWidth(_WIKI_COMBO_WIDTH)
        self._wiki_combo.lineEdit().setPlaceholderText(
            self._copy("riven_calc.wiki_ph", "输入武器名（中/英文）")
        )
        # textEdited：仅用户手动输入时刷新候选（程序填充不触发，避免循环）
        self._wiki_combo.lineEdit().textEdited.connect(self._on_wiki_text_edited)
        # activated：从候选弹窗选中一项
        self._wiki_combo.activated.connect(self._on_wiki_activated)
        # returnPressed：回车时按精确匹配直接打开
        self._wiki_combo.lineEdit().returnPressed.connect(self._on_wiki_return_pressed)

        # 输入防抖：每次击键重置计时，停止输入 250ms 后才查 sqlite
        self._wiki_debounce = QTimer(self)
        self._wiki_debounce.setSingleShot(True)
        self._wiki_debounce.setInterval(_WIKI_DEBOUNCE_MS)
        self._wiki_debounce.timeout.connect(self._wiki_refresh_candidates)

        row3.addWidget(self._wiki_combo)
        row3.addStretch()
        vl.addLayout(row3)

        # 倾向反查提示行（常驻，弱化显示）
        self._wiki_hint_lbl = QLabel(
            self._copy(
                "riven_calc.wiki_hint",
                "选择或回车后在浏览器中打开该武器页面，查看 Disposition（倾向值）",
            )
        )
        self._style(self._wiki_hint_lbl, color="text.tertiary", font_size="xs")
        vl.addWidget(self._wiki_hint_lbl)

        # 反查结果链接（点击可在浏览器打开；默认隐藏）
        self._wiki_link_lbl = QLabel("")
        self._wiki_link_lbl.setOpenExternalLinks(True)
        self._wiki_link_lbl.setWordWrap(True)
        self._wiki_link_lbl.setVisible(False)
        vl.addWidget(self._wiki_link_lbl)

        # 未匹配提示（默认隐藏，红色）
        self._wiki_error_lbl = QLabel(
            self._copy(
                "riven_calc.wiki_no_match",
                "未找到匹配的武器，请从候选列表中选择",
            )
        )
        self._style(self._wiki_error_lbl, color="alias.semantic.danger", font_size="xs")
        self._wiki_error_lbl.setVisible(False)
        vl.addWidget(self._wiki_error_lbl)

        # 初始化默认选中
        self._update_layout_buttons(_DEFAULT_LAYOUT)
        return card

    def _build_positive_section(self) -> CyberCard:
        """构建「正面词条」卡片 + 冻结表头表格（标题行带「清空输入」按钮）。"""
        # 标题行自定义（而非走 _make_section_card 的 title 参数），
        # 以便在标题右侧放「清空输入」按钮
        card, vl = self._make_section_card()

        header_row = QHBoxLayout()
        header_row.setSpacing(self._spacing("sm", 8))
        title = QLabel(self._copy("riven_calc.positive_title", "正面词条"))
        self._style(title, color="accent.primary", font_size="md")
        header_row.addWidget(title)
        header_row.addStretch()

        clear_btn = CyberButton(
            self._copy("riven_calc.clear_inputs", "清空输入"), variant="ghost"
        )
        clear_btn.setFixedWidth(_CLEAR_BTN_WIDTH)
        clear_btn.setToolTip(
            self._copy("riven_calc.clear_tip", "清空所有已输入的「我的数值」")
        )
        clear_btn.clicked.connect(self._on_clear_inputs)
        header_row.addWidget(clear_btn)
        vl.addLayout(header_row)

        self._positive_table = CyberRivenResultTable(is_negative=False)
        vl.addWidget(self._positive_table)
        return card

    def _build_negative_section(self) -> CyberCard:
        """构建「负面词条」卡片 + 冻结表头表格；初始可见性由布局决定。"""
        card, vl = self._make_section_card(
            self._copy("riven_calc.negative_title", "负面词条"),
            title_color="alias.semantic.danger",
        )
        self._negative_card = card
        self._negative_table = CyberRivenResultTable(is_negative=True)
        vl.addWidget(self._negative_table)

        # 默认按初始布局决定是否显示（get_layout 失败/数据损坏时保守隐藏）
        layout_def = riven_calc_service.get_layout(_DEFAULT_LAYOUT)
        has_neg = bool(layout_def) and layout_def.get("neg", 0) != 0.0
        card.setVisible(has_neg)
        return card

    # ══════════════════════════════
    #  交互：布局切换 + 实时计算
    # ══════════════════════════════

    def _on_layout_clicked(self, layout_key: str) -> None:
        """布局按钮点击：切换选中态并触发重算。"""
        if layout_key == self._selected_layout:
            return
        self._selected_layout = layout_key
        self._update_layout_buttons(layout_key)
        self._recompute()

    def _update_layout_buttons(self, active: str) -> None:
        """刷新布局按钮视觉：选中 = solid + 圆点前缀，未选 = outlined。"""
        for key, btn in self._layout_buttons.items():
            selected = key == active
            btn.variant = "solid" if selected else "outlined"
            label = self._layout_labels.get(key, key)
            btn.setText(_LAYOUT_SELECTED_PREFIX + label if selected else label)

    def _recompute(self) -> None:
        """读取控件状态 → 调服务计算 → 更新两表。

        异常分支：
        - 倾向值非法：清空表格（用户正在输入，不崩溃即可）
        - 数据文件缺失/损坏：保留上次结果，仅显示底部红色提示
        """
        if self._weapon_combo is None or self._disposition_edit is None:
            return

        weapon = self._weapon_combo.currentText()
        disp_text = self._disposition_edit.text().strip()

        try:
            disposition = float(disp_text)
        except ValueError:
            self._clear_results()
            return

        try:
            result = riven_calc_service.compute(
                weapon, disposition, self._selected_layout
            )
        except (OSError, ValueError) as exc:
            # FileNotFoundError / json.JSONDecodeError（是 ValueError 子类）等：
            # 数据文件问题不应让页面空白，保留结果 + 提示
            self._set_data_error(exc)
            return

        self._set_data_error(None)

        if self._positive_table is not None:
            self._positive_table.set_rows(result["positive"])

        if self._negative_card is not None:
            has_neg = result["has_negative"]
            self._negative_card.setVisible(has_neg)
            if has_neg and self._negative_table is not None:
                self._negative_table.set_rows(result["negative"])

    def _clear_results(self) -> None:
        """清空结果表格（倾向值非法时调用）。"""
        if self._positive_table is not None:
            self._positive_table.set_rows([])
        if self._negative_table is not None:
            self._negative_table.set_rows([])
        if self._negative_card is not None:
            self._negative_card.setVisible(False)

    def _on_clear_inputs(self) -> None:
        """清空两张表所有「我的数值」输入（位置列同步重置）。"""
        for table in (self._positive_table, self._negative_table):
            if table is not None:
                table.clear_inputs()

    def _set_data_error(self, exc: Exception | None) -> None:
        """显示/隐藏数据文件错误提示；有异常时附带具体原因。"""
        if self._error_lbl is None:
            return
        if exc is None:
            self._error_lbl.setVisible(False)
            return
        text = self._copy(
            "riven_calc.data_error",
            "紫卡数据文件缺失或损坏（riven_base.json），请从安装包恢复该文件。",
        )
        self._error_lbl.setText(f"{text}（{exc}）")
        self._error_lbl.setVisible(True)

    # ══════════════════════════════
    #  倾向反查（武器名 → Wiki 页面直达）
    # ══════════════════════════════

    def _on_wiki_text_edited(self) -> None:
        """用户手动输入：重启防抖计时（停止输入后才查 sqlite）。"""
        if self._wiki_debounce is not None:
            self._wiki_debounce.start()

    def _wiki_refresh_candidates(self) -> None:
        """按当前输入刷新候选下拉项并弹出。

        同时管理「未找到匹配」提示：有候选则隐藏、无候选则显示，
        避免回车时使用上一次查询的陈旧列表。
        """
        if self._wiki_combo is None:
            return
        keyword = self._wiki_combo.lineEdit().text()
        items = riven_wiki_service.search_weapons(keyword, _WIKI_MAX_CANDIDATES)

        combo = self._wiki_combo
        # blockSignals：程序化填充不触发 activated/currentTextChanged
        combo.blockSignals(True)
        combo.clear()
        for it in items:
            label = f"{it['zh_name']}（{it['en_name']}）"
            combo.addItem(label, it["wiki_url"])
        combo.blockSignals(False)

        if items:
            if self._wiki_error_lbl is not None:
                self._wiki_error_lbl.setVisible(False)
            combo.showPopup()
        elif self._wiki_error_lbl is not None:
            # 有关键词但无候选：给出明确反馈（空输入由调用方拦截）
            self._wiki_error_lbl.setVisible(bool(keyword.strip()))

    def _on_wiki_activated(self, index: int) -> None:
        """候选弹窗选中一项：直接用系统浏览器打开对应 Wiki 页面。"""
        if self._wiki_combo is None:
            return
        url = self._wiki_combo.itemData(index)
        label = self._wiki_combo.itemText(index)
        if url:
            self._wiki_open_url(str(url), label)

    def _on_wiki_return_pressed(self) -> None:
        """回车：按精确匹配打开；不精确则刷新候选让用户选择。"""
        if self._wiki_combo is None:
            return
        keyword = self._wiki_combo.lineEdit().text()
        if not keyword.strip():
            return
        matched = riven_wiki_service.resolve_weapon(keyword)
        if matched is not None:
            label = f"{matched['zh_name']}（{matched['en_name']}）"
            self._wiki_open_url(matched["wiki_url"], label)
        else:
            # 同步刷新候选（含 0 匹配时的错误提示），不依赖防抖定时器是否已触发
            self._wiki_refresh_candidates()

    def _wiki_open_url(self, url: str, label: str) -> None:
        """打开 Wiki 页面（系统默认浏览器）并展示可点击链接。

        wiki.warframe.com 有 JS 反爬挑战，程序直连抓取会被拦截；
        用户自己的浏览器点击/回车即可正常通过挑战查看 Disposition。
        """
        QDesktopServices.openUrl(QUrl(url))

        if self._wiki_error_lbl is not None:
            self._wiki_error_lbl.setVisible(False)
        if self._wiki_link_lbl is not None:
            # 内联色随 token 主题走（链接点击由 QLabel.openExternalLinks 处理）
            self._wiki_link_lbl.setText(
                f'<span style="color:{self._color("text.secondary")}">{label}</span>　'
                f'<a href="{url}" '
                f'style="color:{self._color("accent.primary")}">{url}</a>'
            )
            self._wiki_link_lbl.setVisible(True)
