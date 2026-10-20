"""
[L4 Test] riven_table 纯函数测试 — 浮动位置计算与输入解析

覆盖:
  - position_pct: 正值区间 / 负值区间（按绝对值）/ 越界 / 端点 / 退化区间
  - parse_input: 普通数字 / 带 % / 带 + 号 / 全角＋ / 空白 / 非法
  - 模块级列索引常量契约

不创建 QWidget，仅导入模块级纯函数（PySide6 已安装即可）。
"""

from __future__ import annotations

import sys
import os

import pytest

_PROJECT_ROOT = str(__file__).rsplit(os.sep, 2)[0]
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.widgets.riven_table import (
    position_pct,
    parse_input,
    COL_NAME,
    COL_MIN,
    COL_MAX,
    COL_MINE,
    COL_POS,
)


class TestPositionPct:
    """位置百分比计算。"""

    def test_positive_range(self):
        # 基础伤害 +139.9% ~ +171.0%，输入 150
        assert position_pct(150.0, 139.9, 171.0) == pytest.approx(32.48, abs=0.01)

    def test_positive_endpoints(self):
        assert position_pct(139.9, 139.9, 171.0) == pytest.approx(0.0)
        assert position_pct(171.0, 139.9, 171.0) == pytest.approx(100.0)

    def test_negative_range_uses_absolute(self):
        # 装填速度 -33.9% ~ -41.5%，输入 -37：按幅度 (37-33.9)/(41.5-33.9)
        assert position_pct(-37.0, -33.9, -41.5) == pytest.approx(40.79, abs=0.01)

    def test_negative_range_endpoints(self):
        assert position_pct(-33.9, -33.9, -41.5) == pytest.approx(0.0)
        assert position_pct(-41.5, -33.9, -41.5) == pytest.approx(100.0)

    def test_sign_insensitive(self):
        # 输入正负号不影响（幅度比较）
        assert position_pct(37.0, -33.9, -41.5) == pytest.approx(40.79, abs=0.01)

    def test_out_of_range_high(self):
        # 暴击伤害 +101.8% ~ +124.4%，输入 200 → 越界
        p = position_pct(200.0, 101.8, 124.4)
        assert p is not None and p > 100.0

    def test_out_of_range_low(self):
        p = position_pct(50.0, 76.3, 93.3)
        assert p is not None and p < 0.0

    def test_plain_number_range(self):
        # 穿透 2.29 ~ 2.80，输入 2.50
        assert position_pct(2.50, 2.29, 2.80) == pytest.approx(41.18, abs=0.01)

    def test_degenerate_range_returns_none(self):
        assert position_pct(10.0, 5.0, 5.0) is None
        assert position_pct(10.0, -5.0, 5.0) is None  # 幅度相同也算退化


class TestParseInput:
    """输入解析。"""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("150", 150.0),
            ("150%", 150.0),
            ("+150", 150.0),
            ("＋150", 150.0),
            ("-37.0", -37.0),
            (" 2.5 ", 2.5),
            ("0", 0.0),
        ],
    )
    def test_valid_inputs(self, text, expected):
        assert parse_input(text) == pytest.approx(expected)

    @pytest.mark.parametrize("text", ["", "   ", "%", "abc", "--3", "1.2.3"])
    def test_invalid_inputs(self, text):
        assert parse_input(text) is None


class TestColumnContract:
    """列索引常量契约（页面/测试共用）。"""

    def test_column_indices(self):
        assert (COL_NAME, COL_MIN, COL_MAX, COL_MINE, COL_POS) == (0, 1, 2, 3, 4)
