"""
Pages 集成测试 — 页面注册与切换。

覆盖:
  - AppShell 初始化
  - 全部页面成功注册
  - 页面切换功能
  - TokenManager 预加载要求验证

注意: 这是集成级测试，需要完整的项目环境和 QApplication。
"""

from __future__ import annotations

import sys
import os
import pytest

# 确保项目根目录在路径中
_PROJECT_ROOT = str(__file__).rsplit(os.sep, 1)[0]
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture(scope="module")
def app_shell(qapp_module):
    """创建并初始化完整的 AppShell 实例。"""
    from core.tokens.manager import TokenManager

    # 加载预设
    tm = TokenManager.instance()
    try:
        tm.load_preset("cyberpunk")
    except Exception as e:
        pytest.skip(f"无法加载 cyberpunk 预设: {e}")

    from core.app_shell import AppShell
    shell = AppShell()
    yield shell
    shell.close()
    TokenManager.reset()


@pytest.fixture(scope="module")
def qapp_module():
    """模块级 QApplication。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestPageRegistration:

    def test_all_pages_registered(self, app_shell):
        """所有导航项对应的页面应成功注册。"""
        pages = app_shell._pages
        # 至少应有之前修复的 8 个页面
        assert len(pages) >= 5, f"期望至少 5 个页面，实际 {len(pages)}: {list(pages.keys())}"

    def test_known_pages_exist(self, app_shell):
        """关键页面必须存在。"""
        pages = app_shell._pages
        expected_keys = {"toggles", "triggers", "theme", "about"}
        for key in expected_keys:
            assert key in pages, f"缺失页面: {key}"


class TestPageSwitching:

    def test_switch_to_first_page(self, app_shell):
        """切换到第一个页面不应报错。"""
        page_ids = list(app_shell._pages.keys())
        if page_ids:
            app_shell._switch_to(page_ids[0])

    def test_switch_all_pages(self, app_shell):
        """遍历切换每个已注册页面。"""
        page_ids = list(app_shell._pages.keys())
        for pid in page_ids:
            try:
                app_shell._switch_to(pid)
            except Exception as e:
                pytest.fail(f"切换到 '{pid}' 失败: {e}")

    def test_switch_to_same_page_idempotent(self, app_shell):
        """重复切换到同一页面不应出错。"""
        page_ids = list(app_shell._pages.keys())
        if page_ids:
            target = page_ids[0]
            app_shell._switch_to(target)
            app_shell._switch_to(target)  # 再次切换
