"""
数据库连接注册表

集中管理所有模块缓存的 SQLite 连接，在数据库重建前一键关闭所有连接，
释放文件锁，确保 shutil.copy2 能成功覆盖 warframe.db。

使用方式:
    # 注册（在创建持久连接时）
    from data.db_connections import db_conn_registry
    db_conn_registry.register("relic_db", relic_db_instance)
    db_conn_registry.register("search_widget", search_widget_instance)

    # 关闭所有连接（构建前调用）
    from data.db_connections import close_all_db_connections
    close_all_db_connections()

    # 注销（对象销毁时）
    db_conn_registry.unregister("relic_db")
"""

from typing import Any, Callable, Optional


class _DBConnectionRegistry:
    """轻量级数据库连接注册表。"""

    def __init__(self):
        self._handlers: dict[str, Callable[[], None]] = {}

    def register(self, name: str, closer: Callable[[], None]):
        """
        注册一个可关闭的连接。

        Args:
            name: 唯一标识符（如 "relic_db"、"search_widget"）
            closer: 无参调用时关闭该连接的函数/方法
        """
        self._handlers[name] = closer

    def unregister(self, name: str):
        """注销一个连接。"""
        self._handlers.pop(name, None)

    def close_all(self):
        """关闭所有已注册的连接。"""
        for name, closer in list(self._handlers.items()):
            try:
                closer()
            except Exception:
                pass
        self._handlers.clear()

    def registered_names(self) -> list[str]:
        """返回所有已注册的名称（用于调试）。"""
        return list(self._handlers.keys())


# 全局单例
db_conn_registry = _DBConnectionRegistry()


def close_all_db_connections():
    """便捷函数：关闭所有已注册的数据库连接。"""
    db_conn_registry.close_all()
