"""
[L-Service] core.trigger_manager — 辅助触发器引擎

职责:
- 注册全局鼠标/键盘钩子,监听用户输入事件
- 匹配事件与已配置的触发器
- 延迟执行响应动作(按键、鼠标点击、鼠标移动)
- 防抖保护 + 线程安全
- 支持运行时热重载(reload)

架构设计:
- TriggerManager 是单例式引擎,由 AppCore 在后台加载完成后创建并启动
- 所有钩子回调在独立线程中执行,动作执行通过 Timer 延迟到主逻辑线程
- 动作类型通过 _ACTION_EXECUTORS 字典分发,新增动作类型只需注册一个 executor 函数

依赖: keyboard 库 (全局钩子) + PySide6.QtCore (Timer 延迟执行)
被谁用: core.services.screenshot_pipeline.py

## AI 硬约束 — 修改本文件前必读
归属层:    [L0/L1] (core/ 根目录,跨层桥接/全局管理器)
允许依赖:  视文件而定(本层可持有 widget 引用作桥接,但不实现绘制)
禁止依赖:  根目录 .py 不允许做业务实现 → 业务放 core/services/
必读规范:  .trae/rules/开发规范.md §6.7

本文件相关红线:
- 禁止根目录 .py 持有 widget 绘制逻辑 → 视觉交给 core/widgets/
- 禁止硬编码资源路径 → 必须 core.constants 取
- 禁止在根目录定义业务类 → 业务放对应层
- 禁止反向调用 UI(从 Service → Widget) → 单向数据流
- 禁止 try/except: pass 吞错 → 必须记录到日志或抛给上层

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.7,别走捷径。
"""

import random
import threading
import sys
import time
from typing import Optional


# ============================================================
#  结构化日志 — 统一前缀 [TRIGGER]，CMD 中可快速过滤
# ============================================================

def _log(msg: str, tag: str = "INFO"):
    """统一日志输出，格式: [TRIGGER][TAG] message"""
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[TRIGGER][{tag}] {ts} | {msg}", file=sys.stderr, flush=True)

# ★ 全部钩子使用 ctypes 直接调用 Windows API，彻底移除 keyboard 库依赖
# keyboard 库在注册/注销钩子时会创建/销毁隐藏窗口，导致启动时出现一闪而过的黑窗
import ctypes
from ctypes import wintypes
import time as _time

# Windows API 函数声明
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

# keybd_event — 必须声明 argtypes，否则 64-bit 下 ULONG_PTR 长度错误
_user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, wintypes.WPARAM]
_user32.keybd_event.restype = None

# MapVirtualKeyW — 从虚拟键码获取扫描码（MAPVK_VK_TO_VSC = 0）
_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT

# CallNextHookEx 需要显式声明 argtypes，否则 64-bit lParam 会溢出
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = ctypes.c_longlong

# mouse_event 常量
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040

