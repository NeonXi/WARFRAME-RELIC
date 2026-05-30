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
import sqlite3
import time
from datetime import datetime
from typing import Optional

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
    UNIQUE(zh_name, en_name)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_items_zh ON items(zh_name);
CREATE INDEX IF NOT EXISTS idx_items_en ON items(en_name);
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
    # 第6步: 写入数据库
    # ============================================================
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM items")
    cur = conn.cursor()

    inserted = 0
    has_cn = 0
    has_desc = 0
    category_count = {}
    type_count = {}

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

        try:
            cur.execute(
                """INSERT INTO items
                   (unique_name, zh_name, en_name, category, item_type,
                    is_tradable, is_prime, rarity, mr_requirement, image_name,
                    description_zh, description_en)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
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
                )
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass

    # 元信息
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('total', ?)", (str(inserted),))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('has_cn', ?)", (str(has_cn),))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('has_desc', ?)", (str(has_desc),))
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('source', 'zh_en_dict.json (主) + WFCD All.json/i18n.json (补充)')")
    conn.execute("INSERT OR REPLACE INTO items_meta (key, value) VALUES ('updated_at', ?)", (now,))

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


def suggest_items(query: str, limit: int = 20) -> list[dict]:
    """实时输入联想：自动检测输入语言，支持中英双向搜索。

    - 输入英文 → 搜索英文名 → 返回中文翻译
    - 输入中文 → 搜索中文名 → 返回英文原文
    - 精确匹配 > 前缀匹配 > 包含匹配
    - 每个物品返回精简字段

    Args:
        query: 用户输入（英文/中文均可，大小写不敏感）
        limit: 返回数量上限

    Returns:
        [{zh_name, en_name, category, match_quality, search_mode}, ...]
        search_mode: 'en2cn' | 'cn2en'
        match_quality: 'exact' | 'prefix' | 'contains'
    """
    if not query or not query.strip():
        return []

    q = query.strip()

    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    results = []
    seen = set()

    # 检测输入语言
    is_cn = _is_chinese_query(q)
    if is_cn:
        search_field = 'zh_name'  # 搜索中文名
        search_mode = 'cn2en'     # 中文→英文
    else:
        search_field = 'en_name'  # 搜索英文名
        search_mode = 'en2cn'     # 英文→中文

    # 第1级：精确匹配
    if is_cn:
        rows = conn.execute(
            f"SELECT zh_name, en_name, category FROM items WHERE {search_field} = ? LIMIT ?",
            (q, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT zh_name, en_name, category FROM items WHERE LOWER({search_field}) = ? LIMIT ?",
            (q.lower(), limit)
        ).fetchall()
    for r in rows:
        key = (r['en_name'] + r['zh_name']).lower()
        if key not in seen:
            seen.add(key)
            results.append({
                'zh_name': r['zh_name'], 'en_name': r['en_name'],
                'category': r['category'], 'match_quality': 'exact',
                'search_mode': search_mode,
            })

    # 第2级：前缀匹配（以输入开头）
    if len(results) < limit:
        if is_cn:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} != ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"{q}%", q, limit - len(results))
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND LOWER({search_field}) != ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"{q}%", q.lower(), limit - len(results))
            ).fetchall()
        for r in rows:
            key = (r['en_name'] + r['zh_name']).lower()
            if key not in seen:
                seen.add(key)
                results.append({
                    'zh_name': r['zh_name'], 'en_name': r['en_name'],
                    'category': r['category'], 'match_quality': 'prefix',
                    'search_mode': search_mode,
                })

    # 第3级：包含匹配
    if len(results) < limit:
        if is_cn:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} NOT LIKE ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"%{q}%", f"{q}%", limit - len(results))
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT zh_name, en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} NOT LIKE ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"%{q}%", f"{q}%", limit - len(results))
            ).fetchall()
        for r in rows:
            key = (r['en_name'] + r['zh_name']).lower()
            if key not in seen:
                seen.add(key)
                results.append({
                    'zh_name': r['zh_name'], 'en_name': r['en_name'],
                    'category': r['category'], 'match_quality': 'contains',
                    'search_mode': search_mode,
                })

    conn.close()
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
        else:
            print("用法:")
            print("  python items_i18n.py --build       构建/重建全物品数据库")
            print("  python items_i18n.py --stats       查看数据库统计")
            print("  python items_i18n.py --search <词>  搜索物品")
            print("  python items_i18n.py --categories  查看分类")
    else:
        if not os.path.exists(DB_PATH):
            print("全物品数据库不存在，正在构建...")
            build_all_items_db()
        else:
            stats = get_db_stats()
            print(f"全物品数据库已存在 ({stats['total']} 个物品): {DB_PATH}")
            print("使用 --build 重建, --stats 查看统计")
