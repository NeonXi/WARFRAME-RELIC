"""
全物品中英文对照数据库模块 (items_i18n.db)

数据来源:
  - WFCD/warframe-items/All.json       → 物品完整数据（name, uniqueName, category, type, tradable 等）
  - WFCD/warframe-items/i18n.json      → uniqueName → zh.name（中文名）

关联方式: uniqueName 精确关联，确保中英文对应准确无误。

表结构:
  items:          全物品中英对照主表
  items_meta:     元信息表
  items_i18n:     多语言翻译（zh/en/de/fr 等）

用法:
  from data.items_i18n import search_items, translate_item, get_db_stats
  from data.items_i18n import rebuild_all_items_db
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Optional

# ---- 拼音支持 ----
try:
    from pypinyin import pinyin, Style
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False
    pinyin = None
    Style = None

try:
    from PyQt6.QtCore import pyqtSignal, QObject
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False
    # 命令行模式不需要 PyQt6
    pyqtSignal = None
    QObject = object

# ===== 路径 =====
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'items_i18n.db')
ALL_ITEMS_PATH = os.path.join(BASE_DIR, 'all_items.json')  # warframe-items 的 All.json
I18N_PATH = os.path.join(BASE_DIR, 'i18n.json')
ZH_EN_DICT_PATH = os.path.join(BASE_DIR, 'zh_en_dict.json')  # AdminRoc 中英对照补充数据

# ===== 数据源 URL =====
WFCD_ALL_URL = 'https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json'
WFCD_I18N_URL = 'https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json'

# ===== 数据库 Schema 版本 =====
SCHEMA_VERSION = '2'  # v1: 初始版本, v2: 添加拼音完整性检查

# ===== 数据库表结构 =====
SCHEMA = """
-- 全物品中英对照主表
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_name TEXT NOT NULL UNIQUE,   -- 游戏内部唯一标识
    zh_name TEXT NOT NULL,              -- 中文名
    en_name TEXT NOT NULL,              -- 英文名
    category TEXT,                      -- 物品大类 (Warframes/Primary/Secondary/Melee/Relics/Mods/...)
    item_type TEXT,                     -- 物品子类型
    is_tradable INTEGER DEFAULT 0,      -- 是否可交易
    is_prime INTEGER DEFAULT 0,         -- 是否 Prime
    rarity TEXT,                        -- 稀有度
    mr_requirement INTEGER DEFAULT 0,   -- 段位要求
    image_name TEXT,                    -- 图片名称
    description_zh TEXT,                -- 中文描述
    description_en TEXT,                -- 英文描述
    zh_pinyin TEXT DEFAULT '',          -- 中文拼音（全拼+首字母，空格分隔，用于拼音搜索）
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

-- 元信息
CREATE TABLE IF NOT EXISTS items_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _derive_zh_from_pattern(name_lower: str, zh_en_list: list) -> str:
    """从 zh_en_dict.json 的 Prime 版本推导非 Prime 物品的中文翻译。

    策略（按优先级）：
      1. 对于 "X Chassis/Neuroptics/Systems Blueprint"，
         尝试 "X Prime Chassis/Neuroptics/Systems Blueprint" → 去 "Prime" 得中文名
      2. 对于 "X Blueprint"，尝试 "X Prime Blueprint" → 去 "Prime"
      3. 对于资源/合金类，尝试从基础名匹配
      4. 无法推导时返回空字符串（后续用英文名作为中文名）

    Returns:
        str: 推导出的中文名，空字符串表示无法推导
    """
    if not name_lower.endswith(' blueprint'):
        return ''

    # 构建 en_lower → zh_name 查找表
    zh_en_lookup = {}
    for entry in zh_en_list:
        if isinstance(entry, list) and len(entry) >= 2:
            zh_name = entry[0].strip()
            en_name = entry[1].strip()
            if en_name and zh_name:
                zh_en_lookup[en_name.lower()] = zh_name

    # 去掉 "blueprint" 后缀得到基础名
    base = name_lower[:-len(' blueprint')].strip()
    base_title = ' '.join(
        w.capitalize() if w.lower() not in ('of', 'the', 'and', 'in', 'on', 'at', 'to', 'for')
        else w.lower()
        for w in base.split()
    )

    # 尝试1: 识别部件名，在部件名前插入 "Prime"
    # zh_en_dict 格式: "Ash Prime Chassis Blueprint" → "Ash Prime 机体 蓝图"
    # all.json 格式:   "ash chassis blueprint"
    component_keywords = ('chassis', 'neuroptics', 'systems', 'barrel',
                          'receiver', 'stock', 'blade', 'handle', 'link',
                          'grip', 'gauntlet', 'string', 'upper limb', 'lower limb')

    candidate_variants = []

    # 变体A: 在部件词前插入 "Prime"（匹配 zh_en_dict 标准格式）
    parts = base.split()
    if len(parts) >= 2:
        part_idx = None
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] in component_keywords:
                part_idx = i
                break
            if i >= 1 and f"{parts[i-1]} {parts[i]}" in component_keywords:
                part_idx = i - 1
                break
        if part_idx is not None and part_idx > 0:
            warframe_name = ' '.join(parts[:part_idx])
            component_name = ' '.join(parts[part_idx:])
            candidate_variants.append(
                f"{warframe_name} prime {component_name} blueprint")

    # 变体B: 在末尾加 "Prime"（简单拼接，后备）
    candidate_variants.append(f"{base} prime blueprint")

    if ' prime' not in base:
        for variant in candidate_variants:
            if variant in zh_en_lookup:
                zh_prime = zh_en_lookup[variant]
                zh_derived = zh_prime.replace(' Prime', '').replace('Prime ', '').replace('Prime', '')
                zh_derived = zh_derived.strip()
                if zh_derived:
                    return zh_derived

    # 尝试3: 基础名本身在 zh_en_dict 中（不带 Blueprint 的资源/物品）
    if base in zh_en_lookup:
        zh_base = zh_en_lookup[base]
        return f"{zh_base} 蓝图"

    # 尝试4: 如果基础名带有 "x数字" 后缀（资源蓝图）
    # 例如: "adramal alloy x20" → 找 "adramal alloy"
    match = re.match(r'^(.+?)\s+x\d+$', base)
    if match:
        resource_base = match.group(1)
        if resource_base in zh_en_lookup:
            zh_resource = zh_en_lookup[resource_base]
            return f"{zh_resource} x{base.split('x')[-1]} 蓝图"

    # 无法推导
    return ''


