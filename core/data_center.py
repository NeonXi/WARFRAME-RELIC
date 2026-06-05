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

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QStackedWidget, QFrame, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, qRgba

from core.constants import theme


# ============================================================
# 数据访问层
# ============================================================

class DataRepository:
    def __init__(self):
        self._data_dir = Path("data")
        self._relic_db_path = self._data_dir / "relics.db"
        self._items_db_path = self._data_dir / "items_i18n.db"
        self._wm_prices_db_path = self._data_dir / "wm_prices.db"
        self._game_i18n_db_path = self._data_dir / "game_i18n.db"

    @property
    def available(self) -> bool:
        return self._relic_db_path.exists()

    @property
    def items_available(self) -> bool:
        return self._items_db_path.exists()

    def all_databases(self) -> list[dict]:
        """返回所有可用数据库的元信息"""
        db_defs = [
            ("relics.db",           self._relic_db_path,        "遗物数据库 (WAL)"),
            ("items_i18n.db",       self._items_db_path,        "全物品索引 (v6)"),
            ("game_i18n.db",        self._game_i18n_db_path,    "中英对照翻译库 (WAL)"),
            ("wm_prices.db",        self._wm_prices_db_path,    "WM 价格缓存 (WAL)"),
        ]
        return [{"name": n, "path": p, "label": l} for n, p, l in db_defs if p.exists()]

    def tables(self, db_path: Path = None) -> list[str]:
        db_path = db_path or self._relic_db_path
        if not db_path.exists():
            return []
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def schema(self, table: str, db_path: Path = None) -> list[dict]:
        db_path = db_path or self._relic_db_path
        if not db_path.exists():
            return []
        try:
            with sqlite3.connect(db_path) as conn:
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return [
                {"cid": c[0], "name": c[1], "type": c[2],
                 "notnull": bool(c[3]), "default": c[4], "pk": bool(c[5])}
                for c in cols
            ]
        except Exception:
            return []

    def count(self, table: str, db_path: Path = None) -> int:
        db_path = db_path or self._relic_db_path
        if not db_path.exists():
            return 0
        try:
            with sqlite3.connect(db_path) as conn:
                return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            return 0

    def total_count(self) -> int:
        return sum(self.count(t) for t in self.tables())

    def query(self, sql: str, db_path: Path = None, params: tuple = ()) -> tuple[list[str], list[tuple]]:
        """执行 SELECT 查询，返回 (列名列表, 行数据列表)"""
        db_path = db_path or self._relic_db_path
        if not db_path.exists():
            return [], []
        try:
            with sqlite3.connect(db_path) as conn:
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
]

SIDE_NAV = {
    0: [("source", "数据源"), ("fetch", "数据拉取"), ("parse", "数据解析"), ("store", "数据存储")],
    1: [("tables", "表列表"), ("structure", "表结构"), ("query", "数据查询")],
}

