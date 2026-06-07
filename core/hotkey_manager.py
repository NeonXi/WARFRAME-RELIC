"""
热键管理模块 —— 使用 Windows API RegisterHotKey + Qt nativeEventFilter 替代 keyboard 库。

职责：
- 注册/更新全局热键
- 热键健康检查 + 自动恢复
- 热键变更回调
- 防重入保护
"""

import time
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter

from core.hotkey_config import load_hotkeys, DEFAULT_HOTKEYS

# Windows API
_user32 = ctypes.windll.user32

# 修饰键常量
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# 修饰键名 → 常量
_MOD_NAME_TO_FLAG = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "windows": MOD_WIN,
}

# 特殊键名 → VK 码
_SPECIAL_VK = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "printscreen": 0x2C, "pause": 0x13,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}


def _parse_hotkey(hk_str: str) -> tuple[int, int]:
    """解析热键字符串为 (modifiers, vk_code)。

    支持格式: "ctrl+g", "ctrl+shift+f4", "alt+1", "f5" 等。
    """
    if not hk_str:
        return 0, 0

    parts = hk_str.lower().strip().split("+")
    mod_flags = 0
    key_name = parts[-1].strip()

    for part in parts[:-1]:
        part = part.strip()
        flag = _MOD_NAME_TO_FLAG.get(part)
        if flag:
            mod_flags |= flag

    # 解析键名 → VK
    vk = _SPECIAL_VK.get(key_name)
    if vk is None:
        if len(key_name) == 1:
            # 单个字符: a-z, 0-9 等
            vk = ord(key_name.upper())
        else:
            return 0, 0

    return mod_flags, vk


