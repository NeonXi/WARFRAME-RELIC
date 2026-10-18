"""
[L-Service] core.services.cd_hotkey_hook — 低层键盘钩子(LowLevelHotkeyHook)

依赖: ctypes (Win32 API), PySide6.QtCore (Signal/QObject), threading
禁止: PySide6.QtWidgets, QtGui

职责:
  - 安装 Windows WH_KEYBOARD_LL 钩子
  - 在专属后台线程里**装钩子 + 跑消息泵**(必须在同一线程,OS 才能派发回调)
  - 监听配置的 vk_code,触发时放入 thread-safe queue
  - **永远 CallNextHookEx 放行**(不拦截)→ 游戏/系统/其它应用照常接收

为什么不直接用 hotkey_manager 的 RegisterHotKey:
  - RegisterHotKey 是 OS 级"独占"热键,被注册后整个系统都不能再响应该键
  - 裸键 1/2/3/4 被游戏/系统用作核心输入,一旦注册会全游戏抢键
  - WH_KEYBOARD_LL 是"观察者"模式,默认放行,只用于通知
    → 既能触发 CD 倒计时,又不影响游戏/系统的 1/2/3/4 输入

线程模型:
  - **关键**: 钩子安装 + 消息泵必须在同一线程(OS 派发回调的规则)
  - 钩子回调在 OS 钩子线程跑(非主线程,非 Qt 线程)
  - 回调内**不**直接调任何 PySide6 对象的 method(线程不安全)
  - 回调内仅 queue.put(skill_idx) —— thread-safe 的最小操作
  - 主线程 CdAssistService 用 50ms QTimer drain queue,调 start_skill

用法::
    hook = LowLevelHotkeyHook({0x31: 0, 0x32: 1, 0x33: 2, 0x34: 3})
    hook.start()
    # ... 主线程定时 hook.drain() 获取待处理按键 ...
    hook.stop()
"""

from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes
from typing import Dict

from PySide6.QtCore import QObject, Signal

from core.logging_utils import log as _dbg


# ── Win32 常量 ──
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
HC_ACTION = 0

