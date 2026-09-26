"""
[L-Service] WFCD 数据仓库拉取模块（新版本）

使用 Git 稀疏检出，只拉取需要的文件。
从 scripts/pull_warframe_items.py 迁移而来。

支持 3 个上游仓库:
  - WFCD/warframe-items      → 遗物/物品数据
  - WFCD/warframe-drop-data   → 掉落数据
  - calamity-inc/warframe-public-export-plus → 翻译数据

## AI 硬约束 — 修改本文件前必读
归属层:    [L-Service] (core/services/)
允许依赖:  Python 标准库 + data/* + core.hotkey_config 等纯模块
禁止依赖:  PySide6 / QtWidgets / QtGui / QtCore(Signal 除外)
           core.widgets/* / core.pages/* / core.recognizers/*
必读规范:  .trae/rules/开发规范.md §6.2

本文件相关红线:
- 禁止 import PySide6 → Service 是纯逻辑,不能碰 UI
- 禁止返回 Qt 对象 → 只能返回 dict / list / str / int / bool
- 禁止在 Service 中发信号调用 widget → 状态走 core.state / EventBus
- 禁止未捕获的 IO/网络异常冒泡 → 必须 try/except 降级
- 禁止在 Service 中持有 widget 引用

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.2。
"""

import os
import subprocess
import shutil
from pathlib import Path


# ============================================================
# 路径常量(打包/开发环境自适应,见 core.paths)
# ============================================================
from core.paths import app_root as _app_root
_EXTERNAL_DIR = _app_root() / "external"

# ── warframe-items ──
# 注意:上游 2025 年重构,data/json/All.json 已删除,拆分为 26 个分类文件;
# data/json/i18n.json 单文件变为 data/json/i18n/ 目录(按语言 zh/tc/ja... 拆分)。
REPO_DIR = _EXTERNAL_DIR / "warframe-items_sparse"
OUTPUT_DIR = _EXTERNAL_DIR / "warframe-items_sparse" / "data" / "json"

# 分类文件名(即旧 All.json 的拆分产物,Relics.json 也包含在内)
_ITEMS_CATEGORY_FILES = [
    "Arcanes.json", "Arch-Gun.json", "Arch-Melee.json", "Archwing.json",
    "Components.json", "Enemy.json", "Fish.json", "Gear.json", "Glyphs.json",
    "Honoria.json", "Melee.json", "Misc.json", "Mods.json", "Node.json",
    "Pets.json", "Primary.json", "Quests.json", "Railjack.json", "Relics.json",
    "Resources.json", "Secondary.json", "SentinelWeapons.json", "Sentinels.json",
    "Sigils.json", "Skins.json", "Warframes.json",
]

# (仓库内路径, 输出文件名):i18n/zh.json 复制时重命名为 i18n.json,
# 保持下游 db_builder 读取路径不变
ITEMS_PULL_MAP: list[tuple[str, str]] = [
    ("data/json/i18n/zh.json", "i18n.json"),
] + [(f"data/json/{name}", name) for name in _ITEMS_CATEGORY_FILES]

FILES_TO_PULL = [src for src, _ in ITEMS_PULL_MAP]
ITEMS_OUTPUT_FILES = [out for _, out in ITEMS_PULL_MAP]

# ── warframe-drop-data ──
DROP_REPO_URL = "https://github.com/WFCD/warframe-drop-data.git"
DROP_REPO_DIR = _EXTERNAL_DIR / "warframe-drop-data_sparse"
DROP_OUTPUT_DIR = _EXTERNAL_DIR / "warframe-drop-data_sparse" / "data"
DROP_FILES_TO_PULL = ["data/all.json"]

# ── warframe-public-export-plus (翻译) ──
I18N_REPO_URL = "https://github.com/calamity-inc/warframe-public-export-plus.git"
I18N_REPO_BRANCH = "senpai"
I18N_REPO_DIR = _EXTERNAL_DIR / "warframe-i18n_sparse"
I18N_OUTPUT_DIR = _EXTERNAL_DIR / "warframe-i18n_sparse"
I18N_FILES_TO_PULL = ["dict.en.json", "dict.zh.json"]


