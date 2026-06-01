"""
WARFRAME-RELIC 图标配置文件

集中管理项目中使用的所有图标，便于维护和主题更换。

图标风格方案：
- STYLE_ASCII:    ASCII极简线条风格（简洁硬朗）
- STYLE_GEOMETRY: 几何符号风格（圆润现代）
- STYLE_LINEART:  线框艺术风格（科技感）
- STYLE_BOX:      方块组合风格（赛博朋克）
"""

# ============================================================
# 图标风格选择
# 可选值: "ascii", "geometry", "lineart", "box"
# ============================================================
ACTIVE_STYLE = "ascii"

# ============================================================
# ASCII 极简线条风格（简洁硬朗，适合高对比度显示）
# ============================================================
STYLE_ASCII = {
    "nav": {
        "toggles":     "[",    # 功能开关
        "status":      "#",    # 数据状态
        "relic":       "<>",   # 遗物更新
        "trans":       "/\\",   # 翻译库
        "items":       "?",    # 物品查询
        "prices":      "$",    # 价格数据
        "hotkeys":     "=",    # 快捷键
        "theme":       "#",    # 主题换肤
        "about":       "i",    # 关于
        "reset":       "!",    # 紧急重置
    },
    "action": {
        "check_status": "[",   # 出入库查询
        "query_parts":  "O",   # 遗物内容查询
        "query_price":  "$",   # 价格查询
        "translate":    "<>",  # 翻译
    },
    "status": {
        "success":     "+",
        "error":       "-",
        "warning":     "^",
        "info":        "*",
        "loading":     "~",
    },
    "platform": {
        "bilibili":    "B",
        "github":      "G",
        "website":     "W",
    }
}

# ============================================================
# 几何符号风格（圆润现代，清晰易辨）
# ============================================================
STYLE_GEOMETRY = {
    "nav": {
        "toggles":     "⚫",    # 功能开关
        "status":      "⚪",    # 数据状态
        "relic":       "◎",    # 遗物更新
        "trans":       "○",    # 翻译库
        "items":       "◇",    # 物品查询
        "prices":      "●",    # 价格数据
        "hotkeys":     "◉",    # 快捷键
        "theme":       "◐",    # 主题换肤
        "about":       "○",    # 关于
        "reset":       "◎",    # 紧急重置
    },
    "action": {
        "check_status": "□",   # 出入库查询
        "query_parts":  "◎",   # 遗物内容查询
        "query_price":  "◇",   # 价格查询
        "translate":    "△",   # 翻译
    },
    "status": {
        "success":     "✓",
        "error":       "✕",
        "warning":     "▲",
        "info":        "●",
        "loading":     "◎",
    },
    "platform": {
        "bilibili":    "●",
        "github":      "○",
        "website":     "□",
    }
}

# ============================================================
# 线框艺术风格（科技感，线条硬朗）
# ============================================================
STYLE_LINEART = {
    "nav": {
        "toggles":     "⊞",    # 功能开关
        "status":      "⊡",    # 数据状态
        "relic":       "⊜",    # 遗物更新
        "trans":       "⊠",    # 翻译库
        "items":       "⊤",    # 物品查询
        "prices":      "⊥",    # 价格数据
        "hotkeys":     "⊢",    # 快捷键
        "theme":       "⊣",    # 主题换肤
        "about":       "⊤",    # 关于
        "reset":       "⊥",    # 紧急重置
    },
    "action": {
        "check_status": "⊞",   # 出入库查询
        "query_parts":  "⊡",   # 遗物内容查询
        "query_price":  "⊜",   # 价格查询
        "translate":    "⊠",   # 翻译
    },
    "status": {
        "success":     "⊢",
        "error":       "⊣",
        "warning":     "⊤",
        "info":        "⊡",
        "loading":     "⊜",
    },
    "platform": {
        "bilibili":    "⊞",
        "github":      "⊡",
        "website":     "⊠",
    }
}

# ============================================================
# 方块组合风格（赛博朋克风格，高辨识度）
# ============================================================
STYLE_BOX = {
    "nav": {
        "toggles":     "▢",    # 功能开关
        "status":      "▣",    # 数据状态
        "relic":       "▤",    # 遗物更新
        "trans":       "▥",    # 翻译库
        "items":       "▦",    # 物品查询
        "prices":      "▧",    # 价格数据
        "hotkeys":     "▨",    # 快捷键
        "theme":       "▩",    # 主题换肤
        "about":       "▢",    # 关于
        "reset":       "▣",    # 紧急重置
    },
    "action": {
        "check_status": "▢",   # 出入库查询
        "query_parts":  "▣",   # 遗物内容查询
        "query_price":  "▤",   # 价格查询
        "translate":    "▥",   # 翻译
    },
    "status": {
        "success":     "▤",
        "error":       "▧",
        "warning":     "▣",
        "info":        "▢",
        "loading":     "▨",
    },
    "platform": {
        "bilibili":    "▣",
        "github":      "▢",
        "website":     "▤",
    }
}

# ============================================================
# 获取当前风格的图标
# ============================================================

def _get_style_data():
    """获取当前激活的图标风格数据"""
    style_map = {
        "ascii": STYLE_ASCII,
        "geometry": STYLE_GEOMETRY,
        "lineart": STYLE_LINEART,
        "box": STYLE_BOX,
    }
    return style_map.get(ACTIVE_STYLE, STYLE_ASCII)

def get_nav_icon(nav_id: str) -> str:
    """获取导航栏图标"""
    return _get_style_data()["nav"].get(nav_id, "●")

def get_action_icon(action_id: str) -> str:
    """获取功能按钮图标"""
    return _get_style_data()["action"].get(action_id, "●")

def get_status_icon(status_type: str) -> str:
    """获取状态指示图标"""
    return _get_style_data()["status"].get(status_type, "●")

def get_platform_icon(platform: str) -> str:
    """获取平台图标"""
    return _get_style_data()["platform"].get(platform, "●")

# ============================================================
# 风格预览
# ============================================================

def preview_styles():
    """输出所有风格的预览"""
    styles = ["ascii", "geometry", "lineart", "box"]
    for style in styles:
        print(f"\n{'='*40}")
        print(f"风格: {style}")
        print(f"{'='*40}")
        data = {
            "ascii": STYLE_ASCII,
            "geometry": STYLE_GEOMETRY,
            "lineart": STYLE_LINEART,
            "box": STYLE_BOX,
        }[style]
        print("导航图标:")
        for k, v in data["nav"].items():
            print(f"  {k}: {v}")
        print("\n功能图标:")
        for k, v in data["action"].items():
            print(f"  {k}: {v}")

if __name__ == "__main__":
    preview_styles()
