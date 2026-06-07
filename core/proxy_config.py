"""
代理镜像配置管理模块

管理 GitHub 代理镜像列表及其连通性测试结果。
配置文件: data/proxy_mirrors.json

每个仓库独立记录测试结果，支持智能选择上次成功的代理。
"""
import json
import subprocess
import time
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "proxy_mirrors.json"

# 仓库配置: (repo_name, owner, repo)
_REPO_DEFS = {
    "warframe-items": ("WFCD", "warframe-items"),
    "warframe-drop-data": ("WFCD", "warframe-drop-data"),
    "warframe-public-export-plus": ("calamity-inc", "warframe-public-export-plus"),
}

_DEFAULT_MIRRORS = [
    "https://github.com.cnpmjs.org/{owner}/{repo}.git",
    "https://ghfast.top/https://github.com/{owner}/{repo}.git",
    "https://mirror.ghproxy.com/https://github.com/{owner}/{repo}.git",
    "https://ghproxy.com/https://github.com/{owner}/{repo}.git",
    "https://gitclone.com/github.com/{owner}/{repo}.git",
    "https://github.com/{owner}/{repo}.git",
]


def _load() -> dict:
    """加载代理镜像配置。"""
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"mirrors": list(_DEFAULT_MIRRORS), "repo_test_results": {}}


def _save(data: dict):
    """保存代理镜像配置。"""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_mirrors() -> list:
    """获取当前代理镜像列表。"""
    return _load().get("mirrors", list(_DEFAULT_MIRRORS))


def set_mirrors(mirrors: list):
    """设置代理镜像列表（不改变测试结果）。"""
    data = _load()
    data["mirrors"] = mirrors
    _save(data)


def get_default_mirrors() -> list:
    """获取默认代理镜像列表。"""
    return list(_DEFAULT_MIRRORS)


def get_config_path() -> str:
    """获取配置文件路径（用于 UI 提示）。"""
    return str(_CONFIG_PATH.resolve())


def get_repo_defs() -> dict:
    """获取所有仓库定义。"""
    return dict(_REPO_DEFS)


def _get_test_results(repo_name: str) -> dict:
    """获取指定仓库的测试结果。"""
    data = _load()
    return data.get("repo_test_results", {}).get(repo_name, {})


def _set_test_results(repo_name: str, results: dict):
    """设置指定仓库的测试结果。"""
    data = _load()
    if "repo_test_results" not in data:
        data["repo_test_results"] = {}
    data["repo_test_results"][repo_name] = results
    _save(data)


def get_sorted_mirrors(repo_name: str) -> list:
    """获取按优先级排序的代理镜像列表（上次成功的排前面）。

    返回: [(url_template, index), ...]
    """
    mirrors = get_mirrors()
    results = _get_test_results(repo_name)
    last_success = results.get("last_successful_index", None)

    indexed = list(enumerate(mirrors))

    if last_success is not None and 0 <= last_success < len(mirrors):
        # 把上次成功的排到第一位
        successful = indexed.pop(last_success)
        indexed.insert(0, successful)

    # 然后按测试通过状态排序
    tested = results.get("tested_mirrors", {})
    # 分离测试通过和未测试/失败的
    passed = []
    failed_or_untested = []
    for idx, url in indexed:
        if idx == (last_success if last_success is not None else -1):
            continue  # 已排第一
        if tested.get(str(idx), False):
            passed.append((idx, url))
        else:
            failed_or_untested.append((idx, url))

    # 上次成功排第一，然后测试通过的，然后其他的
    if last_success is not None and 0 <= last_success < len(mirrors):
        result = [(last_success, mirrors[last_success])]
    else:
        result = []
    result.extend(passed)
    result.extend(failed_or_untested)
    return result


def update_test_result(repo_name: str, mirror_index: int, success: bool):
    """更新单个镜像的测试结果。"""
    results = _get_test_results(repo_name)
    if "tested_mirrors" not in results:
        results["tested_mirrors"] = {}
    results["tested_mirrors"][str(mirror_index)] = success
    if success:
        results["last_successful_index"] = mirror_index
    _set_test_results(repo_name, results)


def test_repo_mirror(repo_name: str, mirror_template: str, timeout: int = 10) -> bool:
    """测试指定仓库的指定镜像是否可用。

    使用 git ls-remote --heads 快速检测连通性（只拉引用列表，几 KB）。

    Args:
        repo_name: 仓库名 (对应 _REPO_DEFS 的 key)
        mirror_template: 代理 URL 模板，如 "https://github.com.cnpmjs.org/{owner}/{repo}.git"
        timeout: 超时秒数

    Returns:
        True 表示连通成功
    """
    if repo_name not in _REPO_DEFS:
        return False

    owner, repo = _REPO_DEFS[repo_name]
    try:
        url = mirror_template.format(owner=owner, repo=repo)
    except (KeyError, ValueError):
        return False

    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", url],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def resolve_url(repo_name: str, mirror_template: str) -> Optional[str]:
    """将模板解析为实际 URL。

    Args:
        repo_name: 仓库名
        mirror_template: 代理 URL 模板

    Returns:
        解析后的完整 URL，失败返回 None
    """
    if repo_name not in _REPO_DEFS:
        return None
    owner, repo = _REPO_DEFS[repo_name]
    try:
        return mirror_template.format(owner=owner, repo=repo)
    except (KeyError, ValueError):
        return None


def clear_test_results(repo_name: str = None):
    """清除测试结果。

    Args:
        repo_name: 仓库名，None 表示清除所有
    """
    data = _load()
    if repo_name is None:
        data["repo_test_results"] = {}
    elif repo_name in data.get("repo_test_results", {}):
        del data["repo_test_results"][repo_name]
    _save(data)