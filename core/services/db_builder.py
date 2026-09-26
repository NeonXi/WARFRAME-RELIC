"""
[L-Service] 统一数据库构建模块（新版本）

从所有 JSON 源文件构建单一 warframe.db 数据库。
从 data/build_warframe_db.py 迁移而来。

数据源:
  - external/warframe-items_sparse/data/json/*.json → 全物品数据
    (上游 2025 年重构:旧 All.json 已拆分为 26 个分类文件,运行时聚合)
  - external/warframe-items_sparse/data/json/i18n.json  → 物品多语言翻译
    (上游原文件为 data/json/i18n/zh.json,拉取时重命名)
  - external/warframe-drop-data_sparse/data/all.json    → 掉落数据（DE 官方）
  - external/warframe-i18n_sparse/dict.en.json          → 游戏术语英文
  - external/warframe-i18n_sparse/dict.zh.json          → 游戏术语中文

输出: data/warframe.db

## AI 硬约束 — 修改本文件前必读
归属层:    [L-Service] (core/services/)
允许依赖:  Python 标准库 + data/* + core.hotkey_config 等纯模块
禁止依赖:  PySide6 / QtWidgets / QtGui / QtCore(Signal 除外)
           core.widgets/* / core.pages/* / core.recognizers/*
必读规范:  .trae/rules/开发规范.md §6.2

本文件相关红线:
- 禁止 import PySide6 → Service 是纯逻辑,不能碰 UI
- 禁止返回 Qt 对象 → 只能返回 dict / list / str / int / bool
- 禁止在 Service 中发信号调用 widget → 状态走 core.state / EventBus
- 禁止未捕获的 IO/网络异常冒泡 → 必须 try/except 降级
- 禁止在 Service 中持有 widget 引用

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.2。
"""

import json
import re
import sqlite3
import shutil
import time
import urllib.request
import urllib.error
from typing import Optional, Callable

try:
    from pypinyin import lazy_pinyin, Style
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False
    lazy_pinyin = None
    Style = None

# ============================================================
# 路径常量(打包/开发环境自适应,见 core.paths)
#   DATA_DIR    → 用户数据目录(db 输出位置,首启复制初始库)
#   EXTERNAL_DIR→ exe旁/项目根 external(仓库克隆位置)
# ============================================================
from core.paths import app_root as _app_root, user_data_dir as _user_data_dir
DATA_DIR = _user_data_dir()
EXTERNAL_DIR = _app_root() / "external"

ITEMS_JSON_DIR = EXTERNAL_DIR / "warframe-items_sparse" / "data" / "json"
I18N_JSON = ITEMS_JSON_DIR / "i18n.json"
DROP_DATA_JSON = EXTERNAL_DIR / "warframe-drop-data_sparse" / "data" / "all.json"
RELICS_JSON = ITEMS_JSON_DIR / "Relics.json"
DICT_EN_JSON = EXTERNAL_DIR / "warframe-i18n_sparse" / "dict.en.json"
DICT_ZH_JSON = EXTERNAL_DIR / "warframe-i18n_sparse" / "dict.zh.json"

# 旧 All.json 的拆分产物(分类文件名即旧 category 字段值)
from core.services.repo_puller import _ITEMS_CATEGORY_FILES

DB_PATH = DATA_DIR / "warframe.db"

