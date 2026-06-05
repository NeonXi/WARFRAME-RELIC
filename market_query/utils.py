"""
Utility functions for WM Item Search module
"""

import os
import sqlite3
from collections import OrderedDict


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


def format_slug(name):
    """Convert item name to warframe.market slug format using local DB lookup"""
    cached = _cache_get(name)
    if cached:
        return cached
    
    slug = _find_slug_in_db(name)
    if not slug:
        slug = _generate_slug(name)
    
    _cache_set(name, slug)
    return slug


def _find_slug_in_db(name):
    """Find slug from local wm_prices.db database"""
    db_path = get_data_path('wm_prices.db')
    if not os.path.exists(db_path):
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Exact match first
        cursor.execute("SELECT slug FROM item_prices WHERE en_name = ?", (name,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row[0]
        
        # Fallback: LIKE match
        cursor.execute("SELECT slug FROM item_prices WHERE en_name LIKE ?", (f"%{name}%",))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _generate_slug(name):
    """Generate slug from name (fallback when not in DB)"""
    clean = name.lower().strip().replace('_', ' ').replace('-', ' ')
    clean = ' '.join(clean.split())
    parts = clean.split()
    
    variants = [clean.replace(' ', '-')]
    
    if 'prime' in parts:
        others = [p for p in parts if p != 'prime']
        if others:
            variants.append(f"{others[0]}-prime-{'-'.join(others[1:])}")
            variants.append('-'.join(others) + '-prime')
    
    if 'blueprint' in parts:
        others = [p for p in parts if p != 'blueprint']
        variants.append('-'.join(others))
    
    return variants[0]


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
        'online': '#00ff88',
        'ingame': '#00d9ff',
        'offline': '#666666',
        'away': '#ffaa00'
    }.get(status, '#ffffff')