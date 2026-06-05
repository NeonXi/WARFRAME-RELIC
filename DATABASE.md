# WARFRAME-RELIC 数据库架构完整文档

## 1. 数据架构总览

本项目使用多个 SQLite 数据库和 JSON 数据文件构成完整的数据体系。

### 1.1 架构图

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                               外部数据源                                       │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────┐  ┌─────────────────────────┐                      │
│  │ WFCD/warframe-drop-data │  │ calamity-inc/warframe   │                      │
│  │    - all.json           │  │ -public-export-plus     │                      │
│  │  (遗物+掉落源)          │  │    - dict.en.json       │                      │
│  └─────────────────────────┘  │    - dict.zh.json       │                      │
│                                └─────────────────────────┘                      │
│                                                                               │
│  ┌─────────────────────────┐  ┌─────────────────────────┐                      │
│  │ WFCD/warframe-items     │  │  warframe.market API   │                      │
│  │    - All.json           │  │    - /v2/items         │                      │
│  │    - i18n.json          │  │    - /v2/orders        │                      │
│  └─────────────────────────┘  └─────────────────────────┘                      │
└─────────────────────────────┬─────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         本地数据转换与构建层 (data/)                          │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  数据源文件 (JSON)                                                      │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ • all.json          → WFCD 全量数据 (遗物+掉落源)                        │  │
│  │ • dict.en.json      → public-export-plus 英文翻译 (本地/在线)            │  │
│  │ • dict.zh.json      → public-export-plus 中文翻译 (本地/在线)            │  │
│  │ • i18n.json         → WFCD 补充翻译 (本地)                              │  │
│  │ • zh_en_dict.json   → 自定义中英对照 (本地, ~17,000条)                  │  │
│  │ • all_items.json    → WFCD 物品信息 (本地)                              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  数据构建模块                                                           │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ • update_db.py       → all.json → relics.db                            │  │
│  │ • items_i18n.py     → 构建 items_i18n.db (全物品索引)                  │  │
│  │ • game_i18n.py      → 构建 game_i18n.db (翻译库)                       │  │
│  │ • wm_prices.py      → 拉取并构建 wm_prices.db                          │  │
│  │ • data_pipeline.py  → 统一数据更新流水线编排                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└───────────────────────────────────────┬───────────────────────────────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                            SQLite 数据库层                                     │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────┐  ┌───────────────────────────────────────┐          │
│  │  relics.db          │  │      items_i18n.db                  │          │
│  │  - relics           │  │      - items                       │          │
│  │  - relic_parts      │  │      - items_meta                  │          │
│  │  - relic_aliases    │  │      - drop_sources (保留)         │          │
│  └─────────────────────┘  └───────────────────────────────────────┘          │
│                                                                               │
│  ┌─────────────────────┐  ┌───────────────────────────────────────┐          │
│  │  game_i18n.db       │  │      wm_prices.db                  │          │
│  │  - translations     │  │      - item_prices                 │          │
│  └─────────────────────┘  │      - price_meta                  │          │
│                           └───────────────────────────────────────┘          │
│  ┌─────────────────────┐                                                           │
│  │  wm_items.db       │ (搜索和slug映射专用)                                   │
│  │  - items          │                                                           │
│  └─────────────────────┘                                                           │
└───────────────────────────────────────┬───────────────────────────────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                            应用与服务层                                         │
├───────────────────────────────────────────────────────────────────────────────┤
│ • wfinfo_relics.py    → RelicDB (遗物查询)                                   │
│ • drop_tooltip.py     → 掉落来源查询                                         │
│ • price_service.py    → 价格查询（内存缓存 → DB → API）                     │
│ • market_query/*.py  → 物品搜索和市场查询（使用 wm_items.db 和 wm_prices.db） │
│ • recognizer/*.py     → OCR 识别使用翻译                                     │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据库详细说明

### 2.1 relics.db —— 遗物掉落数据库

**文件位置**: `data/relics.db`

**构建脚本**: `update_db.py` (从 `data/all.json` 迁移)

**表结构**:
```sql
CREATE TABLE IF NOT EXISTS relics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,  -- 遗物标准名，如 "古纪 C7"
    era         TEXT NOT NULL,         -- 纪元（中文）: 古纪/前纪/中纪/后纪/安魂/先锋
    code        TEXT NOT NULL,         -- 遗物代码: "C7"
    vaulted     INTEGER NOT NULL DEFAULT 0  -- 出入库状态
);

CREATE TABLE IF NOT EXISTS relic_parts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id    INTEGER NOT NULL,         -- 外键 -> relics.id
    part_name   TEXT NOT NULL,            -- Prime 部件英文名
    rarity      TEXT NOT NULL,            -- 稀有度: Common/Uncommon/Rare
    chance      REAL NOT NULL DEFAULT 0,  -- 掉落概率
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relic_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id    INTEGER NOT NULL,         -- 外键 -> relics.id
    alias       TEXT NOT NULL UNIQUE,     -- 别名变体（用于OCR模糊匹配）
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_relic_parts_relic_id ON relic_parts(relic_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON relic_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_aliases_relic_id ON relic_aliases(relic_id);
CREATE INDEX IF NOT EXISTS idx_relics_era ON relics(era);
CREATE INDEX IF NOT EXISTS idx_relics_vaulted ON relics(vaulted);
```

**出入库状态码 (vaulted)**:
- `0` = 入库（不可获取）
- `1` = 出库（可获取，有掉落途径）
- `2` = 虚空商人（暂未实现）

**查询接口**: `data.wfinfo_relics.RelicDB`
- `find(name)` → 四级降级匹配查询（最快路径为别名精确匹配）
  1. 精确匹配别名表
  2. 精确匹配主表 name 字段
  3. 模糊匹配：忽略空格、大小写
  4. 正则模糊匹配：OCR 可能混淆的字符 (O↔0, I↔1, L↔1, S↔5, B↔8 等)
- `get_parts(name)` → 获取遗物部件列表（已翻译为中文）
- `is_vaulted(name)` → 检查是否已出库
- `stats()` → 返回数据库统计（遗物总数、出库数量、别名数等）

---

### 2.2 items_i18n.db —— 全物品中英对照索引数据库

**文件位置**: `data/items_i18n.db`

**构建脚本**: `data/items_i18n.py`

**数据源优先级**:
1. `data/zh_en_dict.json` —— 主数据源（~17,000条，含Blueprint部件）
2. `data/all_items.json` —— WFCD All.json（补充属性：category/tradable/rarity等）
3. `data/i18n.json` —— WFCD i18n.json（补充未覆盖物品翻译）
4. `data/all.json` —— 补充掉落物品（非Prime战甲部件蓝图等）

**表结构 (v6 schema)**:
```sql
-- 全物品中英对照主表
CREATE TABLE IF NOT EXISTS items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name         TEXT NOT NULL UNIQUE,   -- 游戏内部唯一标识
    zh_name             TEXT NOT NULL,          -- 中文名
    en_name             TEXT NOT NULL,          -- 英文名
    category            TEXT,                   -- 物品大类
    item_type           TEXT,                   -- 物品子类型
    is_tradable         INTEGER DEFAULT 0,      -- 是否可交易
    is_prime            INTEGER DEFAULT 0,      -- 是否 Prime
    rarity              TEXT,                   -- 稀有度
    mr_requirement      INTEGER DEFAULT 0,      -- 段位要求
    image_name          TEXT,                   -- 图片文件名
    description_zh      TEXT,                   -- 中文描述
    description_en      TEXT,                   -- 英文描述
    zh_pinyin           TEXT DEFAULT '',        -- 中文拼音（用于拼音搜索）
    UNIQUE(zh_name, en_name)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_items_zh ON items(zh_name);
CREATE INDEX IF NOT EXISTS idx_items_en ON items(en_name);
CREATE INDEX IF NOT EXISTS idx_items_pinyin ON items(zh_pinyin);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
CREATE INDEX IF NOT EXISTS idx_items_prime ON items(is_prime);
CREATE INDEX IF NOT EXISTS idx_items_tradable ON items(is_tradable);

-- 元信息表
CREATE TABLE IF NOT EXISTS items_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 掉落来源子表（保留，但不再在items表中存储drop_source_zh/en字段）
CREATE TABLE IF NOT EXISTS drop_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL,
    source_en   TEXT NOT NULL,
    source_zh   TEXT NOT NULL,
    rarity      TEXT DEFAULT '',
    chance      REAL DEFAULT 0,
    rotation    TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_drop_sources_item ON drop_sources(item_id);
CREATE INDEX IF NOT EXISTS idx_drop_sources_source ON drop_sources(source_en);
CREATE INDEX IF NOT EXISTS idx_drop_sources_type ON drop_sources(source_type);
```

**常见 category 值**:
- Warframes, Warframe Parts
- Primary, Secondary, Melee, Arch-Gun, Arch-Melee
- Relics, Mods, Arcanes, Sentinels, Pets
- Resources, Sigils, Keys, Gear, Misc, ...

**拼音索引格式**: `items.zh_pinyin` 字段存储格式为 `"全拼1 全拼2 ... 首字母1首字母2..."`

**非Prime翻译推导策略**: 对于如 `"Ash Chassis Blueprint"` 这样的非Prime名称，
尝试从 Prime 版本对应条目中去除 `"Prime"` 来推导中文翻译。

**查询接口**:
- `build_all_items_db()` → 重建完整数据库
- `search_items(query, search_field, category, is_prime, is_tradable, limit)`
- `translate_item(name, direction)`
- `get_db_stats()`
- `check_pinyin_integrity()` / `repair_pinyin_integrity()`

---

### 2.3 game_i18n.db —— 游戏术语中英对照翻译库

**文件位置**: `data/game_i18n.db`

**构建脚本**: `data/game_i18n.py`

**数据源三重交叉验证**:
1. `dict.en.json` + `dict.zh.json` (calamity-inc/warframe-public-export-plus)
   - 支持从 GitHub 在线下载或使用本地文件
2. `i18n.json` (WFCD/warframe-drop-data, 本地)
3. (可选) WFCD/warframe-items i18n.json (仅在线模式)

**构建流程**:
```
[1/6] 获取 dict.en.json (下载或本地)
[2/6] 获取 dict.zh.json (下载或本地)
[3/6] 合并英文/中文翻译数据
[4/6] 交叉验证 WFCD i18n.json
[5/6] 交叉验证 WFCD items i18n.json (仅在线模式, 本地模式跳过)
[6/6] 写入数据库
```

**表结构**:
```sql
CREATE TABLE IF NOT EXISTS translations (
    key         TEXT PRIMARY KEY,        -- 唯一键（如 /Lotus/Language/...）
    en          TEXT NOT NULL,           -- 英文翻译
    zh          TEXT NOT NULL,           -- 中文翻译
    category    TEXT DEFAULT '',         -- 分类（从key路径推断）
    source      TEXT DEFAULT 'public-export-plus',  -- 数据来源
    verified    INTEGER DEFAULT 0        -- 验证状态
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_category ON translations(category);
CREATE INDEX IF NOT EXISTS idx_source ON translations(source);
```

**数据来源标记 (source)**:
- `public-export-plus` —— 来自 calamity-inc 数据源
- `public-export-plus,wfcd-i18n` —— 主数据源 + WFCD补充
- `wfcd-i18n` —— 仅来自WFCD drop-data
- `wfcd-items` —— 仅来自WFCD items（仅在线模式）

**WFCD items i18n特殊处理**: 该数据源不包含英文字段，英文从key路径推断

**查询接口**:
- `translate(key, lang)` → 按键查翻译
- `translate_by_en(en_text)` → 按英文查中文（反向查找）
- `search_zh(keyword, limit)` → 全文搜索中文翻译
- `get_categories()` → 获取所有分类名
- `get_stats()` → 获取数据库统计
- `translate_term(en_text, term_type)` → 通用术语翻译（DB优先，回退game_terms.py硬编码）

---

### 2.4 wm_prices.db —— warframe.market 价格缓存数据库

**文件位置**: `data/wm_prices.db`

**构建脚本**: `data/wm_prices.py`

**数据源**:
- `https://api.warframe.market/v2/items` → 物品列表与slug映射
- `https://api.warframe.market/v2/orders/item/{slug}` → 卖单数据
- `https://api.warframe.market/v1/items/{slug}/statistics` → 历史统计
- `wm_items.db` (已合并) → en_name 和 slug 映射数据

**表结构**:
```sql
CREATE TABLE IF NOT EXISTS item_prices (
    item_id          INTEGER NOT NULL,        -- 关联 items_i18n.db items.id (冗余)
    en_name          TEXT NOT NULL DEFAULT '', -- 物品英文名（直接查询用）
    slug             TEXT NOT NULL,            -- WM URL slug
    sell_min         INTEGER,                  -- 最低卖价（白金）
    sell_median      REAL,                     -- 中位数价格
    sell_weighted    REAL,                     -- ★ 反压价加权参考价（推荐）
    sell_volume      INTEGER,                  -- 参与计算的卖单数（≤20）
    sell_top3        TEXT,                     -- JSON数组：前三最低价 [p1,p2,p3]
    sell_volume_full INTEGER,                  -- 全量卖单数
    volume_48h       INTEGER,                  -- 48小时成交量
    avg_price_90d    REAL,                     -- 90天加权均价
    updated_at       TEXT NOT NULL,            -- 更新时间（YYYY-MM-DD HH:MM:SS）
    PRIMARY KEY (item_id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_prices_en_name ON item_prices(en_name);
CREATE INDEX IF NOT EXISTS idx_prices_slug ON item_prices(slug);
CREATE INDEX IF NOT EXISTS idx_prices_weighted ON item_prices(sell_weighted);
CREATE INDEX IF NOT EXISTS idx_prices_updated ON item_prices(updated_at);

CREATE TABLE IF NOT EXISTS price_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

**反压价权重算法**:
- 取前20个最低卖单
- 计算中位数
- 价格 < 中位数 × 0.7 → 判定为异常压价，权重降为 0.1
- 正常价格权重为 1.0
- `sell_weighted = Σ(price × weight) / Σ(weight)`

**并发与限速**:
- 最大并发线程数: 8
- 全局限速: 3 请求/秒（令牌桶限速器）
- 单次请求超时: 30 秒
- 每批写入: 200 个物品
- 历史统计仅每50个物品拉取一次

**物品匹配策略**:
1. 精确匹配 (en_name)
2. 模糊匹配 (Prime Set ↔ Set 变体)
3. 无Set后缀匹配

**查询接口**:
- `get_price(en_name)` → 查询单个物品价格
- `fetch_price_realtime(en_name, timeout)` → 实时API优先查询，超时回退本地DB
- `get_prices_batch(en_names)` → 批量查询
- `get_price_stats()` → 获取数据库统计
- `fetch_all_prices(log_cb, progress_cb)` → 完整拉取流程

---

### 2.5 wm_items.db —— 物品搜索和 Slug 映射数据库

**文件位置**: `data/wm_items.db`

**构建脚本**: `market_query/db_updater.py`

**用途**:
- 物品搜索（支持中文/英文/拼音搜索）
- 英文名到 warframe.market slug 的映射
- 可交易状态筛选

**表结构**:
```sql
CREATE TABLE IF NOT EXISTS items (
    id                  INTEGER PRIMARY KEY,
    slug                TEXT NOT NULL,
    en_name             TEXT NOT NULL,
    zh_name             TEXT NOT NULL,
    game_ref            TEXT,
    item_type           TEXT,
    is_tradable         INTEGER DEFAULT 0,
    is_prime            INTEGER DEFAULT 0,
    zh_pinyin           TEXT,
    original_is_tradable INTEGER
);
```

**使用场景**:
- `market_query/search_widget.py` 使用此数据库进行物品搜索
- `market_query/utils.py` 使用此数据库查询 slug
- `market_query/db_updater.py` 用于更新此数据库

---

## 3. 数据更新流水线

### 3.1 统一更新入口

**模块**: `data.data_pipeline.py`

**流程编排 (按依赖顺序)**:

```
[1] 下载 all.json (WFCD/warframe-drop-data)
        ↓
[2] 更新 relics.db
        ↓
[3] 重建 items_i18n.db
        ↓
[4] (可选) 拉取 WM 价格 (wm_prices.db)
        ↓
[5] 构建 game_i18n.db
```

**使用方法**:
```python
from data.data_pipeline import DataPipelineWorker

worker = DataPipelineWorker(
    skip_download=False,   # 跳过 all.json 下载（如果已有）
    skip_prices=False,     # 跳过价格拉取
    prices_only=False,     # 仅拉取价格（不更新其他数据）
)

# 连接信号
worker.step_changed.connect(...)
worker.log.connect(...)
worker.progress_pct.connect(...)
worker.finished.connect(...)

# 后台运行
threading.Thread(target=worker.run, daemon=True).start()
```

**状态查询**: `get_pipeline_summary()` → 获取所有数据库存在状态和文件大小

---

## 4. 镜像与网络优化

### 4.1 GitHub 镜像配置

**配置位置**: `core/hotkey_config.py`

**支持的镜像模式**:
1. **域名替换模式** (如 `raw.githubusercontent.com` → `raw.staticdn.net`)
2. **前缀代理模式** (如 `https://ghproxy.com/` + 原始URL)

**镜像URL查询** (由 `data.game_i18n.py` 和 `core.fetch_worker.py` 使用):
```python
from core.hotkey_config import resolve_github_url

url = resolve_github_url(original_url, mirror_config)
```

**网络测速**:
- Ping 延迟测试 (HEAD 请求)
- 下载速度测试 (128KB 采样)
- 超时倒计时显示

---

## 5. 数据库迁移历史

### 5.1 Schema 版本号说明

各数据库都有其独立的 schema 版本管理：

| 数据库 | 版本 | 说明 |
|--------|------|------|
| items_i18n.db | 6 | 移除 items 表中的 drop_source_zh 和 drop_source_en 字段（保留 drop_sources 子表） |
| items_i18n.db | 5 | 完善 drop_sources 富数据（rarity, chance, rotation, source_type） |
| items_i18n.db | 4 | 新增 drop_sources 子表 |
| items_i18n.db | 3 | 新增 items 表中的 drop_source_zh 和 drop_source_en 字段 |
| items_i18n.db | 2 | 新增 zh_pinyin 字段和拼音完整性检查 |
| items_i18n.db | 1 | 初始版本 |

**game_i18n.db** 暂未使用版本号系统。
**relics.db** 和 **wm_prices.db** 也无版本号系统，重建即更新。
**wm_items.db** 无版本号系统。

---

## 6. 数据库优化与维护

### 6.1 优化历史

**2026-06-05 数据库优化**:
1. **items_i18n.db Schema 升级 v5 → v6**
   - 移除了 `items` 表中的 `drop_source_zh` 和 `drop_source_en` 字段
   - 数据完整迁移至 `drop_sources` 子表
   - 保留 `drop_sources` 子表功能完整

2. **统一 WAL 模式**
   - 所有数据库（relics.db、items_i18n.db、game_i18n.db、wm_prices.db、wm_items.db）都已切换到 WAL (Write-Ahead Logging) 模式
   - 提升并发读写性能
   - 减少数据库锁竞争

3. **数据库碎片清理**
   - 对所有数据库执行 VACUUM
   - 释放了约 **3.38MB** 的空间
   - 优化了查询性能

4. **wm_prices.db 数据合并**
   - 从 wm_items.db 合并了完整的 `en_name` 和 `slug` 数据
   - 更新了 2183 条记录的 `en_name` 字段
   - 新增了 1611 条记录
   - wm_prices.db 现在拥有 3794 条完整记录

### 6.2 维护命令

```bash
# 检查数据库大小和统计
python analyze_database.py

# 检查 items_i18n.db 结构
python check_schema_version.py

# 检查 wm_items.db 结构
python check_wm_items.py

# 数据覆盖检查
python check_data_simple.py
```

---

## 7. 数据文件快速参考

### 7.1 本地数据源文件

| 文件名 | 说明 | 是否必须 |
|--------|------|---------|
| `data/all.json` | WFCD 全量掉落数据 | 是（用于遗物数据） |
| `data/dict.en.json` | 英文翻译库（public-export-plus） | 是（本地模式）/ 在线下载（默认） |
| `data/dict.zh.json` | 中文翻译库（public-export-plus） | 是（本地模式）/ 在线下载（默认） |
| `data/i18n.json` | WFCD 补充翻译 | 否（仅用于交叉验证） |
| `data/zh_en_dict.json` | 自定义中英对照（~17,000条） | 是（items_i18n主数据源） |
| `data/all_items.json` | WFCD 物品信息 | 否（items_i18n辅助） |

### 7.2 数据库文件

| 文件名 | 说明 |
|--------|------|
| `data/relics.db` | 遗物掉落数据库 |
| `data/items_i18n.db` | 全物品中英对照索引 |
| `data/game_i18n.db` | 翻译库 |
| `data/wm_prices.db` | 市场价格缓存（已包含完整的 en_name 和 slug 映射） |
| `data/wm_items.db` | 物品搜索和slug映射专用库（被 search_widget.py 和 db_updater.py 使用） |

---

## 8. 开发工具与命令行

### 8.1 常用命令

```bash
# 从本地 dict.en/zh.json 构建翻译库（最快）
python data/game_i18n.py --local

# 在线下载新的翻译源并构建
python data/game_i18n.py

# 重建全物品索引数据库
python -m data.items_i18n --rebuild

# 检查拼音完整性并修复
python -m data.items_i18n --check-pinyin
python -m data.items_i18n --repair-pinyin

# 更新遗物数据库（需要 all.json）
python update_db.py

# 拉取市场价格数据
python -m data.wm_prices --fetch

# 查看价格数据库统计
python -m data.wm_prices --stats

# 查询单个物品价格
python -m data.wm_prices --search "Braton Prime"

# 批量查询价格
python -m data.wm_prices --search-batch "Braton Prime,Latron Prime"
```

---

## 9. 依赖关系图

```
items_i18n.db → (翻译部件) → wfinfo_relics.py → RelicDB
game_i18n.db → (翻译OCR识别内容) → 多种识别器
items_i18n.db → (匹配物品名) → price_service.py → wm_prices.db
wm_items.db → (搜索功能) → market_query/search_widget.py
wm_items.db → (slug查询) → market_query/utils.py
all.json → (掉落源) → items_i18n.py → drop_sources 表
```

**数据流向**:
- 外部数据源 → 本地JSON文件 → SQLite数据库 → 应用查询
- 价格查询: 内存缓存 → wm_prices.db → 实时API (可选)
- 搜索功能: wm_items.db (用于快速搜索) + wm_prices.db (用于价格查询)

---

## 10. 附录

### 10.1 拼音索引格式

`items.zh_pinyin` 字段存储格式：`"全拼1 全拼2 ... 首字母1首字母2..."`

### 10.2 遗物别名变体

每个遗物生成多个别名变体用于OCR容错：
1. 原始名
2. 标准名
3. 无空格
4. 小写带空格
5. 小写无空格

### 10.3 掉落来源类型

`drop_sources.source_type` 可能的值:
- `relic` —— 遗物掉落
- `missionRewards` —— 任务奖励
- `cetusBountyRewards` / `solarisBountyRewards` / `deimosRewards` / `zarimanRewards` —— 赏金奖励
- `sortieRewards` —— 突击奖励
- `keyRewards` —— 钥匙奖励
- `transientRewards` —— 临时奖励
- `blueprintLocations` —— 蓝图位置
- `enemyModTables` / `enemyBlueprintTables` —— 敌人掉落
- `modLocations` —— MOD位置
- `syndicates` —— 集团奖励

---

## 11. 注意事项

### 11.1 drop_source_zh/en 字段已移除

从 v6 schema 开始，`items_i18n.db.items` 表中的 `drop_source_zh` 和 `drop_source_en` 字段已被移除。

完整的掉落来源信息仍保留在独立的 `drop_sources` 子表中，可通过 JOIN 查询获取。

### 11.2 GitHub 网络优化

- 推荐使用镜像配置以加速国内访问
- 支持多种镜像模式（域名替换和前缀代理）
- 可在数据库管理中心界面配置镜像
- 测速功能提供延迟和下载速度反馈

### 11.3 game_i18n.db 英文缺失问题

- WFCD/warframe-items i18n.json 数据源不包含英文字段
- 英文从 key 路径自动推断（驼峰转空格、去除后缀如Key/Blueprint等）
- public-export-plus 数据源是翻译质量最高的主数据源

### 11.4 wm_prices.db 实时查询

- `fetch_price_realtime()` 先查本地DB获取slug
- 然后调用API获取实时卖单并重新计算反压价权重
- 超时或失败自动回退到本地缓存
- 超时可配置（默认2秒）

### 11.5 wm_items.db 和 wm_prices.db 的分工

- **wm_items.db**: 专注于物品搜索和slug映射，数据更完整，包含中文、拼音、可交易状态等
- **wm_prices.db**: 专注于价格缓存，但已合并完整的 en_name 和 slug 数据，可用于价格查询和 slug 查找
- **重叠部分**: 两个数据库都有 en_name 和 slug 映射
- **当前架构**: wm_items.db 仍由 search_widget.py 和 db_updater.py 使用，保持现状为最佳实践
