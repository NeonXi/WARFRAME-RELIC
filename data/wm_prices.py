"""
warframe.market 价格数据库模块 (wm_prices.db)

数据来源:
  - warframe.market API v2: https://api.warframe.market/v2/

关联方式:
  - 通过物品英文名 (en_name) 与 items_i18n.db 的 items 表匹配

表结构:
  item_prices:    物品价格表（仅卖价，含反压价权重机制）
  price_meta:     元信息表

权重机制:
  - 拉取前 20 个最低卖单，检测异常低价（偏离中位数 >30% 视为压价）
  - 异常低价降权（权重 = 0.1），正常价格等权
  - 计算加权均价 sell_weighted 作为推荐参考价
  - 保留 sell_top3 JSON 用于展示价格分布

API 速率限制: 每秒 3 个请求

用法:
  python wm_prices.py --fetch      拉取全量价格数据
  python wm_prices.py --stats      查看数据库统计
  python wm_prices.py --search <词> 查询物品价格
"""

import json
import os
import sqlite3
import threading
import time
import urllib.request
import urllib.error
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

try:
    from PyQt6.QtCore import pyqtSignal, QObject
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False
    pyqtSignal = None
    QObject = object

# ===== 路径 =====
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'wm_prices.db')
ITEMS_I18N_DB = os.path.join(BASE_DIR, 'items_i18n.db')

# ===== API 配置 =====
WM_API_BASE = 'https://api.warframe.market/v2'
WM_API_V1_BASE = 'https://api.warframe.market/v1'
REQUEST_INTERVAL = 0.35  # 每秒约 3 个请求，留一点余量
REQUEST_TIMEOUT = 30     # 单次请求超时

# ===== 并发配置 =====
MAX_WORKERS = 8           # 最大并发线程数（建议 6-12）
BATCH_SIZE = 200          # 每批写入数据库的数量（减少锁竞争）
RATE_LIMIT_PER_SEC = 3    # 全局限速：每秒最大请求数

# ===== 权重机制参数 =====
PRICE_ABNORMAL_THRESHOLD = 0.30  # 价格偏离中位数 > 30% 视为异常压价
ABNORMAL_WEIGHT = 0.1            # 异常价格的权重（正常为 1.0）
SELL_ORDER_SAMPLE = 20           # 拉取前 N 个卖单做权重分析

