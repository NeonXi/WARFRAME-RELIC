"""
调试监控脚本 — 监控快捷键触发、截图、OCR、按钮显示等全流程状态。

使用方法:
  1. 正常启动 main.py
  2. 在另一个终端运行: python debug_monitor.py
  3. 按下功能快捷键，观察输出

状态文件: %APPDATA%/WARFRAME-RELIC/debug/monitor_state.json
日志文件: %APPDATA%/WARFRAME-RELIC/debug/monitor.log

注意: 监控代码已内联到 main.py 中，此脚本只需独立运行即可读取状态。
"""

import os
import sys
import time
import json

APPDATA = os.getenv('APPDATA', os.path.expanduser('~'))
MONITOR_DIR = os.path.join(APPDATA, 'WARFRAME-RELIC', 'debug')
MONITOR_LOG = os.path.join(MONITOR_DIR, 'monitor.log')
STATE_FILE = os.path.join(MONITOR_DIR, 'monitor_state.json')


def log(msg: str, level: str = "INFO"):
    ts = time.strftime("%H:%M:%S", time.localtime())
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        os.makedirs(MONITOR_DIR, exist_ok=True)
        with open(MONITOR_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def clear_log():
    try:
        os.makedirs(MONITOR_DIR, exist_ok=True)
        with open(MONITOR_LOG, 'w', encoding='utf-8') as f:
            f.write('')
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception:
        pass


def read_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def format_bool(v) -> str:
    if v:
        return "\033[92mTrue\033[0m"
    return "\033[91mFalse\033[0m"


def format_state(state: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  📊 当前状态快照")
    lines.append("-" * 60)

    keys_display = [
        ("_screenshot_busy",   "截图忙锁"),
        ("_ocr_done",          "OCR 完成"),
        ("_ocr_type",          "OCR 类型"),
        ("_pending_mode",      "待处理模式"),
        ("_last_frame",        "最后帧 (None=空)"),
        ("_last_region",       "最后区域 (None=空)"),
        ("_ocr_thread_alive",  "OCR 线程存活"),
        ("_ocr_worker_alive",  "OCR Worker 存活"),
        ("_region_selector.is_active", "框选模式中"),
        ("_mode_buttons_count","功能按钮数"),
        ("_hide_at",           "自动隐藏时间"),
        ("_annotations_count", "标注数量"),
        ("_last_action",       "最近动作"),
        ("_last_action_time",  "动作时间"),
        ("_last_hotkey",       "最近热键"),
        ("_last_hotkey_time",  "热键时间"),
    ]

    for key, label in keys_display:
        val = state.get(key, "(未上报)")
        if isinstance(val, bool):
            val = format_bool(val)
        elif val is None:
            val = "\033[93mNone\033[0m"
        elif val == "":
            val = "\033[90m(空)\033[0m"
        lines.append(f"  {label:16s}: {val}")

    lines.append("-" * 60)

    recent_logs = state.get("_recent_logs", [])
    if recent_logs:
        lines.append("  📝 最近事件 (最新在上):")
        for entry in recent_logs[-8:]:
            lines.append(f"     {entry}")
    lines.append("=" * 60)
    return "\n".join(lines)


def watch(interval: float = 0.5):
    log("🔍 调试监控启动，按 Ctrl+C 退出")
    log(f"   状态文件: {STATE_FILE}")
    log(f"   日志文件: {MONITOR_LOG}")
    log("")

    last_seq = -1
    last_state = {}

    try:
        while True:
            state = read_state()
            if not state:
                if last_seq != -1:
                    log("⚠ 状态文件为空或无法读取", "WARN")
                last_seq = -1
                time.sleep(interval)
                continue

            seq = state.get("_seq", 0)
            if seq != last_seq:
                last_seq = seq
                if last_state:
                    changed = []
                    for k in state:
                        if k.startswith("_"):
                            continue
                        if state.get(k) != last_state.get(k):
                            changed.append(k)
                    if changed:
                        log(f"🔄 状态变化: {', '.join(changed)}")

                print(format_state(state))
                last_state = state

            time.sleep(interval)

    except KeyboardInterrupt:
        log("👋 监控已停止")
        print("\n监控结束。")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        clear_log()
        print("日志已清除。")
    else:
        watch(interval=0.5)
