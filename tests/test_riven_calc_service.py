"""
[L-Service Test] RivenCalcService 单元测试

覆盖:
  - 数据加载（JSON 只读资源）
  - 武器类型 / 布局枚举
  - 布局系数正确性
  - 单属性计算（% 与 n 两种单位）
  - compute 输出结构（has_negative / positive / negative）
  - 格式化输出（% 加正号 / n 两位小数 / 负值自然带减号）
  - 缺失值跳过（某武器类型无此词条时忽略）
  - 无效武器 / 布局退化（不抛异常）
  - 缓存 reload_data 隔离

禁止: PySide6（本测试不依赖 Qt）
"""

from __future__ import annotations

import json
import sys
import os
import pytest

_PROJECT_ROOT = str(__file__).rsplit(os.sep, 2)[0]
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.services import riven_calc_service as rs


@pytest.fixture(autouse=True)
def reset_cache():
    """每条测试前强制刷新数据缓存，避免跨测试污染。"""
    rs.reload_data()


class TestDataLoading:
    """只读数据加载与基本结构。"""

    def test_weapon_types(self):
        assert rs.list_weapon_types() == ["步枪", "霰弹枪", "手枪", "空战", "近战"]

    def test_layouts(self):
        assert rs.list_layouts() == ["2正", "2正1负", "3正", "3正1负"]

    def test_layout_coefficients(self):
        assert rs.get_layout("2正") == {"pos": 0.99, "neg": 0.0}
        assert rs.get_layout("2正1负") == {"pos": 1.2375, "neg": -0.495}
        assert rs.get_layout("3正") == {"pos": 0.75, "neg": 0.0}
        assert rs.get_layout("3正1负") == {"pos": 0.9375, "neg": -0.75}

    def test_float_range(self):
        assert rs.float_range() == (0.9, 1.1)

    def test_unknown_layout_returns_none(self):
        assert rs.get_layout("不存在") is None

    def test_attributes_count(self):
        data = rs.load_data()
        # 32 原始词条 → 冰火毒电合并、冲击穿刺切割合并、新增异常状态伤害，
        # 再把手枪专属的「冲击伤害」单独拆出 → 29 条
        assert len(data["attributes"]) == 29

    def test_merged_attributes(self):
        """冰火毒电 → 属性伤害；切割/穿刺 → 物理伤害（冲击对手枪单独保留）。"""
        names = {a["name"] for a in rs.load_data()["attributes"]}
        for merged in (
            "冰冻伤害", "毒素伤害", "电击伤害", "火焰伤害",
            "切割伤害", "穿刺伤害",
        ):
            assert merged not in names, f"应已合并：{merged}"
        assert "属性伤害" in names
        assert "物理伤害" in names
        assert "冲击伤害" in names  # 手枪专属，单独保留

    def test_pistol_only_impact(self):
        """「冲击伤害」只对手枪有值（1.188），其余武器类型为空。"""
        by_name = {a["name"]: a for a in rs.load_data()["attributes"]}
        values = by_name["冲击伤害"]["values"]
        assert values["手枪"] == 1.188
        for other in ("步枪", "霰弹枪", "空战", "近战"):
            assert values[other] is None

    def test_pistol_compute_has_impact_row(self):
        pistol = {r["name"] for r in rs.compute("手枪", 1.0, "3正")["positive"]}
        rifle = {r["name"] for r in rs.compute("步枪", 1.0, "3正")["positive"]}
        assert "冲击伤害" in pistol
        assert "冲击伤害" not in rifle

    def test_merged_attribute_values(self):
        by_name = {a["name"]: a for a in rs.load_data()["attributes"]}
        assert by_name["属性伤害"]["values"] == {
            "步枪": 0.9, "霰弹枪": 0.9, "手枪": 0.9, "空战": 1.197, "近战": 0.9,
        }
        # 物理伤害取切割/穿刺的 1.1997（手枪的 1.188 冲击已单列为独立词条）
        assert by_name["物理伤害"]["values"]["手枪"] == 1.1997
        assert by_name["物理伤害"]["values"]["空战"] == 0.9

    def test_status_damage_uses_proc_chance_base(self):
        """新增「异常状态伤害」，基础数值与触发几率一致。"""
        by_name = {a["name"]: a for a in rs.load_data()["attributes"]}
        assert "异常状态伤害" in by_name
        assert by_name["异常状态伤害"]["unit"] == "%"
        assert by_name["异常状态伤害"]["values"] == by_name["触发几率"]["values"]


