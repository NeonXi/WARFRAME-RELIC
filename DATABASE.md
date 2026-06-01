# WARFRAME-RELIC 数据库结构文档

## 一、数据库结构全景

本项目使用 **4 个 SQLite 数据库** + **2 个 JSON 配置文件** 作为数据存储层：

| 数据库 / 配置文件 | 路径 | 用途 | 核心表 |
|---|---|---|---|
| **items_i18n.db** | `data/items_i18n.db` | 全物品中英对照（主数据） | `items`, `items_meta` |
| **relics.db** | `data/relics.db` | 遗物掉落表 | `relics`, `relic_parts`, `relic_aliases` |
| **wm_prices.db** | `data/wm_prices.db` | warframe.market 价格缓存 | `item_prices`, `price_meta` |
| **translation.db** | `data/translation.db` | 中英翻译缓存（旧版） | `translations`, `translation_meta` |
| **config.json** | `%APPDATA%/WARFRAME-RELIC/config.json` | 框选区域持久化 | — |
| **hotkeys.json** | `data/hotkeys.json` | 热键自定义配置 | — |

> 注：`%APPDATA%` 通常为 `C:\Users\<用户名>\AppData\Roaming`。

---

## 二、items_i18n.db — 全物品中英对照数据库

### 2.1 文件位置

```
data/items_i18n.db
```

定义于 `data/items_i18n.py` 第 47 行：
```python
DB_PATH = os.path.join(BASE_DIR, 'items_i18n.db')
```

### 2.2 完整 DDL

```sql
-- ============================================================
-- 表：items — 全物品中英对照主表
-- ============================================================
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name     TEXT NOT NULL UNIQUE,      -- 游戏内部唯一标识（如 /Lotus/Weapons/Grineer/...）
    zh_name         TEXT NOT NULL,             -- 中文名
    en_name         TEXT NOT NULL,             -- 英文名
    category        TEXT,                      -- 物品大类：Warframes / Primary / Secondary / Melee / Relics / Mods / ...
    item_type       TEXT,                      -- 物品子类型
    is_tradable     INTEGER DEFAULT 0,         -- 是否可交易：0=否, 1=是
    is_prime        INTEGER DEFAULT 0,         -- 是否 Prime：0=否, 1=是
    rarity          TEXT,                      -- 稀有度：Common / Uncommon / Rare / Prime / Legendary
    mr_requirement  INTEGER DEFAULT 0,         -- 段位要求（Mastery Rank）
    image_name      TEXT,                      -- 图片文件名
    description_zh  TEXT,                      -- 中文描述
    description_en  TEXT,                      -- 英文描述
    zh_pinyin       TEXT DEFAULT '',           -- 中文拼音（全拼 + 首字母，空格分隔，用于拼音搜索）
    UNIQUE(zh_name, en_name)
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_items_zh       ON items(zh_name);
CREATE INDEX IF NOT EXISTS idx_items_en       ON items(en_name);
CREATE INDEX IF NOT EXISTS idx_items_pinyin   ON items(zh_pinyin);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_type     ON items(item_type);
CREATE INDEX IF NOT EXISTS idx_items_prime    ON items(is_prime);
CREATE INDEX IF NOT EXISTS idx_items_tradable ON items(is_tradable);

-- ============================================================
-- 表：items_meta — 元信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS items_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### 2.3 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK, AUTO | 自增主键 |
| `unique_name` | TEXT | NOT NULL, UNIQUE | 游戏内部唯一标识符，如 `/Lotus/Weapons/Tenno/LotusAssaultRifle` |
| `zh_name` | TEXT | NOT NULL | 中文名称，如 "布莱顿 Prime" |
| `en_name` | TEXT | NOT NULL | 英文名称，如 "Braton Prime" |
| `category` | TEXT | — | 物品大类枚举值 |
| `item_type` | TEXT | — | 物品子类型 |
| `is_tradable` | INTEGER | DEFAULT 0 | 0=不可交易, 1=可交易 |
| `is_prime` | INTEGER | DEFAULT 0 | 0=普通, 1=Prime/圣装 |
| `rarity` | TEXT | — | 稀有度标识 |
| `mr_requirement` | INTEGER | DEFAULT 0 | 段位需求 |
| `image_name` | TEXT | — | 关联图片文件名 |
| `description_zh` | TEXT | — | 物品中文描述 |
| `description_en` | TEXT | — | 物品英文描述 |
| `zh_pinyin` | TEXT | DEFAULT '' | 中文拼音，用于拼音搜索，如 "bù lái dùn bld" |

### 2.4 category 字段枚举值

`category` 字段包含以下大类：

| 值 | 含义 |
|---|---|
| `Warframes` | 战甲 |
| `Primary` | 主武器 |
| `Secondary` | 副武器 |
| `Melee` | 近战武器 |
| `Relics` | 遗物/核桃 |
| `Mods` | MOD 卡片 |
| `Arcanes` | 赋能 |
| `Sentinels` | 守护 |
| `Archwing` | 反重力曲翼 |
| `Skins` | 外观 |
| `Pets` | 同伴 |
| `Gear` | 装备/道具 |
| `Keys` | 钥匙 |
| `Resources` | 资源 |
| `Sigils` | 纹章 |
| `Node` | 星球节点 |
| `Relic` | 遗物（旧分类） |
| `Misc` | 杂项 |

### 2.5 数据来源

数据构建采用 **三层数据融合**，优先级从高到低：

```
第一层：zh_en_dict.json       ← 主数据源（~17,000 条，含 382 条 Blueprint 部件）
第二层：all_items.json         ← WFCD All.json（~15,729 条，含 category / tradable / rarity 等属性）
第三层：i18n.json              ← WFCD i18n.json（uniqueName → 中文翻译，补充未覆盖条目）
```

**关联方式**：通过 `uniqueName` 精确关联。

**数据源 URL**：
```
https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json
https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json
```

### 2.6 构建/重建流程

`build_all_items_db()` 函数（`data/items_i18n.py`）：

```
1. Schema 版本管理：检查当前数据库版本，自动升级到最新版本（v2）
   - v1 → v2: 添加 zh_pinyin 字段并回填拼音数据
