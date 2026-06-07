"""
价格服务模块 — 实时价格查询 + 缓存 + 标注格式化

仅通过 warframe.market API 实时查询价格，不再依赖本地价格缓存数据库。
保留内存级缓存（30s TTL）以避免短时间内重复 API 请求。

用法:
    from core.price_service import PriceService
    svc = PriceService()
    results = svc.query_prices_batch(matched_items)
"""

import json
import os
import time
import threading
import urllib.request
import urllib.error
import sqlite3
from datetime import datetime
from typing import Optional

from core.constants import (
    COLOR_AVAILABLE, COLOR_GOLD, COLOR_UNKNOWN, COLOR_COPPER,
    CYBER_YELLOW,
)


# ============================================================
# API 配置
# ============================================================

WM_API_ORDERS = "https://api.warframe.market/v2/orders/item"
WM_API_STATS = "https://api.warframe.market/v1/items"
REQUEST_TIMEOUT = 5
REALTIME_TIMEOUT = 3.0

# 反压价权重参数
SELL_ORDER_SAMPLE = 20
PRICE_ABNORMAL_THRESHOLD = 0.30
ABNORMAL_WEIGHT = 0.1


# ============================================================
# 价格颜色映射（唯一权威来源）
# ============================================================

def price_to_color(price: Optional[dict], match_quality: str = '') -> str:
    """根据价格和匹配质量返回对应颜色。"""
    if match_quality == 'none':
        return COLOR_UNKNOWN

    if price and price.get('sell_weighted') is not None:
        weighted = price['sell_weighted']
        if weighted >= 50:
            return COLOR_AVAILABLE
        elif weighted >= 20:
            return COLOR_GOLD
        else:
            return CYBER_YELLOW

    return COLOR_COPPER


# ============================================================
# 显示名构建
# ============================================================

def build_display_name(item: dict) -> str:
    """构建 overlay 显示名：优先中文名，武器部件翻译武器名部分为中文。"""
    zh_name = item.get('zh_name', '')
    if zh_name:
        return zh_name

    en_name = item.get('matched_name') or item.get('en_name') or item['ocr_text']

    from recognizers.item_name import PART_EN_TO_CN
    weapon_name = en_name
    suffix_cn = None
    for en_suffix in sorted(PART_EN_TO_CN, key=len, reverse=True):
        if weapon_name.endswith(' ' + en_suffix):
            weapon_name = weapon_name[:-(len(en_suffix) + 1)].strip()
            suffix_cn = PART_EN_TO_CN[en_suffix]
            break

    translated = _translate_weapon_name(weapon_name)
    if translated:
        if suffix_cn:
            return f"{translated} {suffix_cn}"
        return translated

    from recognizers.matcher import _en_part_to_cn
    return _en_part_to_cn(en_name)


def _translate_weapon_name(weapon_name: str) -> Optional[str]:
    """通过 warframe.db 翻译武器名。"""
    if not weapon_name:
        return None
    try:
        from data.item_index import translate_item
        result = translate_item(weapon_name)
        if result:
            return result.get('zh_name')
    except Exception:
        pass
    return None


# ============================================================
# 标注文本格式化
# ============================================================

def format_price_annotation(item: dict) -> str:
    """将匹配结果格式化为价格标注文本。"""
    from data.ui_strings import S

    quality = item.get('match_quality', 'none')
    price = item.get('price')
    display_name = build_display_name(item)

    if quality == 'none':
        return S.format("overlay", "item_no_match_fmt", ocr_text=item['ocr_text'])

    if price and price.get('sell_weighted') is not None:
        weighted = price['sell_weighted']
        sell_min = price.get('sell_min', '-')
        sell_median = price.get('sell_median', '-')
        source_mark = ' [实时]' if item.get('_price_source') == 'realtime' else ''
        label = S.format("overlay", "item_price_detail_fmt",
            display_name=display_name, weighted=weighted,
            sell_min=sell_min, sell_median=sell_median)
        return label + source_mark

    return S.format("overlay", "item_no_price_fmt", display_name=display_name)


