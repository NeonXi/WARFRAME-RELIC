"""
[L-Service] WorldClockService — 世界时钟（城市时区列表的本地增删与时间换算）

依赖: Python 标准库(datetime / json / pathlib / zoneinfo) + core.paths
禁止: PySide6, QtWidgets, QtGui, QtCore（纯逻辑层）
返回: dict / list / bool / str / tuple / datetime（绝不返回 Qt 对象）

数据模型:
    [{"name": str, "tz": str}, ...]
    - name 展示名（用户可改，如"北京"/"家里时间"）；tz 为 IANA 时区键
      （如 "Asia/Shanghai"），必须能被 zoneinfo 解析
    - 文件位于 user_data_dir()/world_clock.json（用户可写，不进安装包）
    - 文件不存在 = 内置默认（仅北京）；一旦用户改动即写全量，
      因此"删掉默认北京"能被持久记住，reset_cities() 可一键恢复

时间换算全部走标准库 zoneinfo（Windows 依赖 tzdata 包提供时区数据库，
见 requirements.txt）。页面层的走动秒针只需要每秒调一次
now_in_zone()，本层不做任何定时/线程，渲染由 UI 层负责。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.paths import user_data_dir

# ── 常量 ──

_FILE_NAME = "world_clock.json"

# add_city() 返回的原因码（UI 层据此映射文案）
REASON_OK = "ok"
REASON_EMPTY_NAME = "empty_name"
REASON_BAD_TIMEZONE = "bad_timezone"
REASON_DUPLICATE = "duplicate"

# 首启默认城市（用户删掉后靠 reset_cities 恢复）
DEFAULT_CITIES: list[dict] = [
    {"name": "北京", "tz": "Asia/Shanghai"},
]

# 添加对话框用的候选城市库：(展示名, IANA 时区键, 所属地区分组)
# 覆盖 commonly used 时区；地区名仅用于对话框下拉分组，不落盘。
# 用户仍可在对话框名称框里自取别名，所以不追求城市清单大而全。
TIMEZONE_CATALOG: list[tuple[str, str, str]] = [
    # ── 亚洲 ──
    ("北京",   "Asia/Shanghai",        "亚洲"),
    ("香港",   "Asia/Hong_Kong",       "亚洲"),
    ("台北",   "Asia/Taipei",          "亚洲"),
    ("东京",   "Asia/Tokyo",           "亚洲"),
    ("首尔",   "Asia/Seoul",           "亚洲"),
    ("新加坡", "Asia/Singapore",       "亚洲"),
    ("曼谷",   "Asia/Bangkok",         "亚洲"),
    ("雅加达", "Asia/Jakarta",         "亚洲"),
    ("马尼拉", "Asia/Manila",          "亚洲"),
    ("吉隆坡", "Asia/Kuala_Lumpur",    "亚洲"),
    ("迪拜",   "Asia/Dubai",           "亚洲"),
    ("孟买",   "Asia/Kolkata",         "亚洲"),
    ("卡拉奇", "Asia/Karachi",         "亚洲"),
    ("阿拉木图", "Asia/Almaty",        "亚洲"),
    # ── 欧洲 ──
    ("伦敦",   "Europe/London",        "欧洲"),
    ("都柏林", "Europe/Dublin",        "欧洲"),
    ("里斯本", "Europe/Lisbon",        "欧洲"),
    ("巴黎",   "Europe/Paris",         "欧洲"),
    ("柏林",   "Europe/Berlin",        "欧洲"),
    ("阿姆斯特丹", "Europe/Amsterdam", "欧洲"),
    ("马德里", "Europe/Madrid",        "欧洲"),
    ("罗马",   "Europe/Rome",          "欧洲"),
    ("苏黎世", "Europe/Zurich",        "欧洲"),
    ("斯德哥尔摩", "Europe/Stockholm", "欧洲"),
    ("华沙",   "Europe/Warsaw",        "欧洲"),
    ("莫斯科", "Europe/Moscow",        "欧洲"),
    ("伊斯坦布尔", "Europe/Istanbul",  "欧洲"),
    # ── 北美 ──
    ("纽约",     "America/New_York",     "北美"),
    ("多伦多",   "America/Toronto",      "北美"),
    ("芝加哥",   "America/Chicago",      "北美"),
    ("墨西哥城", "America/Mexico_City",  "北美"),
    ("丹佛",     "America/Denver",       "北美"),
    ("洛杉矶",   "America/Los_Angeles",  "北美"),
    ("旧金山",   "America/Los_Angeles",  "北美"),
    ("西雅图",   "America/Los_Angeles",  "北美"),
    ("温哥华",   "America/Vancouver",    "北美"),
    ("安克雷奇", "America/Anchorage",    "北美"),
    ("檀香山",   "Pacific/Honolulu",     "北美"),
    # ── 南美 ──
    ("波哥大",   "America/Bogota",       "南美"),
    ("利马",     "America/Lima",         "南美"),
    ("圣地亚哥", "America/Santiago",     "南美"),
    ("圣保罗",   "America/Sao_Paulo",    "南美"),
    ("布宜诺斯艾利斯", "America/Argentina/Buenos_Aires", "南美"),
    # ── 大洋洲 ──
    ("悉尼",     "Australia/Sydney",     "大洋洲"),
    ("墨尔本",   "Australia/Melbourne",  "大洋洲"),
    ("布里斯班", "Australia/Brisbane",   "大洋洲"),
    ("珀斯",     "Australia/Perth",      "大洋洲"),
    ("奥克兰",   "Pacific/Auckland",     "大洋洲"),
    # ── 非洲 ──
    ("开罗",     "Africa/Cairo",         "非洲"),
    ("拉各斯",   "Africa/Lagos",         "非洲"),
    ("内罗毕",   "Africa/Nairobi",       "非洲"),
    ("约翰内斯堡", "Africa/Johannesburg", "非洲"),
]

# ── 校验 ──


def is_valid_timezone(tz_key: str) -> bool:
    """时区键是否为 zoneinfo 可解析的 IANA 名称。

    ZoneInfo 构造失败（未知键/空串/None）即视为非法；
    已构造过的键有内部缓存，重复调用开销可忽略。
    """
    if not isinstance(tz_key, str) or not tz_key.strip():
        return False
    try:
        ZoneInfo(tz_key.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


def _sanitize(raw_item) -> dict | None:
    """把 JSON 中的单条记录清洗为合法结构；无法挽救则返回 None。"""
    if not isinstance(raw_item, dict):
        return None
    name = raw_item.get("name")
    tz = raw_item.get("tz")
    if not isinstance(name, str) or not name.strip():
        return None
    if not is_valid_timezone(str(tz) if tz is not None else ""):
        return None
    return {"name": name.strip(), "tz": str(tz).strip()}


# ── 读写 ──


def _file_path():
    return user_data_dir() / _FILE_NAME


def load_cities() -> list[dict]:
    """读取城市列表。

    文件缺失/整体损坏 → 返回内置默认列表的副本；
    列表中的坏项逐条丢弃（不影响其它合法项），同一时区只保留首条
    （手工编辑 JSON 造成重复时以先出现者为准）。
    """
    path = _file_path()
    if not path.exists():
        return [dict(item) for item in DEFAULT_CITIES]
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return [dict(item) for item in DEFAULT_CITIES]
    # 走到这里说明文件存在且是合法 JSON 列表：空列表也是合法的用户状态
    # （用户删光了所有时钟），不得回退默认，否则删掉的北京会"复活"。
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_CITIES]

    seen: set[str] = set()
    items: list[dict] = []
    for raw_item in raw:
        item = _sanitize(raw_item)
        if item is None or item["tz"] in seen:
            continue
        seen.add(item["tz"])
        items.append(item)
    return items


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


def add_city(name: str, tz: str) -> tuple[bool, str]:
    """添加一个城市时钟。

    Returns:
        (是否成功, 原因码)；成功后列表立即落盘。
        同一时区不允许重复添加（名字不同也不行——表盘内容会完全一样），
        用户想区分多个同名时区城市时可在名称框里写别名后再从候选里选。
    """
    city_name = (name or "").strip()
    if not city_name:
        return False, REASON_EMPTY_NAME

    tz_key = (tz or "").strip()
    if not is_valid_timezone(tz_key):
        return False, REASON_BAD_TIMEZONE

    items = load_cities()
    if any(item["tz"] == tz_key for item in items):
        return False, REASON_DUPLICATE

    items.append({"name": city_name, "tz": tz_key})
    _write_all(items)  # 写盘失败不影响本次会话展示（与其它偏好策略一致）
    return True, REASON_OK


def remove_city(index: int) -> bool:
    """按当前列表下标删除一个城市；下标非法返回 False。"""
    items = load_cities()
    if not (0 <= index < len(items)):
        return False
    items.pop(index)
    _write_all(items)
    return True


def reset_cities() -> bool:
    """恢复内置默认城市（仅北京，覆盖写盘）。"""
    return _write_all([dict(item) for item in DEFAULT_CITIES])


# ── 时间换算（纯函数，供页面每秒调用） ──


def now_in_zone(tz_key: str, now: datetime | None = None) -> datetime:
    """返回指定时区的当前时间（带时区信息的 aware datetime）。

    Args:
        tz_key: IANA 时区键（调用方需保证合法，违法区返回 UTC 时间兜底）
        now: 换算基准时刻（默认取本机当前时刻）；测试可注入固定值

    时区非法时按 UTC 兜底而不是抛错：页面刷新是每秒执行的高频路径，
    单个坏数据不应让整页计时器崩掉。
    """
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        # 防御：调用方传来 naive 时间时按 UTC 解释，避免 astimezone 歧义
        base = base.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(tz_key)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = timezone.utc
    return base.astimezone(zone)


def zone_offset_label(tz_key: str, now: datetime | None = None) -> str:
    """返回 "UTC+8" / "UTC+05:30" / "UTC-4" 形式的偏移标签。

    整点偏移省略分钟（亚洲大部分地区常见），非整点才显示 :30。
    """
    return _offset_label_of(now_in_zone(tz_key, now))


def local_offset_label(now: datetime | None = None) -> str:
    """返回本机当前时区的偏移标签（与 zone_offset_label 同格式）。

    用于页面里"本地"参照行，让用户知道每张表盘相对自己差了几个小时。
    """
    base = now or datetime.now(timezone.utc)
    return _offset_label_of(base.astimezone())


def _offset_label_of(moment: datetime) -> str:
    """对 aware datetime 直接生成 UTC 偏移标签（内部复用）。"""
    offset = moment.utcoffset()
    if offset is None:
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    if minutes:
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    return f"UTC{sign}{hours}"


def day_shift(tz_key: str, now: datetime | None = None) -> int:
    """目标时区日期相对本机日期的天数差：0=同一天，1=明天，-1=昨天。

    仅按日历日比较（不看具体时刻），页面据此显示"今天/明天/昨天"，
    跨日差 >= 2 天时不显示相对提示（极少见，避免出现"后天"误判夏令时）。
    """
    base = now or datetime.now(timezone.utc)
    local = base.astimezone()
    target = now_in_zone(tz_key, base)
    return (target.date() - local.date()).days
