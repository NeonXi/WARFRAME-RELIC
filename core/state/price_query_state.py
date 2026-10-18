"""
[L-State] core.state.price_query_state — 价格查询全局状态

═══════════════════════════════════════════════════════════════════════
依赖图(严格自上而下,下层不能反向依赖)
═══════════════════════════════════════════════════════════════════════
  core.state.price_query_state  ← 本文件
       ↓ 允许依赖
  PySide6.QtCore (Signal)
  Python 标准库
       ↓ 禁止依赖
  core.services.* / core.widgets.* / core.pages.*
  requests / 网络库

═══════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════
  - 价格查询功能的状态机(顶层 + 搜索子状态 + 查询子状态)
  - 全物品列表缓存(只读)
  - 失败冷却机制(失败后 30s 不自动重试)
  - 跨页面信号: 状态变化 / 进度 / 错误 / 搜索结果 / 查询结果

═══════════════════════════════════════════════════════════════════════
AI 硬约束(开发规范 §6.6)
═══════════════════════════════════════════════════════════════════════
  - State 只存数据,不发 UI 调用
  - 不持有 widget 引用
  - 不直接调 Service,Service 通过订阅本 State 的信号来更新缓存
  - State 是"数据真相"单源,Page 只读
"""

from __future__ import annotations

import json
import time
from enum import Enum

from PySide6.QtCore import QObject, Signal

from core.paths import user_data_dir as _user_data_dir


# ════════════════════════════════════════════════════════════════════════
# 状态枚举
# ════════════════════════════════════════════════════════════════════════

class TopStatus(str, Enum):
    """价格查询顶层状态(全物品列表加载情况)。"""
    IDLE = "idle"               # 初始,未尝试加载
    LOADING = "loading"         # 正在加载全物品列表
    READY = "ready"             # 列表就绪,WM API 搜索可用
    DEGRADED = "degraded"       # 列表加载失败,降级到 DB 搜索
    FAILED = "failed"           # 完全失败(网络 + DB 都不通)

    @property
    def is_search_available(self) -> bool:
        """该状态下用户能否搜索。"""
        return self in (TopStatus.READY, TopStatus.DEGRADED)

    @property
    def is_loading(self) -> bool:
        return self == TopStatus.LOADING


class SearchSubStatus(str, Enum):
    """搜索子状态(独立于顶层状态)。"""
    IDLE = "search_idle"        # 无搜索
    SEARCHING = "searching"     # 搜索中
    READY = "search_ready"      # 搜索完成,有结果
    FAILED = "search_failed"    # 搜索失败
    EMPTY = "search_empty"      # 搜索完成但无结果


class QuerySubStatus(str, Enum):
    """价格查询子状态。"""
    IDLE = "query_idle"
    QUERYING = "querying"       # 拉订单中
    READY = "query_ready"       # 查询完成
    FAILED = "query_failed"     # 查询失败


# ════════════════════════════════════════════════════════════════════════
#  配置常量
# ════════════════════════════════════════════════════════════════════════

# 失败冷却时间(秒)
FAILURE_COOLDOWN_SECONDS = 30.0

# 进度信号节流(秒)
PROGRESS_THROTTLE_SECONDS = 0.2

# 单物品查询 (slug, name, tags)
ItemTuple = tuple[str, str, list[str]]

# ── 磁盘缓存(本地持久化) ──
# 物品列表基本不变,关 App 后下次启动应直接复用本地缓存,
# 避免每次都从 WM API 拉取(冷启动体感很差)。
CACHE_FILE = _user_data_dir() / "wm_items_cache.json"
# 软过期阈值(秒):超过此值后,允许后台静默刷新。
#   24h:大多数日子用户会用一次 App,既新鲜又快。
#   实际 WM 列表几周才更新,设更长也行,但用户每天拉一次能跟上 wiki 异动。
STALE_THRESHOLD_SECONDS = 24 * 3600