# ============================================================
# Schema
# ============================================================
SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS item_type_attrs (
    unique_name     TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    attrs           TEXT NOT NULL,
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_attrs_type ON item_type_attrs(type);

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

CREATE TABLE IF NOT EXISTS item_translations (
    unique_name     TEXT NOT NULL,
    lang            TEXT NOT NULL,
    name            TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    PRIMARY KEY (unique_name, lang),
    FOREIGN KEY (unique_name) REFERENCES items(unique_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_trans_lang ON item_translations(lang);

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

CREATE TABLE IF NOT EXISTS planets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE
);

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

CREATE TABLE IF NOT EXISTS sortie_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name       TEXT NOT NULL,
    item_unique     TEXT DEFAULT '',
    rarity          TEXT DEFAULT '',
    chance          REAL DEFAULT 0,
    drop_data_id    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sortie_item ON sortie_rewards(item_name);

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

CREATE TABLE IF NOT EXISTS prime_parts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    en_name         TEXT NOT NULL UNIQUE,
    unique_name     TEXT DEFAULT '',
    slug            TEXT DEFAULT '',
    zh_name         TEXT DEFAULT '',
    part_type       TEXT DEFAULT '',
    parent_en       TEXT DEFAULT '',
    parent_unique   TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pp_slug ON prime_parts(slug);
CREATE INDEX IF NOT EXISTS idx_pp_zh ON prime_parts(zh_name);
CREATE INDEX IF NOT EXISTS idx_pp_parent ON prime_parts(parent_en);
CREATE INDEX IF NOT EXISTS idx_pp_part_type ON prime_parts(part_type);

CREATE TABLE IF NOT EXISTS db_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
"""


# ============================================================
# 类型专属属性提取
# ============================================================

_COMMON_KEYS = frozenset({
    'uniqueName', 'name', 'type', 'category', 'tradable', 'masterable',
    'description', 'imageName', 'excludeFromCodex', 'showInInventory',
    'buildPrice', 'buildTime', 'skipBuildTimePrice', 'buildQuantity',
    'consumeOnBuild', 'marketCost', 'bpCost', 'introduced', 'releaseDate',
    'wikiaUrl', 'wikiAvailable', 'wikiaThumbnail',
    'abilities', 'attacks', 'components', 'drops', 'patchlogs',
    'i18n', 'versions',
})

_SKIP_KEYS = frozenset({
    'abilities', 'attacks', 'components', 'drops', 'patchlogs',
    'i18n', 'versions', 'wikiaThumbnail',
})


def _safe_str(val, default='') -> str:
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _safe_int(val):
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_type_attrs(item: dict) -> dict:
    attrs = {}
    for k, v in item.items():
        if k in _COMMON_KEYS or k in _SKIP_KEYS:
            continue
        if v is None:
            continue
        attrs[k] = v
    return attrs


def _load_all_items(_log=print) -> list:
    """聚合分类文件,替代已被上游删除的 All.json。

    分类文件中的物品可能缺少 category 字段(类别由所在文件隐含),
    这里按文件名补上,保持与旧 All.json 数据一致。
    """
    all_items: list = []
    loaded_files = 0
    for cat_file in _ITEMS_CATEGORY_FILES:
        path = ITEMS_JSON_DIR / cat_file
        if not path.exists():
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                items = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            _log(f"  [!] 读取 {cat_file} 失败: {e}")
            continue
        category = cat_file[:-5]  # 去掉 .json
        for item in items:
            if isinstance(item, dict) and not item.get('category'):
                item['category'] = category
            all_items.append(item)
        loaded_files += 1
    _log(f"  聚合 {loaded_files}/{len(_ITEMS_CATEGORY_FILES)} 个分类文件")
    return all_items


def _build_name_map(items_data: list) -> dict:
    """构建 name -> uniqueName 映射。"""
    name_map = {}
    for item in items_data:
        name = item.get('name', '')
        unique = item.get('uniqueName', '')
        if name and unique and name not in name_map:
            name_map[name] = unique
    return name_map


def _iter_i18n(i18n_data: dict):
    """把 i18n 数据展开为 (unique_name, lang, {name, description})。

    兼容上游两种格式:
      - 旧多语言 i18n.json: {unique_name: {lang: {name, description}}}
      - 新单语言 i18n/zh.json: {unique_name: {name, description}}
        (文件本身就是中文,lang 固定记为 zh)
    """
    for unique_name, entry in i18n_data.items():
        if not isinstance(entry, dict):
            continue
        if "name" in entry or "description" in entry:
            yield unique_name, "zh", entry
        else:
            for lang, texts in entry.items():
                if isinstance(texts, dict):
                    yield unique_name, lang, texts


def _i18n_lookup(i18n_data: dict, unique_name: str,
                 lang: str = "zh") -> dict:
    """取单物品某语言的 {name, description};结构兼容同 _iter_i18n。"""
    entry = i18n_data.get(unique_name)
    if not isinstance(entry, dict):
        return {}
    if "name" in entry or "description" in entry:
        return entry  # 单语言文件(zh.json),本身即目标语言
    texts = entry.get(lang)
    return texts if isinstance(texts, dict) else {}


def _build_prime_parts(cur, conn, all_items: list, i18n_data: dict):
    """
    构建 prime_parts 表 —— 遗物奖励部件专用表。

    全部按 uniqueName 精确关联,不做字符串猜测:
      - Relics.json 奖励 item: name / uniqueName / warframeMarket.urlName
      - 父物品 components: comp.uniqueName → parent.name(反查归属)
      - i18n(zh.json 单语言或旧多语言): 部件官方译名 / parent 中文

    中文名两条轨道:
      ① 部件 uniqueName 在 i18n 有官方译名 → 直接用;
      ② 否则用「parent 中文 + 部件词中文」组合。
    """

    # ---- 1. 部件类型中文名映射（游戏官方汉化，硬编码常量） ----
    _PART_ZH_MAP = {
        'Blueprint': '蓝图',
        'Barrel': '枪管',
        'Receiver': '枪机',
        'Stock': '枪托',
        'Grip': '握把',
        'Handle': '握柄',
        'Head': '锤头',
        'Blade': '刀刃',
        'Link': '连接器',
        'Chassis': '机体',
        'Neuroptics': '头部神经光元',
        'Systems': '系统',
        'Shell': '外壳',
        'Cabinet': '内核',
        'Harness': '背饰',
        'Collar': '项圈',
        'Brain': '大脑',
        'Carapace': '甲壳',
        # 稀有武器/守护部件
        'Gauntlet': '拳套',
        'Cerebrum': '头部',
        'Lower Limb': '下弓臂',
        'Upper Limb': '上弓臂',
        'String': '弓弦',
        'Hilt': '握柄',
        'Guard': '护手',
        'Blades': '爪刃',
        'Boot': '靴子',
        'Chain': '链条',
        'Disc': '圆盘',
        'Ornament': '饰物',
        'Pouch': '镖袋',
        'Stars': '星镖',
        'Wings': '机翼',
        'Buckle': '项圈扣',
        'Band': '项圈带',
    }

    # ---- 2. uniqueName 精确索引(不依赖 comp.name,规避上游命名变体) ----
    _uniq_to_parent = {}  # 部件 uniqueName → parent 英文名
    _name_to_uniq = {}    # parent 英文名 → parent uniqueName
    for item in all_items:
        pname = item.get('name', '')
        puniq = item.get('uniqueName', '')
        if pname and puniq and pname not in _name_to_uniq:
            _name_to_uniq[pname] = puniq
        if not pname:
            continue
        for comp in item.get('components', []):
            cu = comp.get('uniqueName', '')
            if not cu:
                continue
            if cu not in _uniq_to_parent:
                _uniq_to_parent[cu] = pname
            # 战甲部件桥接:components 中是 XxxComponent,遗物奖励的部件蓝图
            # uniqueName 是 XxxBlueprint(如 ChassisComponent → ChassisBlueprint)
            if cu.endswith('Component'):
                bp_uniq = cu[:-len('Component')] + 'Blueprint'
                if bp_uniq not in _uniq_to_parent:
                    _uniq_to_parent[bp_uniq] = pname

    # ---- 3. parent uniqueName → 中文名(单语言/多语言 i18n 兼容) ----
    _parent_zh = {}
    for uniq in i18n_data.keys():
        d = _i18n_lookup(i18n_data, uniq, "zh")
        n = d.get("name", "")
        if n:
            _parent_zh[uniq] = n

    # 同名物品修正:部分物品有 StoreItems/正常两个 uniqueName,
    # 优先选 i18n 中有中文的那个(如 Forma)
    for name, uniq in list(_name_to_uniq.items()):
        if uniq in _parent_zh:
            continue
        for item in all_items:
            if item.get('name') == name:
                cand = item.get('uniqueName', '')
                if cand and cand in _parent_zh:
                    _name_to_uniq[name] = cand
                    break

    # ---- 4. Relics.json: 收集全部奖励(item 直接带 uniqueName) ----
    with open(RELICS_JSON, 'r', encoding='utf-8') as f:
        relics_data = json.load(f)
    _relic_items = {}  # en_name → {'slug', 'unique'}
    for relic in relics_data:
        for rw in relic.get('rewards', []):
            item_obj = rw.get('item', {})
            name = item_obj.get('name', '')
            if not name or name in _relic_items:
                continue
            _relic_items[name] = {
                'slug': item_obj.get('warframeMarket', {}).get('urlName', ''),
                'unique': item_obj.get('uniqueName', ''),
            }

    # parent 中文名人工修正(i18n 译名与使用习惯不符时)
    _PARENT_ZH_OVERRIDE = {
        'Kavasa Prime Kubrow Collar': '喀婆萨 Prime',
    }

    def _part_phrase(remainder: str) -> str:
        """parent 名之后的英文部件词逐个翻中文并拼接。

        如 'Chassis Blueprint' → '机体蓝图'; 'Lower Limb' → '下弓臂'。
        """
        keys = sorted(_PART_ZH_MAP.keys(), key=len, reverse=True)
        out = []
        r = remainder.strip()
        while r:
            for k in keys:
                if r.startswith(k):
                    out.append(_PART_ZH_MAP[k])
                    r = r[len(k):].strip()
                    break
            else:
                break
        return ''.join(out)
    # ---- 5. 组装数据并写入 ----
    cur.execute("DELETE FROM prime_parts")
    pp_rows = []
    for en_name in sorted(_relic_items.keys()):
        info = _relic_items[en_name]
        unique_name = info['unique']
        slug = info['slug']

        # parent 归属:直接用部件 uniqueName 反查 components(精确)
        parent_en = _uniq_to_parent.get(unique_name, '')
        parent_unique = _name_to_uniq.get(parent_en, '')

        # 部件词原文:en_name 中 parent 名之后的部分
        # find 兼容数量前缀(如 '2X Forma Blueprint')
        remainder = ''
        if parent_en:
            pos = en_name.find(parent_en)
            if pos >= 0:
                remainder = en_name[pos + len(parent_en):].strip()
        part_type = remainder

        zh_name = ''
        # 轨道①: parent 中文 + 部件词中文(组合完整名,如「迅发电浆炮 Prime 枪管」)
        # 前提:en_name 必须确实包含 parent 名,排除「材料被引用进其它物品
        # components」的误归属(如 Kuva 出现在破损珽杖材料中)
        if parent_en and en_name.find(parent_en) >= 0:
            base_full = (_PARENT_ZH_OVERRIDE.get(parent_en)
                         or _parent_zh.get(parent_unique, ''))
            if base_full:
                base = re.sub(r'\s*Prime\s*$', '', base_full).rstrip()
                phrase = _part_phrase(remainder or 'Blueprint')
                if base and phrase:
                    # 仅当物品英文名含 Prime 时才补 Prime(Forma/Kuva 等非 Prime 不加)
                    if 'Prime' in en_name and 'Prime' not in base:
                        zh_name = f"{base} Prime {phrase}"
                    else:
                        zh_name = f"{base} {phrase}"

        # 轨道②: 组合失败(无 parent/无 parent 中文)时,
        # 用部件 uniqueName 自身的官方译名(赤毒/阿耶坦/安魂密语等独立物品)
        if not zh_name:
            own = _i18n_lookup(i18n_data, unique_name, 'zh')
            if own.get('name'):
                zh_name = own['name']

        pp_rows.append((en_name, unique_name, slug, zh_name, part_type,
                        parent_en, parent_unique))

    cur.executemany(
        "INSERT INTO prime_parts "
        "(en_name, unique_name, slug, zh_name, part_type, parent_en, parent_unique) "
        "VALUES (?,?,?,?,?,?,?)",
        pp_rows
    )
    conn.commit()

    # 统计日志
    total = len(pp_rows)
    has_slug = sum(1 for r in pp_rows if r[2])
    has_zh = sum(1 for r in pp_rows if r[3])
    has_unique = sum(1 for r in pp_rows if r[1])
    has_part = sum(1 for r in pp_rows if r[4])

    # 返回统计供调用方打印（避免在辅助函数中引入日志依赖）
    return {
        'total': total,
        'has_slug': has_slug,
        'has_zh': has_zh,
        'has_unique': has_unique,
        'has_part': has_part,
    }


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
        close_connections_fn: 关闭缓存连接的函数
    Returns:
        统计信息字典
    """
    stats = {}
    start_time = time.time()

    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    def _progress(step: str, cur: int = 0, total: int = 0):
        if progress_callback:
            progress_callback(step, cur, total)

    # ── 构建到临时文件 ──
    _TMP_DB = DB_PATH.with_suffix('.db.new')
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

    name_map = {}
    relic_vaulted_map = {}

    # ================================================================
    # Step 1: 聚合分类物品文件(旧 All.json)
    # ================================================================
    _log("[1/6] 聚合分类物品文件(旧 All.json)...")
    all_items = _load_all_items(_log)
    if all_items:
        name_map = _build_name_map(all_items)
        _log(f"  加载 {len(all_items)} 条物品数据")

        for item in all_items:
            if item.get('category') == 'Relics' and 'vaulted' in item:
                parts = item.get('name', '').rsplit(' ', 2)
                if len(parts) >= 3:
                    tier, rname, state = parts[0], parts[1], parts[2]
                    key = (tier, rname)
                    if key not in relic_vaulted_map or not item['vaulted']:
                        relic_vaulted_map[key] = 1 if item['vaulted'] else 0
        _log(f"  遗物 vaulted 映射: {len(relic_vaulted_map)} 个遗物")

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

            is_prime = 1 if item.get('isPrime') or 'Prime' in item.get('name', '') else 0
            item_rows.append((
                unique, _safe_str(item.get('name', '')), '', _safe_str(item.get('type', '')),
                _safe_str(item.get('category', '')), 1 if item.get('tradable') else 0,
                1 if item.get('masterable') else 0, is_prime,
                _safe_str(item.get('description', '')), '', _safe_str(item.get('imageName', '')),
                1 if item.get('excludeFromCodex') else 0,
                1 if item.get('showInInventory', True) else 0,
                _safe_int(item.get('buildPrice')), _safe_int(item.get('buildTime')),
                _safe_int(item.get('skipBuildTimePrice')),
                _safe_int(item.get('buildQuantity', 1)),
                1 if item.get('consumeOnBuild', True) else 0,
                _safe_int(item.get('marketCost')), _safe_int(item.get('bpCost')),
                _safe_str(item.get('introduced', '')), _safe_str(item.get('releaseDate', '')),
                _safe_str(item.get('wikiaUrl', '')), 1 if item.get('wikiAvailable') else 0,
            ))

            attrs = _extract_type_attrs(item)
            if attrs:
                attr_rows.append((unique, item.get('type', ''), json.dumps(attrs, ensure_ascii=False)))

            for idx, ab in enumerate(item.get('abilities', [])):
                ability_rows.append((unique, idx, _safe_str(ab.get('uniqueName', '')),
                    _safe_str(ab.get('name', '')), _safe_str(ab.get('description', '')),
                    _safe_str(ab.get('imageName', ''))))
            for idx, atk in enumerate(item.get('attacks', [])):
                pellet = atk.get('pellet', {})
                attack_rows.append((unique, idx, _safe_str(atk.get('name', '')),
                    _safe_float(atk.get('crit_chance', 0)) or 0,
                    _safe_float(atk.get('crit_mult', 0)) or 0,
                    _safe_float(atk.get('status_chance', 0)) or 0,
                    _safe_str(atk.get('shot_type', '')), _safe_float(atk.get('speed', 0)) or 0,
                    _safe_float(atk.get('charge_time', 0)) or 0,
                    json.dumps(atk.get('damage', {}), ensure_ascii=False) if atk.get('damage') else '',
                    _safe_int(pellet.get('count', 1)) if pellet else 1))
            for comp in item.get('components', []):
                component_rows.append((unique, _safe_str(comp.get('name', '')),
                    _safe_str(comp.get('uniqueName', '')),
                    _safe_int(comp.get('itemCount', 1)) or 1,
                    1 if comp.get('tradable') else 0, _safe_str(comp.get('imageName', ''))))
            for drop in item.get('drops', []):
                drop_rows.append((unique, _safe_str(drop.get('type', '')),
                    _safe_str(drop.get('location', '')), _safe_str(drop.get('rarity', '')),
                    _safe_float(drop.get('chance', 0)) or 0))
            for pl in item.get('patchlogs', []):
                patchlog_rows.append((unique, _safe_str(pl.get('name', '')),
                    _safe_str(pl.get('date', '')), _safe_str(pl.get('url', '')),
                    _safe_str(pl.get('additions', '')), _safe_str(pl.get('changes', '')),
                    _safe_str(pl.get('fixes', ''))))

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
    else:
        _log("  [!] 未加载到任何分类物品文件,请检查拉取步骤")

    # ================================================================
    # Step 2: i18n.json → 翻译 + 回填中文
    # ================================================================
    _log("[2/6] 解析 i18n.json...")
    if I18N_JSON.exists():
        with open(I18N_JSON, 'r', encoding='utf-8') as f:
            i18n_data = json.load(f)
        _log(f"  加载 {len(i18n_data)} 条翻译数据")

        trans_rows = []
        zh_updates = []

        # _iter_i18n 同时兼容旧多语言和 zh.json 单语言结构
        for unique_name, lang, texts in _iter_i18n(i18n_data):
            trans_rows.append((unique_name, lang,
                _safe_str(texts.get('name', '')), _safe_str(texts.get('description', ''))))
            if lang == 'zh':
                zh_name = _safe_str(texts.get('name', ''))
                zh_desc = _safe_str(texts.get('description', ''))
                if zh_name or zh_desc:
                    zh_updates.append((zh_name, zh_desc, unique_name))

        cur.executemany("INSERT OR IGNORE INTO item_translations (unique_name, lang, name, description) VALUES (?,?,?,?)", trans_rows)
        cur.executemany("UPDATE items SET zh_name=?, description_zh=? WHERE unique_name=? AND (zh_name='' OR zh_name IS NULL)", zh_updates)
        conn.commit()

        stats['translations'] = len(trans_rows)
        stats['zh_backfilled'] = len([u for u in zh_updates if u[0]])
        _log(f"  translations={len(trans_rows)}, zh_backfilled={stats['zh_backfilled']}")

        # 拼音生成
        py_rows = conn.execute(
            "SELECT unique_name, zh_name FROM items WHERE zh_name IS NOT NULL AND zh_name != ''"
        ).fetchall()
        py_updates = []
        if _HAS_PYPINYIN:
            for row in py_rows:
                py_str = ''.join(lazy_pinyin(row[1], style=Style.NORMAL))
                if py_str:
                    py_updates.append((py_str.lower(), row[0]))
        else:
            _log("  [!] pypinyin 未安装，跳过拼音生成")
        cur.executemany("UPDATE items SET zh_pinyin=? WHERE unique_name=?", py_updates)
        conn.commit()
        stats['pinyin_generated'] = len(py_updates)
        _log(f"  pinyin={len(py_updates)}")
    else:
        _log(f"  [!] i18n.json 不存在: {I18N_JSON}")
        i18n_data = {}  # 兜底:保证后续 _build_prime_parts 等引用不 UnboundLocal

    # ================================================================
    # Step 3: 掉落数据 all.json
    # ================================================================
    _log("[3/6] 解析 all.json (掉落数据)...")
    if DROP_DATA_JSON.exists():
        with open(DROP_DATA_JSON, 'r', encoding='utf-8') as f:
            drop_data = json.load(f)

        # 3a: relics — 优先使用 Relics.json（含 uniqueName + warframeMarket.urlName）
        relic_rows = []
        reward_rows = []
        relic_id_map = {}

        # ── 构建「实际可获得遗物」集合 ──
        # 上游 Relics.json 的 vaulted 语义是「不在 Prime 常规轮换池」,
        # 但大量遗物(如 Citrine Prime 批次)仍可通过任务/赏金/瞬时奖励
        # 等途径获得。drop-data 的掉落表是游戏实际数据,以此为出库的
        # 最终依据:凡在常规掉落源中出现的遗物一律标为出库。
        # 例外: 九重天(Railjack)任务的奖励表是 DE 为入库遗物设置的
        # 特殊回归途径——仅在九重天(Skirmish 节点及其 Extra/Caches
        # 变体,含 Veil Proxima 全域)出现的遗物仍认定为入库。
        import re as _re
        _RELIC_NAME_RE = _re.compile(
            r"^(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s+(\S+?)\s+Relic")
        _live_relics = set()      # 常规来源
        _railjack_relics = set()  # 九重天来源

        def _make_scan(target_set):
            def _scan(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == "itemName" and isinstance(v, str):
                            m = _RELIC_NAME_RE.match(v)
                            if m:
                                target_set.add((m.group(1), m.group(2)))
                        else:
                            _scan(v)
                elif isinstance(obj, list):
                    for v in obj:
                        _scan(v)
            return _scan

        _scan_live = _make_scan(_live_relics)
        _scan_rj = _make_scan(_railjack_relics)

        # missionRewards: 区分九重天节点与常规节点
        for _planet, _nodes in drop_data.get("missionRewards", {}).items():
            # Skirmish = 九重天任务模式;其 (Extra)/(Caches) 变体同前缀
            _rj_bases = {
                _n.split(" (")[0]
                for _n, _nd in _nodes.items()
                if _nd.get("gameMode") == "Skirmish"
            }
            for _node, _ndata in _nodes.items():
                if _planet == "Veil Proxima" or _node.split(" (")[0] in _rj_bases:
                    _scan_rj(_ndata)   # 九重天来源单独收集
                else:
                    _scan_live(_ndata)

        # 其他掉落源(赏金/突击/瞬时/钥匙/集团)全部视为常规来源
        for _drop_key in (
            "cetusBountyRewards", "solarisBountyRewards",
            "deimosRewards", "zarimanRewards", "entratiLabRewards",
            "hexRewards", "sortieRewards", "transientRewards",
            "keyRewards", "syndicates",
        ):
            _scan_live(drop_data.get(_drop_key))
        _log(f"  常规途径可获得的遗物: {len(_live_relics)} 种; "
             f"九重天来源: {len(_railjack_relics)} 种")

        # ★ 优先从 Relics.json 构建（数据更丰富：含 item_unique + wm_url_name）
        if RELICS_JSON.exists():
            with open(RELICS_JSON, 'r', encoding='utf-8') as f:
                relics_data = json.load(f)
            _log(f"  使用 Relics.json: {len(relics_data)} 条遗物")

            for relic in relics_data:
                tier = ''
                rname = ''
                state = ''
                # 解析遗物名: "Axi A1 Intact" → tier="Axi", name="A1", state="Intact"
                parts = relic.get('name', '').rsplit(' ', 2)
                if len(parts) >= 3:
                    tier, rname, state = parts[0], parts[1], parts[2]
                elif len(parts) == 2:
                    # 上游内部占位符(如 "Axi Relic"/"Void Relic"),无实际意义,跳过
                    continue
                else:
                    continue

                # 出库判定: 以 drop-data(游戏客户端实时解析的掉落表)为唯一权威
                # 1. 常规掉落源出现 → 出库
                # 2. Requiem(安魂) → 常驻:I/II/III/IV 经赤毒玄骸系统、
                #    Eterna 经瞬时奖励获得,均不在常规掉落表,强制出库
                # 3. 其他一律入库(含: 仅九重天缓存的回归遗物、Vanguard
                #    先锋遗物(活动已结束不可获取)、上游 vaulted 滞后的)
                if (tier, rname) in _live_relics or tier == 'Requiem':
                    vaulted = 0
                else:
                    vaulted = 1
                did = relic.get('uniqueName', '')
                cur.execute("INSERT OR IGNORE INTO relics (tier, relic_name, state, vaulted, drop_data_id) VALUES (?,?,?,?,?)",
                            (tier, rname, state, vaulted, did))
                row = cur.execute("SELECT id FROM relics WHERE tier=? AND relic_name=? AND state=?", (tier, rname, state)).fetchone()
                if not row:
                    continue
                relic_id = row[0]
                relic_id_map[(tier, rname, state)] = relic_id

                for rw in relic.get('rewards', []):
                    item_data = rw.get('item', {})
                    wm_info = item_data.get('warframeMarket', {})
                    reward_rows.append((
                        relic_id,
                        item_data.get('name', ''),           # item_name
                        item_data.get('uniqueName', ''),     # item_unique ★ 填充
                        rw.get('rarity', ''),
                        rw.get('chance', 0),
                        did,                                  # drop_data_id
                        wm_info.get('urlName', '')           # wm_url_name ★ 填充
                    ))
            _log(f"  Relics.json: {len(relic_id_map)} 遗物, {len(reward_rows)} 奖励")
        elif DROP_DATA_JSON.exists():
            # 回退: 使用 drop-data all.json（字段较少，item_unique/wm_url_name 为空）
            _log("  [!] Relics.json 不存在，回退到 drop-data all.json（字段不完整）")
            with open(DROP_DATA_JSON, 'r', encoding='utf-8') as f:
                drop_data = json.load(f)

            for relic in drop_data.get('relics', []):
                tier = relic.get('tier', '')
                rname = relic.get('relicName', '')
                state = relic.get('state', '')
                did = relic.get('_id', '')
                vaulted = relic_vaulted_map.get((tier, rname), 0)
                cur.execute("INSERT OR IGNORE INTO relics (tier, relic_name, state, vaulted, drop_data_id) VALUES (?,?,?,?,?)",
                            (tier, rname, state, vaulted, did))
                row = cur.execute("SELECT id FROM relics WHERE tier=? AND relic_name=? AND state=?", (tier, rname, state)).fetchone()
                if row:
                    relic_id = row[0]
                    relic_id_map[(tier, rname, state)] = relic_id
                    for rw in relic.get('rewards', []):
                        reward_rows.append((relic_id, rw.get('itemName', ''), name_map.get(rw.get('itemName', ''), ''),
                            rw.get('rarity', ''), rw.get('chance', 0), rw.get('_id', ''), ''))

        cur.executemany("""INSERT OR IGNORE INTO relic_rewards
            (relic_id, item_name, item_unique, rarity, chance, drop_data_id, wm_url_name)
            VALUES (?,?,?,?,?,?,?)""", reward_rows)
        conn.commit()
        stats['relics'] = len(relic_id_map)
        stats['relic_rewards'] = len(reward_rows)

        # ★ 3a-补: 跨表关联填充残留空值
        _log("  跨表填充: 补全 item_unique / wm_url_name ...")
        # 用 items 表的 name → unique_name 回填 relic_rewards.item_unique
        filled_unique = cur.execute("""
            UPDATE relic_rewards SET item_unique = (
                SELECT i.unique_name FROM items i
                WHERE i.name = relic_rewards.item_name
                  AND i.unique_name IS NOT NULL AND i.unique_name != ''
            ) WHERE (item_unique IS NULL OR item_unique = '')
              AND EXISTS (
                  SELECT 1 FROM items i WHERE i.name = relic_rewards.item_name
                    AND i.unique_name IS NOT NULL AND i.unique_name != ''
              )
        """).rowcount

        # 用 market_items 的 slug 回填 relic_rewards.wm_url_name（通过 item_unique 关联）
        filled_wm = cur.execute("""
            UPDATE relic_rewards SET wm_url_name = (
                SELECT mi.slug FROM market_items mi
                WHERE mi.item_unique = relic_rewards.item_unique
                  AND mi.slug IS NOT NULL AND mi.slug != ''
            ) WHERE (wm_url_name IS NULL OR wm_url_name = '')
              AND (item_unique IS NOT NULL AND item_unique != '')
              AND EXISTS (
                  SELECT 1 FROM market_items mi WHERE mi.item_unique = relic_rewards.item_unique
                    AND mi.slug IS NOT NULL AND mi.slug != ''
              )
        """).rowcount

        # 二次回填：用 items.name 匹配 market_items.en_name，再填 wm_url_name
        filled_wm2 = cur.execute("""
            UPDATE relic_rewards SET wm_url_name = (
                SELECT mi.slug FROM market_items mi
                WHERE mi.en_name = relic_rewards.item_name
                  AND mi.slug IS NOT NULL AND mi.slug != ''
            ) WHERE (wm_url_name IS NULL OR wm_url_name = '')
              AND EXISTS (
                  SELECT 1 FROM market_items mi WHERE mi.en_name = relic_rewards.item_name
                    AND mi.slug IS NOT NULL AND mi.slug != ''
              )
        """).rowcount

        conn.commit()
        _log(f"  跨表填充: item_unique +{filled_unique}, wm_url_name(关联) +{filled_wm}, wm_url_name(名称) +{filled_wm2}")

        # 3b: missionRewards
        planet_rows = []; node_rows = []; mreward_rows = []
        planet_id_map = {}; node_id_map = {}

        for planet_name, nodes in drop_data.get('missionRewards', {}).items():
            cur.execute("INSERT OR IGNORE INTO planets (name) VALUES (?)", (planet_name,))
            row = cur.execute("SELECT id FROM planets WHERE name=?", (planet_name,)).fetchone()
            pid = row[0]
            planet_id_map[planet_name] = pid
            for node_name, node_data in nodes.items():
                gm = node_data.get('gameMode', '') if isinstance(node_data, dict) else ''
                ie = 1 if (node_data.get('isEvent', False) if isinstance(node_data, dict) else False) else 0
                cur.execute("INSERT OR IGNORE INTO mission_nodes (planet_id, node_name, game_mode, is_event) VALUES (?,?,?,?)",
                            (pid, node_name, gm, ie))
                row = cur.execute("SELECT id FROM mission_nodes WHERE planet_id=? AND node_name=?", (pid, node_name)).fetchone()
                nid = row[0]
                node_id_map[(planet_name, node_name)] = nid
                rewards = node_data.get('rewards', {}) if isinstance(node_data, dict) else {}
                if isinstance(rewards, dict):
                    for rotation, rlist in rewards.items():
                        if isinstance(rlist, list):
                            for r in rlist:
                                mreward_rows.append((nid, rotation, r.get('itemName', ''), name_map.get(r.get('itemName', ''), ''),
                                    r.get('rarity', ''), r.get('chance', 0), r.get('_id', '')))
                elif isinstance(rewards, list):
                    # 非轮换任务
                    for r in rewards:
                        iname = r.get('itemName', '')
                        mreward_rows.append((nid, '', iname, name_map.get(iname, ''),
                            r.get('rarity', ''), r.get('chance', 0), r.get('_id', '')))

        cur.executemany("""INSERT OR IGNORE INTO mission_rewards
            (node_id, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", mreward_rows)
        stats['mission_rewards'] = len(mreward_rows)

        cur.executemany("""INSERT OR IGNORE INTO mission_nodes
            (planet_id, node_name, game_mode, is_event) VALUES (?,?,?,?)""",
            [(planet_id_map[pn], nn, nd.get('gameMode',''), nd.get('isEvent',False) if isinstance(nd, dict) else False)
             for pn, nodes in drop_data.get('missionRewards', {}).items()
             for nn, nd in nodes.items() if isinstance(nd, dict)])
        # ... (简化: 实际逻辑与原版一致，此处省略重复代码以节省篇幅)
        # 完整实现见下方补充的各子步骤

        # 3c-k: 各类掉落表（mod_drops, enemy_mod_tables, blueprint_drops, enemy_bp_tables,
        #         sortie_rewards, bounty_rewards, transient_rewards, key_rewards, syndicates）
        # 这些表的构建逻辑与 data/build_warframe_db.py 完全一致，直接复用

        # modLocations
        mod_drop_rows = [(ml.get('modName',''), name_map.get(ml.get('modName'),''),
            e.get('enemyName',''), e.get('enemyModDropChance',0),
            e.get('rarity',''), e.get('chance',0), e.get('_id',''))
            for ml in drop_data.get('modLocations',[]) for e in ml.get('enemies',[])]
        cur.executemany("""INSERT OR IGNORE INTO mod_drops
            (mod_name, mod_unique, enemy_name, enemy_mod_drop_chance, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", mod_drop_rows)
        stats['mod_drops'] = len(mod_drop_rows)

        # enemyModTables
        emod_rows = []
        for emt in drop_data.get('enemyModTables', []):
            ename = emt.get('enemyName', '')
            dc = emt.get('enemyModDropChance') or emt.get('ememyModDropChance') or 0
            try: dc = float(dc)
            except: dc = 0
            for m in emt.get('mods', []):
                emod_rows.append((ename, dc, m.get('modName',''), name_map.get(m.get('modName'),''),
                    m.get('rarity',''), m.get('chance',0), m.get('_id','')))
        cur.executemany("""INSERT OR IGNORE INTO enemy_mod_tables
            (enemy_name, enemy_mod_drop_chance, mod_name, mod_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", emod_rows)
        stats['enemy_mod_tables'] = len(emod_rows)

        # blueprintLocations
        bp_drop_rows = [(bl.get('blueprintName',''), name_map.get(bl.get('blueprintName'),''),
            e.get('enemyName',''), e.get('enemyBlueprintDropChance',0),
            e.get('rarity',''), e.get('chance',0), e.get('_id',''))
            for bl in drop_data.get('blueprintLocations',[]) for e in bl.get('enemies',[])]
        cur.executemany("""INSERT OR IGNORE INTO blueprint_drops
            (blueprint_name, blueprint_unique, enemy_name, enemy_bp_drop_chance, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", bp_drop_rows)
        stats['blueprint_drops'] = len(bp_drop_rows)

        # enemyBlueprintTables
        ebp_rows = []
        for ebt in drop_data.get('enemyBlueprintTables', []):
            ename = ebt.get('enemyName', '')
            dc = ebt.get('enemyBlueprintDropChance') or ebt.get('ememyBlueprintDropChance') or 0
            try: dc = float(dc)
            except: dc = 0
            for bp in ebt.get('items', ebt.get('blueprints', [])):
                bname = bp.get('itemName', bp.get('blueprintName', ''))
                ebp_rows.append((ename, dc, bname, name_map.get(bname,''),
                    bp.get('rarity',''), bp.get('chance',0), bp.get('_id','')))
        cur.executemany("""INSERT OR IGNORE INTO enemy_bp_tables
            (enemy_name, enemy_bp_drop_chance, blueprint_name, blueprint_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", ebp_rows)
        stats['enemy_bp_tables'] = len(ebp_rows)

        # sortieRewards
        sortie_rows = [(sr.get('itemName',''), name_map.get(sr.get('itemName'),''),
            sr.get('rarity',''), sr.get('chance',0), sr.get('_id',''))
            for sr in drop_data.get('sortieRewards',[])]
        cur.executemany("""INSERT OR IGNORE INTO sortie_rewards
            (item_name, item_unique, rarity, chance, drop_data_id) VALUES (?,?,?,?,?)""", sortie_rows)
        stats['sortie_rewards'] = len(sortie_rows)

        # 赏金奖励
        bounty_sources = {
            'cetusBountyRewards': 'cetus', 'solarisBountyRewards': 'solaris',
            'deimosRewards': 'deimos', 'zarimanRewards': 'zariman',
            'entratiLabRewards': 'entrati_lab', 'hexRewards': 'hex',
        }
        bounty_rows = []
        for jk, src in bounty_sources.items():
            for br in drop_data.get(jk, []):
                blvl = br.get('bountyLevel', '')
                rwds = br.get('rewards', {})
                if isinstance(rwds, dict):
                    for rot, rl in rwds.items():
                        if isinstance(rl, list):
                            for r in rl:
                                if isinstance(r, dict):
                                    bounty_rows.append((src, blvl, rot, r.get('itemName',''),
                                        name_map.get(r.get('itemName'),''), r.get('rarity',''),
                                        r.get('chance',0), r.get('_id','')))
                elif isinstance(rwds, list):
                    for r in rwds:
                        if isinstance(r, dict):
                            bounty_rows.append((src, blvl, '', r.get('itemName',''),
                                name_map.get(r.get('itemName'),''), r.get('rarity',''),
                                r.get('chance',0), r.get('_id','')))
        cur.executemany("""INSERT OR IGNORE INTO bounty_rewards
            (source, bounty_level, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?,?)""", bounty_rows)
        stats['bounty_rewards'] = len(bounty_rows)

        # transientRewards
        trans_rows = [(tr.get('objectiveName',''), r.get('rotation',''), r.get('itemName',''),
            name_map.get(r.get('itemName'),''), r.get('rarity',''), r.get('chance',0), r.get('_id',''))
            for tr in drop_data.get('transientRewards',[]) for r in tr.get('rewards',[])]
        cur.executemany("""INSERT OR IGNORE INTO transient_rewards
            (objective_name, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", trans_rows)
        stats['transient_rewards'] = len(trans_rows)

        # keyRewards
        key_rows = []
        for kr in drop_data.get('keyRewards', []):
            kn = kr.get('keyName', '')
            for r in kr.get('rewards', []):
                if isinstance(r, str):
                    key_rows.append((kn, '', r, name_map.get(r,''), '', 0, ''))
                else:
                    key_rows.append((kn, r.get('rotation',''), r.get('itemName',''),
                        name_map.get(r.get('itemName'),''), r.get('rarity',''),
                        r.get('chance',0), r.get('_id','')))
        cur.executemany("""INSERT OR IGNORE INTO key_rewards
            (key_name, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", key_rows)
        stats['key_rewards'] = len(key_rows)

        # syndicates
        synd_rows = []
        for sn, rwds in drop_data.get('syndicates', {}).items():
            if not isinstance(rwds, list): continue
            for r in rwds:
                if not isinstance(r, dict): continue
                synd_rows.append((sn, r.get('place',''), r.get('item',''),
                    name_map.get(r.get('item'),''), r.get('rarity',''),
                    r.get('chance',0), r.get('_id','')))
        cur.executemany("""INSERT OR IGNORE INTO syndicate_rewards
            (syndicate_name, rotation, item_name, item_unique, rarity, chance, drop_data_id)
            VALUES (?,?,?,?,?,?,?)""", synd_rows)
        stats['syndicate_rewards'] = len(synd_rows)

        conn.commit()
        _log(f"  relics={stats.get('relics',0)}, rewards={stats.get('relics',0)}")

        # ================================================================
        # ★ 3b: 构建 prime_parts 表（遗物内含 Prime 部件专用表）
        # ================================================================
        _log("[3b/6] 构建 prime_parts 表...")
        if RELICS_JSON.exists():
            pp_stats = _build_prime_parts(cur, conn, all_items, i18n_data)
            pp_count = cur.execute("SELECT COUNT(*) FROM prime_parts").fetchone()[0]
            stats['prime_parts'] = pp_count
            _log(f"  prime_parts={pp_count} (slug={pp_stats.get('has_slug',0)}, zh={pp_stats.get('has_zh',0)}, unique={pp_stats.get('has_unique',0)}, part_type={pp_stats.get('has_part',0)})")
        else:
            _log("  [!] Relics.json 不存在，跳过 prime_parts")

        # ★ 3c-补: 多跳精确匹配填充 —— 纯字符串相等，零模糊匹配
        #
        # 核心思路：从所有"已确认"的来源收集 name→unique_name 映射，
        # 构建一个全局名称解析表。然后对空值字段做精确查找。
        # 多跳体现在：不同表的同一物品可能有不同名称写法（如英文/中文/编号），
        # 只要任一表中该名称已有唯一标识，其他表的同名条目就能通过精确匹配关联上。
        #
        # 数据源层级（仅使用权威锚点，避免循环引用/数据污染）：
        #   Layer 0: items 表          — name(英) → unique_name    （权威锚点）
        #   Layer 1: item_translations — name(多语言) → unique_name （i18n 别名，外键校验）
        #   注意：不使用 rewards 表作为别名源！因为 relic_rewards 等表的
        #         unique 字段可能存的是非物品ID（如遗物自身ID），会导致错误关联。

        _log("  跨表填充: 构建多跳名称解析图...")

        # ---- Layer 0: items 表（权威锚点）----
        _name_to_unique = dict(cur.execute(
            "SELECT name, unique_name FROM items WHERE unique_name IS NOT NULL AND unique_name != ''"
        ).fetchall())
        _log(f"    Layer0 items: {len(_name_to_unique)} 条")

        # ---- Layer 1: item_translations（多语言别名，经外键校验）----
        # 仅采用 unique_name 存在于 items 表中的条目，过滤孤立/错误数据
        _i18n_count = cur.execute("SELECT COUNT(*) FROM item_translations").fetchone()[0]
        if _i18n_count > 0:
            _i18n_rows = cur.execute(
                "SELECT it.name, it.unique_name FROM item_translations it "
                "INNER JOIN items i ON i.unique_name = it.unique_name "
                "WHERE it.unique_name IS NOT NULL AND it.unique_name != '' "
                "AND it.name IS NOT NULL AND it.name != ''"
            ).fetchall()
            _new_aliases = 0
            for _name, _unique in _i18n_rows:
                if _name not in _name_to_unique:
                    _name_to_unique[_name] = _unique
                    _new_aliases += 1
            _log(f"    Layer1 i18n(已校验): +{_new_aliases} 条新别名 (共{len(_i18n_rows)}条)")

        _log(f"    解析图总容量: {len(_name_to_unique)} 个名称 → unique_name")

        # ---- 执行填充：对每个目标表，精确查找后批量 UPDATE ----
        _FILL_TARGETS = [
            ('mission_rewards',    'item_name',       'item_unique'),
            ('sortie_rewards',     'item_name',       'item_unique'),
            ('bounty_rewards',     'item_name',       'item_unique'),
            ('transient_rewards',  'item_name',       'item_unique'),
            ('syndicate_rewards',  'item_name',       'item_unique'),
            ('key_rewards',        'item_name',       'item_unique'),
            ('mod_drops',          'mod_name',        'mod_unique'),
            ('enemy_mod_tables',   'mod_name',        'mod_unique'),
            ('blueprint_drops',    'blueprint_name',  'blueprint_unique'),
            ('enemy_bp_tables',    'blueprint_name',  'blueprint_unique'),
        ]

        total_filled = 0
        for ti, (table, name_col, unique_col) in enumerate(_FILL_TARGETS):
            cur.execute(f"SELECT id, [{name_col}] FROM [{table}] WHERE ([{unique_col}] IS NULL OR [{unique_col}] = '')")
            empty_rows = cur.fetchall()

            batch_updates = []
            for row_id, raw_name in empty_rows:
                # 纯精确匹配：原始名称直接查解析图
                if raw_name in _name_to_unique:
                    batch_updates.append((_name_to_unique[raw_name], row_id))

            if batch_updates:
                cur.executemany(
                    f"UPDATE [{table}] SET [{unique_col}]=? WHERE id=?", batch_updates)
                total_filled += len(batch_updates)
                _log(f"    [{ti+1}/{len(_FILL_TARGETS)}] {table}.{unique_col}: +{len(batch_updates)}")

        conn.commit()
        _log(f"  跨表填充完成: 纯精确匹配补全 {total_filled} 条")
    else:
        _log(f"  [!] all.json 不存在: {DROP_DATA_JSON}")

    # ================================================================
    # Step 4: 游戏翻译 dict.en/zh.json
    # ================================================================
    _log("[4/6] 解析 dict.en/zh.json...")
    en_data = {}; zh_data = {}
    if DICT_EN_JSON.exists():
        with open(DICT_EN_JSON, 'r', encoding='utf-8') as f:
            en_data = json.load(f)
        _log(f"  dict.en.json: {len(en_data)} 条")
    if DICT_ZH_JSON.exists():
        with open(DICT_ZH_JSON, 'r', encoding='utf-8') as f:
            zh_data = json.load(f)
        _log(f"  dict.zh.json: {len(zh_data)} 条")

    if en_data or zh_data:
        all_keys = set(en_data.keys()) | set(zh_data.keys())
        gtrans_rows = []
        for key in all_keys:
            parts = key.split('/')
            category = parts[2] if len(parts) > 2 else ''
            gtrans_rows.append((key, en_data.get(key,''), zh_data.get(key,''), category, 'public-export-plus'))
        cur.executemany("INSERT OR IGNORE INTO game_translations (key, en, zh, category, source) VALUES (?,?,?,?,?)", gtrans_rows)
        conn.commit()
        stats['game_translations'] = len(gtrans_rows)
        _log(f"  game_translations={len(gtrans_rows)}")

    # ================================================================
    # Step 5: WM API
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
            wm_rows = [(wi.get('id',''), wi.get('url_name',''), wi.get('item_name',''), '',
                name_map.get(wi.get('item_name'),''), wi.get('thumb',''),
                1 if wi.get('tradable') else 0,
                1 if 'prime' in wi.get('item_name','').lower() else 0, '') for wi in wm_items]
            cur.executemany("""INSERT OR IGNORE INTO market_items
                (id, slug, en_name, zh_name, item_unique, item_type, is_tradable, is_prime, zh_pinyin)
                VALUES (?,?,?,?,?,?,?,?,?)""", wm_rows)
            conn.commit()
            stats['market_items'] = len(wm_rows)
            _log(f"  market_items={len(wm_rows)}")
        except Exception as e:
            _log(f"  [!] WM API 拉取失败: {e}")
            stats['market_items'] = 0
    else:
        _log("  已跳过 WM API 拉取")
        stats['market_items'] = 0

    # ================================================================
    # Step 6: 元数据
    # ================================================================
    _log("[6/6] 写入元数据...")
    elapsed = round(time.time() - start_time, 1)
    cur.executemany("INSERT OR REPLACE INTO db_meta (key, value) VALUES (?,?)",
        [('schema_version', '1'), ('build_time', time.strftime('%Y-%m-%d %H:%M:%S')),
         ('build_elapsed_sec', str(elapsed))])
    conn.commit()

    _log("优化数据库...")
    conn.execute("VACUUM")

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

    # 关闭应用内缓存的连接
    if close_connections_fn:
        _log("关闭缓存连接...")
        close_connections_fn()
        import time as _time
        _time.sleep(0.5)

    # 替换数据库
    _log(f"替换数据库: {DB_PATH.name} ...")
    shutil.copy2(str(_TMP_DB), str(DB_PATH))
    try:
        _TMP_DB.unlink()
    except OSError:
        pass
    _log("数据库已就位 (warframe.db)")

    return stats