_MOUSE_CLICK_EVENTS = {
    "left":   (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
    "right":  (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
    "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
}


def _mouse_click(button: str):
    """通过 Windows API mouse_event 模拟鼠标点击。"""
    events = _MOUSE_CLICK_EVENTS.get(button)
    if events:
        down, up = events
        _user32.mouse_event(down, 0, 0, 0, 0)
        _user32.mouse_event(up, 0, 0, 0, 0)


def _mouse_get_pos() -> tuple[int, int]:
    """通过 Windows API GetCursorPos 获取鼠标位置。"""
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def _mouse_move(x: int, y: int):
    """通过 Windows API SetCursorPos 移动鼠标。"""
    _user32.SetCursorPos(x, y)


# ============================================================
# WH_MOUSE_LL 钩子 — 替代 keyboard.mouse，避免 C 扩展崩溃
# ============================================================

_WH_MOUSE_LL = 14
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_WM_MBUTTONDOWN = 0x0207
_WM_MBUTTONUP = 0x0208
_WM_XBUTTONDOWN = 0x020B
_WM_XBUTTONUP = 0x020C
_WM_QUIT = 0x0012


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("hwnd", wintypes.HWND),
        ("wHitTestCode", wintypes.UINT),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


# 低级鼠标钩子回调类型
_HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_longlong,   # LRESULT (64-bit on x64 Windows)
    ctypes.c_int,        # nCode
    wintypes.WPARAM,     # wParam
    wintypes.LPARAM,     # lParam
)

# 消息 → (按钮名, 事件类型)  支持 press/release 精确匹配
# XButton(侧键) 的消息在 _hook_proc 里单独处理,因为同一 WM_XBUTTONDOWN/UP
# 对应两个按钮,需读 wParam 高位区分 XBUTTON1(1)/XBUTTON2(2)
_WM_BTN_MAP = {
    _WM_LBUTTONDOWN: ("left",   "press"),
    _WM_LBUTTONUP:   ("left",   "release"),
    _WM_RBUTTONDOWN: ("right",  "press"),
    _WM_RBUTTONUP:   ("right",  "release"),
    _WM_MBUTTONDOWN: ("middle", "press"),
    _WM_MBUTTONUP:   ("middle", "release"),
}

# XButton 编号 → 内部按钮名 (与 trigger_config.MOUSE_BUTTONS 的 side1/side2 对齐)
_XBUTTON_TO_NAME = {1: "side1", 2: "side2"}


class _MouseEvent:
    """模拟 keyboard.mouse 的 MouseEvent 接口。"""
    __slots__ = ("event_type", "button")

    def __init__(self, event_type: str, button: str):
        self.event_type = event_type
        self.button = button


class _MouseHookThread:
    """用 WH_MOUSE_LL 实现的低级鼠标钩子，运行在独立守护线程。

    替代 keyboard.mouse.hook()，避免 keyboard.mouse C 扩展导致的
    STATUS_STACK_BUFFER_OVERRUN (0xC0000409) 崩溃。
    """

    def __init__(self, callback):
        self._callback = callback
        self._hook_handle = None
        self._thread = None
        self._running = False
        self._cb_ref = None  # 防止 GC 回收回调

    def start(self):
        """启动 hook 监听线程(鼠标/键盘共用此模式,幂等,已运行则直接返回)。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止 hook 线程:发 WM_QUIT 消息 + join(2s 超时)。"""
        self._running = False
        if self._hook_handle:
            _user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._hook_handle = None

    def _loop(self):
        self._thread_id = _kernel32.GetCurrentThreadId()

        # 保存回调引用防止 GC
        self._cb_ref = _HOOKPROC(self._hook_proc)

        self._hook_handle = _user32.SetWindowsHookExW(
            _WH_MOUSE_LL, self._cb_ref, None, 0
        )
        if not self._hook_handle:
            self._running = False
            return

        # 消息循环
        msg = wintypes.MSG()
        while self._running:
            ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or msg.message == _WM_QUIT:
                break

        # 清理
        if self._hook_handle:
            _user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None
        self._cb_ref = None

    def _hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0:
            # wParam 低 16 位是消息类型;侧键时高 16 位是 XBUTTON 编号
            msg = wParam & 0xFFFF
            if msg in _WM_BTN_MAP:
                button, event_type = _WM_BTN_MAP[msg]
            elif msg in (_WM_XBUTTONDOWN, _WM_XBUTTONUP):
                # 侧键:高 16 位为 XBUTTON 编号(1=后退,2=前进)
                xbtn = (wParam >> 16) & 0xFFFF
                button = _XBUTTON_TO_NAME.get(xbtn)
                if button is None:
                    return _user32.CallNextHookEx(None, nCode, wParam, lParam)
                event_type = "press" if msg == _WM_XBUTTONDOWN else "release"
            else:
                return _user32.CallNextHookEx(None, nCode, wParam, lParam)
            evt = _MouseEvent(event_type, button)
            try:
                self._callback(evt)
            except Exception:
                pass
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)


# ============================================================
# WH_KEYBOARD_LL 钩子 — 替代 keyboard.hook，避免隐藏窗口闪烁
# ============================================================

