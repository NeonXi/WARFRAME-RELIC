"""
WARFRAME-RELIC 图标加载器

支持多种图标格式：
1. Unicode Emoji 图标（内置）
2. SVG 图标文件
3. 自定义字体图标
4. PNG 图标文件

图标文件搜索路径：
1. project_root/icon/ - 用户自定义图标库（Unoline）
2. project_root/assets/icons/ - 内置图标目录
"""

import os
from pathlib import Path

# 图标资源目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_DIR = _PROJECT_ROOT / 'assets'
_BUILTIN_ICONS_DIR = _ASSETS_DIR / 'icons'
_CUSTOM_ICONS_DIR = _PROJECT_ROOT / 'icon'

# ============================================================
# 图标映射配置
# 将项目内部图标 ID 映射到图标文件名
# 使用 unoline-icons 图标库
# ============================================================
ICON_MAPPINGS = {
    "nav": {
        "toggles":     "hard drive",   # 功能开关 - 硬盘图标代表功能模块
        "status":      "profile",      # 数据状态 - 个人资料图标代表状态信息
        "db_center":       "reload_right", # 数据管理 - 刷新图标代表数据库管理
        "trans":       "mail",         # 翻译库 - 邮件图标代表语言转换
        "items":       "search",       # 物品查询 - 搜索图标
        "prices":      "card",         # 价格数据 - 卡片图标代表价格
        "hotkeys":     "write",        # 快捷键 - 写入图标代表配置编辑
        "theme":       "smartphone",   # 主题换肤 - 手机图标代表外观定制
        "preset":      "notebook",     # 语言预设 - 笔记本图标代表文案配置
        "about":       "message",      # 关于 - 消息图标代表信息
        "reset":       "shield",       # 紧急重置 - 盾牌图标代表安全保护
    },
    "action": {
        "check_status": "folder",      # 出入库查询 - 文件夹图标代表状态检查
        "query_parts":  "notebook",    # 遗物内容查询 - 笔记本图标代表详细记录
        "query_price":  "battery",     # 价格查询 - 电池图标代表能量/价值
        "translate":    "time",        # 翻译 - 时间图标代表转换过程
    },
    "platform": {
        "bilibili":    "message",      # B站 - 使用消息图标作为视频平台替代
        "github":      "Github",       # GitHub
    }
}

# ============================================================
# 内置图标（作为 fallback）
# ============================================================
FALLBACK_ICONS = {
    "nav": {
        "toggles":     "⚙",
        "status":      "📊",
        "db_center":       "🔄",
        "trans":       "🌐",
        "items":       "🔍",
        "prices":      "💰",
        "hotkeys":     "⌨",
        "theme":       "🎨",
        "about":       "ℹ",
        "reset":       "⚠",
    },
    "action": {
        "check_status": "⊞",
        "query_parts":  "◎",
        "query_price":  "⟐",
        "translate":    "⬢",
    },
    "platform": {
        "bilibili":    "📺",
        "github":      "💻",
    }
}

# ============================================================
# 图标文件搜索路径（按优先级排序）
# ============================================================
def _get_icon_search_paths() -> list:
    """获取图标文件搜索路径列表"""
    paths = []
    
    # 1. 用户自定义图标库（Unoline）
    unoline_dir = _CUSTOM_ICONS_DIR / 'unoline-icons' / 'Unoline'
    if unoline_dir.exists():
        paths.append(unoline_dir / 'Essentials')
        paths.append(unoline_dir / 'Navigation')
        paths.append(unoline_dir / 'Social')
    
    # 2. 内置图标目录
    if _BUILTIN_ICONS_DIR.exists():
        paths.append(_BUILTIN_ICONS_DIR)
    
    return paths

# ============================================================
# 图标加载器类
# ============================================================

