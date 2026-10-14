"""
[L-Service] SitesService — 常用网站收藏（名称/网址的本地增删与持久化）

依赖: Python 标准库(json / pathlib / urllib) + core.paths
禁止: PySide6, QtWidgets, QtGui, QtCore（纯逻辑层）
返回: dict / list / bool / str / tuple（绝不返回 Qt 对象）

数据模型:
    [{"name": str, "url": str, "desc": str}, ...]
    - name/url 必填；desc 仅预置网站有，用户手动添加的为空串
    - 文件位于 user_data_dir()/sites.json（用户可写，不进安装包）
    - 文件不存在 = 内置默认列表；一旦用户改动即写全量，
      因此"删除预置网站"能被持久记住，reset_sites() 可一键恢复

打开链接由 UI 层用 QDesktopServices 完成，本层只负责数据与校验。
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

from core.paths import user_data_dir

# ── 常量 ──

_FILE_NAME = "sites.json"

# add_site() 返回的原因码（UI 层据此映射文案）
REASON_OK = "ok"
REASON_EMPTY_NAME = "empty_name"
REASON_BAD_URL = "bad_url"
REASON_DUP_URL = "dup_url"

# 预置网站（描述内置；恢复默认时原样返回）
DEFAULT_SITES: list[dict] = [
    {
        "name": "中文维基",
        "url": "https://warframe.huijiwiki.com/wiki/Mainpage",
        "desc": "Warframe 中文玩家维基，战甲、武器、MOD、遗物资料齐全",
    },
    {
        "name": "WM 交易网站",
        "url": "https://warframe.market/zh-hans/",
        "desc": "Warframe.Market 中文站，实时查询玩家交易价格与挂单",
    },
]


# ── URL 处理 ──

def normalize_url(raw: str) -> str | None:
    """把用户输入规范化为可打开的 http(s) URL；非法返回 None。

    规则:
      - 去首尾空白；空串拒绝
      - 无协议头时补 https://（用户通常只输域名）
      - 只允许 http/https（拦截 file://、javascript: 等危险协议）
      - 必须有含点的主机名（拒绝 localhost / 纯乱码）
      - 丢弃 fragment（#锚点对网站首页无意义），保留 path/query
    """
    text = (raw or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = parts.hostname or ""
    if "." not in host:
        return None
    # 主机名不区分大小写，统一小写后重组 netloc（保留端口/IPv6 括号；
    # 含用户名的极少见，原样保留）
    host = host.lower()
    if ":" in host:  # IPv6 字面量需加方括号
        host = f"[{host}]"
    if parts.username is not None:
        netloc = parts.netloc
    elif parts.port is not None:
        netloc = f"{host}:{parts.port}"
    else:
        netloc = host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def _url_key(url: str) -> str:
    """URL 去重比较键：忽略末尾斜杆差异（...market 与 ...market/ 视为同一站）。"""
    return url.rstrip("/")


# ── 读写 ──

def _file_path():
    return user_data_dir() / _FILE_NAME


def _sanitize(raw_item) -> dict | None:
    """把 JSON 中的单条记录清洗为合法结构；无法挽救则返回 None。"""
    if not isinstance(raw_item, dict):
        return None
    name = raw_item.get("name")
    url = normalize_url(str(raw_item.get("url", "")))
    if not isinstance(name, str) or not name.strip() or url is None:
        return None
    desc = raw_item.get("desc", "")
    return {
        "name": name.strip(),
        "url": url,
        "desc": str(desc) if isinstance(desc, str) else "",
    }


def load_sites() -> list[dict]:
    """读取网站列表。

    文件缺失/整体损坏 → 返回内置默认列表的副本；
    列表中的坏项逐条丢弃（不影响其它合法项）。
    """
    path = _file_path()
    if not path.exists():
        return [dict(item) for item in DEFAULT_SITES]
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return [dict(item) for item in DEFAULT_SITES]
    # 走到这里说明文件存在且是合法 JSON 列表：空列表也是合法的用户状态
    # （用户删光了所有网站），不得回退默认，否则删掉的预置项会"复活"。
    # 仅逐条丢弃坏项；全是坏项时返回空列表（用户可点「恢复默认」）。
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_SITES]

    items = [_sanitize(item) for item in raw]
    return [item for item in items if item is not None]


def _write_all(items: list[dict]) -> bool:
    """全量写入；失败返回 False（不抛异常到 UI）。"""
    path = _file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def add_site(name: str, url: str) -> tuple[bool, str]:
    """添加一个网站。

    Returns:
        (是否成功, 原因码)；原因码见模块顶部 REASON_*。
        成功后列表立即落盘。
    """
    site_name = (name or "").strip()
    if not site_name:
        return False, REASON_EMPTY_NAME

    norm = normalize_url(url)
    if norm is None:
        return False, REASON_BAD_URL

    items = load_sites()
    if any(_url_key(item["url"]) == _url_key(norm) for item in items):
        return False, REASON_DUP_URL

    items.append({"name": site_name, "url": norm, "desc": ""})
    _write_all(items)  # 写盘失败不影响本次会话展示（与其它偏好策略一致）
    return True, REASON_OK


def remove_site(index: int) -> bool:
    """按当前列表下标删除一个网站；下标非法返回 False。"""
    items = load_sites()
    if not (0 <= index < len(items)):
        return False
    items.pop(index)
    _write_all(items)
    return True


def reset_sites() -> bool:
    """恢复内置默认网站（覆盖写盘）。"""
    return _write_all([dict(item) for item in DEFAULT_SITES])
