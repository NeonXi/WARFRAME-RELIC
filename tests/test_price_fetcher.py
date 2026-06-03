"""
Tests for market_query/price_fetcher.py — API error handling & order parsing

Note: Uses unittest.mock to simulate HTTP responses without real network calls.
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import urllib.error
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'market_query'))

from price_fetcher import PriceFetcher


class TestParseOrder(unittest.TestCase):
    """_parse_order 方法测试"""

    def setUp(self):
        self.fetcher = PriceFetcher("test-slug", "Test Item")

    def test_basic_order_parsing(self):
        """基本订单解析"""
        order = {
            'user': {
                'ingame_name': 'TestPlayer',
                'status': 'ingame',
                'reputation': 10,
            },
            'platinum': 45,
            'quantity': 2,
            'mod_rank': 5,
        }
        result = self.fetcher._parse_order(order)
        self.assertEqual(result['username'], 'TestPlayer')
        self.assertEqual(result['status'], 'ingame')
        self.assertEqual(result['platinum'], 45)
        self.assertEqual(result['quantity'], 2)
        self.assertEqual(result['item_level'], 5)
        self.assertEqual(result['reputation'], 10)
        self.assertEqual(result['en_name'], 'Test Item')

    def test_parse_order_missing_user(self):
        """缺少 user 字段"""
        order = {'platinum': 100}
        result = self.fetcher._parse_order(order)
        self.assertEqual(result['username'], 'Unknown')
        self.assertEqual(result['status'], 'offline')
        self.assertEqual(result['platinum'], 100)
        self.assertEqual(result['reputation'], 0)

    def test_parse_order_reputation_dict(self):
        """reputation 为嵌套 dict"""
        order = {
            'user': {
                'ingame_name': 'Player',
                'status': 'online',
                'reputation': {'level': 15, 'bonus': 2},
            },
            'platinum': 30,
        }
        result = self.fetcher._parse_order(order)
        self.assertEqual(result['reputation'], 15)

    def test_parse_order_alternative_username_field(self):
        """ingameName 替代字段"""
        order = {
            'user': {
                'ingameName': 'AltPlayer',
                'status': 'offline',
                'reputation': 0,
            },
            'platinum': 10,
        }
        result = self.fetcher._parse_order(order)
        self.assertEqual(result['username'], 'AltPlayer')

    def test_parse_order_item_level_sources(self):
        """item_level 多来源回退"""
        # mod_rank in item dict
        order = {
            'user': {},
            'item': {'mod_rank': 3},
            'platinum': 20,
        }
        result = self.fetcher._parse_order(order)
        self.assertEqual(result['item_level'], 3)

        # mod_rank at top level
        order2 = {
            'user': {},
            'item': {},
            'platinum': 20,
            'mod_rank': 7,
        }
        result2 = self.fetcher._parse_order(order2)
        self.assertEqual(result2['item_level'], 7)

        # rank field
        order3 = {
            'user': {},
            'item': {},
            'platinum': 20,
            'rank': 12,
        }
        result3 = self.fetcher._parse_order(order3)
        self.assertEqual(result3['item_level'], 12)

    def test_safe_int_valid(self):
        """_safe_int 正常值"""
        self.assertEqual(self.fetcher._safe_int(42), 42)
        self.assertEqual(self.fetcher._safe_int("99"), 99)
        self.assertEqual(self.fetcher._safe_int(0), 0)

    def test_safe_int_invalid(self):
        """_safe_int 非法值"""
        self.assertEqual(self.fetcher._safe_int("abc"), 0)
        self.assertEqual(self.fetcher._safe_int(None), 0)
        self.assertEqual(self.fetcher._safe_int("abc", -1), -1)


class TestFetchErrorHandling(unittest.TestCase):
    """run() 方法错误处理测试"""

    def setUp(self):
        self.fetcher = PriceFetcher("test-slug", "Test Item")

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_http_404_error(self, mock_req, mock_urlopen):
        """HTTP 404"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'http://test', 404, 'Not Found', {}, None
        )
        finished_calls = []

        def on_finished(success, message):
            finished_calls.append((success, message))

        self.fetcher.finished.connect(on_finished)
        self.fetcher.run()
        self.assertEqual(len(finished_calls), 1)
        self.assertFalse(finished_calls[0][0])
        self.assertIn('不存在', finished_calls[0][1])

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_http_500_error(self, mock_req, mock_urlopen):
        """HTTP 500"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'http://test', 500, 'Internal Server Error', {}, None
        )
        finished_calls = []

        def on_finished(success, message):
            finished_calls.append((success, message))

        self.fetcher.finished.connect(on_finished)
        self.fetcher.run()
        self.assertEqual(len(finished_calls), 1)
        self.assertFalse(finished_calls[0][0])
        self.assertIn('HTTP 错误 500', finished_calls[0][1])

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_network_timeout(self, mock_req, mock_urlopen):
        """网络超时"""
        mock_urlopen.side_effect = TimeoutError('timed out')
        finished_calls = []

        def on_finished(success, message):
            finished_calls.append((success, message))

        self.fetcher.finished.connect(on_finished)
        self.fetcher.run()
        self.assertEqual(len(finished_calls), 1)
        self.assertFalse(finished_calls[0][0])
        self.assertIn('网络超时', finished_calls[0][1])

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_urlerror(self, mock_req, mock_urlopen):
        """URL 错误（DNS / 连接失败）"""
        mock_urlopen.side_effect = urllib.error.URLError('connection refused')
        finished_calls = []

        def on_finished(success, message):
            finished_calls.append((success, message))

        self.fetcher.finished.connect(on_finished)
        self.fetcher.run()
        self.assertEqual(len(finished_calls), 1)
        self.assertFalse(finished_calls[0][0])
        self.assertIn('网络错误', finished_calls[0][1])

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_invalid_json_response(self, mock_req, mock_urlopen):
        """无效 JSON 响应"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'not json at all'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        finished_calls = []

        def on_finished(success, message):
            finished_calls.append((success, message))

        self.fetcher.finished.connect(on_finished)
        # json.loads on b'not json at all' will raise json.JSONDecodeError
        # but this is caught by the generic Exception handler
        self.fetcher.run()
        self.assertEqual(len(finished_calls), 1)
        self.assertFalse(finished_calls[0][0])
        # Should be either "数据解析错误" or "未知错误"
        self.assertTrue(
            '解析' in finished_calls[0][1] or '未知错误' in finished_calls[0][1],
            f"Expected error message about JSON, got: {finished_calls[0][1]}"
        )

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_empty_orders(self, mock_req, mock_urlopen):
        """空订单列表"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            'data': []
        }).encode('utf-8')
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        finished_calls = []

        def on_finished(success, message):
            finished_calls.append((success, message))

        self.fetcher.finished.connect(on_finished)
        self.fetcher.run()
        self.assertEqual(len(finished_calls), 1)
        self.assertTrue(finished_calls[0][0])
        self.assertIn('未找到', finished_calls[0][1])


if __name__ == '__main__':
    unittest.main()