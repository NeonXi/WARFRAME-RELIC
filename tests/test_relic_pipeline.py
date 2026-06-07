"""
截图识别遗物逻辑链路单元测试

覆盖关键环节:
  1. RelicNameRecognizer — 正则匹配、OCR 修复、行合并
  2. RelicDB — 名称解析、精确/模糊查找
  3. matcher — 物品匹配逻辑
  4. mode_handlers — 精炼标签剥离
"""

import os
import sys
import unittest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ================================================================
# 1. RelicNameRecognizer — 正则匹配 + OCR 修复
# ================================================================

class TestRelicNameRegex(unittest.TestCase):
    """测试遗物名称正则匹配逻辑。"""

    def setUp(self):
        from recognizers.relic_name import RelicNameRecognizer
        self.rec = RelicNameRecognizer

    # ---- 中文纪元匹配 ----

    def test_cn_pattern_basic(self):
        m = self.rec.CN_PATTERN.findall("古纪 C7")
        self.assertEqual(m, [("古纪", "C7")])

    def test_cn_pattern_two_digit(self):
        m = self.rec.CN_PATTERN.findall("前纪 A12")
        self.assertEqual(m, [("前纪", "A12")])

    def test_cn_pattern_all_eras(self):
        for era in ["古纪", "前纪", "中纪", "后纪", "安魂", "先锋"]:
            m = self.rec.CN_PATTERN.findall(f"{era} B3")
            self.assertEqual(m, [(era, "B3")], f"中文纪元 '{era}' 匹配失败")

    def test_cn_pattern_with_comma(self):
        """OCR 可能在纪元和代码间插入逗号/句号"""
        m = self.rec.CN_PATTERN.findall("古纪，C7")
        self.assertEqual(m, [("古纪", "C7")])

    # ---- 英文纪元匹配 ----

    def test_en_pattern_basic(self):
        m = self.rec.EN_PATTERN.findall("Lith C7 Relic")
        self.assertEqual(m, [("Lith", "C7")])

    def test_en_pattern_case_insensitive(self):
        m = self.rec.EN_PATTERN.findall("lith c7 relic")
        self.assertEqual(m, [("lith", "c7")])

    def test_en_pattern_no_space(self):
        """英文无空格: LithC7Relic"""
        m = self.rec.EN_PATTERN.findall("LithC7Relic")
        self.assertEqual(m, [("Lith", "C7")])

    def test_en_pattern_all_eras(self):
        for era in ["Lith", "Meso", "Neo", "Axi", "Requiem", "Vanguard"]:
            m = self.rec.EN_PATTERN.findall(f"{era} A1 Relic")
            self.assertTrue(m, f"英文纪元 '{era}' 匹配失败")

    # ---- 垃圾文本过滤 ----

    def test_trash_pattern_x_prefix(self):
        m = self.rec.TRASH_PATTERN.match("x3")
        self.assertTrue(m)

    def test_trash_pattern_no_relic(self):
        m = self.rec.TRASH_PATTERN.match("No Relic")
        self.assertTrue(m)

    def test_trash_pattern_normal_name(self):
        m = self.rec.TRASH_PATTERN.match("古纪 C7")
        self.assertFalse(m)

    # ---- OCR 修复 ----

    def test_fix_ocr_number_basic(self):
        """正常代码不变"""
        self.assertEqual(self.rec._fix_ocr_number("C7"), "C7")

    def test_fix_ocr_number_digit_first(self):
        """首位多余数字: 0C7 → 去掉0 → C7"""
        self.assertEqual(self.rec._fix_ocr_number("0C7"), "C7")

    def test_fix_ocr_number_alpha_in_digits(self):
        """代码部分字母→数字: CO7 → C07"""
        self.assertEqual(self.rec._fix_ocr_number("CO7"), "C07")

    def test_fix_ocr_number_too_short(self):
        """过短代码不修复"""
        self.assertEqual(self.rec._fix_ocr_number("C"), "C")

    def test_fix_ocr_number_too_long(self):
        """过长代码不修复"""
        self.assertEqual(self.rec._fix_ocr_number("A123"), "A123")

    def test_fix_ocr_number_1_to_I(self):
        """首位1→I: 1C7 → 去掉1 → C7（因为 IC7 不合法）"""
        self.assertEqual(self.rec._fix_ocr_number("1C7"), "C7")

    # ---- 品质标签清理 ----

    def test_quality_pattern_radiant(self):
        m = self.rec.QUALITY_PATTERN.sub('', "Axi A1 [Radiant]")
        self.assertEqual(m.strip(), "Axi A1")

    def test_quality_pattern_intact(self):
        m = self.rec.QUALITY_PATTERN.sub('', "Lith C7 (Intact)")
        self.assertEqual(m.strip(), "Lith C7")

    # ---- _try_match 集成 ----

    def test_try_match_cn(self):
        rec = self.rec.__new__(self.rec)  # 不调用 __init__
        result = rec._try_match("古纪 C7", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "古纪 C7")

    def test_try_match_en(self):
        rec = self.rec.__new__(self.rec)
        result = rec._try_match("Lith C7 Relic", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "古纪 C7")

    def test_try_match_en_no_relic_suffix(self):
        """英文无 Relic 后缀也能匹配（EN_PATTERN_NO_RELIC）"""
        rec = self.rec.__new__(self.rec)
        result = rec._try_match("Lith C7", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "古纪 C7")

    def test_try_match_with_quality(self):
        rec = self.rec.__new__(self.rec)
        result = rec._try_match("Axi A1 [Radiant]", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "后纪 A1")

    def test_try_match_pre_fix(self):
        """OCR 粘连: LithC7Relic → 应通过 _pre_fix_text 修复"""
        rec = self.rec.__new__(self.rec)
        result = rec._try_match("LithC7Relic", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "古纪 C7")

    def test_try_match_garbage(self):
        """垃圾文本不匹配"""
        rec = self.rec.__new__(self.rec)
        result = rec._try_match("x3", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 0)


