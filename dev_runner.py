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
import threading
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


def _safe_decode(data: bytes) -> str:
    """安全解码字节数据，尝试多种编码。"""
    encodings = ['utf-8', 'gbk', 'gb18030', 'cp936', 'big5']
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def write_crash_log(returncode: int, stderr: str = '', stdout_tail: str = ''):
    """将崩溃信息写入 crash_log.txt"""
    try:
        with open(CRASH_LOG, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"崩溃时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"退出码: {returncode} (0x{returncode & 0xFFFFFFFF:08X})\n")
            if stderr:
                f.write(f"stderr:\n{stderr}\n")
            if stdout_tail:
                f.write(f"stdout 最后输出:\n{stdout_tail}\n")
            f.write(f"{'=' * 60}\n")
    except Exception:
        pass


def get_mtimes():
    """扫描项目文件的最后修改时间（仅 WATCH_EXTS）。"""
    mtimes = {}
    for root, dirs, files in os.walk(PROJECT_DIR):
        # 跳过不需要监听的目录
        dirs[:] = [d for d in dirs if d not in (
            'venv', '.git', '__pycache__', '.codebuddy', 'dist', 'build',
            'testvenv', 'tests',
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
    ★ 始终捕获 stdout 用于崩溃时回溯最后几行输出。
    """
    kwargs = {'env': os.environ.copy()}
    # Windows: 隐藏控制台窗口（防止 keyboard 钩子注册时弹出黑窗）
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    if capture_output:
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.STDOUT
        kwargs['text'] = False
    else:
        # ★ 始终捕获 stdout 和 stderr，用于崩溃时回溯
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE
        kwargs['text'] = False
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
                if isinstance(line, bytes):
                    line = line.decode('utf-8', errors='replace')
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
        stderr_text = ""
        if proc.stderr:
            try:
                stderr_bytes = proc.stderr.read()
                if isinstance(stderr_bytes, bytes):
                    stderr_text = stderr_bytes.decode('utf-8', errors='replace')
            except:
                pass
        log(f"WARNING: Process exited, code: {returncode}")
        write_crash_log(returncode, stderr_text)
    else:
        log("OK: Process exited normally")


def run_watch():
    """监听文件变更，自动重启。"""
    proc = start_process()
    last_mtimes = get_mtimes()
    restart_count = 0
    stdout_lines = []  # ★ 保留最近的 stdout 行用于崩溃诊断
    MAX_TAIL = 50

    # 启动 stdout 读取线程
    def _reader(pipe, buf):
        """后台线程：持续读取子进程 stdout，保留最近行。"""
        while True:
            try:
                line = pipe.readline()
                if not line:
                    break
                decoded = _safe_decode(line).rstrip('\n\r')
                buf.append(decoded)
                if len(buf) > MAX_TAIL:
                    buf.pop(0)
                # 同时输出到 dev_runner 控制台
                print(decoded, flush=True)
            except Exception:
                break

    stdout_thread = threading.Thread(
        target=_reader, args=(proc.stdout, stdout_lines), daemon=True)
    stdout_thread.start()

    # 启动时清空旧崩溃日志
    try:
        with open(CRASH_LOG, 'w', encoding='utf-8', errors='replace') as f:
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
                stderr_text = ""
                stdout_tail = ""
                if proc.stderr:
                    try:
                        stderr_bytes = proc.stderr.read()
                        if isinstance(stderr_bytes, bytes):
                            stderr_text = stderr_bytes.decode('utf-8', errors='replace')
                        else:
                            stderr_text = str(stderr_bytes)
                    except Exception as e:
                        try:
                            stderr_text = str(proc.stderr.read(), errors='replace')
                        except:
                            stderr_text = "Failed to read stderr"
                # ★ 获取 stdout 最后输出
                stdout_tail = '\n'.join(stdout_lines[-30:])
                log(f"WARNING: Process crashed (exit code: {ret}), writing crash log...")
                if stderr_text.strip():
                    log(f"   Error: {stderr_text.strip().split(chr(10))[-1]}")
                if stdout_tail:
                    log(f"   Last stdout: {stdout_tail.split(chr(10))[-1]}")
                write_crash_log(ret, stderr_text, stdout_tail)
                # 等待 1 秒再重启，避免频繁崩溃循环
                time.sleep(1)
                log(">> Restarting main.py ...")
                stdout_lines.clear()
                proc = start_process()
                stdout_thread = threading.Thread(
                    target=_reader, args=(proc.stdout, stdout_lines), daemon=True)
                stdout_thread.start()
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
                        print(f"     -> {f}")
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
