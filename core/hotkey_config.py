"""
热键配置管理模块
- 读写 data/hotkeys.json
- 提供默认热键
- 支持 keyboard 库格式的热键字符串
"""

import json
import os
from pathlib import Path
from typing import Dict

from data.ui_strings import S


# 默认热键
DEFAULT_HOTKEYS = {
    "select": "ctrl+g",           # 框选截图
    "fullscreen": "ctrl+h",       # 全屏截图
    "query_price": "ctrl+t",  # 价格查询（4等分截图+识别+标注）
}

# 可用的修饰键
MODIFIERS = ["ctrl", "alt", "shift", "win"]

# 热键功能说明
HOTKEY_LABELS = {
    "select": S("hotkey", "label_select"),
    "fullscreen": S("hotkey", "label_fullscreen"),
    "query_price": S("hotkey", "label_query_price"),
}


def _config_path() -> str:
    """获取配置文件路径"""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "hotkeys.json")


def load_hotkeys() -> Dict[str, str]:
    """加载热键配置，如果文件不存在或损坏则返回默认值"""
    path = _config_path()
    if not os.path.exists(path):
        return dict(DEFAULT_HOTKEYS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 合并默认值：用户可能只改了部分热键
        result = dict(DEFAULT_HOTKEYS)
        if isinstance(data, dict):
            for key in DEFAULT_HOTKEYS:
                if key in data and isinstance(data[key], str) and data[key].strip():
                    result[key] = data[key].strip().lower()
        return result
    except (json.JSONDecodeError, Exception):
        return dict(DEFAULT_HOTKEYS)


def save_hotkeys(hotkeys: Dict[str, str]) -> bool:
    """保存热键配置"""
    path = _config_path()
    try:
        # 只保存非默认的键（精简文件）
        to_save = {k: v for k, v in hotkeys.items() if v != DEFAULT_HOTKEYS.get(k)}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def validate_hotkey(hotkey_str: str) -> bool:
    """验证热键字符串格式是否合法"""
    if not hotkey_str or not hotkey_str.strip():
        return False

    hk = hotkey_str.strip().lower()
    parts = hk.split("+")

    # 至少需要 1 个修饰键 + 1 个普通键
    if len(parts) < 2:
        return False

    # 最后一个必须是普通键（非修饰键）
    main_key = parts[-1]
    if main_key in MODIFIERS:
        return False

    # 修饰键必须合法
    for p in parts[:-1]:
        if p not in MODIFIERS:
            return False

    return True


# ============================================================
# 功能开关配置（截图后显示哪些功能按钮）
# ============================================================

DEFAULT_FEATURE_TOGGLES = {
    "check_status": True,    # 出入库查询
    "query_parts": True,     # 遗物内容查询
    "translate": False,      # 翻译英文（默认关闭）
}

# 物品区域配置文件路径
def _item_region_config_path() -> str:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "item_region.json")


def load_item_region() -> dict | None:
    """加载用户设置的物品区域。返回 {'x','y','w','h'} 或 None。"""
    path = _item_region_config_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and all(k in data for k in ('x', 'y', 'w', 'h')):
            return data
    except Exception:
        pass
    return None


def save_item_region(region: dict) -> bool:
    """保存物品区域到配置文件。"""
    path = _item_region_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(region, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def _get_feature_toggle_label(key: str) -> str:
    """动态获取功能开关标签（跟随语言预设）。"""
    try:
        from data.ui_strings import S
        return S("feature_toggle", f"label_{key}")
    except Exception:
        pass
    return {
        "check_status": "遗物出/入库态判定（光墓查询）",
        "query_parts": "遗物内含物逆向解析（破壁人协议）",
        "query_price": "跨维度市场价值评估（黑暗森林博弈）",
        "translate": "跨语种符号学映射（智子翻译）",
    }.get(key, key)


def get_feature_toggle_labels() -> dict:
    """获取功能开关标签字典（动态读取）。"""
    return {k: _get_feature_toggle_label(k) for k in DEFAULT_FEATURE_TOGGLES}


# 向后兼容的模块级变量（懒加载）
FEATURE_TOGGLE_LABELS = {k: "" for k in DEFAULT_FEATURE_TOGGLES}

FEATURE_TOGGLE_REQUIRES = {
    # 每个功能需要什么 OCR 类型
    "check_status": "relic",
    "query_parts": "relic",
    "query_price": "item",
    "translate": "text",
}


def _feature_config_path() -> str:
    """获取功能开关配置文件路径。"""
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "feature_toggles.json")


def load_feature_toggles() -> dict:
    """加载功能开关配置，不存在则返回默认值。"""
    path = _feature_config_path()
    if not os.path.exists(path):
        return dict(DEFAULT_FEATURE_TOGGLES)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = dict(DEFAULT_FEATURE_TOGGLES)
        if isinstance(data, dict):
            for key in DEFAULT_FEATURE_TOGGLES:
                if key in data:
                    result[key] = bool(data[key])
        return result
    except (json.JSONDecodeError, Exception):
        return dict(DEFAULT_FEATURE_TOGGLES)


