"""
[L-Service Test] RivenWikiService 单元测试

覆盖:
  - 模糊搜索(中/英文、前缀/包含)
  - 精确解析(resolve_weapon)
  - 排名规则(exact > prefix > contains, Prime 优先)
  - wikia_url 缺失时按英文名兜底拼接
  - 空关键词 / DB 不存在降级
  - LIKE 通配符清洗(% 和 _ 不引发 SQL 异常)

测试用 tmp_path 自建最小 sqlite 库，不依赖真实 warframe.db。
"""

from __future__ import annotations

import sqlite3
import sys
import os

import pytest

_PROJECT_ROOT = str(__file__).rsplit(os.sep, 2)[0]
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.services.riven_wiki_service import RivenWikiService


_FAKE_ITEMS = [
    # zh_name, name, category, is_prime, wikia_url, zh_pinyin
    ("阿利乌双枪 Prime", "Akarius Prime", "Secondary", 1, "https://wiki.warframe.com/w/Akarius_Prime", "aliwushuangqiang prime"),
    ("阿利乌双枪", "Akarius", "Secondary", 0, "https://wiki.warframe.com/w/Akarius", "aliwushuangqiang"),
    ("猎豹 Prime", "Panthera Prime", "Primary", 1, "https://wiki.warframe.com/w/Panthera_Prime", "liebao prime"),
    ("台词编辑器", "Kitgun", "Secondary", 0, "", "taicibianjiqi"),  # wikia_url 缺失 → 兜底
    ("救世者", "Paracesis", "Melee", 0, "https://wiki.warframe.com/w/Paracesis", "jiushizhe"),
    ("某些皮肤", "Some Skin", "Skins", 0, "https://wiki.warframe.com/w/Some_Skin", "mouxiepifu"),  # 非武器类目
]


@pytest.fixture()
def svc(tmp_path):
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE items (name TEXT, zh_name TEXT, category TEXT, "
        "is_prime INTEGER, wikia_url TEXT, zh_pinyin TEXT)"
    )
    conn.executemany(
        "INSERT INTO items (zh_name, name, category, is_prime, wikia_url, zh_pinyin) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        _FAKE_ITEMS,
    )
    conn.commit()
    conn.close()
    return RivenWikiService(db_path=db)


class TestSearch:
    def test_search_chinese_keyword(self, svc):
        results = svc.search_weapons("阿利乌")
        names = [r["zh_name"] for r in results]
        assert names == ["阿利乌双枪 Prime", "阿利乌双枪"]  # Prime 优先

    def test_search_english_keyword(self, svc):
        results = svc.search_weapons("akarius")
        # "Akarius" 英文名精确匹配(rank 0) > "Akarius Prime" 前缀匹配(rank 1)
        assert [r["en_name"] for r in results] == ["Akarius", "Akarius Prime"]

    def test_exact_match_ranks_first(self, svc):
        results = svc.search_weapons("阿利乌双枪")
        # "阿利乌双枪 Prime" 是前缀匹配(rank 1)，"阿利乌双枪" 是精确匹配(rank 0)
        assert results[0]["zh_name"] == "阿利乌双枪"

    def test_prefix_before_contains(self, svc):
        # "猎豹" 精确匹配猎豹 Prime；"Panthera" 也应命中
        results = svc.search_weapons("Panthera")
        assert results[0]["en_name"] == "Panthera Prime"

    def test_non_weapon_category_excluded(self, svc):
        results = svc.search_weapons("皮肤")
        assert all(r["category"] != "Skins" for r in results)
        assert not any(r["zh_name"] == "某些皮肤" for r in results)

    def test_no_match_returns_empty(self, svc):
        assert svc.search_weapons("不存在的武器xyz") == []

    def test_empty_keyword_returns_empty(self, svc):
        assert svc.search_weapons("") == []
        assert svc.search_weapons("   ") == []

    def test_limit(self, svc):
        assert len(svc.search_weapons("a", limit=1)) == 1

    def test_like_wildcards_not_break_query(self, svc):
        # % 和 _ 不应导致 SQL 异常或命中全部
        results = svc.search_weapons("%")
        assert results == []


class TestPinyinSearch:
    """拼音搜索（复用 items.zh_pinyin，与物品查询页同源）。"""

    def test_pinyin_prefix_match(self, svc):
        results = svc.search_weapons("aliwu")
        assert [r["zh_name"] for r in results] == ["阿利乌双枪 Prime", "阿利乌双枪"]

    def test_pinyin_full_match_ranks_exact_first(self, svc):
        # 全拼与「阿利乌双枪」拼音完全相等 → 精确(rank 0)排前
        results = svc.search_weapons("aliwushuangqiang")
        assert results[0]["zh_name"] == "阿利乌双枪"
        assert results[1]["zh_name"] == "阿利乌双枪 Prime"

    def test_pinyin_with_prime_suffix(self, svc):
        results = svc.search_weapons("liebao")
        assert results[0]["en_name"] == "Panthera Prime"

    def test_pinyin_case_insensitive(self, svc):
        assert svc.search_weapons("ALIWU")[0]["en_name"] == "Akarius Prime"

    def test_result_contains_pinyin_field(self, svc):
        results = svc.search_weapons("aliwu")
        assert results[0]["pinyin"] == "aliwushuangqiang prime"

    def test_resolve_by_pinyin(self, svc):
        r = svc.resolve_weapon("aliwushuangqiang")
        assert r is not None and r["en_name"] == "Akarius"

    def test_resolve_by_pinyin_with_space(self, svc):
        r = svc.resolve_weapon("liebao prime")
        assert r is not None and r["en_name"] == "Panthera Prime"

    def test_resolve_by_pinyin_melee(self, svc):
        r = svc.resolve_weapon("jiushizhe")
        assert r is not None and r["zh_name"] == "救世者"


class TestResolve:
    def test_resolve_exact_chinese(self, svc):
        r = svc.resolve_weapon("阿利乌双枪 Prime")
        assert r is not None
        assert r["en_name"] == "Akarius Prime"
        assert r["wiki_url"] == "https://wiki.warframe.com/w/Akarius_Prime"

    def test_resolve_exact_english_case_insensitive(self, svc):
        r = svc.resolve_weapon("akarius prime")
        assert r is not None and r["en_name"] == "Akarius Prime"

    def test_resolve_fuzzy_returns_none(self, svc):
        assert svc.resolve_weapon("阿利乌") is None

    def test_resolve_empty(self, svc):
        assert svc.resolve_weapon("") is None


class TestWikiUrlFallback:
    def test_url_built_when_missing(self, svc):
        results = svc.search_weapons("Kitgun")
        assert len(results) == 1
        assert results[0]["wiki_url"] == "https://wiki.warframe.com/w/Kitgun"

    def test_build_wiki_url(self):
        assert RivenWikiService.build_wiki_url("Akarius Prime") == (
            "https://wiki.warframe.com/w/Akarius_Prime"
        )
        assert RivenWikiService.build_wiki_url("Paracesis") == (
            "https://wiki.warframe.com/w/Paracesis"
        )


class TestDbMissing:
    def test_missing_db_degrades(self, tmp_path):
        svc = RivenWikiService(db_path=tmp_path / "nonexistent.db")
        assert svc.search_weapons("阿利乌") == []
        assert svc.resolve_weapon("阿利乌双枪 Prime") is None
