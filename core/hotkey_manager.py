"""
[L0/L1] core.hotkey_manager — 全局热键管理器(Windows API)

使用 Windows API RegisterHotKey + Qt nativeEventFilter 替代 keyboard 库。
原因: keyboard 库在某些 Windows 版本/权限下不可靠。

职责:
- 注册/更新全局热键
- 热键健康检查 + 自动恢复(系统注销后重新注册)
- 热键变更回调(on_config_changed)
- 紧急重置(force_reset)

依赖: PySide6.QtCore + Windows API (user32.dll)
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

import time
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

from core.hotkey_config import load_hotkeys, load_hotkey_enabled, DEFAULT_HOTKEYS

# Windows API
# use_last_error=True: 注册失败时 ctypes.get_last_error() 才能拿到可靠的
# Win32 错误码（如 1409 ERROR_HOTKEY_ALREADY_REGISTERED）
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL

# 修饰键常量
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# 走 RegisterHotKey 全局注册的功能（顺序即状态报告/诊断 UI 的展示顺序）。
# 注意: cd_1..cd_4 不走此路线（WH_KEYBOARD_LL 观察者钩子，不独占按键）
REGISTERED_ACTIONS = ("select", "fullscreen", "eye_mask", "bring_to_front")

# ── 注册状态报告原因码（get_status_report / probe_candidate 共用）──
REASON_OK = "ok"                # 注册成功 / 组合空闲
REASON_OCCUPIED = "occupied"    # 1409: 被系统中其他程序占用
REASON_INTERNAL = "internal"    # 与本软件另一个功能的快捷键冲突
REASON_INVALID = "invalid"      # 组合非法或无法解析
REASON_FAILED = "failed"        # 其他注册失败
REASON_DISABLED = "disabled"    # 用户在功能开关页禁用了该快捷键
REASON_UNKNOWN = "unknown"      # 尚未注册/未知

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

        # 最近一次注册使用的配置 {action: hotkey_str}（预检内部冲突用）
        self._current_hotkeys: dict[str, str] = {}
        # 最近一次注册的状态报告 {action: {action, hotkey, ok, reason, error_code}}
        self._last_report: dict[str, dict] = {}

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
        enabled_map = load_hotkey_enabled()
        # 若所有走 RegisterHotKey 的功能都被用户禁用，则没有已注册热键是正常的
        any_enabled = any(enabled_map.get(a, True) for a in REGISTERED_ACTIONS)
        if not self._registered:
            if any_enabled:
                print("[快捷键诊断] [x] 警告：没有任何已注册的热键！", flush=True)
                return False
            print("[快捷键诊断] [ok] 所有全局快捷键已被用户禁用", flush=True)
            return True

        expected_actions = ["select", "fullscreen"]
        all_ok = True
        for action in expected_actions:
            # 用户主动禁用的快捷键不算"缺失"
            if not enabled_map.get(action, True):
                continue
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

    # ================================================================
    # 占用诊断（UI「重新检测」/ 改键预检入口）
    # ================================================================

    def get_status_report(self) -> list[dict]:
        """返回各全局热键最近一次注册的状态报告（纯数据，供 UI 渲染）。

        每项: {action, hotkey, ok, reason, error_code}
        reason ∈ ok/occupied/internal/invalid/failed/unknown
        无副作用：只读最近一次注册结果，不注销、不重注册。
        """
        report = []
        for action in REGISTERED_ACTIONS:
            item = self._last_report.get(action)
            if item is None:
                item = {
                    "action": action,
                    "hotkey": self._current_hotkeys.get(action, DEFAULT_HOTKEYS.get(action, "")),
                    "ok": False,
                    "reason": REASON_UNKNOWN,
                    "error_code": None,
                }
            report.append(item)
        return report

    def probe_candidate(self, hk_str: str, exclude_action: str | None = None) -> dict:
        """预检某个热键组合当前是否可用（不改动现有注册状态）。

        判定顺序:
          1. 与 exclude_action 自身当前组合相同（用户没改）→ ok
          2. 与本软件其他已注册功能组合相同 → internal（内部冲突）
          3. Win32 临时 ID 试探注册: 成功立即注销 → ok;
             1409 → occupied（外部程序占用）; 其他 → failed

        Args:
            hk_str: 热键字符串，如 "ctrl+h"
            exclude_action: 正在修改的 action，其现有组合不算冲突

        返回: {ok, reason, hotkey, conflict_action, error_code}
        """
        raw = hk_str or ""
        result = {
            "ok": False, "reason": REASON_INVALID, "hotkey": raw.strip().lower(),
            "conflict_action": None, "error_code": None,
        }

        hk = raw.strip().lower()
        if not hk:
            return result

        # 1. 与自身当前组合相同 → 没改，可用
        if exclude_action and self._current_hotkeys.get(exclude_action) == hk:
            result["ok"] = True
            result["reason"] = REASON_OK
            return result

        # 2. 与本软件其他走 RegisterHotKey 的功能撞键
        for action in REGISTERED_ACTIONS:
            if action == exclude_action:
                continue
            if self._current_hotkeys.get(action) == hk:
                result["reason"] = REASON_INTERNAL
                result["conflict_action"] = action
                return result

        # 3. 解析键名
        mod, vk = _parse_hotkey(hk)
        if vk == 0:
            return result

        # 4. 选取一个不与任何已持有 ID 冲突的临时 ID
        used_ids = set(self._hotkey_ids.values())
        probe_id = next((i for i in range(0x7000, 0x8000) if i not in used_ids), None)
        if probe_id is None:
            result["reason"] = REASON_FAILED
            return result

        try:
            ok, err = self._raw_register(probe_id, mod, vk)
            if ok:
                _user32.UnregisterHotKey(None, probe_id)
                result.update(ok=True, reason=REASON_OK, error_code=0)
            elif err == 1409:
                result.update(reason=REASON_OCCUPIED, error_code=err)
            else:
                result.update(reason=REASON_FAILED, error_code=err)
        except Exception as e:
            print(f"[热键] 探测异常 {hk}: {e}", flush=True)
            result["reason"] = REASON_FAILED
        finally:
            # 兜底：无论成功失败都确保临时 ID 不残留
            try:
                _user32.UnregisterHotKey(None, probe_id)
            except Exception:
                pass
        return result

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

    def _alloc_hotkey_id(self, action: str) -> int:
        """业务热键 ID：action 哈希取低 15 位（进程内稳定即可）。

        注意：MOD_NOREPEAT 属于修饰键标志，必须放在 RegisterHotKey 的
        fsModifiers 参数（见 _raw_register），不能拼进 ID。
        """
        return hash(action) & 0x7FFF

    def _raw_register(self, hk_id: int, mod: int, vk: int) -> tuple[bool, int]:
        """单次 RegisterHotKey（自动附加 MOD_NOREPEAT：长按不连发）。

        Returns:
            (是否成功, Win32 错误码)；成功时错误码为 0。
        """
        ctypes.set_last_error(0)
        ok = bool(_user32.RegisterHotKey(None, hk_id, mod | MOD_NOREPEAT, vk))
        return ok, (0 if ok else ctypes.get_last_error())

    @staticmethod
    def _make_report(action: str, hotkey: str, ok: bool,
                     reason: str, error_code: int | None = None) -> dict:
        return {
            "action": action,
            "hotkey": hotkey,
            "ok": ok,
            "reason": reason,
            "error_code": error_code,
        }

    def _register(self, hotkeys: dict):
        """注册热键（使用 RegisterHotKey 替代 keyboard.add_hotkey）。

        注册结果逐键写入 self._last_report，供 get_status_report()/UI 诊断。
        """
        print(f"[热键] ===== 开始注册热键: {hotkeys} =====", flush=True)
        self._current_hotkeys = dict(hotkeys)
        report: dict[str, dict] = {}

        # 第一步：注销所有旧热键
        for hk_id in self._hotkey_ids.values():
            try:
                _user32.UnregisterHotKey(None, hk_id)
            except Exception as e:
                print(f"[热键] 注销失败 id={hk_id}: {e}", flush=True)
        self._hotkey_ids.clear()
        self._registered.clear()

        # 第二步:注册新热键
        # 注意: cd_1..cd_4 不走 RegisterHotKey 路线,改用 WH_KEYBOARD_LL 钩子
        # (LowLevelHotkeyHook in core/services/cd_hotkey_hook.py),原因:
        #   RegisterHotKey 注册的键组合会被全系统独占拦截 → 1/2/3/4 是游戏
        #   和系统的核心输入键,一旦注册会全游戏抢键
        #   WH_KEYBOARD_LL 是"观察者"模式,默认 CallNextHookEx 放行,只用于通知
        #   → 既能触发 CD 倒计时,又不影响游戏/系统的 1/2/3/4 输入
        enabled_map = load_hotkey_enabled()
        success_count = 0
        for action in REGISTERED_ACTIONS:
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])

            # 用户在功能开关页禁用了该快捷键 → 不注册,标记为 disabled
            if not enabled_map.get(action, True):
                print(f"[热键] [跳过] {action} 已被用户禁用", flush=True)
                report[action] = self._make_report(action, hk_str, False, REASON_DISABLED)
                continue

            if not hk_str:
                print(f"[热键] [x] 跳过空热键: {action} -> ''", flush=True)
                report[action] = self._make_report(action, "", False, REASON_INVALID)
                continue
            # 允许无 modifier 的单键,但带 '+' 时必须至少一个合法 modifier
            if '+' in hk_str:
                parts = hk_str.split('+')
                if not any(p.strip() in _MOD_NAME_TO_FLAG for p in parts[:-1]):
                    print(f"[热键] [x] 跳过非法热键: {action} -> '{hk_str}'", flush=True)
                    self._log(f"快捷键 {action} 格式非法，使用默认值", "warn", "hotkeys")
                    hk_str = DEFAULT_HOTKEYS[action]

            mod, vk = _parse_hotkey(hk_str)
            if vk == 0:
                print(f"[热键] [x] 无法解析: {action} -> '{hk_str}'", flush=True)
                report[action] = self._make_report(action, hk_str, False, REASON_INVALID)
                continue

            hk_id = self._alloc_hotkey_id(action)
            final_ok = False
            final_err = 0

            # 主尝试：最多 3 轮，每轮「直接注册 + 先注销再注册」
            for attempt in range(3):
                try:
                    ok, err = self._raw_register(hk_id, mod, vk)
                    if ok:
                        final_ok = True
                        self._hotkey_ids[action] = hk_id
                        self._registered[hk_id] = action
                        print(f"[热键] [ok] {hk_str} 注册成功 ({action}) [第{attempt + 1}次]",
                              flush=True)
                        success_count += 1
                        break
                    # 尝试先注销再注册
                    _user32.UnregisterHotKey(None, hk_id)
                    ok2, err2 = self._raw_register(hk_id, mod, vk)
                    if ok2:
                        final_ok = True
                        self._hotkey_ids[action] = hk_id
                        self._registered[hk_id] = action
                        print(f"[热键] [ok] {hk_str} 注册成功 ({action}) [第{attempt + 1}次/重试]",
                              flush=True)
                        success_count += 1
                        break
                    final_err = err2 or err
                    print(f"[热键] [!] {hk_str} 注册失败 (第{attempt + 1}/3次) 错误码={final_err}",
                          flush=True)
                    if attempt < 2:
                        time.sleep(0.05)
                except Exception as e:
                    print(f"[热键] [!] {hk_str} 注册异常 (第{attempt + 1}/3次): {e}", flush=True)
                    if attempt < 2:
                        time.sleep(0.05)

            # 回退默认值（默认组合与当前相同则不再重复尝试）
            if not final_ok:
                self._log(f"快捷键 {hk_str} ({action}) 注册失败，尝试回退默认值",
                          "error", "hotkeys")
                fallback = DEFAULT_HOTKEYS[action]
                if fallback != hk_str:
                    mod2, vk2 = _parse_hotkey(fallback)
                    if vk2 != 0:
                        try:
                            _user32.UnregisterHotKey(None, hk_id)
                            ok3, err3 = self._raw_register(hk_id, mod2, vk2)
                            if ok3:
                                final_ok = True
                                hk_str = fallback
                                self._hotkey_ids[action] = hk_id
                                self._registered[hk_id] = action
                                print(f"[热键] [ok] 回退默认: {fallback} ({action})", flush=True)
                                success_count += 1
                            else:
                                final_err = err3
                        except Exception as e2:
                            print(f"[热键] [x] 回退也失败: {fallback} - {e2}", flush=True)

            if final_ok:
                report[action] = self._make_report(action, hk_str, True, REASON_OK)
            else:
                reason = REASON_OCCUPIED if final_err == 1409 else REASON_FAILED
                report[action] = self._make_report(
                    action, hk_str, False, reason, final_err or None)
                if final_err == 1409:
                    self._log(
                        f"快捷键 {hk_str}（{action}）已被其他程序占用，注册失败，按下将无反应；"
                        f"请在「功能开关」页改键或关闭占用程序后重新检测",
                        "error", "hotkeys")

        self._last_report = report
        print(f"[热键] ===== 注册完成: {success_count}/{len(REGISTERED_ACTIONS)} 成功 =====",
              flush=True)

        # 健康检查
        self.health_check()