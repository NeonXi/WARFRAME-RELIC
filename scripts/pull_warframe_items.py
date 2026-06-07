#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WFCD/warframe-items 数据获取（生产级方案）
使用 Git 稀疏检出，只拉取需要的文件
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Callable


# 配置
REPO_URL = "https://github.com/WFCD/warframe-items.git"
REPO_DIR = Path(__file__).parent.parent / "external" / "warframe-items_sparse"
OUTPUT_DIR = Path(__file__).parent.parent / "external" / "warframe-items_sparse" / "data" / "json"
FILES_TO_PULL = [
    "data/json/Relics.json",
    "data/json/i18n.json",
    "data/json/All.json",
]

# Drop data 稀疏检出配置
DROP_REPO_URL = "https://github.com/WFCD/warframe-drop-data.git"
DROP_REPO_DIR = Path(__file__).parent.parent / "external" / "warframe-drop-data_sparse"
DROP_OUTPUT_DIR = Path(__file__).parent.parent / "external" / "warframe-drop-data_sparse" / "data"
DROP_FILES_TO_PULL = ["data/all.json"]

# I18n 翻译数据稀疏检出配置
I18N_REPO_URL = "https://github.com/calamity-inc/warframe-public-export-plus.git"
I18N_REPO_BRANCH = "senpai"
I18N_REPO_DIR = Path(__file__).parent.parent / "external" / "warframe-i18n_sparse"
I18N_OUTPUT_DIR = Path(__file__).parent.parent / "external" / "warframe-i18n_sparse"
I18N_FILES_TO_PULL = ["dict.en.json", "dict.zh.json"]


