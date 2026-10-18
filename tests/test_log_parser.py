"""LogParserService：解析正确性与「可取消」行为。

这两个用例同时充当 P0-2 的回归网：
  - 取消必须抛 ParseCancelled（而不是被通用 except 吞成 None）
  - 正常解析的字段映射不能因改造漂移
"""

from __future__ import annotations

import pytest

from core.services.log_parser_service import LogParserService, ParseCancelled

_SINGLE_MISSION_LOG = """\
1.0 Sys [Info]: Set squad mission: {"name":"SolNode309"}
2.0 Sys [Info]: OnStateStarted, mission type=MT_SURVIVAL
3.0 Sys [Info]: MISSION_REWARD_CREDITS): 5000
4.0 Sys [Info]: Mission Succeeded
5.0 Sys [Info]: OpenLevel - /Lotus/Levels/PlayerShip
"""


def test_parse_extracts_single_mission(tmp_path):
    log = tmp_path / "EE.log"
    log.write_text(_SINGLE_MISSION_LOG, encoding="utf-8")

    result = LogParserService.parse(str(log))

    assert result is not None
    assert result.total_missions == 1
    mission = result.missions[0]
    assert mission.node_id == "SolNode309"
    assert mission.mission_type == "MT_SURVIVAL"
    assert mission.mission_type_name == "生存"
    assert mission.credits == 5000
    assert mission.success is True
    assert mission.is_ongoing is False


def test_parse_missing_file_returns_none(tmp_path):
    assert LogParserService.parse(str(tmp_path / "not_exists.log")) is None


def test_parse_can_be_cancelled(tmp_path):
    log = tmp_path / "big.log"
    log.write_text(
        "".join(f"{i}.0 Sys [Info]: noise line\n" for i in range(5000)),
        encoding="utf-8",
    )
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return True

    with pytest.raises(ParseCancelled):
        LogParserService.parse(str(log), should_cancel=should_cancel)

    # 取消检查每 2000 行一次，5000 行文件应在第一个检查点就中止
    assert calls["n"] == 1


def test_parse_without_cancel_callback_still_works(tmp_path):
    log = tmp_path / "EE.log"
    log.write_text(_SINGLE_MISSION_LOG, encoding="utf-8")

    result = LogParserService.parse(str(log), should_cancel=None)

    assert result is not None and result.total_missions == 1
