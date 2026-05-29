import subprocess
import sys
import os
import time

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_mtimes():
    """扫描所有 .py 文件的最后修改时间"""
    mtimes = {}
    for root, dirs, files in os.walk(PROJECT_DIR):
        if 'venv' in root:
            continue
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                mtimes[path] = os.path.getmtime(path)
    return mtimes


def main():
    proc = None
    last_mtimes = get_mtimes()

    def restart():
        nonlocal proc
        if proc:
            proc.kill()
            proc.wait()
        print("\n▶ 启动 main.py ...\n")
        proc = subprocess.Popen([sys.executable, 'main.py'])

    restart()

    try:
        while True:
            time.sleep(1)
            current = get_mtimes()
            if current != last_mtimes:
                changed = [p for p in current if current[p] != last_mtimes.get(p)]
                print(f"\n📝 检测到文件变更，自动重启...")
                last_mtimes = current
                restart()
    except KeyboardInterrupt:
        print("\n■ 退出")
        if proc:
            proc.kill()


if __name__ == '__main__':
    main()
