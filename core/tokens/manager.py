"""
Token 管理器 — Design Token 的统一访问入口。

提供单例模式的全局 token 访问，封装 TokenResolver 和预设加载逻辑。
本模块是唯一需要导入 PyYAML 的地方（用于加载 YAML 预设文件）。

使用方式::

    # 初始化（应用启动时调用一次）
    TokenManager.get().load_preset("cyberpunk")

    # 任意位置获取 token 值
    tm = TokenManager.get()
    color = tm.get("components.button.solid.fill")  → "#FFE600"
    height = tm.space("btn_md")                      → 36

See Also:
    ui-framework-design.md §2 颜色系统 — Design Token 架构

## AI 硬约束 — 修改本文件前必读
归属层:    [L-Infrastructure] (core/tokens/)
允许依赖:  PyYAML, Python 标准库
禁止依赖:  PySide6 / QtWidgets / QtCore(任何 Qt 命名空间)
           (Token 是数据层,不能引入 UI)
必读规范:  .trae/rules/开发规范.md §6.1

本文件相关红线:
- **模块顶层**禁止 import PySide6 → Token 必须能在无 Qt 的进程(单测/构建脚本)里导入
- 唯一例外:`get_qcolor()` 在函数内惰性导入 `QColor`(全项目仅此一处 Qt 触点)
- 类型注解可用 `TYPE_CHECKING` 导入 QColor(运行期不执行,不引入 Qt 依赖)
- 禁止在 Token 里持有 widget 引用
- 禁止在 Token 中做 IO(读文件应该 lazy)

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.1。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    # 仅供类型检查器/IDE 使用：运行期不会执行，因此不构成对 Qt 的依赖
    from PySide6.QtGui import QColor

try:
    import yaml
except ImportError:
    yaml = None

from core.tokens.resolver import TokenResolver, TokenResolveError
from core.paths import resource_dir as _resource_dir


# ═══════════════════════════════════════════════════
#  预设文件默认路径
# ═══════════════════════════════════════════════════

# 预设为只读资源:开发环境 = 项目根/data/presets;打包环境 = 解包目录/data/presets
_PRESETS_DIR = _resource_dir() / "presets"


# ═══════════════════════════════════════════════════
#  管理器核心
# ═══════════════════════════════════════════════════

class TokenManager:
    """Design Token 全局管理器。

    职责：
    - 加载和管理 YAML 预设文件
    - 封装 TokenResolver 提供统一的查询 API
    - 维护当前活跃主题状态
    - 提供分类便捷方法（get_color / get_space / get_component）

    设计原则：
    - 单例模式：全局只有一个实例，通过 TokenManager.get() 访问
    - 懒初始化：首次调用 get() 时才创建实例
    - 低耦合：不持有任何 UI 引用，纯数据层

    Attributes:
        current_preset: 当前加载的预设名称（如 "cyberpunk"）
    """

    _instance: Optional["TokenManager"] = None

    def __init__(self):
        if TokenManager._instance is not None:
            raise RuntimeError(
                "TokenManager 是单例类，请使用 TokenManager.get() 获取实例"
            )
        self._resolver: Optional[TokenResolver] = None
        self._preset_name: str = ""
        self._preset_data: dict[str, Any] = {}
        self._presets_dir: Path = _PRESETS_DIR

    # ─────────────────────────────────────────────
    #  单例接口
    # ─────────────────────────────────────────────

    @classmethod
    def instance(cls) -> "TokenManager":
        """获取全局单例实例。

        首次调用时自动创建。

        Returns:
            TokenManager 单例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（主要用于测试）。

        正常代码不应调用此方法。
        """
        if cls._instance is not None:
            cls._instance = None

    # ─────────────────────────────────────────────
    #  预设加载
    # ─────────────────────────────────────────────

    def load_preset(self, name: str, preset_dir: Optional[Path] = None) -> None:
        """从 YAML 文件加载主题预设。

        Args:
            name: 预设名称（不含扩展名），如 "cyberpunk"、"daylight"
            preset_dir: 自定义预设目录，默认为 data/presets/

        Raises:
            FileNotFoundError: 预设文件不存在
            ImportError: 未安装 PyYAML 库
            TokenResolveError: 预设文件格式错误或解析失败
        """
        if yaml is None:
            raise ImportError(
                "需要 PyYAML 库来加载预设文件。请执行: pip install pyyaml"
            )

        directory = preset_dir or self._presets_dir
        file_path = directory / f"{name}.yaml"

        if not file_path.exists():
            raise FileNotFoundError(
                f"预设文件不存在: {file_path}\n"
                f"可用目录: {directory}\n"
                f"可用预设: {self._list_available(directory)}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise TokenResolveError(
                name,
                f"预设文件根节点必须是字典，收到 {type(data).__name__}"
            )

        self._preset_data = data
        self._preset_name = name
        self._resolver = TokenResolver(data)

        # 预热：解析所有顶层键以确保无循环引用
        for top_key in data.keys():
            if top_key.startswith("_"):
                continue
            try:
                self._resolver.resolve(top_key)
            except TokenResolveError:
                pass  # 顶层字典解析失败是正常的（它们是命名空间）

    def load_from_dict(self, data: dict[str, Any], name: str = "custom") -> None:
        """直接从字典加载预设（用于测试或动态生成）。

        Args:
            data: 预设数据字典
            name: 预设名称标识
        """
        self._preset_data = data
        self._preset_name = name
        self._resolver = TokenResolver(data)

    # ─────────────────────────────────────────────
    #  Token 查询 API
    # ─────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """获取任意 token 的解析值。

        这是通用的查询入口。支持完整点分路径。

        Args:
            key: 点分路径，如 "components.button.solid.fill"
            default: 当 key 不存在时的默认返回值

        Returns:
            解析后的值，或 default（如果 key 不存在且提供了 default）

        Raises:
            TokenResolveError: 解析失败且未提供 default
            RuntimeError: 尚未加载任何预设
        """
        if self._resolver is None:
            return default
        try:
            return self._resolver.resolve(key)
        except TokenResolveError:
            if default is not None:
                return default
            raise

    def get_color(self, key: str) -> tuple[int, int, int]:
        """获取颜色 token 并返回 (R, G, B) 元组。

        Args:
            key: 颜色 token 路径

        Returns:
            (r, g, b) 元组
        """
        self._ensure_loaded()
        return self._resolver.resolve_color(key)

    def get_qcolor(self, key: str) -> "QColor":
        """获取颜色 token 并返回 QColor 对象。

        ★ 分层例外（开发规范 §6.1）：
        本模块**顶层**不得 import PySide6 —— Token 层必须能在无 Qt 的进程里
        被导入（单元测试/构建脚本）。QColor 转换是全项目唯一的 Qt 触点，
        因此只允许在函数内惰性导入，且仅限本方法。
        该不变量由 tests/test_layer_rules.py 自动守卫。

        Args:
            key: 颜色 token 路径

        Returns:
            QColor 实例

        Raises:
            ImportError: 非 GUI 环境（未安装 PySide6）调用时
        """
        from PySide6.QtGui import QColor
        r, g, b = self.get_color(key)
        return QColor(r, g, b)

    # ─────────────────────────────────────────────
    #  分类便捷方法
    # ─────────────────────────────────────────────

    def raw(self, key: str, default: Any = None) -> Any:
        """获取 Raw 层 token（快捷方式）。

        用法: tm.raw("brand.yellow") → "#FFE600"
        """
        return self.get(f"raw.{key}", default)

    def alias(self, key: str, default: Any = None) -> Any:
        """获取 Alias 层 token（快捷方式）。"""
        return self.get(f"alias.{key}", default)

    def semantic(self, key: str, default: Any = None) -> Any:
        """获取 Semantic 层 token（快捷方式）。"""
        return self.get(f"semantic.{key}", default)

    def component(self, comp_type: str, key: str, default: Any = None) -> Any:
        """获取 Component 层 token（快捷方式）。

        用法: tm.component("button", "solid.fill") → "#FFE600"
        """
        return self.get(f"components.{comp_type}.{key}", default)

    def space(self, key: str, default: int = 0) -> int:
        """获取 Space token（快捷方式），保证返回数值类型。

        用法: tm.space("height.btn_md") → 36
              tm.space("spacing.lg")   → 16
        """
        value = self.get(f"space.{key}", default)
        if isinstance(value, (int, float)):
            return int(value)
        return default

    def copy(self, key: str, default: str = "", **kwargs) -> str:
        """获取文案 token 并返回字符串。

        支持使用 Python format 语法进行模板替换。

        用法:
            tm.copy("status.title")                    → "数据库概览"
            tm.copy("status.update_complete", elapsed=5) → "基础数据更新完成! 总耗时: 5s"

        Args:
            key: 文案 token 路径（不含 "copy." 前缀）
            default: key 不存在时的默认返回值
            **kwargs: 模板变量（用于 .format() 替换）

        Returns:
            解析后的文案字符串
        """
        value = self.get(f"copy.{key}", default)
        if isinstance(value, str) and kwargs:
            try:
                return value.format(**kwargs)
            except (KeyError, IndexError):
                return value
        return str(value) if value is not None else default

    # ─────────────────────────────────────────────
    #  属性与调试
    # ─────────────────────────────────────────────

    @property
    def current_preset(self) -> str:
        """当前加载的预设名称。"""
        return self._preset_name

    @property
    def is_loaded(self) -> bool:
        """是否已加载预设。"""
        return self._resolver is not None

    @property
    def meta(self) -> dict[str, Any]:
        """返回预设的 _meta 信息。"""
        return self._preset_data.get("_meta", {})

    def list_resolved_keys(self, prefix: str = "") -> list[str]:
        """列出已解析的 token 键（支持前缀过滤）。

        用于调试和文档生成。

        Args:
            prefix: 可选前缀过滤，如 "components.button"

        Returns:
            匹配的 key 列表
        """
        self._ensure_loaded()
        keys = self._resolver.resolved_keys
        if prefix:
            return [k for k in keys if k.startswith(prefix)]
        return keys

    # ─────────────────────────────────────────────
    #  内部工具
    # ─────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """确保已加载预设。"""
        if self._resolver is None:
            raise RuntimeError(
                "TokenManager 尚未加载任何预设。请先调用 load_preset()。"
            )

    @staticmethod
    def _list_available(directory: Path) -> str:
        """列出可用预设文件名。"""
        if directory.exists():
            files = [f.stem for f in directory.glob("*.yaml")]
            return ", ".join(files) if files else "(空)"
        return f"(目录不存在: {directory})"
