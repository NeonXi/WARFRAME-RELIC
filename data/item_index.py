"""
全物品中英文对照数据库模块 (item_index.py)

数据来源: warframe.db 统一数据库
  - items 表 → 全物品数据（name, zh_name, category, type, tradable 等）
  - item_translations 表 → 多语言翻译
  - market_items 表 → 市场物品（含 zh_pinyin）

用法:
  from data.item_index import search_items, suggest_items, translate_item, get_db_stats
"""

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# ===== 路径 =====
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'warframe.db')  # 统一数据库

# ===== 拼音支持 =====
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
    pyqtSignal = None
    QObject = object


# ============================================================
# 字段映射: warframe.db → item_index 旧字段名
# ============================================================
# warframe.db items 表字段:
#   unique_name, name, zh_name, type, category, tradable, is_prime, ...
# 旧 item_index.db items 表字段:
#   unique_name, en_name, zh_name, category, item_type, is_tradable, ...

def _get_conn():
    """获取 warframe.db 连接。"""
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _row_to_old_format(row: dict) -> dict:
    """将 warframe.db 行转换为旧 item_index.db 格式（兼容调用方）。"""
    return {
        'id': row.get('rowid', 0),
        'unique_name': row.get('unique_name', ''),
        'en_name': row.get('name', ''),       # name → en_name
        'zh_name': row.get('zh_name', ''),
        'category': row.get('category', ''),
        'item_type': row.get('type', ''),     # type → item_type
        'is_tradable': row.get('tradable', 0),
        'is_prime': row.get('is_prime', 0),
        'rarity': row.get('rarity', ''),
        'mr_requirement': row.get('mr_requirement', 0),
        'image_name': row.get('image_name', ''),
        'description_zh': row.get('description_zh', ''),
        'description_en': row.get('description', ''),
    }


# ============================================================
# 搜索 API
# ============================================================

def search_items(query: str,
                 search_field: str = 'all',
                 category: str = None,
                 is_prime: bool = None,
                 is_tradable: bool = None,
                 limit: int = 50) -> list[dict]:
    """全物品搜索（从 warframe.db）。"""
    conn = _get_conn()
    if conn is None:
        return []

    conn.row_factory = sqlite3.Row

    sql = "SELECT * FROM items WHERE 1=1"
    params = []

    if query:
        if search_field == 'zh':
            sql += " AND zh_name LIKE ?"
            params.append(f"%{query}%")
        elif search_field == 'en':
            sql += " AND name LIKE ?"
            params.append(f"%{query}%")
        elif search_field == 'unique':
            sql += " AND unique_name LIKE ?"
            params.append(f"%{query}%")
        else:  # all
            sql += " AND (zh_name LIKE ? OR name LIKE ? OR unique_name LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

    if category:
        sql += " AND category = ?"
        params.append(category)

    if is_prime is not None:
        sql += " AND is_prime = ?"
        params.append(int(is_prime))

    if is_tradable is not None:
        sql += " AND tradable = ?"
        params.append(int(is_tradable))

    sql += " ORDER BY category, zh_name LIMIT ?"
    params.append(limit)

    cur = conn.cursor()
    cur.execute(sql, params)
    results = [_row_to_old_format(dict(row)) for row in cur.fetchall()]
    conn.close()
    results = _filter_relic_refinements(results)
    return results


def _is_chinese_query(query: str) -> bool:
    """判断查询是否为中文。"""
    for ch in query:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return True
    return False


# 遗物精炼标签
_REFINEMENT_TAGS = {'Intact', 'Exceptional', 'Flawless', 'Radiant'}
_RELIC_ERAS = {'Lith', 'Meso', 'Neo', 'Axi', 'Requiem', 'Vanguard'}


def _filter_relic_refinements(results: list[dict]) -> list[dict]:
    """过滤遗物精炼版本，只保留 Intact（最基础版本）。

    遗物在 items 表中有 4 个精炼状态（Intact/Exceptional/Flawless/Radiant），
    搜索结果只需保留 Intact 版本，避免同一遗物重复出现。
    """
    if not results:
        return results

    filtered = []
    for r in results:
        en_name = r.get('en_name', '')
        words = en_name.split()
        # 匹配 "Era Code State" 格式的遗物，如 "Axi A1 Exceptional"
        if (len(words) >= 3
                and words[0] in _RELIC_ERAS
                and words[-1] in _REFINEMENT_TAGS):
            # 只保留 Intact 版本
            if words[-1] != 'Intact':
                continue
        filtered.append(r)

    return filtered