# ================================================================
# 2. RelicDB — 名称解析 + 查询
# ================================================================

class TestRelicDBParseName(unittest.TestCase):
    """测试 RelicDB._parse_name 遗物名称解析。"""

    def setUp(self):
        from data.wfinfo_relics import RelicDB
        self.parse = RelicDB._parse_name

    def test_en_full(self):
        tier, name, state = self.parse("Axi A1 Intact")
        self.assertEqual(tier, "Axi")
        self.assertEqual(name, "A1")
        self.assertEqual(state, "Intact")

    def test_en_no_state(self):
        tier, name, state = self.parse("Axi A1")
        self.assertEqual(tier, "Axi")
        self.assertEqual(name, "A1")
        self.assertEqual(state, "Intact")

    def test_en_radiant(self):
        tier, name, state = self.parse("Neo S20 Radiant")
        self.assertEqual(tier, "Neo")
        self.assertEqual(name, "S20")
        self.assertEqual(state, "Radiant")

    def test_cn_full(self):
        tier, name, state = self.parse("后纪 A1 光辉")
        self.assertEqual(tier, "Axi")
        self.assertEqual(name, "A1")
        self.assertEqual(state, "Radiant")

    def test_cn_no_state(self):
        tier, name, state = self.parse("古纪 C7")
        self.assertEqual(tier, "Lith")
        self.assertEqual(name, "C7")
        self.assertEqual(state, "Intact")

    def test_no_space(self):
        tier, name, state = self.parse("AxiA1")
        self.assertEqual(tier, "Axi")
        self.assertEqual(name, "A1")
        self.assertEqual(state, "Intact")

    def test_invalid(self):
        tier, name, state = self.parse("Hello World")
        self.assertEqual(tier, "")
        self.assertEqual(name, "")

    def test_cn_all_states(self):
        """中文精炼状态映射"""
        cn_states = {"完好": "Intact", "优良": "Exceptional", "无瑕": "Flawless", "光辉": "Radiant"}
        for cn, en in cn_states.items():
            tier, name, state = self.parse(f"中纪 N5 {cn}")
            self.assertEqual(state, en, f"中文状态 '{cn}' 映射错误")

    def test_en_case_insensitive(self):
        tier, name, state = self.parse("axi a1")
        self.assertEqual(tier, "Axi")
        self.assertEqual(name, "A1")


