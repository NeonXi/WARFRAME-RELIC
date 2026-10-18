"""
分层依赖规则守卫（对应 `.trae/rules/开发规范.md` §2 / §6）

这些规则过去只写在文档和每个文件的头部注释里，靠人自觉。本文件把它们
变成可执行断言：任何新代码引入跨层依赖，都会在 pytest 阶段直接失败。

设计取舍：
  - 只检查**静态 import**。函数内惰性导入同样会被检查（除非该规则只约束
    模块顶层，如 Token 层允许函数内 import QColor）。
  - 相对导入（level > 0）不跨包，直接跳过。
  - 允许清单故意保持最小：新增合法依赖时应修改本文件，而不是绕过检查。
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "core"
PROJECT = CORE.parent


def _iter_imports(path: Path):
    """产出 (行号, 模块名, 是否模块顶层语句)。"""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, node.col_offset == 0
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对导入不跨包
                continue
            yield node.lineno, node.module or "", node.col_offset == 0


def _layer_files(subdir: str):
    return sorted(
        p for p in (CORE / subdir).glob("*.py")
        if p.name != "__init__.py" and "__pycache__" not in p.parts
    )


def _violations(
    subdir: str,
    forbidden: tuple[str, ...],
    *,
    module_level_only: bool = False,
) -> list[str]:
    """返回违规描述列表，形如 'core/state/x.py:12 -> core.services.y'。"""
    found: list[str] = []
    for path in _layer_files(subdir):
        for lineno, module, is_top_level in _iter_imports(path):
            if module_level_only and not is_top_level:
                continue
            if any(module == p or module.startswith(p + ".") for p in forbidden):
                rel = path.relative_to(PROJECT).as_posix()
                found.append(f"{rel}:{lineno} -> {module}")
    return found


def _assert_clean(violations: list[str], rule: str) -> None:
    assert not violations, (
        f"{rule}\n违规导入：\n  " + "\n  ".join(violations)
        + "\n\n修复方向见 .trae/rules/开发规范.md §2 分层依赖表。"
    )


def test_tokens_layer_has_no_module_level_qt():
    """Token 层必须在无 Qt 的进程里可导入（函数内惰性导入 QColor 除外）。"""
    _assert_clean(
        _violations("tokens", ("PySide6",), module_level_only=True),
        "Token 层禁止模块级 import PySide6（§6.1）。",
    )


def test_services_layer_never_touches_widgets_or_gui():
    """Service 层禁止 QtWidgets/QtGui；QtCore 仅限 QObject/Signal/QTimer。"""
    _assert_clean(
        _violations("services", ("PySide6.QtWidgets", "PySide6.QtGui")),
        "Service 层禁止 import QtWidgets / QtGui（§6.2 / §7-1）。",
    )


def test_widgets_layer_does_not_depend_on_services_or_data():
    """Widget 只负责绘制与发信号，不调业务、不读数据。"""
    _assert_clean(
        _violations("widgets", ("core.services", "data")),
        "Widget 层禁止 import core.services / data（§6.4 / §7-2）。",
    )


def test_state_layer_does_not_depend_on_upper_layers():
    """State 是数据真相源，只能被上层读取，不能反向依赖。"""
    _assert_clean(
        _violations("state", ("core.services", "core.widgets", "core.pages")),
        "State 层禁止反向依赖 services / widgets / pages（§6.6）。",
    )


def test_recognizers_layer_stays_ui_free():
    """识别层输出纯数据，不碰 UI 与全局状态。"""
    _assert_clean(
        _violations("recognizers", ("core.widgets", "core.pages", "core.state")),
        "Recognizer 层禁止 import widgets / pages / state（§6.3）。",
    )


def test_tokens_importable_without_qt():
    """在「PySide6 不可用」的子进程里导入 tokens —— 证明运行期真的零 Qt 依赖。

    上一个用例只检查语法（模块顶层没有 import）；本用例是行为验证：
    即使 QColor 的类型注解存在，`from __future__ import annotations` +
    `TYPE_CHECKING` 也保证运行期不会去解析它。
    """
    code = textwrap.dedent(
        """
        import sys, importlib.abc

        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith("PySide6"):
                    raise ImportError(f"{fullname} blocked by test")
                return None

        sys.meta_path.insert(0, Block())
        import core.tokens.manager
        import core.tokens.resolver
        print("ok")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"无 Qt 导入失败:\n{proc.stderr}"
    assert "ok" in proc.stdout
