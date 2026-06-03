"""
价格服务模块 — 统一价格查询、缓存、颜色映射

整合了原本分散在 main.py、matcher.py、item_info_panel.py 中的价格相关逻辑：
  - 本地 DB 价格查询（带连接缓存）
  - 实时 API 价格查询
  - 价格颜色映射
  - 显示名构建
  - 标注文本格式化

用法:
    from core.price_service import PriceService
    svc = PriceService()
    results = svc.query_prices(matched_items)
"""

import json
import os

import time
import threading
from typing import Optional

from core.constants import (
    COLOR_AVAILABLE, COLOR_GOLD, COLOR_UNKNOWN, COLOR_COPPER,
    CYBER_YELLOW,
)


# ============================================================
# 价格颜色映射（唯一权威来源）
# ============================================================

def price_to_color(price: Optional[dict], match_quality: str = '') -> str:
    """根据价格和匹配质量返回对应颜色。

    颜色规则：
      - 未匹配 → COLOR_UNKNOWN
      - 加权价 >= 50 → COLOR_AVAILABLE (绿色/高价)
      - 加权价 >= 20 → COLOR_GOLD (金色/中价)
      - 有价格但 < 20 → CYBER_YELLOW (黄色/低价)
      - 无价格数据 → COLOR_COPPER (铜色)

    Args:
        price: 价格字典或 None
        match_quality: 匹配质量 ('exact', 'fuzzy', 'variant', 'part_direct', 'none')

    Returns:
        颜色常量字符串
    """
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
# 显示名构建（从 main.py _make_display_name 迁移）
# ============================================================

def build_display_name(item: dict) -> str:
    """构建 overlay 显示名：优先中文名，武器部件翻译武器名部分为中文。

    例如:
      武器部件 Dual Zoren Prime Blade  → "佐伦双斧 Prime 刀刃"
      武器本体 Dual Zoren              → "佐伦双斧"
      Ash Prime Chassis Blueprint      → "Ash Prime 机体蓝图"
    """
    zh_name = item.get('zh_name', '')
    if zh_name:
        return zh_name

    # 没有 zh_name（如 part_direct），尝试翻译武器名为中文
    en_name = item.get('matched_name') or item.get('en_name') or item['ocr_text']

    # 提取部件后缀和武器名
    from recognizers.item_name import PART_EN_TO_CN
    weapon_name = en_name
    suffix_cn = None
    for en_suffix in sorted(PART_EN_TO_CN, key=len, reverse=True):
        if weapon_name.endswith(' ' + en_suffix):
            weapon_name = weapon_name[:-(len(en_suffix) + 1)].strip()
            suffix_cn = PART_EN_TO_CN[en_suffix]
            break

    # 翻译武器名部分（英译中）
    translated = _translate_weapon_name(weapon_name)

    if translated:
        if suffix_cn:
            return f"{translated} {suffix_cn}"
        return translated

    # 翻译失败，回退到只翻译部件后缀
    from recognizers.matcher import _en_part_to_cn
    return _en_part_to_cn(en_name)


def _translate_weapon_name(weapon_name: str) -> Optional[str]:
    """通过 items_i18n.db 翻译武器名。"""
    if not weapon_name:
        return None
    try:
        from data.items_i18n import translate_item
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
    """将匹配结果格式化为价格标注文本。

    Args:
        item: 包含 ocr_text, matched_name, zh_name, price, match_quality 的字典

    Returns:
        格式化后的标注字符串
    """
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
            display_name=display_name,
            weighted=weighted, sell_min=sell_min, sell_median=sell_median)
        return label + source_mark

    return S.format("overlay", "item_no_price_fmt", display_name=display_name)


# ============================================================
# 价格服务（带缓存）
# ============================================================