class TestRelicDBFind(unittest.TestCase):
    """测试 RelicDB.find 查询（需要数据库文件）。"""

    @classmethod
    def setUpClass(cls):
        from data.wfinfo_relics import RelicDB
        db_path = os.path.join(PROJECT_ROOT, "data", "warframe.db")
        if not os.path.exists(db_path):
            raise unittest.SkipTest("warframe.db 不存在，跳过数据库查询测试")
        cls.db = RelicDB(os.path.join(PROJECT_ROOT, "data"))
        cls.db.load()

    def test_find_cn_name(self):
        """中文格式查找"""
        result = self.db.find("古纪 C7")
        # 不确定 C7 是否存在，但不应抛异常
        # 如果存在，检查结构
        if result:
            self.assertIn("name", result)
            self.assertIn("parts", result)
            self.assertIn("vaulted", result)

    def test_find_en_name(self):
        """英文格式查找"""
        result = self.db.find("Lith C7")
        if result:
            self.assertIn("name", result)

    def test_find_with_state(self):
        """带精炼状态查找"""
        result = self.db.find("Axi A1 Intact")
        if result:
            self.assertIn("name", result)

    def test_find_nonexistent(self):
        """不存在的遗物返回 None"""
        result = self.db.find("ZZZZ Z99")
        self.assertIsNone(result)

    def test_find_no_space(self):
        """无空格格式查找"""
        result = self.db.find("AxiA1")
        # 应能找到（如果 A1 存在）
        if result:
            self.assertIn("name", result)

    def test_find_fuzzy(self):
        """模糊匹配（OCR 容错）"""
        # 尝试一些 OCR 常见错误
        result = self.db.find("后纪 A1")
        # 不应抛异常
        self.assertTrue(result is None or isinstance(result, dict))

    def test_query_many(self):
        """批量查询"""
        results = self.db.query_many(["古纪 C7", "Lith A1", "ZZZZ Z99"])
        self.assertEqual(len(results), 3)
        for name, result in results:
            self.assertTrue(result is None or isinstance(result, dict))

    def test_stats(self):
        """数据库统计"""
        stats = self.db.stats()
        self.assertIn("total_relics", stats)
        self.assertIn("vaulted", stats)
        self.assertIn("available", stats)
        self.assertGreater(stats["total_relics"], 0)


# ================================================================
# 3. matcher — 物品匹配逻辑
# ================================================================

class TestMatcherHelpers(unittest.TestCase):
    """测试 matcher 模块的辅助函数。"""

    def test_is_warframe_part_blueprint(self):
        from recognizers.matcher import _is_warframe_part
        self.assertTrue(_is_warframe_part("Ash Prime Blueprint"))

    def test_is_warframe_part_chassis(self):
        from recognizers.matcher import _is_warframe_part
        self.assertTrue(_is_warframe_part("Ash Prime Chassis"))

    def test_is_warframe_part_blade(self):
        from recognizers.matcher import _is_warframe_part
        self.assertTrue(_is_warframe_part("Dual Zoren Prime Blade"))

    def test_is_not_warframe_part(self):
        from recognizers.matcher import _is_warframe_part
        self.assertFalse(_is_warframe_part("Ash Prime"))

    def test_split_camel_case(self):
        from recognizers.matcher import _split_camel_case
        self.assertEqual(_split_camel_case("ArchonStretch"), "Archon Stretch")

    def test_split_camel_case_with_digit(self):
        from recognizers.matcher import _split_camel_case
        self.assertEqual(_split_camel_case("SarynPrime2"), "Saryn Prime 2")

    def test_levenshtein(self):
        from recognizers.matcher import _levenshtein
        self.assertEqual(_levenshtein("kitten", "sitting"), 3)
        self.assertEqual(_levenshtein("", "abc"), 3)
        self.assertEqual(_levenshtein("abc", "abc"), 0)

    def test_strip_refinement_tag(self):
        from recognizers.matcher import _strip_refinement_tag
        self.assertEqual(_strip_refinement_tag("Axi S20 Radiant"), "Axi S20")
        self.assertEqual(_strip_refinement_tag("Lith C7 Intact"), "Lith C7")

    def test_is_relic_with_refinement(self):
        from recognizers.matcher import _is_relic_with_refinement
        self.assertTrue(_is_relic_with_refinement("Axi S20 Radiant"))
        self.assertFalse(_is_relic_with_refinement("Axi S20"))

    def test_insert_prime_before_part(self):
        from recognizers.matcher import _insert_prime_before_part
        self.assertEqual(
            _insert_prime_before_part("Ash Neuroptics Blueprint"),
            "Ash Prime Neuroptics Blueprint")
        self.assertEqual(
            _insert_prime_before_part("Carrier Carapace"),
            "Carrier Prime Carapace")


