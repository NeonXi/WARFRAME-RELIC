"""
[L1] ThemeManager — 全局主题管理(唯一主题切换入口)

依赖: core.tokens.manager(纯数据层), core.services.ui_prefs(持久化),
      PySide6.QtCore(仅 Signal,不持有 widget)
禁止: 直接操作 widget / 绘制 / QSS 字符串拼接
职责:
  - 启动时恢复上次主题预设(apply_on_startup)
  - 运行时切换主题(switch_preset): 加载 token + 持久化 + 广播 theme_changed
  - 提供 theme_changed 信号,所有需要刷新的对象统一订阅

## 设计原则

  1. **唯一入口**: 启动恢复和运行时切换都走本类,
     禁止其它模块直接调 TokenManager.load_preset + save_theme_preset。
  2. **信号驱动**: 切换后发 theme_changed(name),订阅方自行刷新;
     不在这里遍历所有 widget,避免 ThemeManager 依赖具体 UI。
  3. **纯数据+编排**: 不持有 widget 引用,不做绘制;
     颜色计算仍由控件自己从 TokenManager 取。

## 控件响应主题的三类策略

  - A. 自绘控件(CyberWidgetMixin 子类): paintEvent 每次读 token,
    天然响应,无需订阅。
  - B. 页面层 _style(raw=callable): PageBase.on_theme_change 重放配方。
  - C. widgets 对话框 setStyleSheet(f"...token..."):
    提取 _build_qss() 方法,订阅 theme_changed 信号重建 QSS。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.tokens.manager import TokenManager
from core.services.ui_prefs import load_theme_preset, save_theme_preset


class ThemeManager(QObject):
    """全局主题管理器(单例)。

    唯一主题切换入口,负责:
      - 加载 token 预设
      - 持久化到 ui_prefs.json
      - 广播 theme_changed 信号通知所有订阅方刷新
    """

    # 主题切换完成后发射,参数为新预设名
    theme_changed = Signal(str)

    _instance: "ThemeManager | None" = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例(测试用)。"""
        if cls._instance is not None:
            cls._instance = None

    # ── 启动入口 ──

    def apply_on_startup(self) -> str:
        """启动时恢复上次主题预设。

        从 ui_prefs.json 读取上次保存的预设名并加载。
        失败回退到默认 cyberpunk,不阻塞启动。

        Returns:
            实际加载的预设名
        """
        try:
            preset = load_theme_preset()
        except Exception:
            preset = "cyberpunk"

        tm = TokenManager.instance()
        try:
            tm.load_preset(preset)
        except Exception:
            # 预设文件损坏/缺失,回退默认
            preset = "cyberpunk"
            try:
                tm.load_preset(preset)
            except Exception:
                pass

        print(f"[ThemeManager] 启动主题: {preset}", flush=True)
        return preset

    # ── 运行时切换入口 ──

    def switch_preset(self, name: str) -> bool:
        """切换主题预设(唯一运行时切换入口)。

        流程:
          1. TokenManager.load_preset(name)  — 加载新 token
          2. save_theme_preset(name)          — 持久化
          3. emit theme_changed(name)         — 广播,订阅方自行刷新

        Args:
            name: 预设名(如 "cyberpunk" / "glassmorphism")

        Returns:
            True=切换成功并已广播; False=加载失败(未广播)
        """
        tm = TokenManager.instance()
        try:
            tm.load_preset(name)
        except Exception as e:
            print(f"[ThemeManager] 加载预设失败 {name}: {e}", flush=True)
            return False

        try:
            save_theme_preset(name)
        except Exception as e:
            print(f"[ThemeManager] 保存预设失败: {e}", flush=True)
            # 保存失败不影响内存中的主题生效

        self.theme_changed.emit(name)
        print(f"[ThemeManager] 已切换到: {name}", flush=True)
        return True

    # ── 查询辅助 ──

    @property
    def current_preset(self) -> str:
        """当前预设名。"""
        return TokenManager.instance().current_preset
