"""
统一数据库构建模块 (build_warframe_db.py)

从所有 JSON 源文件构建单一 warframe.db 数据库。

数据源:
  - external/warframe-items_sparse/data/json/All.json   → 全物品数据
  - external/warframe-items_sparse/data/json/i18n.json  → 物品多语言翻译
  - external/warframe-drop-data_sparse/data/all.json    → 掉落数据（DE 官方）
  - external/warframe-i18n_sparse/dict.en.json          → 游戏术语英文
  - external/warframe-i18n_sparse/dict.zh.json          → 游戏术语中文
  - https://api.warframe.market/v2/items                → 市场物品映射

输出: data/warframe.db
"""

import json
import re
import sqlite3
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Callable

from pypinyin import lazy_pinyin, Style

# ============================================================
# 路径常量
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
EXTERNAL_DIR = BASE_DIR.parent / "external"

ALL_JSON = EXTERNAL_DIR / "warframe-items_sparse" / "data" / "json" / "All.json"
I18N_JSON = EXTERNAL_DIR / "warframe-items_sparse" / "data" / "json" / "i18n.json"
DROP_DATA_JSON = EXTERNAL_DIR / "warframe-drop-data_sparse" / "data" / "all.json"
DICT_EN_JSON = EXTERNAL_DIR / "warframe-i18n_sparse" / "dict.en.json"
DICT_ZH_JSON = EXTERNAL_DIR / "warframe-i18n_sparse" / "dict.zh.json"

DB_PATH = BASE_DIR / "warframe.db"

# ============================================================
# Schema
# ============================================================