2. 加载 zh_en_dict.json → 作为主数据源，构建 en_name → zh_name 映射
3. 加载 all_items.json  → 构建 en_name → item_info（category / tradable / rarity 等）映射
4. 加载 i18n.json       → 作为翻译补充
5. 构建 item_map        → 以 zh_en_dict 为主，用 all_items 补充属性，生成 uniqueName → item_info
6. 补充未覆盖物品       → all_items 中有但 zh_en_dict 中没有的条目
7. 写入数据库（批量插入优化）：
   - DELETE FROM items（清空）
   - 批量 INSERT INTO items（每500条提交一次，使用 executemany()）
   - 写入 items_meta 元信息（包含 schema_version）
```

**关键 INSERT 语句**：
```sql
INSERT OR IGNORE INTO items
    (unique_name, zh_name, en_name, category, item_type,
     is_tradable, is_prime, rarity, mr_requirement, image_name,
     description_zh, description_en, zh_pinyin)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

**性能优化（v3.4）**：
- **批量插入**：使用 `executemany()` 替代逐条INSERT，每500条提交一次
- **SQL调用次数**：从17564次降至约36次（提升约500倍）
- **实际耗时**：从30-60秒降至5-10秒（提升5-10倍，含拼音生成时间）

**Schema版本管理（v3.4）**：
```python
# items_meta 表新增字段
INSERT OR REPLACE INTO items_meta (key, value) VALUES ('schema_version', '2')
```

### 2.6a 拼音完整性检查与修复（v3.4新增）

**检查函数**：`check_pinyin_integrity()`
```python
# 返回字典
{
    'total': 17564,              # 总记录数
    'has_pinyin': 17564,         # 有拼音的记录数
    'missing_pinyin': 0,         # 缺失拼音的记录数
    'integrity_rate': 1.0,       # 完整率（0-1）
    'needs_repair': False        # 是否需要修复
}
```

**修复函数**：`repair_pinyin_data(batch_size=500)`
```python
# 批量修复缺失的拼音数据
# 1. 查询所有 zh_pinyin 为空的记录
# 2. 调用 _make_pinyin() 生成拼音
# 3. 批量 UPDATE（每500条提交一次）
# 4. 返回修复统计
{
    'repaired': 17564,           # 修复数量
    'total': 17564,              # 总数
    'elapsed': 15.3              # 耗时（秒）
}
```

**命令行工具**：
```bash
# 启动时自动检查并修复
python data/items_i18n.py

# 手动检查拼音完整性
python data/items_i18n.py --check-pinyin

# 手动修复拼音数据
python data/items_i18n.py --repair-pinyin
```

### 2.7 查询函数

#### `search_items()` — 多条件物品搜索

```python
def search_items(
    query: str,
    search_field: str = 'all',      # 'all' | 'zh' | 'en' | 'unique'
    category: str = None,
    is_prime: int = None,
    is_tradable: int = None,
    limit: int = 20
) -> list[dict]
```

**对应 SQL**（动态构建 WHERE 子句）：
```sql
SELECT * FROM items
WHERE 1=1
    -- search_field='all': 三字段模糊搜索
    AND (zh_name LIKE '%query%' OR en_name LIKE '%query%' OR unique_name LIKE '%query%')
    -- search_field='zh': 仅中文搜索
    AND zh_name LIKE '%query%'
    -- search_field='en': 仅英文搜索
    AND en_name LIKE '%query%'
    -- search_field='unique': 仅 unique_name 搜索
    AND unique_name LIKE '%query%'
    -- 可选过滤
    AND category = ?        -- 按类别过滤
    AND is_prime = ?        -- 按 Prime 过滤
    AND is_tradable = ?     -- 按可交易过滤
ORDER BY
    CASE WHEN en_name = ? THEN 0 ELSE 1 END,  -- 精确匹配优先
    LENGTH(en_name)                              -- 短名优先
LIMIT ?
```

#### `translate_item()` — 物品翻译

```python
def translate_item(name: str, direction: str = 'auto') -> Optional[str]
```

**逻辑**：
- `direction='auto'`：检测输入语言（包含中文 → 中译英，否则 → 英译中）
- `direction='en2zh'`：英文 → 中文
- `direction='zh2en'`：中文 → 英文

**对应 SQL**：
```sql
-- 英译中
SELECT zh_name FROM items WHERE en_name = ? LIMIT 1
-- 中译英
SELECT en_name FROM items WHERE zh_name = ? LIMIT 1
```

#### `get_db_stats()` — 数据库统计

