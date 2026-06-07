"""
遗物物品与市场价格查询模块 (market_items.py)

从 warframe.db 统一数据库查询遗物奖励物品，并通过 warframe.market API 查询实时价格。

数据源:
  - warframe.db (market_items 表) → 遗物奖励物品列表 + 中英文名称
  - warframe.market API           → 实时价格（不缓存到本地，每次查询）
"""

import json
import os
import re
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 路径配置 =====
BASE_DIR = Path(__file__).resolve().parent
WARFRAME_DB_PATH = BASE_DIR / "warframe.db"

# ===== WM API 配置 =====
WM_API_ORDERS = "https://api.warframe.market/v2/orders/item"
REQUEST_TIMEOUT = 5
MAX_WORKERS = 4


# ============================================================
# 辅助函数
# ============================================================

def _get_db_path() -> Path:
    """获取 warframe.db 路径。"""
    return WARFRAME_DB_PATH


def _parse_json_field(value) -> list:
    """安全解析 JSON 字段。"""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# ============================================================
# 模糊搜索（从 warframe.db market_items 表）
# ============================================================

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Levenshtein 编辑距离。"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        cur_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            cur_row.append(min(
                cur_row[j] + 1,
                prev_row[j + 1] + 1,
                prev_row[j] + cost
            ))
        prev_row = cur_row
    return prev_row[-1]


def fuzzy_search(query: str, limit: int = 20) -> list[dict]:
    """模糊搜索物品。

    搜索策略:
      1. 中文字符 → LIKE 匹配 zh_name（每个字符做 AND 条件）
      2. 英文字符 → LIKE 匹配 en_name 和 slug
      3. 编辑距离精排
      4. 按编辑距离升序，优先精确匹配

    Args:
        query: 搜索文本（OCR 识别结果）
        limit: 返回结果数量上限

    Returns:
        [{"id", "en_name", "zh_name", "url_name", "slug", "item_type",
          "is_tradable", "is_prime", "source_relics", "source_rarity", "distance"}, ...]
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    query = query.strip()
    if not query:
        conn.close()
        return []

    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
    has_english = bool(re.search(r'[a-zA-Z]', query))

    if has_chinese and not has_english:
        results = _search_by_chinese(conn, query)
    elif has_english and not has_chinese:
        results = _search_by_english(conn, query)
    else:
        results = _search_by_chinese(conn, query)
        en_results = _search_by_english(conn, query)
        seen = {r["id"] for r in results}
        for r in en_results:
            if r["id"] not in seen:
                results.append(r)
                seen.add(r["id"])

    conn.close()

    # 编辑距离精排
    for r in results:
        r["_distance"] = _levenshtein_distance(query.lower(), r.get("zh_name", "").lower())
        en_dist = _levenshtein_distance(query.lower(), r.get("en_name", "").lower())
        r["_distance"] = min(r["_distance"], en_dist)

    results.sort(key=lambda x: x["_distance"])

    output = []
    for r in results[:limit]:
        item = {
            "id": r["id"],
            "en_name": r.get("en_name", ""),
            "zh_name": r.get("zh_name", ""),
            "url_name": r.get("slug", r.get("url_name", "")),
            "slug": r.get("slug", ""),
            "item_type": r.get("item_type", ""),
            "is_tradable": r.get("is_tradable", 0),
            "is_prime": r.get("is_prime", 0),
            "source_relics": _parse_json_field(r.get("source_relics", "[]")),
            "source_rarity": r.get("source_rarity", ""),
            "distance": r["_distance"],
        }
        output.append(item)

    return output


def batch_fuzzy_search(queries: list[tuple[str, list[str]]], limit: int = 5) -> dict[str, list[dict]]:
    """批量模糊搜索：单连接处理多个查询，避免重复打开/关闭 SQLite。

    Args:
        queries: [(ocr_text, variants), ...]  — OCR 文本 + 纠错候选
        limit: 每个查询返回结果数量上限

    Returns:
        {ocr_text: [{"en_name", "zh_name", "url_name", "distance", ...}, ...], ...}
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    results = {}
    try:
        for ocr_text, variants in queries:
            query = ocr_text.strip()
            if not query:
                results[ocr_text] = []
                continue

            has_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
            has_english = bool(re.search(r'[a-zA-Z]', query))

            rows = []
            if has_chinese and not has_english:
                rows = _search_by_chinese(conn, query)
            elif has_english and not has_chinese:
                rows = _search_by_english(conn, query)
            else:
                rows = _search_by_chinese(conn, query)
                en_rows = _search_by_english(conn, query)
                seen = {r["id"] for r in rows}
                for r in en_rows:
                    if r["id"] not in seen:
                        rows.append(r)

            # 编辑距离精排
            for r in rows:
                r["_distance"] = _levenshtein_distance(query.lower(), r.get("zh_name", "").lower())
                en_dist = _levenshtein_distance(query.lower(), r.get("en_name", "").lower())
                r["_distance"] = min(r["_distance"], en_dist)

            rows.sort(key=lambda x: x["_distance"])

            output = []
            for r in rows[:limit]:
                item = {
                    "id": r["id"],
                    "en_name": r.get("en_name", ""),
                    "zh_name": r.get("zh_name", ""),
                    "url_name": r.get("slug", r.get("url_name", "")),
                    "slug": r.get("slug", ""),
                    "item_type": r.get("item_type", ""),
                    "is_tradable": r.get("is_tradable", 0),
                    "is_prime": r.get("is_prime", 0),
                    "source_relics": _parse_json_field(r.get("source_relics", "[]")),
                    "source_rarity": r.get("source_rarity", ""),
                    "distance": r["_distance"],
                }
                output.append(item)

            results[ocr_text] = output
    finally:
        conn.close()

    return results