SCHEMA_SQL = """
-- ============================================================
-- 1. 全物品主表（来源：warframe-items/All.json）
-- ============================================================
CREATE TABLE IF NOT EXISTS items (
    unique_name         TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    zh_name             TEXT DEFAULT '',
    type                TEXT NOT NULL,
    category            TEXT DEFAULT '',
    tradable            INTEGER DEFAULT 0,
    masterable          INTEGER DEFAULT 0,
    is_prime            INTEGER DEFAULT 0,
    description         TEXT DEFAULT '',
    description_zh      TEXT DEFAULT '',
    image_name          TEXT DEFAULT '',
    exclude_from_codex  INTEGER DEFAULT 0,
    show_in_inventory   INTEGER DEFAULT 1,
    build_price             INTEGER,
    build_time              INTEGER,
    skip_build_time_price   INTEGER,
    build_quantity          INTEGER DEFAULT 1,
    consume_on_build        INTEGER DEFAULT 1,
    market_cost             INTEGER,
    bp_cost                 INTEGER,
    introduced              TEXT DEFAULT '',
    release_date            TEXT DEFAULT '',
    wikia_url          TEXT DEFAULT '',
    wiki_available      INTEGER DEFAULT 0,
    zh_pinyin           TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);
CREATE INDEX IF NOT EXISTS idx_items_zh_name ON items(zh_name);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_tradable ON items(tradable);
CREATE INDEX IF NOT EXISTS idx_items_prime ON items(is_prime);
CREATE INDEX IF NOT EXISTS idx_items_zh_pinyin ON items(zh_pinyin);

-- ============================================================
-- 2. 类型专属属性表（JSON 扩展字段）
-- ============================================================
CREATE TABLE IF NOT EXISTS item_type_attrs (
    unique_name     TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    attrs           TEXT NOT NULL,
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attrs_type ON item_type_attrs(type);

-- ============================================================
-- 3. 技能表（Warframe / Archwing 专属）
-- ============================================================
CREATE TABLE IF NOT EXISTS item_abilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name     TEXT NOT NULL,
    ability_index   INTEGER NOT NULL,
    ability_unique  TEXT DEFAULT '',
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    image_name      TEXT DEFAULT '',
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE,
    UNIQUE(unique_name, ability_index)
);

CREATE INDEX IF NOT EXISTS idx_abilities_item ON item_abilities(unique_name);

-- ============================================================
-- 4. 攻击模式表（武器专属）
-- ============================================================
CREATE TABLE IF NOT EXISTS item_attacks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name     TEXT NOT NULL,
    attack_index    INTEGER NOT NULL,
    attack_name     TEXT DEFAULT '',
    crit_chance     REAL DEFAULT 0,
    crit_mult       REAL DEFAULT 0,
    status_chance   REAL DEFAULT 0,
    shot_type       TEXT DEFAULT '',
    speed           REAL DEFAULT 0,
    charge_time     REAL DEFAULT 0,
    damage_json     TEXT DEFAULT '',
    pellet_count    INTEGER DEFAULT 1,
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE,
    UNIQUE(unique_name, attack_index)
);

CREATE INDEX IF NOT EXISTS idx_attacks_item ON item_attacks(unique_name);

-- ============================================================
-- 5. 制造组件表
-- ============================================================
CREATE TABLE IF NOT EXISTS item_components (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_name     TEXT NOT NULL,
    component_name  TEXT NOT NULL,
    component_unique TEXT DEFAULT '',
    item_count      INTEGER DEFAULT 1,
    tradable        INTEGER DEFAULT 0,
    image_name      TEXT DEFAULT '',
    FOREIGN KEY (parent_name) REFERENCES items(unique_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_components_parent ON item_components(parent_name);

-- ============================================================
-- 6. 物品掉落来源表（All.json 的 drops[]）
-- ============================================================
CREATE TABLE IF NOT EXISTS item_drops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name     TEXT NOT NULL,
    drop_type       TEXT DEFAULT '',
    location        TEXT NOT NULL,
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_drops_item ON item_drops(unique_name);
CREATE INDEX IF NOT EXISTS idx_drops_location ON item_drops(location);

-- ============================================================
-- 7. 更新日志表
-- ============================================================
CREATE TABLE IF NOT EXISTS item_patchlogs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name     TEXT NOT NULL,
    patch_name      TEXT DEFAULT '',
    patch_date      TEXT DEFAULT '',
    patch_url       TEXT DEFAULT '',
    additions       TEXT DEFAULT '',
    changes         TEXT DEFAULT '',
    fixes           TEXT DEFAULT '',
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_patchlogs_item ON item_patchlogs(unique_name);

-- ============================================================
-- 8. 多语言翻译表（i18n.json）
-- ============================================================
CREATE TABLE IF NOT EXISTS item_translations (
    unique_name     TEXT NOT NULL,
    lang            TEXT NOT NULL,
    name            TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    PRIMARY KEY (unique_name, lang),
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trans_lang ON item_translations(lang);

-- ============================================================
-- 9. 遗物表（来源：warframe-drop-data all.json relics[]）
-- ============================================================
CREATE TABLE IF NOT EXISTS relics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tier            TEXT NOT NULL,
    relic_name      TEXT NOT NULL,
    state           TEXT NOT NULL,
    vaulted         INTEGER DEFAULT 0,
    drop_data_id    TEXT DEFAULT '',
    UNIQUE(tier, relic_name, state)
);

CREATE INDEX IF NOT EXISTS idx_relics_tier ON relics(tier);
CREATE INDEX IF NOT EXISTS idx_relics_vaulted ON relics(vaulted);
CREATE INDEX IF NOT EXISTS idx_relics_lookup ON relics(tier, relic_name);

-- ============================================================
-- 10. 遗物奖励表
-- ============================================================
CREATE TABLE IF NOT EXISTS relic_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    relic_id        INTEGER NOT NULL,
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT NOT NULL,
    chance          REAL NOT NULL DEFAULT 0,
    drop_data_id    TEXT DEFAULT '',
    wm_url_name     TEXT DEFAULT '',
    FOREIGN KEY (relic_id) REFERENCES relics(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rewards_relic ON relic_rewards(relic_id);
CREATE INDEX IF NOT EXISTS idx_rewards_item ON relic_rewards(item_name);
CREATE INDEX IF NOT EXISTS idx_rewards_unique ON relic_rewards(item_unique);

-- ============================================================
-- 11. 星球表（来源：all.json missionRewards）
-- ============================================================
CREATE TABLE IF NOT EXISTS planets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE
);

-- ============================================================
-- 12. 任务节点表
-- ============================================================
CREATE TABLE IF NOT EXISTS mission_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    planet_id       INTEGER NOT NULL,
    node_name       TEXT NOT NULL,
    game_mode       TEXT DEFAULT '',
    is_event        INTEGER DEFAULT 0,
    UNIQUE(planet_id, node_name),
    FOREIGN KEY (planet_id) REFERENCES planets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_nodes_planet ON mission_nodes(planet_id);
CREATE INDEX IF NOT EXISTS idx_nodes_mode ON mission_nodes(game_mode);

-- ============================================================
-- 13. 任务奖励表
-- ============================================================
CREATE TABLE IF NOT EXISTS mission_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         INTEGER NOT NULL,
    rotation        TEXT DEFAULT '',
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT '',
    FOREIGN KEY (node_id) REFERENCES mission_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mrewards_node ON mission_rewards(node_id);
CREATE INDEX IF NOT EXISTS idx_mrewards_item ON mission_rewards(item_name);
CREATE INDEX IF NOT EXISTS idx_mrewards_rotation ON mission_rewards(node_id, rotation);

-- ============================================================
-- 14. Mod 掉落表（all.json modLocations）
-- ============================================================
CREATE TABLE IF NOT EXISTS mod_drops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_name        TEXT NOT NULL,
    mod_unique      TEXT DEFAULT '',
    enemy_name      TEXT NOT NULL,
    enemy_mod_drop_chance REAL DEFAULT 0,
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_moddrops_mod ON mod_drops(mod_name);
CREATE INDEX IF NOT EXISTS idx_moddrops_enemy ON mod_drops(enemy_name);

-- ============================================================
-- 15. 敌人 Mod 掉落表（all.json enemyModTables）
-- ============================================================
CREATE TABLE IF NOT EXISTS enemy_mod_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    enemy_name      TEXT NOT NULL,
    enemy_mod_drop_chance REAL DEFAULT 0,
    mod_name        TEXT NOT NULL,
    mod_unique      TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_enemymod_enemy ON enemy_mod_tables(enemy_name);
CREATE INDEX IF NOT EXISTS idx_enemymod_mod ON enemy_mod_tables(mod_name);

-- ============================================================
-- 16. 蓝图掉落表（all.json blueprintLocations）
-- ============================================================
CREATE TABLE IF NOT EXISTS blueprint_drops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    blueprint_name  TEXT NOT NULL,
    blueprint_unique TEXT DEFAULT '',
    enemy_name      TEXT NOT NULL,
    enemy_bp_drop_chance REAL DEFAULT 0,
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_bpdrops_bp ON blueprint_drops(blueprint_name);
CREATE INDEX IF NOT EXISTS idx_bpdrops_enemy ON blueprint_drops(enemy_name);

-- ============================================================
-- 17. 敌人蓝图掉落表（all.json enemyBlueprintTables）
-- ============================================================
CREATE TABLE IF NOT EXISTS enemy_bp_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    enemy_name      TEXT NOT NULL,
    enemy_bp_drop_chance REAL DEFAULT 0,
    blueprint_name  TEXT NOT NULL,
    blueprint_unique TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_enemybp_enemy ON enemy_bp_tables(enemy_name);
CREATE INDEX IF NOT EXISTS idx_enemybp_bp ON enemy_bp_tables(blueprint_name);

-- ============================================================
-- 18. 突击奖励表（all.json sortieRewards）
-- ============================================================
CREATE TABLE IF NOT EXISTS sortie_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sortie_item ON sortie_rewards(item_name);

-- ============================================================
-- 19. 赏金奖励表（all.json cetus/solaris/deimos/zariman/entratiLab/hex）
-- ============================================================
CREATE TABLE IF NOT EXISTS bounty_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    bounty_level    TEXT DEFAULT '',
    rotation        TEXT DEFAULT '',
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_bounty_source ON bounty_rewards(source);
CREATE INDEX IF NOT EXISTS idx_bounty_item ON bounty_rewards(item_name);

-- ============================================================
-- 20. 临时奖励表（all.json transientRewards）
-- ============================================================
CREATE TABLE IF NOT EXISTS transient_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_name  TEXT NOT NULL,
    rotation        TEXT DEFAULT '',
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_transient_obj ON transient_rewards(objective_name);
CREATE INDEX IF NOT EXISTS idx_transient_item ON transient_rewards(item_name);

-- ============================================================
-- 21. 钥匙奖励表（all.json keyRewards）
-- ============================================================
CREATE TABLE IF NOT EXISTS key_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name        TEXT NOT NULL,
    rotation        TEXT DEFAULT '',
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_keyrewards_key ON key_rewards(key_name);

-- ============================================================
-- 22. 集团奖励表（all.json syndicates）
-- ============================================================
CREATE TABLE IF NOT EXISTS syndicate_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    syndicate_name  TEXT NOT NULL,
    rotation        TEXT DEFAULT '',
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_syndicate_name ON syndicate_rewards(syndicate_name);
CREATE INDEX IF NOT EXISTS idx_syndicate_item ON syndicate_rewards(item_name);

-- ============================================================
-- 23. 游戏术语翻译表（dict.en/zh.json）
-- ============================================================
CREATE TABLE IF NOT EXISTS game_translations (
    key             TEXT PRIMARY KEY,
    en              TEXT NOT NULL,
    zh              TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    source          TEXT DEFAULT 'public-export-plus'
);

CREATE INDEX IF NOT EXISTS idx_gametrans_category ON game_translations(category);
CREATE INDEX IF NOT EXISTS idx_gametrans_en ON game_translations(en);
CREATE INDEX IF NOT EXISTS idx_gametrans_zh ON game_translations(zh);

-- ============================================================
-- 24. 市场物品映射表
-- ============================================================
CREATE TABLE IF NOT EXISTS market_items (
    id              INTEGER PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    en_name         TEXT NOT NULL,
    zh_name         TEXT DEFAULT '',
    item_unique     TEXT DEFAULT '',
    item_type       TEXT DEFAULT '',
    is_tradable     INTEGER DEFAULT 0,
    is_prime        INTEGER DEFAULT 0,
    zh_pinyin       TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_mktitems_slug ON market_items(slug);
CREATE INDEX IF NOT EXISTS idx_mktitems_en ON market_items(en_name);
CREATE INDEX IF NOT EXISTS idx_mktitems_zh ON market_items(zh_name);
CREATE INDEX IF NOT EXISTS idx_mktitems_unique ON market_items(item_unique);

-- ============================================================
-- 25. 元数据表
-- ============================================================
CREATE TABLE IF NOT EXISTS db_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
"""


