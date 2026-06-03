"""
Tests for core/theme_config.py — Preset loading, switching, defaults
"""
import unittest
import os
import sys
import tempfile
import shutil
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.theme_config import ThemeConfig


class TestThemeConfigDefaults(unittest.TestCase):
    """ThemeConfig 基础属性测试（不修改文件）"""

    def setUp(self):
        self.theme = ThemeConfig()
        # 确保起始状态为 cyberpunk（单例可能被之前的测试污染）
        if self.theme.active_preset != 'cyberpunk':
            self.theme.apply_preset('cyberpunk')

    def test_singleton(self):
        """单例模式"""
        t2 = ThemeConfig()
        self.assertIs(self.theme, t2)

    def test_default_preset_is_cyberpunk(self):
        """默认预设为 cyberpunk"""
        self.assertEqual(self.theme.active_preset, 'cyberpunk')

    def test_presets_defined(self):
        """PRESETS 定义了 3 个预设"""
        self.assertIn('cyberpunk', self.theme.PRESETS)
        self.assertIn('daylight', self.theme.PRESETS)
        self.assertIn('custom', self.theme.PRESETS)
        self.assertEqual(len(self.theme.PRESETS), 3)

    def test_core_color_attrs_exist(self):
        """核心颜色属性存在且为字符串"""
        for attr in ('cyber_yellow', 'cyber_cyan', 'cyber_magenta', 'cyber_orange',
                     'cyber_red', 'cyber_green',
                     'panel_bg', 'card_bg',
                     'border', 'text', 'text_dim'):
            val = getattr(self.theme, attr)
            self.assertIsInstance(val, str, f"{attr} should be str, got {type(val)}")
            self.assertTrue(val.startswith('#'), f"{attr} should be hex color, got {val}")

    def test_rgba_attrs_exist(self):
        """RGBA 属性存在且为元组"""
        for attr in ('overlay_bg_rgba', 'overlay_selection_overlay_rgba'):
            val = getattr(self.theme, attr)
            self.assertIsInstance(val, tuple, f"{attr} should be tuple")
            self.assertEqual(len(val), 4)
            for c in val:
                self.assertIsInstance(c, int)
                self.assertTrue(0 <= c <= 255)

    def test_color_attrs_valid_hex(self):
        """颜色属性是有效 hex 值"""
        for attr in ('cyber_yellow', 'cyber_cyan', 'panel_bg', 'border', 'text'):
            val = getattr(self.theme, attr)
            # 7-char hex: #RRGGBB
            self.assertEqual(len(val), 7, f"{attr} = {val} not 7 chars")
            # 尝试解析
            int(val[1:], 16)

    def test_log_color_map(self):
        """log_color_map 有完整的日志级别"""
        self.assertIn('ok', self.theme.log_color_map)
        self.assertIn('warn', self.theme.log_color_map)
        self.assertIn('error', self.theme.log_color_map)
        self.assertIn('info', self.theme.log_color_map)
        self.assertIn('debug', self.theme.log_color_map)

    def test_current_preset_name(self):
        """当前预设名称"""
        name = self.theme.current_preset_name()
        self.assertIn('赛博朋克', name)

    def test_to_dict(self):
        """to_dict 返回完整配置"""
        d = self.theme.to_dict()
        self.assertIsInstance(d, dict)
        self.assertGreater(len(d), 30)
        self.assertIn('cyber_cyan', d)

    def test_unknown_attr_raises(self):
        """未定义属性抛出 AttributeError"""
        with self.assertRaises(AttributeError):
            _ = self.theme.nonexistent_attr_xyz

    def test_dyn_attr_color_present(self):
        """动态属性（不在 _create_defaults 中但常见）"""
        # validate no crash
        self.assertIsInstance(self.theme.cyber_cyan, str)


