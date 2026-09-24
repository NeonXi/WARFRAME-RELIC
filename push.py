"""
[L0-Tool] push.py — 一键提交并推送到 GitHub(构建/维护工具,非运行时代码)

依赖: Python 标准库 + git 命令行
职责: 提交本地改动 → 检查远程分歧 → 直连推送

用法:
    python push.py                    # 交互式:列出改动,输入提交信息后推送
    python push.py -m "fix: xxx"      # 免交互:直接用给定信息提交并推送
    python push.py --push-only        # 不提交,只把已有本地提交推上去

流程设计(考虑点):
    1. 改动检查 —— 无改动且无未推送提交时直接退出,不产生空提交
    2. 远程分歧 —— push 前 fetch,远程领先时中止并提示先 pull,避免 non-fast-forward 失败
    3. 网络说明 —— 本脚本只走直连;若直连 GitHub 不通(报 Failed to connect),
       请自行开启系统代理的 TUN/全局模式后重试,脚本不处理代理配置
    4. 大文件护栏 —— 暂存前扫描超过 50MB 的文件并警告,防止误推撑爆仓库
    5. 敏感文件护栏 —— .env / 密钥类文件名直接拦截
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent

# 超过该体积的暂存文件给出警告(GitHub 单文件硬限 100MB)
_LARGE_FILE_MB = 50

# 敏感文件名/后缀,命中即拦截
_SENSITIVE_PATTERNS = (".env", "credential", "secret", "private_key", ".pem", ".key")


# ── 日志 ──────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[push] {msg}", flush=True)


def _ok(msg: str) -> None:
    print(f"[push]   OK  {msg}", flush=True)


def _warn(msg: str) -> None:
    print(f"[push]  WARN {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"[push]  FAIL {msg}", flush=True)


# ── git 封装 ──────────────────────────────────────────────────────────

def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """执行 git 命令并捕获输出。"""
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _git_out(*args: str) -> str:
    """执行 git 并返回 stdout(失败返回空串)。"""
    r = _git(*args)
    return r.stdout.strip() if r.returncode == 0 else ""


# ── 步骤 1:检查改动 ───────────────────────────────────────────────────

def collect_changes() -> tuple[list[str], list[str]]:
    """返回 (已跟踪改动列表, 未跟踪文件列表)。"""
    r = _git("status", "--porcelain")
    if r.returncode != 0:
        _fail("git status 执行失败,请确认当前目录是 git 仓库")
        sys.exit(1)
    tracked, untracked = [], []
    for line in r.stdout.splitlines():
        if not line:
            continue
        status, path = line[:2], line[3:]
        if status == "??":
            untracked.append(path)
        else:
            tracked.append(f"{status} {path}")
    return tracked, untracked


def check_sensitive_and_large(paths: list[str]) -> bool:
    """扫描待提交文件:敏感文件拦截,大文件警告。返回是否可继续。"""
    for p in paths:
        low = p.lower()
        if any(s in low for s in _SENSITIVE_PATTERNS):
            _fail(f"检测到疑似敏感文件,已拦截: {p}")
            _log("如确认无害,请手动 git add 并提交")
            return False
    for p in paths:
        fp = PROJECT / p
        if fp.is_file() and fp.stat().st_size > _LARGE_FILE_MB * 1024 * 1024:
            _warn(f"大文件 {_large}MB: {p}".replace("_large",
                  str(fp.stat().st_size // 1024 // 1024)))
    return True


# ── 步骤 2:提交 ───────────────────────────────────────────────────────

def do_commit(message: str, tracked: list[str], untracked: list[str]) -> bool:
    all_files = [line.split(" ", 1)[1] for line in tracked] + untracked
    if not check_sensitive_and_large(all_files):
        return False

    # 已跟踪改动直接 -u 暂存;未跟踪文件逐个加入(避免 git add . 误加)
    if tracked:
        _git("add", "-u")
    for f in untracked:
        _git("add", "--", f)

    r = _git("commit", "-m", message)
    if r.returncode != 0:
        _fail(f"提交失败: {r.stderr.strip()}")
        return False
    _ok(f"已提交: {message}")
    return True


# ── 步骤 3:远程分歧检查 ───────────────────────────────────────────────

def check_remote_diverged() -> bool:
    """fetch 后检查远程是否领先。远程领先返回 True(应中止)。"""
    try:
        r = _git("fetch", "origin", timeout=30)
    except subprocess.TimeoutExpired:
        r = None
    if r is None or r.returncode != 0:
        _warn("fetch 远程失败(网络问题?),跳过分歧检查直接尝试 push")
        return False
    behind = _git_out("rev-list", "--count", "HEAD..@{u}")
    if behind and behind != "0":
        _fail(f"远程领先本地 {behind} 个提交,直接 push 会被拒绝")
        _log("请先执行: git pull --rebase origin main  (解决后再运行本脚本)")
        return True
    return False


# ── 步骤 4:直连推送 ───────────────────────────────────────────────────

def push_direct() -> bool:
    """直连推送,返回是否成功。"""
    _log("直连推送 GitHub ...")
    try:
        r = _git("push", "origin", "main", timeout=180)
    except subprocess.TimeoutExpired:
        _fail("推送超时(180s)")
        return False
    if r.returncode == 0:
        _ok("推送成功")
        return True
    err = (r.stderr or "").strip().splitlines()
    _fail(f"推送失败: {err[-1] if err else '未知错误'}")
    if err and "Failed to connect" in err[-1]:
        _log("排查建议: 直连不通时请开启系统代理的 TUN/全局模式后重试")
    return False


# ── 主流程 ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="一键提交并推送到 GitHub")
    parser.add_argument("-m", "--message", help="提交信息(不给则交互输入)")
    parser.add_argument("--push-only", action="store_true",
                        help="跳过提交,只推送已有本地提交")
    args = parser.parse_args()

    _log(f"仓库: {PROJECT}")

    tracked, untracked = collect_changes()
    ahead = _git_out("rev-list", "--count", "@{u}..HEAD") or "0"

    # 无改动且无待推送 → 直接退出
    if not tracked and not untracked and ahead == "0":
        _ok("工作区干净,本地与远程已同步,无需操作")
        return

    # ── 提交阶段 ──
    if args.push_only:
        if tracked or untracked:
            _warn("--push-only 模式下工作区有未提交改动,将只推送已有提交")
    else:
        if tracked or untracked:
            print()
            _log("检测到以下改动:")
            for line in tracked:
                print(f"    {line}")
            for f in untracked:
                print(f"    ?? {f} (新文件)")
            print()

            message = args.message
            if not message:
                try:
                    message = input("[push] 请输入提交信息(回车取消): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    _log("已取消")
                    return
            if not message:
                _log("提交信息为空,已取消")
                return

            if not do_commit(message, tracked, untracked):
                sys.exit(1)
            ahead = _git_out("rev-list", "--count", "@{u}..HEAD") or "0"

    # ── 推送阶段 ──
    if ahead == "0":
        _ok("本地没有待推送的提交")
        return

    _log(f"本地领先远程 {ahead} 个提交,准备推送")

    if check_remote_diverged():
        sys.exit(1)

    if not push_direct():
        sys.exit(1)

    # 最终确认
    remaining = _git_out("rev-list", "--count", "@{u}..HEAD") or "0"
    if remaining == "0":
        _ok("本地与远程已完全同步")
    else:
        _warn(f"推送后仍领先 {remaining} 个提交?请检查远程分支配置")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        _log("用户中断")
        sys.exit(130)