SIDE_TITLES = {0: "数据链路", 1: "数据表", 2: "操作日志"}


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
        self.showMaximized()

        self._build()

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
            ("🌐", "all.json", "WFCD warframe-drop-data",
             "主数据源，包含 relics 定义、missionRewards / bountyRewards / keyRewards 掉落表",
             True),
            ("🌐", "all_items.json", "WFCD warframe-drop-data",
             "多语言翻译数据，uniqueName → zh.name / en.name 映射",
             True),
            ("🌐", "All.json", "WFCD warframe-drop-data",
             "全物品详细数据，15,729 个物品的 name / category / type / tradable / rarity / mr 等属性",
             True),
            ("🌐", "zh_en_dict.json", "AdminRoc 中英对照词典",
             "最全面的中英对照数据源，16,907 条记录，含 382 条 Blueprint 部件翻译",
             True),
            ("🌐", "dict.en.json", "calamity-inc/warframe-public-export-plus",
             "DE 官方 Public Export 英文翻译数据，a 类可靠来源",
             True),
            ("🌐", "dict.zh.json", "calamity-inc/warframe-public-export-plus",
             "DE 官方 Public Export 中文翻译数据，a 类可靠来源",
             True),
        ]),
        ("数据拉取", [
            ("⬇️", "下载 all.json", "GitHub Raw → HTTPS",
             "分块下载 (8KB/块) → 进度回调 → 超时重试(2次) → 速度统计",
             True),
            ("⬇️", "下载 all_items.json", "GitHub Raw → HTTPS",
             "多语言翻译数据下载，失败跳过不阻塞主流程",
             True),
            ("⬇️", "下载 dict.en.json", "GitHub Raw → HTTPS",
             "DE 官方英文翻译数据下载，约 1.5MB JSON",
             True),
            ("⬇️", "下载 dict.zh.json", "GitHub Raw → HTTPS",
             "DE 官方中文翻译数据下载，约 1.5MB JSON",
             True),
        ]),
        ("数据解析", [
            ("🧪", "JSON 格式验证", "json.loads",
             "验证 JSON 格式正确性 → 输出顶层字段列表 (relics, missionRewards, ...)",
             True),
            ("📁", "文件备份", "old → .bak",
             "旧文件重命名为 .bak 备份，防止数据丢失",
             True),
            ("💾", "JSON 格式化保存", "json.dump",
             "ensure_ascii=False, indent=2 → 格式化保存 all.json 到本地",
             True),
            ("✂️", "i18n 语言清洗", "lang filter",
             "遍历每个 uniqueName 的翻译字典，仅保留 zh / en 语言，移除其余语言",
             True),
            ("🗺️", "纪元映射", "TIER_MAP",
             "Lith→古纪, Meso→前纪, Neo→中纪, Axi→后纪, Requiem→安魂, Vanguard→先锋",
             True),
            ("🔍", "掉落数据扫描", "extract_dropping_relics",
             "递归遍历 missionRewards / bountyRewards / keyRewards 等所有 rewards 数组\n收集含 'Relic' 的 itemName 条目",
             True),
            ("🧹", "正则解析掉落名", "re.match",
             "r'(\\w+)\\s+(\\S+)\\s+Relic' → \"Lith C14 Relic\" → \"古纪 C14\"\n\"Lith C14 Relic (Radiant)\" → \"古纪 C14\"（自动忽略后缀）",
             True),
            ("📋", "State 去重", "(tier, relicName) dedup",
             "同遗物存在 Intact / Exceptional / Flawless / Radiant 四种 state\n按 (tier, relicName) 去重，优先保留 Intact 状态",
             True),
            ("🚦", "vaulted 状态推断", "三级优先级判定",
             "虚空商人(2) > 出库/有掉落(1) > 入库/无掉落(0)\nname in vt_set → vaulted=2\nname in dropping_set → vaulted=1\nelse → vaulted=0",
             True),
            ("🏷️", "别名生成", "generate_aliases",
             "每个遗物生成 5 个别名变体:\n\"古纪 C7\" / \"古纪C7\" / \"lith c7\" / \"lithc7\" / 原始名\n用于 OCR 模糊匹配和搜索容错",
             True),
            ("📖", "zh_en_dict 加载", "json.load",
             "主数据源加载，16,907 条中英对照，含 382 条 Blueprint 部件翻译",
             True),
            ("📖", "all_items.json 加载", "json.load",
             "辅助数据源，15,729 个物品 → 构建 en_name → (category, tradable, rarity, ...) 查找表",
             True),
            ("📖", "all_items.json 翻译补充", "json.load",
             "补充翻译源，uniqueName → zh.name，用于 zh_en_dict 未覆盖的条目",
             True),
            ("🧩", "部件名推导", "_derive_zh_from_pattern",
             "在 zh_en_dict 中查找 \"X Prime Chassis Blueprint\" → 去 Prime → 得 \"X 机体 蓝图\"\n支持 14 种部件关键词: chassis, neuroptics, systems, barrel, receiver, stock, blade, handle, link, grip, gauntlet, string, upper limb, lower limb",
             True),
            ("🏆", "Prime 推导", "模式匹配",
             "非 Prime 物品尝试从 Prime 版本推导中文名\n\"acceltra blueprint\" → try \"acceltra prime blueprint\" → \"Acceltra 蓝图\"",
             True),
            ("📐", "资源蓝图推导", "regex: x\\d+",
             "\"adramal alloy x20\" → 匹配 \"adramal alloy\" → \"阿德拉玛合金 x20 蓝图\"",
             True),
            ("�", "拼音生成", "pypinyin",
             "中文名 → 全拼 + 首字母 → \"古纪C7\" → \"gujic7 gjc7\"\n用于拼音搜索和 OCR 容错匹配",
             True),
            ("🔗", "数据关联", "uniqueName 精确匹配",
             "zh_en_dict.en_name ↔ all_items.name 以 uniqueName 为主键关联\n确保中英文对应准确无误",
             True),
            ("📊", "数据优先级", "三级合并策略",
             "zh_en_dict (16,907条) > all_items.json (15,729条) > all_items.json (补充)\n中文名: zh_en_dict > English fallback\n属性: all_items.json (category, tradable, rarity, ...)",
             True),
            ("🔗", "中英数据合并", "key 对齐",
             "dict.en + dict.zh 以 /Lotus/Language/... key 对齐合并\n统计: 中英皆有 / 仅英文 / 仅中文",
             True),
            ("✅", "双重交叉验证", "public-export-plus ↔ WFCD i18n",
             "以 dict.*.json 为主数据源，WFCD all_items.json 为补充源\n若 dict 缺失翻译 → 从 zh_en_dict 补充\n若 zh_en_dict 有独有 key → 追加到数据库",
             True),
            ("🏷️", "分类提取", "路径解析",
             "/Lotus/Language/Missions/... → Missions\n/Lotus/Language/Items/... → Items\n/Lotus/Language/Relics/... → Relics\n共 30+ 分类",
             True),
        ]),
        ("数据存储", [
            ("🏗️", "relics.db 建表", "SCHEMA_SQL",
             "relics 表 (id, name, era, code, vaulted)\nrelic_parts 表 (relic_id, part_name, rarity, chance)\nrelic_aliases 表 (relic_id, alias)\nPRAGMA journal_mode=WAL · PRAGMA foreign_keys=ON",
             True),
            ("🏗️", "items_i18n.db 建表", "SCHEMA",
             "items 表 (unique_name, zh_name, en_name, category, item_type, tradable, is_prime, rarity, mr, zh_pinyin, description)\nitems_meta 表 (key, value)\nitems_i18n 表 (多语言翻译)",
             True),
            ("📊", "relics 索引", "CREATE INDEX",
             "idx_relic_parts_relic_id — 部件→遗物关联\nidx_aliases_alias — OCR 别名匹配\nidx_aliases_relic_id — 别名→遗物反向\nidx_relics_era — 纪元筛选\nidx_relics_vaulted — 出入库过滤",
             True),
            ("📊", "items 索引", "CREATE INDEX",
             "idx_items_zh — 中文名搜索\nidx_items_en — 英文名搜索\nidx_items_pinyin — 拼音搜索\nidx_items_category — 分类筛选\nidx_items_type — 子类型筛选\nidx_items_prime — Prime 过滤\nidx_items_tradable — 可交易过滤",
             True),
            ("✅", "事务提交", "conn.commit()",
             "批量 INSERT 后统一提交事务\nrelics 表: ~300 条遗物 + ~1,200 个部件 + ~1,500 个别名\nitems 表: ~16,000 条物品",
             True),
            ("🔄", "DB 文件替换", "finalize_db",
             "若原 DB 被占用 → 写入 .new 临时文件 → shutil.move 替换\n否则直接覆盖写入原文件",
             True),
            ("🏗️", "game_i18n.db 建表", "CREATE TABLE",
             "translations 表 (key PRIMARY KEY, en, zh, category, source, verified)\nidx_category — 分类索引\nidx_source — 来源索引\nPRAGMA journal_mode=WAL",
             True),
            ("📊", "game_i18n 批量写入", "executemany",
             "5,000 条/批次批量 INSERT → 统一事务提交\n总计约 30,000+ 条中英对照记录",
             True),
            ("📊", "game_i18n 分类统计", "GROUP BY category",
             "Missions / Items / Relics / Menu / 1999 / ... 等 30+ 分类\n每个分类标注记录数和来源",
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
            QHeaderView::section {{
                background: rgba(0,0,0,0.40);
                color: rgba(255,255,255,0.20);
                font-size: 12px;
                font-weight: 600;
                padding: 10px 14px;
                border: none;
                border-bottom: 1px solid rgba(255,255,255,0.03);
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

    def _table_list_page(self) -> QWidget:
        """列出所有数据库及其表"""
        pg = QWidget()
        layout = QVBoxLayout(pg)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        title = QLabel("🗄️  数据表列表")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {theme.cyber_cyan};")
        layout.addWidget(title)

        desc = QLabel("所有已注册数据库的表及其属性概览")
        desc.setStyleSheet(f"font-size: 13px; color: {theme.text_dim};")
        layout.addWidget(desc)

        # 构建数据
        headers = ["数据库", "表名", "行数", "列数"]
        rows_data = []
        self._table_row_db: list[tuple] = []  # (db_path, table_name) 供选中查询
        for db in self._repo.all_databases():
            db_path = db["path"]
            for table in self._repo.tables(db_path):
                cnt = self._repo.count(table, db_path)
                cols = len(self._repo.schema(table, db_path))
                rows_data.append([db["label"], table, f"{cnt:,}", str(cols)])
                self._table_row_db.append((db_path, table))

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
        table.setColumnWidth(0, 130)
        table.setColumnWidth(1, 150)
        table.setColumnWidth(2, 80)
        table.setColumnWidth(3, 60)

        table.verticalHeader().setDefaultSectionSize(42)
        table.verticalHeader().setVisible(False)

        for ri, row in enumerate(rows_data):
            for ci, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
        sel_label = QLabel("选择表:")
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

        refresh_btn = QPushButton("刷新")
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
                label = f"{db['label']}  ›  {table}"
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
        ql = QLabel("选择表:")
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
                label = f"{db['label']}  ›  {table}"
                self._query_combo.addItem(label)
                self._query_refs.append((db["path"], table))
        self._query_combo.currentIndexChanged.connect(self._on_query_combo_changed)

        # 筛选条件区域
        filter_label = QLabel("筛选条件")
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

        qbtn = QPushButton("执行查询")
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
        self._query_status = QLabel("就绪 — 选择表后添加筛选条件，或直接点击「执行查询」查看全部数据")
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
        value_edit.setPlaceholderText("值")
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
            self._query_status.setText("请先选择数据库表")
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

        tables = len(self._repo.tables())
        records = self._repo.total_count()
        items_tables = len(self._repo.tables(self._repo._items_db_path)) if self._repo.items_available else 0
        items_records = sum(self._repo.count(t, self._repo._items_db_path) for t in self._repo.tables(self._repo._items_db_path)) if self._repo.items_available else 0
        info = QLabel(
            f"遗物库: {tables} 表, {records:,} 条  |  "
            f"物品库: {items_tables} 表, {items_records:,} 条"
        )
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
        self._side_list.clear()
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