"""
WARFRAME-RELIC 版本配置文件

集中管理项目版本信息，便于后续更新维护。
"""

# 主版本号
MAJOR_VERSION = 3
# 次版本号
MINOR_VERSION = 2
# 修订号
PATCH_VERSION = 0

# 完整版本字符串
VERSION = f"{MAJOR_VERSION}.{MINOR_VERSION}.{PATCH_VERSION}"

# 版本标签（可选，如 "beta", "alpha", "rc1"）
VERSION_TAG = ""

# 完整版本标识（含标签）
if VERSION_TAG:
    FULL_VERSION = f"v{VERSION}-{VERSION_TAG}"
else:
    FULL_VERSION = f"v{VERSION}"

# 项目名称
PROJECT_NAME = "WARFRAME-RELIC"

# 项目全称（用于显示）
PROJECT_FULL_NAME = f"{PROJECT_NAME} {FULL_VERSION}"

# 作者信息
AUTHOR = "NeonXi"
AUTHOR_BILIBILI = "MichaelJackso2"

# 仓库地址
REPO_URL = "https://github.com/NeonXi/WARFRAME-RELIC"
BILIBILI_URL = "https://space.bilibili.com/35143377"

# 版本描述（简短介绍）
VERSION_DESCRIPTION = "Warframe 遗物实时 OCR 辅助工具"

# 版本历史
VERSION_HISTORY = [
    ("3.2.0", "2024-01-XX", "新增价格查询快捷键、主题换肤系统、语言预设切换"),
    ("3.1.0", "2024-01-XX", "优化 OCR 识别精度，添加模糊匹配引擎"),
    ("3.0.0", "2024-01-XX", "重构核心架构，支持多显示器 DPI 适配"),
    ("2.0.0", "2023-12-XX", "赛博朋克2077风格 UI 重设计"),
    ("1.0.0", "2023-11-XX", "初始版本发布"),
]
