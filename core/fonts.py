"""
[L0/L1] core.fonts — 内嵌字体管理器

将 assets/fonts/ 下的 .ttf/.otf 文件注册到 QApplication,
使项目不依赖用户系统安装的字体。

依赖: PySide6.QtGui.QFontDatabase
职责: 启动时一次性注册所有内嵌字体,后续通过字体名访问
被谁用: 任何创建 QFont 的模块

使用方式::

    from core.fonts import FontManager
    FontManager.register_all()   # 启动时调用一次

    # 之后直接用字体常量创建 QFont（禁止再写字面量）
    from PySide6.QtGui import QFont
    from core.fonts import FONT_DISPLAY
    font = QFont(FONT_DISPLAY, 12)

## AI 硬约束 — 修改本文件前必读
归属层:    [L0/L1] (core/ 根目录,跨层桥接/全局管理器)
允许依赖:  视文件而定(本层可持有 widget 引用作桥接,但不实现绘制)
禁止依赖:  根目录 .py 不允许做业务实现 → 业务放 core/services/
必读规范:  .trae/rules/开发规范.md §6.7

本文件相关红线:
- 禁止根目录 .py 持有 widget 绘制逻辑 → 视觉交给 core/widgets/
- 禁止硬编码资源路径 → 必须 core.constants 取
- 禁止在根目录定义业务类 → 业务放对应层
- 禁止反向调用 UI(从 Service → Widget) → 单向数据流
- 禁止 try/except: pass 吞错 → 必须记录到日志或抛给上层

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.7,别走捷径。
"""

from __future__ import annotations

import os

from core.paths import resource_root as _resource_root

# ══════════════════════════════════════════════
#  内嵌字体清单（文件名 → 逻辑名称）
#  逻辑名称就是 QFont() 中使用的 family 名字
# ══════════════════════════════════════════════

FONTS = {
    "Iceberg-Regular.ttf":                  "Iceberg",
    "Monoton-Regular.ttf":                  "Monoton",
    "AlibabaPuHuiTi-3-45-Light.ttf":        "Alibaba PuHuiTi 3",
}

# ══════════════════════════════════════════════
#  字体族常量 —— 全项目唯一来源
#
#  代码里禁止再写字面量 QFont("Iceberg") / QFont("Consolas")，
#  统一使用以下常量：换字体、补字重、加回退只需改这里。
#  QSS 里的 font-family 栈(含 fallback 顺序)是另一回事，仍按上下文书写。
# ══════════════════════════════════════════════
FONT_DISPLAY = "Iceberg"            # 标题 / 强调（内嵌字体）
FONT_ACCENT = "Monoton"             # 数字 / 大字号装饰（内嵌字体）
FONT_UI = "Alibaba PuHuiTi 3"       # 正文（内嵌字体）
FONT_FALLBACK = "Microsoft YaHei"   # 内嵌字体不可用时的系统回退
FONT_MONO = "Consolas"              # 等宽：激活码 / 日志 / 坐标

# 字体目录(assets 随包分发;打包/开发环境自适应,见 core.paths)
_FONTS_DIR = str(_resource_root() / "assets" / "fonts")

# 已注册标记
_registered: bool = False


def register_all() -> list[str]:
    """注册所有内嵌字体到 Qt 字体数据库。

    应在创建 QApplication 之后、任何 UI 组件之前调用（仅一次）。

    Returns:
        成功注册的字体逻辑名称列表。
    """
    global _registered
    if _registered:
        return []

    from PySide6.QtGui import QFontDatabase

    ok_names: list[str] = []
    fonts_dir = os.path.abspath(_FONTS_DIR)

    for filename, family in FONTS.items():
        path = os.path.join(fonts_dir, filename)
        if not os.path.exists(path):
            print(f"[Fonts] 文件不存在: {path}", flush=True)
            continue

        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            print(f"[Fonts] 注册失败: {filename}", flush=True)
            continue

        # 验证注册后的实际 family 名称
        families = QFontDatabase.applicationFontFamilies(font_id)
        actual_family = families[0] if families else family
        ok_names.append(actual_family)
        print(f"[Fonts] 已注册: {filename} → \"{actual_family}\"", flush=True)

    _registered = True
    return ok_names


def get(family: str, fallback: str = "Microsoft YaHei UI") -> str:
    """获取字体 family 名称，已注册则返回内嵌字体，否则返回 fallback。

    Args:
        family: 期望的字体系列名（如 "Iceberg"）
        fallback: 未注册时的回退字体

    Returns:
        实际可用的字体系列名。
    """
    from PySide6.QtGui import QFontDatabase
    # 检查该 family 是否在已注册字体中
    for _, reg_family in FONTS.items():
        if reg_family == family and _registered:
            return family
    return fallback
