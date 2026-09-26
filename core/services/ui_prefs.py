"""
[L-Service] core.services.ui_prefs — 全局 UI 偏好(主窗口透明度/背景图等)

依赖: Python 标准库(json / pathlib)
禁止: PySide6, QtWidgets, QtGui, QtCore
职责:
  - 读写 data/ui_prefs.json
  - 提供 window_opacity 的 load / save 接口
  - 提供 background(背景图路径/透明度/模糊度)的 load / save 接口
  - 自动钳制有效范围 + 损坏文件回退默认

设计要点:
  - 用纯模块函数(参考 hotkey_config.py),不引入 QObject
  - 后续若需"任意 widget 订阅变化"再加 Signal,但当前无此需求
  - 读旧值时做 merge,保留扩展字段
"""

from __future__ import annotations

import json
from pathlib import Path

# ── 常量 ──
# 100 = 完全不透明(默认),30 = 几乎透明(再低就看不清文字了)
_DEFAULT_OPACITY: int = 100
_MIN_OPACITY: int = 30
_MAX_OPACITY: int = 100

# JSON key(所有 UI 偏好都进 ui_prefs.json 这一个文件)
_KEY_OPACITY: str = "window_opacity"
_KEY_BACKGROUND: str = "background"
_KEY_THEME_PRESET: str = "theme_preset"

# 背景图配置默认值
# source: data/backgrounds/ 下保存的原图文件名(空串=未设置)
# crop:   用户选区 [x,y,w,h](原图像素)；None = 使用整图
# opacity/blur: 0-100 的 100 档
# immersive: 是否开启全局沉浸模式(导航栏/卡片透出壁纸)
# immersive_strength: 沉浸强度 0-100，越大底色越透(壁纸露出越多)
# immersive_color: 沉浸底色预设 "theme"=沿用 token 当前主题底色 / "black"=纯黑
_DEFAULT_BACKGROUND: dict = {
    "source": "", "crop": None, "opacity": 100, "blur": 0,
    "immersive": False, "immersive_strength": 70,
    "immersive_color": "theme",
}

# 主题预设默认值(cyberpunk=默认赛博朋克风)
_DEFAULT_THEME_PRESET: str = "cyberpunk"


# ── 路径 ──

def _prefs_path() -> Path:
    """获取 ui_prefs.json 的绝对路径(打包/开发环境自适应,见 core.paths)。

    开发:   <项目根>/data/ui_prefs.json
    打包:   <exe旁>/data/ui_prefs.json(不可写时降级 %LOCALAPPDATA%)
    """
    from core.paths import ensure_user_file
    return ensure_user_file("ui_prefs.json")


# ── 公开 API ──

def load_window_opacity() -> int:
    """读取主窗口透明度百分比(返回 30-100 之间的整数)。

    失败兜底(文件不存在/JSON 损坏/字段缺失/越界):返回 _DEFAULT_OPACITY = 100。
    """
    raw = _read_all().get(_KEY_OPACITY, _DEFAULT_OPACITY)
    try:
        return _clamp_0_100(int(raw), low=_MIN_OPACITY)
    except (TypeError, ValueError):
        return _DEFAULT_OPACITY


def save_window_opacity(pct: int) -> bool:
    """保存主窗口透明度百分比。

    行为:
      - 自动钳制 30-100(传 -1 或 999 都会被拉回 30 / 100)
      - 读旧 JSON,合并字段(保留其它 key)
      - 失败返回 False(不抛异常,UI 不感知)
    """
    data = _read_all()
    data[_KEY_OPACITY] = _clamp_0_100(int(pct), low=_MIN_OPACITY)
    return _write_all(data)