# ============================================================
# WM API 底层函数（从旧 wm_prices.py 内联）
# ============================================================

def _name_to_slug(en_name: str) -> str:
    """将英文物品名转换为 warframe.market slug。"""
    slug = en_name.lower()
    slug = slug.replace("'", "")
    slug = slug.replace(" & ", "_")
    slug = slug.replace("&", "")
    slug = slug.replace(" ", "_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _get_slug(en_name: str) -> Optional[str]:
    """从 warframe.db market_items 表获取 slug，或从名称构造。"""
    warframe_db = os.path.join(os.path.dirname(__file__), '..', 'data', 'warframe.db')
    if os.path.exists(warframe_db):
        try:
            conn = sqlite3.connect(warframe_db, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT slug FROM market_items WHERE en_name = ?", (en_name,)
            ).fetchone()
            conn.close()
            if row and row['slug']:
                return row['slug']
        except Exception:
            pass

    return _name_to_slug(en_name)


def _http_get(url: str, timeout: int = REQUEST_TIMEOUT) -> dict:
    """发送 GET 请求并解析 JSON。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'WARFRAME-RELIC/1.0',
        'Accept': 'application/json',
        'Platform': 'pc',
    })
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read()
    resp.close()
    return json.loads(data.decode('utf-8'))


def _extract_sell_orders(orders_data: list) -> list[int]:
    """从 API 返回的订单数据中提取卖价列表。"""
    sells = []
    for o in orders_data:
        order_type = o.get('order_type') or o.get('type', '')
        if order_type == 'sell':
            platinum = o.get('platinum', 0)
            if platinum and platinum > 0:
                sells.append(platinum)
    return sells


def _compute_weighted_price(sell_prices: list[int]) -> dict:
    """反压价权重算法：计算加权参考价。"""
    if not sell_prices:
        return {
            'weighted': None, 'median': None,
            'abnormal_count': 0, 'abnormal_prices': [],
            'top3': [], 'sample_size': 0,
        }

    sample = sell_prices[:SELL_ORDER_SAMPLE]
    n = len(sample)

    mid = n // 2
    if n % 2 == 0:
        median = (sample[mid - 1] + sample[mid]) / 2.0
    else:
        median = float(sample[mid])

    lower_bound = median * (1 - PRICE_ABNORMAL_THRESHOLD)

    total_weight = 0.0
    weighted_sum = 0.0
    abnormal_prices = []

    for price in sample:
        if price < lower_bound:
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


def _fetch_price_from_api(en_name: str, timeout: float = REALTIME_TIMEOUT) -> Optional[dict]:
    """实时通过 warframe.market API 查询单个物品价格。"""
    slug = _get_slug(en_name)
    if not slug:
        return None

    try:
        data = _http_get(f'{WM_API_ORDERS}/{slug}', timeout=int(timeout))
    except Exception as e:
        print(f"[price_service] API 失败: {slug} - {e}")
        return None

    try:
        orders = data.get('payload', {}).get('orders', [])
        if not orders and isinstance(data.get('data'), list):
            orders = data['data']

        sell_prices = _extract_sell_orders(orders)
        sell_prices.sort()

        if not sell_prices:
            return None

        weighted_result = _compute_weighted_price(sell_prices)

        # 尝试获取统计信息（非阻塞）
        volume_48h = None
        avg_price_90d = None
        try:
            stats = _http_get(f'{WM_API_STATS}/{slug}/statistics', timeout=max(int(timeout), 3))
            stat_payload = stats.get('payload', {})
            closed = stat_payload.get('statistics_closed', {})
            hours_48 = closed.get('48hours', [])
            days_90 = closed.get('90days', [])
            if hours_48:
                volume_48h = sum(h.get('volume', 0) for h in hours_48)
            if days_90:
                avg_price_90d = days_90[-1].get('wa_price')
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
        return None


# ============================================================
# 价格服务（仅内存缓存 + 实时 API）
# ============================================================

class PriceService:
    """统一价格服务：内存缓存 + warframe.market 实时 API。

    不再依赖任何本地价格数据库。
    30 秒内存缓存避免短时间内重复 API 请求。
    """

    CACHE_TTL = 30.0

    def __init__(self):
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._cache_lock = threading.Lock()

    def clear_cache(self):
        """清空价格缓存。"""
        with self._cache_lock:
            self._cache.clear()

    def _get_cached(self, en_name: str) -> Optional[dict]:
        """从缓存读取（如果未过期）。"""
        with self._cache_lock:
            entry = self._cache.get(en_name.lower())
            if entry:
                ts, price = entry
                if time.time() - ts < self.CACHE_TTL:
                    return price
                del self._cache[en_name.lower()]
        return None

    def _set_cached(self, en_name: str, price: Optional[dict]):
        """写入缓存。"""
        with self._cache_lock:
            self._cache[en_name.lower()] = (time.time(), price)

    def query_price(self, en_name: str, match_quality: str = '') -> Optional[dict]:
        """查询单个物品价格（缓存 → 实时 API）。

        Args:
            en_name: 物品英文名
            match_quality: 匹配质量

        Returns:
            价格 dict 或 None
        """
        if not en_name:
            return None

        cached = self._get_cached(en_name)
        if cached is not None:
            return cached if cached else None

        try:
            price = _fetch_price_from_api(en_name)
        except Exception:
            price = None

        if price:
            price['_source'] = 'realtime'

        self._set_cached(en_name, price)
        return price

    def query_prices_batch(self, matched_items: list[dict]) -> list[dict]:
        """批量查询价格（缓存 + 并发 API）。

        先用缓存覆盖，未命中的并发查询 warframe.market API。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        api_tasks: dict[int, str] = {}
        results: list[Optional[dict]] = [None] * len(matched_items)

        for i, item in enumerate(matched_items):
            en_name = item.get('en_name', '')

            cached = self._get_cached(en_name)
            if cached is not None:
                result = dict(item)
                result['matched_name'] = en_name
                result['price'] = cached if cached else None
                if cached and cached.get('_source'):
                    result['_price_source'] = cached['_source']
                results[i] = result
                continue

            api_tasks[i] = en_name

        if api_tasks:
            with ThreadPoolExecutor(max_workers=min(4, len(api_tasks))) as executor:
                future_to_idx = {
                    executor.submit(_fetch_price_from_api, en_name): idx
                    for idx, en_name in api_tasks.items()
                }
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    item = matched_items[idx]
                    en_name = api_tasks[idx]
                    try:
                        price = future.result()
                    except Exception:
                        price = None
                    if price:
                        price['_source'] = 'realtime'
                    self._set_cached(en_name, price)
                    result = dict(item)
                    result['matched_name'] = en_name
                    result['price'] = price
                    if price:
                        result['_price_source'] = 'realtime'
                    results[idx] = result

        for i, item in enumerate(matched_items):
            if results[i] is None:
                en_name = item.get('en_name', '')
                result = dict(item)
                result['matched_name'] = en_name
                result['price'] = None
                results[i] = result

        return results


# ============================================================
# 单例
# ============================================================

_price_service_instance: Optional[PriceService] = None
_price_service_lock = threading.Lock()


def get_price_service() -> PriceService:
    """获取 PriceService 单例。"""
    global _price_service_instance
    if _price_service_instance is None:
        with _price_service_lock:
            if _price_service_instance is None:
                _price_service_instance = PriceService()
    return _price_service_instance


def clear_price_cache():
    """清空全局价格缓存。"""
    svc = get_price_service()
    svc.clear_cache()