# 默认监听 1/2/3/4 (主键盘区数字键)
DEFAULT_VK_TO_SKILL: Dict[int, int] = {
    0x31: 0,  # '1' → 技能 0
    0x32: 1,  # '2' → 技能 1
    0x33: 2,  # '3' → 技能 2
    0x34: 3,  # '4' → 技能 3
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Windows 低层键盘钩子数据结构。"""
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


# 钩子回调类型: LRESULT CALLBACK(int nCode, WPARAM wParam, LPARAM lParam)
# ctypes 等价: c_int, c_void_p(WPARAM 是 UINT_PTR), POINTER(KBDLLHOOKSTRUCT)
LowLevelProc = ctypes.WINFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,        # nCode
    wintypes.WPARAM,     # wParam (消息类型)
    wintypes.LPARAM,     # lParam (指向 KBDLLHOOKSTRUCT)
)


class LowLevelHotkeyHook(QObject):
    """WH_KEYBOARD_LL 钩子(低层键盘监听)。"""

    triggered = Signal(int)  # 每次按键触发,emit skill_index (主线程安全)

    # 钩子状态枚举(用哨兵值替代 None,避免与 0 hook_id 冲突)
    _S_INIT = -1
    _S_FAIL = 0

    def __init__(
        self,
        vk_to_skill: Dict[int, int] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        # vk_code (Win32 Virtual-Key code) -> skill index (0..3)
        self._vk_to_skill: Dict[int, int] = dict(
            vk_to_skill if vk_to_skill is not None else DEFAULT_VK_TO_SKILL
        )
        # 钩子句柄(由专属线程装;None=未启动, -1=启动中, 0=失败, 正整数=成功)
        self._hook_id: int | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._queue: queue.Queue[int] = queue.Queue()
        # 钩子回调函数引用(必须保持,否则会被 GC,导致回调里 crash)
        self._proc_ref: LowLevelProc | None = None
        # 调试用:统计收到的按键(可被外部读取)
        self._key_count: int = 0

    # ══════════════════════════════════
    #  公开 API
    # ══════════════════════════════════

    def start(self) -> bool:
        """装钩子并启动消息泵(都在专属线程里跑)。返回 True 表示成功。

        关键: 钩子安装和消息泵必须**在同一个线程**,Windows OS
        才会把 hook 回调派发到这个线程。如果装在主线程但跑消息泵
        在子线程,回调会丢失。
        """
        if self._hook_id is not None and self._hook_id > 0:
            return True  # 已启动
        if self._hook_id == self._S_FAIL:
            return False  # 上次启动失败,不要重试

        # 标记启动中
        self._hook_id = self._S_INIT
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main, name="CDHotkeyHook", daemon=True
        )
        self._thread.start()

        # 等待 hook_id 被设置(成功=正整数,失败=0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self._hook_id is not None and self._hook_id != self._S_INIT:
                break
            time.sleep(0.01)
        return self._hook_id is not None and self._hook_id > 0

    def stop(self) -> None:
        """停止钩子(等线程退出 + 兜底卸载)。"""
        if self._hook_id is None and self._thread is None:
            return
        # 通知消息泵线程退出
        self._stop_event.set()
        # 等线程结束(最多 1 秒)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        # 兜底:如果线程未正常清理钩子,再调一次 UnhookWindowsHookEx
        if self._hook_id is not None and self._hook_id > 0:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._hook_id)
            except Exception:
                pass
        self._hook_id = None
        self._proc_ref = None

    def is_running(self) -> bool:
        """钩子是否在运行。"""
        return self._hook_id is not None and self._hook_id > 0

    def set_vk_to_skill(self, mapping: Dict[int, int]) -> None:
        """动态更新 vk -> skill 映射(下一次按键生效)。"""
        self._vk_to_skill = dict(mapping)

    def drain(self) -> list[int]:
        """从 queue 里取出所有待处理的 skill 索引(非阻塞)。由主线程 QTimer 周期调用。"""
        out: list[int] = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out

    def key_count(self) -> int:
        """调试用:累计收到的按键数。"""
        return self._key_count

    # ══════════════════════════════════
    #  内部 - 专属线程(装钩子 + 消息泵)
    # ══════════════════════════════════

    def _thread_main(self) -> None:
        """专属线程入口:装钩子 + 跑消息泵(都在本线程,OS 才能派发回调)。

        关键:
          - SetWindowsHookExW 在**本线程**调用 → OS 知道回调要派发到这里
          - 本线程跑 PeekMessage 消息循环 → OS 通过 PeekMessage 派发 hook 回调
          - 钩子回调里只做最小操作(queue.put),不碰 PySide6 对象

        ⚠ hMod 参数必须是 NULL(0):
          传 EXE 的 GetModuleHandleW(None) 会让 OS 把它当 DLL 去找,
          找不到就 err=126 (ERROR_MOD_NOT_FOUND)。
          正确做法: hMod=0,表示"回调在调用进程内"(EXE 内,虽然不是 DLL,
          但 OS 会从当前进程找到回调函数地址)。
        """
        user32 = ctypes.windll.user32
        _dbg("hook", f"专属线程启动 (tid={threading.get_ident()})")

        # 钩子回调(在钩子线程跑,只放 queue,不调 PySide6 对象)
        def low_level_proc(nCode, wParam, lParam):
            try:
                if nCode == HC_ACTION and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kbd = ctypes.cast(
                        lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)
                    ).contents
                    if kbd.vkCode in self._vk_to_skill:
                        idx = self._vk_to_skill[kbd.vkCode]
                        self._key_count += 1
                        # 放进 queue(线程安全),让主线程 drain 后再 emit
                        self._queue.put(idx)
                        _dbg("hook", f"收到 vk=0x{kbd.vkCode:X} → 技能 idx={idx} (count={self._key_count})", level="OK")
                    # 其他按键: 静默忽略(WH_KEYBOARD_LL 必收所有键盘事件,
                    # 回调里只关心 1/2/3/4,其余直接放行 → 不打日志,免得刷屏)
                # **永远 CallNextHookEx 放行**(不拦截游戏/系统/其它应用)
                return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)
            except Exception as e:
                # 钩子回调里任何异常都安全地放行,绝不 crash OS 钩子链
                _dbg("hook", f"回调异常: {e}", level="ERR")
                return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

        # 1. 在本线程装钩子
        # ⚠ hMod 必须传 0(NULL): 回调在调用进程内,OS 从当前进程找回调地址
        self._proc_ref = LowLevelProc(low_level_proc)  # 保持引用,防 GC
        hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc_ref, 0, 0  # hMod=NULL, dwThreadId=0(全局)
        )
        if not hook_id:
            err = ctypes.get_last_error()
            _dbg("hook", f"SetWindowsHookExW 失败 err={err}", level="ERR")
            print(
                f"[CDHotkeyHook] SetWindowsHookExW 失败, err={err} "
                f"(可能需要管理员权限或被其它 hook 占用)",
                flush=True,
            )
            self._hook_id = self._S_FAIL
            self._proc_ref = None
            return

        # 2. 标记成功
        self._hook_id = hook_id
        _dbg("hook", f"钩子安装成功 hook_id={hook_id} (hMod=NULL 全局钩子)", level="OK")
        print(
            f"[CDHotkeyHook] 钩子已装, hook_id={hook_id} "
            f"(专属线程={threading.current_thread().name})",
            flush=True,
        )

        # 3. 跑消息泵(PeekMessage 阻塞到有消息,无消息时 wait 5ms)
        msg = wintypes.MSG()
        _dbg("hook", "进入 PeekMessage 消息循环")
        try:
            while not self._stop_event.is_set():
                has_msg = user32.PeekMessageW(
                    ctypes.byref(msg), 0, 0, 0, 0x0001  # PM_REMOVE
                )
                if has_msg:
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    # 没消息,睡 5ms 让出 CPU(stop_event 是 1ms 粒度)
                    self._stop_event.wait(0.005)
                # 注: 不打心跳日志(每秒 1 条无意义,会污染 CMD)
                #   钩子线程是否活着可以用 hook.is_running() 查
        finally:
            # 4. 退出前:卸钩子(线程上下文里卸载)
            if self._hook_id and self._hook_id > 0:
                try:
                    user32.UnhookWindowsHookEx(self._hook_id)
                except Exception:
                    pass
                self._hook_id = None
                self._proc_ref = None
                _dbg("hook", "钩子已卸(消息泵退出)", level="OK")
                print("[CDHotkeyHook] 钩子已卸", flush=True)
