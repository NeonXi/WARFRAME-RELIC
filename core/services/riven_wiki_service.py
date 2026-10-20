"""
[L-Service] RivenWikiService — 武器 Wiki 反查（紫卡倾向查询辅助）

依赖: Python 标准库(sqlite3 / pathlib) + core.paths
禁止: PySide6 / QtWidgets / QtGui / QtCore（纯逻辑层）
返回: dict / list / str（绝不返回 Qt 对象）

背景:
    玩家想知道某把武器的紫卡倾向值(Disposition)，需要去英文 Wiki 查。
    wiki.warframe.com 有 JS 反爬挑战(Anubis/Please wait)，程序直连抓取
    会被 403/连接重置，因此本服务不做任何网络请求，只负责:
        中文/英文武器名 → wiki.warframe.com 的武器页 URL
    打开浏览器由 UI 层完成(QDesktopServices.openUrl) —— 真实浏览器能
    自然通过反爬挑战，用户自己点击/回车即可查看页面里的 Disposition。

数据源:
    warframe.db items 表:
      - zh_name / name   → 中英文武器名(如 "阿利乌双枪 Prime" / "Akarius Prime")
      - zh_pinyin        → 拼音全拼(如 "aliwushuangqiang prime"，与物品查询页同源，
                           639 把武器 100% 覆盖)，支持 "aliwu" / "liebao prime" 检索
      - wikia_url        → 现成 wiki 链接(如 https://wiki.warframe.com/w/Akarius_Prime)
      - category         → 武器类目筛选(Primary 步枪/霰弹, Secondary 手枪, Melee 近战)
    wikia_url 缺失时按英文名回退拼接: https://wiki.warframe.com/w/{Name_With_Underscores}

用法:
    svc = RivenWikiService()
    svc.search_weapons("阿利乌", limit=10)   # 模糊搜索(自动补全候选)
    svc.resolve_weapon("阿利乌双枪 Prime")   # 精确匹配(回车直接跳转用)

模块级便捷函数(页面直接用，内部持懒创建单例):
    riven_wiki_service.search_weapons(...) / resolve_weapon(...)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from core.paths import ensure_user_file as _ensure_db_file

DB_PATH = _ensure_db_file("warframe.db")

# Wiki 页面 URL 前缀(不变部分,与用户约定一致)
WIKI_BASE = "https://wiki.warframe.com/w/"

# 可查倾向的武器类目(紫卡适用: 步枪/霰弹枪=Primary, 手枪=Secondary, 近战=Melee)
WEAPON_CATEGORIES = ("Primary", "Secondary", "Melee")

# 搜索排名: 精确匹配 > 前缀匹配 > 包含匹配(值越小越靠前)
_RANK_EXACT = 0
_RANK_PREFIX = 1
_RANK_CONTAINS = 2


class RivenWikiService:
    """武器名 → Wiki 链接解析服务。

    单例语义(类级 DB 路径共享)，每次操作独立获取连接，
    与 ItemService 的连接模式一致，避免跨请求状态污染。
    db_path 可注入(测试隔离)。
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DB_PATH

    # ── 连接管理(与 ItemService 相同的获取/关闭模式) ──

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        """获取数据库连接，文件不存在/打开失败返回 None。"""
        if not Path(self._db_path).exists():
            return None
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error:
            return None

    @staticmethod
    def _close(conn: Optional[sqlite3.Connection]) -> None:
        """关闭连接，忽略异常。"""
        if conn is None:
            return
        try:
            conn.close()
        except sqlite3.Error:
            pass

    # ── 查询 ──

    def search_weapons(self, keyword: str, limit: int = 15) -> list[dict]:
        """模糊搜索武器(支持中文/英文/拼音)，返回候选列表。

        Args:
            keyword: 关键词(如 "阿利乌" / "Akarius" / "aliwu" / "liebao prime")
            limit: 返回数量上限(下拉候选展示用，默认 15)

        Returns:
            [{"zh_name", "en_name", "pinyin", "category", "wiki_url"}, ...]
            排名规则: 精确匹配 > 前缀匹配 > 包含匹配(中/英/拼音任一命中)；
            同级内 Prime 优先、再按中文名字典序。数据库缺失返回空列表。
        """
        kw = (keyword or "").strip()
        # 清洗 LIKE 通配符：武器名不含 %/_，直接剥离避免 SQL 语义污染
        kw = kw.replace("%", "").replace("_", "")
        if not kw:
            return []

        conn = self._get_conn()
        if conn is None:
            return []
        try:
            placeholders = ",".join("?" for _ in WEAPON_CATEGORIES)
            rows = conn.execute(
                f"SELECT name, zh_name, category, is_prime, wikia_url, zh_pinyin "
                f"FROM items "
                f"WHERE category IN ({placeholders}) "
                f"AND (zh_name LIKE ? OR name LIKE ? OR zh_pinyin LIKE ?)",
                (
                    *WEAPON_CATEGORIES,
                    f"%{kw}%",
                    f"%{kw}%",
                    f"%{kw.lower()}%",  # zh_pinyin 存的是小写
                ),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            self._close(conn)

        kw_lower = kw.lower()
        items: list[dict] = []
        for row in rows:
            en_name = (row["name"] or "").strip()
            zh_name = (row["zh_name"] or "").strip()
            if not en_name:
                continue
            pinyin = (row["zh_pinyin"] or "").strip()
            # wikia_url 缺失/为空时按英文名回退拼接(与用户约定的 URL 规则一致)
            wiki_url = (row["wikia_url"] or "").strip() or self.build_wiki_url(en_name)
            items.append({
                "zh_name": zh_name or en_name,
                "en_name": en_name,
                "pinyin": pinyin,
                "category": row["category"] or "",
                "is_prime": bool(row["is_prime"]),
                "rank": self._rank(
                    kw_lower, zh_name.lower(), en_name.lower(), pinyin.lower()
                ),
                "wiki_url": wiki_url,
            })

        # 排名 → Prime 优先 → 中文名升序，结果稳定可预期
        items.sort(key=lambda it: (it["rank"], 0 if it["is_prime"] else 1, it["zh_name"]))
        # rank/is_prime 只是排序辅助键，不作为对外契约返回
        for it in items:
            del it["rank"]
            del it["is_prime"]
        return items[:limit]

    def resolve_weapon(self, keyword: str) -> Optional[dict]:
        """精确解析单个武器名(大小写不敏感)，用于回车直接跳转。

        仅当中文名、英文名或拼音全拼完全相等时命中；模糊结果请走
        search_weapons 让用户从候选中选，避免打开错误的页面。
        """
        kw = (keyword or "").strip().lower()
        if not kw:
            return None
        for it in self.search_weapons(kw, limit=50):
            if kw in (it["zh_name"].lower(), it["en_name"].lower(), it["pinyin"].lower()):
                return it
        return None

    # ── 内部工具 ──

    @staticmethod
    def _rank(
        keyword_lower: str,
        zh_lower: str,
        en_lower: str,
        pinyin_lower: str,
    ) -> int:
        """计算搜索排名(内部用)，中/英/拼音三路取最优。"""
        candidates = (zh_lower, en_lower, pinyin_lower)
        if keyword_lower in candidates:
            return _RANK_EXACT
        if any(c.startswith(keyword_lower) for c in candidates if c):
            return _RANK_PREFIX
        return _RANK_CONTAINS

    @staticmethod
    def build_wiki_url(en_name: str) -> str:
        """按约定拼接 Wiki 页面 URL：空格转下划线，无空格。

        例: "Akarius Prime" → https://wiki.warframe.com/w/Akarius_Prime
        """
        slug = (en_name or "").strip().replace(" ", "_")
        return f"{WIKI_BASE}{slug}"


# ══════════════════════════════════════════════
#  模块级便捷函数（页面直接调用，内部懒创建单例）
# ══════════════════════════════════════════════

_default_service: Optional[RivenWikiService] = None


def _service() -> RivenWikiService:
    """懒创建默认服务实例（DB 路径取 ensure_user_file 结果）。"""
    global _default_service
    if _default_service is None:
        _default_service = RivenWikiService()
    return _default_service


def search_weapons(keyword: str, limit: int = 15) -> list[dict]:
    """模块级便捷入口：模糊搜索武器，见 RivenWikiService.search_weapons。"""
    return _service().search_weapons(keyword, limit)


def resolve_weapon(keyword: str) -> Optional[dict]:
    """模块级便捷入口：精确解析武器，见 RivenWikiService.resolve_weapon。"""
    return _service().resolve_weapon(keyword)