```python
def get_db_stats() -> dict
```

**对应 SQL**：
```sql
SELECT COUNT(*) FROM items
SELECT COUNT(*) FROM items WHERE is_tradable = 1
SELECT COUNT(*) FROM items WHERE is_prime = 1
```

---

## 三、relics.db — 遗物掉落表数据库

### 3.1 文件位置

```
data/relics.db
```

定义于 `data/wfinfo_relics.py`：
```python
self._db_path = os.path.join(data_dir, 'relics.db')
```

### 3.2 完整 DDL

```sql
-- ============================================================
-- 表：relics — 遗物主表
-- ============================================================
CREATE TABLE IF NOT EXISTS relics (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE,        -- 遗物标准名称，如 "古纪 C7"
    era     TEXT NOT NULL,              -- 纪元中文名
    code    TEXT NOT NULL,              -- 遗物代码，如 "C7"
    vaulted INTEGER NOT NULL DEFAULT 0  -- 出入库状态
);

-- ============================================================
-- 表：relic_parts — 遗物包含的 Prime 部件
-- ============================================================
CREATE TABLE IF NOT EXISTS relic_parts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id  INTEGER NOT NULL,         -- 外键，关联 relics.id
    part_name TEXT NOT NULL,            -- Prime 部件名称
    rarity    TEXT NOT NULL,            -- 稀有度：Common / Uncommon / Rare
    chance    REAL NOT NULL DEFAULT 0,  -- 掉落几率
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

-- ============================================================
-- 表：relic_aliases — 遗物别名表（OCR 模糊匹配用）
-- ============================================================
CREATE TABLE IF NOT EXISTS relic_aliases (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id INTEGER NOT NULL,          -- 外键，关联 relics.id
    alias    TEXT NOT NULL UNIQUE,      -- 别名变体
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_relic_parts_relic_id ON relic_parts(relic_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias        ON relic_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_aliases_relic_id     ON relic_aliases(relic_id);
CREATE INDEX IF NOT EXISTS idx_relics_era           ON relics(era);
CREATE INDEX IF NOT EXISTS idx_relics_vaulted       ON relics(vaulted);
```

### 3.3 字段说明

#### relics 表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK, AUTO | 自增主键 |
| `name` | TEXT | NOT NULL, UNIQUE | 遗物标准名，如 "古纪 C7"、"后纪 G14"、"安魂 I" |
| `era` | TEXT | NOT NULL | 纪元名（中文） |
| `code` | TEXT | NOT NULL | 遗物代码，如 "C7"、"G14"、"I" |
| `vaulted` | INTEGER | DEFAULT 0 | 出入库状态：0=入库(不可获取), 1=出库(可获取), 2=虚空商人 |

#### relic_parts 表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK, AUTO | 自增主键 |
| `relic_id` | INTEGER | NOT NULL, FK | 关联 relics.id，级联删除 |
| `part_name` | TEXT | NOT NULL | Prime 部件英文名，如 "Braton Prime Blueprint" |
| `rarity` | TEXT | NOT NULL | 稀有度：Common（铜）、Uncommon（银）、Rare（金） |
| `chance` | REAL | DEFAULT 0 | 掉落几率（百分比） |

#### relic_aliases 表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK, AUTO | 自增主键 |
| `relic_id` | INTEGER | NOT NULL, FK | 关联 relics.id，级联删除 |
| `alias` | TEXT | NOT NULL, UNIQUE | 别名变体，用于 OCR 模糊匹配 |

### 3.4 纪元（era）枚举值

| 中文 | 英文 | 说明 |
|---|---|---|
| 古纪 | Lith | T1 |
| 前纪 | Meso | T2 |
| 中纪 | Neo | T3 |
| 后纪 | Axi | T4 |
| 安魂 | Requiem | 巫妖遗物 |
| 先锋 | Veiled | 裂隙遗物 |

### 3.5 别名生成策略

`generate_aliases()` 函数（`data/db_utils.py`）为每个遗物生成 **5 种别名变体**：

| 序号 | 格式 | 示例 |
|---|---|---|
| 1 | 原始名称 | `古纪 C7` |
| 2 | 标准名 | `古纪 C7` |
| 3 | 无空格 | `古纪C7` |
| 4 | 小写带空格 | `古纪 c7` |
| 5 | 小写无空格 | `古纪c7` |

### 3.6 数据来源

- **WFInfo 遗物掉落数据**：通过 `data/update_db.py` 从 WFInfo API 拉取最新遗物数据
- **源格式**：`data/relics.json`（JSON 格式，由 `migrate_to_sqlite.py` 转换为 SQLite）

### 3.7 查询函数（RelicDB 类）

`RelicDB` 类（`data/wfinfo_relics.py`）提供 **四级降级匹配查询**：

#### `find(name)` — 单遗物查询

```
第1级：别名精确匹配（最快路径）
  SELECT r.id, r.name, r.era, r.code, r.vaulted
  FROM relics r JOIN relic_aliases a ON a.relic_id = r.id
  WHERE a.alias = ?

第2级：主表 name 精确匹配
  SELECT id, name, era, code, vaulted FROM relics WHERE name = ?

第3级：忽略空格和大小写的模糊匹配
  SELECT r.id, r.name, r.era, r.code, r.vaulted
  FROM relics r JOIN relic_aliases a ON a.relic_id = r.id
  WHERE REPLACE(a.alias, ' ', '') = ? OR REPLACE(LOWER(a.alias), ' ', '') = ?

第4级：正则模糊匹配（处理 OCR 易混淆字符 O↔0, I↔1, 5↔S, 8↔B）
  遍历所有别名，应用 _fuzzy_normalize() 后比对
```