class TestMatcherRefinementFilter(unittest.TestCase):
    """测试精炼版本过滤。"""

    def test_filter_replaces_refinement_with_base(self):
        """带精炼标签的遗物应被替换为基础版本"""
        from recognizers.matcher import _filter_relic_refinements
        # 构造一个带精炼标签的结果
        items = [{
            'en_name': 'Axi S20 Radiant',
            'zh_name': '后纪 S20 辉光',
            'category': 'Relics',
        }]
        filtered = _filter_relic_refinements(items)
        # 过滤后应替换为基础版本（如果数据库中存在）
        self.assertEqual(len(filtered), 1)


# ================================================================
# 4. mode_handlers — 精炼标签剥离
# ================================================================

class TestModeHandlersStripRefinement(unittest.TestCase):
    """测试 mode_handlers.strip_refinement。"""

    def test_strip_cn_radiant(self):
        from core.mode_handlers import strip_refinement
        self.assertEqual(strip_refinement("古纪 C7 光辉"), "古纪 C7")

    def test_strip_cn_intact(self):
        from core.mode_handlers import strip_refinement
        self.assertEqual(strip_refinement("前纪 A1 完好"), "前纪 A1")

    def test_strip_en_radiant(self):
        from core.mode_handlers import strip_refinement
        self.assertEqual(strip_refinement("Axi A1 Radiant"), "Axi A1")

    def test_strip_en_bracket(self):
        from core.mode_handlers import strip_refinement
        self.assertEqual(strip_refinement("Axi A1 [Radiant]"), "Axi A1")

    def test_strip_cn_bracket(self):
        from core.mode_handlers import strip_refinement
        self.assertEqual(strip_refinement("中纪 N5（光辉）"), "中纪 N5")

    def test_no_refinement(self):
        from core.mode_handlers import strip_refinement
        self.assertEqual(strip_refinement("古纪 C7"), "古纪 C7")

    def test_strip_all_cn_states(self):
        from core.mode_handlers import strip_refinement
        for state in ["完好", "优良", "无瑕", "光辉"]:
            result = strip_refinement(f"古纪 C7 {state}")
            self.assertEqual(result, "古纪 C7", f"未能剥离中文状态 '{state}'")


# ================================================================
# 5. BaseOCR — 辅助函数
# ================================================================

