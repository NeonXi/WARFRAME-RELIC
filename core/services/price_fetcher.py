"""
[L-Service] core.services.price_fetcher — 单物品价格查询

═══════════════════════════════════════════════════════════════════════
依赖图(严格自上而下,下层不能反向依赖)
═══════════════════════════════════════════════════════════════════════
  core.services.price_fetcher  ← 本文件
       ↓ 允许依赖
  core.services.http_client (HttpClient + 异常类)
  core.state.price_query_state (PriceQueryState, QuerySubStatus)
  Python 标准库 (threading, time, dataclasses)
       ↓ 禁止依赖
  PySide6.QtWidgets / QtGui
  core.widgets.* / core.pages.*

═══════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════
  - 单物品订单 API 查询(WM v2)
  - 解析卖单(过滤 in-game/online, 按价格排序)
  - 返回 PriceResult(均价/最低/最高/订单数)
  - 异步 + 同步两个 API
  - 失败时通过 State 通知 UI

═══════════════════════════════════════════════════════════════════════
响应格式参考(WM v2 orders API)
═══════════════════════════════════════════════════════════════════════
  GET /v2/orders/item/{slug}?order_type=sell
  Response:
    {
      "apiVersion": "...",
      "data": [
        {
          "id": "...",
          "type": "sell",
          "platinum": 70,
          "quantity": 1,
          "perTrade": 1,
          "visible": true,
          "createdAt": "2026-01-01T00:00:00Z",
          "updatedAt": "...",
          "itemId": "...",
          "user": {
            "id": "...",
            "ingameName": "...",
            "slug": "...",
            "reputation": 0,
            "platform": "pc",
            "crossplay": true,
            "locale": "en",
            "status": "ingame" | "online" | "offline",
            "lastSeen": "..."
          }
        },
        ...
      ]
    }
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from core.services.http_client import (
    HttpClient, HttpError, ApiError,
)
from core.state.price_query_state import (
    PriceQueryState, QuerySubStatus,
)
from core.logging_utils import log as _dbg


# ════════════════════════════════════════════════════════════════════════
#  配置常量
# ════════════════════════════════════════════════════════════════════════

# WM v2 订单 API 模板
WM_ORDERS_URL = "https://api.warframe.market/v2/orders/item/{slug}"

# 状态优先级(用于排序): ingame > online > offline
STATUS_PRIORITY = {"ingame": 0, "online": 1, "offline": 2}

# 最多取多少 in-game 订单展示
MAX_ONLINE_ORDERS = 50


# ════════════════════════════════════════════════════════════════════════
#  数据类
# ════════════════════════════════════════════════════════════════════════

@dataclass
class SellOrder:
    """单条卖单(已解析)。"""
    platinum: int
    quantity: int
    rank: int                 # 物品等级(0 = 无)
    user_name: str
    user_status: str          # ingame / online / offline
    user_reputation: int
    created_at: str           # ISO 时间戳


@dataclass
class PriceResult:
    """单个物品的价格查询结果。"""
    slug: str
    name: str = ""
    min_platinum: int = 0
    max_platinum: int = 0
    avg_platinum: float = 0.0
    weighted_avg: float = 0.0  # 按 quantity 加权
    sell_orders: list[SellOrder] = field(default_factory=list)
    online_count: int = 0      # ingame + online 的卖单数
    total_count: int = 0       # 所有卖单数
    fetched_at: float = 0.0    # 时间戳

    @property
    def has_data(self) -> bool:
        return self.total_count > 0

    def to_dict(self) -> dict:
        """序列化为 dict(发信号用)。"""
        return {
            "slug": self.slug,
            "name": self.name,
            "min_platinum": self.min_platinum,
            "max_platinum": self.max_platinum,
            "avg_platinum": self.avg_platinum,
            "weighted_avg": self.weighted_avg,
            "online_count": self.online_count,
            "total_count": self.total_count,
            "sell_orders": [
                {
                    "platinum": o.platinum,
                    "quantity": o.quantity,
                    "rank": o.rank,
                    "user_name": o.user_name,
                    "user_status": o.user_status,
                    "user_reputation": o.user_reputation,
                    "created_at": o.created_at,
                }
                for o in self.sell_orders
            ],
            "fetched_at": self.fetched_at,
        }


# ════════════════════════════════════════════════════════════════════════
#  PriceFetcher — 单物品价格查询器(单例)
# ════════════════════════════════════════════════════════════════════════

class PriceFetcher:
    """单物品价格查询器(单例)。

    异步: fetch_async() 启动后台线程,通过 State 发信号
    同步: fetch_blocking() 直接返回(测试用)
    """

    _instance: "PriceFetcher | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "PriceFetcher":
        with cls._lock:
            if cls._instance is None:
                cls._instance = PriceFetcher()
        return cls._instance

    def __init__(self) -> None:
        self._http = HttpClient.instance()
        self._state = PriceQueryState.instance()
        # 防止同一 slug 重复查
        self._query_lock = threading.Lock()
        self._query_in_progress: set[str] = set()
        self._current_thread: threading.Thread | None = None

    # ══════════════════════════════════════════════════════
    #  公开 API
    # ══════════════════════════════════════════════════════

    def fetch_async(self, slug: str, name: str = "") -> None:
        """异步查询(后台线程,结果通过 State 信号通知)。

        Args:
            slug: WM API slug (e.g. "rhino_prime_set")
            name: 显示名(用于 UI,e.g. "Rhino Prime Set")
        """
        with self._query_lock:
            if slug in self._query_in_progress:
                _dbg("price", f"fetch_async: {slug} 已在查询中, 跳过")
                return
            self._query_in_progress.add(slug)

        self._state.set_query_status(QuerySubStatus.QUERYING, slug=slug)
        self._state.query_started.emit(slug)

        thread = threading.Thread(
            target=self._fetch_worker,
            args=(slug, name),
            daemon=True,
            name=f"PriceFetch-{slug}",
        )
        self._current_thread = thread
        thread.start()

    def fetch_blocking(self, slug: str, name: str = "") -> PriceResult:
        """同步查询(测试用)。同样更新 State 状态。"""
        self._state.set_query_status(QuerySubStatus.QUERYING, slug=slug)
        self._state.query_started.emit(slug)
        try:
            result = self._fetch_impl(slug, name)
            self._state.set_query_status(QuerySubStatus.READY, slug=slug)
            self._state.set_last_query_result(result.to_dict())
            self._state.query_completed.emit(result.to_dict())
            return result
        except HttpError as e:
            self._state.set_query_status(QuerySubStatus.FAILED, slug=slug)
            self._state.query_failed.emit(slug, e.message)
            raise
        except Exception as e:
            self._state.set_query_status(QuerySubStatus.FAILED, slug=slug)
            self._state.query_failed.emit(slug, f"{type(e).__name__}: {e}")
            raise

    # ══════════════════════════════════════════════════════
    #  内部
    # ══════════════════════════════════════════════════════

    def _fetch_worker(self, slug: str, name: str) -> None:
        """后台线程:调 _fetch_impl,更新 State。"""
        try:
            result = self._fetch_impl(slug, name)
            self._state.set_query_status(QuerySubStatus.READY, slug=slug)
            self._state.set_last_query_result(result.to_dict())
            self._state.query_completed.emit(result.to_dict())
        except HttpError as e:
            self._state.set_query_status(QuerySubStatus.FAILED, slug=slug)
            self._state.query_failed.emit(slug, e.message)
        except Exception as e:
            self._state.set_query_status(QuerySubStatus.FAILED, slug=slug)
            self._state.query_failed.emit(slug, f"{type(e).__name__}: {e}")
        finally:
            with self._query_lock:
                self._query_in_progress.discard(slug)

    def _fetch_impl(self, slug: str, name: str) -> PriceResult:
        """实际下载 + 解析。"""
        url = WM_ORDERS_URL.format(slug=slug)
        _dbg("price", f"_fetch_impl: {url}")

        data = self._http.get_json(url, params={"order_type": "sell"})
        orders_raw = data.get("data", [])
        if not isinstance(orders_raw, list):
            raise ApiError(
                f"响应格式错误: data 不是 list (got {type(orders_raw).__name__})",
                url=url,
            )

        # ── 解析 + 过滤 ──
        all_sell: list[SellOrder] = []
        for o in orders_raw:
            if not isinstance(o, dict):
                continue
            # 兼容 v1/v2 字段名
            order_type = o.get("order_type") or o.get("type", "")
            if order_type != "sell":
                continue
            platinum = int(o.get("platinum", 0) or 0)
            if platinum <= 0:
                continue
            user = o.get("user", {})
            if not isinstance(user, dict):
                user = {}
            # user.status: ingame / online / offline
            user_status = user.get("status", "offline")
            # 兼容 v1 ingame_name / v2 ingameName
            user_name = (
                user.get("ingameName")
                or user.get("ingame_name")
                or "Unknown"
            )
            reputation = user.get("reputation", 0)
            if isinstance(reputation, dict):
                reputation = reputation.get("level", 0)
            reputation = int(reputation) if reputation else 0
            all_sell.append(SellOrder(
                platinum=platinum,
                quantity=int(o.get("quantity", 1) or 1),
                rank=int(o.get("rank", 0) or 0),
                user_name=str(user_name),
                user_status=str(user_status),
                user_reputation=reputation,
                created_at=str(o.get("creation_date") or o.get("createdAt", "")),
            ))

        # ── 排序: status 优先 (ingame > online > offline), 然后价格升序 ──
        all_sell.sort(key=lambda x: (
            STATUS_PRIORITY.get(x.user_status, 4),
            x.platinum,
        ))

        # ── 统计 ──
        online_orders = [o for o in all_sell if o.user_status in ("ingame", "online")]
        offline_orders = [o for o in all_sell if o.user_status not in ("ingame", "online")]

        if all_sell:
            prices = [o.platinum for o in all_sell]
            min_p = min(prices)
            max_p = max(prices)
            avg_p = sum(prices) / len(prices)
            # 按数量加权
            total_qty = sum(o.quantity for o in all_sell)
            weighted = (
                sum(o.platinum * o.quantity for o in all_sell) / total_qty
                if total_qty > 0 else avg_p
            )
        else:
            min_p = max_p = 0
            avg_p = weighted = 0.0

        # 限制展示条数
        limited = online_orders + offline_orders[:MAX_ONLINE_ORDERS]

        return PriceResult(
            slug=slug,
            name=name,
            min_platinum=min_p,
            max_platinum=max_p,
            avg_platinum=round(avg_p, 1),
            weighted_avg=round(weighted, 1),
            sell_orders=limited,
            online_count=len(online_orders),
            total_count=len(all_sell),
            fetched_at=time.time(),
        )
