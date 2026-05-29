"""
WARFRAME-RELIC 主题配置引擎
- ThemeConfig 单例：管理配色加载/保存/预设切换
- 颜色由 data/presets/ 下的独立预设文件驱动，各预设互不影响

使用方式：
    from core.theme_config import theme, ThemeConfig
"""
import json
import os
from pathlib import Path


class ThemeConfig:
    """主题配色管理器（单例模式）。

    使用方式：
        theme = ThemeConfig()           # 获取单例
        theme.cyber_yellow              # 直接访问属性
        theme.reload()                  # 热重载
        theme.save(modified_dict)       # 保存修改到当前预设文件
        theme.apply_preset("daylight")  # 切换到白天模式
        theme.reset()                   # 恢复 2077 默认
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
            cls._instance._active_preset = None
            cls._instance._load()
        return cls._instance

    # ---- 文件路径 ----

    @property
    def _data_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / 'data'

    @property
    def _presets_dir(self) -> Path:
        return self._data_dir / 'presets'

    def _preset_path(self, preset_id: str) -> Path:
        return self._presets_dir / f'{preset_id}.json'

    @property
    def _active_path(self) -> Path:
        return self._presets_dir / '_active.json'

    @property
    def _legacy_theme_path(self) -> Path:
        """旧版 theme.json（迁移用）。"""
        return self._data_dir / 'theme.json'

    # ---- 加载 / 重载 ----

    # 出厂默认值（首次 _load 时缓存）
    _DEFAULTS = None

    def _load(self):
        """加载配色：先设默认值，再根据活动预设文件覆盖。"""
        # 出厂默认值（Cyberpunk 2077 主题）
        if ThemeConfig._DEFAULTS is None:
            ThemeConfig._DEFAULTS = {
                # ---- 霓虹主色 ----
                "cyber_yellow": "#FFE600", "cyber_cyan": "#00FFFF",
                "cyber_magenta": "#FF0099", "cyber_orange": "#FF7700",
                "cyber_red": "#FF0055", "cyber_green": "#00FF99",
                "cyber_blue": "#3399FF",
                # ---- 暗色背景 ----
                "dark_bg": "#020208", "panel_bg": "#08081A",
                "card_bg": "#0E0E24", "border": "#FF0055",
                # ---- 文字 ----
                "text": "#E8ECFF", "text_dim": "#6677AA",
                # ---- 遗物状态 ----
                "color_vaulted": "#00FF99", "color_available": "#FF0055",
                "color_unknown": "#556688",
                # ---- 稀有度 ----
                "color_gold": "#FFD700", "color_silver": "#00FFFF",
                "color_copper": "#FF7700",
                # ---- 日志 ----
                "log_ok": "#00FF99", "log_warn": "#FF7700",
                "log_error": "#FF0055", "log_info": "#00FFFF",
                "log_debug": "#556688",
                # ---- 覆盖层 ----
                "overlay_bg_rgba": [8, 8, 22, 230],
                "overlay_selection_overlay_rgba": [20, 2, 40, 120],
                "overlay_status_bg_rgba": [8, 8, 20, 210],
                "overlay_crosshair_color": "#FF0055",
                "overlay_selection_border": "#FFE600",
                # ---- 按钮 ----
                "btn_default_bg": "#0E0E24", "btn_default_text": "#FFE600",
                "btn_default_border": "#FFE600",
                "btn_hover_bg": "#1A1030", "btn_hover_text": "#00FFFF",
                "btn_hover_border": "#00FFFF",
                "btn_pressed_bg": "#050510",
                "btn_disabled_bg": "#0A0A18", "btn_disabled_text": "#444466",
                "btn_disabled_border": "#2A2040",
                # ---- 主要按钮 ----
                "primary_bg": "#1A0030", "primary_text": "#FFE600",
                "primary_border": "#FFE600",
                "primary_hover_bg": "#2A0048", "primary_hover_border": "#00FFFF",
                "primary_disabled_bg": "#0A0A18", "primary_disabled_text": "#444466",
                "primary_disabled_border": "#2A2040",
                # ---- 危险/成功按钮 ----
                "danger_text": "#FF0055", "danger_border": "#FF0055",
                "danger_hover_bg": "#200010", "danger_hover_text": "#FF3377",
                "success_text": "#00FF99", "success_border": "#00FF99",
                "success_hover_bg": "#002010", "success_hover_text": "#33FFBB",
                # ---- 品牌色 ----
                "brand_bilibili": "#FB7299", "brand_bilibili_hover": "#FF8DB0",
                "brand_github": "#58A6FF", "brand_github_hover": "#79C0FF",
                # ---- 其他 ----
                "label_default": "#99AACC",
                "panel_darkest": "#040412", "panel_deeper": "#020210",
                "progress_gradient_start": "#FFE600",
                "progress_gradient_mid": "#FF0055",
                "progress_gradient_end": "#00FFFF",
                "log_timestamp": "#555577",
                "fetch_manual_hint": "#FFAA33", "fetch_error_color": "#FF4455",
            }
        self._data = dict(ThemeConfig._DEFAULTS)
        self._migrate_legacy()
        self._apply_active_preset()
        self._build_derived()
        self._loaded = True

    def _migrate_legacy(self):
        """从旧版 theme.json 迁移到新的独立预设文件系统。"""
        if not self._legacy_theme_path.exists():
            return
        try:
            with open(self._legacy_theme_path, 'r', encoding='utf-8') as f:
                legacy = json.load(f)
            if not legacy:
                return
            # 判断旧数据属于哪个预设
            bg = legacy.get("panel_bg", "#000000")
            try:
                r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                is_light = (r + g + b) / 3 > 128
            except (ValueError, IndexError):
                is_light = False
            target_id = "daylight" if is_light else "cyberpunk"
            # 合并：默认值 + 旧 theme.json 覆盖
            merged = dict(self._data)
            merged.update(legacy)
            self._write_preset(target_id, merged)
            self._write_active(target_id)
            # 删除旧文件
            os.remove(self._legacy_theme_path)
        except Exception:
            pass

    def _apply_active_preset(self):
        """根据 _active.json 或内置默认加载对应预设。"""
        active_id = self._read_active()
        if active_id and active_id in self.PRESETS:
            self._active_preset = active_id
            if active_id == "cyberpunk":
                self._load_preset_file("cyberpunk")
            elif active_id == "custom":
                self._load_preset_file("custom")
            else:
                # daylight 等有 PRESET_DATA 的预设
                self._data.update(self.PRESET_DATA.get(active_id, {}))
                self._load_preset_file(active_id)
        else:
            # 首次启动或记录丢失：使用内置 2077 默认值
            self._active_preset = "cyberpunk"
            self._load_preset_file("cyberpunk")

    def _load_preset_file(self, preset_id: str):
        """从预设文件加载配色覆盖默认值。"""
        preset_path = self._preset_path(preset_id)
        if preset_id == "cyberpunk" and not preset_path.exists():
            # 2077 无文件时使用内置默认值（即 _data 本身）
            return
        if preset_path.exists():
            try:
                with open(preset_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                if file_data:
                    self._data.update(file_data)
            except Exception:
                pass

    # ---- 活跃预设读写 ----

    def _read_active(self) -> str | None:
        try:
            if self._active_path.exists():
                with open(self._active_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get("active")
        except Exception:
            pass
        return None

    def _write_active(self, preset_id: str):
        try:
            os.makedirs(self._presets_dir, exist_ok=True)
            with open(self._active_path, 'w', encoding='utf-8') as f:
                json.dump({"active": preset_id}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _write_preset(self, preset_id: str, data: dict):
        """全量写入预设文件。"""
        try:
            os.makedirs(self._presets_dir, exist_ok=True)
            with open(self._preset_path(preset_id), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

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
            "ok": d["log_ok"], "warn": d["log_warn"],
            "error": d["log_error"], "info": d["log_info"],
            "debug": d["log_debug"],
        }
        self._loaded = True

    # ---- 公共 API ----

    def reload(self):
        """热重载：重新读取预设文件并重建所有属性。"""
        self._load()

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

        # 若当前是内置默认预设，自动切换到自定义
        if self._active_preset in ("cyberpunk", "daylight"):
            self._active_preset = "custom"
            self._write_active("custom")

        self._write_preset(self._active_preset, self._data)
        return True

    def reset(self):
        """恢复当前活动预设为出厂默认值。"""
        # 删除当前预设文件，让下次加载时使用出厂值
        preset_path = self._preset_path(self._active_preset)
        try:
            os.remove(preset_path)
        except Exception:
            pass
        # 重新加载
        self._data = dict(ThemeConfig._DEFAULTS)
        if self._active_preset != "cyberpunk":
            preset_data = self.PRESET_DATA.get(self._active_preset, {})
            if preset_data:
                self._data.update(preset_data)
        self._build_derived()
        # 写入干净的预设文件
        self._write_preset(self._active_preset, self._data)

    @property
    def active_preset(self) -> str:
        """当前活动预设 ID。"""
        return self._active_preset

    # ---- 预设主题 ----

    PRESETS = {
        "cyberpunk": {
            "name": "赛博朋克 2077（推荐）",
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
        "cyberpunk": {},  # 空 = 使用内置默认值
        "custom": {},     # 空 = 从文件加载
        "daylight": {
            # ==== 主色：蓝色系为主调，明亮清晰 ====
            "cyber_yellow": "#E67E00",      # 暖橙色 — 标题/高亮
            "cyber_cyan": "#0077CC",        # 亮蓝色 — 数据/数值
            "cyber_magenta": "#C2185B",     # 品红 — 装饰强调
            "cyber_orange": "#E65100",      # 深橙 — 警告提示
            "cyber_red": "#D32F2F",         # 红色 — 错误/入库
            "cyber_green": "#2E7D32",       # 翠绿 — 成功/出库
            "cyber_blue": "#1565C0",        # 蓝色 — 辅助信息

            # ==== 背景：纯白层次 ====
            "dark_bg": "#F0F2F5",
            "panel_bg": "#F5F6FA",
            "card_bg": "#FFFFFF",
            "border": "#D1D5DB",

            # ==== 文字：深色高对比 ====
            "text": "#1F2937",
            "text_dim": "#6B7280",

            # ==== 遗物状态标注 ====
            "color_vaulted": "#2E7D32",
            "color_available": "#D32F2F",
            "color_unknown": "#9CA3AF",

            # ==== 稀有度标注 ====
            "color_gold": "#D4A017",
            "color_silver": "#5C7B9E",
            "color_copper": "#B8631F",

            # ==== 日志颜色 ====
            "log_ok": "#2E7D32", "log_warn": "#E65100",
            "log_error": "#D32F2F", "log_info": "#1565C0",
            "log_debug": "#9CA3AF",

            # ==== 游戏覆盖层（RGBA: 半透明深色）====
            "overlay_bg_rgba": [30, 30, 36, 230],
            "overlay_selection_overlay_rgba": [50, 50, 60, 100],
            "overlay_status_bg_rgba": [30, 30, 36, 210],
            "overlay_crosshair_color": "#D32F2F",
            "overlay_selection_border": "#E67E00",

            # ==== 按钮：默认 ====
            "btn_default_bg": "#FFFFFF", "btn_default_text": "#374151",
            "btn_default_border": "#D1D5DB",
            "btn_hover_bg": "#EFF6FF", "btn_hover_text": "#1565C0",
            "btn_hover_border": "#1565C0",
            "btn_pressed_bg": "#DBEAFE",
            "btn_disabled_bg": "#F9FAFB", "btn_disabled_text": "#9CA3AF",
            "btn_disabled_border": "#E5E7EB",

            # ==== 按钮：主要 ====
            "primary_bg": "#EFF6FF", "primary_text": "#1D4ED8",
            "primary_border": "#3B82F6",
            "primary_hover_bg": "#DBEAFE", "primary_hover_border": "#2563EB",
            "primary_disabled_bg": "#F9FAFB", "primary_disabled_text": "#9CA3AF",
            "primary_disabled_border": "#E5E7EB",

            # ==== 按钮：危险 ====
            "danger_text": "#DC2626", "danger_border": "#DC2626",
            "danger_hover_bg": "#FEF2F2", "danger_hover_text": "#B91C1C",
            # ==== 按钮：成功 ====
            "success_text": "#16A34A", "success_border": "#16A34A",
            "success_hover_bg": "#F0FDF4", "success_hover_text": "#15803D",

            # ==== 品牌色 ====
            "brand_bilibili": "#FB7299", "brand_bilibili_hover": "#FF8DB0",
            "brand_github": "#374151", "brand_github_hover": "#111827",

            # ==== 其他 ====
            "label_default": "#4B5563",
            "panel_darkest": "#E5E7EB", "panel_deeper": "#F3F4F6",
            "progress_gradient_start": "#3B82F6",
            "progress_gradient_mid": "#0077CC",
            "progress_gradient_end": "#2E7D32",
            "log_timestamp": "#9CA3AF",
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
            return True  # 已经是当前预设

        # 保存当前配色到当前预设文件（如果有修改）
        self._write_preset(self._active_preset, self._data)

        # 加载目标预设
        self._data = dict(ThemeConfig._DEFAULTS)
        if preset_id == "cyberpunk":
            # 从 cyberpunk.json 加载（可能包含用户修改）
            self._load_preset_file("cyberpunk")
        elif preset_id == "custom":
            # 从 custom.json 加载
            self._load_preset_file("custom")
        else:
            # daylight: 用 PRESET_DATA 覆盖
            self._data.update(self.PRESET_DATA.get(preset_id, {}))
            # 再叠加 daylight.json 中的用户修改
            self._load_preset_file("daylight")

        self._active_preset = preset_id
        self._write_active(preset_id)
        self._build_derived()
        return True

    def current_preset_name(self) -> str:
        """返回当前活动预设的显示名称。"""
        return self.PRESETS.get(self._active_preset, {}).get("name", "未知")

    def __getattr__(self, name):
        """属性代理：未定义属性时从 _data 字典取值。"""
        if name.startswith('_'):
            raise AttributeError(name)
        if '_data' in self.__dict__ and name in self._data:
            return self._data[name]
        raise AttributeError(f"'ThemeConfig' has no attribute '{name}'")


# 全局单例（其他模块通过 import theme 访问）
theme = ThemeConfig()
