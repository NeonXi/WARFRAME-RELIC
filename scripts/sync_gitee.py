"""
Gitee 仓库同步工具 — 从 GitHub 拉取最新代码并推送到 Gitee。

使用方式:
    python scripts/sync_gitee.py

首次运行会在 data/ 目录下创建 .gitee_sync_cache/ 缓存目录，
后续同步只需增量拉取，速度很快。
"""

import os
import subprocess
import sys
from pathlib import Path

# ===== 配置区 =====
GITEE_USER = "zdljarvis"
GITEE_REPO = "warframe-drop-data"
GITHUB_REPO_URL = "https://github.com/WFCD/warframe-drop-data.git"
GITEE_REPO_URL = f"https://gitee.com/{GITEE_USER}/{GITEE_REPO}.git"

# 缓存目录（放在项目 data/ 下，不污染项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / ".gitee_sync_cache"


def run(cmd: str, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    """执行 shell 命令并打印输出。"""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    if result.stderr and "warning:" not in result.stderr.lower():
        for line in result.stderr.strip().split("\n"):
            print(f"    [stderr] {line}")
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败 (exit={result.returncode}): {cmd}")
    return result


def main():
    print("=" * 60)
    print("Gitee 仓库同步工具")
    print(f"  GitHub: {GITHUB_REPO_URL}")
    print(f"  Gitee:  {GITEE_REPO_URL}")
    print("=" * 60)

    # 检查 git 是否可用
    try:
        run("git --version", check=False)
    except Exception:
        print("✗ 未找到 git 命令，请先安装 Git")
        print("  下载: https://git-scm.com/download/win")
        return 1

    # 准备缓存目录
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    repo_dir = CACHE_DIR / GITEE_REPO

    # 步骤 1: 克隆或更新 GitHub 仓库
    print()
    if (repo_dir / ".git").exists():
        print("[1/3] 更新本地缓存（从 GitHub 拉取最新代码）...")
        run("git fetch origin --prune", cwd=repo_dir)
        # 强制重置到 GitHub 最新状态
        run("git reset --hard origin/main", cwd=repo_dir)
        run("git clean -fd", cwd=repo_dir)
        print("  ✓ 本地缓存已更新")
    else:
        print("[1/3] 首次克隆 GitHub 仓库（仅首次较慢，后续增量更新）...")
        run(f"git clone --bare {GITHUB_REPO_URL} {repo_dir}")
        print("  ✓ 克隆完成")

    # 步骤 2: 推送到 Gitee
    print()
    print("[2/3] 推送到 Gitee...")
    try:
        run(f"git push --mirror {GITEE_REPO_URL}", cwd=repo_dir)
        print("  ✓ 推送成功")
    except RuntimeError:
        # 如果推送失败（可能是认证问题），提示用户
        print()
        print("  ⚠ 推送失败！可能原因:")
        print("    1. 未配置 Gitee 认证信息")
        print("    2. 网络问题")
        print()
        print("  解决方法：")
        print("    a) 使用 SSH（推荐）:")
        print(f"       git remote set-url origin git@gitee.com:{GITEE_USER}/{GITEE_REPO}.git")
        print("    b) 使用 HTTPS + 密码:")
        print("       git config --global credential.helper store")
        print(f"       git push https://gitee.com/{GITEE_USER}/{GITEE_REPO}.git --mirror")
        return 1

    # 步骤 3: 验证
    print()
    print("[3/3] 验证同步结果...")
    github_latest = run("git log -1 --format=%H", cwd=repo_dir, check=False)
    print(f"  GitHub 最新 commit: {github_latest.stdout.strip()[:12]}")
    print(f"  Gitee 仓库: https://gitee.com/{GITEE_USER}/{GITEE_REPO}")

    print()
    print("=" * 60)
    print("✓ 同步完成！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())