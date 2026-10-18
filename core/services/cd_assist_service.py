"""
[L-Service] core.services.cd_assist_service — CD 辅助显示 业务逻辑

依赖: PySide6.QtCore (Signal / QTimer 驱动倒计时)
       纯逻辑层,不持有 widget,不读 JSON(用户要求:会话级,不持久化)
禁止: PySide6.QtWidgets / QtGui / 直接调 widget

职责:
  - 维护 4 个技能的秒数(内存 dict)
  - 维护"启用屏幕"集合
  - 维护总开关
  - 接收热键触发的 start_skill(idx) 调用
  - 内部 QTimer 推进倒计时,发出 countdown_tick 信号

设计要点:
  - 纯单例(CdAssistService.instance())
  - 倒计时用 QElapsedTimer 记录 start time,避免累加漂移
  - 倒计时归零时自动从活动集合移除,UI 端根据 countdown_tick dict 决定是否显示
  - duration=0 的技能被触发时仍会"闪一下"(显示"·"),让用户知道按键生效
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, QTimer, QElapsedTimer

from core.services.cd_debug_log import log as _dbg

# 4 个技能的固定数量
SKILL_COUNT = 4
# 倒计时刷新频率(ms) —— 100ms 让秒数变化看起来平滑
TICK_MS = 100
# duration = 0 的技能被触发时,"·" 状态的持续时间(ms)
ZERO_DURATION_FLASH_MS = 500


@dataclass
class SkillState:
    """单个技能的完整状态(配置 + 运行 + 提醒 + flash)。

    字段分组:
      配置(由 set_skill_duration / set_skill_reminder 改):
        duration   持续秒数(0 = 不参与倒计时,触发时只显示"·")
        reminder   提醒阈值(0 = 关闭)
      运行(由 start_skill / _on_tick 改):
        remaining      当前剩余秒数
        start_ms       起点 (QElapsedTimer.elapsed())
        active         是否在倒计时
        in_reminder    是否处于提醒态(remaining <= reminder)
        zero_until_ms  duration=0 触发时,"·" 闪烁结束时刻(0 = 不在 flash)

    设计: 把 7 个并列 list 合并到一个 SkillState 对象,
    让 _on_tick 循环里的索引操作集中到一个对象上,不易漏改。
    """
    # 配置
    duration: float = 0.0
    reminder: float = 0.0
    # 运行
    remaining: float = 0.0
    start_ms: int = 0
    active: bool = False
    in_reminder: bool = False
    zero_until_ms: int = 0
# 显示位置偏移持久化文件(打包/开发环境自适应,见 core.paths)
from core.paths import ensure_user_file as _ensure_user_file
_POS_FILE = _ensure_user_file("cd_assist_pos.json")
# 位置偏移范围(±2000px 覆盖所有合理屏幕尺寸)
POS_OFFSET_MIN = -2000
POS_OFFSET_MAX = 2000
# 技能持续秒数范围(0 = 不参与倒计时,按下仅闪一下 ·)
SKILL_DURATION_MIN = 0.0
SKILL_DURATION_MAX = 300.0
# 技能提醒阈值范围(0 = 关闭,快到时间闪烁)
SKILL_REMINDER_MIN = 0.0
SKILL_REMINDER_MAX = 60.0
# spinbox 步长
SKILL_STEP = 0.5


class CdAssistService(QObject):
    """CD 辅助显示服务(单例)。

    对外信号:
      countdown_tick(dict[int, float])  每个 tick 发送当前各技能的剩余秒数
                                          (skill_index -> remaining_seconds)
                                          0 表示该技能未在倒计时
      state_changed()                    任何"非 tick"状态变化时(duration / 屏 / 总开关)
      enabled_changed(bool)              总开关变化
      enabled_screens_changed(list[int]) 启用屏幕集合变化

    公开 API:
      set_skill_duration(idx, sec)   设置技能 N 的秒数
      set_enabled(bool)              总开关
      set_enabled_screens(indices)   启用屏幕(列表)
      start_skill(idx)               手动/热键触发技能 N 的倒计时
      get_state()                    取全部状态(dict)
      is_enabled()                   总开关
      get_enabled_screens()          启用屏幕列表
      get_skill_durations()          4 个技能的秒数(list[4])
    """

    countdown_tick = Signal(dict)
    state_changed = Signal()
    enabled_changed = Signal(bool)
    enabled_screens_changed = Signal(list)

    _instance: "CdAssistService | None" = None

    @classmethod
    def instance(cls) -> "CdAssistService":
        """单例访问(惰性创建)。"""
        if cls._instance is None:
            cls._instance = CdAssistService()
        return cls._instance

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # ── 技能状态(SkillState 列表,每个元素是一组完整状态) ──
        # 替代之前的 7 个并列 list(durations / reminders / remaining / starts /
        # active / in_reminder / zero_until),集中管理减少漏改。
        self._skills: list[SkillState] = [SkillState() for _ in range(SKILL_COUNT)]

        # ── 屏 + 总开关 ──
        # 启用屏幕集合(默认全选,on_enter 重新设置)
        self._enabled_screens: set[int] = set()
        # 总开关:开启时按键才生效
        # 会话级不持久化 → 每次启动软件默认关闭，用户当次会话手动开启
        self._enabled: bool = False

        # ── 倒计时 timer ──
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._elapsed = QElapsedTimer()

        # ── 低层键盘钩子(裸键 1/2/3/4) ──
        # 用 WH_KEYBOARD_LL 默认放行,游戏/系统照常接收 → 不会抢键
        self._hook = None
        self._hook_poll_timer: QTimer | None = None
        self._hook_bound: bool = False

        # ── View(由 app_shell 在启动时注入,绕过页面) ──
        # view 是 CdAssistManager 这样的 QObject,有 show(payload)/hide() 接口
        # 装上后 service 自己 dispatch tick,即使用户没进过 cd_assist 页面也能用
        self._view = None
        self._view_bound: bool = False

        # ── 显示位置偏移(相对屏幕中心,持久化到 data/cd_assist_pos.json) ──
        # (0, 0) = 屏幕中心;(+100, 0) = 向右 100px;(0, -50) = 向上 50px
        self._x_offset: int = 0
        self._y_offset: int = 0
        self._load_position_from_disk()

    # ════════════════════════════════════
    #  公开 API
    # ════════════════════════════════════

    def set_skill_duration(self, idx: int, sec: float) -> None:
        """设置技能 N 的秒数(0 = 不参与倒计时,触发时只显示"·")。"""
        if not (0 <= idx < SKILL_COUNT):
            return
        # 限制范围:0-300 秒
        sec = max(SKILL_DURATION_MIN, min(SKILL_DURATION_MAX, float(sec)))
        s = self._skills[idx]
        if abs(s.duration - sec) < 1e-6:
            return
        s.duration = sec
        # 如果该技能正在倒计时,新 duration 立即生效
        if s.active:
            s.remaining = sec
            s.start_ms = self._elapsed.elapsed()
        self.state_changed.emit()

    def set_skill_reminder(self, idx: int, sec: float) -> None:
        """设置技能 N 的提醒阈值(秒)。0 = 不提醒。

        当倒计时剩余秒数 <= 提醒阈值时,该技能进入"提醒态":
          - overlay 数字变橙色 (semantic.warning)
          - 数字以 500ms 间隔闪烁 (opacity 1.0 ↔ 0.3)
        """
        if not (0 <= idx < SKILL_COUNT):
            return
        # 限制范围:0-60 秒(提醒一般在 0-10s 区间,设上限防误填)
        sec = max(SKILL_REMINDER_MIN, min(SKILL_REMINDER_MAX, float(sec)))
        if abs(self._skills[idx].reminder - sec) < 1e-6:
            return
        self._skills[idx].reminder = sec
        _dbg("service", f"set_skill_reminder({idx}): 提醒阈值={sec}s")
        self.state_changed.emit()

    def set_enabled(self, on: bool) -> None:
        """总开关:关闭后按键不再触发,overlay 立即隐藏。"""
        on = bool(on)
        if self._enabled == on:
            return
        self._enabled = on
        # 关闭时:清空所有倒计时 + 发 tick(duration 全 0)+ 通知 overlay 隐藏
        if not on:
            for s in self._skills:
                s.active = False
                s.remaining = 0.0
                s.zero_until_ms = 0
            self._timer.stop()
            self._emit_tick(zero=True)
        self.enabled_changed.emit(on)
        self.state_changed.emit()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled_screens(self, indices: list[int]) -> None:
        """设置启用屏幕集合(空集 = 任何屏都不显示,但 service 仍工作)。"""
        new_set = set(int(i) for i in indices)
        if new_set == self._enabled_screens:
            return
        self._enabled_screens = new_set
        self.enabled_screens_changed.emit(sorted(new_set))
        self.state_changed.emit()

    def get_enabled_screens(self) -> list[int]:
        return sorted(self._enabled_screens)

    def set_position_offset(self, x: int, y: int) -> None:
        """设置 overlay 显示位置偏移(相对屏幕中心,px)。

        立即生效:通知 view(manager)重设所有 overlay 位置。
        立即持久化:写到 data/cd_assist_pos.json,防止应用崩溃丢数据。
        """
        # 钳制到合理范围
        x = max(POS_OFFSET_MIN, min(POS_OFFSET_MAX, int(x)))
        y = max(POS_OFFSET_MIN, min(POS_OFFSET_MAX, int(y)))
        if self._x_offset == x and self._y_offset == y:
            return
        self._x_offset = x
        self._y_offset = y
        _dbg("service", f"set_position_offset: x={x}, y={y}")
        # 通知 view(manager)重设所有 overlay 位置
        if self._view is not None:
            try:
                self._view.set_position_offset(x, y)
            except Exception as e:
                _dbg("service", f"view.set_position_offset 异常: {e}", level="ERR")
        # 持久化(防崩溃丢失)
        self._save_position_to_disk()
        self.state_changed.emit()

    def get_position_offset(self) -> tuple[int, int]:
        """取当前显示位置偏移。"""
        return (self._x_offset, self._y_offset)

    def _load_position_from_disk(self) -> None:
        """启动时从 JSON 加载位置偏移。失败用默认 (0, 0)。"""
        try:
            if not _POS_FILE.exists():
                _dbg("service", f"_load_position: 文件不存在 {_POS_FILE},用默认 (0, 0)", level="WARN")
                return
            with open(_POS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            x = int(data.get("x_offset", 0))
            y = int(data.get("y_offset", 0))
            x = max(POS_OFFSET_MIN, min(POS_OFFSET_MAX, x))
            y = max(POS_OFFSET_MIN, min(POS_OFFSET_MAX, y))
            self._x_offset = x
            self._y_offset = y
            _dbg("service", f"_load_position: 从磁盘加载 x={x}, y={y}")
        except Exception as e:
            _dbg("service", f"_load_position 失败(用默认): {e}", level="WARN")

    def _save_position_to_disk(self) -> None:
        """把当前偏移写到 JSON。失败仅记日志,不抛异常。"""
        try:
            _POS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"x_offset": self._x_offset, "y_offset": self._y_offset}
            with open(_POS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _dbg("service", f"_save_position 失败: {e}", level="WARN")

    def start_skill(self, idx: int) -> None:
        """触发技能 N 的倒计时(按键触发 / 测试用)。

        行为: 每次按键都从头开始倒计时(重置 remaining 到完整 duration)
          - 按 1 → 10.0
          - 再按 1 → 10.0(重置,不走下去)
          - 适合"按一次技能 = 重新触发 CD"的玩法
        - duration > 0: 启动/重置倒计时
        - duration = 0: "·" 闪一下 ZERO_DURATION_FLASH_MS
        - 总开关关闭: 直接返回
        """
        if not self._enabled:
            _dbg("service", f"start_skill({idx}): 总开关关闭,直接返回", level="WARN")
            return
        if not (0 <= idx < SKILL_COUNT):
            _dbg("service", f"start_skill({idx}): 越界,直接返回", level="WARN")
            return
        s = self._skills[idx]
        dur = s.duration
        was_active = s.active
        prev_remaining = s.remaining
        _dbg("service",
             f"start_skill({idx}): dur={dur}s, "
             f"{'重置已有倒计时 (之前 remaining=' + f'{prev_remaining:.1f}s)' if was_active else '启动新倒计时'}")
        if not self._elapsed.isValid():
            self._elapsed.start()
        now_ms = self._elapsed.elapsed()
        if dur <= 0:
            # 不参与倒计时,只闪一下
            s.active = False
            s.remaining = 0.0
            s.zero_until_ms = now_ms + ZERO_DURATION_FLASH_MS
        else:
            # ★ 每次按键都重置: 重新设 remaining=dur, 起点=now
            s.active = True
            s.remaining = dur
            s.start_ms = now_ms
            s.zero_until_ms = 0
        # 启动 timer(如果还没启动)
        if not self._timer.isActive():
            self._timer.start()
        # 立刻发一次 tick,让 UI 立即刷新
        self._emit_tick()

    def get_state(self) -> dict:
        """取全部状态(供 UI 同步)。"""
        return {
            "enabled": self._enabled,
            "durations": [s.duration for s in self._skills],
            "reminders": [s.reminder for s in self._skills],
            "remaining": dict(self._current_remaining_dict()),
            "enabled_screens": sorted(self._enabled_screens),
            "x_offset": self._x_offset,
            "y_offset": self._y_offset,
        }

    def get_skill_durations(self) -> list[float]:
        return [s.duration for s in self._skills]

    def get_skill_reminders(self) -> list[float]:
        return [s.reminder for s in self._skills]

    def get_current_remaining(self, idx: int) -> float:
        """单个技能的当前剩余秒数(0 = 不在倒计时)。"""
        return self._skills[idx].remaining if 0 <= idx < SKILL_COUNT else 0.0

    def is_any_active(self) -> bool:
        """是否有任何技能正在倒计时(用于 UI 决定是否显示 overlay)。"""
        if not self._enabled:
            return False
        if any(s.active for s in self._skills):
            return True
        now_ms = self._elapsed.elapsed() if self._elapsed.isValid() else 0
        return any(s.zero_until_ms > now_ms for s in self._skills)

    # ════════════════════════════════════
    #  内部 - timer 推进
    # ════════════════════════════════════

    def _on_tick(self) -> None:
        """QTimer 回调:推进各技能倒计时,归零后停止 timer。"""
        if not self._elapsed.isValid():
            self._elapsed.start()
        now_ms = self._elapsed.elapsed()

        any_active = False
        for s in self._skills:
            if s.active:
                # 用 elapsed 算 remaining,避免累加漂移
                elapsed_sec = (now_ms - s.start_ms) / 1000.0
                s.remaining = max(0.0, s.duration - elapsed_sec)
                # ★ 计算提醒态: remaining > 0 且 remaining <= reminder
                if s.reminder > 0 and s.remaining > 0 and s.remaining <= s.reminder:
                    s.in_reminder = True
                else:
                    s.in_reminder = False
                if s.remaining <= 0.0:
                    # 倒计时归零,关闭 + 清提醒态
                    s.active = False
                    s.remaining = 0.0
                    s.in_reminder = False
                else:
                    any_active = True
            # 检查 zero-flash 是否到期
            if s.zero_until_ms > 0 and now_ms >= s.zero_until_ms:
                s.zero_until_ms = 0

        # 没有任何倒计时 + 没有 flash 时,停 timer
        still_flashing = any(s.zero_until_ms > now_ms for s in self._skills)
        if not any_active and not still_flashing:
            self._timer.stop()

        self._emit_tick()

    def _current_remaining_dict(self) -> dict:
        """返回 {idx: remaining_sec} —— 归零或非活动的技能不包含(由 UI 决定显示)。"""
        return {i: s.remaining for i, s in enumerate(self._skills) if s.active}

    def _emit_tick(self, *, zero: bool = False) -> None:
        """发 countdown_tick 信号(payload 同时含 remaining + 提醒态)。

        payload 格式: {"0": {"r": 4.5, "m": True}, "1": {"r": 7.0, "m": False}, ...}
          - r (float): 剩余秒数
          - m (bool):  是否处于"提醒态"(remaining <= reminder)

        参数:
          zero=True  → 强制发空 dict({}),让 UI 立即清空(总开关关闭时用)
          zero=False → 按当前 skills 状态构造 payload(默认)

        注意: PySide6 Signal.emit(dict) 要求 key 是 str(否则触发 C++ 转换失败)。
        """
        if zero:
            self.countdown_tick.emit({})
            return
        now_ms = self._elapsed.elapsed() if self._elapsed.isValid() else 0
        payload: dict = {}
        for i, s in enumerate(self._skills):
            if s.active:
                payload[str(i)] = {
                    "r": s.remaining,
                    "m": s.in_reminder,
                }
            elif s.zero_until_ms > now_ms:
                payload[str(i)] = {"r": 0.0, "m": False}  # 0 = "·" 状态
        self.countdown_tick.emit(payload)

    # ════════════════════════════════════
    #  低层键盘钩子(裸键 1/2/3/4)
    # ════════════════════════════════════

    def bind_to_app(self) -> bool:
        """启动低层键盘钩子,绑定 1/2/3/4 裸键。

        必须在 QApplication 已创建的主线程调用。
        返回 True 表示成功安装钩子。

        实现:
          - 启动 LowLevelHotkeyHook(WH_KEYBOARD_LL,专属线程装钩子+跑消息泵)
          - 启动 50ms QTimer,在主线程 drain 钩子 queue
          - drain 出的按键 → start_skill
        """
        _dbg("service", "bind_to_app() 被调用")
        if self._hook_bound:
            _dbg("service", "钩子已绑定,跳过")
            return True
        try:
            from core.services.cd_hotkey_hook import LowLevelHotkeyHook
            self._hook = LowLevelHotkeyHook()
            _dbg("service", "LowLevelHotkeyHook 实例已创建,准备 start()")
            ok = self._hook.start()
            _dbg("service", f"hook.start() 返回: {ok}")
            if not ok:
                self._hook = None
                _dbg("service", "钩子启动失败", level="ERR")
                print("[CdAssistService] 钩子启动失败,按键 1/2/3/4 不会触发倒计时",
                      flush=True)
                return False
            # 主线程 50ms 一次轮询钩子 queue,把待处理按键转给 start_skill
            self._hook_poll_timer = QTimer(self)
            self._hook_poll_timer.setInterval(50)
            self._hook_poll_timer.timeout.connect(self._drain_hook)
            self._hook_poll_timer.start()
            self._hook_bound = True
            _dbg("service", f"钩子绑定完成,50ms 轮询已启动 (enabled={self._enabled}, durations={[s.duration for s in self._skills]})", level="OK")
            print("[CdAssistService] 钩子绑定完成,开始监听 1/2/3/4 键", flush=True)
            # 按当前启用状态初始化 vk→skill 映射（禁用的技能不进映射，钩子直接忽略其按键）
            self.rebuild_hotkey_mapping()
            return True
        except Exception as e:
            _dbg("service", f"启动低层键盘钩子失败: {e}", level="ERR")
            print(f"[CdAssistService] 启动低层键盘钩子失败: {e}", flush=True)
            self._hook = None
            return False

    def rebuild_hotkey_mapping(self) -> None:
        """根据各技能的启用状态重建钩子 vk→skill 映射。

        被禁用的技能从映射中移除，低层钩子不会再把对应按键放入队列，
        从而完全不触发该技能的倒计时（同时不影响游戏内 1/2/3/4 的正常输入）。

        钩子未绑定时仅记录，不报错（bind_to_app 会在启动后补调一次）。
        """
        try:
            from core.hotkey_config import load_hotkey_enabled
            enabled = load_hotkey_enabled()
        except Exception as e:
            _dbg("service", f"读取快捷键启用状态失败: {e}", level="WARN")
            enabled = {}

        actions = ("cd_1", "cd_2", "cd_3", "cd_4")
        mapping: dict[int, int] = {}
        for i, action in enumerate(actions):
            if enabled.get(action, True):
                mapping[0x31 + i] = i  # '1'..'4' → skill 0..3

        if self._hook is not None:
            self._hook.set_vk_to_skill(mapping)
            _dbg("service", f"钩子映射已重建: {mapping}")
        else:
            _dbg("service", "钩子未绑定，跳过映射重建", level="WARN")

    def shutdown(self) -> None:
        """停止钩子 + 清理(应用退出时调用)。"""
        if self._hook_poll_timer is not None:
            self._hook_poll_timer.stop()
            self._hook_poll_timer = None
        if self._hook is not None:
            try:
                self._hook.stop()
            except Exception as e:
                _dbg("service", f"_hook.stop() 异常: {e}", level="ERR")
            self._hook = None
        self._hook_bound = False

    def _drain_hook(self) -> None:
        """主线程 50ms 一次:从钩子 queue 取出待处理按键,启动对应技能。"""
        if self._hook is None:
            return
        # 即使总开关关闭,也要把按键消化掉,避免 queue 积压
        items = self._hook.drain()
        if items:
            _dbg("service", f"drain_hook: 从 queue 取出 {len(items)} 个按键: {items}")
        for idx in items:
            _dbg("service", f"→ start_skill({idx}) (enabled={self._enabled}, dur={self._skills[idx].duration})")
            self.start_skill(idx)

    # ══════════════════════════════════
    #  View 注入(让 service 直接驱动 manager,不依赖页面)
    # ══════════════════════════════════

    def set_view(self, view) -> None:
        """注入 view(由 CdAssistManager 提供),让 service 直接派发 tick。

        设计动机: 用户按 1/2/3/4 时,service 会 emit countdown_tick。
        如果 view 还没绑(用户没进过 cd_assist 页面),tick 无人接收 → 倒计时不显示。
        此方法在 app_shell 启动时调用,把 view 提前接好 → 永远有显示出口。

        view 接口:
          - show(payload: dict)   有活动时调用
          - hide()                无活动时调用
          - clear_cells()         总开关关闭时调用
        """
        if self._view is view:
            return
        # 断开旧的
        if self._view is not None:
            try:
                self.countdown_tick.disconnect(self._dispatch_to_view)
            except Exception as e:
                _dbg("service", f"断开旧 view 失败: {e}", level="ERR")
        self._view = view
        if self._view is not None:
            try:
                self.countdown_tick.connect(self._dispatch_to_view)
                self._view_bound = True
                # ★ 关键: 绑 view 时立即把当前偏移同步过去
                # (service __init__ 从磁盘加载偏移时,manager 还没创建)
                try:
                    self._view.set_position_offset(self._x_offset, self._y_offset)
                except Exception as e:
                    _dbg("service", f"同步 position_offset 给 view 失败: {e}", level="ERR")
                _dbg("service", f"set_view: view={type(view).__name__} 已注入, countdown_tick 直驱", level="OK")
                print("[CdAssistService] view 已注入, countdown_tick 直驱 manager",
                      flush=True)
            except Exception as e:
                _dbg("service", f"view 连接失败: {e}", level="ERR")
                print(f"[CdAssistService] view 连接失败: {e}", flush=True)

    def _dispatch_to_view(self, payload: dict) -> None:
        """内部:把 tick 派发给 view(由 view 决定 show/hide/update)。"""
        if self._view is None:
            return
        if not self._enabled:
            try:
                self._view.clear_cells()
            except Exception as e:
                _dbg("service", f"view.clear_cells 异常: {e}", level="ERR")
            return
        try:
            if not payload:
                self._view.hide()
            else:
                self._view.show(payload)
        except Exception as e:
            print(f"[CdAssistService] view 派发异常: {e}", flush=True)