_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104

# 键盘动作常量 (keybd_event)
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_EXTENDEDKEY = 0x0001

# VK 码 → 键名映射（与 keyboard 库行为一致的小写名称）
_VK_TO_NAME = {}
for _i in range(10):
    _VK_TO_NAME[0x30 + _i] = str(_i)           # 0-9
for _i in range(26):
    _VK_TO_NAME[0x41 + _i] = chr(0x61 + _i)    # a-z
for _i in range(1, 13):
    _VK_TO_NAME[0x6F + _i] = f"f{_i}"          # F1-F12
_VK_TO_NAME.update({
    0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "esc",
    0x08: "backspace", 0x2E: "delete", 0x2D: "insert",
    0x25: "left", 0x27: "right", 0x26: "up", 0x28: "down",
    0x24: "home", 0x23: "end", 0x21: "page up", 0x22: "page down",
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl",  0xA2: "ctrl",  0xA3: "ctrl",
    0x12: "alt",   0xA4: "alt",   0xA5: "alt",
    0x5B: "left windows", 0x5C: "right windows",
    0x2C: "print screen", 0x13: "pause", 0x91: "scroll lock",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
})

# 键名 → VK 码反向映射（用于 keybd_event 模拟按键）
_NAME_TO_VK = {v: k for k, v in _VK_TO_NAME.items()}
# 补充：确保数字键和字母键有反向映射
for _i in range(10):
    _NAME_TO_VK[str(_i)] = 0x30 + _i
for _i in range(26):
    _NAME_TO_VK[chr(0x61 + _i)] = 0x41 + _i
for _i in range(1, 13):
    _NAME_TO_VK[f"f{_i}"] = 0x6F + _i


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


_HOOKPROC_KB = ctypes.CFUNCTYPE(
    ctypes.c_longlong,   # LRESULT (64-bit on x64 Windows)
    ctypes.c_int,        # nCode
    wintypes.WPARAM,     # wParam
    wintypes.LPARAM,     # lParam
)


class _KeyEvent:
    """模拟 keyboard 库的 KeyboardEvent 接口。"""
    __slots__ = ("event_type", "name")

    def __init__(self, event_type: str, name: str):
        self.event_type = event_type
        self.name = name


class _KeyboardHookThread:
    """用 WH_KEYBOARD_LL 实现的低级键盘钩子，运行在独立守护线程。

    替代 keyboard.hook()，避免 keyboard 库创建/销毁隐藏窗口导致的闪窗。
    """

    def __init__(self, callback):
        self._callback = callback
        self._hook_handle = None
        self._thread = None
        self._running = False
        self._cb_ref = None

    def start(self):
        """启动 hook 监听线程(鼠标/键盘共用此模式,幂等,已运行则直接返回)。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止 hook 线程:发 WM_QUIT 消息 + join(2s 超时)。"""
        self._running = False
        if self._hook_handle:
            _user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._hook_handle = None

    def _loop(self):
        self._thread_id = _kernel32.GetCurrentThreadId()

        self._cb_ref = _HOOKPROC_KB(self._hook_proc)

        self._hook_handle = _user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, self._cb_ref, None, 0
        )
        if not self._hook_handle:
            self._running = False
            return

        msg = wintypes.MSG()
        while self._running:
            ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or msg.message == _WM_QUIT:
                break

        if self._hook_handle:
            _user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None
        self._cb_ref = None

    def _hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            name = _VK_TO_NAME.get(kb.vkCode)
            if name:
                evt = _KeyEvent("down", name)
                try:
                    self._callback(evt)
                except Exception:
                    pass
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)