#### `get_parts(name)` — 获取遗物部件

```sql
SELECT part_name, rarity, chance FROM relic_parts WHERE relic_id = ? ORDER BY id
```

#### `query_many(names)` — 批量查询

```python
# 对每个名称调用 find()
[(name, self.find(name)) for name in names]
```

#### `stats()` — 数据库统计

```sql
SELECT COUNT(*) FROM relics
SELECT COUNT(*) FROM relics WHERE vaulted = 1   -- 出库数量
SELECT COUNT(*) FROM relic_aliases              -- 别名总数
SELECT COUNT(*) FROM relic_parts                -- 部件总数
```

#### `is_vaulted(name)` — 检查出入库

```python
relic = self.find(name)
return relic.get('vaulted', False) if relic else False
```

### 3.8 返回数据结构

```python
{
    'name': '古纪 C7',          # 遗物标准名
    'era': '古纪',              # 纪元
    'code': 'C7',               # 代码
    'vaulted': True,            # 是否出库（True=可获取, False=入库不可获取）
    'parts': [
        {
            'name': 'Braton Prime 枪机',     # 部件名（自动翻译为中文）
            'rarity': 'Common',               # 稀有度
            'chance': 25.33                   # 掉落几率 %
        },
        # ...
    ]
}
```

---

## 四、wm_prices.db — Warframe.Market 价格数据库

### 4.1 文件位置

```
data/wm_prices.db
```

定义于 `data/wm_prices.py` 第 50 行：
```python
DB_PATH = os.path.join(BASE_DIR, 'wm_prices.db')
```

### 4.2 完整 DDL

```sql
-- ============================================================
-- 表：item_prices — 物品价格表（仅卖价）
-- ============================================================
CREATE TABLE IF NOT EXISTS item_prices (
    item_id          INTEGER NOT NULL,        -- 关联 items_i18n.db items.id
    en_name          TEXT NOT NULL DEFAULT '', -- 物品英文名（直接查询用，不依赖 JOIN）
    slug             TEXT NOT NULL,            -- warframe.market 物品 slug
    sell_min         INTEGER,                 -- 最低卖价（白金）— 前 5 中的最低价
    sell_median      REAL,                    -- 卖价中位数 — 前 5 中位数
    sell_weighted    REAL,                    -- ★ 加权卖价（反压价后推荐参考价）
    sell_volume      INTEGER,                 -- 前 5 卖单数
    sell_top3        TEXT,                    -- 前 3 个卖价 JSON 数组：[p1, p2, p3]
    sell_volume_full INTEGER,                 -- 该物品全量卖单总数
    volume_48h       INTEGER,                 -- 48 小时成交量（来自 statistics API）
    avg_price_90d    REAL,                    -- 90 天加权均价
    updated_at       TEXT NOT NULL,           -- 价格更新时间（格式：YYYY-MM-DD HH:MM:SS）
    PRIMARY KEY (item_id)
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prices_en_name  ON item_prices(en_name);
CREATE INDEX IF NOT EXISTS idx_prices_slug     ON item_prices(slug);
CREATE INDEX IF NOT EXISTS idx_prices_weighted ON item_prices(sell_weighted);
CREATE INDEX IF NOT EXISTS idx_prices_updated  ON item_prices(updated_at);

-- ============================================================
-- 表：price_meta — 元信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS price_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### 4.3 字段说明

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `item_id` | INTEGER | PK | 关联 `items_i18n.db` 的 `items.id` |
| `en_name` | TEXT | NOT NULL, DEFAULT '' | 物品英文名（冗余字段，避免 JOIN 查询） |
| `slug` | TEXT | NOT NULL | warframe.market URL slug，如 `braton_prime_set` |
| `sell_min` | INTEGER | — | 前 5 个卖单中的最低价（白金） |
| `sell_median` | REAL | — | 前 5 个卖单的中位数价格 |
| `sell_weighted` | REAL | — | ★ 反压价加权参考价（推荐使用此价格） |
| `sell_volume` | INTEGER | — | 参与计算的卖单数（≤ 20） |
| `sell_top3` | TEXT | — | JSON 数组 `[p1, p2, p3]`，前 3 个最低卖价 |
| `sell_volume_full` | INTEGER | — | 该物品在 warframe.market 上的全量卖单数 |
| `volume_48h` | INTEGER | — | 48 小时内成交量 |
| `avg_price_90d` | REAL | — | 90 天加权均价 |
| `updated_at` | TEXT | NOT NULL | 价格最后更新时间 |

### 4.4 反压价权重算法

价格数据拉取时内置 **反压价机制**，参数定义：

```python
PRICE_ABNORMAL_THRESHOLD = 0.30   # 价格偏离中位数 > 30% 视为异常压价
ABNORMAL_WEIGHT = 0.1            # 异常价格的权重（正常价格为 1.0）
SELL_ORDER_SAMPLE = 20           # 拉取前 20 个最低卖单做分析
```

**算法流程**：

```
1. 拉取物品全量卖单 → 按价格升序排列
2. 取前 20 个最低卖价
3. 计算中位数
4. 价格 < 中位数 × (1 - 30%) → 标记为异常压价（权重 0.1）
5. 正常价格权重 = 1.0
6. 加权均价 = Σ(price × weight) / Σ(weight)  →  即 sell_weighted
```

**示例**：某物品卖价 `[5, 5, 5, 10, 12, 13, 14, 15, ...]`
- 中位数 ≈ 12.5
- 异常阈值 = 12.5 × 0.7 = 8.75
- 5p 的卖单 → 异常（权重 0.1）
- 加权均价 ≈ (5×0.1×3 + 10+12+13+14+15+...) / (0.1×3 + 1×17) ≈ 14.3p
- 如果不用权重，最低价只有 5p，会被压价者误导

### 4.5 数据来源

**API 端点**：
```
https://api.warframe.market/v2/items                         ← 全物品列表
https://api.warframe.market/v2/orders/item/{slug}            ← 物品卖单数据
https://api.warframe.market/v1/items/{slug}/statistics       ← 历史统计
```

**并发配置**：
```python
MAX_WORKERS = 8            # 最大并发线程数
RATE_LIMIT_PER_SEC = 3     # 全局限速：每秒最多 3 个请求
REQUEST_INTERVAL = 0.35    # 每次请求间隔 0.35 秒
REQUEST_TIMEOUT = 30       # 单次请求超时 30 秒
```

**拉取流程** (`fetch_all_prices()`)：
```
步骤1：获取 warframe.market 全物品列表（~1,200 个物品）
步骤2：与本地 items_i18n.db 匹配（精确 + 模糊匹配）
步骤3：多线程并发拉取每个物品的卖单数据（8 线程 + 限速器）
步骤4：反压价权重计算
步骤5：分批写入数据库（每 200 条提交一次）
```

### 4.6 查询函数

#### `get_price(en_name)` — 单物品价格查询

```sql
-- 优先：en_name 精确匹配
SELECT * FROM item_prices WHERE en_name = ?