# ===== 数据库表结构 =====
SCHEMA = """
-- 物品价格表（仅卖价）
CREATE TABLE IF NOT EXISTS item_prices (
    item_id         INTEGER NOT NULL,           -- 关联 items_i18n.db items.id
    en_name         TEXT NOT NULL DEFAULT '',    -- 物品英文名（直接查询用，不依赖JOIN）
    slug            TEXT NOT NULL,               -- warframe.market 物品 slug
    sell_min        INTEGER,                     -- 最低卖价 (白金) - 前 5 中的最低
    sell_median     REAL,                        -- 卖价中位数 - 前 5 中位数
    sell_weighted   REAL,                        -- 加权卖价 (反压价后推荐参考价)
    sell_volume     INTEGER,                     -- 前 5 卖单数
    sell_top3       TEXT,                        -- 前 3 个卖价 JSON: [p1, p2, p3]
    sell_volume_full INTEGER,                    -- 该物品全量卖单数
    volume_48h      INTEGER,                     -- 48小时成交量 (来自 statistics)
    avg_price_90d   REAL,                        -- 90天加权均价
    updated_at      TEXT NOT NULL,               -- 价格更新时间
    PRIMARY KEY (item_id)
);

CREATE INDEX IF NOT EXISTS idx_prices_en_name ON item_prices(en_name);
CREATE INDEX IF NOT EXISTS idx_prices_slug ON item_prices(slug);
CREATE INDEX IF NOT EXISTS idx_prices_weighted ON item_prices(sell_weighted);
CREATE INDEX IF NOT EXISTS idx_prices_updated ON item_prices(updated_at);

-- 元信息表
CREATE TABLE IF NOT EXISTS price_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ============================================================
# 查询 API
# ============================================================

def get_price(en_name: str) -> Optional[dict]:
    """根据英文名查询物品价格。

    优先用 en_name 直接查询（wm_prices.db 自带 en_name 列），
    兼容旧数据库（通过 items_i18n.db JOIN）。

    Args:
        en_name: 物品英文名

    Returns:
        dict 或 None:
            {slug, sell_min, sell_median, sell_weighted, sell_volume,
             sell_top3, sell_volume_full, volume_48h, avg_price_90d, updated_at}
    """
    if not os.path.exists(DB_PATH):
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 尝试直接用 en_name 查询（新版数据库自带 en_name 列）
    row = conn.execute(
        "SELECT * FROM item_prices WHERE en_name = ?",
        (en_name,)
    ).fetchone()

    if row is None:
        # 精确模糊匹配（处理名称差异，如 Prime Set vs Set）
        row = conn.execute(
            "SELECT * FROM item_prices WHERE en_name LIKE ? ORDER BY LENGTH(en_name) ASC LIMIT 1",
            (f"%{en_name}%",)
        ).fetchone()

    if row is None and os.path.exists(ITEMS_I18N_DB):
        # 兼容旧数据库：通过 items_i18n JOIN 查询
        conn.execute(f"ATTACH DATABASE '{ITEMS_I18N_DB}' AS items_i18n_db")
        row = conn.execute("""
            SELECT p.* FROM item_prices p
            INNER JOIN items_i18n_db.items i ON p.item_id = i.id
            WHERE i.en_name = ?
        """, (en_name,)).fetchone()

        if row is None:
            row = conn.execute("""
                SELECT p.* FROM item_prices p
                INNER JOIN items_i18n_db.items i ON p.item_id = i.id
                WHERE i.en_name LIKE ?
                ORDER BY LENGTH(i.en_name) ASC
                LIMIT 1
            """, (f"%{en_name}%",)).fetchone()

    conn.close()
    if row is None:
        return None
    result = dict(row)
    # 解析 sell_top3 JSON
    if result.get('sell_top3'):
        try:
            result['sell_top3'] = json.loads(result['sell_top3'])
        except (json.JSONDecodeError, TypeError):
            result['sell_top3'] = []
    return result


# ============================================================
# 实时价格查询（API 优先，超时则 fallback 本地 DB）
# ============================================================

REALTIME_TIMEOUT = 2.0        # 实时查询超时秒数


def fetch_price_realtime(en_name: str, timeout: float = REALTIME_TIMEOUT) -> Optional[dict]:
    """实时通过 warframe.market API 查询物品价格。

    先从本地 DB 获取 slug，然后调用 API 获取实时卖单数据，
    使用反压价权重算法计算加权参考价。

    如果本地 DB 不存在、slug 缺失、或 API 在 timeout 秒内无响应，
    则自动 fallback 到本地 DB 缓存数据。

    Args:
        en_name: 物品英文名
        timeout: API 请求超时秒数（默认 2 秒）

    Returns:
        与 get_price() 相同的 dict，或 None
    """
    # 1. 从本地 DB 获取 slug
    slug = _get_slug(en_name)
    if not slug:
        # 无 slug 则 fallback 本地 DB
        print(f"[wm_prices] fetch_price_realtime: 无 slug for \"{en_name}\"，fallback 本地DB", flush=True)
        return get_price(en_name)

    print(f"[wm_prices] fetch_price_realtime: en_name=\"{en_name}\" → slug=\"{slug}\"", flush=True)

    # 2. 尝试实时 API 查询
    try:
        data = _http_get(
            f'{WM_API_BASE}/orders/item/{slug}',
            timeout=int(timeout)
        )
        print(f"[wm_prices] API 成功: /orders/item/{slug}", flush=True)
    except Exception as e:
        # API 失败/超时 → fallback 本地 DB
        print(f"[wm_prices] API 失败: {e} → fallback 本地DB", flush=True)
        return get_price(en_name)

    # 3. 解析实时卖单数据
    try:
        orders = data.get('payload', {}).get('orders', [])
        if not orders and isinstance(data.get('data'), list):
            orders = data['data']

        sell_prices = _extract_sell_orders(orders)
        sell_prices.sort()

        if not sell_prices:
            return get_price(en_name)

        # 反压价权重计算
        weighted_result = _compute_weighted_price(sell_prices)

        # 也尝试获取统计信息（非阻塞，失败不影响主流程）
        volume_48h = None
        avg_price_90d = None
        try:
            stats = _http_get(
                f'{WM_API_V1_BASE}/items/{slug}/statistics',
                timeout=max(int(timeout), 3)
            )
            stat_data = _parse_statistics(stats)
            volume_48h = stat_data.get('volume_48h')
            avg_price_90d = stat_data.get('avg_price_90d')
        except Exception:
            pass

        return {
            'slug': slug,
            'sell_min': weighted_result['top3'][0] if weighted_result['top3'] else None,
            'sell_median': weighted_result['median'],
            'sell_weighted': weighted_result['weighted'],
            'sell_volume': weighted_result['sample_size'],
            'sell_top3': weighted_result['top3'],
            'sell_volume_full': len(sell_prices),
            'volume_48h': volume_48h,
            'avg_price_90d': avg_price_90d,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '_source': 'realtime',
        }
    except Exception:
        # 解析失败 → fallback 本地 DB
        return get_price(en_name)


def _name_to_slug(en_name: str) -> str:
    """将英文物品名转换为 warframe.market slug。

    规则：
      - 全小写
      - 空格替换为下划线
      - 移除 & 符号及其周围空格
      - 移除单引号
    """
    slug = en_name.lower()
    slug = slug.replace("'", "")
    slug = slug.replace(" & ", "_")
    slug = slug.replace("&", "")
    slug = slug.replace(" ", "_")
    # 清理连续下划线
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _get_slug(en_name: str) -> Optional[str]:
    """从本地 DB 获取物品的 warframe.market slug。

    优先用 en_name 直接查询（新版数据库），兼容旧数据库 JOIN。
    如果本地 DB 中没有，则尝试从名称直接构造 slug。
    """
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row

            # 新版数据库：直接 en_name 查询
            row = conn.execute(
                "SELECT slug FROM item_prices WHERE en_name = ?",
                (en_name,)
            ).fetchone()

            if not row:
                # 兼容旧数据库：JOIN 查询
                conn.execute(f"ATTACH DATABASE '{ITEMS_I18N_DB}' AS items_i18n_db")
                row = conn.execute("""
                    SELECT p.slug FROM item_prices p
                    INNER JOIN items_i18n_db.items i ON p.item_id = i.id
                    WHERE i.en_name = ?
                """, (en_name,)).fetchone()

            conn.close()
            if row and row['slug']:
                return row['slug']
        except Exception:
            pass
    # 本地没有，从名称构造 slug
    constructed = _name_to_slug(en_name)
    print(f"[wm_prices] _get_slug: 本地DB无 \"{en_name}\" 的slug → 从名称构造: \"{constructed}\"", flush=True)
    return constructed


def _parse_statistics(data: dict) -> dict:
    """解析 statistics API 返回数据。"""
    result = {'volume_48h': None, 'avg_price_90d': None}
    try:
        payload = data.get('payload', {})
        closed = payload.get('statistics_closed', {})
        days_90 = closed.get('90days', [])
        hours_48 = closed.get('48hours', [])

        if hours_48:
            result['volume_48h'] = sum(h.get('volume', 0) for h in hours_48)
        if days_90:
            last = days_90[-1]
            result['avg_price_90d'] = last.get('wa_price')
    except Exception:
        pass
    return result


def get_prices_batch(en_names: list[str]) -> dict[str, dict]:
    """批量查询多个物品的价格。

    优先用 en_name 直接查询（新版数据库），兼容旧数据库 JOIN。

    Args:
        en_names: 物品英文名列表

    Returns:
        {en_name: price_dict, ...}
    """
    if not en_names or not os.path.exists(DB_PATH):
        return {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    placeholders = ','.join('?' * len(en_names))

    # 新版数据库：直接 en_name 查询
    rows = conn.execute(
        f"SELECT * FROM item_prices WHERE en_name IN ({placeholders})",
        en_names
    ).fetchall()

    if not rows and os.path.exists(ITEMS_I18N_DB):
        # 兼容旧数据库：JOIN 查询
        conn.execute(f"ATTACH DATABASE '{ITEMS_I18N_DB}' AS items_i18n_db")
        rows = conn.execute(f"""
            SELECT p.* FROM item_prices p
            INNER JOIN items_i18n_db.items i ON p.item_id = i.id
            WHERE i.en_name IN ({placeholders})
        """, en_names).fetchall()

    result = {}
    for row in rows:
        d = dict(row)
        if d.get('sell_top3'):
            try:
                d['sell_top3'] = json.loads(d['sell_top3'])
            except (json.JSONDecodeError, TypeError):
                d['sell_top3'] = []
        # 使用 en_name 列（如果存在）或需要从 items_i18n 获取
        key = d.get('en_name', '')
        if key:
            result[key] = d
        else:
            # 旧格式，需要通过 JOIN 获取 en_name
            pass

    conn.close()
    return result


def get_price_stats() -> dict:
    """获取价格数据库统计信息。"""
    if not os.path.exists(DB_PATH):
        return {
            'exists': False, 'total': 0, 'has_sell': 0, 'has_weighted': 0,
            'db_size': 0, 'db_mtime': '',
        }
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        total = cur.execute("SELECT COUNT(*) FROM item_prices").fetchone()[0]
        has_sell = cur.execute(
            "SELECT COUNT(*) FROM item_prices WHERE sell_weighted IS NOT NULL"
        ).fetchone()[0]
        has_weighted = cur.execute(
            "SELECT COUNT(*) FROM item_prices WHERE sell_weighted IS NOT NULL AND sell_min != sell_weighted"
        ).fetchone()[0]

        # 元信息
        updated_at = ''
        source = ''
        for key, value in cur.execute("SELECT key, value FROM price_meta").fetchall():
            if key == 'updated_at':
                updated_at = value
            elif key == 'source':
                source = value

        conn.close()
        stat = os.stat(DB_PATH)
        return {
            'exists': True,
            'total': total,
            'has_sell': has_sell,
            'has_weighted': has_weighted,
            'source': source,
            'updated_at': updated_at,
            'db_size': stat.st_size,
            'db_mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception as e:
        return {'exists': False, 'error': str(e)}


# ============================================================
# 价格拉取核心逻辑
# ============================================================

def _http_get(url: str, timeout: int = REQUEST_TIMEOUT) -> dict:
    """发送 GET 请求并解析 JSON。"""
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'WARFRAME-RELIC/1.0',
            'Accept': 'application/json',
            'Platform': 'pc',
        }
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read()
    resp.close()
    return json.loads(data.decode('utf-8'))


def _fetch_wm_items(log_cb=None) -> list[dict]:
    """从 warframe.market 获取全量物品列表。

    Returns:
        [{id, slug, en_name, tags, ducats, ...}, ...]
    """
    if log_cb:
        log_cb('info', '正在获取 warframe.market 全物品列表...')
    data = _http_get(f'{WM_API_BASE}/items')
    items = data.get('payload', {}).get('items', [])
    if not items and isinstance(data.get('data'), list):
        items = data['data']  # 兼容旧格式

    result = []
    for item in items:
        i18n = item.get('i18n', {})
        en_info = i18n.get('en', {}) if isinstance(i18n, dict) else {}
        result.append({
            'id': item.get('id', ''),
            'slug': item.get('slug', ''),
            'en_name': en_info.get('name', item.get('name', '')),
            'tags': item.get('tags', []),
            'ducats': item.get('ducats'),
        })

    if log_cb:
        log_cb('ok', f'获取到 {len(result)} 个 warframe.market 物品')
    return result


def _match_items(wm_items: list[dict], log_cb=None) -> list[dict]:
    """将 warframe.market 物品与本地 items_i18n.db 匹配。

    Returns:
        [{item_id, en_name, zh_name, slug, ...}, ...]
    """
    if not os.path.exists(ITEMS_I18N_DB):
        if log_cb:
            log_cb('error', 'items_i18n.db 不存在，无法匹配物品')
        return []

    conn = sqlite3.connect(ITEMS_I18N_DB)
    conn.row_factory = sqlite3.Row

    # 构建 en_name → item 映射
    all_items = conn.execute(
        "SELECT id, en_name, zh_name, category, is_tradable FROM items"
    ).fetchall()

    # 精确匹配索引
    en_map = {row['en_name'].lower(): dict(row) for row in all_items}

    matched = []
    exact_count = 0
    fuzzy_count = 0

    for wm in wm_items:
        wm_en = wm['en_name'].lower().strip()
        if not wm_en:
            continue

        # 精确匹配
        if wm_en in en_map:
            item = en_map[wm_en]
            matched.append({
                'item_id': item['id'],
                'en_name': item['en_name'],
                'zh_name': item['zh_name'],
                'category': item['category'],
                'is_tradable': item['is_tradable'],
                'slug': wm['slug'],
                'tags': wm['tags'],
                'ducats': wm['ducats'],
            })
            exact_count += 1
        else:
            # 模糊匹配：尝试多种变体
            # 1. Prime Set → Set 变体
            if 'prime' in wm_en and 'set' in wm_en:
                alt_name = wm_en.replace(' prime set', ' set').replace(' set', ' prime set')
                if alt_name in en_map:
                    item = en_map[alt_name]
                    matched.append({
                        'item_id': item['id'],
                        'en_name': item['en_name'],
                        'zh_name': item['zh_name'],
                        'category': item['category'],
                        'is_tradable': item['is_tradable'],
                        'slug': wm['slug'],
                        'tags': wm['tags'],
                        'ducats': wm['ducats'],
                    })
                    fuzzy_count += 1
                    continue

            # 2. 仅名称匹配（不含 Set 后缀）
            base = wm_en.replace(' set', '')
            if base in en_map:
                item = en_map[base]
                matched.append({
                    'item_id': item['id'],
                    'en_name': item['en_name'],
                    'zh_name': item['zh_name'],
                    'category': item['category'],
                    'is_tradable': item['is_tradable'],
                    'slug': wm['slug'],
                    'tags': wm['tags'],
                    'ducats': wm['ducats'],
                })
                fuzzy_count += 1

    conn.close()

    if log_cb:
        log_cb('ok', f'物品匹配完成: 精确 {exact_count}, 模糊 {fuzzy_count}, '
                     f'总计 {len(matched)} / {len(wm_items)}')

    return matched


# ============================================================
# 反压价权重算法
# ============================================================

def _extract_sell_orders(orders_data: list) -> list[int]:
    """从 API 返回的订单数据中提取卖价列表（仅 sell 类型）。"""
    sells = []
    for o in orders_data:
        order_type = o.get('order_type') or o.get('type', '')
        if order_type == 'sell':
            platinum = o.get('platinum', 0)
            if platinum and platinum > 0:
                sells.append(platinum)
    return sells


def _compute_weighted_price(sell_prices: list[int]) -> dict:
    """对卖价列表应用反压价权重机制，计算加权参考价。

    算法:
        1. 取前 SELL_ORDER_SAMPLE 个最低卖价
        2. 计算中位数
        3. 价格低于中位数 * (1 - PRICE_ABNORMAL_THRESHOLD) 视为异常压价
        4. 异常价格权重 = ABNORMAL_WEIGHT，正常价格权重 = 1.0
        5. 计算加权平均 = sum(price * weight) / sum(weight)

    Args:
        sell_prices: 卖价列表（已排序升序）

    Returns:
        {
            weighted: float,         # 加权参考价
            median: float,           # 中位数
            abnormal_count: int,     # 被标记为异常的价格数量
            abnormal_prices: list,   # 异常价格列表
            top3: list,              # 前 3 最低价
            sample_size: int,        # 实际采样的卖单数
        }
    """
    if not sell_prices:
        return {
            'weighted': None, 'median': None,
            'abnormal_count': 0, 'abnormal_prices': [],
            'top3': [], 'sample_size': 0,
        }

    # 取前 N 个最低价做分析
    sample = sell_prices[:SELL_ORDER_SAMPLE]
    n = len(sample)

    # 中位数
    mid = n // 2
    if n % 2 == 0:
        median = (sample[mid - 1] + sample[mid]) / 2.0
    else:
        median = float(sample[mid])

    # 异常检测阈值
    lower_bound = median * (1 - PRICE_ABNORMAL_THRESHOLD)

    # 加权计算
    total_weight = 0.0
    weighted_sum = 0.0
    abnormal_prices = []

    for price in sample:
        if price < lower_bound:
            # 异常低价（可能是压价）
            weight = ABNORMAL_WEIGHT
            abnormal_prices.append(price)
        else:
            weight = 1.0
        total_weight += weight
        weighted_sum += price * weight

    weighted = round(weighted_sum / total_weight, 1) if total_weight > 0 else median

    return {
        'weighted': weighted,
        'median': round(median, 1),
        'abnormal_count': len(abnormal_prices),
        'abnormal_prices': abnormal_prices,
        'top3': sample[:3],
        'sample_size': n,
    }


def _fetch_sell_orders_full(slug: str) -> dict:
    """获取单个物品的卖价数据（全量卖单，用于权重分析）。

    调用 /v2/orders/item/{slug} 获取全部订单，仅提取 sell 类型。

    Returns:
        {
            sell_prices: [int, ...],      # 排序后的卖价列表（升序）
            sell_volume_full: int,         # 全量卖单数
        }
    """
    result = {'sell_prices': [], 'sell_volume_full': 0}
    try:
        data = _http_get(f'{WM_API_BASE}/orders/item/{slug}')
        orders = data.get('payload', {}).get('orders', [])
        if not orders and isinstance(data.get('data'), list):
            orders = data['data']

        sell_prices = _extract_sell_orders(orders)
        sell_prices.sort()

        result['sell_prices'] = sell_prices
        result['sell_volume_full'] = len(sell_prices)

    except Exception:
        pass  # 单个物品失败不影响整体

    return result


def _fetch_item_statistics(slug: str) -> dict:
    """获取单个物品的历史统计（成交量/均价）。

    Returns:
        {volume_48h, avg_price_90d}
    """
    result = {'volume_48h': None, 'avg_price_90d': None}
    try:
        data = _http_get(f'{WM_API_V1_BASE}/items/{slug}/statistics')
        payload = data.get('payload', {})

        closed = payload.get('statistics_closed', {})
        days_90 = closed.get('90days', [])
        hours_48 = closed.get('48hours', [])

        # 48h 成交量
        if hours_48:
            result['volume_48h'] = sum(h.get('volume', 0) for h in hours_48)

        # 90天加权均价（取最后一条的 wa_price）
        if days_90:
            last = days_90[-1]
            result['avg_price_90d'] = last.get('wa_price')

    except Exception:
        pass  # 单个物品失败不影响整体

    return result


# ============================================================
# 全局限速器（线程安全）
# ============================================================

class _RateLimiter:
    """线程安全的令牌桶限速器。"""

    def __init__(self, rate_per_sec: float = RATE_LIMIT_PER_SEC):
        self._rate = rate_per_sec
        self._interval = 1.0 / rate_per_sec
        self._lock = threading.Lock()
        self._next_available = time.monotonic()

    def acquire(self):
        """等待直到可以发送下一个请求。"""
        with self._lock:
            now = time.monotonic()
            wait = self._next_available - now
            if wait > 0:
                time.sleep(wait)
            self._next_available = time.monotonic() + self._interval


# 全局限速器实例（每个拉取任务共用）
_rate_limiter = _RateLimiter(RATE_LIMIT_PER_SEC)


def _fetch_single_item(item: dict, get_stats: bool = False) -> dict:
    """拉取单个物品的价格数据（线程安全，供线程池使用）。

    Args:
        item: 匹配后的物品字典
        get_stats: 是否同时获取历史统计

    Returns:
        {item_id, slug, sell_data, stats, success, error}
    """
    result = {
        'item_id': item['item_id'],
        'slug': item['slug'],
        'sell_data': {'sell_prices': [], 'sell_volume_full': 0},
        'stats': {'volume_48h': None, 'avg_price_90d': None},
        'success': False,
        'error': None,
    }

    try:
        # 全局限速
        _rate_limiter.acquire()

        # 获取全量卖单
        sell_data = _fetch_sell_orders_full(item['slug'])
        result['sell_data'] = sell_data

        # 可选：获取历史统计
        if get_stats:
            _rate_limiter.acquire()
            result['stats'] = _fetch_item_statistics(item['slug'])

        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def _batch_insert(cur, batch: list[dict], now: str) -> dict:
    """批量插入一批价格数据到数据库。

    Returns:
        {inserted, with_sell, with_weighted, with_stats, errors, total_abnormal}
    """
    stats = {'inserted': 0, 'with_sell': 0, 'with_weighted': 0,
             'with_stats': 0, 'errors': 0, 'total_abnormal': 0}

    for item in batch:
        fetch_result = item.get('_fetch_result', {})
        if not fetch_result.get('success'):
            stats['errors'] += 1
            continue

        sell_data = fetch_result.get('sell_data', {})
        item_stats = fetch_result.get('stats', {})
        sell_prices = sell_data.get('sell_prices', [])

        # 反压价权重计算
        w = _compute_weighted_price(sell_prices)
        stats['total_abnormal'] += w['abnormal_count']

        top3_json = json.dumps(w['top3']) if w['top3'] else None

        try:
            cur.execute(
                """INSERT INTO item_prices
                   (item_id, en_name, slug, sell_min, sell_median, sell_weighted, sell_volume,
                    sell_top3, sell_volume_full,
                    volume_48h, avg_price_90d, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item['item_id'], item.get('en_name', ''),
                    item['slug'],
                    w['top3'][0] if w['top3'] else None,
                    w['median'],
                    w['weighted'],
                    w['sample_size'],
                    top3_json,
                    sell_data.get('sell_volume_full', 0),
                    item_stats.get('volume_48h'),
                    item_stats.get('avg_price_90d'),
                    now,
                )
            )
            stats['inserted'] += 1
            if w['weighted'] is not None:
                stats['with_sell'] += 1
            if w['abnormal_count'] > 0:
                stats['with_weighted'] += 1
            if item_stats.get('avg_price_90d') is not None:
                stats['with_stats'] += 1
        except sqlite3.IntegrityError:
            stats['errors'] += 1

    return stats