def build_all_items_db(all_items_path: str = None,
                       i18n_path: str = None) -> dict:
    """构建全物品中英对照数据库。

    数据优先级（zh_en_dict.json 最全，作为主数据源）:
      1. zh_en_dict.json  — 16907 条中英对照（最全，含 382 条 Blueprint 部件）
      2. all_items.json   — 15729 条物品详细数据（含 category/tradable/rarity 等）
      3. i18n.json        — uniqueName → 中文翻译（补充 zh_en_dict 未覆盖的翻译）

    Args:
        all_items_path: All.json 路径
        i18n_path: i18n.json 路径

    Returns:
        dict: {'total': int, 'stats': dict}
    """
    start_time = time.time()

    # ---- Schema 版本管理和自动迁移 ----
    if os.path.exists(DB_PATH):
        try:
            conn_tmp = sqlite3.connect(DB_PATH)
            _ensure_schema_version(conn_tmp)  # 自动检测并升级 schema
            conn_tmp.close()
        except Exception as e:
            print(f"[items_i18n] Schema 迁移失败: {e}")
            import traceback
            traceback.print_exc()

    all_path = all_items_path or ALL_ITEMS_PATH
    i18n_path = i18n_path or I18N_PATH

    # ============================================================
    # 第1步: 加载 zh_en_dict.json（最全数据源，作为主数据源）
    # ============================================================
    zh_en_dict_path = ZH_EN_DICT_PATH
    if not zh_en_dict_path or not os.path.exists(zh_en_dict_path):
        zh_en_dict_path = os.path.join(BASE_DIR, 'zh_en_dict.json')

    zh_en_list = []
    if os.path.exists(zh_en_dict_path):
        print(f"[items_i18n] 主数据源: zh_en_dict.json ({zh_en_dict_path})")
        with open(zh_en_dict_path, 'r', encoding='utf-8') as f:
            zh_en_list = json.load(f)
        print(f"[items_i18n] zh_en_dict.json 包含 {len(zh_en_list)} 条中英对照")
    else:
        print(f"[items_i18n] zh_en_dict.json 不存在")

    # ============================================================
    # 第2步: 加载 all_items.json（补充详细属性）
    # ============================================================
    all_item_by_name = {}  # en_name → item_info 快速查找
    if os.path.exists(all_path):
        print(f"[items_i18n] 辅助数据源: all_items.json ({all_path})")
        with open(all_path, 'r', encoding='utf-8') as f:
            all_data = json.load(f)

        if not isinstance(all_data, list):
            raise ValueError(f"All.json 应为数组，实际为 {type(all_data).__name__}")

        print(f"[items_i18n] all_items.json 包含 {len(all_data)} 个物品")

        for item in all_data:
            en_name = item.get('name', '').strip()
            if en_name:
                all_item_by_name[en_name.lower()] = {
                    'name': en_name,
                    'unique_name': item.get('uniqueName', ''),
                    'category': item.get('category', ''),
                    'type': item.get('type', ''),
                    'tradable': item.get('tradable', False),
                    'is_prime': 'Prime' in item.get('name', ''),
                    'rarity': item.get('rarity', ''),
                    'mr_requirement': item.get('masteryReq', 0) or 0,
                    'image_name': item.get('imageName', ''),
                    'description': item.get('description', ''),
                    'patchlogs': item.get('patchlogs', []),
                }
    else:
        print(f"[items_i18n] all_items.json 不存在，仅使用 zh_en_dict.json")

    # ============================================================
    # 第3步: 加载 i18n.json（补充中文翻译，仅用于 zh_en_dict 未覆盖的条目）
    # ============================================================
    i18n_data = {}
    if os.path.exists(i18n_path):
        print(f"[items_i18n] 翻译补充: i18n.json ({i18n_path})")
        with open(i18n_path, 'r', encoding='utf-8') as f:
            i18n_data = json.load(f)
        print(f"[items_i18n] i18n.json 包含 {len(i18n_data)} 条翻译")
    else:
        print(f"[items_i18n] i18n.json 不存在")

    # ============================================================
    # 第4步: 以 zh_en_dict.json 为主构建 item_map
    # ============================================================
    item_map = {}  # key → item_info
    seen_en_lower = set()

    for entry in zh_en_list:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        zh_name, en_name = entry[0].strip(), entry[1].strip()
        if not en_name or not zh_name:
            continue

        en_lower = en_name.lower()
        if en_lower in seen_en_lower:
            continue
        seen_en_lower.add(en_lower)

        # 从 all_items.json 补充详细属性
        extra = all_item_by_name.get(en_lower, {})
        unique_name = extra.get('unique_name', '')
        if not unique_name:
            slug = en_lower.replace(' ', '_').replace("'", "").replace('-', '_')
            unique_name = f"/Lotus/Supplement/{slug}"

        is_prime = extra.get('is_prime', False) or ('Prime' in en_name)
        is_part = 'Blueprint' in en_name

        item_map[unique_name] = {
            'name': en_name,
            'category': extra.get('category', '') or ('Warframe Parts' if is_part else 'Misc'),
            'type': extra.get('type', ''),
            'tradable': extra.get('tradable', False) or is_part,
            'is_prime': is_prime,
            'rarity': extra.get('rarity', '') or ('Prime' if is_prime else ''),
            'mr_requirement': extra.get('mr_requirement', 0),
            'image_name': extra.get('image_name', ''),
            'description': extra.get('description', ''),
            'patchlogs': extra.get('patchlogs', []),
            '_zh_name': zh_name,
        }

    zh_en_count = len(item_map)
    print(f"[items_i18n] 主数据源构建完成: {zh_en_count} 个物品（含 {zh_en_count - len(zh_en_list):,} 个重复已去重）"
          if zh_en_count != len(zh_en_list) else
          f"[items_i18n] 主数据源构建完成: {zh_en_count} 个物品")

    # ============================================================
    # 第5步: 补充 all_items.json 中有但 zh_en_dict.json 中没有的物品
    # ============================================================
    all_supplemented = 0
    for en_lower, info in all_item_by_name.items():
        if en_lower in seen_en_lower:
            continue
        un = info['unique_name']
        if not un:
            continue

        seen_en_lower.add(en_lower)
        en_name = info['name']

        item_map[un] = {
            'name': en_name,
            'category': info['category'],
            'type': info['type'],
            'tradable': info['tradable'],
            'is_prime': info['is_prime'],
            'rarity': info['rarity'],
            'mr_requirement': info['mr_requirement'],
            'image_name': info['image_name'],
            'description': info['description'],
            'patchlogs': info['patchlogs'],
            '_zh_name': '',  # 中文翻译后续从 i18n.json 获取
        }
        all_supplemented += 1

    if all_supplemented:
        print(f"[items_i18n] all_items.json 补充了 {all_supplemented} 个额外物品")

    # ============================================================
    # 第5.5步: 从掉落数据 (all.json) 补充缺失的掉落物品
    # ============================================================
    # all.json 是项目的掉落数据源，其中包含一些 all_items.json / zh_en_dict.json
    # 中不存在的物品（如非 Prime 战甲部件蓝图、资源蓝图等），需要补充到数据库
    # 以便用户在搜索时能匹配到掉落来源。
    #
    # 翻译策略：
    #   1. 优先从 zh_en_dict.json 中查找 Prime 版本对应条目，去除 "Prime" 推导中文
    #   2. 对于以 "blueprint" 结尾的物品，尝试从基础名中匹配
    #   3. 无法翻译时使用英文名作为中文名
    drop_supplemented = 0
    alljson_path = os.path.join(os.path.dirname(BASE_DIR), 'data', 'all.json')
    if os.path.exists(alljson_path):
        with open(alljson_path, 'r', encoding='utf-8') as f:
            drop_data = json.load(f)

        # 收集所有掉落物品名
        drop_names = set()

        def _collect_drop_names(name):
            if name:
                n = name.strip().lower()
                if n:
                    drop_names.add(n)

        for top_key, top_val in drop_data.items():
            if top_key == 'relics':
                for relic in top_val:
                    for reward in relic.get('rewards', []):
                        _collect_drop_names(reward.get('itemName', ''))
            elif top_key == 'missionRewards':
                for planet, nodes in top_val.items():
                    if not isinstance(nodes, dict):
                        continue
                    for node, ndata in nodes.items():
                        if not isinstance(ndata, dict):
                            continue
                        rewards = ndata.get('rewards', {})
                        if isinstance(rewards, dict):
                            for rot, items in rewards.items():
                                if isinstance(items, list):
                                    for item in items:
                                        if isinstance(item, dict):
                                            _collect_drop_names(item.get('itemName', ''))
            elif top_key in ('cetusBountyRewards', 'solarisBountyRewards', 'deimosRewards',
                             'zarimanRewards', 'entratiLabRewards', 'hexRewards'):
                for entry in top_val:
                    if not isinstance(entry, dict):
                        continue
                    rewards = entry.get('rewards', {})
                    if isinstance(rewards, dict):
                        for rot, items in rewards.items():
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict):
                                        _collect_drop_names(item.get('itemName', ''))
            elif top_key in ('sortieRewards',):
                for entry in top_val:
                    if isinstance(entry, dict):
                        _collect_drop_names(entry.get('itemName', ''))
            elif top_key in ('keyRewards', 'transientRewards'):
                for entry in top_val:
                    if not isinstance(entry, dict):
                        continue
                    rewards = entry.get('rewards', {})
                    if isinstance(rewards, list):
                        for item in rewards:
                            if isinstance(item, dict):
                                _collect_drop_names(item.get('itemName', ''))
                    elif isinstance(rewards, dict):
                        for rot, items in rewards.items():
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict):
                                        _collect_drop_names(item.get('itemName', ''))
            elif top_key == 'blueprintLocations':
                for bp in top_val:
                    if isinstance(bp, dict):
                        _collect_drop_names(
                            bp.get('blueprintName', bp.get('itemName', '')))
            elif top_key == 'enemyModTables':
                for entry in top_val:
                    if isinstance(entry, dict):
                        for mod in entry.get('mods', []):
                            if isinstance(mod, dict):
                                _collect_drop_names(mod.get('modName', ''))
            elif top_key == 'enemyBlueprintTables':
                for bp in top_val:
                    if isinstance(bp, dict):
                        _collect_drop_names(
                            bp.get('blueprintName', bp.get('itemName', '')))
            elif top_key == 'modLocations':
                for mod in top_val:
                    if isinstance(mod, dict):
                        _collect_drop_names(mod.get('modName', mod.get('itemName', '')))
            elif top_key == 'syndicates':
                for faction, items in top_val.items():
                    if isinstance(items, list):
                        for entry in items:
                            if isinstance(entry, dict):
                                _collect_drop_names(entry.get('item', ''))
            elif top_key in ('resourceByAvatar', 'sigilByAvatar', 'additionalItemByAvatar'):
                for entry in top_val:
                    if isinstance(entry, dict):
                        for item in entry.get('items', []):
                            if isinstance(item, dict):
                                _collect_drop_names(item.get('item', ''))

        # 过滤掉资源/货币类（数字+材料名的组合）
        skip_pattern = re.compile(r'^\d+[\sx]')
        skip_keywords = {'credit', 'credits', 'endo', 'ducat', 'ducats', 'booster',
                         'boosters', 'relic', 'relics', 'forma', 'aya', 'cache'}
        for name_lower in sorted(drop_names):
            # 跳过已存在的
            if name_lower in seen_en_lower:
                continue
            # 跳过资源/货币
            if skip_pattern.match(name_lower):
                continue
            if name_lower.split()[-1] in skip_keywords:
                continue
            if any(kw in name_lower for kw in skip_keywords):
                continue

            seen_en_lower.add(name_lower)

            # 生成标题大小写的英文名
            en_name = ' '.join(
                w.capitalize() if w.lower() not in ('of', 'the', 'and', 'in', 'on', 'at', 'to', 'for')
                else w.lower()
                for w in name_lower.split()
            )

            # 尝试推导中文翻译
            zh_name = _derive_zh_from_pattern(name_lower, zh_en_list)

            # 生成 unique_name
            slug = re.sub(r"[^a-z0-9_]", '_', name_lower)
            unique_name = f"/Lotus/Supplement/Drop/{slug}"

            is_prime = 'prime' in name_lower
            is_part = 'blueprint' in name_lower

            item_map[unique_name] = {
                'name': en_name,
                'category': 'Warframe Parts' if is_part else 'Misc',
                'type': '',
                'tradable': is_part,
                'is_prime': is_prime,
                'rarity': 'Prime' if is_prime else '',
                'mr_requirement': 0,
                'image_name': '',
                'description': '',
                'patchlogs': [],
                '_zh_name': zh_name,
            }
            drop_supplemented += 1

        if drop_supplemented:
            print(f"[items_i18n] all.json 掉落数据补充了 {drop_supplemented} 个额外物品")

    # ============================================================
    # 第6步: 写入数据库（批量插入优化）
    # ============================================================
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM items")
    
    inserted = 0
    has_cn = 0
    has_desc = 0
    category_count = {}
    type_count = {}
    
    # 批量插入参数
    BATCH_SIZE = 500
    batch_data = []
    
    # 预编译 SQL
    INSERT_SQL = """INSERT OR IGNORE INTO items
                   (unique_name, zh_name, en_name, category, item_type,
                    is_tradable, is_prime, rarity, mr_requirement, image_name,
                    description_zh, description_en, zh_pinyin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    for unique_name, item_info in item_map.items():
        en_name = item_info['name'].strip()
        if not en_name:
            continue

        # 获取中文翻译：zh_en_dict 优先 → i18n.json 补充
        zh_name = item_info.pop('_zh_name', '')
        description_zh = ''

        if not zh_name:
            # 从 i18n.json 查找
            i18n_entry = i18n_data.get(unique_name, {})
            if isinstance(i18n_entry, dict):
                zh_val = i18n_entry.get('zh', '')
                if isinstance(zh_val, dict):
                    zh_name = (zh_val.get('name', '') or '').strip()
                    desc = zh_val.get('description', '')
                    if isinstance(desc, str):
                        description_zh = desc.strip()
                elif isinstance(zh_val, str):
                    zh_name = zh_val.strip()
                    if zh_name == en_name:
                        zh_name = ''

        # 获取英文描述
        desc_en = item_info.get('description', '')
        description_en = desc_en.strip() if isinstance(desc_en, str) else ''

        # 如果 zh_name 为空，使用 en_name
        if not zh_name:
            zh_name = en_name

        cat = item_info['category'] or 'Other'
        itype = item_info['type'] or ''

        category_count[cat] = category_count.get(cat, 0) + 1
        type_count[itype] = type_count.get(itype, 0) + 1

        if zh_name != en_name:
            has_cn += 1
        if description_zh or description_en:
            has_desc += 1

        # 生成拼音索引
        pinyin_str = _make_pinyin(zh_name)

        # 添加到批处理
        batch_data.append((
            unique_name,
            zh_name,
            en_name,
            cat,
            itype,
            int(item_info['tradable']),
            int(item_info['is_prime']),
            item_info['rarity'] or '',
            item_info['mr_requirement'],
            item_info['image_name'] or '',
            description_zh,
            description_en,
            pinyin_str,
        ))
        
        # 达到批次大小时提交
        if len(batch_data) >= BATCH_SIZE:
            conn.executemany(INSERT_SQL, batch_data)
            inserted += len(batch_data)
            batch_data.clear()
            
            # 进度提示
            if inserted % 2000 == 0:
                print(f"[items_i18n] 已插入: {inserted} 条...")

    # 提交剩余数据
    if batch_data:
        conn.executemany(INSERT_SQL, batch_data)
        inserted += len(batch_data)

    # 元信息（包含 schema 版本）
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('total', ?)", (str(inserted),))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('has_cn', ?)", (str(has_cn),))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('has_desc', ?)", (str(has_desc),))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('source', 'zh_en_dict.json (主) + WFCD All.json/i18n.json (补充)')")
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('updated_at', ?)", (now,))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))

    conn.commit()
    conn.close()

    elapsed = time.time() - start_time
    stats = {
        'total': inserted,
        'has_cn': has_cn,
        'has_desc': has_desc,
        'categories': dict(sorted(category_count.items(), key=lambda x: -x[1])),
        'types': dict(sorted(type_count.items(), key=lambda x: -x[1])[:20]),
        'elapsed': elapsed,
    }

    # 武器合并统计（WFCD 无统一 Weapons 分类，按子类合并）
    weapon_cats = {'Primary', 'Secondary', 'Melee', 'Arch-Gun', 'Arch-Melee'}
    weapon_total = sum(category_count.get(c, 0) for c in weapon_cats)

    print(f"\n[items_i18n] 全物品数据库构建完成 (耗时 {elapsed:.1f}s)")
    print(f"  总计: {inserted} 个物品")
    print(f"  有中文翻译: {has_cn} ({has_cn*100//max(inserted,1)}%)")
    print(f"  有描述: {has_desc} ({has_desc*100//max(inserted,1)}%)")
    print(f"  武器合计: {weapon_total} 个 "
          f"(主武器 {category_count.get('Primary', 0)}, "
          f"副武器 {category_count.get('Secondary', 0)}, "
          f"近战 {category_count.get('Melee', 0)}, "
          f"Archwing枪 {category_count.get('Arch-Gun', 0)}, "
          f"Archwing近战 {category_count.get('Arch-Melee', 0)})")
    print(f"  分类统计:")
    for cat, count in sorted(category_count.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    return stats


# ============================================================
# Schema 版本管理和拼音完整性检查
# ============================================================

def _get_schema_version(conn) -> str:
    """获取当前数据库的 schema 版本"""
    try:
        row = conn.execute("SELECT value FROM items_meta WHERE key = 'schema_version'").fetchone()
        return row[0] if row else '1'  # 默认为 v1（无版本号）
    except Exception:
        return '1'


def _ensure_schema_version(conn):
    """确保数据库 schema 版本是最新的，自动执行迁移"""
    current_version = _get_schema_version(conn)
    
    if current_version == '1':
        # v1 -> v2: 添加拼音完整性检查和修复
        print("[items_i18n] 检测到旧版 schema (v1)，正在升级到 v2...")
        
        # 检查拼音字段是否存在
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(items)")
        cols = [row[1] for row in cur.fetchall()]
        
        if 'zh_pinyin' not in cols:
            print("[items_i18n] 添加 zh_pinyin 字段...")
            conn.execute("ALTER TABLE items ADD COLUMN zh_pinyin TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_items_pinyin ON items(zh_pinyin)")
        
        # 检查并修复拼音数据
        if _HAS_PYPINYIN:
            missing_count = conn.execute(
                "SELECT COUNT(*) FROM items WHERE zh_pinyin = '' OR zh_pinyin IS NULL"
            ).fetchone()[0]
            
            if missing_count > 0:
                print(f"[items_i18n] 发现 {missing_count} 条记录缺少拼音，开始修复...")
                rows = conn.execute(
                    "SELECT id, zh_name FROM items WHERE zh_pinyin = '' OR zh_pinyin IS NULL"
                ).fetchall()
                
                updated = 0
                for row_id, zh_name in rows:
                    py = _make_pinyin(zh_name)
                    if py:
                        conn.execute("UPDATE items SET zh_pinyin = ? WHERE id = ?", (py, row_id))
                        updated += 1
                
                conn.commit()
                print(f"[items_i18n] 拼音修复完成: {updated}/{len(rows)} 条")
        else:
            print("[items_i18n] ⚠ pypinyin 未安装，无法修复拼音数据")
        
        # 更新版本号
        conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
        conn.commit()
        print("[items_i18n] Schema 升级到 v2 完成")
    
    elif current_version != SCHEMA_VERSION:
        print(f"[items_i18n] ⚠ 未知的 schema 版本: {current_version} (期望: {SCHEMA_VERSION})")


def check_pinyin_integrity() -> dict:
    """检查数据库中拼音数据的完整性。
    
    Returns:
        {
            'total': 总记录数,
            'has_pinyin': 有拼音的记录数,
            'missing_pinyin': 缺少拼音的记录数,
            'integrity_rate': 完整率 (0-1),
            'needs_repair': 是否需要修复
        }
    """
    if not os.path.exists(DB_PATH):
        return {
            'total': 0, 'has_pinyin': 0, 'missing_pinyin': 0,
            'integrity_rate': 0, 'needs_repair': False
        }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # 检查拼音字段是否存在
        cur = conn.execute("PRAGMA table_info(items)")
        cols = [row[1] for row in cur.fetchall()]
        
        if 'zh_pinyin' not in cols:
            conn.close()
            return {
                'total': 0, 'has_pinyin': 0, 'missing_pinyin': 0,
                'integrity_rate': 0, 'needs_repair': True,
                'error': 'zh_pinyin 字段不存在'
            }
        
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        has_pinyin = conn.execute(
            "SELECT COUNT(*) FROM items WHERE zh_pinyin != '' AND zh_pinyin IS NOT NULL"
        ).fetchone()[0]
        missing_pinyin = total - has_pinyin
        
        conn.close()
        
        integrity_rate = has_pinyin / total if total > 0 else 0
        needs_repair = missing_pinyin > 0 and _HAS_PYPINYIN
        
        return {
            'total': total,
            'has_pinyin': has_pinyin,
            'missing_pinyin': missing_pinyin,
            'integrity_rate': integrity_rate,
            'needs_repair': needs_repair
        }
    except Exception as e:
        return {
            'total': 0, 'has_pinyin': 0, 'missing_pinyin': 0,
            'integrity_rate': 0, 'needs_repair': False,
            'error': str(e)
        }


def repair_pinyin_data(batch_size: int = 500) -> dict:
    """修复数据库中缺失的拼音数据（批量处理）。
    
    Args:
        batch_size: 批量更新的大小
        
    Returns:
        {'repaired': 修复数量, 'total': 总数, 'elapsed': 耗时}
    """
    if not _HAS_PYPINYIN:
        raise RuntimeError("pypinyin 库未安装，无法修复拼音")
    
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}")
    
    start_time = time.time()
    conn = sqlite3.connect(DB_PATH)
    
    # 获取需要修复的记录
    rows = conn.execute(
        "SELECT id, zh_name FROM items WHERE zh_pinyin = '' OR zh_pinyin IS NULL"
    ).fetchall()
    
    total = len(rows)
    if total == 0:
        conn.close()
        return {'repaired': 0, 'total': 0, 'elapsed': 0}
    
    print(f"[items_i18n] 开始修复拼音数据: {total} 条记录...")
    
    repaired = 0
    batch_data = []
    
    for row_id, zh_name in rows:
        py = _make_pinyin(zh_name)
        if py:
            batch_data.append((py, row_id))
            repaired += 1
            
            # 批量提交
            if len(batch_data) >= batch_size:
                conn.executemany(
                    "UPDATE items SET zh_pinyin = ? WHERE id = ?",
                    batch_data
                )
                batch_data.clear()
                print(f"[items_i18n] 已修复: {repaired}/{total}")
    
    # 提交剩余数据
    if batch_data:
        conn.executemany("UPDATE items SET zh_pinyin = ? WHERE id = ?", batch_data)
    
    conn.commit()
    elapsed = time.time() - start_time
    
    print(f"[items_i18n] 拼音修复完成: {repaired}/{total} 条 (耗时 {elapsed:.1f}s)")
    
    conn.close()
    return {'repaired': repaired, 'total': total, 'elapsed': elapsed}


# ============================================================
# 拼音工具
# ============================================================

def _make_pinyin(zh_name: str) -> str:
    """为中文名生成拼音索引字符串（全拼 + 首字母，空格分隔）。
    例: "龙骑兵 Prime 枪托" → "longqibing prime qiangtuo lqb prime qt"
    """
    if not _HAS_PYPINYIN or not zh_name:
        return ''
    result_parts = []
    initials_parts = []
    for ch in zh_name:
        if '\u4e00' <= ch <= '\u9fff':
            try:
                py = pinyin(ch, style=Style.NORMAL, heteronym=False)
                if py and py[0]:
                    full = py[0][0].lower()
                    result_parts.append(full)
                    initials_parts.append(full[0] if full else '')
            except Exception:
                pass
        elif ch.isalpha():
            result_parts.append(ch.lower())
            initials_parts.append(ch.lower())
        elif ch == ' ':
            result_parts.append(' ')
            initials_parts.append(' ')
    # 合并：全拼 + 空格 + 首字母
    full_str = ''.join(result_parts).strip()
    initials_str = ''.join(initials_parts).strip().replace(' ', '')
    # 如果首字母和全拼相同则只保留全拼
    if initials_str and initials_str != full_str.replace(' ', ''):
        return f"{full_str} {initials_str}"
    return full_str


# ============================================================
# 查询 API
# ============================================================

def search_items(query: str,
                 search_field: str = 'all',
                 category: str = None,
                 is_prime: bool = None,
                 is_tradable: bool = None,
                 limit: int = 50) -> list[dict]:
    """全物品搜索。

    Args:
        query: 搜索关键词
        search_field: 'all' | 'zh' | 'en' | 'unique'
        category: 物品分类过滤 (Warframes/Primary/Secondary/Melee/...)
        is_prime: 是否 Prime
        is_tradable: 是否可交易
        limit: 返回数量上限

    Returns:
        [{id, unique_name, zh_name, en_name, category, item_type, ...}, ...]
    """
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = "SELECT * FROM items WHERE 1=1"
    params = []

    if query:
        if search_field == 'zh':
            sql += " AND zh_name LIKE ?"
            params.append(f"%{query}%")
        elif search_field == 'en':
            sql += " AND en_name LIKE ?"
            params.append(f"%{query}%")
        elif search_field == 'unique':
            sql += " AND unique_name LIKE ?"
            params.append(f"%{query}%")
        else:  # all
            sql += " AND (zh_name LIKE ? OR en_name LIKE ? OR unique_name LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

    if category:
        sql += " AND category = ?"
        params.append(category)

    if is_prime is not None:
        sql += " AND is_prime = ?"
        params.append(int(is_prime))

    if is_tradable is not None:
        sql += " AND is_tradable = ?"
        params.append(int(is_tradable))

    sql += " ORDER BY category, zh_name LIMIT ?"
    params.append(limit)

    cur = conn.cursor()
    cur.execute(sql, params)
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def _is_chinese_query(query: str) -> bool:
    """判断查询是否为中文（含任意中文字符）。"""
    for ch in query:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return True
    return False


# ============================================================
# 精炼版本过滤（用于 suggest_items）
# ============================================================

# 遗物精炼标签
_REFINEMENT_TAGS = {'Intact', 'Exceptional', 'Flawless', 'Radiant'}

# 遗物纪元前缀
_RELIC_ERAS = {'Lith', 'Meso', 'Neo', 'Axi', 'Requiem', 'Vanguard'}


def _filter_relic_refinements_in_suggest(results: list[dict]) -> list[dict]:
    """过滤 suggest_items 结果中的遗物精炼版本。
    
    策略：
      1. 收集所有基础版遗物名称（如 "Axi S20 Relic"）
      2. 移除对应的精炼版本（如 "Axi S20 Radiant", "Axi S20 Intact" 等）
    """
    if not results:
        return results
    
    # 第一步：找出所有遗物项（含基础版和精炼版）
    relic_items = []
    base_names = set()
    refinement_items = []
    
    for r in results:
        en_name = r.get('en_name', '')
        if not en_name:
            continue
        words = en_name.split()
        # 检测是否是遗物：至少3个词，第一个词是纪元，包含 Relic 或精炼标签
        if len(words) >= 3 and words[0] in _RELIC_ERAS:
            last_word = words[-1]
            if last_word == 'Relic':
                # 基础版遗物，如 "Axi S20 Relic"
                base_names.add(en_name.lower())
                relic_items.append(r)
            elif last_word in _REFINEMENT_TAGS:
                # 精炼版遗物，如 "Axi S20 Radiant"
                refinement_items.append(r)
    
    if not refinement_items:
        return results
    
    # 第二步：从结果中移除精炼版遗物（其基础版已经在结果中）
    filtered = []
    for r in results:
        en_name = r.get('en_name', '')
        words = en_name.split()
        if len(words) >= 3 and words[0] in _RELIC_ERAS and words[-1] in _REFINEMENT_TAGS:
            # 这是精炼版遗物，检查基础版是否已在结果中
            base_name = ' '.join(words[:-1]) + ' Relic'
            if base_name.lower() in base_names:
                # 基础版已存在，跳过精炼版
                print(f"[suggest过滤] 跳过精炼版: '{en_name}' (基础版 '{base_name}' 已存在)", flush=True)
                continue
        filtered.append(r)
    
    return filtered


def _search_by_field(conn, q: str, search_field: str, match_field: str,
                     results: list, seen: set, limit: int):
    """在指定字段上执行三级匹配搜索，结果追加到 results。

    - 精确匹配 > 前缀匹配 > 包含匹配
    - match_field: 'en' | 'zh' | 'py'（标识匹配到哪个字段，用于 UI 高亮）
    """
    is_cn = (search_field == 'zh_name')
    remain = limit - len(results)

    # 第1级：精确匹配
    if is_cn:
        rows = conn.execute(
            f"SELECT zh_name, en_name, category FROM items WHERE {search_field} = ? LIMIT ?",
            (q, remain)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT zh_name, en_name, category FROM items WHERE LOWER({search_field}) = ? LIMIT ?",
            (q.lower(), remain)
        ).fetchall()
    for r in rows:
        key = (r['en_name'] + r['zh_name']).lower()
        if key not in seen:
            seen.add(key)
            results.append({
                'zh_name': r['zh_name'], 'en_name': r['en_name'],
                'category': r['category'], 'match_quality': 'exact',
                'match_field': match_field,
            })

    # 第2级：前缀匹配
    remain = limit - len(results)
    if remain > 0:
        if is_cn:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} != ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"{q}%", q, remain)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE LOWER({search_field}) LIKE ? AND LOWER({search_field}) != ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"{q.lower()}%", q.lower(), remain)
            ).fetchall()
        for r in rows:
            key = (r['en_name'] + r['zh_name']).lower()
            if key not in seen:
                seen.add(key)
                results.append({
                    'zh_name': r['zh_name'], 'en_name': r['en_name'],
                    'category': r['category'], 'match_quality': 'prefix',
                    'match_field': match_field,
                })

    # 第3级：包含匹配
    remain = limit - len(results)
    if remain > 0:
        if is_cn:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} NOT LIKE ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"%{q}%", f"{q}%", remain)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE LOWER({search_field}) LIKE ? AND LOWER({search_field}) NOT LIKE ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"%{q.lower()}%", f"{q.lower()}%", remain)
            ).fetchall()
        for r in rows:
            key = (r['en_name'] + r['zh_name']).lower()
            if key not in seen:
                seen.add(key)
                results.append({
                    'zh_name': r['zh_name'], 'en_name': r['en_name'],
                    'category': r['category'], 'match_quality': 'contains',
                    'match_field': match_field,
                })


# ---- 拼音完整性缓存（避免每次 suggest 都检查数据库）----
_pinyin_integrity_checked = False
_pinyin_integrity_ok = False


def suggest_items(query: str, limit: int = 20) -> list[dict]:
    """实时输入联想：自动检测输入语言，支持中/英/拼音搜索。

    - 输入中文 → 搜索中文名
    - 输入英文/拼音 → 同时搜索英文名和拼音字段（两者在数据库中不冲突）
    - 精确匹配 > 前缀匹配 > 包含匹配
    - 结果按 match_quality 排序（exact > prefix > contains）

    Args:
        query: 用户输入（英文/中文/拼音均可，大小写不敏感）
        limit: 返回数量上限

    Returns:
        [{zh_name, en_name, category, match_quality, match_field}, ...]
        match_field: 'en' | 'zh' | 'py'（匹配到哪个字段，用于 UI 高亮）
        match_quality: 'exact' | 'prefix' | 'contains'
    """
    global _pinyin_integrity_checked, _pinyin_integrity_ok

    if not query or not query.strip():
        return []

    q = query.strip()

    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 检测 zh_pinyin 列是否存在（兼容旧数据库）
    has_pinyin_col = False
    try:
        cur = conn.execute("PRAGMA table_info(items)")
        has_pinyin_col = any(row[1] == 'zh_pinyin' for row in cur.fetchall())
    except Exception:
        pass

    # ★ 自动修复缺失的拼音数据（仅首次检查，后续跳过）
    if has_pinyin_col and not _pinyin_integrity_checked:
        _pinyin_integrity_checked = True
        try:
            missing = conn.execute(
                "SELECT COUNT(*) FROM items WHERE zh_pinyin = '' OR zh_pinyin IS NULL"
            ).fetchone()[0]
            if missing > 0 and _HAS_PYPINYIN:
                print(f"[items_i18n] 检测到 {missing} 条拼音数据缺失，自动修复中...")
                conn.close()
                repair_pinyin_data()
                _pinyin_integrity_ok = True
                # 重新打开连接
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
            else:
                _pinyin_integrity_ok = True
        except Exception:
            pass

    results = []
    seen = set()

    if _is_chinese_query(q):
        # 中文 → 搜索中文名
        _search_by_field(conn, q, 'zh_name', 'zh', results, seen, limit)
    else:
        # 非中文：同时搜索英文名和拼音字段（自然不冲突）
        _search_by_field(conn, q, 'en_name', 'en', results, seen, limit)
        if has_pinyin_col:
            _search_by_field(conn, q, 'zh_pinyin', 'py', results, seen, limit)

        # 按匹配质量排序（exact > prefix > contains）
        quality_order = {'exact': 0, 'prefix': 1, 'contains': 2}
        results.sort(key=lambda x: quality_order.get(x['match_quality'], 99))

    conn.close()
    
    # ★ 过滤遗物精炼版本：只保留基础版本（不带精炼标签的）
    results = _filter_relic_refinements_in_suggest(results)
    
    return results[:limit]


def translate_item(name: str) -> Optional[dict]:
    """精确翻译（中→英 或 英→中）。

    Returns:
        dict: {zh_name, en_name, category, ...} 或 None
    """
    if not os.path.exists(DB_PATH):
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT * FROM items WHERE zh_name = ? OR en_name = ? LIMIT 1",
        (name, name)
    ).fetchone()

    conn.close()
    return dict(row) if row else None


def get_categories() -> list[str]:
    """获取所有物品分类列表。"""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM items "
        "GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_db_stats() -> dict:
    """获取全物品数据库统计信息。"""
    if not os.path.exists(DB_PATH):
        return {
            'exists': False,
            'total': 0,
            'has_cn': 0,
            'categories': {},
            'db_size': 0,
            'db_mtime': '',
        }
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        total = cur.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        has_cn = cur.execute(
            "SELECT COUNT(*) FROM items WHERE zh_name != en_name"
        ).fetchone()[0]

        cat_rows = cur.execute(
            "SELECT category, COUNT(*) FROM items GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall()
        categories = dict(cat_rows)

        # 获取元信息
        updated_at = ''
        source = ''
        meta_rows = cur.execute("SELECT key, value FROM items_meta").fetchall()
        for key, value in meta_rows:
            if key == 'updated_at':
                updated_at = value
            elif key == 'source':
                source = value

        # 武器合并统计
        weapon_cats = {'Primary', 'Secondary', 'Melee', 'Arch-Gun', 'Arch-Melee'}
        weapon_total = sum(categories.get(c, 0) for c in weapon_cats)
        weapon_detail = {c: categories.get(c, 0) for c in weapon_cats if categories.get(c, 0)}

        conn.close()
        stat = os.stat(DB_PATH)
        return {
            'exists': True,
            'total': total,
            'has_cn': has_cn,
            'categories': categories,
            'weapon_total': weapon_total,
            'weapon_detail': weapon_detail,
            'source': source,
            'updated_at': updated_at,
            'db_size': stat.st_size,
            'db_mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception as e:
        return {'exists': False, 'error': str(e)}


# ============================================================
# 自动跟随更新 Worker
# ============================================================

if _HAS_PYQT:

    class ItemsI18nUpdateWorker(QObject):
        """后台线程：重建全物品中英对照数据库。

        由 TranslationUpdateWorker 或 UpdateWorker 完成后自动触发。
        """

        step_changed = pyqtSignal(int, str)
        log = pyqtSignal(str, str)
        progress_pct = pyqtSignal(int)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, silent: bool = False):
            """
            Args:
                silent: True 时静默更新（不弹提示），False 时显示日志
            """
            super().__init__()
            self.silent = silent

        def run(self):
            start_time = time.time()

            if not self.silent:
                self.step_changed.emit(1, "构建全物品中英对照数据库")
                self.log.emit("info", "正在从 all_items.json + i18n.json 构建全物品数据库...")

            try:
                # 检查数据文件
                if not os.path.exists(ALL_ITEMS_PATH):
                    if not self.silent:
                        self.log.emit("error", f"all_items.json 不存在: {ALL_ITEMS_PATH}")
                    self.error.emit(f"all_items.json 不存在")
                    return

                if not os.path.exists(I18N_PATH):
                    if not self.silent:
                        self.log.emit("warn", f"i18n.json 不存在，将仅使用英文数据")

                self.step_changed.emit(2, "加载数据文件")
                stats = build_all_items_db()

                total_time = time.time() - start_time

                if not self.silent:
                    self.step_changed.emit(3, "完成")
                    self.log.emit("ok", f"========== 全物品数据库更新完成 (耗时 {total_time:.1f}s) ==========")
                    self.log.emit("ok", f"  总计: {stats['total']} 个物品")
                    self.log.emit("ok", f"  有中文翻译: {stats['has_cn']} 个")
                    self.log.emit("info", f"  分类统计:")
                    for cat, count in list(stats['categories'].items())[:10]:
                        self.log.emit("info", f"    {cat}: {count}")

                self.finished.emit(stats)

            except Exception as e:
                if not self.silent:
                    self.log.emit("error", f"全物品数据库更新失败: {e}")
                self.error.emit(str(e))


def auto_rebuild_items_db(silent: bool = True) -> bool:
    """同步方式自动重建全物品数据库（静默模式）。

    Returns:
        bool: 是否成功
    """
    try:
        build_all_items_db()
        return True
    except Exception as e:
        print(f"[items_i18n] 自动重建失败: {e}")
        return False


def init_database_check(auto_repair: bool = True) -> dict:
    """初始化时检查数据库完整性（建议在应用启动时调用）。
    
    Args:
        auto_repair: 是否自动修复缺失的拼音数据
        
    Returns:
        检查结果字典
    """
    if not os.path.exists(DB_PATH):
        print("[items_i18n] ⚠ 数据库不存在，将在首次搜索时自动创建")
        return {'status': 'missing', 'action': 'will_create_on_first_search'}
    
    # 检查拼音完整性
    integrity = check_pinyin_integrity()
    
    if integrity.get('error'):
        print(f"[items_i18n] ⚠ 数据库检查失败: {integrity['error']}")
        return {'status': 'error', 'error': integrity['error']}
    
    total = integrity['total']
    has_pinyin = integrity['has_pinyin']
    missing = integrity['missing_pinyin']
    rate = integrity['integrity_rate']
    
    # 输出检查结果
    if total == 0:
        print("[items_i18n] ⚠ 数据库为空，建议重建")
        return {'status': 'empty', 'action': 'rebuild_recommended'}
    
    if rate < 0.5:  # 完整率低于50%
        print(f"[items_i18n] ⚠ 拼音数据严重缺失: {has_pinyin}/{total} ({rate*100:.1f}%)")
        if auto_repair and _HAS_PYPINYIN:
            print("[items_i18n] 正在自动修复拼音数据...")
            try:
                result = repair_pinyin_data()
                print(f"[items_i18n] ✅ 拼音修复完成: {result['repaired']} 条 (耗时 {result['elapsed']:.1f}s)")
                return {'status': 'repaired', 'result': result}
            except Exception as e:
                print(f"[items_i18n] 拼音修复失败: {e}")
                return {'status': 'repair_failed', 'error': str(e)}
        else:
            print("[items_i18n] 提示: 运行以下命令修复拼音:")
            print("  python -c \"from data.items_i18n import repair_pinyin_data; repair_pinyin_data()\"")
            return {'status': 'needs_repair', 'missing': missing}
    
    elif missing > 0:  # 有少量缺失
        print(f"[items_i18n] 拼音数据基本完整: {has_pinyin}/{total} ({rate*100:.1f}%), 缺失 {missing} 条")
        if auto_repair and _HAS_PYPINYIN and missing < 100:
            # 自动修复少量缺失
            try:
                result = repair_pinyin_data()
                print(f"[items_i18n] 已修复 {result['repaired']} 条拼音")
                return {'status': 'repaired', 'result': result}
            except Exception:
                pass
        return {'status': 'good_with_minor_issues', 'missing': missing}
    
    else:  # 完全完整
        print(f"[items_i18n] 数据库检查通过: {total} 条记录，拼音完整率 100%")
        return {'status': 'ok', 'total': total, 'pinyin_complete': True}


# ============================================================
# 命令行入口
# ============================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ('--build', '-b'):
            build_all_items_db()
        elif cmd in ('--stats', '-s'):
            stats = get_db_stats()
            if stats['exists']:
                print(f"全物品数据库: {DB_PATH}")
                print(f"  总物品数: {stats['total']}")
                weapon_total = stats.get('weapon_total', 0)
                weapon_detail = stats.get('weapon_detail', {})
                print(f"  武器合计: {weapon_total} 个 "
                      f"(主武器 {weapon_detail.get('Primary', 0)}, "
                      f"副武器 {weapon_detail.get('Secondary', 0)}, "
                      f"近战 {weapon_detail.get('Melee', 0)}, "
                      f"Archwing枪 {weapon_detail.get('Arch-Gun', 0)}, "
                      f"Archwing近战 {weapon_detail.get('Arch-Melee', 0)})")
                print(f"  有中文翻译: {stats['has_cn']}")
                print(f"  文件大小: {stats['db_size']/1024:.1f} KB")
                print(f"  最后更新: {stats['db_mtime']}")
                print(f"  数据源: {stats.get('source', 'N/A')}")
                print(f"  分类统计:")
                for cat, count in stats.get('categories', {}).items():
                    print(f"    {cat}: {count}")
            else:
                print("全物品数据库不存在")
        elif cmd in ('--search', '-q') and len(sys.argv) > 2:
            for r in search_items(sys.argv[2], limit=20):
                print(f"  {r['zh_name']}  ←→  {r['en_name']}  [{r['category']}]")
        elif cmd in ('--categories', '-c'):
            cats = get_categories()
            print(f"物品分类 ({len(cats)} 种):")
            for c in cats:
                print(f"  {c}")
        elif cmd in ('--check-pinyin', '--check'):
            # 检查拼音完整性
            print("[items_i18n] 检查拼音数据完整性...")
            result = init_database_check(auto_repair=False)
            print(f"\n检查结果: {result}")
        elif cmd in ('--repair-pinyin', '--repair'):
            # 修复拼音数据
            if not _HAS_PYPINYIN:
                print("[items_i18n] ❌ pypinyin 未安装，无法修复")
                sys.exit(1)
            print("[items_i18n] 开始修复拼音数据...")
            try:
                result = repair_pinyin_data()
                print(f"\n✅ 修复完成: {result['repaired']}/{result['total']} 条 (耗时 {result['elapsed']:.1f}s)")
            except Exception as e:
                print(f"\n❌ 修复失败: {e}")
                sys.exit(1)
        else:
            print("用法:")
            print("  python items_i18n.py --build           构建/重建全物品数据库")
            print("  python items_i18n.py --stats           查看数据库统计")
            print("  python items_i18n.py --search <词>      搜索物品")
            print("  python items_i18n.py --categories       查看分类")
            print("  python items_i18n.py --check-pinyin     检查拼音完整性")
            print("  python items_i18n.py --repair-pinyin    修复拼音数据")
    else:
        # 默认行为：检查并初始化
        print("[items_i18n] 启动数据库完整性检查...")
        result = init_database_check(auto_repair=True)
        
        if result['status'] == 'ok':
            print(f"[items_i18n] ✅ 数据库状态正常 ({result['total']} 条记录)")
        elif result['status'] == 'repaired':
            print(f"[items_i18n] ✅ 已自动修复拼音数据")
        elif result['status'] == 'missing':
            print("[items_i18n] ℹ 数据库将在首次使用时创建")
        else:
            print(f"[items_i18n] ⚠ 数据库状态: {result['status']}")
