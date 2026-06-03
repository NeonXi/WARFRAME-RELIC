"""
Tests for market_query/utils.py — Slug generation & status mapping
"""
import unittest
import os
import sys

# Ensure market_query is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'market_query'))

from utils import format_slug, _generate_slug, get_status_text, get_status_color


class TestSlugFormatting(unittest.TestCase):
    """Slug 生成函数测试"""

    def test_fallback_generate_simple_name(self):
        """简单名称：小写 + 空格转连字符"""
        result = _generate_slug("Saryn Prime")
        self.assertEqual(result, "saryn-prime")

    def test_fallback_generate_with_underscore(self):
        """含下划线的名称"""
        result = _generate_slug("Nova_Prime_Set")
        self.assertEqual(result, "nova-prime-set")

    def test_fallback_generate_with_hyphen(self):
        """含连字符的名称"""
        result = _generate_slug("Kuva-Ayanga")
        self.assertEqual(result, "kuva-ayanga")

    def test_fallback_generate_extra_spaces(self):
        """多余空白字符"""
        result = _generate_slug("  Wukong   Prime  ")
        self.assertEqual(result, "wukong-prime")

    def test_fallback_generate_blueprint(self):
        """Blueprint 后缀生成变体"""
        result = _generate_slug("Frost Prime Blueprint")
        self.assertEqual(result, "frost-prime-blueprint")

    def test_fallback_generate_empty_string(self):
        """空字符串"""
        result = _generate_slug("")
        self.assertEqual(result, "")  # clean.split() -> [] -> variants[0] is ""

    def test_fallback_generate_single_word(self):
        """单词"""
        result = _generate_slug("Excalibur")
        self.assertEqual(result, "excalibur")

    def test_fallback_generate_prime_variant(self):
        """Prime 物品带多个词"""
        result = _generate_slug("Nyx Prime Systems")
        # clean="nyx prime systems", variants=["nyx-prime-systems", "nyx-prime-systems", "nyx-systems-prime"]
        # The generate includes: clean, then if prime in parts: first variant "[first]-prime-[rest]", then "all-but-prime-prime"
        self.assertEqual(result, "nyx-prime-systems")

    def test_fallback_generate_case_insensitive(self):
        """大小写不敏感"""
        result = _generate_slug("EMBER PRIME NEUROPTICS")
        self.assertEqual(result, "ember-prime-neuroptics")

    def test_format_slug_returns_string(self):
        """format_slug 始终返回字符串"""
        result = format_slug("SomeRandomItemThatDoesNotExist")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "")
        self.assertEqual(result, "somerandomitemthatdoesnotexist")


class TestStatusMapping(unittest.TestCase):
    """状态映射函数测试"""

    def test_get_status_text_known(self):
        """已知状态码"""
        self.assertEqual(get_status_text('ingame'), '游戏中')
        self.assertEqual(get_status_text('online'), '在线')
        self.assertEqual(get_status_text('offline'), '离线')
        self.assertEqual(get_status_text('away'), '离开')

    def test_get_status_text_unknown(self):
        """未知状态码返回原值"""
        self.assertEqual(get_status_text('playing'), 'playing')
        self.assertEqual(get_status_text(''), '')
        self.assertEqual(get_status_text(123), 123)

    def test_get_status_color_known(self):
        """已知状态颜色"""
        self.assertNotEqual(get_status_color('ingame'), '#ffffff')
        self.assertNotEqual(get_status_color('online'), '#ffffff')
        self.assertNotEqual(get_status_color('offline'), '#ffffff')
        self.assertNotEqual(get_status_color('away'), '#ffffff')

    def test_get_status_color_unknown(self):
        """未知状态返回白色"""
        self.assertEqual(get_status_color('unknown'), '#ffffff')


if __name__ == '__main__':
    unittest.main()