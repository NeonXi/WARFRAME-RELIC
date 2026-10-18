"""
[L-Infrastructure] core.services.http_client — 统一 HTTP 客户端

═══════════════════════════════════════════════════════════════════════
依赖图(严格自上而下,下层不能反向依赖)
═══════════════════════════════════════════════════════════════════════
  core.services.http_client  ← 本文件
       ↓ 允许依赖
  requests 库
       ↓ 禁止依赖
  PySide6 / Qt 任何模块
  core.services.* / core.state.* / core.widgets.* / core.pages.*

═══════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════
  - 封装 requests.Session 复用(连接池)
  - 统一 headers(User-Agent / Platform / Language)
  - 重试策略: 指数退避,仅对 NetworkError / TimeoutError / 5xx 重试
  - 超时分两段: connect (5s) + read (10s)
  - 错误归一化: NetworkError / TimeoutError / ApiError

═══════════════════════════════════════════════════════════════════════
设计要点
═══════════════════════════════════════════════════════════════════════
  - 单例 HttpClient.instance()
  - 纯函数式 API:get_json(url) → dict,无副作用
  - 调用方负责捕获 HttpError 子类处理
  - 重试 sleep 在调用线程(因为是同步函数),调用方决定是同步还是异步
"""

from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter


# ════════════════════════════════════════════════════════════════════════
#  配置常量
# ════════════════════════════════════════════════════════════════════════

# 重试配置
DEFAULT_MAX_RETRIES = 3                        # 失败最多重试 3 次(共 4 次尝试)
DEFAULT_RETRY_BACKOFF = [1.0, 2.0, 4.0]        # 指数退避(秒),3 次重试各 sleep 多久

# 超时配置
# WM API (warframe.market) 响应普遍偏慢(订单接口 200KB+ 常需 20-30s,
# 物品列表 2.5MB+),原 5s/10s 频繁超时导致"查不到价格"。
DEFAULT_CONNECT_TIMEOUT = 10.0                 # TCP 连接 + SSL 握手超时
DEFAULT_READ_TIMEOUT = 30.0                    # 单次读响应超时(订单接口够用)

# Session 配置
DEFAULT_POOL_SIZE = 10                         # 连接池大小
DEFAULT_HEADERS = {
    "User-Agent": "WARFRAME-RELIC/1.0",
    "Accept": "application/json",
    "Platform": "pc",
    "Language": "zh-hans",
}

# 调试日志
from core.logging_utils import log as _dbg


# ════════════════════════════════════════════════════════════════════════
#  异常类层次
# ════════════════════════════════════════════════════════════════════════