class IconLoader:
    """图标加载器 - 支持多种图标格式"""
    
    def __init__(self):
        self._icon_cache = {}  # 缓存已加载的图标
        self._qt_available = False
        self._QIcon = None
        self._QPixmap = None
        self._search_paths = _get_icon_search_paths()
        
    def _ensure_qt_imported(self):
        """延迟导入 Qt 模块"""
        if not self._qt_available:
            try:
                from PyQt6.QtGui import QIcon, QPixmap
                self._QIcon = QIcon
                self._QPixmap = QPixmap
                self._qt_available = True
            except ImportError:
                self._qt_available = False
    
    def _find_icon_file(self, icon_name: str) -> Path:
        """在搜索路径中查找图标文件"""
        for search_path in self._search_paths:
            for ext in ['.svg', '.png']:
                # 尝试原始名称
                filepath = search_path / f"{icon_name}{ext}"
                if filepath.exists():
                    return filepath
                # 尝试去掉空格的名称
                filepath = search_path / f"{icon_name.replace(' ', '')}{ext}"
                if filepath.exists():
                    return filepath
                # 尝试下划线替换空格
                filepath = search_path / f"{icon_name.replace(' ', '_')}{ext}"
                if filepath.exists():
                    return filepath
        return None
    
    def load_svg_icon(self, icon_name: str, size: int = 24):
        """加载 SVG 图标文件"""
        self._ensure_qt_imported()
        if not self._qt_available:
            return None
            
        filepath = self._find_icon_file(icon_name)
        if filepath and filepath.suffix == '.svg':
            icon = self._QIcon(str(filepath))
            if not icon.isNull():
                self._icon_cache[f"svg_{icon_name}_{size}"] = icon
                return icon
        return None
    
    def load_png_icon(self, icon_name: str, size: int = 24):
        """加载 PNG 图标文件"""
        self._ensure_qt_imported()
        if not self._qt_available:
            return None
            
        filepath = self._find_icon_file(icon_name)
        if filepath and filepath.suffix == '.png':
            pixmap = self._QPixmap(str(filepath))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(size, size, aspectRatioMode=1)
                icon = self._QIcon(pixmap)
                self._icon_cache[f"png_{icon_name}_{size}"] = icon
                return icon
        return None
    
    def get_icon(self, category: str, icon_id: str, size: int = 24):
        """获取图标，按优先级尝试加载
        
        优先级：
        1. SVG 文件（从自定义图标库）
        2. PNG 文件（从自定义图标库）
        3. 内置图标目录的图标文件
        4. 内置 Emoji（返回字符串，用于文本显示）
        """
        # 获取映射的图标文件名
        mapped_name = ICON_MAPPINGS.get(category, {}).get(icon_id, icon_id)
        
        # 先尝试加载映射名称的图标文件
        icon = self.load_svg_icon(mapped_name, size)
        if icon:
            return icon
        
        icon = self.load_png_icon(mapped_name, size)
        if icon:
            return icon
        
        # 如果没有映射或映射文件不存在，尝试原始 icon_id
        if mapped_name != icon_id:
            icon = self.load_svg_icon(icon_id, size)
            if icon:
                return icon
            icon = self.load_png_icon(icon_id, size)
            if icon:
                return icon
        
        # 尝试 category_icon_id 格式（兼容旧文件名）
        combined_name = f"{category}_{icon_id}"
        icon = self.load_svg_icon(combined_name, size)
        if icon:
            return icon
        icon = self.load_png_icon(combined_name, size)
        if icon:
            return icon
        
        return None
    
    def get_emoji(self, category: str, icon_id: str) -> str:
        """获取 Emoji 图标字符串（用于文本显示场景）"""
        return FALLBACK_ICONS.get(category, {}).get(icon_id, "●")
    
    def has_icon_file(self, icon_name: str) -> bool:
        """检查是否存在图标文件"""
        return self._find_icon_file(icon_name) is not None
    
    def list_available_icons(self) -> list:
        """列出所有可用的图标文件"""
        icons = set()
        for search_path in self._search_paths:
            if search_path.exists():
                for file in search_path.iterdir():
                    if file.suffix in ('.svg', '.png'):
                        icons.add(file.stem)
        return sorted(list(icons))
    
    def list_mapped_icons(self) -> dict:
        """列出当前映射配置"""
        result = {}
        for category, mappings in ICON_MAPPINGS.items():
            result[category] = {}
            for icon_id, file_name in mappings.items():
                found = self.has_icon_file(file_name)
                status = "OK" if found else "MISSING"
                result[category][icon_id] = f"{file_name} [{status}]"
        return result