def run_cmd(cmd: list, cwd: Path = None, capture: bool = False) -> tuple:
    """
    运行 Git 命令
    :param cmd: 命令列表
    :param cwd: 工作目录
    :param capture: 是否捕获输出
    :return: (返回码, 标准输出, 标准错误)
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


def init_sparse_checkout(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    clone_url: str = None,
):
    """初始化稀疏检出仓库。

    使用 git clone --sparse 方式（现代推荐方式），
    避免手动 git init + config + pull 的兼容性问题。

    :param log_callback: 日志回调函数 (level, message)
    :param progress_callback: 进度回调函数 (stage, cur, total, pct)
    :param clone_url: 自定义克隆 URL（用于代理镜像），None 使用默认 REPO_URL
    """
    total_steps = 5
    current_step = 0

    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)
        else:
            print(msg)

    def _progress(stage: str, cur: int = None, total: int = None, pct: int = None):
        nonlocal current_step
        if progress_callback:
            if pct is not None:
                progress_callback(pct)
            elif cur is not None and total is not None:
                progress_callback(stage, cur, total)

    _log('info', "=" * 80)
    _log('info', "WFCD/warframe-items 数据获取（Git 稀疏检出）")
    _log('info', "=" * 80)

    # 使用自定义 URL 或默认 URL
    url = clone_url if clone_url else REPO_URL

    current_step += 1
    _progress("初始化仓库", current_step, total_steps, int((current_step / total_steps) * 100))

    # 清理旧的（如果有）
    if REPO_DIR.exists():
        _log('info', f"\n清理旧仓库: {REPO_DIR}")
        _rmtree_force(REPO_DIR)

    # 步骤 1: git clone --sparse（一次性完成 clone + sparse checkout 配置）
    current_step += 1
    _progress("克隆仓库", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', f"\n克隆仓库: {url}")
    _log('info', "参数: --depth=1 --filter=blob:none --sparse --no-checkout")

    code, out, err = run_cmd(
        ["git", "clone", "--depth=1", "--filter=blob:none", "--sparse", "--no-checkout",
         url, str(REPO_DIR)],
        capture=True
    )
    if code != 0:
        _log('error', f"[X] git clone 失败: {err}")
        _log('error', f"  输出: {out}")
        # 回退: 尝试不带 --filter 的克隆
        _log('info', "回退: 尝试不带 --filter 的克隆...")
        if REPO_DIR.exists():
            _rmtree_force(REPO_DIR)
        code, out, err = run_cmd(
            ["git", "clone", "--depth=1", "--sparse", "--no-checkout",
             url, str(REPO_DIR)],
            capture=True
        )
        if code != 0:
            _log('error', f"[X] git clone (回退) 也失败: {err}")
            return False

    # 步骤 2: 配置要检出的文件
    current_step += 1
    _progress("配置稀疏检出", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "配置要检出的文件:")
    for f in FILES_TO_PULL:
        _log('info', f"  - {f}")

    code, _, err = run_cmd(
        ["git", "sparse-checkout", "set", "--no-cone"] + FILES_TO_PULL,
        cwd=REPO_DIR
    )
    if code != 0:
        _log('error', f"[X] sparse-checkout 配置失败: {err}")
        return False

    # 步骤 3: 检出文件
    current_step += 1
    _progress("检出文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n检出文件...")
    code, out, err = run_cmd(["git", "checkout"], cwd=REPO_DIR, capture=True)
    if code != 0:
        _log('error', f"[X] git checkout 失败: {err}")
        _log('error', f"  输出: {out}")
        return False

    # 步骤 4: 复制文件到输出目录
    current_step += 1
    _progress("复制文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n复制文件到目标目录...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for idx, src_path in enumerate(FILES_TO_PULL):
        _progress("复制文件", idx + 1, len(FILES_TO_PULL), int((idx + 1) / len(FILES_TO_PULL) * 100))
        src_file = REPO_DIR / src_path
        if src_file.exists():
            dest_file = OUTPUT_DIR / Path(src_path).name
            # 源和目标相同时跳过（git sparse checkout 已将文件放到了正确位置）
            try:
                if src_file.samefile(dest_file):
                    _log('info', f"  [OK] {Path(src_path).name} (已在目标位置)")
                    success_count += 1
                    continue
            except OSError:
                pass
            # 重试复制：目标文件可能被其他进程锁定
            copied = False
            for attempt in range(5):
                try:
                    shutil.copy2(src_file, dest_file)
                    copied = True
                    break
                except PermissionError:
                    import time as _time
                    if attempt < 4:
                        _log('warn', f"  [!] {Path(src_path).name} 被占用，等待 1 秒后重试 ({attempt + 1}/5)...")
                        _time.sleep(1)
                    else:
                        _log('error', f"  [X] {Path(src_path).name} 复制失败: 文件被锁定，请关闭正在使用该文件的程序后重试")
            if copied:
                _log('info', f"  [OK] {Path(src_path).name}")
                success_count += 1

    # 步骤 5: 完成
    current_step += 1
    _progress("完成", current_step, total_steps, 100)

    _log('info', "\n" + "=" * 80)
    if success_count == len(FILES_TO_PULL):
        _log('ok', f"[OK] 全部成功！")
    else:
        _log('warn', f"[!] 完成，部分文件缺失: {success_count}/{len(FILES_TO_PULL)}")
    _log('info', f"  保存位置: {OUTPUT_DIR.absolute()}")
    _log('info', "=" * 80)
    return success_count > 0


def _rmtree_force(path: Path):
    """强制删除目录（处理 Windows 下的只读文件问题）。"""
    import stat
    def _on_error(func, p, exc_info):
        # 只读文件: 先改权限再删除
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(str(path), onerror=_on_error)


def update_existing(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    clone_url: str = None,
):
    """更新已有的稀疏检出仓库。

    由于 Git 浅克隆 (--depth=1) 在已有仓库上更新时容易出问题
    （尤其是已经 unshallow 的仓库），这里采用更稳健的策略：
    直接删除旧仓库，重新初始化。

    :param log_callback: 日志回调函数 (level, message)
    :param progress_callback: 进度回调函数 (stage, cur, total, pct)
    :param clone_url: 自定义克隆 URL（用于代理镜像），None 使用默认 REPO_URL
    """
    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)
        else:
            print(msg)

    _log('info', "\n仓库已存在，删除后重新初始化（避免浅克隆冲突）...")
    if REPO_DIR.exists():
        _rmtree_force(REPO_DIR)
    return init_sparse_checkout(log_callback=log_callback, progress_callback=progress_callback, clone_url=clone_url)


def init_drop_data_sparse_checkout(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    clone_url: str = None,
):
    """初始化 warframe-drop-data 稀疏检出仓库（只拉取 data/all.json）。

    :param log_callback: 日志回调函数 (level, message)
    :param progress_callback: 进度回调函数 (stage, cur, total, pct)
    :param clone_url: 自定义克隆 URL（用于代理镜像），None 使用默认 DROP_REPO_URL
    """
    total_steps = 5
    current_step = 0

    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)
        else:
            print(msg)

    def _progress(stage: str, cur: int = None, total: int = None, pct: int = None):
        nonlocal current_step
        if progress_callback:
            if pct is not None:
                progress_callback(pct)
            elif cur is not None and total is not None:
                progress_callback(stage, cur, total)

    _log('info', "=" * 80)
    _log('info', "WFCD/warframe-drop-data 数据获取（Git 稀疏检出）")
    _log('info', "=" * 80)

    # 使用自定义 URL 或默认 URL
    drop_url = clone_url if clone_url else DROP_REPO_URL

    current_step += 1
    _progress("初始化仓库", current_step, total_steps, int((current_step / total_steps) * 100))

    # 清理旧的
    if DROP_REPO_DIR.exists():
        _log('info', f"\n清理旧仓库: {DROP_REPO_DIR}")
        _rmtree_force(DROP_REPO_DIR)

    # 步骤 1: git clone --sparse
    current_step += 1
    _progress("克隆仓库", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', f"\n克隆仓库: {drop_url}")
    _log('info', "参数: --depth=1 --filter=blob:none --sparse --no-checkout")

    code, out, err = run_cmd(
        ["git", "clone", "--depth=1", "--filter=blob:none", "--sparse", "--no-checkout",
         drop_url, str(DROP_REPO_DIR)],
        capture=True
    )
    if code != 0:
        _log('error', f"[X] git clone 失败: {err}")
        _log('error', f"  输出: {out}")
        _log('info', "回退: 尝试不带 --filter 的克隆...")
        if DROP_REPO_DIR.exists():
            _rmtree_force(DROP_REPO_DIR)
        code, out, err = run_cmd(
            ["git", "clone", "--depth=1", "--sparse", "--no-checkout",
             drop_url, str(DROP_REPO_DIR)],
            capture=True
        )
        if code != 0:
            _log('error', f"[X] git clone (回退) 也失败: {err}")
            return False

    # 步骤 2: 配置要检出的文件
    current_step += 1
    _progress("配置稀疏检出", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "配置要检出的文件:")
    for f in DROP_FILES_TO_PULL:
        _log('info', f"  - {f}")

    code, _, err = run_cmd(
        ["git", "sparse-checkout", "set", "--no-cone"] + DROP_FILES_TO_PULL,
        cwd=DROP_REPO_DIR
    )
    if code != 0:
        _log('error', f"[X] sparse-checkout 配置失败: {err}")
        return False

    # 步骤 3: 检出文件
    current_step += 1
    _progress("检出文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n检出文件...")
    code, out, err = run_cmd(["git", "checkout"], cwd=DROP_REPO_DIR, capture=True)
    if code != 0:
        _log('error', f"[X] git checkout 失败: {err}")
        _log('error', f"  输出: {out}")
        return False

    # 步骤 4: 复制文件到输出目录
    current_step += 1
    _progress("复制文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n复制文件到目标目录...")
    DROP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for idx, src_path in enumerate(DROP_FILES_TO_PULL):
        _progress("复制文件", idx + 1, len(DROP_FILES_TO_PULL), int((idx + 1) / len(DROP_FILES_TO_PULL) * 100))
        src_file = DROP_REPO_DIR / src_path
        if src_file.exists():
            dest_file = DROP_OUTPUT_DIR / Path(src_path).name
            try:
                if src_file.samefile(dest_file):
                    _log('info', f"  [OK] {Path(src_path).name} (已在目标位置)")
                    success_count += 1
                    continue
            except OSError:
                pass
            shutil.copy2(src_file, dest_file)
            _log('info', f"  [OK] {Path(src_path).name}")
            success_count += 1

    # 步骤 5: 完成
    current_step += 1
    _progress("完成", current_step, total_steps, 100)

    _log('info', "\n" + "=" * 80)
    if success_count == len(DROP_FILES_TO_PULL):
        _log('ok', f"[OK] 掉落数据全部成功！")
    else:
        _log('warn', f"[!] 完成，部分文件缺失: {success_count}/{len(DROP_FILES_TO_PULL)}")
    _log('info', f"  保存位置: {DROP_OUTPUT_DIR.absolute()}")
    _log('info', "=" * 80)
    return success_count > 0


def update_drop_data_existing(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    clone_url: str = None,
):
    """更新已有的 warframe-drop-data 稀疏检出仓库。

    :param clone_url: 自定义克隆 URL（用于代理镜像），None 使用默认 DROP_REPO_URL
    """
    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)
        else:
            print(msg)

    _log('info', "\n掉落数据仓库已存在，删除后重新初始化...")
    if DROP_REPO_DIR.exists():
        _rmtree_force(DROP_REPO_DIR)
    return init_drop_data_sparse_checkout(log_callback=log_callback, progress_callback=progress_callback, clone_url=clone_url)


def init_i18n_sparse_checkout(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    clone_url: str = None,
):
    """初始化 warframe-public-export-plus 稀疏检出仓库（只拉取 dict.en.json / dict.zh.json）。

    :param log_callback: 日志回调函数 (level, message)
    :param progress_callback: 进度回调函数 (stage, cur, total, pct)
    :param clone_url: 自定义克隆 URL（用于代理镜像），None 使用默认 I18N_REPO_URL
    """
    total_steps = 5
    current_step = 0

    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)
        else:
            print(msg)

    def _progress(stage: str, cur: int = None, total: int = None, pct: int = None):
        nonlocal current_step
        if progress_callback:
            if pct is not None:
                progress_callback(pct)
            elif cur is not None and total is not None:
                progress_callback(stage, cur, total)

    _log('info', "=" * 80)
    _log('info', "calamity-inc/warframe-public-export-plus 数据获取（Git 稀疏检出）")
    _log('info', "=" * 80)

    # 使用自定义 URL 或默认 URL
    i18n_url = clone_url if clone_url else I18N_REPO_URL

    current_step += 1
    _progress("初始化仓库", current_step, total_steps, int((current_step / total_steps) * 100))

    # 清理旧的
    if I18N_REPO_DIR.exists():
        _log('info', f"\n清理旧仓库: {I18N_REPO_DIR}")
        _rmtree_force(I18N_REPO_DIR)

    # 步骤 1: git clone --sparse（指定分支）
    current_step += 1
    _progress("克隆仓库", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', f"\n克隆仓库: {i18n_url} (分支: {I18N_REPO_BRANCH})")
    _log('info', "参数: --depth=1 --branch=senpai --filter=blob:none --sparse --no-checkout")

    code, out, err = run_cmd(
        ["git", "clone", "--depth=1", f"--branch={I18N_REPO_BRANCH}",
         "--filter=blob:none", "--sparse", "--no-checkout",
         i18n_url, str(I18N_REPO_DIR)],
        capture=True
    )
    if code != 0:
        _log('error', f"[X] git clone 失败: {err}")
        _log('error', f"  输出: {out}")
        _log('info', "回退: 尝试不带 --filter 的克隆...")
        if I18N_REPO_DIR.exists():
            _rmtree_force(I18N_REPO_DIR)
        code, out, err = run_cmd(
            ["git", "clone", "--depth=1", f"--branch={I18N_REPO_BRANCH}",
             "--sparse", "--no-checkout",
             i18n_url, str(I18N_REPO_DIR)],
            capture=True
        )
        if code != 0:
            _log('error', f"[X] git clone (回退) 也失败: {err}")
            return False

    # 步骤 2: 配置要检出的文件
    current_step += 1
    _progress("配置稀疏检出", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "配置要检出的文件:")
    for f in I18N_FILES_TO_PULL:
        _log('info', f"  - {f}")

    code, _, err = run_cmd(
        ["git", "sparse-checkout", "set", "--no-cone"] + I18N_FILES_TO_PULL,
        cwd=I18N_REPO_DIR
    )
    if code != 0:
        _log('error', f"[X] sparse-checkout 配置失败: {err}")
        return False

    # 步骤 3: 检出文件
    current_step += 1
    _progress("检出文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n检出文件...")
    code, out, err = run_cmd(["git", "checkout"], cwd=I18N_REPO_DIR, capture=True)
    if code != 0:
        _log('error', f"[X] git checkout 失败: {err}")
        _log('error', f"  输出: {out}")
        return False

    # 步骤 4: 复制文件到输出目录
    current_step += 1
    _progress("复制文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n复制文件到目标目录...")
    I18N_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for idx, src_path in enumerate(I18N_FILES_TO_PULL):
        _progress("复制文件", idx + 1, len(I18N_FILES_TO_PULL),
                  int((idx + 1) / len(I18N_FILES_TO_PULL) * 100))
        src_file = I18N_REPO_DIR / src_path
        if src_file.exists():
            dest_file = I18N_OUTPUT_DIR / Path(src_path).name
            try:
                if src_file.samefile(dest_file):
                    _log('info', f"  [OK] {Path(src_path).name} (已在目标位置)")
                    success_count += 1
                    continue
            except OSError:
                pass
            shutil.copy2(src_file, dest_file)
            _log('info', f"  [OK] {Path(src_path).name}")
            success_count += 1

    # 步骤 5: 完成
    current_step += 1
    _progress("完成", current_step, total_steps, 100)

    _log('info', "\n" + "=" * 80)
    if success_count == len(I18N_FILES_TO_PULL):
        _log('ok', f"[OK] 翻译数据全部成功！")
    else:
        _log('warn', f"[!] 完成，部分文件缺失: {success_count}/{len(I18N_FILES_TO_PULL)}")
    _log('info', f"  保存位置: {I18N_OUTPUT_DIR.absolute()}")
    _log('info', "=" * 80)
    return success_count > 0


def update_i18n_existing(
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    clone_url: str = None,
):
    """更新已有的 warframe-public-export-plus 稀疏检出仓库。

    :param clone_url: 自定义克隆 URL（用于代理镜像），None 使用默认 I18N_REPO_URL
    """
    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)
        else:
            print(msg)

    _log('info', "\n翻译数据仓库已存在，删除后重新初始化...")
    if I18N_REPO_DIR.exists():
        _rmtree_force(I18N_REPO_DIR)
    return init_i18n_sparse_checkout(log_callback=log_callback, progress_callback=progress_callback, clone_url=clone_url)


def main():
    # 检查是否已初始化
    if REPO_DIR.exists() and (REPO_DIR / ".git").exists():
        # 已存在，尝试更新
        return update_existing()
    else:
        # 不存在，初始化
        return init_sparse_checkout()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