def _search_by_field(conn, q: str, search_field: str, match_field: str,
                     results: list, seen: set, limit: int):
    """在指定字段上执行三级匹配搜索（精确 > 前缀 > 包含）。"""
    is_cn = (search_field == 'zh_name')
    remain = limit - len(results)

    # 第1级：精确匹配
    if is_cn:
        rows = conn.execute(
            f"SELECT zh_name, name AS en_name, category FROM items WHERE {search_field} = ? LIMIT ?",
            (q, remain)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT zh_name, name AS en_name, category FROM items WHERE LOWER({search_field}) = ? LIMIT ?",
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
                f"SELECT zh_name, name AS en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} != ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"{q}%", q, remain)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT zh_name, name AS en_name, category FROM items "
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
                f"SELECT zh_name, name AS en_name, category FROM items "
                f"WHERE {search_field} LIKE ? AND {search_field} NOT LIKE ? "
                f"ORDER BY {search_field} LIMIT ?",
                (f"%{q}%", f"{q}%", remain)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT zh_name, name AS en_name, category FROM items "
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


def suggest_items(query: str, limit: int = 20) -> list[dict]:
    """实时输入联想：自动检测输入语言，支持中/英/拼音搜索。

    - 输入中文 → 搜索中文名
    - 输入英文 → 搜索英文名 + market_items.zh_pinyin
    - 精确匹配 > 前缀匹配 > 包含匹配

    Args:
        query: 用户输入（英文/中文/拼音均可）
        limit: 返回数量上限

    Returns:
        [{zh_name, en_name, category, match_quality, match_field}, ...]
    """
    if not query or not query.strip():
        return []

    q = query.strip()
    conn = _get_conn()
    if conn is None:
        return []

    conn.row_factory = sqlite3.Row

    results = []
    seen = set()

    if _is_chinese_query(q):
        _search_by_field(conn, q, 'zh_name', 'zh', results, seen, limit)
    else:
        _search_by_field(conn, q, 'name', 'en', results, seen, limit)
        # 拼音搜索：从 market_items 表
        _search_by_pinyin(conn, q, results, seen, limit)
        quality_order = {'exact': 0, 'prefix': 1, 'contains': 2}
        results.sort(key=lambda x: quality_order.get(x['match_quality'], 99))

    conn.close()
    results = _filter_relic_refinements(results)
    return results[:limit]


def _search_by_pinyin(conn, q: str, results: list, seen: set, limit: int):
    """从 items 表的 zh_pinyin 字段拼音搜索。"""
    remain = limit - len(results)
    if remain <= 0:
        return

    try:
        # 包含匹配拼音
        rows = conn.execute(
            "SELECT zh_name, name AS en_name, category FROM items "
            "WHERE zh_pinyin LIKE ? LIMIT ?",
            (f"%{q.lower()}%", remain)
        ).fetchall()
        for r in rows:
            key = (r['en_name'] + r['zh_name']).lower()
            if key not in seen:
                seen.add(key)
                results.append({
                    'zh_name': r['zh_name'], 'en_name': r['en_name'],
                    'category': r['category'], 'match_quality': 'contains',
                    'match_field': 'py',
                })
    except Exception:
        pass


def translate_item(name: str) -> Optional[dict]:
    """精确翻译（中→英 或 英→中）。

    Returns:
        dict: {zh_name, en_name, category, ...} 或 None
    """
    conn = _get_conn()
    if conn is None:
        return None

    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM items WHERE zh_name = ? OR name = ? LIMIT 1",
        (name, name)
    ).fetchone()
    conn.close()
    return _row_to_old_format(dict(row)) if row else None