# ============================================================
# 全局图标加载器实例
# ============================================================
_icon_loader = None

def get_icon_loader() -> IconLoader:
    """获取全局图标加载器实例"""
    global _icon_loader
    if _icon_loader is None:
        _icon_loader = IconLoader()
    return _icon_loader

# ============================================================
# 便捷函数（兼容原有接口）
# ============================================================

def get_nav_icon(nav_id: str) -> str:
    """获取导航栏图标（返回 Emoji 字符串，兼容原有代码）"""
    loader = get_icon_loader()
    
    icon = loader.get_icon("nav", nav_id)
    if icon:
        return f"__ICON__nav_{nav_id}"
    
    return loader.get_emoji("nav", nav_id)

def get_action_icon(action_id: str) -> str:
    """获取功能按钮图标（返回 Emoji 字符串，兼容原有代码）"""
    loader = get_icon_loader()
    
    icon = loader.get_icon("action", action_id)
    if icon:
        return f"__ICON__action_{action_id}"
    
    return loader.get_emoji("action", action_id)

def get_platform_icon(platform: str) -> str:
    """获取平台图标（返回 Emoji 字符串，兼容原有代码）"""
    loader = get_icon_loader()
    
    icon = loader.get_icon("platform", platform)
    if icon:
        return f"__ICON__platform_{platform}"
    
    return loader.get_emoji("platform", platform)

# ============================================================
# 使用说明生成器
# ============================================================

def generate_usage_instructions() -> str:
    """生成图标使用说明"""
    instructions = """
WARFRAME-RELIC 图标使用说明
============================

1. 图标文件格式：
   - SVG 格式（推荐）
   - PNG 格式

2. 图标搜索路径（按优先级）：
   1. icon/unoline-icons/Unoline/Essentials/
   2. icon/unoline-icons/Unoline/Navigation/
   3. icon/unoline-icons/Unoline/Social/
   4. assets/icons/

3. 当前图标库：Unoline Icons
   包含分类：Essentials, Navigation, Social

4. 当前图标映射：
"""
    loader = get_icon_loader()
    mappings = loader.list_mapped_icons()
    for category, items in mappings.items():
        instructions += f"\n   {category}:\n"
        for icon_id, status in items.items():
            instructions += f"     {icon_id}: {status}\n"
    
    instructions += """
5. 添加/修改图标映射：
   编辑 data/icon_loader.py 中的 ICON_MAPPINGS 字典

6. 查看可用图标：
   python -m data.icon_loader

7. 可用图标列表（Unoline）：
   Essentials: battery, card, folder, home, mail, message, navigation, 
               note, notebook, profile, search, shield, smartphone, time, write
   Navigation: arrow left/right/up/down, plus, minus, multiply, divide, 
               reload_left, reload_right, sharp_arrow, thin_arrow, wave_arrow
   Social: Github, Gmail, Twitter, Wechat, WhatsApp, Telegram, Facebook, 
           Instagram, Discord, Slack, Youtube, Spotify, etc.
"""
    return instructions

if __name__ == "__main__":
    print(generate_usage_instructions())
    
    loader = get_icon_loader()
    print("\n" + "="*40)
    print("可用图标文件列表:")
    print("="*40)
    icons = loader.list_available_icons()
    if icons:
        for icon in icons:
            print(f"  - {icon}")
    else:
        print("  (暂无图标文件)")