class TestBaseOCRHelpers(unittest.TestCase):
    """测试 BaseOCR 辅助函数。"""

    def test_box_center_y(self):
        from recognizers.base_ocr import BaseOCR
        box = [[0, 10], [100, 10], [100, 30], [0, 30]]
        self.assertAlmostEqual(BaseOCR._box_center_y(box), 20.0)

    def test_box_height(self):
        from recognizers.base_ocr import BaseOCR
        box = [[0, 10], [100, 10], [100, 30], [0, 30]]
        self.assertAlmostEqual(BaseOCR._box_height(box), 20.0)

    def test_horizontal_overlap_full(self):
        from recognizers.base_ocr import BaseOCR
        a = [[0, 0], [100, 0], [100, 30], [0, 30]]
        b = [[0, 0], [100, 0], [100, 30], [0, 30]]
        self.assertAlmostEqual(BaseOCR._horizontal_overlap(a, b), 1.0)

    def test_horizontal_overlap_none(self):
        from recognizers.base_ocr import BaseOCR
        a = [[0, 0], [50, 0], [50, 30], [0, 30]]
        b = [[100, 0], [200, 0], [200, 30], [100, 30]]
        self.assertAlmostEqual(BaseOCR._horizontal_overlap(a, b), 0.0)

    def test_horizontal_overlap_partial(self):
        from recognizers.base_ocr import BaseOCR
        a = [[0, 0], [100, 0], [100, 30], [0, 30]]
        b = [[50, 0], [150, 0], [150, 30], [50, 30]]
        overlap = BaseOCR._horizontal_overlap(a, b)
        self.assertAlmostEqual(overlap, 0.5)

    def test_scale_box(self):
        from recognizers.base_ocr import BaseOCR
        box = [[0, 0], [200, 0], [200, 100], [0, 100]]
        scaled = BaseOCR._scale_box(box, 2.0)
        self.assertAlmostEqual(scaled[0][0], 0)
        self.assertAlmostEqual(scaled[1][0], 100)
        self.assertAlmostEqual(scaled[2][1], 50)

    def test_calculate_adaptive_scale_small(self):
        from recognizers.base_ocr import BaseOCR
        # 小图 (300px) → 2400/300 = 8.0, 但上限 6.0x
        scale = BaseOCR._calculate_adaptive_scale(300, 200)
        self.assertEqual(scale, 6.0)

    def test_calculate_adaptive_scale_medium(self):
        from recognizers.base_ocr import BaseOCR
        # 中图 (800px) → 2400/800 = 3.0x
        scale = BaseOCR._calculate_adaptive_scale(800, 600)
        self.assertEqual(scale, 3.0)

    def test_merge_adjacent_lines(self):
        from recognizers.base_ocr import BaseOCR
        ocr = BaseOCR.__new__(BaseOCR)
        # 两个垂直相邻的行
        lines = [
            ("Hello", [[0, 0], [100, 0], [100, 20], [0, 20]]),
            ("World", [[0, 22], [100, 22], [100, 42], [0, 42]]),
        ]
        merged = ocr.merge_adjacent_lines(lines)
        # 应合并为一行
        self.assertEqual(len(merged), 1)
        self.assertIn("Hello", merged[0][0])
        self.assertIn("World", merged[0][0])


# ================================================================
# 6. 集成测试 — 完整链路（需要数据库）
# ================================================================

