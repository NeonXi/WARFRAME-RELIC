"""
WorldClockService 单元测试 — 世界时钟数据层（时区校验/增删/时间换算）。

覆盖:
  - 默认列表（仅北京）与文件缺失行为
  - add_city 校验：空名 / 非法时区 / 重复时区 / 成功落盘
  - 坏数据清洗：非法条目逐条丢弃、同区去重、空列表不回退默认
  - remove / reset 语义
  - 时间换算：now_in_zone / zone_offset_label / day_shift（注入固定时刻）

测试隔离：monkeypatch world_clock_service.user_data_dir 指向 tmp_path，
不碰开发者本机 data/ 下的真实 world_clock.json。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.services import world_clock_service as svc


@pytest.fixture()
def isolated_data(tmp_path, monkeypatch):
    """把用户数据目录重定向到临时目录，并清掉服务内可能的缓存。"""
    monkeypatch.setattr(svc, "user_data_dir", lambda: tmp_path)
    return tmp_path


# 固定基准时刻：2026-10-19 12:00 UTC（周一）
#   - 北京 (UTC+8)  = 20:00 当天
#   - 东京 (UTC+9)  = 21:00 当天
#   - 纽约 (UTC-4, EDT) = 08:00 当天
#   - 悉尼 (UTC+11, AEDT) = 23:00 当天
#   - 檀香山 (UTC-10) = 02:00 当天
_FIXED_NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)


class TestDefaults:

    def test_default_is_beijing(self, isolated_data):
        """文件缺失 → 内置默认（仅北京）。"""
        cities = svc.load_cities()
        assert cities == [{"name": "北京", "tz": "Asia/Shanghai"}]

    def test_corrupt_file_falls_back(self, isolated_data):
        """文件损坏 → 回退默认列表。"""
        (isolated_data / "world_clock.json").write_text(
            "{not json", encoding="utf-8"
        )
        assert svc.load_cities() == [{"name": "北京", "tz": "Asia/Shanghai"}]

    def test_empty_list_is_user_state(self, isolated_data):
        """空列表是合法用户状态（删光时钟），不得回退默认。"""
        (isolated_data / "world_clock.json").write_text("[]", encoding="utf-8")
        assert svc.load_cities() == []


class TestSanitize:

    def test_bad_entries_dropped(self, isolated_data):
        """坏项逐条丢弃，好项保留。"""
        (isolated_data / "world_clock.json").write_text(
            """[
                {"name": "东京", "tz": "Asia/Tokyo"},
                {"name": "", "tz": "Asia/Seoul"},
                {"name": "坏时区", "tz": "Mars/Olympus"},
                "not-a-dict",
                {"tz": "Asia/Seoul"}
            ]""",
            encoding="utf-8",
        )
        cities = svc.load_cities()
        assert cities == [{"name": "东京", "tz": "Asia/Tokyo"}]

    def test_duplicate_timezone_deduped(self, isolated_data):
        """同一时区只保留首条（手工编辑 JSON 时防重复表盘）。"""
        (isolated_data / "world_clock.json").write_text(
            """[
                {"name": "东京", "tz": "Asia/Tokyo"},
                {"name": "东京2", "tz": "Asia/Tokyo"}
            ]""",
            encoding="utf-8",
        )
        cities = svc.load_cities()
        assert len(cities) == 1
        assert cities[0]["name"] == "东京"


class TestAddCity:

    def test_add_success_and_persisted(self, isolated_data):
        ok, reason = svc.add_city("伦敦", "Europe/London")
        assert (ok, reason) == (True, svc.REASON_OK)
        cities = svc.load_cities()
        assert {"name": "伦敦", "tz": "Europe/London"} in cities

    def test_empty_name_rejected(self, isolated_data):
        ok, reason = svc.add_city("   ", "Europe/London")
        assert ok is False
        assert reason == svc.REASON_EMPTY_NAME

    def test_bad_timezone_rejected(self, isolated_data):
        ok, reason = svc.add_city("火星", "Mars/Olympus")
        assert ok is False
        assert reason == svc.REASON_BAD_TIMEZONE

    def test_duplicate_timezone_rejected(self, isolated_data):
        svc.add_city("家里", "Asia/Shanghai")  # 与默认北京同时区
        ok, reason = svc.add_city("另一个名字", "Asia/Shanghai")
        assert ok is False
        assert reason == svc.REASON_DUPLICATE

    def test_whitespace_stripped(self, isolated_data):
        svc.add_city("  纽约  ", "  America/New_York  ")
        cities = svc.load_cities()
        assert {"name": "纽约", "tz": "America/New_York"} in cities


class TestRemoveAndReset:

    def test_remove_by_index(self, isolated_data):
        svc.add_city("东京", "Asia/Tokyo")
        assert svc.remove_city(1) is True   # 0=北京（默认），1=东京
        assert svc.load_cities() == [{"name": "北京", "tz": "Asia/Shanghai"}]

    def test_remove_bad_index(self, isolated_data):
        assert svc.remove_city(99) is False
        assert svc.remove_city(-1) is False

    def test_reset_restores_default(self, isolated_data):
        svc.reset_cities()
        svc.add_city("巴黎", "Europe/Paris")
        assert len(svc.load_cities()) == 2
        svc.reset_cities()
        assert svc.load_cities() == [{"name": "北京", "tz": "Asia/Shanghai"}]


class TestTimezoneValidation:

    @pytest.mark.parametrize("tz", [
        "Asia/Shanghai", "America/New_York", "UTC", "Pacific/Auckland",
    ])
    def test_valid(self, tz):
        assert svc.is_valid_timezone(tz) is True

    @pytest.mark.parametrize("tz", [
        "Mars/Olympus", "", "   ", "not a zone", None,
    ])
    def test_invalid(self, tz):
        assert svc.is_valid_timezone(tz) is False


class TestTimeConversion:
    """时间换算 —— 注入固定时刻，结果不依赖运行时机。"""

    def test_beijing_offset_and_time(self):
        moment = svc.now_in_zone("Asia/Shanghai", _FIXED_NOW)
        assert (moment.hour, moment.minute) == (20, 0)
        assert svc.zone_offset_label("Asia/Shanghai", _FIXED_NOW) == "UTC+8"

    def test_new_york_offset_dst(self):
        """纽约 10 月处于夏令时（EDT, UTC-4）。"""
        moment = svc.now_in_zone("America/New_York", _FIXED_NOW)
        assert (moment.hour, moment.minute) == (8, 0)
        assert svc.zone_offset_label("America/New_York", _FIXED_NOW) == "UTC-4"

    def test_half_hour_offset_label(self):
        """印度 UTC+5:30 —— 非整点偏移必须显示分钟。"""
        assert svc.zone_offset_label("Asia/Kolkata", _FIXED_NOW) == "UTC+05:30"

    def test_bad_zone_falls_back_utc(self):
        """非法时区按 UTC 兜底，不抛异常（页面每秒刷新路径必须稳）。"""
        moment = svc.now_in_zone("Mars/Olympus", _FIXED_NOW)
        assert (moment.hour, moment.minute) == (12, 0)

    def test_day_shift(self):
        """北京时间 20:00 当天；檀香山 02:00 当天；基准时刻不变时都是 0。"""
        assert svc.day_shift("Asia/Shanghai", _FIXED_NOW) == 0
        assert svc.day_shift("Pacific/Honolulu", _FIXED_NOW) == 0

    def test_day_shift_crosses_midnight(self):
        """UTC 15:00 → 悉尼 UTC+11 已是次日 02:00（shift=+1）。"""
        now = datetime(2026, 10, 19, 15, 0, 0, tzinfo=timezone.utc)
        assert svc.day_shift("Australia/Sydney", now) == 1

    def test_local_offset_label_format(self):
        """本机偏移标签与 zone_offset_label 同格式（正则校验形态即可，
        因为本机时区随运行环境变化，不能硬编码期望值）。"""
        import re
        label = svc.local_offset_label(_FIXED_NOW)
        assert re.fullmatch(r"UTC([+-]\d{1,2})(:\d{2})?", label), label