def _search_by_chinese(conn: sqlite3.Connection, query: str) -> list[dict]:
    """中文模糊搜索: 每个中文字符做 LIKE AND 条件。"""
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', query)
    if not chinese_chars:
        return []

    conditions = ["zh_name LIKE ?" for _ in chinese_chars]
    params = [f"%{ch}%" for ch in chinese_chars]
    sql = f"SELECT * FROM market_items WHERE {' AND '.join(conditions)} LIMIT 100"

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        return []

    return [dict(r) for r in rows]


def _search_by_english(conn: sqlite3.Connection, query: str) -> list[dict]:
    """英文模糊搜索: LIKE 匹配 en_name 和 slug。"""
    words = query.lower().split()
    conditions = []
    params = []

    for word in words:
        if len(word) >= 2:
            conditions.append("(en_name LIKE ? OR slug LIKE ?)")
            params.extend([f"%{word}%", f"%{word}%"])

    if not conditions:
        conditions.append("(en_name LIKE ? OR slug LIKE ?)")
        params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])

    sql = f"SELECT * FROM market_items WHERE {' AND '.join(conditions)} LIMIT 100"

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        return []

    return [dict(r) for r in rows]


def search_by_url_name(url_name: str) -> dict | None:
    """通过 url_name/slug 精确查找物品。"""
    db_path = _get_db_path()
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM market_items WHERE slug = ? OR url_name = ?",
        (url_name, url_name)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["source_relics"] = _parse_json_field(d.get("source_relics", "[]"))
        return d
    return None


# ============================================================
# WM API 价格查询
# ============================================================

def _http_get(url: str, timeout: int = REQUEST_TIMEOUT) -> dict:
    """HTTP GET 请求，返回 JSON。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Platform": "pc",
        "Language": "zh",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_wm_price(url_name: str) -> Optional[dict]:
    """查询 warframe.market 实时价格。

    获取该物品所有 sell 订单，仅统计状态为 "ingame" 的卖家，
    返回前 10 个最低单价。

    Args:
        url_name: warframe.market API slug

    Returns:
        {
            "url_name": str,
            "total_ingame": int,
            "top10": [{"platinum": int, "quantity": int, "ingame_name": str}, ...],
        }
        或 None
    """
    url = f"{WM_API_ORDERS}/{url_name}?order_type=sell"
    try:
        data = _http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        print(f"[market_items] API 请求失败: {url_name} - {e}")
        return None

    orders = data.get("payload", {}).get("orders", [])
    if not orders and isinstance(data.get("data"), list):
        orders = data["data"]

    sell_orders = []
    for o in orders:
        order_type = o.get("order_type") or o.get("type", "")
        user = o.get("user", {})
        if order_type == "sell" and user.get("status", "") == "ingame":
            platinum = o.get("platinum", 0)
            if platinum and platinum > 0:
                sell_orders.append({
                    "platinum": platinum,
                    "quantity": o.get("quantity", 1),
                    "ingame_name": user.get("ingame_name", ""),
                })

    if not sell_orders:
        return None

    sell_orders.sort(key=lambda x: x["platinum"])

    return {
        "url_name": url_name,
        "total_ingame": len(sell_orders),
        "top10": sell_orders[:10],
    }


def query_prices_batch(url_names: list[str], max_workers: int = MAX_WORKERS) -> dict[str, dict]:
    """批量查询多个物品的价格。

    Args:
        url_names: url_name 列表
        max_workers: 最大并发数

    Returns:
        {url_name: price_result, ...}
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(query_wm_price, name): name for name in url_names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                if result:
                    results[name] = result
            except Exception as e:
                print(f"[market_items] query_prices_batch 异常: {name} - {e}")
    return results