# ============================================================
# 类型专属属性提取
# ============================================================

# 通用字段（已在 items 主表中），不放入 attrs
_COMMON_KEYS = frozenset({
    'uniqueName', 'name', 'type', 'category', 'tradable', 'masterable',
    'description', 'imageName', 'excludeFromCodex', 'showInInventory',
    'buildPrice', 'buildTime', 'skipBuildTimePrice', 'buildQuantity',
    'consumeOnBuild', 'marketCost', 'bpCost', 'introduced', 'releaseDate',
    'wikiaUrl', 'wikiAvailable', 'wikiaThumbnail',
    # 子表单独处理
    'abilities', 'attacks', 'components', 'drops', 'patchlogs',
    # 翻译相关
    'i18n', 'versions',
})

# 不存入 attrs 的列表/嵌套字段（已单独建表或无价值）
_SKIP_KEYS = frozenset({
    'abilities', 'attacks', 'components', 'drops', 'patchlogs',
    'i18n', 'versions', 'wikiaThumbnail',
})


def _safe_str(val, default='') -> str:
    """安全转换为字符串，dict/list 转 JSON，None 返回 default。"""
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _safe_int(val) -> Optional[int]:
    """安全转换为整数，非数值返回 None。"""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    """安全转换为浮点数，非数值返回 None。"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_type_attrs(item: dict) -> dict:
    """从物品对象中提取类型专属属性（排除通用字段和子表字段）。"""
    attrs = {}
    for k, v in item.items():
        if k in _COMMON_KEYS or k in _SKIP_KEYS:
            continue
        # 跳过 None 值
        if v is None:
            continue
        attrs[k] = v
    return attrs


# ============================================================
# 名称 → uniqueName 映射构建
# ============================================================

def _build_name_map(items_data: list) -> dict:
    """构建 name → uniqueName 映射，用于关联掉落数据。"""
    name_map = {}
    for item in items_data:
        name = item.get('name', '')
        unique = item.get('uniqueName', '')
        if name and unique:
            # 同名物品取第一个（通常唯一）
            if name not in name_map:
                name_map[name] = unique
    return name_map


# ============================================================
# 构建函数
# ============================================================

def build(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    skip_wm: bool = False,
    close_connections_fn: Optional[Callable] = None,
) -> dict:
    """
    构建完整的 warframe.db 数据库。

    Args:
        log_callback: 日志回调 (message)
        progress_callback: 进度回调 (step, current, total)
        skip_wm: 是否跳过 WM API 拉取

    Returns:
        统计信息字典
    """
    stats = {}
    start_time = time.time()

    def _log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    def _progress(step: str, cur: int = 0, total: int = 0):
        if progress_callback:
            progress_callback(step, cur, total)

    # ── 构建到临时文件（避免锁定正在使用的 warframe.db） ──
    import os as _os
    _TMP_DB = DB_PATH.with_suffix('.db.new')

    # 清理上次可能残留的临时文件
    if _TMP_DB.exists():
        try:
            _TMP_DB.unlink()
        except OSError:
            pass

    conn = sqlite3.connect(str(_TMP_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    # ── 创建 Schema ──
    _log("创建数据库表结构...")
    cur.executescript(SCHEMA_SQL)
    conn.commit()

    # ── 名称映射 ──
    name_map = {}
    # ── 遗物 vaulted 映射: (tier, relicName) → vaulted ──
    relic_vaulted_map = {}

    # ================================================================
    # Step 1: 解析 All.json
    # ================================================================
    _log("[1/6] 解析 All.json...")
    if ALL_JSON.exists():
        with open(ALL_JSON, 'r', encoding='utf-8') as f:
            all_items = json.load(f)
        name_map = _build_name_map(all_items)
        _log(f"  加载 {len(all_items)} 条物品数据")

        # 从 All.json 中提取遗物 vaulted 映射
        for item in all_items:
            if item.get('category') == 'Relics' and 'vaulted' in item:
                # name 格式: "Axi A1 Intact" → tier="Axi", relicName="A1", state="Intact"
                parts = item.get('name', '').rsplit(' ', 2)
                if len(parts) >= 3:
                    tier, rname, state = parts[0], parts[1], parts[2]
                    key = (tier, rname)
                    # 只在未设置或当前为 False 时更新（任一 state 为 False 即出库）
                    if key not in relic_vaulted_map or not item['vaulted']:
                        relic_vaulted_map[key] = 1 if item['vaulted'] else 0
        _log(f"  遗物 vaulted 映射: {len(relic_vaulted_map)} 个遗物, 入库={sum(1 for v in relic_vaulted_map.values() if v)}")

        item_rows = []
        attr_rows = []
        ability_rows = []
        attack_rows = []
        component_rows = []
        drop_rows = []
        patchlog_rows = []

        for item in all_items:
            unique = item.get('uniqueName', '')
            if not unique:
                continue

            # ── items 主表 ──
            is_prime = 1 if item.get('isPrime') or 'Prime' in item.get('name', '') else 0
            item_rows.append((
                unique,
                _safe_str(item.get('name', '')),
                '',  # zh_name 稍后回填
                _safe_str(item.get('type', '')),
                _safe_str(item.get('category', '')),
                1 if item.get('tradable') else 0,
                1 if item.get('masterable') else 0,
                is_prime,
                _safe_str(item.get('description', '')),
                '',  # description_zh 稍后回填
                _safe_str(item.get('imageName', '')),
                1 if item.get('excludeFromCodex') else 0,
                1 if item.get('showInInventory', True) else 0,
                _safe_int(item.get('buildPrice')),
                _safe_int(item.get('buildTime')),
                _safe_int(item.get('skipBuildTimePrice')),
                _safe_int(item.get('buildQuantity', 1)),
                1 if item.get('consumeOnBuild', True) else 0,
                _safe_int(item.get('marketCost')),
                _safe_int(item.get('bpCost')),
                _safe_str(item.get('introduced', '')),
                _safe_str(item.get('releaseDate', '')),
                _safe_str(item.get('wikiaUrl', '')),
                1 if item.get('wikiAvailable') else 0,
            ))

            # ── item_type_attrs ──
            attrs = _extract_type_attrs(item)
            if attrs:
                attr_rows.append((
                    unique,
                    item.get('type', ''),
                    json.dumps(attrs, ensure_ascii=False),
                ))

            # ── abilities ──
            for idx, ab in enumerate(item.get('abilities', [])):
                ability_rows.append((
                    unique,
                    idx,
                    _safe_str(ab.get('uniqueName', '')),
                    _safe_str(ab.get('name', '')),
                    _safe_str(ab.get('description', '')),
                    _safe_str(ab.get('imageName', '')),
                ))

            # ── attacks ──
            for idx, atk in enumerate(item.get('attacks', [])):
                pellet = atk.get('pellet', {})
                attack_rows.append((
                    unique,
                    idx,
                    _safe_str(atk.get('name', '')),
                    _safe_float(atk.get('crit_chance', 0)) or 0,
                    _safe_float(atk.get('crit_mult', 0)) or 0,
                    _safe_float(atk.get('status_chance', 0)) or 0,
                    _safe_str(atk.get('shot_type', '')),
                    _safe_float(atk.get('speed', 0)) or 0,
                    _safe_float(atk.get('charge_time', 0)) or 0,
                    json.dumps(atk.get('damage', {}), ensure_ascii=False) if atk.get('damage') else '',
                    _safe_int(pellet.get('count', 1)) if pellet else 1,
                ))

            # ── components ──
            for comp in item.get('components', []):
                component_rows.append((
                    unique,
                    _safe_str(comp.get('name', '')),
                    _safe_str(comp.get('uniqueName', '')),
                    _safe_int(comp.get('itemCount', 1)) or 1,
                    1 if comp.get('tradable') else 0,
                    _safe_str(comp.get('imageName', '')),
                ))

            # ── drops ──
            for drop in item.get('drops', []):
                drop_rows.append((
                    unique,
                    _safe_str(drop.get('type', '')),
                    _safe_str(drop.get('location', '')),
                    _safe_str(drop.get('rarity', '')),
                    _safe_float(drop.get('chance', 0)) or 0,
                ))

            # ── patchlogs ──
            for pl in item.get('patchlogs', []):
                patchlog_rows.append((
                    unique,
                    _safe_str(pl.get('name', '')),
                    _safe_str(pl.get('date', '')),
                    _safe_str(pl.get('url', '')),
                    _safe_str(pl.get('additions', '')),
                    _safe_str(pl.get('changes', '')),
                    _safe_str(pl.get('fixes', '')),
                ))

        # 批量写入
        cur.executemany("""INSERT OR IGNORE INTO items (
            unique_name, name, zh_name, type, category, tradable, masterable, is_prime,
            description, description_zh, image_name, exclude_from_codex, show_in_inventory,
            build_price, build_time, skip_build_time_price, build_quantity, consume_on_build,
            market_cost, bp_cost, introduced, release_date, wikia_url, wiki_available
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", item_rows)

        cur.executemany("INSERT OR IGNORE INTO item_type_attrs (unique_name, type, attrs) VALUES (?,?,?)", attr_rows)
        cur.executemany("INSERT OR IGNORE INTO item_abilities (unique_name, ability_index, ability_unique, name, description, image_name) VALUES (?,?,?,?,?,?)", ability_rows)
        cur.executemany("INSERT OR IGNORE INTO item_attacks (unique_name, attack_index, attack_name, crit_chance, crit_mult, status_chance, shot_type, speed, charge_time, damage_json, pellet_count) VALUES (?,?,?,?,?,?,?,?,?,?,?)", attack_rows)
        cur.executemany("INSERT OR IGNORE INTO item_components (parent_name, component_name, component_unique, item_count, tradable, image_name) VALUES (?,?,?,?,?,?)", component_rows)
        cur.executemany("INSERT OR IGNORE INTO item_drops (unique_name, drop_type, location, rarity, chance) VALUES (?,?,?,?,?)", drop_rows)
        cur.executemany("INSERT OR IGNORE INTO item_patchlogs (unique_name, patch_name, patch_date, patch_url, additions, changes, fixes) VALUES (?,?,?,?,?,?,?)", patchlog_rows)

        conn.commit()
        stats['items'] = len(item_rows)
        stats['type_attrs'] = len(attr_rows)
        stats['abilities'] = len(ability_rows)
        stats['attacks'] = len(attack_rows)
        stats['components'] = len(component_rows)
        stats['drops'] = len(drop_rows)
        stats['patchlogs'] = len(patchlog_rows)
        _log(f"  items={len(item_rows)}, attrs={len(attr_rows)}, abilities={len(ability_rows)}, attacks={len(attack_rows)}")
        _log(f"  components={len(component_rows)}, drops={len(drop_rows)}, patchlogs={len(patchlog_rows)}")
    else:
        _log(f"  [!] All.json 不存在: {ALL_JSON}")

    # ================================================================
    # Step 2: 解析 i18n.json → item_translations + 回填 zh_name
    # ================================================================
    _log("[2/6] 解析 i18n.json...")
    if I18N_JSON.exists():
        with open(I18N_JSON, 'r', encoding='utf-8') as f:
            i18n_data = json.load(f)
        _log(f"  加载 {len(i18n_data)} 条翻译数据")

        trans_rows = []
        zh_updates = []

        for unique_name, translations in i18n_data.items():
            if not isinstance(translations, dict):
                continue
            for lang, texts in translations.items():
                if not isinstance(texts, dict):
                    continue
                trans_rows.append((
                    unique_name,
                    lang,
                    _safe_str(texts.get('name', '')),
                    _safe_str(texts.get('description', '')),
                ))
                # 提取中文翻译回填
                if lang == 'zh':
                    zh_name = _safe_str(texts.get('name', ''))
                    zh_desc = _safe_str(texts.get('description', ''))
                    if zh_name or zh_desc:
                        zh_updates.append((zh_name, zh_desc, unique_name))

        cur.executemany("INSERT OR IGNORE INTO item_translations (unique_name, lang, name, description) VALUES (?,?,?,?)", trans_rows)

        # 回填 items 表的 zh_name 和 description_zh
        cur.executemany("UPDATE items SET zh_name=?, description_zh=? WHERE unique_name=? AND (zh_name='' OR zh_name IS NULL)", zh_updates)

        conn.commit()
        stats['translations'] = len(trans_rows)
        stats['zh_backfilled'] = len([u for u in zh_updates if u[0]])  # 有中文名的
        _log(f"  translations={len(trans_rows)}, zh_backfilled={stats['zh_backfilled']}")

        # ── 为 items 表生成中文拼音 ──
        _log("  生成 items.zh_pinyin ...")
        py_rows = conn.execute(
            "SELECT unique_name, zh_name FROM items WHERE zh_name IS NOT NULL AND zh_name != ''"
        ).fetchall()
        py_updates = []
        for row in py_rows:
            py_str = ''.join(lazy_pinyin(row[1], style=Style.NORMAL))
            if py_str:
                py_updates.append((py_str.lower(), row[0]))
        cur.executemany("UPDATE items SET zh_pinyin=? WHERE unique_name=?", py_updates)
        conn.commit()
        stats['pinyin_generated'] = len(py_updates)
        _log(f"  pinyin={len(py_updates)}")
    else:
        _log(f"  [!] i18n.json 不存在: {I18N_JSON}")

    # ================================================================
    # Step 3: 解析 all.json（掉落数据）
    # ================================================================
    _log("[3/6] 解析 all.json (掉落数据)...")
    if DROP_DATA_JSON.exists():
        with open(DROP_DATA_JSON, 'r', encoding='utf-8') as f:
            drop_data = json.load(f)

        # ── 3a: relics ──
        relic_rows = []
        reward_rows = []
        relic_id_map = {}  # (tier, name, state) → id

        for relic in drop_data.get('relics', []):
            tier = relic.get('tier', '')
            rname = relic.get('relicName', '')
            state = relic.get('state', '')
            did = relic.get('_id', '')
            vaulted = relic_vaulted_map.get((tier, rname), 0)

            cur.execute("INSERT OR IGNORE INTO relics (tier, relic_name, state, vaulted, drop_data_id) VALUES (?,?,?,?,?)",
                        (tier, rname, state, vaulted, did))
            # 获取自增ID
            row = cur.execute("SELECT id FROM relics WHERE tier=? AND relic_name=? AND state=?",
                              (tier, rname, state)).fetchone()
            if row:
                relic_id = row[0]
                relic_id_map[(tier, rname, state)] = relic_id

                for rw in relic.get('rewards', []):
                    item_name = rw.get('itemName', '')
                    item_unique = name_map.get(item_name, '')
                    wm_url = ''
                    # 尝试从 All.json Relic 的 rewards 中获取 warframeMarket 信息
                    reward_rows.append((
                        relic_id,
                        item_name,
                        item_unique,
                        rw.get('rarity', ''),
                        rw.get('chance', 0),
                        rw.get('_id', ''),
                        wm_url,
                    ))

        cur.executemany("""INSERT OR IGNORE INTO relic_rewards
            (relic_id, item_name, item_unique, rarity, chance, drop_data_id, wm_url_name)
            VALUES (?,?,?,?,?,?,?)""", reward_rows)
        conn.commit()
        stats['relics'] = len(relic_id_map)
        stats['relic_rewards'] = len(reward_rows)
        _log(f"  relics={stats['relics']}, relic_rewards={stats['relic_rewards']}")

        # ── 3b: missionRewards ──
        planet_rows = []
        node_rows = []
        mreward_rows = []
        planet_id_map = {}
        node_id_map = {}

        for planet_name, nodes in drop_data.get('missionRewards', {}).items():
            cur.execute("INSERT OR IGNORE INTO planets (name) VALUES (?)", (planet_name,))
            row = cur.execute("SELECT id FROM planets WHERE name=?", (planet_name,)).fetchone()
            planet_id = row[0]
            planet_id_map[planet_name] = planet_id

            for node_name, node_data in nodes.items():
                game_mode = node_data.get('gameMode', '') if isinstance(node_data, dict) else ''
                is_event = 1 if (node_data.get('isEvent', False) if isinstance(node_data, dict) else False) else 0

                cur.execute("INSERT OR IGNORE INTO mission_nodes (planet_id, node_name, game_mode, is_event) VALUES (?,?,?,?)",
                            (planet_id, node_name, game_mode, is_event))
                row = cur.execute("SELECT id FROM mission_nodes WHERE planet_id=? AND node_name=?",
                                  (planet_id, node_name)).fetchone()
                node_id = row[0]
                node_id_map[(planet_name, node_name)] = node_id

                rewards = node_data.get('rewards', {}) if isinstance(node_data, dict) else {}
                if isinstance(rewards, dict):
                    # 轮换任务：A/B/C
                    for rotation, rlist in rewards.items():
                        if isinstance(rlist, list):
                            for r in rlist:
                                iname = r.get('itemName', '')
                                mreward_rows.append((
                                    node_id,
                                    rotation,
                                    iname,
                                    name_map.get(iname, ''),
                                    r.get('rarity', ''),
                                    r.get('chance', 0),
                                    r.get('_id', ''),
                                ))
                elif isinstance(rewards, list):
                    # 非轮换任务
                    for r in rewards:
                        iname = r.get('itemName', '')
                        mreward_rows.append((
                            node_id,
                            '',
                            iname,
                            name_map.get(iname, ''),
                            r.get('rarity', ''),
                            r.get('chance', 0),
                            r.get('_id', ''),
                        ))

        cur.executemany("""INSERT OR IGNORE INTO mission_rewards
            (node_id, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", mreward_rows)
        conn.commit()
        stats['planets'] = len(planet_id_map)
        stats['mission_nodes'] = len(node_id_map)
        stats['mission_rewards'] = len(mreward_rows)
        _log(f"  planets={stats['planets']}, nodes={stats['mission_nodes']}, rewards={stats['mission_rewards']}")

        # ── 3c: modLocations ──
        mod_drop_rows = []
        for ml in drop_data.get('modLocations', []):
            mod_name = ml.get('modName', '')
            for enemy in ml.get('enemies', []):
                mod_drop_rows.append((
                    mod_name,
                    name_map.get(mod_name, ''),
                    enemy.get('enemyName', ''),
                    enemy.get('enemyModDropChance', 0),
                    enemy.get('rarity', ''),
                    enemy.get('chance', 0),
                    enemy.get('_id', ''),
                ))
        cur.executemany("""INSERT OR IGNORE INTO mod_drops
            (mod_name, mod_unique, enemy_name, enemy_mod_drop_chance, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", mod_drop_rows)
        stats['mod_drops'] = len(mod_drop_rows)
        _log(f"  mod_drops={stats['mod_drops']}")

        # ── 3d: enemyModTables ──
        emod_rows = []
        for emt in drop_data.get('enemyModTables', []):
            enemy_name = emt.get('enemyName', '')
            # 兼容两种拼写
            drop_chance = emt.get('enemyModDropChance') or emt.get('ememyModDropChance') or 0
            try:
                drop_chance = float(drop_chance)
            except (ValueError, TypeError):
                drop_chance = 0
            for mod in emt.get('mods', []):
                mname = mod.get('modName', '')
                emod_rows.append((
                    enemy_name,
                    drop_chance,
                    mname,
                    name_map.get(mname, ''),
                    mod.get('rarity', ''),
                    mod.get('chance', 0),
                    mod.get('_id', ''),
                ))
        cur.executemany("""INSERT OR IGNORE INTO enemy_mod_tables
            (enemy_name, enemy_mod_drop_chance, mod_name, mod_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", emod_rows)
        stats['enemy_mod_tables'] = len(emod_rows)
        _log(f"  enemy_mod_tables={stats['enemy_mod_tables']}")

        # ── 3e: blueprintLocations ──
        bp_drop_rows = []
        for bl in drop_data.get('blueprintLocations', []):
            bp_name = bl.get('blueprintName', '')
            for enemy in bl.get('enemies', []):
                bp_drop_rows.append((
                    bp_name,
                    name_map.get(bp_name, ''),
                    enemy.get('enemyName', ''),
                    enemy.get('enemyBlueprintDropChance', 0),
                    enemy.get('rarity', ''),
                    enemy.get('chance', 0),
                    enemy.get('_id', ''),
                ))
        cur.executemany("""INSERT OR IGNORE INTO blueprint_drops
            (blueprint_name, blueprint_unique, enemy_name, enemy_bp_drop_chance, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", bp_drop_rows)
        stats['blueprint_drops'] = len(bp_drop_rows)
        _log(f"  blueprint_drops={stats['blueprint_drops']}")

        # ── 3f: enemyBlueprintTables ──
        ebp_rows = []
        for ebt in drop_data.get('enemyBlueprintTables', []):
            enemy_name = ebt.get('enemyName', '')
            drop_chance = ebt.get('enemyBlueprintDropChance') or ebt.get('ememyBlueprintDropChance') or 0
            try:
                drop_chance = float(drop_chance)
            except (ValueError, TypeError):
                drop_chance = 0
            # 实际数据中字段是 items 而非 blueprints，字段名是 itemName 而非 blueprintName
            for bp in ebt.get('items', ebt.get('blueprints', [])):
                bname = bp.get('itemName', bp.get('blueprintName', ''))
                ebp_rows.append((
                    enemy_name,
                    drop_chance,
                    bname,
                    name_map.get(bname, ''),
                    bp.get('rarity', ''),
                    bp.get('chance', 0),
                    bp.get('_id', ''),
                ))
        cur.executemany("""INSERT OR IGNORE INTO enemy_bp_tables
            (enemy_name, enemy_bp_drop_chance, blueprint_name, blueprint_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", ebp_rows)
        stats['enemy_bp_tables'] = len(ebp_rows)
        _log(f"  enemy_bp_tables={stats['enemy_bp_tables']}")

        # ── 3g: sortieRewards ──
        sortie_rows = []
        for sr in drop_data.get('sortieRewards', []):
            iname = sr.get('itemName', '')
            sortie_rows.append((
                iname,
                name_map.get(iname, ''),
                sr.get('rarity', ''),
                sr.get('chance', 0),
                sr.get('_id', ''),
            ))
        cur.executemany("""INSERT OR IGNORE INTO sortie_rewards
            (item_name, item_unique, rarity, chance, drop_data_id) VALUES (?,?,?,?,?)""", sortie_rows)
        stats['sortie_rewards'] = len(sortie_rows)
        _log(f"  sortie_rewards={stats['sortie_rewards']}")

        # ── 3h: 赏金奖励（6 个来源） ──
        bounty_sources = {
            'cetusBountyRewards': 'cetus',
            'solarisBountyRewards': 'solaris',
            'deimosRewards': 'deimos',
            'zarimanRewards': 'zariman',
            'entratiLabRewards': 'entrati_lab',
            'hexRewards': 'hex',
        }
        bounty_rows = []
        for json_key, source_name in bounty_sources.items():
            for br in drop_data.get(json_key, []):
                bounty_level = br.get('bountyLevel', '')
                rewards = br.get('rewards', {})
                if isinstance(rewards, dict):
                    # 轮换结构 A/B/C
                    for rotation, rlist in rewards.items():
                        if isinstance(rlist, list):
                            for r in rlist:
                                if not isinstance(r, dict):
                                    continue
                                iname = r.get('itemName', '')
                                bounty_rows.append((
                                    source_name,
                                    bounty_level,
                                    rotation,
                                    iname,
                                    name_map.get(iname, ''),
                                    r.get('rarity', ''),
                                    r.get('chance', 0),
                                    r.get('_id', ''),
                                ))
                elif isinstance(rewards, list):
                    for r in rewards:
                        if not isinstance(r, dict):
                            continue
                        iname = r.get('itemName', '')
                        bounty_rows.append((
                            source_name,
                            bounty_level,
                            '',
                            iname,
                            name_map.get(iname, ''),
                            r.get('rarity', ''),
                            r.get('chance', 0),
                            r.get('_id', ''),
                        ))
        cur.executemany("""INSERT OR IGNORE INTO bounty_rewards
            (source, bounty_level, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?,?)""", bounty_rows)
        stats['bounty_rewards'] = len(bounty_rows)
        _log(f"  bounty_rewards={stats['bounty_rewards']}")

        # ── 3i: transientRewards ──
        trans_rows = []
        for tr in drop_data.get('transientRewards', []):
            obj_name = tr.get('objectiveName', '')
            for r in tr.get('rewards', []):
                iname = r.get('itemName', '')
                trans_rows.append((
                    obj_name,
                    r.get('rotation', ''),
                    iname,
                    name_map.get(iname, ''),
                    r.get('rarity', ''),
                    r.get('chance', 0),
                    r.get('_id', ''),
                ))
        cur.executemany("""INSERT OR IGNORE INTO transient_rewards
            (objective_name, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", trans_rows)
        stats['transient_rewards'] = len(trans_rows)
        _log(f"  transient_rewards={stats['transient_rewards']}")

        # ── 3j: keyRewards ──
        key_rows = []
        for kr in drop_data.get('keyRewards', []):
            key_name = kr.get('keyName', '')
            for r in kr.get('rewards', []):
                if isinstance(r, str):
                    key_rows.append((key_name, '', r, name_map.get(r, ''), '', 0, ''))
                    continue
                iname = r.get('itemName', '')
                key_rows.append((
                    key_name,
                    r.get('rotation', ''),
                    iname,
                    name_map.get(iname, ''),
                    r.get('rarity', ''),
                    r.get('chance', 0),
                    r.get('_id', ''),
                ))
        cur.executemany("""INSERT OR IGNORE INTO key_rewards
            (key_name, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", key_rows)
        stats['key_rewards'] = len(key_rows)
        _log(f"  key_rewards={stats['key_rewards']}")

        # ── 3k: syndicates ──
        synd_rows = []
        syndicates = drop_data.get('syndicates', {})
        if isinstance(syndicates, dict):
            for syn_name, rewards in syndicates.items():
                if not isinstance(rewards, list):
                    continue
                for r in rewards:
                    if not isinstance(r, dict):
                        continue
                    iname = r.get('item', '')
                    synd_rows.append((
                        syn_name,
                        r.get('place', ''),  # 集团等级
                        iname,
                        name_map.get(iname, ''),
                        r.get('rarity', ''),
                        r.get('chance', 0),
                        r.get('_id', ''),
                    ))
        cur.executemany("""INSERT OR IGNORE INTO syndicate_rewards
            (syndicate_name, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", synd_rows)
        stats['syndicate_rewards'] = len(synd_rows)
        _log(f"  syndicate_rewards={stats['syndicate_rewards']}")

        conn.commit()
    else:
        _log(f"  [!] all.json 不存在: {DROP_DATA_JSON}")

    # ================================================================
    # Step 4: 解析 dict.en/zh.json → game_translations
    # ================================================================
    _log("[4/6] 解析 dict.en/zh.json...")
    en_data = {}
    zh_data = {}

    if DICT_EN_JSON.exists():
        with open(DICT_EN_JSON, 'r', encoding='utf-8') as f:
            en_data = json.load(f)
        _log(f"  dict.en.json: {len(en_data)} 条")
    else:
        _log(f"  [!] dict.en.json 不存在: {DICT_EN_JSON}")

    if DICT_ZH_JSON.exists():
        with open(DICT_ZH_JSON, 'r', encoding='utf-8') as f:
            zh_data = json.load(f)
        _log(f"  dict.zh.json: {len(zh_data)} 条")
    else:
        _log(f"  [!] dict.zh.json 不存在: {DICT_ZH_JSON}")

    if en_data or zh_data:
        all_keys = set(en_data.keys()) | set(zh_data.keys())
        gtrans_rows = []
        for key in all_keys:
            en_val = en_data.get(key, '')
            zh_val = zh_data.get(key, '')
            # 从 key 推断分类
            parts = key.split('/')
            category = parts[2] if len(parts) > 2 else ''
            gtrans_rows.append((key, en_val, zh_val, category, 'public-export-plus'))

        cur.executemany("INSERT OR IGNORE INTO game_translations (key, en, zh, category, source) VALUES (?,?,?,?,?)", gtrans_rows)
        conn.commit()
        stats['game_translations'] = len(gtrans_rows)
        _log(f"  game_translations={stats['game_translations']}")
    else:
        _log("  无翻译数据可导入")

    # ================================================================
    # Step 5: 拉取 WM 物品列表 → market_items
    # ================================================================
    _log("[5/6] 拉取 warframe.market 物品列表...")
    if not skip_wm:
        try:
            req = urllib.request.Request(
                "https://api.warframe.market/v2/items",
                headers={"User-Agent": "WARFRAME-RELIC/1.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                wm_data = json.loads(resp.read().decode('utf-8'))

            wm_items = wm_data.get('payload', {}).get('items', [])
            wm_rows = []
            for wi in wm_items:
                en_name = wi.get('item_name', '')
                slug = wi.get('url_name', '')
                wm_id = wi.get('id', '')
                item_unique = name_map.get(en_name, '')
                wm_rows.append((
                    wm_id,
                    slug,
                    en_name,
                    '',  # zh_name 稍后可从 item_translations 回填
                    item_unique,
                    wi.get('thumb', ''),
                    1 if wi.get('tradable') else 0,
                    1 if 'prime' in en_name.lower() else 0,
                    '',
                ))

            cur.executemany("""INSERT OR IGNORE INTO market_items
                (id, slug, en_name, zh_name, item_unique, item_type, is_tradable, is_prime, zh_pinyin)
                VALUES (?,?,?,?,?,?,?,?,?)""", wm_rows)
            conn.commit()
            stats['market_items'] = len(wm_rows)
            _log(f"  market_items={stats['market_items']}")
        except Exception as e:
            _log(f"  [!] WM API 拉取失败: {e}")
            stats['market_items'] = 0
    else:
        _log("  已跳过 WM API 拉取")
        stats['market_items'] = 0

    # ================================================================
    # Step 6: 写入元数据
    # ================================================================
    _log("[6/6] 写入元数据...")
    elapsed = round(time.time() - start_time, 1)
    meta_rows = [
        ('schema_version', '1'),
        ('build_time', time.strftime('%Y-%m-%d %H:%M:%S')),
        ('build_elapsed_sec', str(elapsed)),
    ]
    cur.executemany("INSERT OR REPLACE INTO db_meta (key, value) VALUES (?,?)", meta_rows)
    conn.commit()

    # ── VACUUM ──
    _log("优化数据库...")
    conn.execute("VACUUM")

    # ── 统计 ──
    _log("\n=== 构建完成 ===")
    for table in ['items', 'item_type_attrs', 'item_abilities', 'item_attacks',
                   'item_components', 'item_drops', 'item_patchlogs', 'item_translations',
                   'relics', 'relic_rewards', 'planets', 'mission_nodes', 'mission_rewards',
                   'mod_drops', 'enemy_mod_tables', 'blueprint_drops', 'enemy_bp_tables',
                   'sortie_rewards', 'bounty_rewards', 'transient_rewards',
                   'key_rewards', 'syndicate_rewards', 'game_translations', 'market_items']:
        row = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        _log(f"  {table}: {row[0]}")

    _log(f"\n耗时: {elapsed}s")
    _log(f"数据库大小: {_TMP_DB.stat().st_size / 1024 / 1024:.1f} MB")

    conn.close()
    stats['elapsed_sec'] = elapsed
    stats['db_size_mb'] = round(_TMP_DB.stat().st_size / 1024 / 1024, 1)

    # ── 关闭应用内缓存的数据库连接（释放文件锁） ──
    if close_connections_fn:
        _log("关闭缓存连接...")
        close_connections_fn()
        import time as _time
        _time.sleep(0.5)

    # ── 替换数据库：copy + delete（Windows 上 copy 覆盖被读锁定的文件可行） ──
    import shutil as _shutil
    _log(f"替换数据库: {DB_PATH.name} ...")
    _shutil.copy2(str(_TMP_DB), str(DB_PATH))
    try:
        _TMP_DB.unlink()
    except OSError:
        pass  # 残留临时文件无影响，下次构建会清理
    _log("数据库已就位 (warframe.db)")

    return stats



# ============================================================
# 独立运行
# ============================================================
if __name__ == "__main__":
    build()