class HttpError(Exception):
    """HTTP 层错误基类。

    Attributes:
        message: 人类可读错误描述
        status_code: HTTP 状态码(None = 网络层失败,没有响应)
        url: 失败的 URL
        attempt: 第几次尝试失败(1-based)
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        url: str = "",
        attempt: int = 1,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.url = url
        self.attempt = attempt
        super().__init__(self._format_msg())

    def _format_msg(self) -> str:
        parts = [self.message]
        if self.url:
            parts.append(f"url={self.url}")
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        parts.append(f"attempt={self.attempt}")
        return " | ".join(parts)


class NetworkError(HttpError):
    """网络层错误(DNS/连接拒绝/SSL 握手等)。可重试。"""


class TimeoutError(HttpError):  # noqa: F811 (redefines built-in contextually)
    """超时错误(connect 或 read timeout)。可重试。"""


class ApiError(HttpError):
    """API 业务错误(HTTP 4xx / 5xx)。4xx 不可重试,5xx 可重试。"""


# ════════════════════════════════════════════════════════════════════════
#  HttpClient — 统一 HTTP 客户端
# ════════════════════════════════════════════════════════════════════════

class HttpClient:
    """统一 HTTP 客户端(单例,惰性创建)。

    特性:
      - 复用 requests.Session(连接池)
      - 自动重试: NetworkError / TimeoutError / 5xx
      - 4xx 立即抛 ApiError(不重试)
      - 错误归一化为 HttpError 子类
      - 同步 API,调用方自行决定异步封装

    线程安全: 是(requests.Session 是线程安全的)
    """

    _instance: "HttpClient | None" = None

    @classmethod
    def instance(cls) -> "HttpClient":
        """单例访问。"""
        if cls._instance is None:
            cls._instance = HttpClient()
        return cls._instance

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: list[float] | None = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> None:
        # ── 重试配置 ──
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff or list(DEFAULT_RETRY_BACKOFF)
        assert len(self._retry_backoff) >= max_retries, (
            f"retry_backoff 长度({len(self._retry_backoff)})必须 >= max_retries({max_retries})"
        )

        # ── 超时配置 ──
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        # 单次请求总超时 = connect + read
        self._total_timeout = (connect_timeout, read_timeout)

        # ── Session 初始化 ──
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        # 连接池配置
        adapter = HTTPAdapter(pool_connections=DEFAULT_POOL_SIZE, pool_maxsize=DEFAULT_POOL_SIZE)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    # ── 公开 API ──

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """GET 请求并解析 JSON。

        Args:
            url: 请求地址
            params: 查询参数
            timeout: 可选 (connect, read) 超时覆盖。
                     None = 用实例默认值(10s/30s)。
                     物品列表等大响应可传 (10, 60) 等更长读超时。

        Returns:
            dict: 响应的 JSON 内容

        Raises:
            NetworkError: 网络层失败(可重试)
            TimeoutError: 超时(可重试)
            ApiError: HTTP 错误(4xx 不重试,5xx 重试)
        """
        last_exc: HttpError | None = None
        total_attempts = self._max_retries + 1  # 首次 + 重试
        req_timeout = timeout or self._total_timeout

        for attempt in range(1, total_attempts + 1):
            try:
                _dbg("http", f"GET {url} (attempt {attempt}/{total_attempts})")
                response = self._session.get(
                    url,
                    params=params,
                    timeout=req_timeout,
                )
                # 触发 raise_for_status,把 HTTP 4xx/5xx 转异常
                response.raise_for_status()
                data = response.json()
                _dbg("http", f"  ✓ {url} 200 OK ({len(response.content)} bytes)")
                return data

            except requests.exceptions.Timeout as e:
                last_exc = TimeoutError(
                    f"请求超时 (connect={self._connect_timeout}s, read={self._read_timeout}s)",
                    url=url,
                    attempt=attempt,
                )
                _dbg("http", f"  ✗ timeout: {e}")
                if attempt < total_attempts:
                    self._sleep_backoff(attempt)
                    continue

            except requests.exceptions.SSLError as e:
                last_exc = NetworkError(
                    f"SSL 握手失败: {e}",
                    url=url,
                    attempt=attempt,
                )
                _dbg("http", f"  ✗ SSL: {e}")
                if attempt < total_attempts:
                    self._sleep_backoff(attempt)
                    continue

            except requests.exceptions.ConnectionError as e:
                last_exc = NetworkError(
                    f"连接失败: {e}",
                    url=url,
                    attempt=attempt,
                )
                _dbg("http", f"  ✗ connection: {e}")
                if attempt < total_attempts:
                    self._sleep_backoff(attempt)
                    continue

            except requests.exceptions.HTTPError as e:
                # raise_for_status 触发后到这里
                status = e.response.status_code if e.response is not None else 0
                # 4xx 不重试,5xx 重试
                if 400 <= status < 500:
                    last_exc = ApiError(
                        f"HTTP {status} (客户端错误,不重试)",
                        status_code=status,
                        url=url,
                        attempt=attempt,
                    )
                    _dbg("http", f"  ✗ HTTP {status} (4xx, 不重试)")
                    break  # 4xx 直接抛
                else:
                    last_exc = ApiError(
                        f"HTTP {status} (服务端错误)",
                        status_code=status,
                        url=url,
                        attempt=attempt,
                    )
                    _dbg("http", f"  ✗ HTTP {status} (5xx, 重试)")
                    if attempt < total_attempts:
                        self._sleep_backoff(attempt)
                        continue

            except requests.exceptions.JSONDecodeError as e:
                # 响应不是 JSON(可能是 HTML 错误页)
                last_exc = ApiError(
                    f"响应不是 JSON: {e}",
                    status_code=last_exc.status_code if last_exc else None,
                    url=url,
                    attempt=attempt,
                )
                _dbg("http", f"  ✗ JSON decode: {e}")
                break  # JSON 错误不重试

            except requests.exceptions.RequestException as e:
                # 其他 requests 异常(兜底)
                last_exc = NetworkError(
                    f"未知 requests 错误: {type(e).__name__}: {e}",
                    url=url,
                    attempt=attempt,
                )
                _dbg("http", f"  ✗ request: {e}")
                if attempt < total_attempts:
                    self._sleep_backoff(attempt)
                    continue

        # 所有重试都失败
        assert last_exc is not None
        raise last_exc

    # ── 内部 ──

    def _sleep_backoff(self, attempt: int) -> None:
        """指数退避 sleep。attempt=1 后 sleep retry_backoff[0] 秒。"""
        idx = min(attempt - 1, len(self._retry_backoff) - 1)
        delay = self._retry_backoff[idx]
        _dbg("http", f"  ⏳ 退避 {delay}s 后重试")
        time.sleep(delay)