def _build_price_db(matched_items: list[dict], log_cb=None, progress_cb=None,
                    max_workers: int = MAX_WORKERS, batch_size: int = BATCH_SIZE) -> dict:
    """多线程批量拉取价格（仅卖价）并写入数据库。

    流程:
        1. 使用 ThreadPoolExecutor 并发拉取每个物品的卖单数据
        2. 全局限速器控制每秒请求数不超过 API 限制
        3. 按批次写入数据库（减少锁竞争）
        4. 每 50 个物品附带拉取一次历史统计

    为什么用多线程而不是多进程:
        - 瓶颈是网络 I/O（HTTP 请求），不是 CPU
        - 线程共享内存，数据传递零开销
        - 多进程需要序列化大量数据，反而更慢

    加速原理:
        - 串行: request1 → wait → request2 → wait → ...
        - 多线程: 线程1 request1(等待中) + 线程2 request2(等待中) + ...
        - 全局限速器确保总速率不超标，但并发减少等待浪费

    Args:
        matched_items: _match_items 的结果
        log_cb: 日志回调 (level, msg)
        progress_cb: 进度回调 (current, total)
        max_workers: 最大并发线程数
        batch_size: 每批写入数量

    Returns:
        {'total': int, 'with_sell': int, 'with_weighted': int, 'with_stats': int, ...}
    """
    total = len(matched_items)
    if log_cb:
        log_cb('info', f'开始拉取 {total} 个物品的卖价数据...')
        log_cb('info', f'并发配置: {max_workers} 线程, 全局限速 {RATE_LIMIT_PER_SEC} 请求/秒')
        log_cb('info', f'预计耗时约 {total / RATE_LIMIT_PER_SEC / 60:.1f} 分钟（串行），'
                       f'多线程预计可缩短 30-50%')
        log_cb('info', f'权重机制: 偏离中位数 >{int(PRICE_ABNORMAL_THRESHOLD*100)}% 视为压价，权重降为 {ABNORMAL_WEIGHT}')

    # 初始化数据库
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM item_prices")

    # 全局统计（线程安全）
    stat_lock = threading.Lock()
    completed_count = [0]  # 用列表实现可变引用
    inserted = 0
    with_sell = 0
    with_weighted = 0
    with_stats = 0
    errors = 0
    total_abnormal = 0
    start_time = time.time()
    last_log_time = [start_time]

    # 创建写入游标
    cur = conn.cursor()

    # 收集待写入的批次
    pending_batch = []  # [(item, fetch_result), ...]

    def _flush_batch():
        """将待写入批次刷入数据库（调用方需持有 stat_lock）。"""
        nonlocal inserted, with_sell, with_weighted, with_stats, errors, total_abnormal
        if not pending_batch:
            return
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        batch_stats = _batch_insert(cur, pending_batch, now)
        inserted += batch_stats['inserted']
        with_sell += batch_stats['with_sell']
        with_weighted += batch_stats['with_weighted']
        with_stats += batch_stats['with_stats']
        errors += batch_stats['errors']
        total_abnormal += batch_stats['total_abnormal']
        conn.commit()
        pending_batch.clear()

    def _log_progress():
        """输出进度日志（调用方需持有 stat_lock）。"""
        now_t = time.time()
        if now_t - last_log_time[0] < 15:
            return
        last_log_time[0] = now_t
        elapsed = now_t - start_time
        cnt = completed_count[0]
        rate = cnt / elapsed if elapsed > 0 else 0
        eta = (total - cnt) / rate if rate > 0 else 0
        if log_cb:
            log_cb('info',
                   f'进度: {cnt}/{total} ({100*cnt//total}%)  '
                   f'速度: {rate:.1f} 个/秒  预计剩余: {eta:.0f}s  '
                   f'已写入: {inserted}  检测压价: {total_abnormal}  错误: {errors}')

    # 提交任务到线程池
    if log_cb:
        log_cb('info', f'启动 {max_workers} 个工作线程...')

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 分批提交 future（避免一次性提交太多）
        future_to_idx = {}
        submit_batch = 500  # 每批提交 500 个 future

        for start in range(0, total, submit_batch):
            end = min(start + submit_batch, total)
            chunk = matched_items[start:end]

            # 提交本批任务
            for i, item in enumerate(chunk):
                idx = start + i
                # 每 50 个附带统计请求
                need_stats = (idx % 50 == 0)
                future = executor.submit(_fetch_single_item, item, need_stats)
                future_to_idx[future] = idx

            # 收集完成结果
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                item = matched_items[idx]
                try:
                    fetch_result = future.result()
                except Exception as e:
                    fetch_result = {
                        'item_id': item['item_id'], 'slug': item['slug'],
                        'sell_data': {'sell_prices': [], 'sell_volume_full': 0},
                        'stats': {}, 'success': False, 'error': str(e),
                    }

                # 挂载结果到 item 上，加入待写入批次
                item['_fetch_result'] = fetch_result

                with stat_lock:
                    pending_batch.append(item)
                    completed_count[0] += 1

                    # 批次满了就刷入数据库
                    if len(pending_batch) >= batch_size:
                        _flush_batch()

                    # 进度回调
                    if progress_cb:
                        progress_cb(completed_count[0], total)

                    _log_progress()

            # 清理已完成 future
            future_to_idx.clear()

        # 刷入剩余数据
        with stat_lock:
            _flush_batch()

    # 写入元信息
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('source', 'warframe.market API v2')")
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('total', ?)", (str(inserted),))
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('with_sell', ?)", (str(with_sell),))
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('with_weighted', ?)", (str(with_weighted),))
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('with_stats', ?)", (str(with_stats),))
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('total_abnormal', ?)", (str(total_abnormal),))
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('updated_at', ?)", (now,))
    conn.execute("INSERT OR REPLACE INTO price_meta (key, value) VALUES ('concurrency', ?)",
                 (f'{max_workers} threads, rate_limit={RATE_LIMIT_PER_SEC}/s',))

    conn.commit()
    conn.close()

    elapsed = time.time() - start_time
    result = {
        'total': inserted, 'with_sell': with_sell, 'with_weighted': with_weighted,
        'with_stats': with_stats, 'errors': errors,
        'total_abnormal': total_abnormal, 'elapsed': elapsed,
        'max_workers': max_workers,
    }

    if log_cb:
        log_cb('ok', f'========== 价格数据拉取完成 (总耗时 {elapsed:.1f}s, {max_workers} 线程) ==========')
        log_cb('ok', f'  总计写入: {inserted} 个物品')
        log_cb('ok', f'  有卖价: {with_sell} ({100*with_sell//max(inserted,1)}%)')
        log_cb('ok', f'  检测到压价: {total_abnormal} 次 (涉及 {with_weighted} 个物品)')
        log_cb('ok', f'  有历史统计: {with_stats} ({100*with_stats//max(inserted,1)}%)')
        log_cb('ok', f'  错误: {errors}')
        log_cb('ok', f'  平均速度: {total/elapsed:.1f} 个/秒')

    return result


