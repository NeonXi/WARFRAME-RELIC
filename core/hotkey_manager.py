"""
热键管理模块 —— 从 AppCore 拆分出来的热键注册/健康检查/恢复逻辑。

职责：
- 注册/更新全局热键
- 热键健康检查 + 自动恢复
- 热键变更回调
- 防重入保护
"""

import time
import keyboard

from core.hotkey_config import load_hotkeys, DEFAULT_HOTKEYS


class HotkeyManager:
    """管理全局快捷键的注册、健康检查、恢复。"""

    def __init__(self, bridge, log_func):
        """
        Args:
            bridge: TriggerBridge 实例，用于发射快捷键事件
            log_func: 日志回调函数，签名 log_func(msg, log_type, source)
        """
        self._bridge = bridge
        self._log = log_func

        # 已注册的热键: {hotkey_string: hotkey_id}
        self._registered_hotkeys = {}

        # 防重入保护
        self._last_action_time = 0

    # ================================================================
    # 公开接口
    # ================================================================

    @property
    def registered(self) -> dict:
        return self._registered_hotkeys

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
        if not self._registered_hotkeys:
            print("[快捷键诊断] ✘ 警告：没有任何已注册的热键！", flush=True)
            return False

        expected_actions = ["select", "fullscreen", "query_price"]
        all_ok = True
        for action in expected_actions:
            hk_str = load_hotkeys().get(action, DEFAULT_HOTKEYS[action])
            if hk_str not in self._registered_hotkeys:
                print(f"[快捷键诊断] ✘ 缺失: {action} ({hk_str}) 未注册！", flush=True)
                all_ok = False

        if all_ok:
            print(f"[快捷键诊断] ✓ 所有热键正常 (已注册 {len(self._registered_hotkeys)} 个)", flush=True)
        return all_ok

    def auto_recover(self):
        """定期心跳：检查热键是否仍然有效，失效则自动恢复。"""
        if not self.health_check():
            self._log("检测到快捷键异常，自动尝试恢复...", "warn", "health_check")
            self._register(load_hotkeys())
            if self.health_check():
                self._log("快捷键自动恢复成功", "ok", "health_check")
            else:
                self._log("快捷键自动恢复失败！请手动点击管理面板的「紧急重置」按钮", "error", "health_check")

    def force_reset(self):
        """紧急重置：用硬编码默认值重新注册所有快捷键。"""
        self._register(dict(DEFAULT_HOTKEYS))

    def clear(self):
        """注销所有热键。"""
        for hk_id in self._registered_hotkeys.values():
            try:
                keyboard.remove_hotkey(hk_id)
            except Exception:
                pass
        self._registered_hotkeys.clear()
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    # ================================================================
    # 内部实现
    # ================================================================

    def _register(self, hotkeys: dict):
        """注册热键（增强版：逐键清除、失败重试、健康诊断）。"""
        import ctypes

        # 权限检查
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() if hasattr(ctypes, 'windll') else True
        if not is_admin:
            print("[热键] ⚠ 未以管理员身份运行！keyboard 库注册全局热键需要管理员权限。", flush=True)
            self._log("未以管理员身份运行，快捷键可能无法生效。请右键 → 以管理员身份运行。", "warn", "hotkeys")

        print(f"[热键] ===== 开始注册热键: {hotkeys} =====", flush=True)

        # 第一步：逐个清除旧热键
        for hk_str, hk_id in list(self._registered_hotkeys.items()):
            try:
                keyboard.remove_hotkey(hk_id)
                print(f"[热键] 已清除: {hk_str}", flush=True)
            except Exception as e:
                print(f"[热键] 清除失败 {hk_str}: {e}", flush=True)
        self._registered_hotkeys.clear()

        # 第二步：unhook_all 兜底
        if self._registered_hotkeys or True:  # 始终执行兜底
            try:
                keyboard.unhook_all()
                print("[热键] unhook_all 兜底完成", flush=True)
            except Exception as e:
                print(f"[热键] unhook_all 异常: {e}", flush=True)

        # 第三步：注册新热键
        action_map = {
            "select": "select", "fullscreen": "fullscreen",
            "query_price": "query_price",
        }

        success_count = 0
        for action, action_name in action_map.items():
            hk_str = hotkeys.get(action, DEFAULT_HOTKEYS[action])

            # 验证合法性
            if not hk_str or '+' not in hk_str:
                print(f"[热键] ✘ 跳过非法热键: {action} → '{hk_str}'", flush=True)
                self._log(f"快捷键 {action} 格式非法，使用默认值", "warn", "hotkeys")
                hk_str = DEFAULT_HOTKEYS[action]

            registered = False
            for attempt in range(3):
                try:
                    try:
                        keyboard.remove_hotkey(hk_str)
                    except Exception:
                        pass

                    hk_id = keyboard.add_hotkey(
                        hk_str,
                        lambda a=action_name: self._bridge.fired.emit(a)
                    )
                    self._registered_hotkeys[hk_str] = hk_id
                    print(f"[热键] ✓ {hk_str} 注册成功 ({action_name}) [第{attempt + 1}次]", flush=True)
                    registered = True
                    success_count += 1
                    break
                except Exception as e:
                    print(f"[热键] ⚠ {hk_str} 注册失败 (第{attempt + 1}/3次): {e}", flush=True)
                    if attempt < 2:
                        time.sleep(0.05)

            if not registered:
                self._log(f"✘ 快捷键 {hk_str} ({action_name}) 注册失败，请检查是否有其他程序占用了该快捷键",
                         "error", "hotkeys")
                # 回退到默认
                fallback = DEFAULT_HOTKEYS[action]
                try:
                    hk_id = keyboard.add_hotkey(
                        fallback,
                        lambda a=action_name: self._bridge.fired.emit(a)
                    )
                    self._registered_hotkeys[fallback] = hk_id
                    print(f"[热键] ↻ 回退默认: {fallback} ({action_name})", flush=True)
                    success_count += 1
                except Exception as e2:
                    print(f"[热键] ✘ 回退也失败: {fallback} - {e2}", flush=True)

        print(f"[热键] ===== 注册完成: {success_count}/{len(action_map)} 成功 =====", flush=True)

        # 第四步：全部失败则用默认值紧急恢复
        if success_count == 0:
            print("[热键] 🆘 所有热键注册失败！尝试用默认热键紧急恢复...", flush=True)
            self._log("所有快捷键注册失败，使用默认值紧急恢复", "error", "hotkeys")
            for action, action_name in action_map.items():
                hk_str = DEFAULT_HOTKEYS[action]
                try:
                    hk_id = keyboard.add_hotkey(
                        hk_str,
                        lambda a=action_name: self._bridge.fired.emit(a)
                    )
                    self._registered_hotkeys[hk_str] = hk_id
                    print(f"[热键] ✓ 紧急恢复: {hk_str} ({action_name})", flush=True)
                    success_count += 1
                except Exception as e:
                    print(f"[热键] ✘ 紧急恢复失败: {hk_str} - {e}", flush=True)

        # 健康检查
        self.health_check()
