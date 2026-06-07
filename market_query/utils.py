"""
Utility functions for WM Item Search module
"""

import os
import sqlite3
from collections import OrderedDict
from core.theme_proxy import (
    STATUS_ONLINE, STATUS_INGAME, STATUS_OFFLINE, STATUS_AWAY, CYBER_TEXT,
)


# ─── Slug cache (LRU, max 500 entries) ────────────────────
_MAX_CACHE_SIZE = 500
_item_slug_cache = OrderedDict()


def _cache_get(key):
    """Get from cache, moving to end (LRU)"""
    if key in _item_slug_cache:
        _item_slug_cache.move_to_end(key)
        return _item_slug_cache[key]
    return None


def _cache_set(key, value):
    """Set cache, evict oldest if full"""
    if key in _item_slug_cache:
        _item_slug_cache.move_to_end(key)
    _item_slug_cache[key] = value
    if len(_item_slug_cache) > _MAX_CACHE_SIZE:
        _item_slug_cache.popitem(last=False)


# ─── Path utilities ────────────────────────────────────────


def get_data_path(filename):
    """Get path to data file in parent directory"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', filename)


# ─── Slug resolution ──────────────────────────────────────


def _name_to_slug(en_name: str) -> str:
    """将英文物品名转换为 warframe.market slug。

    规则：
      - 全小写
      - 空格替换为下划线
      - 移除特殊字符
    """
    slug = en_name.lower()
    slug = slug.replace('\n', ' ').replace('\r', '')
    slug = slug.replace("'", "")
    slug = slug.replace('"', '')
    slug = slug.replace(" & ", "_")
    slug = slug.replace("&", "")
    slug = slug.replace(" ", "_")
    slug = slug.replace("-", "_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def format_slug(name):
    """Convert item name to warframe.market slug format using local DB lookup"""
    cached = _cache_get(name)
    if cached:
        return cached

    slug = _find_slug_in_db(name)
    if not slug:
        slug = _name_to_slug(name)

    _cache_set(name, slug)
    return slug


def _find_slug_in_db(name):
    """Find slug from warframe.db market_items table"""
    db_path = get_data_path('warframe.db')
    if not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()

        # Exact match first
        cursor.execute("SELECT slug FROM market_items WHERE en_name = ?", (name,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row[0]

        # Fallback: LIKE match with shortest name first (best match)
        cursor.execute(
            "SELECT slug FROM market_items WHERE en_name LIKE ? ORDER BY LENGTH(en_name) ASC LIMIT 1",
            (f"%{name}%",)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


# ─── Status helpers ────────────────────────────────────────


def get_status_text(status):
    """Convert status code to human readable text"""
    return {
        'online': '在线',
        'ingame': '游戏中',
        'offline': '离线',
        'away': '离开'
    }.get(status, status)


def get_status_color(status):
    """Get color code for status"""
    return {
        'online': STATUS_ONLINE,
        'ingame': STATUS_INGAME,
        'offline': STATUS_OFFLINE,
        'away': STATUS_AWAY
    }.get(status, CYBER_TEXT)