def fetch_all_prices(log_cb=None, progress_cb=None) -> dict:
    """完整的价格拉取流程：获取物品列表 → 匹配 → 拉取价格 → 写入数据库。

    Args:
        log_cb: 日志回调 (level, msg)  - level: 'info'|'ok'|'warn'|'error'
        progress_cb: 进度回调 (current, total)

    Returns:
        dict: 结果统计
    """
    # 步骤 1: 获取 warframe.market 全物品
    wm_items = _fetch_wm_items(log_cb)

    # 步骤 2: 与本地物品数据库匹配
    matched = _match_items(wm_items, log_cb)

    if not matched:
        if log_cb:
            log_cb('error', '没有匹配到任何物品，请先确保 items_i18n.db 已构建')
        return {'total': 0, 'error': 'no_match'}

    # 步骤 3: 批量拉取价格并写入
    result = _build_price_db(matched, log_cb, progress_cb)
    return result


# ============================================================
# PyQt6 Worker（后台线程）
# ============================================================

if _HAS_PYQT:

    class PriceFetchWorker(QObject):
        """后台线程：拉取 warframe.market 卖价数据（含反压价权重，多线程加速）。

        信号:
            step_changed(int, str): 步骤变化
            log(str, str): 日志消息 (level, msg)
            progress_pct(int): 进度百分比
            progress_detail(int, int): 进度详情 (current, total)
            finished(dict): 完成 (结果统计)
            error(str): 错误
        """

        step_changed = pyqtSignal(int, str)
        log = pyqtSignal(str, str)
        progress_pct = pyqtSignal(int)
        progress_detail = pyqtSignal(int, int)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, max_workers: int = MAX_WORKERS, batch_size: int = BATCH_SIZE):
            super().__init__()
            self._cancelled = False
            self._max_workers = max_workers
            self._batch_size = batch_size

        def cancel(self):
            self._cancelled = True

        def run(self):
            start_time = time.time()

            def _log(level, msg):
                if not self._cancelled:
                    self.log.emit(level, msg)

            def _progress(current, total):
                if not self._cancelled:
                    self.progress_detail.emit(current, total)
                    if total > 0:
                        self.progress_pct.emit(int(current * 100 / total))

            try:
                # 步骤 1
                self.step_changed.emit(1, '获取 warframe.market 物品列表')
                _log('info', '正在连接 warframe.market API...')
                wm_items = _fetch_wm_items(_log)

                if self._cancelled:
                    return

                # 步骤 2
                self.step_changed.emit(2, '匹配本地物品数据库')
                _log('info', '正在与本地 items_i18n.db 进行物品匹配...')
                matched = _match_items(wm_items, _log)

                if self._cancelled:
                    return

                if not matched:
                    _log('error', '没有匹配到任何物品，请先确保 items_i18n.db 已构建')
                    self.error.emit('no_match')
                    return

                # 步骤 3 - 多线程拉取
                self.step_changed.emit(3,
                    f'拉取 {len(matched)} 个物品的卖价 ({self._max_workers} 线程并发)')
                result = _build_price_db(
                    matched, _log, _progress,
                    max_workers=self._max_workers,
                    batch_size=self._batch_size,
                )

                if self._cancelled:
                    return

                total_time = time.time() - start_time
                self.step_changed.emit(4, '完成')
                self.progress_pct.emit(100)
                _log('ok', f'总耗时: {total_time:.1f}s ({self._max_workers} 线程)')
                self.finished.emit(result)

            except Exception as e:
                _log('error', f'价格拉取失败: {e}')
                self.error.emit(str(e))


