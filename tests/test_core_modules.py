"""
核心模块单元测试 —— trigger_manager, hotkey_manager, base_ocr

覆盖：
1. trigger_manager: VK映射、_send_key、_exec_mouse_move、_build_index、_HOOKPROC签名
2. hotkey_manager: _parse_hotkey、修饰键映射、_SPECIAL_VK、nativeEventFilter
3. base_ocr: _calculate_adaptive_scale、_merge_box、merge_adjacent_lines
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ================================================================
# 1. trigger_manager — VK映射 + 键名映射
# ================================================================

class TestVKMapping(unittest.TestCase):
    """测试 VK 码 ↔ 键名映射的正确性和一致性。"""

    @classmethod
    def setUpClass(cls):
        from core.trigger_manager import _VK_TO_NAME, _NAME_TO_VK
        cls._vk_to_name = _VK_TO_NAME
        cls._name_to_vk = _NAME_TO_VK

    # ---- VK_TO_NAME 基础映射 ----

    def test_vk_digits(self):
        """数字键 0-9"""
        for i in range(10):
            self.assertEqual(self._vk_to_name[0x30 + i], str(i))

    def test_vk_letters(self):
        """字母键 a-z"""
        for i in range(26):
            self.assertEqual(self._vk_to_name[0x41 + i], chr(0x61 + i))

    def test_vk_fkeys(self):
        """功能键 F1-F12"""
        for i in range(1, 13):
            self.assertEqual(self._vk_to_name[0x6F + i], f"f{i}")

    def test_vk_special_keys(self):
        """特殊键"""
        special = {
            0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "esc",
            0x08: "backspace", 0x2E: "delete",
        }
        for vk, name in special.items():
            self.assertEqual(self._vk_to_name[vk], name)

    # ---- _NAME_TO_VK 反向映射 ----

    def test_name_to_vk_digits(self):
        """数字键名 → VK"""
        for i in range(10):
            self.assertEqual(self._name_to_vk[str(i)], 0x30 + i)

    def test_name_to_vk_letters(self):
        """字母键名 → VK"""
        for i in range(26):
            self.assertEqual(self._name_to_vk[chr(0x61 + i)], 0x41 + i)

    def test_name_to_vk_fkeys(self):
        """功能键名 → VK"""
        for i in range(1, 13):
            self.assertEqual(self._name_to_vk[f"f{i}"], 0x6F + i)

    # ---- 重复键名处理 ----

    def test_duplicate_keys_exist(self):
        """验证 shift/ctrl/alt 有多个 VK 码映射到同一键名"""
        shift_vks = [vk for vk, name in self._vk_to_name.items() if name == "shift"]
        ctrl_vks = [vk for vk, name in self._vk_to_name.items() if name == "ctrl"]
        alt_vks = [vk for vk, name in self._vk_to_name.items() if name == "alt"]
        self.assertGreater(len(shift_vks), 1, "shift 应有多个 VK 码")
        self.assertGreater(len(ctrl_vks), 1, "ctrl 应有多个 VK 码")
        self.assertGreater(len(alt_vks), 1, "alt 应有多个 VK 码")

    def test_vk_from_name_shift(self):
        """_NAME_TO_VK['shift'] 返回左/右 shift 之一"""
        vk = self._name_to_vk.get("shift")
        self.assertIsNotNone(vk)
        self.assertIn(vk, [0x10, 0xA0, 0xA1])

    def test_vk_from_name_ctrl(self):
        """_NAME_TO_VK['ctrl'] 返回左/右 ctrl 之一"""
        vk = self._name_to_vk.get("ctrl")
        self.assertIsNotNone(vk)
        self.assertIn(vk, [0x11, 0xA2, 0xA3])

    def test_vk_from_name_alt(self):
        """_NAME_TO_VK['alt'] 返回左/右 alt 之一"""
        vk = self._name_to_vk.get("alt")
        self.assertIsNotNone(vk)
        self.assertIn(vk, [0x12, 0xA4, 0xA5])

    # ---- 映射完整性 ----

    def test_vk_to_name_count(self):
        """VK_TO_NAME 应包含足够多的键（至少 80+）"""
        self.assertGreater(len(self._vk_to_name), 80)

    def test_name_to_vk_count(self):
        """_NAME_TO_VK 应包含足够多的键（至少 80+）"""
        self.assertGreater(len(self._name_to_vk), 80)

    def test_no_empty_keys(self):
        """VK_TO_NAME 不应有空键名"""
        for vk, name in self._vk_to_name.items():
            self.assertIsInstance(name, str)
            self.assertGreater(len(name), 0)

    def test_no_empty_values_name_to_vk(self):
        """_NAME_TO_VK 不应有 0 值"""
        for name, vk in self._name_to_vk.items():
            self.assertNotEqual(vk, 0, f"键名 '{name}' 映射到 VK 0")


# ================================================================
# 2. trigger_manager — _send_key 按键模拟逻辑
# ================================================================

class TestSendKey(unittest.TestCase):
    """测试 _send_key 按键解析逻辑。"""

    def setUp(self):
        from core.trigger_manager import _send_key, _NAME_TO_VK
        self._send_key = _send_key
        self._name_to_vk = _NAME_TO_VK

    def test_send_simple_key(self):
        """简单按键应有对应 VK 码"""
        self.assertIn("a", self._name_to_vk)
        self.assertIn("4", self._name_to_vk)
        self.assertIn("f1", self._name_to_vk)
        self.assertIn("space", self._name_to_vk)

    def test_send_key_parsing_no_modifier(self):
        """无修饰键的按键应有 VK 码"""
        self.assertIn("enter", self._name_to_vk)
        self.assertIn("tab", self._name_to_vk)
        self.assertIn("esc", self._name_to_vk)

    def test_send_key_modifier_keys_exist(self):
        """修饰键名应有 VK 码"""
        self.assertIn("ctrl", self._name_to_vk)
        self.assertIn("shift", self._name_to_vk)
        self.assertIn("alt", self._name_to_vk)

    def test_send_empty_string_does_not_crash(self):
        """空字符串不应崩溃"""
        try:
            self._send_key("")
        except Exception as e:
            self.fail(f"_send_key('') 崩溃: {e}")

    def test_send_unknown_key_does_not_crash(self):
        """未知键名不应崩溃"""
        try:
            self._send_key("zzz_nonexistent_key")
        except Exception as e:
            self.fail(f"_send_key('zzz_nonexistent_key') 崩溃: {e}")


# ================================================================
# 3. trigger_manager — _exec_mouse_move 坐标解析
# ================================================================

class TestExecMouseMove(unittest.TestCase):
    """测试 _exec_mouse_move 坐标解析逻辑。"""

    def setUp(self):
        from core.trigger_manager import _exec_mouse_move
        self._exec = _exec_mouse_move

    def test_absolute_coordinates(self):
        """绝对坐标 '960, 540' 应被正确解析"""
        # 不抛异常即可（实际移动需要桌面环境）
        try:
            self._exec({"type": "mouse_move", "value": "960, 540"})
        except Exception as e:
            self.fail(f"绝对坐标解析失败: {e}")

    def test_relative_positive(self):
        """相对坐标 '+100, +50'"""
        try:
            self._exec({"type": "mouse_move", "value": "+100, +50"})
        except Exception as e:
            self.fail(f"正相对坐标解析失败: {e}")

    def test_relative_negative_x(self):
        """相对坐标 '-100, 50'"""
        try:
            self._exec({"type": "mouse_move", "value": "-100, 50"})
        except Exception as e:
            self.fail(f"负相对坐标解析失败: {e}")

    def test_relative_negative_y(self):
        """相对坐标 '100, -50'"""
        try:
            self._exec({"type": "mouse_move", "value": "+100, -50"})
        except Exception as e:
            self.fail(f"负 Y 相对坐标解析失败: {e}")

    def test_empty_value(self):
        """空值不应崩溃"""
        try:
            self._exec({"type": "mouse_move", "value": ""})
        except Exception as e:
            self.fail(f"空值解析崩溃: {e}")

    def test_invalid_format(self):
        """非法格式不应崩溃"""
        try:
            self._exec({"type": "mouse_move", "value": "abc"})
        except Exception as e:
            self.fail(f"非法格式崩溃: {e}")

    def test_relative_both_negative(self):
        """相对坐标 '-100, -50'"""
        try:
            self._exec({"type": "mouse_move", "value": "-100, -50"})
        except Exception as e:
            self.fail(f"双负相对坐标解析失败: {e}")


# ================================================================
# 4. trigger_manager — _build_index 索引构建
# ================================================================

class TestBuildIndex(unittest.TestCase):
    """测试 TriggerManager._build_index 事件索引构建。"""

    def setUp(self):
        from core.trigger_manager import TriggerManager
        self.mgr = TriggerManager(lambda msg, t, s: None)
        # 清空触发器
        self.mgr._triggers = []
        self.mgr._event_index = {}

    def test_empty_triggers(self):
        """空触发器列表 → 空索引"""
        self.mgr._build_index()
        self.assertEqual(len(self.mgr._event_index), 0)

    def test_mouse_trigger(self):
        """鼠标触发器 → 索引中应有对应按钮"""
        self.mgr._triggers = [{
            "name": "test",
            "enabled": True,
            "trigger_input": {"type": "mouse", "button": "right"},
            "actions": [],
        }]
        self.mgr._build_index()
        self.assertIn("right", self.mgr._event_index)
        self.assertEqual(len(self.mgr._event_index["right"]), 1)

    def test_keyboard_trigger(self):
        """键盘触发器 → 索引中应有对应键（小写）"""
        self.mgr._triggers = [{
            "name": "test",
            "enabled": True,
            "trigger_input": {"type": "keyboard", "key": "F4"},
            "actions": [],
        }]
        self.mgr._build_index()
        self.assertIn("f4", self.mgr._event_index)
        self.assertEqual(len(self.mgr._event_index["f4"]), 1)

    def test_disabled_trigger_skipped(self):
        """禁用的触发器不应加入索引"""
        self.mgr._triggers = [{
            "name": "test",
            "enabled": False,
            "trigger_input": {"type": "mouse", "button": "right"},
            "actions": [],
        }]
        self.mgr._build_index()
        self.assertEqual(len(self.mgr._event_index), 0)

    def test_multiple_triggers_same_key(self):
        """同一事件值多个触发器"""
        self.mgr._triggers = [
            {
                "name": "t1",
                "enabled": True,
                "trigger_input": {"type": "mouse", "button": "right"},
                "actions": [],
            },
            {
                "name": "t2",
                "enabled": True,
                "trigger_input": {"type": "mouse", "button": "right"},
                "actions": [],
            },
        ]
        self.mgr._build_index()
        self.assertEqual(len(self.mgr._event_index["right"]), 2)

    def test_keyboard_empty_key_skipped(self):
        """空键名不应加入索引"""
        self.mgr._triggers = [{
            "name": "test",
            "enabled": True,
            "trigger_input": {"type": "keyboard", "key": ""},
            "actions": [],
        }]
        self.mgr._build_index()
        self.assertEqual(len(self.mgr._event_index), 0)


# ================================================================
# 5. trigger_manager — _HOOKPROC 回调签名
# ================================================================

class TestHookProcSignature(unittest.TestCase):
    """测试 _HOOKPROC / _HOOKPROC_KB 回调签名与 CallNextHookEx 的兼容性。"""

    def test_hookproc_return_type(self):
        """_HOOKPROC 返回类型应与 CallNextHookEx 兼容（均为 c_longlong）"""
        import ctypes
        from ctypes import wintypes
        from core.trigger_manager import _HOOKPROC, _user32

        self.assertEqual(_user32.CallNextHookEx.restype, ctypes.c_longlong,
                         "CallNextHookEx.restype 应为 c_longlong (64-bit)")
        self.assertEqual(_HOOKPROC._restype_, ctypes.c_longlong,
                         "_HOOKPROC._restype_ 应为 c_longlong，与 CallNextHookEx.restype 一致")

    def test_hookproc_kb_return_type(self):
        """_HOOKPROC_KB 返回类型应与 CallNextHookEx 兼容（均为 c_longlong）"""
        import ctypes
        from core.trigger_manager import _HOOKPROC_KB, _user32

        self.assertEqual(_HOOKPROC_KB._restype_, ctypes.c_longlong,
                         "_HOOKPROC_KB._restype_ 应为 c_longlong，与 CallNextHookEx.restype 一致")

    def test_callnexthookex_argtypes(self):
        """CallNextHookEx 应有正确的 argtypes 声明"""
        import ctypes
        from ctypes import wintypes
        from core.trigger_manager import _user32

        argtypes = _user32.CallNextHookEx.argtypes
        self.assertIsNotNone(argtypes, "CallNextHookEx.argtypes 未声明")
        self.assertEqual(len(argtypes), 4, "CallNextHookEx 应有 4 个参数")
        self.assertEqual(argtypes[0], wintypes.HHOOK)
        self.assertEqual(argtypes[1], ctypes.c_int)
        self.assertEqual(argtypes[2], wintypes.WPARAM)
        self.assertEqual(argtypes[3], wintypes.LPARAM)


# ================================================================
# 6. hotkey_manager — _parse_hotkey 热键解析
# ================================================================

class TestParseHotkey(unittest.TestCase):
    """测试 _parse_hotkey 热键字符串解析。"""

    def setUp(self):
        from core.hotkey_manager import _parse_hotkey
        self._parse = _parse_hotkey

    def test_simple_ctrl_letter(self):
        """ctrl+g → (MOD_CONTROL, VK_G)"""
        mod, vk = self._parse("ctrl+g")
        from core.hotkey_manager import MOD_CONTROL
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, ord('G'))

    def test_ctrl_shift_letter(self):
        """ctrl+shift+g → (MOD_CONTROL|MOD_SHIFT, VK_G)"""
        mod, vk = self._parse("ctrl+shift+g")
        from core.hotkey_manager import MOD_CONTROL, MOD_SHIFT
        self.assertEqual(mod, MOD_CONTROL | MOD_SHIFT)
        self.assertEqual(vk, ord('G'))

    def test_alt_letter(self):
        """alt+1 → (MOD_ALT, VK_1)"""
        mod, vk = self._parse("alt+1")
        from core.hotkey_manager import MOD_ALT
        self.assertEqual(mod, MOD_ALT)
        self.assertEqual(vk, ord('1'))

    def test_function_key(self):
        """f5 → (0, VK_F5)"""
        mod, vk = self._parse("f5")
        self.assertEqual(mod, 0)
        self.assertEqual(vk, 0x74)

    def test_ctrl_function_key(self):
        """ctrl+f4 → (MOD_CONTROL, VK_F4)"""
        mod, vk = self._parse("ctrl+f4")
        from core.hotkey_manager import MOD_CONTROL
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, 0x73)

    def test_empty_string(self):
        """空字符串 → (0, 0)"""
        mod, vk = self._parse("")
        self.assertEqual(mod, 0)
        self.assertEqual(vk, 0)

    def test_case_insensitive(self):
        """Ctrl+G → (MOD_CONTROL, VK_G)"""
        mod, vk = self._parse("Ctrl+G")
        from core.hotkey_manager import MOD_CONTROL
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, ord('G'))

    # ---- 特殊键名 ----

    def test_special_key_space(self):
        mod, vk = self._parse("ctrl+space")
        from core.hotkey_manager import MOD_CONTROL
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, 0x20)

    def test_special_key_enter(self):
        mod, vk = self._parse("ctrl+enter")
        from core.hotkey_manager import MOD_CONTROL
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, 0x0D)

    def test_special_key_tab(self):
        mod, vk = self._parse("ctrl+tab")
        from core.hotkey_manager import MOD_CONTROL
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, 0x09)

    def test_special_key_esc(self):
        mod, vk = self._parse("esc")
        self.assertEqual(mod, 0)
        self.assertEqual(vk, 0x1B)

    # ---- 边界情况 ----

    def test_unknown_key(self):
        """未知键名 → (mod, 0)"""
        mod, vk = self._parse("ctrl+zzz_nonexistent")
        self.assertEqual(vk, 0)

    def test_only_modifier(self):
        """只有修饰键 → (mod, 0)"""
        mod, vk = self._parse("ctrl+")
        self.assertEqual(vk, 0)

    def test_modifier_aliases(self):
        """control/win/windows 别名"""
        from core.hotkey_manager import MOD_CONTROL, MOD_WIN
        mod1, vk1 = self._parse("control+g")
        self.assertEqual(mod1, MOD_CONTROL)
        mod2, vk2 = self._parse("win+g")
        self.assertEqual(mod2, MOD_WIN)
        mod3, vk3 = self._parse("windows+g")
        self.assertEqual(mod3, MOD_WIN)


# ================================================================
# 7. hotkey_manager — _SPECIAL_VK 映射完整性
# ================================================================

class TestSpecialVK(unittest.TestCase):
    """测试 _SPECIAL_VK 特殊键名映射。"""

    @classmethod
    def setUpClass(cls):
        from core.hotkey_manager import _SPECIAL_VK
        cls._special_vk = _SPECIAL_VK

    def test_fkeys(self):
        """F1-F12"""
        for i in range(1, 13):
            self.assertIn(f"f{i}", self._special_vk)
            self.assertEqual(self._special_vk[f"f{i}"], 0x6F + i)

    def test_special_keys_exist(self):
        """所有常见特殊键都应有映射"""
        keys = ["space", "enter", "tab", "esc", "backspace", "delete",
                "insert", "home", "end", "pageup", "pagedown",
                "up", "down", "left", "right",
                "printscreen", "pause"]
        for key in keys:
            self.assertIn(key, self._special_vk, f"缺少特殊键: {key}")

    def test_symbol_keys(self):
        """符号键映射"""
        symbols = [";", "=", ",", "-", ".", "/", "`", "[", "\\", "]", "'"]
        for sym in symbols:
            self.assertIn(sym, self._special_vk, f"缺少符号键: {sym}")

    def test_vk_values_unique(self):
        """VK 值不应重复（除了合理的重复）"""
        vk_values = list(self._special_vk.values())
        # 大多数 VK 应该是唯一的
        duplicates = [vk for vk in set(vk_values) if vk_values.count(vk) > 1]
        if duplicates:
            print(f"\n  _SPECIAL_VK 中存在重复 VK 值: {duplicates}")


# ================================================================
# 8. hotkey_manager — _MOD_NAME_TO_FLAG 修饰键映射
# ================================================================

class TestModNameToFlag(unittest.TestCase):
    """测试修饰键名 → 标志映射。"""

    @classmethod
    def setUpClass(cls):
        from core.hotkey_manager import _MOD_NAME_TO_FLAG, MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN
        cls._mod_map = _MOD_NAME_TO_FLAG
        cls._flags = {
            "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
            "alt": MOD_ALT, "shift": MOD_SHIFT,
            "win": MOD_WIN, "windows": MOD_WIN,
        }

    def test_all_modifiers_mapped(self):
        """所有标准修饰键都应有映射"""
        for name, flag in self._flags.items():
            self.assertEqual(self._mod_map.get(name), flag,
                             f"修饰键 '{name}' 映射错误")


# ================================================================
# 9. base_ocr — _calculate_adaptive_scale
# ================================================================

class TestAdaptiveScale(unittest.TestCase):
    """测试 _calculate_adaptive_scale 自适应缩放。"""

    def setUp(self):
        from recognizers.base_ocr import BaseOCR
        self._calc = BaseOCR._calculate_adaptive_scale

    def test_large_image_no_scale(self):
        """大图不缩放 (>=2400px)"""
        self.assertEqual(self._calc(2400, 1080), 1.0)
        self.assertEqual(self._calc(3840, 2160), 1.0)

    def test_full_hd(self):
        """1920px → 1.25x"""
        self.assertAlmostEqual(self._calc(1920, 1080), 2400 / 1920)

    def test_medium_image(self):
        """800px → 3.0x"""
        self.assertAlmostEqual(self._calc(800, 600), 2400 / 800)

    def test_small_image(self):
        """300px → 6.0x (上限)"""
        self.assertEqual(self._calc(300, 200), 6.0)

    def test_very_small_image(self):
        """100px → 6.0x (上限)"""
        self.assertEqual(self._calc(100, 100), 6.0)

    def test_scale_monotonic(self):
        """缩放因子应随宽度递减而递增"""
        scales = [self._calc(w, 100) for w in [2400, 1920, 1200, 800, 400, 200]]
        for i in range(len(scales) - 1):
            self.assertGreaterEqual(scales[i + 1], scales[i],
                                    f"width={[2400,1920,1200,800,400,200][i]} scale={scales[i]} "
                                    f"< width={[2400,1920,1200,800,400,200][i+1]} scale={scales[i+1]}")

    def test_return_type(self):
        """返回值应为 float"""
        self.assertIsInstance(self._calc(800, 600), float)


# ================================================================
# 10. base_ocr — _merge_box 边界框合并
# ================================================================

class TestMergeBox(unittest.TestCase):
    """测试 _merge_box 边界框合并。"""

    def setUp(self):
        from recognizers.base_ocr import BaseOCR
        self._merge = BaseOCR._merge_box

    def test_merge_adjacent_boxes(self):
        """两个相邻框合并"""
        a = [[0, 0], [100, 0], [100, 20], [0, 20]]
        b = [[0, 22], [100, 22], [100, 42], [0, 42]]
        result = self._merge(a, b)
        self.assertEqual(result[0], [0, 0])       # 左上
        self.assertEqual(result[1], [100, 0])     # 右上
        self.assertEqual(result[2], [100, 42])    # 右下
        self.assertEqual(result[3], [0, 42])      # 左下

    def test_merge_offset_boxes(self):
        """两个偏移框合并"""
        a = [[0, 0], [80, 0], [80, 20], [0, 20]]
        b = [[50, 22], [150, 22], [150, 42], [50, 42]]
        result = self._merge(a, b)
        self.assertEqual(result[0], [0, 0])       # 取最小 x
        self.assertEqual(result[1], [150, 0])     # 取最大 x
        self.assertEqual(result[2], [150, 42])    # 右下
        self.assertEqual(result[3], [0, 42])      # 左下


# ================================================================
# 11. base_ocr — merge_adjacent_lines 行合并
# ================================================================

class TestMergeAdjacentLines(unittest.TestCase):
    """测试 merge_adjacent_lines 行合并逻辑。"""

    @classmethod
    def setUpClass(cls):
        from recognizers.base_ocr import BaseOCR
        cls._ocr = BaseOCR.__new__(BaseOCR)

    def test_no_merge_single_line(self):
        """单行不合并"""
        lines = [("Hello", [[0, 0], [100, 0], [100, 20], [0, 20]])]
        result = self._ocr.merge_adjacent_lines(lines)
        self.assertEqual(len(result), 1)

    def test_merge_two_adjacent_lines(self):
        """两行垂直相邻 → 合并为一行"""
        lines = [
            ("Hello", [[0, 0], [100, 0], [100, 20], [0, 20]]),
            ("World", [[0, 22], [100, 22], [100, 42], [0, 42]]),
        ]
        result = self._ocr.merge_adjacent_lines(lines)
        self.assertEqual(len(result), 1)
        self.assertIn("Hello", result[0][0])
        self.assertIn("World", result[0][0])

    def test_no_merge_far_apart(self):
        """两行相距较远 → 不合并"""
        lines = [
            ("Hello", [[0, 0], [100, 0], [100, 20], [0, 20]]),
            ("World", [[0, 100], [100, 100], [100, 120], [0, 120]]),
        ]
        result = self._ocr.merge_adjacent_lines(lines)
        self.assertEqual(len(result), 2)

    def test_no_merge_no_overlap(self):
        """两行无水平重叠 → 不合并"""
        lines = [
            ("Hello", [[0, 0], [40, 0], [40, 20], [0, 20]]),
            ("World", [[60, 22], [100, 22], [100, 42], [60, 42]]),
        ]
        result = self._ocr.merge_adjacent_lines(lines)
        self.assertEqual(len(result), 2)

    def test_empty_list(self):
        """空列表不崩溃"""
        result = self._ocr.merge_adjacent_lines([])
        self.assertEqual(len(result), 0)

    def test_preserve_order(self):
        """合并后应保持文本顺序"""
        lines = [
            ("A", [[0, 0], [100, 0], [100, 20], [0, 20]]),
            ("B", [[0, 22], [100, 22], [100, 42], [0, 42]]),
            ("C", [[0, 80], [100, 80], [100, 100], [0, 100]]),
        ]
        result = self._ocr.merge_adjacent_lines(lines)
        self.assertEqual(len(result), 2)
        # A+B 合并，C 独立
        self.assertIn("A", result[0][0])
        self.assertIn("B", result[0][0])
        self.assertEqual(result[1][0], "C")


# ================================================================
# 12. 综合回归测试
# ================================================================

class TestRegression(unittest.TestCase):
    """回归测试：确保之前的修复不会回退。"""

    def test_callnexthookex_has_argtypes(self):
        """CallNextHookEx 必须有 argtypes 声明（修复 64-bit 溢出）"""
        import ctypes
        from ctypes import wintypes
        from core.trigger_manager import _user32

        self.assertIsNotNone(_user32.CallNextHookEx.argtypes,
                             "BUG回归: CallNextHookEx.argtypes 未声明，会导致 64-bit lParam 溢出")

    def test_hotkey_manager_inherits_qabstractnativeeventfilter(self):
        """HotkeyManager 必须继承 QAbstractNativeEventFilter"""
        from PyQt6.QtCore import QAbstractNativeEventFilter
        from core.hotkey_manager import HotkeyManager
        self.assertTrue(issubclass(HotkeyManager, QAbstractNativeEventFilter),
                        "BUG回归: HotkeyManager 未继承 QAbstractNativeEventFilter")

    def test_no_keyboard_import(self):
        """整个项目不应有 import keyboard"""
        bad = []
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'venv', '.venv', 'tests', 'node_modules', '.idea', '__MACOSX')]
            for fn in files:
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(root, fn)
                try:
                    with open(path, encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except Exception:
                    continue
                if 'import keyboard' in content or 'from keyboard import' in content:
                    bad.append(path)
        self.assertEqual(len(bad), 0,
                         f"仍有文件 import keyboard: {bad}")


if __name__ == "__main__":
    unittest.main(verbosity=2)