def _send_key(key_str: str):
    """通过 Windows API keybd_event 模拟按键，替代 keyboard.send()。

    支持格式: "4", "f", "ctrl+4", "space", "f1" 等。

    ★ 关键：使用 MapVirtualKeyW 获取扫描码填充 bScan 参数。
    bScan=0 意味着"无物理按键"，DirectInput 游戏（如 Warframe）会直接忽略。
    """
    if not key_str:
        _log("_send_key | SKIP: empty key_str", "KEY")
        return

    # 解析修饰键
    parts = key_str.lower().strip().split("+")
    modifiers = {"ctrl": False, "shift": False, "alt": False}
    key_name = parts[-1].strip()

    for part in parts[:-1]:
        part = part.strip()
        if part in modifiers:
            modifiers[part] = True

    vk = _NAME_TO_VK.get(key_name)
    if vk is None:
        _log(f"_send_key | FAIL: no VK for '{key_name}' | key_str='{key_str}'", "KEY")
        return

    # ★ 获取扫描码（MAPVK_VK_TO_VSC = 0）
    scan = _user32.MapVirtualKeyW(vk, 0)
    _log(f"_send_key | key='{key_str}' | vk=0x{vk:02X} | scan=0x{scan:02X}", "KEY")

    # 按下修饰键
    if modifiers["ctrl"]:
        _user32.keybd_event(0x11, 0, 0, 0)
    if modifiers["shift"]:
        _user32.keybd_event(0x10, 0, 0, 0)
    if modifiers["alt"]:
        _user32.keybd_event(0x12, 0, 0, 0)

    # 按下主键（带扫描码）
    _user32.keybd_event(vk, scan, 0, 0)
    _time.sleep(0.03)
    # 释放主键
    _user32.keybd_event(vk, scan, _KEYEVENTF_KEYUP, 0)

    # 释放修饰键（逆序）
    if modifiers["alt"]:
        _user32.keybd_event(0x12, 0, _KEYEVENTF_KEYUP, 0)
    if modifiers["shift"]:
        _user32.keybd_event(0x10, 0, _KEYEVENTF_KEYUP, 0)
    if modifiers["ctrl"]:
        _user32.keybd_event(0x11, 0, _KEYEVENTF_KEYUP, 0)


from core.trigger_config import (
    load_triggers,
    MOUSE_BUTTON_VALUES,
    ACTION_TYPE_VALUES,
)


# ============================================================
# 鼠标按钮映射：keyboard 库内部名称 → 用户可见名称
# ============================================================

_MOUSE_BUTTON_MAP = {
    # 新格式：press/release 精确匹配
    "left_press":     "left_press",
    "left_release":   "left_release",
    "right_press":    "right_press",
    "right_release":  "right_release",
    "middle_press":   "middle_press",
    "middle_release": "middle_release",
    "side1_press":    "side1_press",
    "side1_release":  "side1_release",
    "side2_press":    "side2_press",
    "side2_release":  "side2_release",
    # 旧格式兼容（已废弃，保留防止崩溃）
    "left":   "left",
    "right":  "right",
    "middle": "middle",
    "side1":  "side1",
    "side2":  "side2",
}

# 反向映射（用于从 hook 事件匹配用户配置）
_HOOK_BUTTON_TO_CONFIG = {}
for _k, _v in _MOUSE_BUTTON_MAP.items():
    _HOOK_BUTTON_TO_CONFIG[_v] = _k
    _HOOK_BUTTON_TO_CONFIG[_k] = _k  # 也支持直接用 left/right