# ============================================================
# 命令行入口
# ============================================================

if __name__ == '__main__':
    import sys

    def _print_log(level, msg):
        prefix = {'ok': '  ✓', 'warn': '  ⚠', 'error': '  ✗'}.get(level, '   ')
        print(f'{prefix} {msg}')

    def _print_progress(current, total):
        pct = current * 100 // total if total else 0
        bar = '█' * (pct // 5) + '░' * (20 - pct // 5)
        print(f'\r  [{bar}] {current}/{total} ({pct}%)', end='', flush=True)

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ('--fetch', '-f'):
            print('开始拉取 warframe.market 卖价数据（含反压价权重）...\n')
            result = fetch_all_prices(_print_log, _print_progress)
            print()  # 换行
            if result.get('error'):
                print(f'拉取失败: {result["error"]}')
            else:
                print(f'\n完成! 共写入 {result["total"]} 个物品的卖价')
                print(f'  检测到压价: {result.get("total_abnormal", 0)} 次')

        elif cmd in ('--stats', '-s'):
            stats = get_price_stats()
            if stats['exists']:
                print(f'价格数据库: {DB_PATH}')
                print(f'  总物品数: {stats["total"]}')
                print(f'  有加权卖价: {stats["has_sell"]}')
                print(f'  检测到压价物品: {stats["has_weighted"]}')
                print(f'  文件大小: {stats["db_size"]/1024:.1f} KB')
                print(f'  最后更新: {stats["db_mtime"]}')
                print(f'  数据源: {stats.get("source", "N/A")}')
            else:
                print('价格数据库不存在')

        elif cmd in ('--search', '-q') and len(sys.argv) > 2:
            query = sys.argv[2]
            result = get_price(query)
            if result:
                print(f'\n物品: {query}')
                print(f'  slug: {result.get("slug", "")}')
                if result.get('sell_weighted'):
                    sell_min = result.get('sell_min', '-')
                    sell_median = result.get('sell_median', '-')
                    sell_weighted = result['sell_weighted']
                    top3 = result.get('sell_top3', [])
                    print(f'  最低卖价: {sell_min}p')
                    print(f'  卖价中位数: {sell_median}p')
                    print(f'  ★ 加权参考价: {sell_weighted}p  (已过滤压价)')
                    if top3:
                        print(f'  前3卖价: {top3}')
                    print(f'  采样卖单数: {result.get("sell_volume", 0)}')
                    print(f'  全量卖单数: {result.get("sell_volume_full", 0)}')
                if result.get('avg_price_90d'):
                    print(f'  90天均价: {result["avg_price_90d"]:.1f}p')
                if result.get('volume_48h'):
                    print(f'  48h成交量: {result["volume_48h"]}')
                print(f'  更新时间: {result.get("updated_at", "")}')
            else:
                print(f'未找到物品 "{query}" 的卖价信息')

        elif cmd in ('--search-batch', '-qb') and len(sys.argv) > 2:
            names = sys.argv[2].split(',')
            results = get_prices_batch([n.strip() for n in names])
            for name, info in results.items():
                weighted = info.get('sell_weighted')
                sell = f'{weighted}p (加权)' if weighted else 'N/A'
                print(f'  {name}: {sell}')
            missing = set(n.strip() for n in names) - set(results.keys())
            for m in missing:
                print(f'  {m}: 无卖价数据')

        else:
            print('用法:')
            print('  python wm_prices.py --fetch              拉取全量卖价数据')
            print('  python wm_prices.py --stats              查看数据库统计')
            print('  python wm_prices.py --search <英文名>      查询单个物品卖价')
            print('  python wm_prices.py --search-batch <名1,名2>  批量查询')

    else:
        stats = get_price_stats()
        if stats['exists']:
            print(f'价格数据库已存在 ({stats["total"]} 个物品): {DB_PATH}')
            print('使用 --fetch 重新拉取, --stats 查看统计, --search 查询')
        else:
            print('价格数据库不存在')
            print('运行 --fetch 开始拉取')