def run_cmd(cmd: list, cwd: Path = None, capture: bool = False,
            timeout: float = None) -> tuple:
    """
    运行 Git 命令（Windows 下隐藏 CMD 窗口）
    :param cmd: 命令列表
    :param cwd: 工作目录
    :param capture: 是否捕获输出
    :param timeout: 超时秒数(超时返回非零,由调用方换下一个镜像)
    :return: (返回码, 标准输出, 标准错误)
    """
    try:
        kwargs = dict(
            cwd=cwd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # Windows 下隐藏 CMD 弹窗
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        if timeout is not None and os.name == "nt":
            # subprocess.run 的 timeout 只杀父进程,git 的子进程
            # (git-remote-https/index-pack) 会残留并持有文件锁,
            # 导致后续删除仓库目录失败。改用 Popen + taskkill /T 杀整棵树。
            # 注意: Popen 不支持 capture_output,需显式 PIPE
            popen_kwargs = dict(kwargs)
            popen_kwargs.pop("capture_output", None)
            if capture:
                popen_kwargs["stdout"] = subprocess.PIPE
                popen_kwargs["stderr"] = subprocess.PIPE
            proc = subprocess.Popen(cmd, **popen_kwargs)
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                )
                proc.wait()
                return -1, "", f"命令超时({timeout}s),疑似代理卡死"
            return proc.returncode, out, err

        result = subprocess.run(cmd, timeout=timeout, **kwargs)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        # 代理「连上但不出数据」卡死的典型场景:明确标记,让调用方换源
        return -1, "", f"命令超时({timeout}s),疑似代理卡死"
    except Exception as e:
        return -1, "", str(e)


def _rmtree_force(path: Path):
    """强制删除目录（处理 Windows 下的只读文件问题）。"""
    import stat
    def _on_error(func, p, exc_info):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(str(path), onerror=_on_error)


# ============================================================
# 通用稀疏检出模板
# ============================================================

def _normalize_file_map(files_to_pull) -> list[tuple[str, str]]:
    """统一文件清单格式为 (仓库内路径, 输出文件名)。

    - str:输出名取 basename(向后兼容 drop/i18n 调用方)
    - tuple/list:直接采用(支持重命名,如 i18n/zh.json → i18n.json)
    """
    result: list[tuple[str, str]] = []
    for item in files_to_pull:
        if isinstance(item, (tuple, list)):
            result.append((str(item[0]), str(item[1])))
        else:
            result.append((str(item), Path(str(item)).name))
    return result


def _do_clone(url: str, repo_dir: Path, branch: str = None,
              use_filter: bool = True, timeout: float = 180) -> tuple:
    """执行稀疏克隆。use_filter=True 走 partial clone(blob 按需拉取),
    False 走普通克隆(全量 blob,慢但稳)。timeout 防止代理卡死永久挂起。"""
    args = ["git", "clone", "--depth=1", "--sparse", "--no-checkout"]
    if use_filter:
        args.insert(3, "--filter=blob:none")
    if branch:
        args.append(f"--branch={branch}")
    args.extend([url, str(repo_dir)])
    return run_cmd(args, capture=True, timeout=timeout)