class HotkeyManager(QAbstractNativeEventFilter):
    """管理全局快捷键的注册、健康检查、恢复。

    使用 RegisterHotKey + nativeEventFilter 替代 keyboard 库，
    彻底避免 keyboard 库创建/销毁隐藏窗口导致的启动闪窗。
    """

    def __init__(self, bridge, log_func, app):
        """
        Args:
            bridge: TriggerBridge 实例，用于发射快捷键事件
            log_func: 日志回调函数，签名 log_func(msg, log_type, source)
            app: QApplication 实例，用于安装 nativeEventFilter
        """
        self._bridge = bridge
        self._log = log_func
        self._app = app

        super().__init__()

        # 安装原生事件过滤器
        self._app.installNativeEventFilter(self)

        # 已注册的热键: {action: hotkey_id}
        self._hotkey_ids = {}
        # 反向映射: {hotkey_id: action}
        self._registered = {}

        # 防重入保护
        self._last_action_time = 0

    # ================================================================
    # 公开接口
    # ================================================================

    @property
    def registered(self) -> dict:
        return self._registered

    @property
    def last_action_time(self) -> float:
        return self._last_action_time

    @last_action_time.setter
    def last_action_time(self, value: float):
        self._last_action_time = value

    def register_initial(self):
        """启动时注册热键（从配置文件读取）。"""
        self._register(load_hotkeys())

    def on_config_changed(self, new_hotkeys: dict):
        """配置变更时重新注册热键。"""
        print(f"[热键] 快捷键已更新: {new_hotkeys}", flush=True)
        self._register(new_hotkeys)

    def health_check(self) -> bool:
        """诊断快捷键健康状态。返回 True 表示一切正常。"""
        if not self._registered:
            print("[快捷键诊断] [x] 警告：没有任何已注册的热键！", flush=True)
            return False

        expected_actions = ["select", "fullscreen", "query_price"]
        all_ok = True
        for action in expected_actions:
            hk_str = load_hotkeys().get(action, DEFAULT_HOTKEYS[action])
            if action not in self._hotkey_ids:
                print(f"[快捷键诊断] [x] 缺失: {action} ({hk_str}) 未注册！", flush=True)
                all_ok = False

        if all_ok:
            print(f"[快捷键诊断] [ok] 所有热键正常 (已注册 {len(self._registered)} 个)", flush=True)
        return all_ok

    def auto_recover(self):
        """定期心跳：检查热键是否仍然有效，失效则自动恢复。"""
        if not self.health_check():
            self._log("检测到快捷键异常，自动尝试恢复...", "warn", "health_check")
            self._register(load_hotkeys())
            if self.health_check():
                self._log("快捷键自动恢复成功", "ok", "health_check")
            else:
                self._log("快捷键自动恢复失败！请手动点击管理面板的「紧急重置」按钮",
                         "error", "health_check")

    def force_reset(self):
        """紧急重置：用硬编码默认值重新注册所有快捷键。"""
        self._register(dict(DEFAULT_HOTKEYS))

    def clear(self):
        """注销所有热键。"""
        for hk_id in self._hotkey_ids.values():
            try:
                _user32.UnregisterHotKey(None, hk_id)
            except Exception:
                pass
        self._hotkey_ids.clear()
        self._registered.clear()

    # ================================================================
    # nativeEventFilter — 捕获 WM_HOTKEY 消息
    # ================================================================

    def nativeEventFilter(self, eventType, message):
        """Qt 原生事件过滤器，捕获 WM_HOTKEY 消息。"""
        msg = wintypes.MSG.from_address(message.__int__())
        if msg.message == 0x0312:  # WM_HOTKEY
            hk_id = msg.wParam
            action = self._registered.get(hk_id)
            if action:
                self._bridge.fired.emit(action)
                return True, 0
        return False, 0

    # ================================================================
    # 内部实现
    # ================================================================

    def _register(self, hotkeys: dict):
        """注册热键（使用 RegisterHotKey 替代 keyboard.add_hotkey）。"""
        print(f"[热键] ===== 开始注册热键: {hotkeys} =====", flush=True)

        # 第一步：注销所有旧热键
        for hk_id in self._hotkey_ids.values():
            try:
                _user32.UnregisterHotKey(None, hk_id)
            except Exception as e:
                print(f"[热键] 注销失败 id={hk_id}: {e}", flush=True)
        self._hotkey_ids.clear()
        self._registered.clear()

        # 第二步：注册新热键
        action_map = {
            "select": "select", "fullscreen": "fullscreen",
            "query_price": "query_price",
        }

        success_count = 0
        for action, action_name in action_map.items():
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])

            if not hk_str or '+' not in hk_str:
                print(f"[热键] [x] 跳过非法热键: {action} -> '{hk_str}'", flush=True)
                self._log(f"快捷键 {action} 格式非法，使用默认值", "warn", "hotkeys")
                hk_str = DEFAULT_HOTKEYS[action]

            mod, vk = _parse_hotkey(hk_str)
            if vk == 0:
                print(f"[热键] [x] 无法解析: {action} -> '{hk_str}'", flush=True)
                continue

            # 生成唯一 ID（避免 hash 冲突）
            hk_id = (hash(action) & 0x7FFF) | MOD_NOREPEAT

            for attempt in range(3):
                try:
                    if _user32.RegisterHotKey(None, hk_id, mod, vk):
                        self._hotkey_ids[action] = hk_id
                        self._registered[hk_id] = action
                        print(f"[热键] [ok] {hk_str} 注册成功 ({action_name}) [第{attempt + 1}次]", flush=True)
                        success_count += 1
                        break
                    else:
                        # 尝试先注销再注册
                        _user32.UnregisterHotKey(None, hk_id)
                        if _user32.RegisterHotKey(None, hk_id, mod, vk):
                            self._hotkey_ids[action] = hk_id
                            self._registered[hk_id] = action
                            print(f"[热键] [ok] {hk_str} 注册成功 ({action_name}) [第{attempt + 1}次/重试]", flush=True)
                            success_count += 1
                            break
                except Exception as e:
                    print(f"[热键] [!] {hk_str} 注册失败 (第{attempt + 1}/3次): {e}", flush=True)
                    if attempt < 2:
                        time.sleep(0.05)

            if action not in self._hotkey_ids:
                self._log(f"[x] 快捷键 {hk_str} ({action_name}) 注册失败，尝试回退默认值",
                         "error", "hotkeys")
                fallback = DEFAULT_HOTKEYS[action]
                mod2, vk2 = _parse_hotkey(fallback)
                if vk2 != 0:
                    try:
                        hk_id2 = (hash(action) & 0x7FFF) | MOD_NOREPEAT
                        _user32.UnregisterHotKey(None, hk_id2)
                        if _user32.RegisterHotKey(None, hk_id2, mod2, vk2):
                            self._hotkey_ids[action] = hk_id2
                            self._registered[hk_id2] = action
                            print(f"[热键] [ok] 回退默认: {fallback} ({action_name})", flush=True)
                            success_count += 1
                    except Exception as e2:
                        print(f"[热键] [x] 回退也失败: {fallback} - {e2}", flush=True)

        print(f"[热键] ===== 注册完成: {success_count}/{len(action_map)} 成功 =====", flush=True)

        # 健康检查
        self.health_check()