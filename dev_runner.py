"""
开发运行器：文件变更监听 + 自动重启 + 崩溃日志记录。

用法：
    python dev_runner.py           # 监听 .py 变更，自动重启
    python dev_runner.py --once    # 只启动一次，不监听
    python dev_runner.py --stdout  # 启动一次，捕获 stdout/stderr 到控制台
"""
import subprocess
import sys
import os
import time
import traceback
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CRASH_LOG = os.path.join(PROJECT_DIR, 'crash_log.txt')

# 监听的扩展名
WATCH_EXTS = {'.py', '.qss'}


def timestamp() -> str:
    return datetime.now().strftime('%H:%M:%S')


def log(msg: str):
    print(f"[{timestamp()}] {msg}")


def write_crash_log(returncode: int, stderr: str = ''):
    """将崩溃信息写入 crash_log.txt"""
    try:
        with open(CRASH_LOG, 'a', encoding='utf-8') as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"崩溃时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"退出码: {returncode}\n")
            if stderr:
                f.write(f"stderr:\n{stderr}\n")
            f.write(f"{'=' * 60}\n")
    except Exception:
        pass


def get_mtimes():
    """扫描项目文件的最后修改时间（仅 WATCH_EXTS）。"""
    mtimes = {}
    for root, dirs, files in os.walk(PROJECT_DIR):
        # 跳过不需要监听的目录
        dirs[:] = [d for d in dirs if d not in (
            'venv', '.git', '__pycache__', '.codebuddy', 'dist', 'build'
        )]
        for f in files:
            _, ext = os.path.splitext(f)
            if ext not in WATCH_EXTS:
                continue
            path = os.path.join(root, f)
            try:
                mtimes[path] = os.path.getmtime(path)
            except OSError:
                pass
    return mtimes


def _find_python() -> str:
    """找到正确的 Python 解释器路径。

    优先级：
    1. 项目目录下的 venv/Scripts/python.exe
    2. VIRTUAL_ENV 环境变量
    3. sys.executable（回退）
    """
    # 1. 项目目录下的 venv
    for venv_name in ('venv', '.venv'):
        path = os.path.join(PROJECT_DIR, venv_name, 'Scripts', 'python.exe')
        if os.path.exists(path):
            return path

    # 2. VIRTUAL_ENV 环境变量
    venv_home = os.environ.get('VIRTUAL_ENV')
    if venv_home:
        for name in ('python.exe', 'python'):
            path = os.path.join(venv_home, 'Scripts', name)
            if os.path.exists(path):
                return path

    # 3. 回退
    return sys.executable


def start_process(capture_output: bool = False) -> subprocess.Popen:
    """启动 main.py 子进程（继承当前环境变量，确保 venv 可用）。
    
    watch 模式下始终捕获 stderr 用于崩溃日志记录。
    """
    kwargs = {'env': os.environ.copy()}
    if capture_output:
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.STDOUT
        kwargs['text'] = True
    else:
        # watch 模式：只捕获 stderr，stdout 仍输出到控制台
        kwargs['stderr'] = subprocess.PIPE
        kwargs['text'] = True
    return subprocess.Popen([_find_python(), 'main.py'], **kwargs)


def kill_process(proc: subprocess.Popen):
    """安全终止子进程。"""
    if proc is None:
        return
    try:
        proc.kill()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log("Process not responding, force kill...")
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    except Exception:
        pass


def run_once(capture_output: bool = False):
    """只启动一次，不退出的手动重启循环（Ctrl+C 退出）。"""
    log(">> Starting main.py (once mode)...")
    proc = start_process(capture_output=capture_output)

    try:
        if capture_output and proc.stdout:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
        else:
            proc.wait()
    except KeyboardInterrupt:
        log("Interrupted, exiting...")
        kill_process(proc)
        return

    returncode = proc.poll()
    if returncode is None:
        kill_process(proc)
        returncode = proc.poll()

    if returncode != 0:
        log(f"WARNING: Process exited, code: {returncode}")
        write_crash_log(returncode)
    else:
        log("OK: Process exited normally")


def run_watch():
    """监听文件变更，自动重启。"""
    proc = start_process()
    last_mtimes = get_mtimes()
    restart_count = 0

    # 启动时清空旧崩溃日志
    try:
        with open(CRASH_LOG, 'w', encoding='utf-8') as f:
            f.write(f"=== dev_runner 崩溃日志 (启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)

            # 检查进程是否意外退出
            ret = proc.poll()
            if ret is not None and ret != 0:
                restart_count += 1
                # 读取 stderr
                stderr_text = ""
                if proc.stderr:
                    try:
                        stderr_text = proc.stderr.read()
                    except Exception:
                        pass
                log(f"WARNING: Process crashed (exit code: {ret}), writing crash log...")
                if stderr_text.strip():
                    log(f"   Error: {stderr_text.strip().split(chr(10))[-1]}")
                write_crash_log(ret, stderr_text)
                # 等待 1 秒再重启，避免频繁崩溃循环
                time.sleep(1)
                log(">> Restarting main.py ...")
                proc = start_process()
                last_mtimes = get_mtimes()  # 重启后刷新时间戳
                continue

            # 检测文件变更
            try:
                current = get_mtimes()
            except OSError:
                continue

            if current != last_mtimes:
                changed = [
                    os.path.relpath(p, PROJECT_DIR)
                    for p in current
                    if current[p] != last_mtimes.get(p)
                ]
                added = [
                    os.path.relpath(p, PROJECT_DIR)
                    for p in current
                    if p not in last_mtimes
                ]
                removed = [
                    os.path.relpath(p, PROJECT_DIR)
                    for p in last_mtimes
                    if p not in current
                ]

                log(f"[CHANGED] {len(changed)} files changed, restarting...")
                if changed:
                    # 最多显示前 5 个文件
                    for f in changed[:5]:
                        print(f"     → {f}")
                    if len(changed) > 5:
                        print(f"     ... 还有 {len(changed) - 5} 个文件")

                last_mtimes = current
                restart_count += 1
                kill_process(proc)
                time.sleep(0.3)  # 短暂等待文件写入完成
                log(f">> Restart #{restart_count} main.py ...")
                proc = start_process()

    except KeyboardInterrupt:
        log("Dev runner stopped.")
        kill_process(proc)


# ============================================================
# 入口
# ============================================================

def main():
    args = sys.argv[1:]

    if '--once' in args:
        run_once(capture_output='--stdout' in args)
    elif '--stdout' in args:
        run_once(capture_output=True)
    else:
        log("Dev runner started (watch mode, Ctrl+C to exit)")
        log(f"  Watch dir: {PROJECT_DIR}")
        log(f"  Watch exts: {', '.join(WATCH_EXTS)}")
        log(f"  Crash log: {CRASH_LOG}")
        run_watch()


if __name__ == '__main__':
    main()
