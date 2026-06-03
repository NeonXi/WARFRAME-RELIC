"""
WARFRAME-RELIC 主题配置引擎
- ThemeConfig 单例：管理配色加载/保存/预设切换
- 颜色由 data/presets/ 下的独立预设文件驱动，各预设互不影响
- 支持自定义背景图（透明度、模糊度可调）

使用方式：
    from core.theme_config import theme, ThemeConfig
    
    # 背景图操作
    theme.set_background_image("path/to/image.jpg")
    theme.set_background_opacity(0.5)
    theme.set_background_blur(10)
    theme.clear_background_image()
"""
import json
import logging
import os
import threading
from pathlib import Path

# 设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ThemeConfig:
    """主题配色管理器（线程安全单例模式）。

    使用方式：
        theme = ThemeConfig()           # 获取单例
        theme.cyber_yellow              # 直接访问属性
        theme.reload()                  # 热重载
        theme.save(modified_dict)       # 保存修改到当前预设文件
        theme.apply_preset("daylight")  # 切换到白天模式
        theme.reset()                   # 恢复 2077 默认
        
        # 背景图设置
        theme.set_background_image("image.jpg")
        theme.background_opacity = 0.5
        theme.background_blur = 10
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_once()
        return cls._instance

    def _init_once(self):
        """初始化（仅调用一次）"""
        self._loaded = False
        self._active_preset = None
        self._data = {}
        # 背景图相关配置
        self._bg_image_path = None
        self._bg_opacity = 0.3
        self._bg_blur = 8
        self._bg_enabled = False
        self._panel_overlay_opacity = 180  # 面板遮罩透明度 (0-255)
        # 延迟保存机制
        self._bg_save_pending = False
        self._bg_save_timer = None  # 延迟到 add_listener 后初始化
        # 监听器列表（主题变化通知）
        self._listeners = []
        # 加载主题数据
        self._load()

    # ---- 文件路径 ----

    @property
    def _data_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / 'data'

    @property
    def _presets_dir(self) -> Path:
        return self._data_dir / 'presets'

    @property
    def _backgrounds_dir(self) -> Path:
        """背景图存储目录"""
        return self._data_dir / 'backgrounds'

    def _preset_path(self, preset_id: str) -> Path:
        return self._presets_dir / f'{preset_id}.json'

    @property
    def _active_path(self) -> Path:
        return self._presets_dir / '_active.json'

    @property
    def _legacy_theme_path(self) -> Path:
        """旧版 theme.json（迁移用）。"""
        return self._data_dir / 'theme.json'

    @property
    def _bg_config_path(self) -> Path:
        """背景图配置文件路径"""
        return self._data_dir / 'background_config.json'

    # ---- 加载 / 重载 ----

    _DEFAULTS = None

    def _load(self):
        """加载配色：先设默认值，再根据活动预设文件覆盖。"""
        try:
            # 初始化默认目录
            os.makedirs(self._presets_dir, exist_ok=True)
            os.makedirs(self._backgrounds_dir, exist_ok=True)

            # 出厂默认值（Cyberpunk 2077 主题）
            if ThemeConfig._DEFAULTS is None:
                ThemeConfig._DEFAULTS = self._create_defaults()

            self._data = dict(ThemeConfig._DEFAULTS)
            self._migrate_legacy()
            self._apply_active_preset()
            self._load_background_config()
            self._build_derived()
            self._loaded = True
            logger.info(f"主题配置加载成功，当前预设: {self._active_preset}")

        except Exception as e:
            logger.error(f"主题配置加载失败: {e}", exc_info=True)
            self._data = dict(ThemeConfig._DEFAULTS)
            self._loaded = False

    def _create_defaults(self) -> dict:
        """创建默认配色配置（精简版，合并冗余字段）"""
        return {
            # ---- 霓虹主色 (6) ----
            "cyber_yellow": "#FFE600", "cyber_cyan": "#00FFFF",
            "cyber_magenta": "#FF0099", "cyber_orange": "#FF7700",
            "cyber_red": "#FF0055", "cyber_green": "#00FF99",
            # ---- 面板背景 (4) ----
            "panel_bg": "#08081A", "card_bg": "#0E0E24",
            "panel_darkest": "#040412", "panel_deeper": "#020210",
            # ---- 边框 & 文字 (3) ----
            "border": "#FF0055", "text": "#E8ECFF", "text_dim": "#6677AA",
            # ---- 遗物状态 (1) ----
            "color_unknown": "#556688",
            # ---- 稀有度 (3) ----
            "color_gold": "#FFD700", "color_silver": "#00FFFF",
            "color_copper": "#FF7700",
            # ---- 覆盖层 (5) ----
            "overlay_bg_rgba": [8, 8, 22, 230],
            "overlay_selection_overlay_rgba": [20, 2, 40, 120],
            "overlay_status_bg_rgba": [8, 8, 20, 210],
            "overlay_crosshair_color": "#FF0055",
            "overlay_selection_border": "#FFE600",
            # ---- 面板遮罩 ----
            "panel_overlay_rgb": [5, 5, 20],
            # ---- 按钮：默认 (10) ----
            "btn_default_bg": "#0E0E24", "btn_default_text": "#FFE600",
            "btn_default_border": "#FFE600",
            "btn_hover_bg": "#1A1030", "btn_hover_text": "#00FFFF",
            "btn_hover_border": "#00FFFF",
            "btn_pressed_bg": "#050510",
            "btn_disabled_bg": "#0A0A18", "btn_disabled_text": "#444466",
            "btn_disabled_border": "#2A2040",
            # ---- 按钮：主要 (5) ----
            "primary_bg": "#1A0030", "primary_text": "#FFE600",
            "primary_border": "#FFE600",
            "primary_hover_bg": "#2A0048", "primary_hover_border": "#00FFFF",
            # ---- 按钮：危险/成功 (8) ----
            "danger_text": "#FF0055", "danger_border": "#FF0055",
            "danger_hover_bg": "#200010", "danger_hover_text": "#FF3377",
            "success_text": "#00FF99", "success_border": "#00FF99",
            "success_hover_bg": "#002010", "success_hover_text": "#33FFBB",
            # ---- 品牌色 (4) ----
            "brand_bilibili": "#FB7299", "brand_bilibili_hover": "#FF8DB0",
            "brand_github": "#58A6FF", "brand_github_hover": "#79C0FF",
            # ---- 其他 (6) ----
            "label_default": "#99AACC",
            "progress_gradient_start": "#FFE600",
            "progress_gradient_mid": "#FF0055",
            "progress_gradient_end": "#00FFFF",
            "fetch_manual_hint": "#FFAA33", "fetch_error_color": "#FF4455",
        }

    def _migrate_legacy(self):
        """从旧版 theme.json 迁移到新的独立预设文件系统。"""
        if not self._legacy_theme_path.exists():
            return
        try:
            with open(self._legacy_theme_path, 'r', encoding='utf-8') as f:
                legacy = json.load(f)
            if not legacy:
                return

            bg = legacy.get("panel_bg", "#000000")
            try:
                r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                is_light = (r + g + b) / 3 > 128
            except (ValueError, IndexError):
                is_light = False

            target_id = "daylight" if is_light else "cyberpunk"
            merged = dict(self._data)
            merged.update(legacy)
            self._write_preset(target_id, merged)
            self._write_active(target_id)
            os.remove(self._legacy_theme_path)
            logger.info(f"已从旧版 theme.json 迁移到预设: {target_id}")

        except Exception as e:
            logger.warning(f"旧版配置迁移失败: {e}")

    def _apply_active_preset(self):
        """根据 _active.json 或内置默认加载对应预设。"""
        active_id = self._read_active()
        if active_id and active_id in self.PRESETS:
            self._active_preset = active_id
            self._load_preset_data(active_id)
        else:
            self._active_preset = "cyberpunk"
            self._load_preset_data("cyberpunk")

    def _load_preset_data(self, preset_id: str):
        """加载预设数据"""
        if preset_id == "cyberpunk":
            self._load_preset_file("cyberpunk")
        elif preset_id == "custom":
            self._load_preset_file("custom")
        else:
            self._data.update(self.PRESET_DATA.get(preset_id, {}))
            self._load_preset_file(preset_id)

    def _load_preset_file(self, preset_id: str):
        """从预设文件加载配色覆盖默认值。"""
        preset_path = self._preset_path(preset_id)
        if preset_id == "cyberpunk" and not preset_path.exists():
            return

        if preset_path.exists():
            try:
                with open(preset_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                if file_data:
                    self._data.update(file_data)
            except Exception as e:
                logger.warning(f"加载预设文件失败 {preset_path}: {e}")

    # ---- 背景图配置 ----

    def _load_background_config(self):
        """加载背景图配置"""
        if self._bg_config_path.exists():
            try:
                with open(self._bg_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self._bg_image_path = config.get('image_path')
                    self._bg_opacity = config.get('opacity', 0.3)
                    self._bg_blur = config.get('blur', 8)
                    self._bg_enabled = config.get('enabled', False)
                    self._panel_overlay_opacity = config.get('panel_overlay_opacity', 180)
                    # 验证路径是否存在
                    if self._bg_image_path and not os.path.exists(self._bg_image_path):
                        self._bg_image_path = None
                        self._bg_enabled = False
            except Exception as e:
                logger.warning(f"加载背景图配置失败: {e}")

    def _save_background_config(self):
        """保存背景图配置"""
        try:
            config = {
                'image_path': self._bg_image_path,
                'opacity': self._bg_opacity,
                'blur': self._bg_blur,
                'enabled': self._bg_enabled,
                'panel_overlay_opacity': self._panel_overlay_opacity
            }
            with open(self._bg_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存背景图配置失败: {e}")

    def set_background_image(self, file_path: str) -> bool:
        """设置背景图
        
        Args:
            file_path: 背景图文件路径
            
        Returns:
            是否设置成功
        """
        if not os.path.exists(file_path):
            logger.error(f"背景图文件不存在: {file_path}")
            return False

        # 验证文件类型
        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
        if not file_path.lower().endswith(valid_extensions):
            logger.error(f"不支持的图片格式: {file_path}")
            return False

        # 复制到应用目录
        try:
            import shutil
            file_name = os.path.basename(file_path)
            dest_path = str(self._backgrounds_dir / file_name)
            
            # 如果是同一文件则不复制
            if os.path.abspath(file_path) != os.path.abspath(dest_path):
                shutil.copy2(file_path, dest_path)
            
            self._bg_image_path = dest_path
            self._bg_enabled = True
            self._clear_background_cache()  # 清除旧缓存
            self._save_background_config()
            self._notify_listeners()
            logger.info(f"背景图设置成功: {dest_path}")
            return True

        except Exception as e:
            logger.error(f"设置背景图失败: {e}")
            return False

    def clear_background_image(self):
        """清除背景图"""
        self._bg_image_path = None
        self._bg_enabled = False
        self._notify_listeners()

    def calculate_background_size(self, window_width: int, window_height: int) -> str:
        """计算背景图显示尺寸，保证无黑边且不过度放大
        
        Args:
            window_width: 窗口宽度
            window_height: 窗口高度
            
        Returns:
            CSS background-size 值，如 "cover" 或 "1920px 1080px"
        """
        if not self._bg_image_path or not os.path.exists(self._bg_image_path):
            return "cover"
            
        # 获取缓存的图片尺寸
        img_width, img_height = self._get_background_image_size()
        if img_width <= 0 or img_height <= 0:
            return "cover"
            
        # 计算缩放比例：至少让一个维度贴紧窗口
        scale_x = window_width / img_width
        scale_y = window_height / img_height
        scale = max(scale_x, scale_y)
        
        # 限制最大缩放比例为 1.5 倍（避免过度放大）
        max_scale = 1.5
        scale = min(scale, max_scale)
        
        # 计算最终尺寸
        final_width = int(img_width * scale)
        final_height = int(img_height * scale)
        
        return f"{final_width}px {final_height}px"

    def _get_background_image_size(self) -> tuple:
        """获取背景图尺寸（带缓存）"""
        if not hasattr(self, '_cached_bg_size') or self._cached_bg_size is None:
            self._cached_bg_size = (0, 0)
            if self._bg_image_path and os.path.exists(self._bg_image_path):
                try:
                    from PIL import Image
                    with Image.open(self._bg_image_path) as img:
                        self._cached_bg_size = img.size
                except Exception as e:
                    logger.error(f"读取背景图尺寸失败: {e}")
        return self._cached_bg_size

    def _clear_background_cache(self):
        """清除背景图缓存（更换背景图时调用）"""
        self._cached_bg_size = None

    @property
    def background_enabled(self) -> bool:
        """背景图是否启用"""
        return self._bg_enabled and self._bg_image_path and os.path.exists(self._bg_image_path)

    @property
    def background_image_path(self) -> str | None:
        """背景图路径"""
        if self._bg_image_path and os.path.exists(self._bg_image_path):
            return self._bg_image_path
        return None

    @property
    def background_opacity(self) -> float:
        """背景图透明度 (0.0-1.0)"""
        return self._bg_opacity

    @background_opacity.setter
    def background_opacity(self, value: float):
        """设置背景图透明度（延迟保存）"""
        self._bg_opacity = max(0.0, min(1.0, value))
        self._notify_listeners()
        # 延迟保存（2秒后自动保存）
        self._bg_save_pending = True
        if self._bg_save_timer:
            self._bg_save_timer.start(2000)

    @property
    def background_blur(self) -> int:
        """背景图模糊度 (0-50)"""
        return self._bg_blur

    @background_blur.setter
    def background_blur(self, value: int):
        """设置背景图模糊度（延迟保存）"""
        self._bg_blur = max(0, min(50, value))
        self._notify_listeners()
        # 延迟保存（2秒后自动保存）
        self._bg_save_pending = True
        if self._bg_save_timer:
            self._bg_save_timer.start(2000)

    @property
    def panel_overlay_opacity(self) -> int:
        """面板遮罩透明度 (0-255)，控制导航区/日志区等半透明面板的 alpha 值"""
        return self._panel_overlay_opacity

    @panel_overlay_opacity.setter
    def panel_overlay_opacity(self, value: int):
        """设置面板遮罩透明度（延迟保存）"""
        self._panel_overlay_opacity = max(0, min(255, value))
        self._notify_listeners()
        self._bg_save_pending = True
        if self._bg_save_timer:
            self._bg_save_timer.start(2000)

    # ---- 活跃预设读写 ----

    def _read_active(self) -> str | None:
        try:
            if self._active_path.exists():
                with open(self._active_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get("active")
        except Exception as e:
            logger.warning(f"读取活跃预设失败: {e}")
        return None

    def _write_active(self, preset_id: str):
        try:
            os.makedirs(self._presets_dir, exist_ok=True)
            with open(self._active_path, 'w', encoding='utf-8') as f:
                json.dump({"active": preset_id}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"写入活跃预设失败: {e}")

    def _write_preset(self, preset_id: str, data: dict):
        """全量写入预设文件。"""
        try:
            os.makedirs(self._presets_dir, exist_ok=True)
            with open(self._preset_path(preset_id), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"写入预设文件失败 {preset_id}: {e}")

    # ---- 派生属性 ----

    def _build_derived(self):
        """从 _data 构建派生属性（RGBA 元组、日志映射等）。"""
        d = self._data
        for k, v in d.items():
            setattr(self, k, v)

        self.overlay_bg_rgba = tuple(d["overlay_bg_rgba"])
        self.overlay_selection_overlay_rgba = tuple(d["overlay_selection_overlay_rgba"])
        self.overlay_status_bg_rgba = tuple(d["overlay_status_bg_rgba"])

        self.log_color_map = {
            "ok": d["cyber_green"], "warn": d["cyber_orange"],
            "error": d["cyber_red"], "info": d["cyber_cyan"],
            "debug": d["color_unknown"],
        }

    # ---- 观察者模式 ----

    def add_listener(self, callback):
        """添加主题变化监听器"""
        if callback not in self._listeners:
            self._listeners.append(callback)
        
        # 延迟初始化定时器（需要 PyQt 环境）
        if self._bg_save_timer is None:
            try:
                from PyQt6.QtCore import QTimer
                self._bg_save_timer = QTimer()
                self._bg_save_timer.setSingleShot(True)
                self._bg_save_timer.timeout.connect(self._do_save_background_config)
            except Exception:
                pass  # 非 PyQt 环境忽略

    def remove_listener(self, callback):
        """移除主题变化监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _do_save_background_config(self):
        """执行保存背景图配置"""
        if self._bg_save_pending:
            self._save_background_config()
            self._bg_save_pending = False

    def save_background_config_now(self):
        """立即保存背景图配置"""
        if self._bg_save_timer:
            self._bg_save_timer.stop()
        self._do_save_background_config()

    def _notify_listeners(self):
        """通知所有监听器主题已变化"""
        for callback in self._listeners:
            try:
                callback()
            except Exception as e:
                logger.error(f"通知监听器失败: {e}")

    # ---- 公共 API ----

    def reload(self):
        """热重载：重新读取预设文件并重建所有属性。"""
        self._load()
        self._notify_listeners()

    def to_dict(self) -> dict:
        """返回当前配色字典的副本。"""
        return dict(self._data)

    def save(self, changes: dict) -> bool:
        """将修改合并到内存并全量写入当前活动预设文件。

        重要规则：若当前预设为内置默认（cyberpunk / daylight），
        则自动切换到自定义（custom），并将修改后的完整配色保存到 custom.json。
        这确保内置预设不被用户修改污染，修改始终存为「自定义配色」。
        """
        valid = {k: v for k, v in changes.items() if k in self._data}
        if not valid:
            return False

        self._data.update(valid)
        self._build_derived()

        if self._active_preset in ("cyberpunk", "daylight"):
            self._active_preset = "custom"
            self._write_active("custom")

        self._write_preset(self._active_preset, self._data)
        self._notify_listeners()
        return True

    def reset(self):
        """恢复当前活动预设为出厂默认值。"""
        preset_path = self._preset_path(self._active_preset)
        try:
            os.remove(preset_path)
        except Exception:
            pass

        self._data = dict(ThemeConfig._DEFAULTS)
        if self._active_preset != "cyberpunk":
            preset_data = self.PRESET_DATA.get(self._active_preset, {})
            if preset_data:
                self._data.update(preset_data)

        self._build_derived()
        self._write_preset(self._active_preset, self._data)
        self._notify_listeners()

    @property
    def active_preset(self) -> str:
        """当前活动预设 ID。"""
        return self._active_preset

    # ---- 预设主题 ----

    PRESETS = {
        "cyberpunk": {
            "name": "赛博朋克",
            "description": "霓虹暗色主题，护眼且酷炫",
        },
        "daylight": {
            "name": "白天模式",
            "description": "白色基调，适合明亮环境",
        },
        "custom": {
            "name": "自定义配色",
            "description": "你的专属配色方案",
        },
    }

    PRESET_DATA = {
        "cyberpunk": {},
        "custom": {},
        "daylight": {
            # ---- 霓虹主色 (6) ----
            "cyber_yellow": "#E67E00", "cyber_cyan": "#0077CC",
            "cyber_magenta": "#C2185B", "cyber_orange": "#E65100",
            "cyber_red": "#D32F2F", "cyber_green": "#2E7D32",
            # ---- 面板背景 (4) ----
            "panel_bg": "#F5F6FA", "card_bg": "#FFFFFF",
            "panel_darkest": "#E5E7EB", "panel_deeper": "#F3F4F6",
            # ---- 边框 & 文字 (3) ----
            "border": "#D1D5DB", "text": "#1F2937", "text_dim": "#6B7280",
            # ---- 遗物状态 (1) ----
            "color_unknown": "#9CA3AF",
            # ---- 稀有度 (3) ----
            "color_gold": "#D4A017", "color_silver": "#5C7B9E",
            "color_copper": "#B8631F",
            # ---- 覆盖层 (5) ----
            "overlay_bg_rgba": [30, 30, 36, 230],
            "overlay_selection_overlay_rgba": [50, 50, 60, 100],
            "overlay_status_bg_rgba": [30, 30, 36, 210],
            "overlay_crosshair_color": "#D32F2F",
            "overlay_selection_border": "#E67E00",
            # ---- 面板遮罩 ----
            "panel_overlay_rgb": [220, 220, 230],
            # ---- 按钮 (15) ----
            "btn_default_bg": "#FFFFFF", "btn_default_text": "#374151",
            "btn_default_border": "#D1D5DB",
            "btn_hover_bg": "#EFF6FF", "btn_hover_text": "#1565C0",
            "btn_hover_border": "#1565C0",
            "btn_pressed_bg": "#DBEAFE",
            "btn_disabled_bg": "#F9FAFB", "btn_disabled_text": "#9CA3AF",
            "btn_disabled_border": "#E5E7EB",
            "primary_bg": "#EFF6FF", "primary_text": "#1D4ED8",
            "primary_border": "#3B82F6",
            "primary_hover_bg": "#DBEAFE", "primary_hover_border": "#2563EB",
            "danger_text": "#DC2626", "danger_border": "#DC2626",
            "danger_hover_bg": "#FEF2F2", "danger_hover_text": "#B91C1C",
            "success_text": "#16A34A", "success_border": "#16A34A",
            "success_hover_bg": "#F0FDF4", "success_hover_text": "#15803D",
            # ---- 品牌色 (4) ----
            "brand_bilibili": "#FB7299", "brand_bilibili_hover": "#FF8DB0",
            "brand_github": "#374151", "brand_github_hover": "#111827",
            # ---- 其他 (6) ----
            "label_default": "#4B5563",
            "progress_gradient_start": "#3B82F6",
            "progress_gradient_mid": "#0077CC",
            "progress_gradient_end": "#2E7D32",
            "fetch_manual_hint": "#E65100", "fetch_error_color": "#DC2626",
        },
    }

    def apply_preset(self, preset_id: str) -> bool:
        """一键应用整套预设配色。各预设独立存储，互不影响。

        Args:
            preset_id: "cyberpunk"、"daylight" 或 "custom"
        """
        if preset_id not in self.PRESETS:
            return False
        if preset_id == self._active_preset:
            return True

        self._write_preset(self._active_preset, self._data)

        self._data = dict(ThemeConfig._DEFAULTS)
        self._load_preset_data(preset_id)

        self._active_preset = preset_id
        self._write_active(preset_id)
        self._build_derived()
        self._notify_listeners()
        return True

    def current_preset_name(self) -> str:
        """返回当前活动预设的显示名称。"""
        return self.PRESETS.get(self._active_preset, {}).get("name", "未知")

    def get_panel_bg_color(self, alpha: int | None = None) -> str:
        """获取面板背景色（考虑背景图是否启用）。
        
        有背景图时返回半透明色，RGB 由预设的 panel_overlay_rgb 控制，
        透明度由 panel_overlay_opacity 控制（用户可调节）。
        无背景图时返回纯色 panel_darkest。
        
        Args:
            alpha: 透明度值 (0-255)。不传则使用 panel_overlay_opacity 配置值。
                  传入时会按比例缩放：实际 alpha = panel_overlay_opacity * alpha / 180
            
        Returns:
            背景色字符串，有背景图时返回半透明色，无背景图时返回纯色
        """
        if self.background_enabled and self.background_image_path:
            actual_alpha = self._panel_overlay_opacity
            if alpha is not None:
                actual_alpha = int(self._panel_overlay_opacity * alpha / 180)
            actual_alpha = max(0, min(255, actual_alpha))
            rgb = self._data.get("panel_overlay_rgb", [5, 5, 20])
            return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {actual_alpha})"
        return self.panel_darkest

    def __getattr__(self, name):
        """属性代理：未定义属性时从 _data 字典取值。"""
        if name.startswith('_'):
            raise AttributeError(name)
        if '_data' in self.__dict__ and name in self._data:
            return self._data[name]
        raise AttributeError(f"'ThemeConfig' has no attribute '{name}'")


# 全局单例
theme = ThemeConfig()