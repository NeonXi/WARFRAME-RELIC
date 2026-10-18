"""
[L-Service] core.services.search_coordinator — 搜索协调器(简化版)

═══════════════════════════════════════════════════════════════════════
依赖图(严格自上而下,下层不能反向依赖)
═══════════════════════════════════════════════════════════════════════
  core.services.search_coordinator  ← 本文件
       ↓ 允许依赖
  core.services.item_service (ItemService 单例)
  core.services.wm_items_repository (WmItemsRepository 单例)
  core.state.price_query_state (PriceQueryState, TopStatus, SearchSubStatus)
  core.logging_utils (调试日志)
  Python 标准库 (threading, re, pathlib)
       ↓ 禁止依赖
  PySide6.QtWidgets / QtGui
  core.widgets.* / core.pages.*

═══════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════
  - 协调 ItemService 搜索(中/英/拼音,自动检测)
  - 加 黑名单 category 过滤(排除不可交易物品,用户决策 2026-08-07)
  - 异步 + 同步两个 API
  - 根据 State 顶层状态自动降级
  - 搜索结果统一格式化(name, zh_name, slug, tags, degraded)

═══════════════════════════════════════════════════════════════════════
搜索策略(简化版,2026-08-07)
═══════════════════════════════════════════════════════════════════════
  与 ItemsPage 页面共享 ItemService 搜索逻辑:
    - 主搜索走 ItemService.search(query, search_field, limit=N)
    - search_field 智能选择: 中文走 zh, 英文走 en
    - 支持中/英/拼音(自动检测)
  用户决策的过滤层:
    - 黑名单 category 过滤(Glyphs / Sigils / Emotes / Ship Decoration 等)
    - 这些是"明显不能交易"的纯装饰品类,必须排除
  用户决策的不做的事:
    - 不做 Prime 部件(Blueprint/Chassis/Barrel)补全(items 表里没 Prime 部件)
    - 不做部件类关键词特殊排序(纯字母序)
    - 不做战甲 zh 别名映射(战甲无中文名,直接显示英文)
    - 不做战甲优先 / 热门前置 / 同战甲聚类
  注: items.tradable 字段数据错误(战甲/武器都标 0, mod 反而标 1), 不可用。
      因此用 category 黑名单做"可交易"过滤, 而非字段判断。

  顶层状态 READY:   ItemService.search + 黑名单过滤
  顶层状态 DEGRADED: 跳过黑名单过滤(降级, 让用户至少能搜到名字)
  其他状态:         不响应(已发错误信号)
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from core.services.item_service import ItemService
from core.services.wm_items_repository import WmItemsRepository
from core.state.price_query_state import (
    PriceQueryState, TopStatus, SearchSubStatus,
)
from core.logging_utils import log as _dbg


if TYPE_CHECKING:
    pass


# ════════════════════════════════════════════════════════════════════════
#  配置常量
# ════════════════════════════════════════════════════════════════════════

# 主搜索条目上限(传给 ItemService.search, 给排序/过滤留余地)
SEARCH_ITEM_LIMIT = 200

# 最终结果上限
SEARCH_MAX_RESULTS = 20

# ── 不可交易物品黑名单(category 级别) ──
# 为什么不直接用 items.tradable 字段?
#   - 战甲 / 武器 items.tradable=0(错), mod items.tradable=1(也错)
#   - 数据来源有 bug, 字段不可信
# 为什么不完全照搬 ItemsPage?
#   - ItemsPage 列出所有物品(含浮印/外观), 价格页不需要这些(WM 上查不到)
# 为什么不走 WM 列表白名单?
#   - WM 列表只有 1612 个 Prime 物品, 缺 mod / 基础武器 / 战甲本体
#   - 会丢失"加速冲击"等 mod 搜索(用户痛点)
# 因此: 用 category 黑名单 排除"明显不可交易"的纯装饰品类。
# Skins 分类(2026-08-07 加入): 用户决策, 皮肤类物品(头盔/外观/摇头娃娃/色板等)都不能交易
#  加入后, 搜 "Rhino" 前 20 条能出现 Rhino Prime 本体, 而不是一堆 Noggle 玩具
_EXCLUDED_CATEGORIES: frozenset[str] = frozenset({
    "Glyphs",            # 浮印(完全不能交易)
    "Sigils",            # 纹章(完全不能交易)
    "Emotes",            # 表情动作
    "Color Palette",     # 色板
    "Fur Color",         # 毛色
    "Node",              # 星球节点(完全不能交易)
    "Quests",            # 任务物品
    "Skins",             # 皮肤/外观/头盔/摇头娃娃(WM 上不卖)
})

# 已知后缀(用于生成 tags 字段,供 UI 排序/着色)
_SET_SUFFIX = " Set"
_BLUEPRINT_SUFFIX = " Blueprint"
_CHASSIS_SUFFIX = " Chassis Blueprint"
_NEUROPTICS_SUFFIX = " Neuroptics Blueprint"
_SYSTEMS_SUFFIX = " Systems Blueprint"
_BLUEPRINT_SUFFIXES = (
    " Blueprint", " Chassis Blueprint", " Neuroptics Blueprint", " Systems Blueprint",
)
_WEAPON_PART_SUFFIXES = (
    " Barrel", " Receiver", " Stock", " Blade", " Handle", " Link", " Guard",
)


# ════════════════════════════════════════════════════════════════════════
#  SearchCoordinator — 搜索协调器(单例,简化版)
# ════════════════════════════════════════════════════════════════════════

class SearchCoordinator:
    """搜索协调器(单例,简化版)。

    异步: search_async(kw) 启动后台线程,通过 State 发信号
    同步: search_blocking(kw) 直接返回 list[dict](测试用)

    设计: 与 ItemsPage 共享 ItemService 搜索逻辑,
    仅在结果格式化(WF Market slug)上做适配。
    """

    _instance: "SearchCoordinator | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "SearchCoordinator":
        with cls._lock:
            if cls._instance is None:
                cls._instance = SearchCoordinator()
        return cls._instance

    def __init__(self) -> None:
        self._item_svc = ItemService()
        self._repo = WmItemsRepository.instance()
        self._state = PriceQueryState.instance()
        # 防止同一关键词重复搜
        self._search_lock = threading.Lock()
        self._search_in_progress: set[str] = set()
        self._current_thread: threading.Thread | None = None

    # ══════════════════════════════════════════════════════
    #  公开 API
    # ══════════════════════════════════════════════════════

    def search_async(self, keyword: str) -> None:
        """异步搜索。结果通过 State 信号(search_completed/failed/empty)通知。

        Args:
            keyword: 用户输入的关键词
        """
        keyword = keyword.strip()
        if not keyword:
            return

        with self._search_lock:
            if keyword in self._search_in_progress:
                _dbg("search", f"search_async: {keyword!r} 已在搜索, 跳过")
                return
            self._search_in_progress.add(keyword)

        self._state.set_search_status(SearchSubStatus.SEARCHING, keyword=keyword)
        self._state.search_started.emit()

        thread = threading.Thread(
            target=self._search_worker,
            args=(keyword,),
            daemon=True,
            name=f"Search-{keyword[:16]}",
        )
        self._current_thread = thread
        thread.start()

    def search_blocking(self, keyword: str) -> list[dict]:
        """同步搜索(测试用)。同样完整处理:slug 适配 + 字母序 + 限制。"""
        keyword = keyword.strip()
        if not keyword:
            return []
        top = self._state.top_status
        if top == TopStatus.READY:
            raw = self._search_tradable(keyword)
        elif top == TopStatus.DEGRADED:
            raw = self._search_all_items(keyword)
        else:
            return []
        return self._post_process(raw, keyword)

    # ══════════════════════════════════════════════════════
    #  后台 worker
    # ══════════════════════════════════════════════════════

    def _search_worker(self, keyword: str) -> None:
        """后台线程:根据 State 顶层状态走对应策略。"""
        try:
            top = self._state.top_status
            if top == TopStatus.READY:
                results = self._search_tradable(keyword)
            elif top == TopStatus.DEGRADED:
                _dbg("search", f"_search_worker: 降级模式, 搜索所有物品 {keyword!r}")
                results = self._search_all_items(keyword)
            elif top == TopStatus.LOADING:
                _dbg("search", f"_search_worker: 列表加载中, 等 1s 重试")
                import time
                time.sleep(1.0)
                # 再判断一次
                top = self._state.top_status
                if top == TopStatus.READY:
                    results = self._search_tradable(keyword)
                else:
                    results = self._search_all_items(keyword)
            else:
                # IDLE / FAILED
                self._state.set_search_status(SearchSubStatus.FAILED, keyword=keyword)
                self._state.search_failed.emit(f"列表不可用 ({top.value})")
                return

            # 后处理:字母序 + 限制条数
            results = self._post_process(results, keyword)

            if results:
                self._state.set_search_status(SearchSubStatus.READY, keyword=keyword)
                self._state.set_last_results(results)
                self._state.search_completed.emit(results)
            else:
                self._state.set_search_status(SearchSubStatus.EMPTY, keyword=keyword)
                self._state.search_empty.emit(keyword)

        except Exception as e:
            _dbg("search", f"_search_worker 异常: {type(e).__name__}: {e}")
            self._state.set_search_status(SearchSubStatus.FAILED, keyword=keyword)
            self._state.search_failed.emit(f"{type(e).__name__}: {e}")
        finally:
            with self._search_lock:
                self._search_in_progress.discard(keyword)

    # ══════════════════════════════════════════════════════
    #  搜索阶段
    # ══════════════════════════════════════════════════════

    def _search_tradable(self, keyword: str) -> list[dict]:
        """正常模式: 主搜索 + 黑名单 category 过滤。

        设计:
          - 主搜索走 ItemService.search(query, search_field, limit=200)
            → search_field 智能选择: 中文走 zh, 英文/数字走 en
            → 避免 "Rhino" 同时匹配 zh_name='鎏金狂野犀牛' 等装饰物
          - 黑名单 category 过滤(模块级 _EXCLUDED_CATEGORIES)
            → 排除 Glyphs/Sigils/Emotes/Color Palette 等纯装饰品
            → 保留 Warframes/Primary/Secondary/Melee/Mods/Arcanes/Relics/Misc 等
          - WM 列表仅用于 slug 查找(en_name → slug),不作为过滤
            → 因为 WM 列表不包含 mod/Forma/基础武器/战甲本体,做白名单会丢用户痛点
          - 战甲本体在 items 表里 zh_name 通常为空, 用户要求保留显示英文
            → 没中文就显示英文(用户原话: "战甲就没有中文名 就不需要中文对应了")
        """
        items = self._item_svc.search(
            query=keyword,
            search_field=self._detect_search_field(keyword),
            limit=SEARCH_ITEM_LIMIT,
        )
        return self._format_items(items, apply_category_filter=True)

    def _search_all_items(self, keyword: str) -> list[dict]:
        """降级模式: WM 列表为空(网络失败),返回所有 items(标记 degraded)。

        牺牲准确性换取可用性: 即使 WM 列表加载失败, 用户仍能搜到物品名,
        点击查询会因 slug 不在 WM 列表里失败(显示错误提示)。
        """
        items = self._item_svc.search(
            query=keyword,
            search_field=self._detect_search_field(keyword),
            limit=SEARCH_ITEM_LIMIT,
        )
        return self._format_items(items, apply_category_filter=False)

    @staticmethod
    def _detect_search_field(keyword: str) -> str:
        """根据关键词自动选择 search_field。

        规则:
          - 包含中文字符 → "zh"  (zh_name LIKE)
          - 纯英文/数字   → "en"  (name LIKE, 避免命中 zh_name 里的干扰项)
          - 空          → "en"

        为什么不走 "all" (zh+en+unique 都搜)?
          - 搜 "Rhino" 同时匹配 zh_name="鎏金狂野犀牛" → 返回一堆外观/浮印,
            真正的 Rhino Prime 本体被挤掉。
          - 搜 "加速冲击" 必须走 zh 才能命中, 走 en 命不中。
        """
        if any('\u4e00' <= ch <= '\u9fff' for ch in keyword):
            return "zh"
        return "en"

    def _format_items(
        self, items: list[dict], apply_category_filter: bool = True,
    ) -> list[dict]:
        """把 ItemService 返回的 item 列表转成 UI 友好的搜索结果。

        每个结果字段:
          - name:     英文名(WM API 主键)
          - zh_name:  中文名(战甲可能为空 → UI 显示英文)
          - slug:     warframe.market 用的 slug
          - tags:     部件类标签(mod / warframe / rifle 等),供 UI 排序
          - category: 物品分类(原始值,供 Prime 部件扩展使用)
          - degraded: True 表示 slug 走的是 en_name 兜底(WM 列表里没这个 en_name)
          - is_part:  True 表示这是 Prime 部件补全(扩展自战甲本体,可选)

        过滤策略:
          - apply_category_filter=True: 排除 _EXCLUDED_CATEGORIES 里的物品
            → 正常模式, 排除明显不可交易的装饰品
          - apply_category_filter=False: 全部保留
            → 降级模式, 让用户至少能搜到名字

        slug 适配:
          1. 优先 WM 列表精确匹配(取列表里的 slug, 通常含 Prime)
          2. 否则 en_name → slug(基础武器/战甲本体/mod 等走这里, 标 degraded)

        Prime 部件扩展(方案 A, 2026-08-07):
          - 收集结果里的 Prime 战甲本体
          - 调 ItemService.get_prime_parts_for_warframes 取 Blueprint/Chassis/Neuroptics/Systems
          - 用 prime_parts 自己的 slug(已权威, 不标 degraded)
          - 按字母序自然排在战甲本体之后
        """
        # 预构建 WM 索引: en_name.lower() → (slug, tags)
        wm_index: dict[str, tuple[str, list[str]]] = {}
        for wm_name, wm_slug, wm_tags in self._repo.get_items():
            wm_index[wm_name.lower()] = (wm_slug, list(wm_tags))

        results: list[dict] = []
        seen: set[str] = set()
        # 收集 Prime 战甲本体(用于扩展部件)
        prime_warframe_names: list[str] = []

        for it in items:
            en = it.get("en_name", "").strip()
            if not en:
                continue

            # 黑名单 category 过滤
            category = it.get("category", "") or ""
            if apply_category_filter and category in _EXCLUDED_CATEGORIES:
                continue

            en_lower = en.lower()
            wm_hit = wm_index.get(en_lower)

            # slug 解析
            if wm_hit is not None:
                slug, wm_tags = wm_hit
                degraded = False
            else:
                # WM 列表里没这个 en_name(mod / 基础武器 / 战甲本体等)
                slug = self._slugify(en)
                wm_tags = []
                degraded = True

            if slug in seen:
                continue
            seen.add(slug)

            # tags 合并: WM 自带 tags + 部件后缀推断 + 物品 category
            tags = self._merge_tags(wm_tags, en, category)

            results.append({
                "name": en,
                "zh_name": it.get("zh_name", ""),
                "slug": slug,
                "tags": tags,
                "category": category,
                "degraded": degraded,
            })

            # 收集 Prime 战甲本体(用于方案 A 扩展部件)
            # 条件: category=Warframes AND name 以 " Prime" 结尾
            #       排除 "Prime Set" 套装(不是本体)
            if (
                category == "Warframes"
                and en.endswith(" Prime")
                and not en.endswith(" Prime Set")
            ):
                prime_warframe_names.append(en)

        # ── Prime 部件扩展(方案 A) ──
        if prime_warframe_names:
            parts = self._item_svc.get_prime_parts_for_warframes(prime_warframe_names)
            for p in parts:
                en = p.get("en_name", "").strip()
                if not en:
                    continue
                # slug 优先用 prime_parts 表的(权威)
                slug = p.get("slug", "").strip() or self._slugify(en)
                if not slug or slug in seen:
                    continue
                seen.add(slug)

                part_type = p.get("part_type", "")
                # tags: Blueprint 标 blueprint, 其他战甲部件标 part
                tags = ["part"]
                if part_type == "Blueprint":
                    tags = ["blueprint", "part"]
                elif part_type in ("Chassis", "Neuroptics", "Systems"):
                    tags = ["part", part_type.lower()]

                results.append({
                    "name": en,
                    "zh_name": p.get("zh_name", ""),
                    "slug": slug,
                    "tags": tags,
                    "category": "Warframes",  # 标 Warframes 让 UI 显示一致
                    "degraded": False,         # 部件自带权威 slug, 不标降级
                    "is_part": True,           # 标记是 Prime 部件补全
                })

        return results

    @staticmethod
    def _merge_tags(
        wm_tags: list[str], en_name: str, category: str = "",
    ) -> list[str]:
        """合并 WM 列表的 tags + 部件后缀推断的 tags + 物品 category。

        优先级: WM tags > 部件后缀推断 > category 兜底
        例: wm_tags=["warframe", "blueprint"], en="Rhino Prime Blueprint"
            → ["warframe", "blueprint"]
        例: wm_tags=[], en="Rhino Prime", category="Warframes"
            → ["Warframes"]
        """
        tags: list[str] = []
        if wm_tags:
            tags.extend(wm_tags)
        en_lower = en_name.lower()
        if en_lower.endswith(_SET_SUFFIX.lower()) and "set" not in tags:
            tags.append("set")
        for sfx in _BLUEPRINT_SUFFIXES:
            if en_lower.endswith(sfx.lower()) and "blueprint" not in tags:
                tags.append("blueprint")
                break
        for sfx in _WEAPON_PART_SUFFIXES:
            if en_lower.endswith(sfx.lower()):
                tags.append("part")
                break
        # category 兜底(WM tags 为空时给 UI 一个分类标识)
        if not tags and category:
            tags.append(category.lower())
        return tags

    # ══════════════════════════════════════════════════════
    #  后处理
    # ══════════════════════════════════════════════════════

    def _post_process(self, results: list[dict], keyword: str) -> list[dict]:
        """搜索结果后处理: 字母序 + 限制条数(简化版)。

        排序:
          - 优先按 en_name 字母序
          - 完全相同的字母序里,带中文翻译的排前面(更易识别)
        """
        results.sort(key=lambda x: (
            x.get("name", "").lower(),
            0 if x.get("zh_name") else 1,  # 有中文的排前
        ))
        return results[:SEARCH_MAX_RESULTS]

    # ══════════════════════════════════════════════════════
    #  工具方法
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _slugify(name: str) -> str:
        """英文名 → slug(en_name → warframe_prime 等)。

        "Rhino Prime"            → "rhino_prime"
        "Acceltra Prime"         → "acceltra_prime"
        "Accelerated Blast"      → "accelerated_blast"
        """
        return name.lower().replace(" ", "_").replace("'", "")

    def _find_slug_by_name(self, en_name: str) -> str | None:
        """用 en_name 在 WM 列表里查 slug(精确匹配,不区分大小写)。

        用于回退 / 兼容性场景(目前 _format_items 内部已合并,留作公开工具)。
        """
        en_lower = en_name.lower()
        for name, slug, _tags in self._repo.get_items():
            if name.lower() == en_lower:
                return slug
        return None
