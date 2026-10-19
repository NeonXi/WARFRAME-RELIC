"""
[L2] RivenCalcPage — 紫卡数值计算器页面

依赖: widgets/(CyberCard/CyberComboBox/CyberButton/CyberLineEdit/CyberRivenResultTable),
      services/riven_calc_service(纯逻辑层), PySide6
职责: 武器类型 + 倾向值 + 布局 → 实时计算并展示全部词条的最低/最高值。

数据流（单向）:
    用户操作控件 → riven_calc_service.compute() → 表格 set_rows()

布局:
    页面由 QScrollArea 承载（整体可能超出窗口，保证在小屏也完整可见）；
    内部含「控制栏」+「正面词条表格」+「负面词条表格（含负面时显示）」。
    每张结果表独立限定可视行数并自带纵向滚动，因此表头冻结在各自表格顶部。

生命周期:
    on_enter: 默认触发一次计算（控件值已在构造期初始化，用户不必先交互
              即可看到默认布局下的结果）。
    on_leave: 无定时器/心跳，无需清理。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget, QScrollArea, QFrame,
)

from core.pages.base_page import PageBase
from core.services import riven_calc_service
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
# 倾向值输入框默认值（倾向 1.0 为基准中性值）
_DEFAULT_DISPOSITION = "1.00"
# 首次进入时的默认布局（选「3正1负」可同时展示两组表格，功能一览）
_DEFAULT_LAYOUT = "3正1负"


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
        self._selected_layout: str = _DEFAULT_LAYOUT
        self._positive_table: CyberRivenResultTable | None = None
        self._negative_table: CyberRivenResultTable | None = None
        self._negative_card: CyberCard | None = None
        self._formula_lbl: QLabel | None = None

        super().__init__()
        self.page_title = self._copy("nav.riven_calc", "紫卡数值计算器")

    # ══════════════════════════════
    #  生命周期
    # ══════════════════════════════

    def on_enter(self):
        """进入页面时立即按当前控件状态计算一次（用户无需先交互）。"""
        self._recompute()

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
        self._formula_lbl = QLabel(
            self._copy(
                "riven_calc.formula",
                "公式：最终数值 = 基础数值 × 倾向值 × 修正系数 × 浮动系数（0.9 ~ 1.1）",
            )
        )
        self._style(self._formula_lbl, color="text.tertiary", font_size="xs")
        layout.addWidget(self._formula_lbl)

        # ── 控制栏卡片 ──
        layout.addWidget(self._build_control_card())

        # ── 正面词条结果 ──
        layout.addWidget(self._build_positive_section())

        # ── 负面词条结果（含负面的布局时才可见）──
        layout.addWidget(self._build_negative_section())

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_control_card(self) -> CyberCard:
        """构建控制栏：武器类型 / 倾向值 / 布局按钮。"""
        card = CyberCard()
        vl = QVBoxLayout()
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(self._spacing("sm", 8))

        # Row 1: 武器类型 + 倾向值
        row1 = QHBoxLayout()
        row1.setSpacing(self._spacing("sm", 8))

        # 武器类型
        lbl_weapon = QLabel(self._copy("riven_calc.weapon_label", "武器类型"))
        self._style(lbl_weapon, color="text.secondary", font_size="sm")
        row1.addWidget(lbl_weapon)

        self._weapon_combo = CyberComboBox()
        self._weapon_combo.setFixedWidth(_WEAPON_COMBO_WIDTH)
        self._weapon_combo.addItems(riven_calc_service.list_weapon_types())
        self._weapon_combo.currentTextChanged.connect(self._recompute)
        row1.addWidget(self._weapon_combo)

        row1.addSpacing(self._spacing("md", 12))

        # 倾向值
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

        # Row 2: 布局切换按钮组（单选互斥，视觉上 solid=选中 / outlined=未选）
        row2 = QHBoxLayout()
        row2.setSpacing(self._spacing("sm", 8))

        lbl_layout = QLabel(self._copy("riven_calc.layout_label", "词条布局"))
        self._style(lbl_layout, color="text.secondary", font_size="sm")
        row2.addWidget(lbl_layout)

        for layout_key in riven_calc_service.list_layouts():
            btn = CyberButton(layout_key, variant="outlined")
            btn.setFixedWidth(_LAYOUT_BTN_WIDTH)
            btn.clicked.connect(lambda _checked=False, k=layout_key: self._on_layout_clicked(k))
            self._layout_buttons[layout_key] = btn
            row2.addWidget(btn)

        row2.addStretch()
        vl.addLayout(row2)

        card.content_layout().addLayout(vl)

        # 初始化默认选中
        self._update_layout_buttons(_DEFAULT_LAYOUT)
        return card

    def _build_positive_section(self) -> CyberCard:
        """构建「正面词条」卡片 + 冻结表头表格。"""
        card = CyberCard()
        vl = QVBoxLayout()
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(self._spacing("sm", 8))

        header = QLabel(self._copy("riven_calc.positive_title", "正面词条"))
        self._style(header, color="accent.primary", font_size="md")
        vl.addWidget(header)

        self._positive_table = CyberRivenResultTable(is_negative=False)
        vl.addWidget(self._positive_table)

        card.content_layout().addLayout(vl)
        return card

    def _build_negative_section(self) -> CyberCard:
        """构建「负面词条」卡片 + 冻结表头表格；初始可见性由布局决定。"""
        card = CyberCard()
        self._negative_card = card
        vl = QVBoxLayout()
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(self._spacing("sm", 8))

        header = QLabel(self._copy("riven_calc.negative_title", "负面词条"))
        self._style(header, color="alias.semantic.danger", font_size="md")
        vl.addWidget(header)

        self._negative_table = CyberRivenResultTable(is_negative=True)
        vl.addWidget(self._negative_table)

        card.content_layout().addLayout(vl)
        # 默认按初始布局决定是否显示
        card.setVisible(riven_calc_service.get_layout(_DEFAULT_LAYOUT)["neg"] != 0.0)
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
        """刷新四个布局按钮的视觉状态：选中=solid，其余=outlined。"""
        for key, btn in self._layout_buttons.items():
            btn.variant = "solid" if key == active else "outlined"

    def _recompute(self) -> None:
        """读取控件状态 → 调服务计算 → 更新两表。"""
        if self._weapon_combo is None or self._disposition_edit is None:
            return

        weapon = self._weapon_combo.currentText()
        disp_text = self._disposition_edit.text().strip()

        try:
            disposition = float(disp_text)
        except ValueError:
            # 倾向值非法时清空表格（用户输入中不必崩溃）
            if self._positive_table is not None:
                self._positive_table.set_rows([])
            if self._negative_table is not None:
                self._negative_table.set_rows([])
            if self._negative_card is not None:
                self._negative_card.setVisible(False)
            return

        result = riven_calc_service.compute(weapon, disposition, self._selected_layout)

        if self._positive_table is not None:
            self._positive_table.set_rows(result["positive"])

        if self._negative_card is not None:
            has_neg = result["has_negative"]
            self._negative_card.setVisible(has_neg)
            if has_neg and self._negative_table is not None:
                self._negative_table.set_rows(result["negative"])