-- 降级：en_name 模糊匹配
SELECT * FROM item_prices WHERE en_name LIKE ? ORDER BY LENGTH(en_name) ASC LIMIT 1

-- 兼容旧数据库：通过 items_i18n JOIN 查询
SELECT p.* FROM item_prices p
INNER JOIN items_i18n_db.items i ON p.item_id = i.id
WHERE i.en_name = ?
```

#### `get_prices_batch(en_names)` — 批量价格查询

```sql
SELECT * FROM item_prices WHERE en_name IN (?, ?, ...)
```

#### `fetch_price_realtime(en_name)` — 实时 API 查询

```
1. 从本地 DB 获取 slug
2. 调用 /v2/orders/item/{slug} 获取实时卖单
3. 调用 /v1/items/{slug}/statistics 获取历史统计（非阻塞）
4. 反压价权重计算
5. API 失败/超时 → fallback 本地 DB
```

#### `get_price_stats()` — 数据库统计

```sql
SELECT COUNT(*) FROM item_prices
SELECT COUNT(*) FROM item_prices WHERE sell_weighted IS NOT NULL
SELECT COUNT(*) FROM item_prices WHERE sell_weighted IS NOT NULL AND sell_min != sell_weighted
SELECT key, value FROM price_meta
```

### 4.7 元信息（price_meta）键值

| key | value 示例 | 说明 |
|---|---|---|
| `source` | `warframe.market API v2` | 数据来源 |
| `total` | `1234` | 总物品数 |
| `with_sell` | `1100` | 有卖价数据的物品数 |
| `with_weighted` | `85` | 检测到压价的物品数 |
| `with_stats` | `200` | 有历史统计的物品数 |
| `total_abnormal` | `120` | 异常压价总次数 |
| `updated_at` | `2025-06-01 12:00:00` | 最后更新时间 |
| `concurrency` | `8 threads, rate_limit=3/s` | 拉取并发配置 |

---

## 五、translation.db — 中英翻译缓存（旧版）

### 5.1 文件位置

```
data/translation.db
```

### 5.2 完整 DDL

```sql
-- ============================================================
-- 表：translations — 翻译对照表
-- ============================================================
CREATE TABLE IF NOT EXISTS translations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zh_name     TEXT NOT NULL,             -- 中文名
    en_name     TEXT NOT NULL,             -- 英文名
    unique_name TEXT,                      -- 游戏内部唯一标识
    category    TEXT,                      -- 物品分类
    source      TEXT DEFAULT 'wfcd',       -- 数据来源：wfcd / adminroc
    item_type   TEXT,                      -- 物品子类型
    is_tradable INTEGER DEFAULT 0,         -- 是否可交易
    UNIQUE(zh_name, en_name)
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_zh        ON translations(zh_name);
CREATE INDEX IF NOT EXISTS idx_en        ON translations(en_name);
CREATE INDEX IF NOT EXISTS idx_category  ON translations(category);
CREATE INDEX IF NOT EXISTS idx_unique    ON translations(unique_name);
CREATE INDEX IF NOT EXISTS idx_item_type ON translations(item_type);

-- ============================================================
-- 表：translation_meta — 元信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS translation_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### 5.3 状态说明

