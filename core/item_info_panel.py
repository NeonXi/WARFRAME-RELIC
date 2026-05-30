"""
物品信息查询面板 — 可扩展 Provider 架构

设计模式: Provider 模式 — 每个信息维度独立为一个 Provider

当前 Provider:
  - PriceProvider: 价格查询（通过 PriceService 统一服务）

扩展方式:
  新增 Provider 只需:
    1. 继承 ItemInfoProvider
    2. 实现 query() 和 format_annotation()
    3. 注册到 REGISTERED_PROVIDERS
"""

from abc import ABC, abstractmethod
from typing import Optional


# ============================================================
# Provider 基类
# ============================================================

class ItemInfoProvider(ABC):
    """物品信息提供者基类。

    每个 Provider 负责查询物品某一维度的信息。
    """

    name: str = "base"

    @abstractmethod
    def query(self, en_name: str) -> Optional[dict]:
        """查询物品信息。"""
        ...

    @abstractmethod
    def format_annotation(self, item: dict, info: dict) -> str:
        """将查询结果格式化为标注文本。"""
        ...


# ============================================================
# 价格提供者
# ============================================================

class PriceProvider(ItemInfoProvider):
    """warframe.market 价格信息提供者。

    通过 PriceService 统一查询（含缓存）。
    """

    name = "price"

    def query(self, en_name: str) -> Optional[dict]:
        from core.price_service import get_price_service
        return get_price_service().query_price(en_name)

    def format_annotation(self, item: dict, info: dict) -> str:
        """格式化为价格标注文本。"""
        from core.price_service import format_price_annotation
        return format_price_annotation(item)

    @staticmethod
    def get_annotation_color(price: Optional[dict], match_quality: str = '') -> str:
        """根据价格返回对应颜色。"""
        from core.price_service import price_to_color
        return price_to_color(price, match_quality)


# ============================================================
# Provider 注册表
# ============================================================

REGISTERED_PROVIDERS: list[ItemInfoProvider] = [
    PriceProvider(),
]


def get_providers() -> list[ItemInfoProvider]:
    """获取所有已注册的信息提供者。"""
    return REGISTERED_PROVIDERS


def get_provider_by_name(name: str) -> Optional[ItemInfoProvider]:
    """按名称获取提供者。"""
    for p in REGISTERED_PROVIDERS:
        if p.name == name:
            return p
    return None


# ============================================================
# 复合查询
# ============================================================

def query_item_info(en_name: str, provider_names: list[str] = None) -> dict[str, dict]:
    """对单个物品查询多个维度的信息。"""
    if provider_names is None:
        providers = REGISTERED_PROVIDERS
    else:
        providers = [get_provider_by_name(n) for n in provider_names]
        providers = [p for p in providers if p is not None]

    result = {}
    for provider in providers:
        info = provider.query(en_name)
        if info:
            result[provider.name] = info
    return result


def format_item_annotation(item: dict, info_map: dict[str, dict]) -> str:
    """将多个 Provider 的信息合并为标注文本。"""
    if 'price' in info_map:
        provider = get_provider_by_name('price')
        return provider.format_annotation(item, info_map['price'])

    # 降级: 无价格信息时只显示名称
    from data.ui_strings import S
    en = item.get('en_name', '?')
    zh = item.get('zh_name', '')
    if zh:
        return S.format("overlay", "translate_label_fmt", zh_name=zh, en_name=en)
    return en
