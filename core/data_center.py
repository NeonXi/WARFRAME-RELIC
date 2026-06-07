"""
后台数据处理中心
布局层级:
  顶部横栏 ── 一级导航: [数据链路] [数据表] [操作日志]
  ┌──────────┬─────────────────────────────┐
  │ 次级导航  │       主内容区              │
  │ (可选)   │   (QStackedWidget)         │
  └──────────┴─────────────────────────────┘
"""
import sqlite3
from pathlib import Path

from data.ui_strings import S
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QStackedWidget, QFrame, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, qRgba

from core.constants import theme
from core.json_viewer import JsonViewerPage


# ============================================================
# 数据访问层
# ============================================================

class DataRepository:
    def __init__(self):
        self._data_dir = Path("data")
        self._db_path = self._data_dir / "warframe.db"

    @property
    def available(self) -> bool:
        return self._db_path.exists()

    @property
    def items_available(self) -> bool:
        return self._db_path.exists()

    def all_databases(self) -> list[dict]:
        """返回数据库元信息。"""
        return [
            {"name": "warframe.db", "path": self._db_path, "label": "Warframe 统一数据库", "exists": self._db_path.exists()}
        ]

    def tables(self, db_path: Path = None) -> list[str]:
        db_path = db_path or self._db_path
        if not db_path.exists():
            return []
        try:
            with sqlite3.connect(db_path, check_same_thread=False) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def schema(self, table: str, db_path: Path = None) -> list[dict]:
        db_path = db_path or self._db_path
        if not db_path.exists():
            return []
        try:
            with sqlite3.connect(db_path, check_same_thread=False) as conn:
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return [
                {"cid": c[0], "name": c[1], "type": c[2],
                 "notnull": bool(c[3]), "default": c[4], "pk": bool(c[5])}
                for c in cols
            ]
        except Exception:
            return []

    def count(self, table: str, db_path: Path = None) -> int:
        db_path = db_path or self._db_path
        if not db_path.exists():
            return 0
        try:
            with sqlite3.connect(db_path, check_same_thread=False) as conn:
                return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            return 0

    def total_count(self) -> int:
        return sum(self.count(t) for t in self.tables())

    def query(self, sql: str, db_path: Path = None, params: tuple = ()) -> tuple[list[str], list[tuple]]:
        """执行 SELECT 查询，返回 (列名列表, 行数据列表)"""
        db_path = db_path or self._db_path
        if not db_path.exists():
            return [], []
        try:
            with sqlite3.connect(db_path, check_same_thread=False) as conn:
                cur = conn.execute(sql, params)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchall()
            return cols, rows
        except Exception as e:
            return [], [("query_error", str(e))]


# ============================================================
# 样式常量
# ============================================================

STYLE_TOP_BAR = f"""
    QFrame {{
        background: {theme.card_bg};
        border: none;
    }}
"""

STYLE_MAIN_BTN = f"""
    QPushButton {{
        background: transparent;
        color: {theme.text_dim};
        border: none;
        border-radius: 6px;
        font-size: 13px;
        padding: 8px 20px;
    }}
    QPushButton:hover {{
        background: rgba(255,255,255,0.06);
        color: {theme.text};
    }}
    QPushButton:checked {{
        background: rgba(0,255,255,0.12);
        color: {theme.cyber_cyan};
    }}
"""

STYLE_SIDE_PANEL = f"""
    QFrame {{
        background: {theme.card_bg};
        border: none;
    }}
"""

STYLE_SIDE_LIST = f"""
    QListWidget {{
        background: transparent;
        border: none;
        font-size: 13px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 10px 18px;
        color: {theme.text_dim};
        border: none;
        border-radius: 6px;
        margin: 2px 8px;
    }}
    QListWidget::item:hover {{
        background: rgba(255,255,255,0.05);
        color: {theme.text};
    }}
    QListWidget::item:selected {{
        background: rgba(0,255,255,0.12);
        color: {theme.cyber_cyan};
    }}
"""

STYLE_CONTENT = f"""
    QStackedWidget {{
        background: {theme.panel_bg};
        border: none;
    }}
"""

STYLE_STATUS_BAR = f"""
    QFrame {{
        background: {theme.card_bg};
        border: none;
        min-height: 26px;
        max-height: 26px;
    }}
"""

STYLE_DEMO_CARD = f"""
    QFrame {{
        background: {theme.card_bg};
        border: none;
        border-radius: 12px;
    }}
"""

STYLE_REFRESH_BTN = f"""
    QPushButton {{
        background: transparent;
        color: {theme.text_dim};
        border: none;
        border-radius: 4px;
        font-size: 14px;
    }}
    QPushButton:hover {{
        background: rgba(255,255,255,0.08);
        color: {theme.cyber_cyan};
    }}
"""


# ============================================================
# 导航配置
# ============================================================

MAIN_TABS = [
    # (图标, 标签, 索引, 有次级导航)
    ("📊", "数据链路", 0, True),
    ("🗄️", "数据表",   1, True),
    ("📝", "操作日志", 2, False),
    ("📂", "源数据浏览", 3, False),
]

SIDE_NAV = {
    0: [("source", "数据源"), ("fetch", "数据拉取"), ("parse", "数据解析"), ("store", "数据存储")],
    1: [("tables", "表列表"), ("structure", "表结构"), ("query", "数据查询")],
}