# ════════════════════════════════════════════════════════════════════════
#  PriceQueryState — 价格查询状态机(单例)
# ════════════════════════════════════════════════════════════════════════

class PriceQueryState(QObject):
    """价格查询全局状态(单例)。

    Signals:
      top_status_changed(str):       顶层状态变化 (TopStatus value)
      load_progress(int, str):       加载进度 (0-100, message)
      error_occurred(str, str):      错误 (level, message) — level: warn/error

      search_started():              搜索开始
      search_completed(list):        搜索完成 (results)
      search_failed(str):            搜索失败 (error message)
      search_empty(str):             搜索无结果 (keyword)

      query_started(str):            查询开始 (slug)
      query_completed(dict):         查询完成 (result)
      query_failed(str, str):        查询失败 (slug, error)
    """

    # ── 顶层状态 ──
    top_status_changed = Signal(str)
    load_progress = Signal(int, str)  # (percent, message)
    error_occurred = Signal(str, str)  # (level, message)

    # ── 搜索 ──
    search_started = Signal()
    search_completed = Signal(list)  # list[dict]
    search_failed = Signal(str)
    search_empty = Signal(str)  # keyword

    # ── 价格查询 ──
    query_started = Signal(str)  # slug
    query_completed = Signal(dict)
    query_failed = Signal(str, str)  # (slug, error)

    # ── 单例 ──
    _instance: "PriceQueryState | None" = None

    @classmethod
    def instance(cls) -> "PriceQueryState":
        """单例访问(惰性创建)。"""
        if cls._instance is None:
            cls._instance = PriceQueryState()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()

        # ── 顶层状态 ──
        self._top_status: TopStatus = TopStatus.IDLE

        # ── 缓存(全物品列表) ──
        self._items: list[ItemTuple] = []  # [(name, slug, tags), ...]
        self._items_loaded_at: float = 0.0
        # 数据来源标识: "disk" = 启动时从本地 JSON 读 | "network" = 本次进程网络拉的
        # | "none" = 还没数据
        self._items_source: str = "none"

        # ── 失败冷却 ──
        self._failure_time: float = 0.0
        self._failure_message: str = ""

        # ── 搜索子状态 ──
        self._search_status: SearchSubStatus = SearchSubStatus.IDLE
        self._current_keyword: str = ""
        self._last_results: list[dict] = []

        # ── 查询子状态 ──
        self._query_status: QuerySubStatus = QuerySubStatus.IDLE
        self._current_query_slug: str = ""
        self._last_query_result: dict | None = None

        # ── 启动时从磁盘加载(同步、IO 小) ──
        # 让 App 启动后第一次进 prices 页即可 READY,无需等网络
        self._load_items_from_disk()

    # ══════════════════════════════════════════════════════
    #  顶层状态 API
    # ══════════════════════════════════════════════════════

    @property
    def top_status(self) -> TopStatus:
        return self._top_status

    def set_top_status(self, status: TopStatus) -> None:
        """转移顶层状态(只在状态真正变化时发信号)。"""
        if self._top_status == status:
            return
        old = self._top_status
        self._top_status = status
        self.top_status_changed.emit(status.value)
        from core.logging_utils import log as _dbg
        _dbg("state", f"top_status: {old.value} → {status.value}")

    # ══════════════════════════════════════════════════════
    #  缓存 API
    # ══════════════════════════════════════════════════════

    def get_items(self) -> list[ItemTuple]:
        """返回全物品列表(只读副本)。"""
        return list(self._items)

    def has_items(self) -> bool:
        return len(self._items) > 0

    def set_items(self, items: list[ItemTuple]) -> None:
        """更新全物品列表缓存(只读)。"""
        self._items = list(items)
        self._items_loaded_at = time.time()
        from core.logging_utils import log as _dbg
        _dbg("state", f"set_items: 缓存 {len(self._items)} 个物品")

    def clear_items(self) -> None:
        self._items = []
        self._items_loaded_at = 0.0

    def items_age_seconds(self) -> float:
        """物品缓存已加载多久(秒)。0 = 未加载。"""
        if self._items_loaded_at == 0.0:
            return float("inf")
        return time.time() - self._items_loaded_at

    def is_items_cache_stale(self) -> bool:
        """物品缓存是否"软过期"(超 24h)。软过期不阻塞 UI,只允许后台静默刷新。"""
        if self._items_loaded_at == 0.0:
            return True
        return self.items_age_seconds() > STALE_THRESHOLD_SECONDS

    # ── 数据来源标识(用于 UI 提示) ──

    def get_items_source(self) -> str:
        """返回 "disk" | "network" | "none"."""
        return self._items_source

    def set_items_source(self, source: str) -> None:
        """显式标记数据来源。"""
        if source not in ("disk", "network", "none"):
            return
        self._items_source = source

    def format_cache_age(self) -> str:
        """格式化缓存年龄(中文短文)。例: '刚刚' / '5m 前' / '3h 前' / '2d 前'。"""
        if self._items_loaded_at == 0.0:
            return ""
        age = self.items_age_seconds()
        if age < 60:
            return "刚刚"
        if age < 3600:
            return f"{int(age // 60)}m 前"
        if age < 24 * 3600:
            return f"{int(age // 3600)}h 前"
        if age < 30 * 24 * 3600:
            return f"{int(age // (24 * 3600))}d 前"
        return f"{int(age // (30 * 24 * 3600))}mo 前"

    # ── 磁盘持久化 ──────────────────────────────────────────────

    def _load_items_from_disk(self) -> None:
        """从本地 JSON 加载物品列表(同步、启动时调用)。

        设计:
          - 失败不抛异常,只记日志
          - 成功则填充 self._items + 设顶层状态为 READY(免得用户进页等加载)
          - 即使软过期也加载(让 UI 立即有内容,后台再静默刷新)
        """
        from core.logging_utils import log as _dbg
        try:
            if not CACHE_FILE.exists():
                _dbg("state", "_load_items_from_disk: 缓存文件不存在, 跳过")
                return
            with CACHE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            items_raw = data.get("items", [])
            if not isinstance(items_raw, list) or not items_raw:
                _dbg("state", "_load_items_from_disk: 缓存格式异常, 跳过")
                return

            loaded: list[ItemTuple] = []
            for it in items_raw:
                if not isinstance(it, dict):
                    continue
                name = it.get("name", "")
                slug = it.get("slug", "")
                tags = it.get("tags", [])
                if not name or not slug or not isinstance(tags, list):
                    continue
                loaded.append((name, slug, list(tags)))

            if not loaded:
                _dbg("state", "_load_items_from_disk: 无有效数据, 跳过")
                return

            # 用文件 mtime 作为 loaded_at,这样 age 反映"上次落盘时间"
            try:
                mtime = CACHE_FILE.stat().st_mtime
            except OSError:
                mtime = time.time()

            self._items = loaded
            self._items_loaded_at = mtime
            self._items_source = "disk"
            # 直接赋值不发信号(启动阶段尚无消费者)
            if self._top_status == TopStatus.IDLE:
                self._top_status = TopStatus.READY
            _dbg(
                "state",
                f"_load_items_from_disk: 加载 {len(loaded)} 个物品 "
                f"(cache age={time.time() - mtime:.0f}s)",
            )
        except Exception as e:
            _dbg("state", f"_load_items_from_disk 失败: {type(e).__name__}: {e}")

    def persist_to_disk(self) -> None:
        """把当前 items 落盘到 JSON(原子写:先 .tmp 再 rename)。

        应该在 HTTP 拉取成功后的后台线程里调(避免阻塞 UI)。
        失败不抛异常,只记日志(下次启动还是用旧缓存或网络重拉)。
        """
        from core.logging_utils import log as _dbg
        if not self._items:
            return
        try:
            payload = {
                "loaded_at": self._items_loaded_at or time.time(),
                "item_count": len(self._items),
                "items": [
                    {"name": n, "slug": s, "tags": list(t)}
                    for n, s, t in self._items
                ],
            }
            tmp = CACHE_FILE.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            tmp.replace(CACHE_FILE)  # 原子替换(同分区)
            _dbg("state", f"persist_to_disk: 写入 {len(self._items)} 个物品")
        except Exception as e:
            _dbg("state", f"persist_to_disk 失败: {type(e).__name__}: {e}")

    # ══════════════════════════════════════════════════════
    #  失败冷却
    # ══════════════════════════════════════════════════════

    def record_failure(self, message: str) -> None:
        """记录一次失败,设置 30s 冷却。"""
        self._failure_time = time.time()
        self._failure_message = message

    def clear_failure(self) -> None:
        """清除失败状态(成功时调用)。"""
        self._failure_time = 0.0
        self._failure_message = ""

    def is_in_failure_cooldown(self) -> bool:
        """是否在失败冷却期。"""
        if self._failure_time == 0.0:
            return False
        elapsed = time.time() - self._failure_time
        return elapsed < FAILURE_COOLDOWN_SECONDS

    def failure_cooldown_remaining(self) -> float:
        """冷却还剩多少秒。0 = 不在冷却。"""
        if not self.is_in_failure_cooldown():
            return 0.0
        elapsed = time.time() - self._failure_time
        return max(0.0, FAILURE_COOLDOWN_SECONDS - elapsed)

    def get_failure_message(self) -> str:
        return self._failure_message

    # ══════════════════════════════════════════════════════
    #  搜索子状态
    # ══════════════════════════════════════════════════════

    @property
    def search_status(self) -> SearchSubStatus:
        return self._search_status

    @property
    def current_keyword(self) -> str:
        return self._current_keyword

    def set_search_status(self, status: SearchSubStatus, *, keyword: str = "") -> None:
        """更新搜索子状态。"""
        old = self._search_status
        self._search_status = status
        if keyword:
            self._current_keyword = keyword
        from core.logging_utils import log as _dbg
        _dbg("state", f"search_status: {old.value} → {status.value} (kw={keyword!r})")

    def get_last_results(self) -> list[dict]:
        return list(self._last_results)

    def set_last_results(self, results: list[dict]) -> None:
        self._last_results = list(results)

    # ══════════════════════════════════════════════════════
    #  查询子状态
    # ══════════════════════════════════════════════════════

    @property
    def query_status(self) -> QuerySubStatus:
        return self._query_status

    @property
    def current_query_slug(self) -> str:
        return self._current_query_slug

    def set_query_status(self, status: QuerySubStatus, *, slug: str = "") -> None:
        old = self._query_status
        self._query_status = status
        if slug:
            self._current_query_slug = slug
        from core.logging_utils import log as _dbg
        _dbg("state", f"query_status: {old.value} → {status.value} (slug={slug!r})")

    def get_last_query_result(self) -> dict | None:
        return self._last_query_result

    def set_last_query_result(self, result: dict | None) -> None:
        self._last_query_result = result

    # ══════════════════════════════════════════════════════
    #  便利方法
    # ══════════════════════════════════════════════════════

    def emit_load_progress(self, percent: int, message: str) -> None:
        """发送加载进度(节流)。"""
        self.load_progress.emit(max(0, min(100, percent)), message)

    def emit_error(self, level: str, message: str) -> None:
        """发送错误信号 (level: 'warn' | 'error')。"""
        self.error_occurred.emit(level, message)

    def reset_to_idle(self) -> None:
        """重置所有状态到 IDLE(用于测试或完全重置)。"""
        self._top_status = TopStatus.IDLE
        self._search_status = SearchSubStatus.IDLE
        self._query_status = QuerySubStatus.IDLE
        self._current_keyword = ""
        self._current_query_slug = ""
        self.clear_failure()
        self.top_status_changed.emit(TopStatus.IDLE.value)