class PriceService:
    """统一价格服务：查询、缓存、格式化。

    特性：
      - 本地 DB 连接缓存（避免每次 ATTACH）
      - 查询结果内存缓存（同帧多个物品避免重复查库）
      - 统一的价格查询入口
    """

    # 缓存有效期（秒）
    CACHE_TTL = 30.0

    def __init__(self):
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._cache_lock = threading.Lock()

    def clear_cache(self):
        """清空价格缓存。"""
        with self._cache_lock:
            self._cache.clear()

    # ---- 本地 DB 查询（带连接复用） ----

    @staticmethod
    def _get_price_from_db(en_name: str) -> Optional[dict]:
        """从本地 wm_prices.db 查询价格（直接用 en_name，不依赖 ID JOIN）。"""
        from data.wm_prices import get_price
        return get_price(en_name)

    # ---- 实时 API 查询 ----

    @staticmethod
    def _fetch_price_realtime(en_name: str, timeout: float = 3.0) -> Optional[dict]:
        """实时通过 warframe.market API 查询价格。"""
        from data.wm_prices import fetch_price_realtime
        return fetch_price_realtime(en_name, timeout=timeout)

    # ---- 缓存读取 ----

    def _get_cached(self, en_name: str) -> Optional[dict]:
        """从缓存读取价格（如果未过期）。"""
        with self._cache_lock:
            entry = self._cache.get(en_name.lower())
            if entry:
                ts, price = entry
                if time.time() - ts < self.CACHE_TTL:
                    return price
                # 过期，删除
                del self._cache[en_name.lower()]
        return None

    def _set_cached(self, en_name: str, price: Optional[dict]):
        """写入缓存。"""
        with self._cache_lock:
            self._cache[en_name.lower()] = (time.time(), price)

    # ---- 统一查询入口 ----

    def query_price(self, en_name: str, match_quality: str = '') -> Optional[dict]:
        """查询单个物品价格（缓存 → 本地DB → 实时API）。

        查询顺序：
          1. 缓存
          2. 本地 DB
          3. 实时 API（本地 DB 无数据时 fallback）
          4. part_direct 优先实时 API（本地 DB 通常无部件数据）

        Args:
            en_name: 物品英文名
            match_quality: 匹配质量 ('part_direct' 时优先实时 API)

        Returns:
            价格 dict 或 None
        """
        if not en_name:
            return None

        # 1. 检查缓存
        cached = self._get_cached(en_name)
        if cached is not None:
            return cached if cached else None  # None 表示"已查过但无价格"

        price = None

        # 2. part_direct → 优先实时 API（本地 DB 无部件数据）
        if match_quality == 'part_direct':
            try:
                price = self._fetch_price_realtime(en_name, timeout=3.0)
                if price:
                    price['_source'] = 'realtime'
            except Exception:
                pass

        # 3. 本地 DB 查询
        if not price:
            price = self._get_price_from_db(en_name)
            if price:
                price['_source'] = 'local'

        # 4. 本地 DB 无数据 → fallback 实时 API（适用于所有匹配类型）
        if not price and match_quality != 'part_direct':
            try:
                price = self._fetch_price_realtime(en_name, timeout=3.0)
                if price:
                    price['_source'] = 'realtime'
            except Exception:
                pass

        # 写入缓存（包括 None 表示"已查无果"）
        self._set_cached(en_name, price)
        return price

    def query_prices_batch(
        self, matched_items: list[dict]
    ) -> list[dict]:
        """批量查询价格并返回带价格的完整结果。

        使用线程池并发查询（最多 4 个并发），将多个 API 请求并行化，
        把最坏 12 秒降到 ~3 秒。

        Args:
            matched_items: match_items() 的输出 [{ocr_text, en_name, zh_name, box, match_quality}, ...]

        Returns:
            附加了 price 字段的列表 [{..., price, _price_source}, ...]
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 先检查缓存 + 本地DB（这两步很快，同步处理）
        # 收集需要实时API查询的物品
        api_tasks: dict[int, str] = {}  # index → en_name
        results: list[Optional[dict]] = [None] * len(matched_items)

        for i, item in enumerate(matched_items):
            en_name = item.get('en_name', '')
            match_quality = item.get('match_quality', '')

            # 1. 缓存
            cached = self._get_cached(en_name)
            if cached is not None:
                result = dict(item)
                result['matched_name'] = en_name
                result['price'] = cached if cached else None
                if cached and cached.get('_source'):
                    result['_price_source'] = cached['_source']
                results[i] = result
                continue

            # 2. 本地DB
            price = self._get_price_from_db(en_name)
            if price:
                price['_source'] = 'local'
                self._set_cached(en_name, price)
                result = dict(item)
                result['matched_name'] = en_name
                result['price'] = price
                result['_price_source'] = 'local'
                results[i] = result
                continue

            # 3. 需要实时API
            api_tasks[i] = en_name

        # 并发查询实时API
        if api_tasks:
            with ThreadPoolExecutor(max_workers=min(4, len(api_tasks))) as executor:
                future_to_idx = {
                    executor.submit(self._fetch_price_realtime, en_name, 3.0): idx
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

        # 确保所有结果都不为None（防御性）
        for i, item in enumerate(matched_items):
            if results[i] is None:
                en_name = item.get('en_name', '')
                result = dict(item)
                result['matched_name'] = en_name
                result['price'] = None
                results[i] = result

        return results


# ============================================================
# 单例（线程安全）
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