def get_categories() -> list[str]:
    """获取所有物品分类列表。"""
    conn = _get_conn()
    if conn is None:
        return []
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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cur = conn.cursor()

        total = cur.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        has_cn = cur.execute(
            "SELECT COUNT(*) FROM items WHERE zh_name != '' AND zh_name != name"
        ).fetchone()[0]

        cat_rows = cur.execute(
            "SELECT category, COUNT(*) FROM items GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall()
        categories = dict(cat_rows)

        # 元信息
        updated_at = ''
        source = ''
        try:
            meta_rows = cur.execute("SELECT key, value FROM db_meta").fetchall()
            for key, value in meta_rows:
                if key == 'build_time':
                    updated_at = value
                elif key == 'source':
                    source = value
        except Exception:
            pass

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
# 构建函数（已迁移到 build_warframe_db.py，保留伪代码接口）
# ============================================================

def build_all_items_db(*args, **kwargs) -> dict:
    """[已废弃] 构建 item_index.db。数据构建已迁移到 build_warframe_db.py。

    此函数保留为兼容接口，实际由 data_pipeline 调用 build_warframe_db.build() 完成。
    """
    print("[item_index] build_all_items_db 已废弃，请使用 build_warframe_db.build()")
    return {'total': 0, 'has_cn': 0, 'categories': {}}


def rebuild_all_items_db(*args, **kwargs) -> dict:
    """[已废弃] 重建 item_index.db。"""
    print("[item_index] rebuild_all_items_db 已废弃，请使用 build_warframe_db.build()")
    return {'total': 0, 'has_cn': 0, 'categories': {}}


def auto_rebuild_items_db(silent: bool = True) -> bool:
    """[已废弃] 自动重建全物品数据库。"""
    print("[item_index] auto_rebuild_items_db 已废弃，数据构建由 pipeline 完成")
    return True


def init_database_check(auto_repair: bool = True) -> dict:
    """初始化时检查数据库完整性。"""
    if not os.path.exists(DB_PATH):
        return {'status': 'missing', 'action': 'will_create_on_first_update'}
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
        if total == 0:
            return {'status': 'empty', 'action': 'rebuild_recommended'}
        return {'status': 'ok', 'total': total}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def repair_pinyin_data() -> dict:
    """[已废弃] 修复拼音数据。拼音数据现在在 build_warframe_db 中生成。"""
    print("[item_index] repair_pinyin_data 已废弃，拼音数据在 build_warframe_db 中生成")
    return {'total': 0, 'repaired': 0, 'elapsed': 0}


def check_pinyin_integrity() -> dict:
    """[已废弃] 检查拼音完整性。"""
    return {'total': 0, 'has_pinyin': 0, 'missing_pinyin': 0, 'integrity_rate': 1.0}


# ============================================================
# Worker（已废弃，保留伪代码接口）
# ============================================================

if _HAS_PYQT:
    class ItemsI18nUpdateWorker(QObject):
        """[已废弃] 后台线程：重建全物品中英对照数据库。"""

        step_changed = pyqtSignal(int, str)
        log = pyqtSignal(str, str)
        progress_pct = pyqtSignal(int)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, silent: bool = False):
            super().__init__()
            self.silent = silent

        def run(self):
            self.error.emit("ItemsI18nUpdateWorker 已废弃，数据构建由 pipeline 完成")


# ============================================================
# 命令行入口
# ============================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ('--stats', '-s'):
            stats = get_db_stats()
            if stats['exists']:
                print(f"统一数据库: {DB_PATH}")
                print(f"  总物品数: {stats['total']}")
                print(f"  有中文翻译: {stats['has_cn']}")
                print(f"  文件大小: {stats['db_size']/1024:.1f} KB")
                print(f"  最后更新: {stats['db_mtime']}")
                print(f"  分类统计:")
                for cat, count in stats.get('categories', {}).items():
                    print(f"    {cat}: {count}")
            else:
                print("数据库不存在")
        elif cmd in ('--search', '-q') and len(sys.argv) > 2:
            for r in search_items(sys.argv[2], limit=20):
                print(f"  {r['zh_name']}  <->  {r['en_name']}  [{r['category']}]")
        elif cmd in ('--suggest',) and len(sys.argv) > 2:
            for r in suggest_items(sys.argv[2], limit=20):
                print(f"  {r['zh_name']}  <->  {r['en_name']}  [{r['category']}]  ({r['match_quality']})")
        elif cmd in ('--categories', '-c'):
            cats = get_categories()
            print(f"物品分类 ({len(cats)} 种):")
            for c in cats:
                print(f"  {c}")
        elif cmd in ('--check',):
            result = init_database_check(auto_repair=False)
            print(f"检查结果: {result}")
        else:
            print("用法:")
            print("  python item_index.py --stats           查看数据库统计")
            print("  python item_index.py --search <词>      搜索物品")
            print("  python item_index.py --suggest <词>     输入联想")
            print("  python item_index.py --categories       查看分类")
            print("  python item_index.py --check            检查数据库")
    else:
        result = init_database_check(auto_repair=True)
        if result['status'] == 'ok':
            print(f"[item_index] 数据库状态正常 ({result['total']} 条记录)")
        elif result['status'] == 'missing':
            print("[item_index] 数据库将在首次数据更新时创建")
        else:
            print(f"[item_index] 数据库状态: {result['status']}")
