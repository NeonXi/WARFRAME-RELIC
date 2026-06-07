"""
辅助触发器引擎模块

职责：
- 注册全局鼠标/键盘钩子，监听用户输入事件
- 匹配事件与已配置的触发器
- 延迟执行响应动作（按键、鼠标点击、鼠标移动）
- 防抖保护 + 线程安全
- 支持运行时热重载（reload）

架构设计：
- TriggerManager 是单例式引擎，由 AppCore 在后台加载完成后创建并启动
- 所有钩子回调在独立线程中执行，动作执行通过 Timer 延迟到主逻辑线程
- 动作类型通过 _ACTION_EXECUTORS 字典分发，新增动作类型只需注册一个 executor 函数
"""

import random
import threading
import sys
import time
from typing import Optional

_DEBUG = False  # 调试开关

def _dbg(msg: str):
    """调试输出到 stderr（dev_runner watch 模式会捕获 stderr）。"""
    if _DEBUG:
        print(f"[DEBUG] {msg}", file=sys.stderr, flush=True)

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

# 消息 → 按钮名
_WM_BTN_MAP = {
    _WM_LBUTTONDOWN: "left",
    _WM_RBUTTONDOWN: "right",
    _WM_MBUTTONDOWN: "middle",
    _WM_XBUTTONDOWN: "x1",
}


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
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
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
        if nCode >= 0 and wParam in _WM_BTN_MAP:
            button = _WM_BTN_MAP[wParam]
            evt = _MouseEvent("down", button)
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
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
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
    """
    if not key_str:
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
        return

    # 按下修饰键
    if modifiers["ctrl"]:
        _user32.keybd_event(0x11, 0, 0, 0)
    if modifiers["shift"]:
        _user32.keybd_event(0x10, 0, 0, 0)
    if modifiers["alt"]:
        _user32.keybd_event(0x12, 0, 0, 0)

    # 按下主键
    _user32.keybd_event(vk, 0, 0, 0)
    _time.sleep(0.02)
    # 释放主键
    _user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)

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
    "left":   "left",
    "right":  "right",
    "middle": "middle",
    "x1":     "mouse x",      # keyboard 库的侧键1 名称
    "x2":     "mouse x2",     # keyboard 库的侧键2名称
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

    def set_ui_focus_check(self, callback):
        """设置 UI 焦点检查回调。

        Args:
            callback: 无参可调用对象，返回 True 时表示用户正在操作管理面板/悬浮窗，
                     触发器应跳过本次匹配（防止 UI 操作时误触发）。
        """
        self._ui_focus_check = callback

    # ================================================================
    # 生命周期
    # ================================================================

    def start(self):
        """启动引擎：注册所有全局输入钩子。"""
        if self._running:
            return

        self._reload_hooks()
        self._last_reload_time = time.time()  # 启动时也设置，避免启动瞬间的误触发
        self._running = True

        enabled_count = sum(1 for t in self._triggers if t.get("enabled"))
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
        self._log("info", "触发器监控已停止", "TriggerManager")

    def reload(self, triggers: Optional[list[dict]] = None):
        """热重载配置（不重启引擎，仅更新触发器列表和钩子）。

        Args:
            triggers: 新的触发器列表。为 None 时从文件重新加载。
        """
        _dbg(f"reload() 被调用, running={self._running}, "
             f"传入triggers={'有' if triggers is not None else '无(从文件加载)'}")
        if triggers is not None:
            self._triggers = triggers
        else:
            self._triggers = load_triggers()

        self._build_index()

        if self._running:
            _dbg(f"reload: 正在重注册钩子...")
            self._reload_hooks()
            self._last_reload_time = time.time()  # 记录重载时间，用于冷却期
            _dbg(f"reload: 钩子已重注册, 冷却期开始 (800ms)")

        enabled_count = sum(1 for t in self._triggers if t.get("enabled"))
        self._log("ok", f"触发器配置已重载 ({len(self._triggers)} 个 / {enabled_count} 活跃)",
                   "TriggerManager.reload")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def triggers(self) -> list[dict]:
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
                key = ti.get("button", "right")
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
                self._log("error", f"鼠标钩子注册失败: {e}", "TriggerManager")

        if need_kb and not self._has_kb_hook:
            try:
                self._kb_hook_thread = _KeyboardHookThread(self._on_keyboard_event)
                self._kb_hook_thread.start()
                self._has_kb_hook = True
            except Exception as e:
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

        _MouseEvent 始终有 event_type 和 button 属性。
        只处理按下（down）事件，匹配后通过 Timer 延迟执行动作。
        """
        if event.event_type != "down":
            return

        event_button = event.button
        if event_button is None:
            return

        _dbg(f"_on_mouse_event: button={event_button}, type={event.event_type}")
        self._match_and_fire(event_button)

    def _on_keyboard_event(self, event):
        """键盘事件回调（在 _KeyboardHookThread 的独立线程中执行）。"""
        if event.event_type != "down":
            return

        event_name = getattr(event, "name", None)
        if event_name is None:
            return

        _dbg(f"_on_keyboard_event: name={event_name}, type={event.event_type}")
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
                _dbg(f"_match_and_fire: 冷却中 (距上次reload {cooldown:.3f}s < 0.8s), event={event_value}, is_kb={is_keyboard}")
                return

            # ★ UI 焦点检查：用户正在操作管理面板/悬浮窗时跳过触发
            if self._ui_focus_check is not None:
                try:
                    focus_result = self._ui_focus_check()
                    if focus_result:
                        _dbg(f"_match_and_fire: UI焦点检查通过(跳过), event={event_value}, is_kb={is_keyboard}")
                        return
                except Exception as e:
                    _dbg(f"_match_and_fire: UI焦点检查异常: {e}")

            # ★ 通过预建索引快速查找候选触发器
            lookup_key = event_value.lower() if is_keyboard else _HOOK_BUTTON_TO_CONFIG.get(event_value, event_value)
            candidates = self._event_index.get(lookup_key, [])
            if not candidates:
                return

            _dbg(f"_match_and_fire: 索引匹配, event='{event_value}', lookup_key='{lookup_key}', "
                 f"候选数={len(candidates)}")

            for trigger in candidates:
                ti = trigger.get("trigger_input", {})
                ti_type = ti.get("type", "mouse")
                name = trigger.get("name", "未命名")

                # 类型必须匹配（索引中已区分，但防止同一事件值出现在两种类型中）
                if is_keyboard and ti_type != "keyboard":
                    continue
                if not is_keyboard and ti_type != "mouse":
                    continue

                _dbg(f"匹配检查: 触发器='{name}', type={ti_type}, event='{event_value}'")

                # ★ 防抖检查（随机化间隔，模拟人类操作节奏）
                last = self._last_trigger_time.get(name, 0)
                debounce = random.uniform(self.DEBOUNCE_INTERVAL_MIN, self.DEBOUNCE_INTERVAL_MAX)
                if now - last < debounce:
                    _dbg(f"防抖跳过: '{name}', 距上次{now-last:.3f}s < {debounce:.3f}s")
                    continue
                self._last_trigger_time[name] = now

                # ★ 延迟执行
                delay = max(0, trigger.get("delay_ms", 0)) / 1000.0
                actions_str = ", ".join(f"{a.get('type')}:{a.get('value','')}" for a in trigger.get("actions", []))
                _dbg(f"★★ 匹配成功! 触发器='{name}', 延迟={delay*1000:.0f}ms, 动作=[{actions_str}]")
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
        _dbg(f"_execute_actions: 开始执行 '{name}', 动作数={len(actions)}")

        for i, action in enumerate(actions):
            atype = action.get("type", "")
            aval = action.get("value", "")
            _dbg(f"  执行动作 #{i+1}: type='{atype}', value='{aval}'")
            try:
                executor = _ACTION_EXECUTORS.get(atype)
                if executor:
                    executor(action)
                    _dbg(f"    [OK] 动作#{i+1} 执行成功")
                else:
                    self._log("warn",
                              f"触发器「{name}」的第 {i+1} 个动作类型未知: '{atype}'",
                              "TriggerManager")
            except Exception as e:
                self._log("error",
                          f"触发器「{name}」动作执行失败 (#{i+1}): {e}",
                          "TriggerManager")
                import traceback
                _dbg(f"    [X] 动作#{i+1} 异常详情:\n{traceback.format_exc()}")


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