class TriggerManager:
    """辅助触发器引擎。

    用法::

        mgr = TriggerManager(log_func)
        mgr.start()          # 注册钩子
        mgr.reload()         # 配置变更后重新加载
        mgr.stop()           # 注销钩子
    """

    # ── 防抖间隔（同一触发器两次触发的最小间隔，秒，随机化以模拟人类操作）──
    DEBOUNCE_INTERVAL_MIN = 0.15
    DEBOUNCE_INTERVAL_MAX = 0.35

    def __init__(self, log_func):
        """
        Args:
            log_func: 日志回调，签名 log_func(msg: str, log_type: str, source: str)
        """
        self._log = log_func
        self._triggers: list[dict] = []
        self._lock = threading.Lock()
        self._last_trigger_time: dict[str, float] = {}   # {trigger_name: timestamp}
        self._running = False
        self._ui_focus_check = None                          # 回调：返回 True 表示 UI 正被操作，应跳过触发
        self._last_reload_time = 0                           # 上次重载时间戳，用于冷却期
        self._has_mouse_hook = False                         # 钩子状态标志（避免不必要重注册）
        self._has_kb_hook = False
        self._mouse_hook_thread = None                       # WH_MOUSE_LL 钩子线程
        self._kb_hook_thread = None                          # WH_KEYBOARD_LL 钩子线程
        self._event_index: dict[str, list[dict]] = {}        # 事件索引: event_value → [trigger, ...]

        # 加载初始配置
        self._triggers = load_triggers()
        self._build_index()
        _log(f"INIT | triggers={len(self._triggers)} | "
             f"index_keys={list(self._event_index.keys())}", "INIT")

    def set_ui_focus_check(self, callback):
        """设置 UI 焦点检查回调。"""
        self._ui_focus_check = callback

    # ================================================================
    # 生命周期
    # ================================================================

    def start(self):
        """启动引擎：注册所有全局输入钩子。"""
        if self._running:
            return
        self._reload_hooks()
        self._last_reload_time = time.time()
        self._running = True
        enabled_count = sum(1 for t in self._triggers if t.get("enabled"))
        _log(f"START | enabled={enabled_count}/{len(self._triggers)}", "LIFECYCLE")
        if enabled_count > 0:
            self._log("ok", f"触发器监控已启动 ({enabled_count} 个活跃)", "TriggerManager")
        else:
            self._log("info", "触发器监控已启动（无活跃触发器）", "TriggerManager")

    def stop(self):
        """停止引擎：注销所有钩子。"""
        if not self._running:
            return
        self._unregister_all_hooks()
        self._running = False
        _log("STOP | hooks unregistered", "LIFECYCLE")
        self._log("info", "触发器监控已停止", "TriggerManager")

    def reload(self, triggers: Optional[list[dict]] = None):
        """热重载配置。"""
        src = "provided" if triggers is not None else "from_file"
        _log(f"reload() | running={self._running} | src={src}", "RELOAD")
        if triggers is not None:
            self._triggers = triggers
        else:
            self._triggers = load_triggers()
        self._build_index()
        if self._running:
            self._reload_hooks()
            self._last_reload_time = time.time()
        enabled_count = sum(1 for t in self._triggers if t.get("enabled"))
        self._log("ok", f"配置已重载 ({len(self._triggers)} 个 / {enabled_count} 活跃)",
                   "TriggerManager.reload")

    @property
    def is_running(self) -> bool:
        """hook 线程是否在运行(供 UI 启停按钮读取状态)。"""
        return self._running

    @property
    def triggers(self) -> list[dict]:
        """所有触发器配置列表的拷贝(返回新 list 防止外部直接修改内部状态)。"""
        return list(self._triggers)

    # ================================================================
    # 钩子管理
    # ================================================================

    def _build_index(self):
        """根据当前触发器列表重建事件索引（O(1) 查找）。"""
        self._event_index.clear()
        for t in self._triggers:
            if not t.get("enabled"):
                continue
            ti = t.get("trigger_input", {})
            ti_type = ti.get("type", "mouse")
            if ti_type == "mouse":
                key = ti.get("button", "right_press")
            else:
                key = ti.get("key", "").lower()
            if key:
                self._event_index.setdefault(key, []).append(t)

    def _reload_hooks(self):
        """重建所有钩子（先注销旧的，再根据当前配置注册新的）。
        使用标志位避免不必要的钩子注销/重注册。
        """
        need_mouse = any(
            t.get("enabled") and t.get("trigger_input", {}).get("type") == "mouse"
            for t in self._triggers
        )
        need_kb = any(
            t.get("enabled") and t.get("trigger_input", {}).get("type") == "keyboard"
            for t in self._triggers
        )

        # 只注销不再需要的钩子
        if self._has_mouse_hook and not need_mouse:
            self._unregister_hook("mouse")
            self._has_mouse_hook = False
        if self._has_kb_hook and not need_kb:
            self._unregister_hook("keyboard")
            self._has_kb_hook = False

        # 只注册尚未注册的钩子
        if need_mouse and not self._has_mouse_hook:
            try:
                self._mouse_hook_thread = _MouseHookThread(self._on_mouse_event)
                self._mouse_hook_thread.start()
                self._has_mouse_hook = True
            except Exception as e:
                _log(f"HOOK | mouse FAIL: {e}", "ERROR")
                self._log("error", f"鼠标钩子注册失败: {e}", "TriggerManager")

        if need_kb and not self._has_kb_hook:
            try:
                self._kb_hook_thread = _KeyboardHookThread(self._on_keyboard_event)
                self._kb_hook_thread.start()
                self._has_kb_hook = True
            except Exception as e:
                _log(f"HOOK | keyboard FAIL: {e}", "ERROR")
                self._log("error", f"键盘钩子注册失败: {e}", "TriggerManager")

    def _unregister_hook(self, hook_type: str):
        """注销指定类型的钩子。"""
        if hook_type == "mouse" and self._mouse_hook_thread:
            self._mouse_hook_thread.stop()
            self._mouse_hook_thread = None
            return
        if hook_type == "keyboard" and self._kb_hook_thread:
            self._kb_hook_thread.stop()
            self._kb_hook_thread = None
            return

    def _unregister_all_hooks(self):
        """注销所有已注册的钩子。"""
        if self._mouse_hook_thread:
            self._mouse_hook_thread.stop()
            self._mouse_hook_thread = None
        if self._kb_hook_thread:
            self._kb_hook_thread.stop()
            self._kb_hook_thread = None
        self._has_mouse_hook = False
        self._has_kb_hook = False

    # ================================================================
    # 事件处理
    # ================================================================

    def _on_mouse_event(self, event):
        """鼠标事件回调（在 _MouseHookThread 的独立线程中执行）。

        _MouseEvent 始终有 event_type ("press"/"release") 和 button 属性。
        匹配 left_press / left_release 等精确事件后通过 Timer 延迟执行动作。
        """
        event_type = event.event_type
        if event_type not in ("press", "release"):
            return

        event_button = event.button
        if event_button is None:
            return

        # 组合为配置中的 key 格式：如 "left_press", "right_release"
        lookup_key = f"{event_button}_{event_type}"
        self._match_and_fire(lookup_key, is_keyboard=False)

    def _on_keyboard_event(self, event):
        """键盘事件回调（在 _KeyboardHookThread 的独立线程中执行）。"""
        if event.event_type != "down":
            return

        event_name = getattr(event, "name", None)
        if event_name is None:
            return

        self._match_and_fire(event_name, is_keyboard=True)

    def _match_and_fire(self, event_value: str, is_keyboard: bool = False):
        """将输入事件与已启用的触发器匹配，符合条件的延迟执行。
        使用预建索引实现 O(1) 查找。
        """
        with self._lock:
            now = time.time()

            # ★ 重载冷却期：reload 后 800ms 内不处理事件（防止 UI 操作时误触发）
            cooldown = now - self._last_reload_time
            if cooldown < 0.8:
                return

            # ★ UI 焦点检查：用户正在操作管理面板/悬浮窗时跳过触发
            if self._ui_focus_check is not None:
                try:
                    focus_result = self._ui_focus_check()
                    if focus_result:
                        return
                except Exception:
                    pass

            # ★ 通过预建索引快速查找候选触发器
            # 鼠标事件：event_value 已是 left_press / right_release 格式，直接用
            # 键盘事件：转小写匹配
            if is_keyboard:
                lookup_key = event_value.lower()
            else:
                lookup_key = event_value  # 已是 "left_press" 等格式
            candidates = self._event_index.get(lookup_key, [])
            if not candidates:
                return

            for trigger in candidates:
                ti = trigger.get("trigger_input", {})
                ti_type = ti.get("type", "mouse")
                name = trigger.get("name", "未命名")

                # 类型必须匹配（索引中已区分，但防止同一事件值出现在两种类型中）
                if is_keyboard and ti_type != "keyboard":
                    continue
                if not is_keyboard and ti_type != "mouse":
                    continue

                # ★ 防抖检查（随机化间隔，模拟人类操作节奏）
                last = self._last_trigger_time.get(name, 0)
                debounce = random.uniform(self.DEBOUNCE_INTERVAL_MIN, self.DEBOUNCE_INTERVAL_MAX)
                if now - last < debounce:
                    continue
                self._last_trigger_time[name] = now

                # ★ 延迟执行
                delay = max(0, trigger.get("delay_ms", 0)) / 1000.0
                actions_str = ", ".join(f"{a.get('type')}:{a.get('value','')}" for a in trigger.get("actions", []))
                _log(f"FIRE! | '{name}' | {delay*1000:.0f}ms | [{actions_str}]", "FIRE")
                timer = threading.Timer(
                    delay,
                    self._execute_actions,
                    args=[trigger],
                )
                timer.daemon = True
                timer.start()
                break  # 一个事件最多匹配一个触发器

    # ================================================================
    # 动作执行 — 分发器模式，易于扩展新动作类型
    # ================================================================

    def _execute_actions(self, trigger: dict):
        """按顺序执行触发器的所有响应动作。"""
        actions = trigger.get("actions", [])
        name = trigger.get("name", "未命名")

        for i, action in enumerate(actions):
            atype = action.get("type", "")
            aval = action.get("value", "")
            try:
                executor = _ACTION_EXECUTORS.get(atype)
                if executor:
                    executor(action)
                else:
                    self._log("warn",
                              f"触发器「{name}」的第 {i+1} 个动作类型未知: '{atype}'",
                              "TriggerManager")
            except Exception as e:
                self._log("error",
                          f"触发器「{name}」动作执行失败 (#{i+1}): {e}",
                          "TriggerManager")