def load_background_prefs() -> dict:
    """读取背景图配置,返回 {source, crop, opacity, blur, immersive, immersive_strength}。

    - source:  data/backgrounds/ 下的原图文件名(str)，空串=未设置
    - crop:    用户选区 [x,y,w,h](原图像素)；None = 使用整图
    - opacity: 图片不透明度 0-100
    - blur:    模糊强度 0-100
    - immersive: 全局沉浸模式开关(bool)
    - immersive_strength: 沉浸强度 0-100
    - immersive_color: 沉浸底色预设 "theme"/"black"

    兼容旧版配置(旧 ``path`` 字段映射为 source、crop=None)。
    任何字段缺失/损坏均回落默认值，保证返回结构完整。
    """
    raw = _read_all().get(_KEY_BACKGROUND)
    if not isinstance(raw, dict):
        return dict(_DEFAULT_BACKGROUND)

    result = dict(_DEFAULT_BACKGROUND)

    # source：新字段优先，兼容旧 path
    src = raw.get("source", raw.get("path", ""))
    result["source"] = src if isinstance(src, str) else ""

    # crop：必须是 4 个非负整数
    crop = raw.get("crop")
    if isinstance(crop, list) and len(crop) == 4:
        try:
            vals = [int(v) for v in crop]
            if all(v >= 0 for v in vals) and vals[2] > 0 and vals[3] > 0:
                result["crop"] = vals
        except (TypeError, ValueError):
            result["crop"] = None

    try:
        result["opacity"] = _clamp_0_100(int(raw.get("opacity", 100)))
    except (TypeError, ValueError):
        result["opacity"] = _DEFAULT_BACKGROUND["opacity"]
    try:
        result["blur"] = _clamp_0_100(int(raw.get("blur", 0)))
    except (TypeError, ValueError):
        result["blur"] = _DEFAULT_BACKGROUND["blur"]

    # immersive：只接受 bool（其它类型按 False）
    iv = raw.get("immersive", False)
    result["immersive"] = iv if isinstance(iv, bool) else False
    try:
        result["immersive_strength"] = _clamp_0_100(
            int(raw.get("immersive_strength", 70))
        )
    except (TypeError, ValueError):
        result["immersive_strength"] = _DEFAULT_BACKGROUND["immersive_strength"]
    # immersive_color：只接受 "theme"/"black"，其它值按 "theme"
    ic = raw.get("immersive_color", "theme")
    result["immersive_color"] = ic if ic in ("theme", "black") else "theme"
    return result


def save_background_prefs(
    source: str,
    crop: list | None,
    opacity: int,
    blur: int,
    immersive: bool = False,
    immersive_strength: int = 70,
    immersive_color: str = "theme",
) -> bool:
    """保存背景图配置(原图/选区/透明度/模糊度/沉浸开关/沉浸强度/沉浸底色)。

    crop 为 None 表示整图；自动钳制数值；合并写入，不影响其它字段。
    immersive_color 仅接受 "theme"/"black"，其它值按 "theme"。
    失败返回 False。
    """
    data = _read_all()
    data[_KEY_BACKGROUND] = {
        "source": str(source),
        "crop": list(crop) if crop is not None else None,
        "opacity": _clamp_0_100(int(opacity)),
        "blur": _clamp_0_100(int(blur)),
        "immersive": bool(immersive),
        "immersive_strength": _clamp_0_100(int(immersive_strength)),
        "immersive_color": immersive_color if immersive_color in ("theme", "black") else "theme",
    }
    return _write_all(data)


# ── 主题预设 ──

def load_theme_preset() -> str:
    """读取主题预设名(返回 "cyberpunk" / "glassmorphism" 等)。

    失败兜底(文件不存在/JSON 损坏/字段缺失):返回 _DEFAULT_THEME_PRESET = "cyberpunk"。
    """
    raw = _read_all().get(_KEY_THEME_PRESET, _DEFAULT_THEME_PRESET)
    return str(raw) if isinstance(raw, str) else _DEFAULT_THEME_PRESET


def save_theme_preset(name: str) -> bool:
    """保存主题预设名。

    行为:
      - 读旧 JSON,合并字段(保留其它 key)
      - 失败返回 False(不抛异常,UI 不感知)
    """
    data = _read_all()
    data[_KEY_THEME_PRESET] = str(name)
    return _write_all(data)


# ── 内部 ──

def _read_all() -> dict:
    """读取完整偏好 dict。任何失败都返回空 dict(不抛异常)。"""
    path = _prefs_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_all(data: dict) -> bool:
    """整体写入偏好 dict。失败返回 False(不抛异常)。"""
    try:
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def _clamp_0_100(v: int, low: int = 0) -> int:
    """把 int 钳制到 [low, 100]。"""
    return max(low, min(100, v))