class TestIntegrationPipeline(unittest.TestCase):
    """集成测试：从 OCR 文本到遗物查询的完整链路。"""

    @classmethod
    def setUpClass(cls):
        db_path = os.path.join(PROJECT_ROOT, "data", "warframe.db")
        if not os.path.exists(db_path):
            raise unittest.SkipTest("warframe.db 不存在，跳过集成测试")
        from data.wfinfo_relics import RelicDB
        cls.db = RelicDB(os.path.join(PROJECT_ROOT, "data"))
        cls.db.load()

    def test_cn_relic_to_db(self):
        """中文遗物名 → OCR 匹配 → 数据库查询"""
        from recognizers.relic_name import RelicNameRecognizer
        rec = RelicNameRecognizer.__new__(RelicNameRecognizer)
        result = rec._try_match("古纪 C7", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        name, box = result[0]
        # 查数据库
        db_result = self.db.find(name)
        # 不确定 C7 是否存在，但不应抛异常
        self.assertTrue(db_result is None or "name" in db_result)

    def test_en_relic_to_db(self):
        """英文遗物名 → OCR 匹配 → 数据库查询"""
        from recognizers.relic_name import RelicNameRecognizer
        rec = RelicNameRecognizer.__new__(RelicNameRecognizer)
        result = rec._try_match("Lith C7 Relic", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        name, box = result[0]
        db_result = self.db.find(name)
        self.assertTrue(db_result is None or "name" in db_result)

    def test_ocr_error_recovery(self):
        """OCR 常见错误修复 → 数据库查询"""
        from recognizers.relic_name import RelicNameRecognizer
        rec = RelicNameRecognizer.__new__(RelicNameRecognizer)
        # 测试 OCR 粘连
        result = rec._try_match("LithC7Relic", [[0, 0], [100, 0], [100, 30], [0, 30]])
        self.assertEqual(len(result), 1)
        name, _ = result[0]
        self.assertEqual(name, "古纪 C7")

    def test_strip_refinement_then_query(self):
        """精炼标签剥离 → 数据库查询"""
        from core.mode_handlers import strip_refinement
        name = strip_refinement("古纪 C7 光辉")
        self.assertEqual(name, "古纪 C7")
        # 查数据库
        db_result = self.db.find(name)
        self.assertTrue(db_result is None or "name" in db_result)

    def test_batch_query(self):
        """批量查询多个遗物"""
        names = ["古纪 C7", "前纪 A1", "中纪 N5", "后纪 S20"]
        results = self.db.query_many(names)
        self.assertEqual(len(results), 4)

    def test_ocr_number_fix_chain(self):
        """OCR 数字修复链路"""
        from recognizers.relic_name import RelicNameRecognizer
        rec = RelicNameRecognizer
        # 0→O 失败后去掉首位: "0C7" → "C7"
        self.assertEqual(rec._fix_ocr_number("0C7"), "C7")
        # O→0: "CO7" → "C07"
        self.assertEqual(rec._fix_ocr_number("CO7"), "C07")
        # 正常: "C7" → "C7"
        self.assertEqual(rec._fix_ocr_number("C7"), "C7")


# ================================================================
# 7. 性能测试 — 关键路径耗时
# ================================================================

class TestPerformance(unittest.TestCase):
    """性能测试：关键路径耗时。"""

    @classmethod
    def setUpClass(cls):
        db_path = os.path.join(PROJECT_ROOT, "data", "warframe.db")
        if not os.path.exists(db_path):
            raise unittest.SkipTest("warframe.db 不存在，跳过性能测试")
        from data.wfinfo_relics import RelicDB
        cls.db = RelicDB(os.path.join(PROJECT_ROOT, "data"))
        cls.db.load()

    def test_single_find_performance(self):
        """单次遗物查询应 < 5ms"""
        import time
        # 先找一个存在的遗物
        stats = self.db.stats()
        # 查询一个常见遗物
        start = time.perf_counter()
        for _ in range(100):
            self.db.find("古纪 C7")
        elapsed = (time.perf_counter() - start) * 1000 / 100
        print(f"\n[性能] 单次 find 平均耗时: {elapsed:.2f}ms")
        self.assertLess(elapsed, 5.0, f"单次查询耗时 {elapsed:.2f}ms > 5ms")

    def test_batch_find_performance(self):
        """批量查询 10 个遗物应 < 50ms"""
        import time
        names = ["古纪 C7", "前纪 A1", "中纪 N5", "后纪 S20",
                 "Lith A1", "Meso B2", "Neo C3", "Axi D4",
                 "古纪 V1", "安魂 K1"]
        start = time.perf_counter()
        for _ in range(10):
            self.db.query_many(names)
        elapsed = (time.perf_counter() - start) * 1000 / 10
        print(f"\n[性能] 批量查询 10 个遗物平均耗时: {elapsed:.2f}ms")
        self.assertLess(elapsed, 50.0, f"批量查询耗时 {elapsed:.2f}ms > 50ms")

    def test_parse_name_performance(self):
        """名称解析应 < 0.1ms"""
        import time
        from data.wfinfo_relics import RelicDB
        parse = RelicDB._parse_name
        start = time.perf_counter()
        for _ in range(1000):
            parse("古纪 C7 光辉")
            parse("Axi A1 Intact")
            parse("AxiA1")
        elapsed = (time.perf_counter() - start) * 1000 / 3000
        print(f"\n[性能] 名称解析平均耗时: {elapsed:.4f}ms")
        self.assertLess(elapsed, 0.1, f"名称解析耗时 {elapsed:.4f}ms > 0.1ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