def _sparse_checkout(
    repo_url: str,
    repo_dir: Path,
    output_dir: Path,
    files_to_pull,
    label: str,
    log_callback=None,
    progress_callback=None,
    clone_url: str = None,
    branch: str = None,
) -> bool:
    """通用 Git 稀疏检出流程。

    Args:
        repo_url: 默认仓库 URL
        repo_dir: 本地仓库目录
        output_dir: 输出文件目录
        files_to_pull: 清单 —— 元素可为 "路径"(输出名=basename)
                       或 (路径, 输出文件名)
        label: 日志标签（如 "遗物/物品"）
        log_callback: (level, msg)
        progress_callback: (pct) 或 (stage, cur, total)
        clone_url: 自定义克隆 URL（代理镜像）
        branch: 指定分支（None 则用默认）
    Returns:
        是否成功

    可靠性设计:
      1. 默认 partial clone(--filter=blob:none),服务器不支持时 clone 阶段
         自动回退全量克隆;
      2. checkout 后逐个验证文件真实存在 —— git 对清单中不存在的路径会
         静默成功(exit 0),必须主动验证;
      3. checkout 阶段按需拉 blob 被代理掐断(curl 56 等)时,自动删除仓库、
         改用全量克隆重跑。
    """
    total_steps = 5
    current_step = 0

    file_map = _normalize_file_map(files_to_pull)
    # 非 cone 模式下,前导 / 表示锚定根目录,确保精确匹配单文件
    patterns = ["/" + src for src, _ in file_map]

    def _log(level: str, msg: str):
        if log_callback:
            log_callback(level, msg)

    def _progress(stage: str, cur: int = None, total: int = None, pct: int = None):
        nonlocal current_step
        if progress_callback:
            if pct is not None:
                progress_callback(pct)
            elif cur is not None and total is not None:
                progress_callback(stage, cur, total)

    url = clone_url if clone_url else repo_url

    current_step += 1
    _progress("初始化仓库", current_step, total_steps, int((current_step / total_steps) * 100))

    # 清理旧的
    if repo_dir.exists():
        _log('info', f"\n清理旧仓库: {repo_dir}")
        _rmtree_force(repo_dir)

    # 步骤 1: git clone(优先 partial clone,失败则全量克隆)
    current_step += 1
    _progress("克隆仓库", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', f"\n克隆仓库(partial): {url}")

    code, _, err = _do_clone(url, repo_dir, branch, use_filter=True)
    used_full_clone = False
    if code != 0:
        _log('warn', f"[!] partial clone 失败: {err.strip()}")
        _log('info', "回退: 全量克隆(无 --filter)...")
        if repo_dir.exists():
            _rmtree_force(repo_dir)
        code, _, err = _do_clone(url, repo_dir, branch, use_filter=False)
        if code != 0:
            _log('error', f"[X] 全量克隆也失败: {err}")
            return False
        used_full_clone = True

    def _configure_and_checkout() -> tuple[bool, str, list]:
        """配置稀疏检出 + 执行 checkout + 验证文件。

        返回 (成功, 错误信息, 缺失文件路径)。
        """
        code, _, err = run_cmd(
            ["git", "sparse-checkout", "set", "--no-cone"] + patterns,
            cwd=repo_dir,
        )
        if code != 0:
            return False, f"sparse-checkout 配置失败: {err}", []
        code, _, err = run_cmd(["git", "checkout"], cwd=repo_dir,
                               capture=True, timeout=300)
        if code != 0:
            return False, f"git checkout 失败: {err}", []
        # 关键验证:checkout 对不存在的路径静默成功,必须逐个检查
        missing = [src for src, _ in file_map if not (repo_dir / src).exists()]
        return (not missing), "", missing

    # 步骤 2: 配置要检出的文件
    current_step += 1
    _progress("配置稀疏检出", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', f"配置要检出的文件({len(file_map)} 个):")
    for src, out_name in file_map:
        extra = f" → {out_name}" if out_name != Path(src).name else ""
        _log('info', f"  - {src}{extra}")

    # 步骤 3: 检出文件
    current_step += 1
    _progress("检出文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n检出文件并验证...")

    ok, err, missing = _configure_and_checkout()

    # checkout 阶段 blob 按需拉取失败(代理掐断)→ 全量克隆重跑一次
    if not ok and not used_full_clone:
        _log('warn', f"[!] 检出失败/文件缺失: {err or ('缺失 ' + str(missing))}")
        _log('info', "回退: 删除仓库,改用全量克隆重试...")
        if repo_dir.exists():
            _rmtree_force(repo_dir)
        code, _, err = _do_clone(url, repo_dir, branch, use_filter=False)
        if code != 0:
            _log('error', f"[X] 全量克隆失败: {err}")
            return False
        ok, err, missing = _configure_and_checkout()

    if not ok:
        _log('error', f"[X] 最终检出失败: {err or ('缺失 ' + str(missing))}")
        return False
    _log('ok', f"  全部 {len(file_map)} 个文件检出验证通过")

    # 步骤 4: 复制文件到输出目录
    current_step += 1
    _progress("复制文件", current_step, total_steps, int((current_step / total_steps) * 100))
    _log('info', "\n复制文件到目标目录...")
    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for idx, (src_path, out_name) in enumerate(file_map):
        _progress("复制文件", idx + 1, len(file_map), int((idx + 1) / len(file_map) * 100))
        src_file = repo_dir / src_path
        if src_file.exists():
            dest_file = output_dir / out_name
            try:
                if src_file.samefile(dest_file):
                    _log('info', f"  [OK] {out_name} (已在目标位置)")
                    success_count += 1
                    continue
            except OSError:
                pass
            copied = False
            for attempt in range(5):
                try:
                    shutil.copy2(src_file, dest_file)
                    copied = True
                    break
                except PermissionError:
                    import time as _time
                    if attempt < 4:
                        _log('warn', f"  [!] {out_name} 被占用，等待 1 秒后重试 ({attempt + 1}/5)...")
                        _time.sleep(1)
                    else:
                        _log('error', f"  [X] {out_name} 复制失败: 文件被锁定")
            if copied:
                _log('info', f"  [OK] {out_name}")
                success_count += 1

    # 步骤 5: 完成
    current_step += 1
    _progress("完成", current_step, total_steps, 100)

    _log('info', "\n" + "=" * 80)
    if success_count == len(file_map):
        _log('ok', f"[OK] {label} 全部成功！")
    else:
        _log('warn', f"[!] {label} 完成，部分缺失: {success_count}/{len(file_map)}")
    _log('info', f"  保存位置: {output_dir.absolute()}")
    _log('info', "=" * 80)
    return success_count == len(file_map)


# ============================================================
# 公开接口：各仓库的初始化和更新
# ============================================================

def init_items_sparse_checkout(
    log_callback=None, progress_callback=None, clone_url: str = None,
) -> bool:
    """初始化 warframe-items 稀疏检出仓库。

    必须传 ITEMS_PULL_MAP(含重命名映射),不能传 FILES_TO_PULL —— 后者只有
    源路径,i18n/zh.json 会被 basename 成 zh.json,丢失重命名信息。
    """
    return _sparse_checkout(
        repo_url="https://github.com/WFCD/warframe-items.git",
        repo_dir=REPO_DIR,
        output_dir=OUTPUT_DIR,
        files_to_pull=ITEMS_PULL_MAP,
        label="WFCD/warframe-items 遗物/物品",
        log_callback=log_callback,
        progress_callback=progress_callback,
        clone_url=clone_url,
    )


def update_items_existing(
    log_callback=None, progress_callback=None, clone_url: str = None,
) -> bool:
    """更新已有的 warframe-items 仓库（删除后重建）。"""
    def _log(level, msg):
        if log_callback:
            log_callback(level, msg)
    _log('info', "仓库已存在，删除后重新初始化...")
    if REPO_DIR.exists():
        _rmtree_force(REPO_DIR)
    return init_items_sparse_checkout(
        log_callback=log_callback, progress_callback=progress_callback, clone_url=clone_url,
    )


def init_drop_data_sparse_checkout(
    log_callback=None, progress_callback=None, clone_url: str = None,
) -> bool:
    """初始化 warframe-drop-data 稀疏检出仓库。"""
    return _sparse_checkout(
        repo_url=DROP_REPO_URL,
        repo_dir=DROP_REPO_DIR,
        output_dir=DROP_OUTPUT_DIR,
        files_to_pull=DROP_FILES_TO_PULL,
        label="WFCD/warframe-drop-data 掉落数据",
        log_callback=log_callback,
        progress_callback=progress_callback,
        clone_url=clone_url,
    )


def update_drop_data_existing(
    log_callback=None, progress_callback=None, clone_url: str = None,
) -> bool:
    """更新已有的 drop-data 仓库。"""
    def _log(level, msg):
        if log_callback:
            log_callback(level, msg)
    _log('info', "掉落数据仓库已存在，删除后重新初始化...")
    if DROP_REPO_DIR.exists():
        _rmtree_force(DROP_REPO_DIR)
    return init_drop_data_sparse_checkout(
        log_callback=log_callback, progress_callback=progress_callback, clone_url=clone_url,
    )


def init_i18n_sparse_checkout(
    log_callback=None, progress_callback=None, clone_url: str = None,
) -> bool:
    """初始化 warframe-public-export-plus 翻译数据稀疏检出仓库。"""
    return _sparse_checkout(
        repo_url=I18N_REPO_URL,
        repo_dir=I18N_REPO_DIR,
        output_dir=I18N_OUTPUT_DIR,
        files_to_pull=I18N_FILES_TO_PULL,
        label="calamity-inc/warframe-public-export-plus 翻译数据",
        log_callback=log_callback,
        progress_callback=progress_callback,
        clone_url=clone_url,
        branch=I18N_REPO_BRANCH,
    )


def update_i18n_existing(
    log_callback=None, progress_callback=None, clone_url: str = None,
) -> bool:
    """更新已有的 i18n 仓库。"""
    def _log(level, msg):
        if log_callback:
            log_callback(level, msg)
    _log('info', "翻译数据仓库已存在，删除后重新初始化...")
    if I18N_REPO_DIR.exists():
        _rmtree_force(I18N_REPO_DIR)
    return init_i18n_sparse_checkout(
        log_callback=log_callback, progress_callback=progress_callback, clone_url=clone_url,
    )
