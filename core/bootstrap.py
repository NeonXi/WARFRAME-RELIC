"""
启动引导模块 —— 从 main.py 拆分出来的入口函数和系统级工具。

职责：
- 单例检测 (Windows Mutex)
- 管理员权限检测
- 全局异常钩子
- main() 入口函数
"""

import sys
import os
import traceback
import atexit
from datetime import datetime


_CRASH_LOG_PATH = os.path.join(
    os.getenv('APPDATA', os.path.expanduser('~')),
    'WARFRAME-RELIC', 'crash_log.txt'
)


# ================================================================
# 异常钩子 & 退出清理
# ================================================================

def _log_exception(exc_type, exc_value, exc_tb):
    """全局异常钩子：记录未捕获异常到 crash log。"""
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
        with open(_CRASH_LOG_PATH, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"崩溃时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"类型: {exc_type.__name__}: {exc_value}\n")
            f.write(f"堆栈:\n{error_msg}\n")
            f.write(f"{'=' * 60}\n")
        print(f"\n[崩溃] 异常已记录到: {_CRASH_LOG_PATH}", flush=True)
        print(error_msg, flush=True)
    except Exception:
        print(f"\n[崩溃] 无法写入日志文件:\n{error_msg}", flush=True)

    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _on_exit():
    """进程退出时的清理记录。"""
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
        with open(_CRASH_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"--- 进程退出: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception:
        pass


def _install_seh_filter():
    """安装 Windows 结构化异常处理 (SEH) 过滤器。

    捕获 C 层面的崩溃（如 STATUS_STACK_BUFFER_OVERRUN / 0xC0000409），
    在进程终止前将异常代码和模块信息写入 crash_log。

    注意：SEH 回调中不能做任何复杂操作（如 ctypes 指针读取），
    否则可能触发递归崩溃或 OverflowError。
    """
    if sys.platform != 'win32':
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        # LPTOP_LEVEL_EXCEPTION_FILTER 类型
        EXC_FILTER = ctypes.CFUNCTYPE(
            ctypes.c_long,   # LONG return
            ctypes.c_void_p, # _EXCEPTION_POINTERS*
        )

        _original_filter = None

        def _seh_handler(exception_pointers):
            """SEH 异常回调：在 C 崩溃终止进程前记录信息。

            此函数必须极其简单——不能调用任何可能失败的 Python 代码，
            不能做 ctypes 指针操作，不能触发新的异常。
            """
            try:
                msg = (
                    f"\n{'=' * 60}\n"
                    f"** C 层面崩溃 (SEH 异常) **\n"
                    f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"异常指针: {exception_pointers}\n"
                    f"{'=' * 60}\n"
                )

                # 写入 crash log
                os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
                with open(_CRASH_LOG_PATH, 'a', encoding='utf-8', errors='replace') as f:
                    f.write(msg)

                # 也输出到 stderr（dev_runner 可捕获）
                print(msg, file=sys.stderr, flush=True)
            except Exception:
                pass

            # 传递给原始过滤器
            if _original_filter:
                try:
                    return ctypes.cast(_original_filter, EXC_FILTER)(exception_pointers)
                except Exception:
                    pass
            return 1  # EXCEPTION_EXECUTE_HANDLER

        _our_filter = EXC_FILTER(_seh_handler)
        _original_filter = kernel32.SetUnhandledExceptionFilter(_our_filter)

    except Exception as e:
        # SEH 过滤器安装失败不应阻止程序启动
        print(f"[SEH] 安装异常过滤器失败: {e}", flush=True)


def install_crash_handlers():
    """安装全局异常钩子和退出清理。"""
    # 确保日志目录存在
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG_PATH), exist_ok=True)
    except Exception:
        pass

    sys.excepthook = _log_exception
    atexit.register(_on_exit)

    # ★ 安装 Windows SEH 异常过滤器，捕获 C 层崩溃（如 0xC0000409）
    _install_seh_filter()


# ================================================================
# 管理员权限检测
# ================================================================

def _check_admin() -> bool:
    """检测是否为管理员权限。返回 True 表示已是管理员。"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return True


def _warn_not_admin() -> bool:
    """弹出管理员权限提示窗口。
    返回 True 表示用户选择继续，False 表示退出。"""
    title = "[!] 权限不足 - WARFRAME-RELIC"
    msg = (
        "未以管理员身份运行！\n\n"
        "全局热键注册需要管理员权限，否则快捷键（框选、查询等）将无法生效。\n\n"
        "请右键程序 → 「以管理员身份运行」重新启动。\n\n"
        "是否仍然继续以非管理员模式启动？\n"
        "（点击「是」继续启动，点击「否」退出）"
    )
    try:
        import ctypes
        r = ctypes.windll.user32.MessageBoxW(0, msg, title, 0x00000030 | 0x00000004)
        return r == 6  # IDYES = 6
    except Exception:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"  {msg}")
        print(f"{'=' * 60}\n", flush=True)
        return True


def ensure_admin() -> bool:
    """确保以管理员权限运行。如果不是，弹窗询问。
    返回 True 表示可以继续，False 表示应该退出。"""
    if not _check_admin():
        if not _warn_not_admin():
            return False
    return True


# ================================================================
# 单例检测
# ================================================================

def _acquire_singleton() -> bool:
    """单例互斥：通过 Windows 命名 Mutex 确保只运行一个实例。"""
    try:
        import ctypes

        _MUTEX_NAME = "Global\\WARFRAME-RELIC-Singleton-{A8F3C2D1-4E5B-4a6f-8D3C-1B2A3F4E5D6C}"
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        if handle == 0:
            return True
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        return True
    except Exception:
        return True


def _warn_already_running():
    """弹出"已有实例运行"提示窗口。"""
    title = "[!] 程序已在运行 - WARFRAME-RELIC"
    msg = (
        "WARFRAME-RELIC 已经在运行中，不能同时启动多个实例。\n\n"
        "请在系统托盘中查找程序图标，或检查任务管理器。"
    )
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x00000030)
    except Exception:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"  {msg}")
        print(f"{'=' * 60}\n", flush=True)


def ensure_singleton() -> bool:
    """确保单例运行。如果不是第一个实例，弹窗提示并返回 False。"""
    if not _acquire_singleton():
        _warn_already_running()
        return False
    return True


# ================================================================
# 主入口
# ================================================================

def main():
    """程序主入口。"""
    from PyQt6.QtWidgets import QApplication
    from main import AppCore

    # 单例检测
    if not ensure_singleton():
        sys.exit(1)

    # 管理员权限检测
    if not ensure_admin():
        sys.exit(1)

    # 安装异常钩子
    install_crash_handlers()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # 全局样式（对话框等继承）
    from core.stylesheet import build_stylesheet
    app.setStyleSheet(build_stylesheet())

    core = AppCore(app)
    core.run()