# ============================================================
# 动作执行器注册表 — 新增动作类型只需在此添加一行
# ============================================================

def _exec_key(action: dict):
    """执行按键动作。使用 Windows API keybd_event 模拟按键。"""
    value = action.get("value", "").strip()
    if value:
        _send_key(value)


def _exec_mouse_click(action: dict):
    """执行鼠标点击动作。"""
    value = action.get("value", "").strip().lower()
    if value in MOUSE_BUTTON_VALUES:
        _mouse_click(value)


def _exec_mouse_move(action: dict):
    """执行鼠标移动动作：将光标移动到指定屏幕坐标。

    支持绝对坐标 "960, 540" 和相对坐标 "+100, -50"（以"+"或"-"开头）。
    """
    value = action.get("value", "").strip()
    if not value:
        return

    # 判断是否为相对坐标
    relative = value.startswith(("+", "-"))
    # 解析坐标格式: "960, 540" 或 "+100, -50"
    parts = value.lstrip("+-").replace(" ", "").split(",")
    if len(parts) != 2:
        return

    try:
        x = int(parts[0])
        y = int(parts[1])
        # 恢复相对坐标的符号
        if relative:
            if value.strip().startswith("-"):
                x = -x
            # 检查 y 的符号（从原始字符串中查找）
            y_part = value.replace(" ", "").split(",")[1]
            if y_part.startswith("-"):
                y = -y
            cur_x, cur_y = _mouse_get_pos()
            _mouse_move(cur_x + x, cur_y + y)
        else:
            _mouse_move(x, y)
    except (ValueError, TypeError):
        pass


# ── 分发表：action.type → 执行函数 ──
_ACTION_EXECUTORS = {
    "key":         _exec_key,
    "mouse_click": _exec_mouse_click,
    "mouse_move":  _exec_mouse_move,
    # ★ 新增动作类型在此注册：
    # "sequence":   _exec_sequence,
    # "macro":      _exec_macro,
}
