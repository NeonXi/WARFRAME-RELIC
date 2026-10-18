"""
[L-Service] core.services.wm_items_repository — WM 全物品列表仓库

═══════════════════════════════════════════════════════════════════════
依赖图(严格自上而下,下层不能反向依赖)
═══════════════════════════════════════════════════════════════════════
  core.services.wm_items_repository  ← 本文件
       ↓ 允许依赖
  core.services.http_client (HttpClient, HttpError/NetworkError/TimeoutError/ApiError)
  core.state.price_query_state (PriceQueryState 单例)
  Python 标准库 (threading, time)
       ↓ 禁止依赖
  PySide6.QtWidgets / QtGui
  core.widgets.* / core.pages.*

═══════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════
  - 加载 warframe.market 全物品列表(WM v2 API)
  - 缓存到 PriceQueryState
  - 失败冷却: 失败后 30s 内不自动重试
  - 异步预热(后台线程,非阻塞)
  - 手动刷新(忽略冷却)

═══════════════════════════════════════════════════════════════════════
设计要点
═══════════════════════════════════════════════════════════════════════
  - 纯业务类(不继承 QObject),用 threading 异步
  - 状态变化通过 PriceQueryState 通知
  - 不持有 widget 引用
  - 错误处理: 不抛异常,降级返回空列表 + 记录失败
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from core.services.http_client import (
    HttpClient, HttpError, NetworkError, TimeoutError, ApiError,
    DEFAULT_CONNECT_TIMEOUT,
)
from core.state.price_query_state import (
    PriceQueryState, TopStatus, ItemTuple,
)
from core.logging_utils import log as _dbg


if TYPE_CHECKING:
    pass


# ════════════════════════════════════════════════════════════════════════
#  配置常量
# ════════════════════════════════════════════════════════════════════════

# WM v2 API 全物品列表端点
WM_API_ITEMS_URL = "https://api.warframe.market/v2/items"

# 要从搜索中排除的 tag(非交易/装饰性物品)
_EXCLUDED_TAGS = frozenset({
    "glyph", "skin", "helmet", "animation", "relic", "mod",
})


# ════════════════════════════════════════════════════════════════════════
#  WmItemsRepository — 全物品列表仓库(单例)
# ════════════════════════════════════════════════════════════════════════

class WmItemsRepository:
    """WM 全物品列表仓库(单例)。

    线程安全: 简单锁保护(warm_cache_async 可能并发触发)
    """

    _instance: "WmItemsRepository | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "WmItemsRepository":
        """单例访问(惰性创建)。"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = WmItemsRepository()
        return cls._instance

    def __init__(self) -> None:
        self._http = HttpClient.instance()
        self._state = PriceQueryState.instance()
        # 防止同一实例并发预热
        self._warm_lock = threading.Lock()
        self._warm_in_progress: bool = False
        self._warm_thread: threading.Thread | None = None

    # ══════════════════════════════════════════════════════
    #  公开 API
    # ══════════════════════════════════════════════════════

    def get_items(self) -> list[ItemTuple]:
        """取当前缓存(只读副本)。"""
        return self._state.get_items()

    def has_items(self) -> bool:
        return self._state.has_items()

    def warm_cache_async(self, force: bool = False) -> None:
        """异步预热缓存(后台线程,不阻塞调用方)。

        Args:
            force: True = 忽略冷却 + 缓存,强制重新加载

        行为:
          - 已有缓存 + 不强制 + 新鲜: 直接 return(用户体感瞬开)
          - 已有缓存 + 不强制 + 软过期(>24h): 启动后台静默刷新(不阻塞 UI)
          - 无缓存 + 失败冷却中 + 不强制: 直接 return
          - 否则: 启动 daemon 线程跑 _fetch_with_retry
        """
        with self._warm_lock:
            # 已经在跑
            if self._warm_in_progress:
                _dbg("repo", "warm_cache_async: 已在运行, 跳过")
                return

            # 已有缓存 + 不强制
            if not force and self._state.has_items():
                if self._state.is_items_cache_stale():
                    # 软过期:后台静默刷新(不阻塞,让用户继续用旧缓存)
                    _dbg(
                        "repo",
                        f"warm_cache_async: 缓存 {self._state.items_age_seconds():.0f}s 老, "
                        f"后台静默刷新",
                    )
                    # 走下面启动后台线程的逻辑
                else:
                    _dbg("repo", "warm_cache_async: 已有缓存且新鲜, 跳过")
                    return

            # 冷却中 + 不强制 → 跳过
            elif not force and self._state.is_in_failure_cooldown():
                remaining = self._state.failure_cooldown_remaining()
                _dbg("repo", f"warm_cache_async: 冷却中, 还剩 {remaining:.1f}s, 跳过")
                return

            self._warm_in_progress = True

        # 启动后台线程
        self._warm_thread = threading.Thread(
            target=self._warm_worker,
            args=(force,),
            daemon=True,
            name="WmItemsWarmCache",
        )
        self._warm_thread.start()
        _dbg("repo", "warm_cache_async: 启动后台线程")

    def warm_cache_blocking(self, timeout: float = 60.0) -> bool:
        """同步预热(用于测试)。

        Returns:
            bool: True=成功, False=失败
        """
        try:
            items = self._fetch_with_retry()
            self._state.set_items(items)
            self._state.clear_failure()
            self._state.set_top_status(TopStatus.READY)
            return True
        except Exception as e:
            self._state.record_failure(str(e))
            self._state.set_top_status(TopStatus.DEGRADED)
            return False

    def refresh(self) -> None:
        """强制刷新(忽略缓存和冷却,用户主动点"重试"时用)。"""
        _dbg("repo", "refresh: 强制刷新")
        self._state.clear_failure()
        self.warm_cache_async(force=True)

    # ══════════════════════════════════════════════════════
    #  内部
    # ══════════════════════════════════════════════════════

    def _warm_worker(self, force: bool) -> None:
        """后台线程:调用 _fetch_with_retry,更新状态。"""
        try:
            self._state.set_top_status(TopStatus.LOADING)
            self._state.emit_load_progress(10, "正在连接 WM API...")

            items = self._fetch_with_retry()

            self._state.emit_load_progress(90, "正在解析物品列表...")
            self._state.set_items(items)
            # 标记: 本次进程从网络拉的(用于 UI 提示)
            self._state.set_items_source("network")
            # 落盘:下次启动直接复用,免得冷启动又等
            self._state.persist_to_disk()
            self._state.clear_failure()
            self._state.set_top_status(TopStatus.READY)
            self._state.emit_load_progress(100, f"已加载 {len(items)} 个物品")
            self._state.emit_error("info", f"已加载 {len(items)} 个物品")
        except HttpError as e:
            self._state.record_failure(str(e))
            self._state.set_top_status(TopStatus.DEGRADED)
            self._state.emit_load_progress(0, f"加载失败: {e.message}")
            self._state.emit_error("warn", f"WM 物品列表加载失败: {e.message}")
        except Exception as e:
            self._state.record_failure(f"未预期错误: {type(e).__name__}: {e}")
            self._state.set_top_status(TopStatus.DEGRADED)
            self._state.emit_load_progress(0, f"加载失败: {e}")
            self._state.emit_error("error", f"WM 物品列表异常: {e}")
        finally:
            with self._warm_lock:
                self._warm_in_progress = False

    def _fetch_with_retry(self) -> list[ItemTuple]:
        """实际下载 + 解析。

        Raises:
            HttpError: 网络/超时/API 错误(经 HttpClient 重试后仍失败)
        """
        self._state.emit_load_progress(30, "正在下载...")
        # 物品列表 2.5MB+,WM API 慢,单独给 60s 读超时
        data = self._http.get_json(
            WM_API_ITEMS_URL, timeout=(DEFAULT_CONNECT_TIMEOUT, 60.0)
        )
        self._state.emit_load_progress(70, "正在解析...")

        items_raw = data.get("data", [])
        if not isinstance(items_raw, list):
            raise ApiError(
                f"响应格式错误: data 字段不是 list (got {type(items_raw).__name__})",
                url=WM_API_ITEMS_URL,
            )

        result: list[ItemTuple] = []
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            i18n = item.get("i18n", {})
            en = i18n.get("en", {}) if isinstance(i18n, dict) else {}
            name = en.get("name", "")
            slug = item.get("slug", "")
            tags = item.get("tags", [])
            if not name or not slug:
                continue
            # 过滤掉非交易物品
            if any(t in _EXCLUDED_TAGS for t in tags):
                continue
            result.append((name, slug, list(tags)))

        return result