> ⚠️ **此数据库为旧版翻译缓存**，已被 `items_i18n.db` 取代。
>
> 目前仅在 `price_service.py` 的 `_translate_weapon_name()` 函数中作为兜底翻译使用：
> ```python
> cur.execute("SELECT zh_name FROM translations WHERE en_name = ? LIMIT 1", (weapon_name,))
> ```

---

## 六、配置文件

### 6.1 config.json — 框选区域持久化

**文件路径**：`%APPDATA%/WARFRAME-RELIC/config.json`

**格式**：
```json
{
    "region": [left, top, right, bottom]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `region` | `[int, int, int, int]` | 上次框选的截图区域逻辑坐标 |

**生命周期**：
- 程序启动时 → `_load_region()` 读取，恢复上次框选区域
- 框选完成后 → `_save_region()` 写入，持久化当前区域
- 跨程序运行持久化，用户无需每次重新框选

### 6.2 hotkeys.json — 热键自定义配置

**文件路径**：`data/hotkeys.json`

**默认内容**（空对象表示使用默认热键）：
```json
{}
```

**自定义格式**（用户通过管理面板修改后写入）：
```json
{
    "select": "ctrl+g",
    "fullscreen": "ctrl+h",
    "panel": "ctrl+shift+g",
    "query_price": "ctrl+shift+p"
}
```

**默认热键**：

| 动作 ID | 默认快捷键 | 功能说明 |
|---|---|---|
| `select` | `ctrl+g` | 框选截图 → 识别物品 |
| `fullscreen` | `ctrl+h` | 全屏截图 → 识别物品 |
| `panel` | `ctrl+shift+g` | 打开管理面板 |
| `query_price` | `ctrl+shift+p` | 价格查询 |

### 6.3 item_region.json — 物品识别区域配置

**文件路径**：`data/item_region.json`

**格式**：
```json
{
    "x": 45,
    "y": 342,
    "w": 701,
    "h": 87
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `x` | int | 物品名称区域左上角 X 坐标 |
| `y` | int | 物品名称区域左上角 Y 坐标 |
| `w` | int | 区域宽度 |
| `h` | int | 区域高度 |

---

## 七、数据库关系图

```
┌─────────────────────────────────────────────────────────────┐
│                     数据来源（上游）                          │
├─────────────────────────────────────────────────────────────┤
│  WFCD warframe-items/All.json    → 物品完整数据              │
│  WFCD warframe-items/i18n.json   → 多语言翻译                │
│  AdminRoc zh_en_dict.json        → 中英对照补充数据           │
│  WFInfo API                      → 遗物掉落表                │
│  warframe.market API v2          → 实时买卖价格              │
│  warframe.market API v1          → 历史统计                  │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                     本地数据库（存储层）                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐    ┌──────────────────────┐        │
│  │  items_i18n.db       │    │  relics.db            │        │
│  │  ┌─────────────────┐ │    │  ┌──────────────────┐ │        │
│  │  │ items            │ │    │  │ relics           │ │        │
│  │  │  - id (PK)       │ │    │  │  - id (PK)       │ │        │
│  │  │  - unique_name   │ │    │  │  - name (UNIQUE) │ │        │
│  │  │  - zh_name       │ │    │  │  - era           │ │        │
│  │  │  - en_name       │ │    │  │  - code          │ │        │
│  │  │  - category      │ │    │  │  - vaulted       │ │        │
│  │  │  - is_tradable   │ │    │  └──────────────────┘ │        │
│  │  │  - is_prime      │ │    │  ┌──────────────────┐ │        │
│  │  │  - zh_pinyin     │ │    │  │ relic_parts      │ │        │
│  │  │  - ...           │ │    │  │  - relic_id (FK) │ │        │
│  │  └─────────────────┘ │    │  │  - part_name     │ │        │
│  │  ┌─────────────────┐ │    │  │  - rarity        │ │        │
│  │  │ items_meta       │ │    │  │  - chance        │ │        │
│  │  └─────────────────┘ │    │  └──────────────────┘ │        │
│  └─────────────────────┘    │  ┌──────────────────┐ │        │
│                              │  │ relic_aliases    │ │        │
│                              │  │  - relic_id (FK) │ │        │
│                              │  │  - alias (UNIQUE)│ │        │
│                              │  └──────────────────┘ │        │
│                              └──────────────────────┘        │
│                                                             │
│  ┌─────────────────────┐    ┌──────────────────────┐        │
│  │  wm_prices.db        │    │  translation.db      │        │
│  │  ┌─────────────────┐ │    │  (旧版，已弃用)       │        │
│  │  │ item_prices      │ │    │  ┌──────────────────┐ │        │
│  │  │  - item_id (PK)  │◄├────┼──┤ items.id         │ │        │
│  │  │  - en_name       │ │    │  └──────────────────┘ │        │
│  │  │  - slug          │ │    └──────────────────────┘        │
│  │  │  - sell_weighted │ │                                   │
│  │  │  - sell_min      │ │                                   │
│  │  │  - sell_median   │ │                                   │
│  │  │  - sell_top3     │ │                                   │
│  │  │  - volume_48h    │ │                                   │
│  │  │  - avg_price_90d │ │                                   │
│  │  │  - updated_at    │ │                                   │
│  │  └─────────────────┘ │                                   │
│  │  ┌─────────────────┐ │                                   │
│  │  │ price_meta       │ │                                   │
│  │  └─────────────────┘ │                                   │
│  └─────────────────────┘                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                     服务层（查询/写入）                        │
├─────────────────────────────────────────────────────────────┤
│  RelicDB (wfinfo_relics.py)     → 遗物查询（4级模糊匹配）     │
│  PriceService (price_service.py)→ 价格查询（缓存→DB→API）    │
│  matcher.py                     → 物品匹配（4轮降级匹配）     │
│  search_items() (items_i18n.py) → 物品搜索                   │
│  translate_item() (items_i18n.py)→ 物品翻译                   │
│  wm_prices.get_price()          → 本地价格查询               │
│  wm_prices.fetch_price_realtime()→ 实时 API 价格查询          │
│  translation_db                 → 兜底翻译（旧版）             │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                     应用层（展示）                             │
├─────────────────────────────────────────────────────────────┤
│  Overlay (overlay.py)           → 覆盖层标注显示              │
│  ManagementPanel (management_panel.py) → 管理面板设置         │
│  RelicTooltip (relic_tooltip.py)→ 遗物内容悬浮窗              │
│  DropTooltip (drop_tooltip.py)  → 掉落来源悬浮窗              │
└─────────────────────────────────────────────────────────────┘
```

---

## 八、完整调用链

### 8.1 遗物查询调用链

```
用户按 ctrl+g 框选截图
  → dxcam 截图
  → RelicNameRecognizer (relic_name.py) OCR 识别遗物名
  → RelicDB.find(name) (wfinfo_relics.py)
    → 第1级：relic_aliases 精确匹配
    → 第2级：relics.name 精确匹配
    → 第3级：忽略空格大小写模糊匹配
    → 第4级：OCR 字符混淆正则匹配
  → RelicDB._build_result() 查询 relic_parts
  → RelicDB._translate_part() 翻译部件名
  → Overlay.show_annotations_stream() 流式显示
```

### 8.2 物品价格查询调用链

```
用户按 ctrl+g 框选截图
  → dxcam 截图
  → ItemNameRecognizer (item_name.py) OCR 识别物品名
  → matcher.match_items() 4 轮降级匹配
    → 第1轮：精确匹配 en_name
    → 第2轮：模糊匹配（单词合理性验证）
    → 第3轮：纠错候选逐个尝试
    → 第4轮：部件蓝图直通（查 WM API，自动补 Prime）
  → PriceService.query_prices_batch() 批量查价格
    → L1：内存缓存（30 秒 TTL）
    → L2：wm_prices.db 本地数据库
    → L3：warframe.market API 实时查询（4 线程并发）
    → 反压价权重计算
  → format_price_annotation() 格式化标注文本
  → build_display_name() 构建中文显示名
  → price_to_color() 按价格着色
  → Overlay.show_annotations_stream() 流式显示
```

### 8.3 数据库写入调用链

```
# items_i18n.db 写入
matcher._upsert_part_to_db()          → INSERT INTO items（部件直通发现的新物品）
items_i18n.build_all_items_db()       → DELETE + INSERT 全量重建

# wm_prices.db 写入
wm_prices.fetch_all_prices()          → 全量拉取流程
  ├── _fetch_wm_items()               → 获取 WM 全物品列表
  ├── _match_items()                  → 与 items_i18n.db 匹配
  └── _build_price_db()               → 多线程拉取 + 批量写入
      └── _batch_insert()             → INSERT INTO item_prices

# relics.db 写入
update_db.py                          → 从 WFInfo API 拉取最新数据
migrate_to_sqlite.py                  → JSON → SQLite 迁移
```

---

## 九、API 速率限制与并发策略

| API | 限速 | 并发策略 |
|---|---|---|
| warframe.market API v2 | 3 请求/秒 | 8 线程并发 + 全局限速器（令牌桶） |
| warframe.market API v1 | 继承 v2 限速 | 每 50 个物品附带一次统计请求 |
| WFInfo API | 无明确限制 | 单线程顺序拉取 |

**限速器实现**（`wm_prices.py`）：
```python
class _RateLimiter:
    """线程安全的令牌桶限速器"""
    def acquire(self):
        with self._lock:
            wait = self._next_available - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._next_available = time.monotonic() + self._interval
```

---

## 十、文件结构引用（v3.4）

数据库相关文件在项目中的位置：

```
WARFRAME-RELIC/
├── data/
│   ├── items_i18n.py           # items_i18n.db 管理（含拼音检查/修复）
│   ├── items_i18n.db           # 全物品中英对照数据库
│   ├── wfinfo_relics.py        # relics.db 查询类 RelicDB
│   ├── relics.db               # 遗物掉落数据库
│   ├── wm_prices.py            # wm_prices.db 管理（拉取/查询/统计）
│   ├── wm_prices.db            # WM 价格缓存
│   ├── translation_db.py       # translation.db 管理（旧版，已弃用）
│   ├── translation.db          # 翻译缓存（旧版）
│   ├── db_utils.py             # 数据库工具函数
│   ├── ui_strings.py           # UI 字符串路由器
│   └── version.py              # 版本信息
├── core/
│   ├── bootstrap.py            # ★ 入口：单例/管理员/异常钩子/main()
│   ├── hotkey_manager.py       # ★ 热键管理器
│   ├── mode_handlers.py        # ★ 功能处理器（调用数据库查询）
│   ├── price_service.py        # 价格服务（三级查询）
│   └── ...
├── main.py                     # AppCore 中央控制器
├── DATABASE.md                 # 本文档
└── DEVELOPMENT.md              # 开发文档
```

---

## 十一、开发常用命令

```bash
# 重建全物品中英对照数据库（批量插入优化，5-10秒完成）
python data/items_i18n.py --rebuild

# 检查拼音数据完整性
python data/items_i18n.py --check-pinyin

# 修复缺失的拼音数据（批量处理，约15秒完成）
python data/items_i18n.py --repair-pinyin

# 拉取全量 warframe.market 价格数据
python data/wm_prices.py --fetch

# 查看价格数据库统计
python data/wm_prices.py --stats

# 查询单个物品价格
python data/wm_prices.py --search "Braton Prime Set"

# 批量查询物品价格
python data/wm_prices.py --search-batch "Braton Prime Set,Ash Prime Chassis"

# 更新遗物掉落数据
python data/update_db.py

# 启动主程序
python main.py
```

---

## 十一、v3.4 数据库优化说明

### 11.1 Schema版本管理

**问题**：旧版数据库可能缺少 `zh_pinyin` 字段，导致拼音搜索失败。

**解决方案**：在 `items_meta` 表中添加 `schema_version` 字段，自动检测并升级。

```sql
-- v2 schema 新增元信息
INSERT OR REPLACE INTO items_meta (key, value) VALUES ('schema_version', '2')
```

**迁移逻辑**（`_ensure_schema_version()`）：
```python
if current_version == '1':
    # v1 → v2: 添加 zh_pinyin 字段并回填拼音
    ALTER TABLE items ADD COLUMN zh_pinyin TEXT DEFAULT ''
    CREATE INDEX idx_items_pinyin ON items(zh_pinyin)
    
    # 批量回填拼音（如果pypinyin已安装）
    for row_id, zh_name in rows_missing_pinyin:
        py = _make_pinyin(zh_name)
        UPDATE items SET zh_pinyin = ? WHERE id = ?
```

### 11.2 批量插入优化

**问题**：逐条INSERT效率极低，17564条记录需要30-60秒。

**优化方案**：使用 `executemany()` 批量插入，每500条提交一次。

**优化前**：
```python
for item in items:
    cur.execute("INSERT INTO items ...", values)  # 17564次调用
conn.commit()
```

**优化后**：
```python
BATCH_SIZE = 500
batch_data = []

for item in items:
    batch_data.append(values)
    if len(batch_data) >= BATCH_SIZE:
        conn.executemany("INSERT INTO items ...", batch_data)  # 约36次调用
        batch_data.clear()

# 提交剩余数据
if batch_data:
    conn.executemany("INSERT INTO items ...", batch_data)
```

**性能对比**：

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| SQL调用次数 | 17564次 | ~36次 | **~500倍** |
| 总耗时 | 30-60秒 | 5-10秒 | **5-10倍** |
| 内存占用 | 低 | 略高（批次缓存） | 可接受 |

### 11.3 拼音完整性检查与修复

**问题**：数据库重建时如果pypinyin未安装，所有记录的拼音字段为空。

**解决方案**：
1. **启动时自动检查**：`init_database_check(auto_repair=True)`
2. **手动检查工具**：`python items_i18n.py --check-pinyin`
3. **批量修复工具**：`python items_i18n.py --repair-pinyin`

**检查流程**：
```python
def check_pinyin_integrity():
    total = SELECT COUNT(*) FROM items
    has_pinyin = SELECT COUNT(*) FROM items WHERE zh_pinyin != ''
    missing = total - has_pinyin
    rate = has_pinyin / total
    
    return {
        'total': total,
        'has_pinyin': has_pinyin,
        'missing_pinyin': missing,
        'integrity_rate': rate,
        'needs_repair': missing > 0
    }
```

**修复流程**：
```python
def repair_pinyin_data(batch_size=500):
    rows = SELECT id, zh_name FROM items WHERE zh_pinyin = ''
    
    batch_data = []
    for row_id, zh_name in rows:
        py = _make_pinyin(zh_name)
        batch_data.append((py, row_id))
        
        if len(batch_data) >= batch_size:
            executemany("UPDATE items SET zh_pinyin = ? WHERE id = ?", batch_data)
            batch_data.clear()
    
    # 提交剩余数据
    if batch_data:
        executemany("UPDATE items SET zh_pinyin = ? WHERE id = ?", batch_data)
```

### 11.4 框选交互修复

**问题**：右键清除覆盖显示后，首次框选会立即消失。

**根本原因**：
1. Overlay的 `_right_was_down` 状态未重置
2. RegionSelector启动时未等待鼠标状态稳定

**修复方案**：
```python
# overlay.py: start_selection()
def start_selection(self):
    # 重置右键状态
    self._right_was_down = False
    self._ignore_right_until = 0
    self._region_selector.start()

# region_selector.py: start()
def start(self):
    right_now = self._is_key_down(_VK_RBUTTON)
    if right_now:
        # 延迟100ms启动，等待鼠标状态稳定
        QTimer.singleShot(100, self._delayed_start)
        return
    # 正常启动...
```

---

## 十二、数据库关系图（v3.4更新）

详见第七章，新增内容：
- `items_meta` 表新增 `schema_version` 字段
- 批量插入优化流程图
- 拼音完整性检查与修复流程