def save_feature_toggles(toggles: dict) -> bool:
    """保存功能开关配置。"""
    path = _feature_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(toggles, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


# ============================================================
# GitHub 镜像 / 代理配置
# ============================================================

DEFAULT_GITHUB_MIRROR = ""  # 默认直连，如需加速可填 https://gh-proxy.com/


def _mirror_config_path() -> str:
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "mirror_config.json")


def load_github_mirror() -> str:
    """加载 GitHub 镜像配置。"""
    path = _mirror_config_path()
    if not os.path.exists(path):
        return DEFAULT_GITHUB_MIRROR
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("github_mirror", DEFAULT_GITHUB_MIRROR)).strip()
    except (json.JSONDecodeError, Exception):
        return DEFAULT_GITHUB_MIRROR


def save_github_mirror(mirror: str, gitee_username: str = None) -> bool:
    """保存 GitHub 镜像配置。

    Args:
        mirror: 镜像类型 ("", "jsdelivr", "gitee", 或代理 URL)
        gitee_username: Gitee 用户名（当 mirror 为 "gitee" 时使用）
    """
    path = _mirror_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            config = {"github_mirror": mirror.strip()}
            if gitee_username:
                config["gitee_username"] = gitee_username.strip()
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_gitee_username() -> str:
    """加载 Gitee 用户名。"""
    path = _mirror_config_path()
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("gitee_username", "")).strip()
    except (json.JSONDecodeError, Exception):
        return ""


# jsDelivr CDN 多源端点（按优先级排序）
JSDELIVR_ENDPOINTS = [
    "cdn.jsdelivr.net",      # 主端点
    "fastly.jsdelivr.net",   # Fastly CDN 备份
    "gcore.jsdelivr.net",    # Gcore CDN 备份
]

# 当前使用的 jsDelivr 端点索引
_current_jsdelivr_index = 0


def resolve_github_url(url: str, mirror: str = None) -> str:
    """将 GitHub raw URL 解析为实际下载地址。

    - 如果 mirror 为空，返回原始 URL
    - 如果 mirror 以 http:// 或 https:// 开头，作为前缀代理（如 ghproxy.com）
    - 如果 mirror 是 "jsdelivr"，使用 jsDelivr CDN 格式（多源容灾）
    - 如果 mirror 是 "gitee"，使用 Gitee 镜像（需配置用户名）
    - 否则作为域名替换（如 raw.kgithub.com 替换 raw.githubusercontent.com）

    jsDelivr 格式转换示例：
    - 原始: https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/all.json
    - jsDelivr: https://cdn.jsdelivr.net/gh/WFCD/warframe-drop-data@main/data/all.json

    Gitee 格式转换示例：
    - 原始: https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/all.json
    - Gitee: https://gitee.com/{username}/warframe-drop-data/raw/main/data/all.json
    """
    import re
    if mirror is None:
        mirror = load_github_mirror()
    mirror = mirror.strip()
    if not mirror:
        return url

    if mirror == "gitee":
        # Gitee 镜像模式
        # 仅支持 warframe-drop-data 仓库（已成功导入 Gitee）
        # 其他仓库（如 warframe-items）保持原始 URL
        gitee_username = load_gitee_username()
        if not gitee_username:
            # 未配置 Gitee 用户名，回退到直连
            return url
        # 匹配 GitHub raw URL: https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}
        match = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)", url)
        if match:
            user, repo, branch, path = match.groups()
            # warframe-drop-data 仓库使用 Gitee
            if repo == "warframe-drop-data":
                return f"https://gitee.com/{gitee_username}/{repo}/raw/{branch}/{path}"
            # 其他仓库保持原始 URL
        return url

    if mirror == "jsdelivr":
        # → https://{endpoint}/gh/{user}/{repo}@{branch}/{path}
        import re
        match = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)", url)
        if match:
            user, repo, branch, path = match.groups()
            endpoint = JSDELIVR_ENDPOINTS[_current_jsdelivr_index]
            return f"https://{endpoint}/gh/{user}/{repo}@{branch}/{path}"
        return url
    if mirror.startswith("http://") or mirror.startswith("https://"):
        # 前缀代理模式: https://ghproxy.com/https://raw.githubusercontent.com/...
        return mirror.rstrip("/") + "/" + url
    else:
        # 域名替换模式: raw.kgithub.com 替换 raw.githubusercontent.com
        return url.replace("raw.githubusercontent.com", mirror)


def switch_jsdelivr_endpoint() -> str:
    """切换到下一个 jsDelivr CDN 端点（用于故障切换）。

    Returns:
        新的端点域名
    """
    global _current_jsdelivr_index
    _current_jsdelivr_index = (_current_jsdelivr_index + 1) % len(JSDELIVR_ENDPOINTS)
    return JSDELIVR_ENDPOINTS[_current_jsdelivr_index]


def get_current_jsdelivr_endpoint() -> str:
    """获取当前使用的 jsDelivr CDN 端点。"""
    return JSDELIVR_ENDPOINTS[_current_jsdelivr_index]


def get_all_jsdelivr_endpoints() -> list:
    """获取所有可用的 jsDelivr CDN 端点。"""
    return JSDELIVR_ENDPOINTS.copy()