SIDE_TITLES = {0: "数据链路", 1: "数据表", 2: "操作日志", 3: "源数据浏览"}


# ============================================================
# 主窗口
# ============================================================

class DataCenterWindow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repo = DataRepository()
        self._current_tab = 0
        self._nav_btns: list[QPushButton] = []
        self._selected_db_path = None
        self._selected_table = None

        self.setWindowTitle("后台数据处理中心")
        self.setMinimumSize(1000, 600)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build()
        self.showMaximized()

    def closeEvent(self, event):
        super().closeEvent(event)

    # ======================== 整体布局 ========================

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._top_bar())
        root.addWidget(self._body(), 1)
        root.addWidget(self._status_bar())

    # ======================== 顶部一级导航 ========================

    def _top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(STYLE_TOP_BAR)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(0)

        # 品牌
        brand = QLabel("⚙️  数据中心")
        brand.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {theme.cyber_cyan};"
            f" margin-right: 20px;"
        )
        layout.addWidget(brand)

        # 导航按钮
        for icon, label, idx, _has_side in MAIN_TABS:
            btn = QPushButton(f" {icon}  {label}  ")
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setStyleSheet(STYLE_MAIN_BTN)
            btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))
            self._nav_btns.append(btn)
            layout.addWidget(btn)

        self._nav_btns[0].setChecked(True)
        layout.addStretch()

        # 刷新
        refresh = QPushButton("🔄")
        refresh.setFixedSize(30, 30)
        refresh.setStyleSheet(STYLE_REFRESH_BTN)
        refresh.setToolTip("刷新数据")
        refresh.clicked.connect(self._refresh)
        layout.addWidget(refresh)

        # 在线状态
        ok = self._repo.available
        status = QLabel("🟢 在线" if ok else "🔴 离线")
        status.setStyleSheet(
            f"color: {theme.cyber_green if ok else theme.cyber_red};"
            f" font-size: 12px; margin-left: 12px;"
        )
        layout.addWidget(status)

        return bar

    # ======================== 主体 ========================

    def _body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,0.04); }")

        # 左侧次级导航
        self._side_panel = self._side_bar()
        splitter.addWidget(self._side_panel)

        # 右侧内容区
        self._content = QStackedWidget()
        self._content.setStyleSheet(STYLE_CONTENT)
        self._content.addWidget(self._link_page())
        self._content.addWidget(self._table_page())
        self._content.addWidget(self._demo_page(2))
        self._content.addWidget(JsonViewerPage())
        splitter.addWidget(self._content)

        splitter.setSizes([200, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        return splitter

    def _side_bar(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(STYLE_SIDE_PANEL)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        hdr = QFrame()
        hdr.setStyleSheet("background: rgba(0,0,0,0.08);")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(18, 12, 18, 12)
        self._side_title = QLabel(SIDE_TITLES[0])
        self._side_title.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {theme.text_dim};"
            f" letter-spacing: 1px;"
        )
        hl.addWidget(self._side_title)
        layout.addWidget(hdr)

        # 列表
        self._side_list = QListWidget()
        self._side_list.setStyleSheet(STYLE_SIDE_LIST)
        self._side_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._side_list.itemClicked.connect(self._on_side_click)
        layout.addWidget(self._side_list, 1)

        # 初始默认填充（不调 _fill_side，避免访问尚未创建的 self._side_panel）
        self._side_title.setText(SIDE_TITLES[0])
        for key, label in SIDE_NAV.get(0, []):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._side_list.addItem(item)
        if self._side_list.count():
            self._side_list.setCurrentRow(0)

        return panel

    # ======================== 数据链路页面 ========================

    # ── 阶段分组定义 ──
    LINK_SECTIONS = [
        ("数据源", [
            ("🌐", "All.json", "WFCD warframe-items",
             "全物品详细数据 (16,629 条)，含 name / category / type / tradable / rarity / mr\nabilities / attacks / components / drops / patchlogs 等完整属性",
             True),
            ("🌐", "i18n.json", "WFCD warframe-items",
             "多语言翻译数据，uniqueName → 14 种语言的 {name, description}\n共 232,568 条翻译记录",
             True),
            ("🌐", "all.json", "WFCD warframe-drop-data (DE 官方)",
             "DE 官方掉落数据，包含 relics / missionRewards / modLocations\nenemyModTables / blueprintLocations / sortieRewards / bountyRewards\ntransientRewards / keyRewards / syndicates 等完整掉落信息",
             True),
            ("🌐", "dict.en.json", "calamity-inc/warframe-public-export-plus",
             "DE 官方 Public Export 英文翻译数据，35,381 条\n/Lotus/Language/... key → 英文值",
             True),
            ("🌐", "dict.zh.json", "calamity-inc/warframe-public-export-plus",
             "DE 官方 Public Export 中文翻译数据，35,381 条\n/Lotus/Language/... key → 中文值",
             True),
        ]),
        ("数据拉取", [
            ("⬇️", "Git 稀疏检出", "WFCD/warframe-items → 本地",
             "clone --depth=1 --filter=blob:none --sparse\n→ All.json / i18n.json (16,629 物品 + 14 语言翻译)",
             True),
            ("⬇️", "Git 稀疏检出", "WFCD/warframe-drop-data → 本地",
             "clone --depth=1 --filter=blob:none --sparse\n→ all.json (DE 官方掉落数据，含遗物/任务/敌人掉落)",
             True),
            ("⬇️", "Git 稀疏检出", "public-export-plus → 本地",
             "clone --depth=1 --branch=senpai --filter=blob:none --sparse\n→ dict.en.json / dict.zh.json (35,381 条游戏术语翻译)",
             True),
            ("⬇️", "WM API 拉取", "warframe.market/v2/items",
             "HTTP GET → 市场物品映射 (slug, en_name, id)\n网络不通时跳过，不影响核心数据",
             True),
        ]),
        ("数据解析", [
            ("🧪", "JSON 格式验证", "json.loads",
             "验证 5 个 JSON 文件格式正确性 → 输出记录数统计",
             True),
            ("📦", "All.json 解析", "build_warframe_db.py",
             "16,629 条物品 → items 主表 (uniqueName, name, type, category, tradable, ...)\n类型专属属性 → item_type_attrs (JSON 扩展，6,907 条)\n技能 → item_abilities (501 条)\n攻击模式 → item_attacks (1,779 条)\n制造组件 → item_components (5,969 条)\n掉落来源 → item_drops (44,700 条)\n更新日志 → item_patchlogs (32,129 条)",
             True),
            ("🌍", "i18n.json 解析", "build_warframe_db.py",
             "232,568 条翻译 → item_translations (uniqueName, lang, name, description)\n中文翻译回填 items.zh_name / items.description_zh (16,427 条)",
             True),
            ("🎯", "all.json 遗物解析", "build_warframe_db.py",
             "3,014 条遗物 → relics (tier, relic_name, state, vaulted)\n18,086 条奖励 → relic_rewards (item_name, rarity, chance)\nitemName 关联 items.uniqueName 构建跨表关联",
             True),
            ("🗺️", "all.json 任务掉落解析", "build_warframe_db.py",
             "24 个星球 → planets\n431 个节点 → mission_nodes (planet_id, game_mode)\n10,287 条奖励 → mission_rewards (rotation A/B/C)",
             True),
            ("⚔️", "all.json 敌人掉落解析", "build_warframe_db.py",
             "Mod 掉落 → mod_drops (6,494 条) + enemy_mod_tables (6,517 条)\n蓝图掉落 → blueprint_drops (311 条) + enemy_bp_tables (311 条)",
             True),
            ("🏆", "all.json 特殊奖励解析", "build_warframe_db.py",
             "突击 → sortie_rewards (17 条)\n赏金 → bounty_rewards (2,221 条，6 个来源: cetus/solaris/deimos/zariman/entrati_lab/hex)\n临时 → transient_rewards (744 条，仲裁等)\n钥匙 → key_rewards (108 条)\n集团 → syndicate_rewards (1,707 条)",
             True),
            ("📖", "dict.en/zh.json 解析", "build_warframe_db.py",
             "35,381 条翻译 → game_translations (key, en, zh, category)\n从 /Lotus/Language/... 路径推断分类 (Missions/Items/Relics/...)",
             True),
            ("💰", "WM 物品映射", "build_warframe_db.py",
             "WM API → market_items (id, slug, en_name, item_unique)\nen_name 关联 items.uniqueName 构建跨表关联",
             True),
            ("🔗", "跨表关联构建", "name_map",
             "All.json name → uniqueName 映射 (16,629 条)\n用于 all.json 的 itemName → items.unique_name 关联\n遗物奖励/任务奖励/敌人掉落均通过此映射关联到物品主表",
             True),
            ("🛡️", "类型安全转换", "_safe_str/_safe_int/_safe_float",
             "JSON 字段类型不一致时的安全处理:\nintroduced (dict→JSON str), description (list→JSON str)\n数值字段 None→NULL, 非数值→NULL",
             True),
        ]),
        ("数据存储", [
            ("🏗️", "warframe.db 建表", "SCHEMA_SQL",
             "25 张表，统一单库设计:\n核心物品: items / item_type_attrs / item_abilities / item_attacks / item_components / item_drops / item_patchlogs\n翻译: item_translations / game_translations\n遗物: relics / relic_rewards\n任务掉落: planets / mission_nodes / mission_rewards\n敌人掉落: mod_drops / enemy_mod_tables / blueprint_drops / enemy_bp_tables\n特殊奖励: sortie_rewards / bounty_rewards / transient_rewards / key_rewards / syndicate_rewards\n市场: market_items\n元数据: db_meta\nPRAGMA journal_mode=WAL · PRAGMA foreign_keys=ON",
             True),
            ("📊", "索引创建", "CREATE INDEX",
             "items: name / zh_name / type / category / tradable / is_prime\nrelic_rewards: relic_id / item_name / item_unique\nmission_rewards: node_id / item_name / rotation\nmod_drops: mod_name / enemy_name\ngame_translations: category / en / zh\nmarket_items: slug / en_name / zh_name / item_unique",
             True),
            ("✅", "批量写入", "executemany + commit",
             "每步解析完成后批量 INSERT + 统一事务提交\nitems: 16,629 | translations: 232,568 | relic_rewards: 18,086\nmission_rewards: 10,287 | drops: 6,494 | patchlogs: 32,129",
             True),
            ("🔄", "数据库优化", "VACUUM",
             "全量写入后执行 VACUUM 压缩\n最终大小约 124 MB，构建耗时约 7-8 秒",
             True),
            ("📋", "元数据记录", "db_meta",
             "schema_version: 1\nbuild_time: 构建时间\nbuild_elapsed_sec: 耗时\ndrop_data_hash / items_commit / i18n_commit: 数据版本追踪",
             True),
        ]),
    ]

    def _link_page(self) -> QWidget:
        """数据链路页面 —— 按阶段分组展示完整数据处理管道"""
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # 标题
        title = QLabel("📊  数据链路")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {theme.cyber_cyan};")
        layout.addWidget(title)

        desc = QLabel("ETL 管线：从外部数据源到本地数据库的完整处理链路")
        desc.setStyleSheet(f"font-size: 13px; color: {theme.text_dim};")
        layout.addWidget(desc)

        # 构建扁平节点列表（含阶段标题行）
        nodes = []
        self._link_section_rows: dict[str, int] = {}
        row = 0
        for section_name, section_nodes in self.LINK_SECTIONS:
            nodes.append(("section", section_name))
            self._link_section_rows[section_name] = row + 1
            row += 1
            for node in section_nodes:
                nodes.append(node)
                row += 1

        # 表格
        table = QTableWidget()
        table.setColumnCount(3)
        table.setRowCount(len(nodes))
        table.setHorizontalHeaderLabels(["", "链路步骤", "详细描述"])
        table.setStyleSheet(self._link_table_style())

        # 列宽 —— 前两列允许用户拖拽调节
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 44)
        table.setColumnWidth(1, 170)

        # 行高
        table.verticalHeader().setDefaultSectionSize(64)
        table.verticalHeader().setVisible(False)

        # 填充数据
        section_bg = qRgba(0, 0, 0, 40)
        section_fg = QColor(theme.cyber_cyan)
        for i, node in enumerate(nodes):
            if node[0] == "section":
                # 阶段标题行
                item = QTableWidgetItem(f"  ▸  {node[1]}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setBackground(QColor.fromRgba(section_bg))
                item.setForeground(section_fg)
                font = item.font()
                font.setPointSize(11)
                font.setBold(True)
                item.setFont(font)
                table.setItem(i, 0, item)
                table.setSpan(i, 0, 1, 3)
                table.setRowHeight(i, 36)
            else:
                icon, name, component, detail, active = node

                # 状态列
                status_item = QTableWidgetItem(icon)
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_item.setFlags(Qt.ItemFlag.NoItemFlags)
                table.setItem(i, 0, status_item)

                # 步骤列
                step_text = f"{name}\n{component}"
                step_item = QTableWidgetItem(step_text)
                step_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                step_item.setFlags(Qt.ItemFlag.NoItemFlags)
                step_item.setToolTip(step_text)
                table.setItem(i, 1, step_item)

                # 描述列
                desc_item = QTableWidgetItem(detail)
                desc_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                desc_item.setFlags(Qt.ItemFlag.NoItemFlags)
                desc_item.setToolTip(detail)
                table.setItem(i, 2, desc_item)

                if not active:
                    for col in range(3):
                        item = table.item(i, col)
                        if item:
                            item.setForeground(Qt.GlobalColor.darkGray)

                # 根据内容自适应行高（仅数据行，阶段标题行保持固定 36）
                table.resizeRowToContents(i)
                if table.rowHeight(i) < 60:
                    table.setRowHeight(i, 60)

        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)

        self._link_table = table
        layout.addWidget(table, 1)

        return pg

    def _link_table_style(self) -> str:
        return f"""
            QTableWidget {{
                background: {theme.card_bg};
                border: none;
                border-radius: 10px;
                font-size: 13px;
                color: {theme.text};
                gridline-color: rgba(255,255,255,0.04);
                alternate-background-color: rgba(255,255,255,0.03);
            }}
            QTableWidget::item {{
                padding: 8px 14px;
                border: none;
            }}
            QHeaderView {{
                background: {theme.panel_bg};
            }}
            QHeaderView::section {{
                background: {theme.panel_bg};
                color: rgba(255,255,255,0.65);
                font-size: 12px;
                font-weight: 600;
                padding: 10px 14px;
                border: none;
                border-bottom: 1px solid rgba(255,255,255,0.03);
            }}
            QTableCornerButton::section {{
                background: {theme.panel_bg};
                border: none;
            }}
        """

    # ======================== 数据表页面 ========================

    def _table_page(self) -> QWidget:
        """数据表页面 —— 包含表列表 / 表结构 / 数据查询 三个子页面"""
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table_stack = QStackedWidget()
        self._table_stack.addWidget(self._table_list_page())
        self._table_stack.addWidget(self._table_structure_page())
        self._table_stack.addWidget(self._table_query_page())
        layout.addWidget(self._table_stack, 1)

        return pg

    # ── 子页面: 表列表 ──

    # 表分类标签
    _TABLE_CATEGORIES = {
        'items': '核心物品', 'item_type_attrs': '核心物品', 'item_abilities': '核心物品',
        'item_attacks': '核心物品', 'item_components': '核心物品', 'item_drops': '核心物品',
        'item_patchlogs': '核心物品', 'item_translations': '核心物品',
        'relics': '遗物', 'relic_rewards': '遗物',
        'planets': '任务掉落', 'mission_nodes': '任务掉落', 'mission_rewards': '任务掉落',
        'mod_drops': 'Mod掉落', 'enemy_mod_tables': 'Mod掉落',
        'blueprint_drops': '蓝图掉落', 'enemy_bp_tables': '蓝图掉落',
        'sortie_rewards': '特殊奖励', 'bounty_rewards': '特殊奖励',
        'transient_rewards': '特殊奖励', 'key_rewards': '特殊奖励', 'syndicate_rewards': '特殊奖励',
        'game_translations': '翻译', 'market_items': '市场',
        'db_meta': '元数据',
    }

    def _table_list_page(self) -> QWidget:
        """列出数据库所有表，含状态指示"""
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        title = QLabel("🗄️  数据表列表")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {theme.cyber_cyan};")
        layout.addWidget(title)

        desc = QLabel("warframe.db 统一数据库 — 所有表及其属性概览")
        desc.setStyleSheet(f"font-size: 13px; color: {theme.text_dim};")
        layout.addWidget(desc)

        # 汇总卡
        db = self._repo.all_databases()[0]
        total_tables = len(self._repo.tables(db["path"])) if db["exists"] else 0
        total_rows = sum(self._repo.count(t, db["path"]) for t in self._repo.tables(db["path"])) if db["exists"] else 0
        db_size = db["path"].stat().st_size / 1024 / 1024 if db["exists"] else 0
        status_text = "🟢 已构建" if db["exists"] else "🔴 未构建"
        summary = QLabel(f"{status_text}  |  {total_tables} 张表  |  {total_rows:,} 行数据  |  {db_size:.1f} MB")
        summary.setStyleSheet(f"font-size: 12px; color: {theme.cyber_green}; padding: 4px 0;")
        layout.addWidget(summary)

        # 构建数据
        headers = ["分类", "表名", "行数", "列数"]
        rows_data = []
        self._table_row_db: list[tuple] = []  # (db_path, table_name) 供选中查询

        if db["exists"]:
            tables = self._repo.tables(db["path"])
            for table in tables:
                cnt = self._repo.count(table, db["path"])
                cols = len(self._repo.schema(table, db["path"]))
                category = self._TABLE_CATEGORIES.get(table, '其他')
                rows_data.append({
                    "category": category,
                    "table": table,
                    "rows": f"{cnt:,}",
                    "cols": str(cols),
                    "db_path": db["path"],
                })
                self._table_row_db.append((db["path"], table))

        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows_data))
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(self._link_table_style())
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        hh = table.horizontalHeader()
        for ci in range(len(headers)):
            hh.setSectionResizeMode(ci, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 200)
        table.setColumnWidth(2, 90)
        table.setColumnWidth(3, 60)

        table.verticalHeader().setDefaultSectionSize(42)
        table.verticalHeader().setVisible(False)

        # 分类颜色
        cat_colors = {
            '核心物品': QColor(theme.cyber_cyan),
            '遗物': QColor(theme.cyber_yellow),
            '任务掉落': QColor(theme.cyber_green),
            'Mod掉落': QColor(0xBB, 0x86, 0xFC),
            '蓝图掉落': QColor(0xFF, 0x7C, 0x43),
            '特殊奖励': QColor(0xEF, 0x53, 0x50),
            '翻译': QColor(0x26, 0xC6, 0xDA),
            '市场': QColor(0xFF, 0xCA, 0x28),
            '元数据': QColor(theme.text_dim),
            '其他': QColor(theme.text_dim),
        }

        for ri, row_data in enumerate(rows_data):
            values = [row_data["category"], row_data["table"], row_data["rows"], row_data["cols"]]
            for ci, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if ci == 0:
                    item.setForeground(cat_colors.get(val, QColor(theme.text_dim)))
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                table.setItem(ri, ci, item)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)

        layout.addWidget(table, 1)

        self._table_list_table = table
        table.itemSelectionChanged.connect(self._on_table_selected)
        return pg

    def _on_table_selected(self):
        """表列表选中时更新状态"""
        tbl = self._table_list_table
        sel = tbl.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        if row < len(self._table_row_db):
            self._selected_db_path, self._selected_table = self._table_row_db[row]

    # ── 子页面: 表结构 ──

    def _table_structure_page(self) -> QWidget:
        """查看选中表的字段结构"""
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        title = QLabel("🏗️  表结构详情")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {theme.cyber_cyan};")
        layout.addWidget(title)

        # 表选择行
        sel_row = QHBoxLayout()
        sel_row.setSpacing(12)
        sel_label = QLabel(S("data_center", "label_select_table"))
        sel_label.setStyleSheet(f"font-size: 13px; color: {theme.text_dim};")
        sel_row.addWidget(sel_label)

        self._struct_combo = QComboBox()
        self._struct_combo.setMinimumWidth(300)
        self._struct_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(255,255,255,0.06); color: {theme.text};
                border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;
                padding: 6px 12px; font-size: 13px;
            }}
            QComboBox:hover {{ border-color: rgba(255,255,255,0.15); }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {theme.card_bg}; color: {theme.text};
                selection-background-color: rgba(0,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.1);
            }}
        """)
        sel_row.addWidget(self._struct_combo)

        refresh_btn = QPushButton(S("data_center", "btn_refresh"))
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,255,255,0.1); color: {theme.cyber_cyan};
                border: none; border-radius: 6px; padding: 6px 18px; font-size: 12px;
            }}
            QPushButton:hover {{ background: rgba(0,255,255,0.2); }}
        """)
        refresh_btn.clicked.connect(self._build_structure_table)
        sel_row.addWidget(refresh_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # 填充下拉
        self._struct_refs = []  # [(db_path, table_name), ...]
        for db in self._repo.all_databases():
            for table in self._repo.tables(db["path"]):
                cat = self._TABLE_CATEGORIES.get(table, '其他')
                label = f"[{cat}]  {table}"
                self._struct_combo.addItem(label)
                self._struct_refs.append((db["path"], table))
        self._struct_combo.currentIndexChanged.connect(self._build_structure_table)

        # 结构表格
        self._struct_table = QTableWidget()
        self._struct_table.setColumnCount(5)
        self._struct_table.setHorizontalHeaderLabels(["列名", "类型", "主键", "非空", "默认值"])
        self._struct_table.setStyleSheet(self._link_table_style())
        hh = self._struct_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self._struct_table.setColumnWidth(0, 160)
        self._struct_table.setColumnWidth(1, 100)
        self._struct_table.setColumnWidth(2, 60)
        self._struct_table.setColumnWidth(3, 60)
        self._struct_table.setColumnWidth(4, 100)
        self._struct_table.verticalHeader().setDefaultSectionSize(36)
        self._struct_table.verticalHeader().setVisible(False)
        self._struct_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._struct_table.setShowGrid(True)
        self._struct_table.setAlternatingRowColors(True)
        self._struct_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._struct_table, 1)

        if self._struct_refs:
            self._struct_combo.setCurrentIndex(0)
        return pg

    def _build_structure_table(self):
        """根据下拉选择构建表结构表格"""
        idx = self._struct_combo.currentIndex()
        if idx < 0 or idx >= len(self._struct_refs):
            return
        db_path, table_name = self._struct_refs[idx]
        cols = self._repo.schema(table_name, db_path)

        tbl = self._struct_table
        tbl.setRowCount(len(cols))
        pk_color = QColor(theme.cyber_yellow)
        for ri, col in enumerate(cols):
            items = [
                (col["name"], False),
                (col["type"], False),
                ("★ PK" if col["pk"] else "", bool(col["pk"])),
                ("NOT NULL" if col["notnull"] else "", False),
                (str(col["default"]) if col["default"] is not None else "", False),
            ]
            for ci, (text, highlight) in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if ci >= 2 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                if highlight:
                    item.setForeground(pk_color)
                tbl.setItem(ri, ci, item)

    # ── 子页面: 数据查询 ──

    def _table_query_page(self) -> QWidget:
        """可视化条件查询界面"""
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("🔍  数据查询")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {theme.cyber_cyan};")
        layout.addWidget(title)

        # 表选择行
        sel_row = QHBoxLayout()
        sel_row.setSpacing(10)
        ql = QLabel(S("data_center", "label_select_table"))
        ql.setStyleSheet(f"font-size: 13px; color: {theme.text_dim};")
        sel_row.addWidget(ql)

        self._query_combo = QComboBox()
        self._query_combo.setMinimumWidth(280)
        self._query_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(255,255,255,0.06); color: {theme.text};
                border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;
                padding: 6px 12px; font-size: 13px;
            }}
            QComboBox:hover {{ border-color: rgba(255,255,255,0.15); }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {theme.card_bg}; color: {theme.text};
                selection-background-color: rgba(0,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.1);
            }}
        """)
        sel_row.addWidget(self._query_combo)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # 填充表下拉
        self._query_refs = []
        for db in self._repo.all_databases():
            for table in self._repo.tables(db["path"]):
                cat = self._TABLE_CATEGORIES.get(table, '其他')
                label = f"[{cat}]  {table}"
                self._query_combo.addItem(label)
                self._query_refs.append((db["path"], table))
        self._query_combo.currentIndexChanged.connect(self._on_query_combo_changed)

        # 筛选条件区域
        filter_label = QLabel(S("data_center", "label_filter"))
        filter_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {theme.text_dim}; margin-top: 6px;")
        layout.addWidget(filter_label)

        self._filter_rows_widget = QWidget()
        self._filter_rows_layout = QVBoxLayout(self._filter_rows_widget)
        self._filter_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_rows_layout.setSpacing(4)
        layout.addWidget(self._filter_rows_widget)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        add_btn = QPushButton("+ 添加条件")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.05); color: {theme.text_dim};
                border: 1px dashed rgba(255,255,255,0.12); border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); color: {theme.text}; }}
        """)
        add_btn.clicked.connect(self._add_filter_row)
        btn_row.addWidget(add_btn)

        limit_label = QLabel("  限制:")
        limit_label.setStyleSheet(f"font-size: 12px; color: {theme.text_dim};")
        btn_row.addWidget(limit_label)

        self._limit_combo = QComboBox()
        self._limit_combo.setFixedWidth(72)
        self._limit_combo.addItems(["10", "50", "100", "500", "1000", "无限制"])
        self._limit_combo.setCurrentText("100")
        self._limit_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(0,0,0,0.2); color: {theme.text};
                border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;
                padding: 4px 6px; font-size: 12px;
            }}
            QComboBox:hover {{ border-color: rgba(255,255,255,0.15); }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {theme.card_bg}; color: {theme.text};
                selection-background-color: rgba(0,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.1);
            }}
        """)
        btn_row.addWidget(self._limit_combo)

        btn_row.addStretch()

        qbtn = QPushButton(S("data_center", "btn_execute_query"))
        qbtn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,255,255,0.12); color: {theme.cyber_cyan};
                border: none; border-radius: 6px; padding: 6px 24px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: rgba(0,255,255,0.22); }}
        """)
        qbtn.clicked.connect(self._execute_query)
        btn_row.addWidget(qbtn)
        layout.addLayout(btn_row)

        # 结果表格
        self._query_table = QTableWidget()
        self._query_table.setStyleSheet(self._link_table_style())
        self._query_table.verticalHeader().setDefaultSectionSize(36)
        self._query_table.verticalHeader().setVisible(False)
        self._query_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._query_table.setShowGrid(True)
        self._query_table.setAlternatingRowColors(True)
        layout.addWidget(self._query_table, 1)

        # 状态栏
        self._query_status = QLabel(S("data_center", "hint_query_ready"))
        self._query_status.setStyleSheet(f"font-size: 11px; color: {theme.text_dim}; padding: 4px 0;")
        layout.addWidget(self._query_status)

        self._filter_rows: list[tuple] = []  # [(field_combo, op_combo, value_edit, remove_btn), ...]
        return pg

    def _on_query_combo_changed(self):
        """切换表时清空条件"""
        self._clear_filters()
        self._query_table.clear()
        self._query_table.setRowCount(0)
        self._query_table.setColumnCount(0)

    def _clear_filters(self):
        """清除所有筛选条件行"""
        for _, _, _, _, row_widget in self._filter_rows:
            self._filter_rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
        self._filter_rows.clear()

    def _add_filter_row(self):
        """添加一行筛选条件"""
        idx = self._query_combo.currentIndex()
        if idx < 0 or idx >= len(self._query_refs):
            return
        db_path, table_name = self._query_refs[idx]
        cols = self._repo.schema(table_name, db_path)
        if not cols:
            return

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        # 字段下拉
        field_combo = QComboBox()
        field_combo.setMinimumWidth(140)
        field_combo.setFixedHeight(28)
        field_combo.setStyleSheet(self._query_combo.styleSheet())
        for col in cols:
            field_combo.addItem(f"{col['name']}  ({col['type']})", col["name"])
        row_layout.addWidget(field_combo)

        # 运算符
        op_combo = QComboBox()
        op_combo.setFixedSize(64, 28)
        op_combo.setStyleSheet(self._query_combo.styleSheet())
        op_combo.addItems(["=", "!=", ">", "<", ">=", "<=", "LIKE", "IS NULL", "NOT NULL"])
        row_layout.addWidget(op_combo)

        # 值输入
        value_edit = QLineEdit()
        value_edit.setPlaceholderText(S("data_center", "placeholder_value"))
        value_edit.setMinimumWidth(100)
        value_edit.setFixedHeight(28)
        value_edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0,0,0,0.2); color: {theme.text};
                border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;
                padding: 2px 8px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: rgba(0,255,255,0.3); }}
        """)
        row_layout.addWidget(value_edit)

        # 删除按钮
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,60,60,0.12); color: rgba(255,100,100,0.7);
                border: none; border-radius: 3px; font-size: 14px; font-weight: 700;
                padding: 0;
            }}
            QPushButton:hover {{ background: rgba(255,40,40,0.3); color: rgba(255,120,120,1); }}
        """)
        row_layout.addWidget(remove_btn)

        self._filter_rows_layout.addWidget(row_widget)
        self._filter_rows.append((field_combo, op_combo, value_edit, remove_btn, row_widget))

        # 删除按钮事件
        def make_remove(index):
            def _remove():
                self._remove_filter_row(index)
            return _remove
        remove_btn.clicked.connect(make_remove(len(self._filter_rows) - 1))

        # 运算符切换时控制值输入可见性
        def on_op_change(index):
            value_edit.setVisible(index not in (7, 8))  # IS NULL / NOT NULL 不需要值
        op_combo.currentIndexChanged.connect(on_op_change)

    def _remove_filter_row(self, index: int):
        """删除指定筛选条件行"""
        if index < 0 or index >= len(self._filter_rows):
            return
        _, _, _, _, row_widget = self._filter_rows[index]
        self._filter_rows_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        self._filter_rows.pop(index)

    def _execute_query(self):
        """根据筛选条件构建 SQL 并执行"""
        idx = self._query_combo.currentIndex()
        if idx < 0 or idx >= len(self._query_refs):
            self._query_status.setText(S("data_center", "hint_select_table"))
            return
        db_path, table_name = self._query_refs[idx]

        # 构建 WHERE 子句
        where_parts = []
        params = []
        for field_combo, op_combo, value_edit, _, _ in self._filter_rows:
            field = field_combo.currentData()
            if not field:
                continue
            op = op_combo.currentText()
            value = value_edit.text().strip()

            if op in ("IS NULL", "NOT NULL"):
                where_parts.append(f"{field} {op}")
            else:
                if not value and op not in ("IS NULL", "NOT NULL"):
                    continue
                where_parts.append(f"{field} {op} ?")
                params.append(value)

        # 限制
        limit_text = self._limit_combo.currentText()
        if limit_text == "无限制":
            limit = -1
        else:
            try:
                limit = int(limit_text)
            except ValueError:
                limit = 100

        sql = f"SELECT * FROM {table_name}"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        if limit > 0:
            sql += f" LIMIT {limit}"

        cols, rows = self._repo.query(sql, db_path, tuple(params))

        tbl = self._query_table
        tbl.clear()
        if not cols:
            error_msg = rows[0][1] if rows else "未知错误"
            self._query_status.setText(f"查询失败: {error_msg}")
            tbl.setColumnCount(1)
            tbl.setRowCount(1)
            tbl.setHorizontalHeaderLabels(["错误"])
            tbl.setItem(0, 0, QTableWidgetItem(error_msg))
            return

        tbl.setColumnCount(len(cols))
        tbl.setRowCount(len(rows))
        tbl.setHorizontalHeaderLabels(cols)
        for ci in range(len(cols)):
            tbl.horizontalHeader().setSectionResizeMode(ci, QHeaderView.ResizeMode.Interactive)
            tbl.setColumnWidth(ci, max(100, len(cols[ci]) * 14))
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                item = QTableWidgetItem(str(val) if val is not None else "NULL")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                tbl.setItem(ri, ci, item)
        self._query_status.setText(f"查询完成: {len(rows)} 行 × {len(cols)} 列  |  {sql}")

    # ======================== 演示页面 ========================

    def _demo_page(self, idx: int) -> QWidget:
        icon, label, _, has_side = MAIN_TABS[idx]
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        # 标题
        title = QLabel(f"{icon}  {label}")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {theme.cyber_cyan};")
        layout.addWidget(title)

        # 卡片
        card = QFrame()
        card.setStyleSheet(STYLE_DEMO_CARD)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(12)

        card_title = QLabel("📋 演示面板")
        card_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {theme.cyber_yellow};"
        )
        cl.addWidget(card_title)

        items = [
            f"当前模块: {label}",
            f"索引: #{idx}",
            f"次级导航: {'有' if has_side else '无'}"
            + (f" ({len(SIDE_NAV.get(idx, []))} 项)" if has_side else ""),
        ]
        for line in items:
            cl.addWidget(self._info_label(f"  • {line}"))

        cl.addSpacing(8)
        cl.addWidget(self._info_label(
            "此处为主内容区演示占位，后续将替换为实际功能模块。"
        ))
        cl.addWidget(self._info_label(
            "点击上方一级导航切换模块，左侧次级导航切换子页面。"
        ))

        layout.addWidget(card)
        layout.addStretch()
        return pg

    def _info_label(self, text: str) -> QLabel:
        lb = QLabel(text)
        lb.setStyleSheet(f"font-size: 13px; color: {theme.text_dim};")
        lb.setWordWrap(True)
        return lb

    # ======================== 底部状态栏 ========================

    def _status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(STYLE_STATUS_BAR)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 4, 14, 4)

        # 统计数据库
        def _db_stats(db_path, label):
            if not db_path.exists():
                return f"{label}: 未构建"
            tables = len(self._repo.tables(db_path))
            records = sum(self._repo.count(t, db_path) for t in self._repo.tables(db_path))
            size_mb = db_path.stat().st_size / 1024 / 1024
            return f"{label}: {tables} 表, {records:,} 条, {size_mb:.1f} MB"

        parts = [
            _db_stats(self._repo._db_path, "warframe.db"),
        ]
        info = QLabel("  |  ".join(parts))
        info.setStyleSheet(f"font-size: 11px; color: {theme.text_dim};")
        layout.addWidget(info)
        layout.addStretch()
        layout.addWidget(QLabel("v1.0"))

        return bar

    # ======================== 事件 ========================

    def _switch_tab(self, idx: int):
        self._current_tab = idx
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == idx)
        self._content.setCurrentIndex(idx)
        self._fill_side(idx)

    def _fill_side(self, idx: int):
        try:
            self._side_list.clear()
        except RuntimeError:
            return  # C++ 对象已被删除，跳过
        has_side = MAIN_TABS[idx][3]
        self._side_panel.setVisible(has_side)

        if not has_side:
            return

        self._side_title.setText(SIDE_TITLES.get(idx, ""))
        for key, label in SIDE_NAV.get(idx, []):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._side_list.addItem(item)

        if self._side_list.count():
            self._side_list.setCurrentRow(0)

    def _on_side_click(self, item: QListWidgetItem):
        key = item.data(Qt.ItemDataRole.UserRole)
        # 数据链路页：次级导航项对应阶段名称，滚动到对应区域
        section_map = {
            "source": "数据源", "fetch": "数据拉取",
            "parse": "数据解析", "store": "数据存储",
        }
        section_name = section_map.get(key, "")
        tbl = getattr(self, '_link_table', None)
        rows = getattr(self, '_link_section_rows', {})
        if tbl and section_name in rows:
            tbl.scrollToItem(tbl.item(rows[section_name], 0), QTableWidget.ScrollHint.PositionAtTop)

        # 数据表页：切换子页面
        tab_map = {"tables": 0, "structure": 1, "query": 2}
        inner = getattr(self, '_table_stack', None)
        if inner and key in tab_map:
            inner.setCurrentIndex(tab_map[key])

    def _refresh(self):
        print("[DataCenter] 刷新")