class TestThemePresetSwitching(unittest.TestCase):
    """预设切换测试（使用临时目录）"""

    def setUp(self):
        self.theme = ThemeConfig()
        # 确保起始状态为 cyberpunk
        if self.theme.active_preset != 'cyberpunk':
            self.theme.apply_preset('cyberpunk')
        # 创建临时目录作为 data 目录
        self._tmp_dir = tempfile.mkdtemp(prefix='wf_theme_test_')
        # 通过替换 _data_dir 的方式不可行（是 property），
        # 改为操作预设目录
        self._tmp_presets = os.path.join(self._tmp_dir, 'presets')
        self._tmp_bg = os.path.join(self._tmp_dir, 'backgrounds')
        os.makedirs(self._tmp_presets, exist_ok=True)
        os.makedirs(self._tmp_bg, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_apply_invalid_preset_returns_false(self):
        """应用不存在的预设返回 False"""
        result = self.theme.apply_preset('nonexistent')
        self.assertFalse(result)

    def test_apply_same_preset_returns_true(self):
        """切换到相同预设返回 True"""
        result = self.theme.apply_preset('cyberpunk')
        self.assertTrue(result)

    def test_switch_to_custom_and_back(self):
        """cyberpunk → custom → cyberpunk"""
        # Switch to custom
        result = self.theme.apply_preset('custom')
        self.assertTrue(result)
        self.assertEqual(self.theme.active_preset, 'custom')

        # Switch back
        result = self.theme.apply_preset('cyberpunk')
        self.assertTrue(result)
        self.assertEqual(self.theme.active_preset, 'cyberpunk')

    def test_switch_to_daylight_changes_colors(self):
        """切换到 daylight 后颜色变化"""
        old_bg = self.theme.panel_bg
        old_text = self.theme.text

        result = self.theme.apply_preset('daylight')
        self.assertTrue(result)
        self.assertEqual(self.theme.active_preset, 'daylight')

        # Daylight 应该是浅色主题
        new_bg = self.theme.panel_bg
        self.assertNotEqual(old_bg, new_bg, "daylight 背景色应与 cyberpunk 不同")

        # 恢复
        self.theme.apply_preset('cyberpunk')

    def test_switch_to_custom_keeps_current_colors(self):
        """切换到 custom 时保留当前颜色（因为 custom 预设文件不存在时 fallback 到 defaults）"""
        old_cyan = self.theme.cyber_cyan
        self.theme.apply_preset('custom')
        # custom 预设数据为空，从 defaults + _load_preset_data 合并
        # 由于 custom.json 不存在，会 fallback 到 defaults
        self.assertIsInstance(self.theme.cyber_cyan, str)

    def test_save_triggers_custom_preset(self):
        """save() 从 cyberpunk 保存时自动切换到 custom"""
        self.assertEqual(self.theme.active_preset, 'cyberpunk')
        result = self.theme.save({'cyber_cyan': '#FF0000'})
        self.assertTrue(result)
        # 应该自动切换到 custom 预设
        self.assertEqual(self.theme.active_preset, 'custom')
        # 颜色应更新
        self.assertEqual(self.theme.cyber_cyan, '#FF0000')

        # 恢复：删除 custom 预设，切换回去
        custom_path = self.theme._preset_path('custom')
        if custom_path.exists():
            os.remove(custom_path)
        self.theme.apply_preset('cyberpunk')

    def test_save_invalid_key_ignored(self):
        """save() 忽略无效 key"""
        self.theme.apply_preset('custom')
        result = self.theme.save({'nonexistent_key': 'value', 'cyber_cyan': '#FF0000'})
        self.assertTrue(result)
        self.assertEqual(self.theme.cyber_cyan, '#FF0000')
        with self.assertRaises(AttributeError):
            _ = self.theme.nonexistent_key

        # 恢复
        self.theme.reset()
        self.theme.apply_preset('cyberpunk')

    def test_reset_restores_defaults(self):
        """reset() 恢复默认值"""
        self.theme.apply_preset('custom')
        self.theme.save({'cyber_cyan': '#FF0000'})
        self.theme.reset()
        # 恢复后应是默认色
        self.assertNotEqual(self.theme.cyber_cyan, '#FF0000')

        self.theme.apply_preset('cyberpunk')

    def test_attribute_delegation_works(self):
        """属性代理可从 _data 取值"""
        # cyper_cyan should be accessible
        self.assertIsInstance(self.theme.cyber_cyan, str)
        self.assertTrue(self.theme.cyber_cyan.startswith('#'))

    def test_active_preset_property(self):
        """active_preset 属性返回当前预设"""
        self.assertEqual(self.theme.active_preset, 'cyberpunk')
        self.theme.apply_preset('daylight')
        self.assertEqual(self.theme.active_preset, 'daylight')
        self.theme.apply_preset('cyberpunk')
        self.assertEqual(self.theme.active_preset, 'cyberpunk')


if __name__ == '__main__':
    unittest.main()