class TestComputePositive:
    """正面词条计算。"""

    def test_positive_rows_sorted_by_abs_max_desc(self):
        result = rs.compute("步枪", 1.0, "3正")
        max_vals = [r["max"] for r in result["positive"]]
        assert all(abs(max_vals[i]) >= abs(max_vals[i + 1]) for i in range(len(max_vals) - 1))

    def test_positive_format_percent(self):
        result = rs.compute("步枪", 1.0, "3正")
        row = next(r for r in result["positive"] if r["name"] == "基础伤害")
        # base 1.65 * 0.75 * 1.0 * 0.9 = 1.11375 → +111.4%
        assert row["min_str"] == "+111.4%"
        assert row["max_str"] == "+136.1%"

    def test_positive_format_number(self):
        result = rs.compute("步枪", 1.0, "3正")
        row = next(r for r in result["positive"] if r["name"] == "穿透")
        # base 2.7 * 0.75 * 1.0 * 0.9 = 1.8225 → "1.82"
        assert row["min_str"] == "1.82"
        # base 2.7 * 0.75 * 1.0 * 1.1 = 2.2275 → "2.23"
        assert row["max_str"] == "2.23"

    def test_no_negative_for_pure_positive_layouts(self):
        for layout in ("2正", "3正"):
            result = rs.compute("步枪", 1.0, layout)
            assert result["has_negative"] is False
            assert result["negative"] == []


class TestComputeNegative:
    """负面词条计算。"""

    def test_has_negative_for_mixed_layouts(self):
        for layout in ("2正1负", "3正1负"):
            result = rs.compute("步枪", 1.0, layout)
            assert result["has_negative"] is True
            assert len(result["negative"]) > 0

    def test_negative_value_sign_with_positive_base(self):
        """正面基值 + 负系数 → 负结果（如装填速度降低）。"""
        result = rs.compute("步枪", 1.0, "3正1负")
        row = next(r for r in result["negative"] if r["name"] == "装填速度")
        # base 0.5 * -0.75 * 1.0 * 0.9 = -0.3375 → "-33.8%"
        assert row["min_str"] == "-33.8%"
        # base 0.5 * -0.75 * 1.0 * 1.1 = -0.4125 → "-41.2%"
        assert row["max_str"] == "-41.2%"

    def test_negative_value_sign_with_negative_base(self):
        """负面基值（后坐力 -0.9）+ 负系数 → 正结果（后坐力升高）。"""
        result = rs.compute("步枪", 1.0, "3正1负")
        row = next(r for r in result["negative"] if r["name"] == "后坐力")
        # base -0.9 * -0.75 * 1.0 * 0.9 = +0.6075 → "+60.8%"
        assert row["min_str"] == "+60.8%"
        # base -0.9 * -0.75 * 1.0 * 1.1 = +0.7425（浮点实际 0.7425000000000002）→ "+74.3%"
        assert row["max_str"] == "+74.3%"


class TestMissingValues:
    """武器类型下缺失的词条应被跳过。"""

    def test_melee_only_attrs_hidden_for_rifle(self):
        result = rs.compute("步枪", 1.0, "3正1负")
        names = {r["name"] for r in result["positive"]}
        assert "额外连击数几率" not in names
        assert "连击持续时间" not in names
        assert "范围" not in names

    def test_negative_group_also_skips_missing(self):
        result = rs.compute("步枪", 1.0, "3正1负")
        names = {r["name"] for r in result["negative"]}
        assert "后坐力" in names  # 步枪有后坐力
        assert "范围" not in names  # 步枪无范围


class TestEdgeCases:
    """边界与退化。"""

    def test_invalid_weapon_returns_empty(self):
        result = rs.compute("不存在的武器", 1.0, "3正")
        assert result["positive"] == []
        assert result["negative"] == []
        assert result["has_negative"] is False

    def test_invalid_layout_returns_empty(self):
        result = rs.compute("步枪", 1.0, "四正")
        assert result["positive"] == []
        assert result["negative"] == []
        assert result["has_negative"] is False

    def test_zero_disposition_all_zero(self):
        result = rs.compute("步枪", 0.0, "3正")
        for row in result["positive"]:
            assert row["min"] == 0.0
            assert row["max"] == 0.0
            if row["unit"] == "%":
                assert row["min_str"] == "0.0%"
            else:
                assert row["min_str"] == "0.00"

    def test_format_value_edge_cases(self):
        assert rs.format_value(0.0, "%") == "0.0%"
        assert rs.format_value(-0.5, "%") == "-50.0%"
        assert rs.format_value(0.12345, "%") == "+12.3%"
        assert rs.format_value(2.7, "n") == "2.70"
        assert rs.format_value(-1.5, "n") == "-1.50"
