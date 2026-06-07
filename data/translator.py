"""
游戏术语中英对照翻译模块。

数据来源: warframe.db → game_translations 表
  - key(唯一标识), en(英文), zh(中文), category(分类), source(来源)

翻译数据由 data_pipeline 构建，本模块仅提供查询接口。
"""

import sqlite3
from pathlib import Path

# ============================================================
# 配置
# ============================================================
DATA_DIR = Path(__file__).resolve().parent  # data/
DB_PATH = DATA_DIR / "warframe.db"

# 表名
TABLE = "game_translations"


# ============================================================
# 数据库连接
# ============================================================
def _get_connection() -> sqlite3.Connection:
    """获取 warframe.db 连接。"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ============================================================
# 查询接口
# ============================================================
def translate(key: str, lang: str = "zh") -> str:
    """根据 key 查询翻译。

    Args:
        key: 翻译 key，如 /Lotus/Language/Missions/MissionName_Crossfire
        lang: 目标语言 "zh" 或 "en"

    Returns:
        翻译文本，未找到返回空字符串
    """
    if not DB_PATH.exists():
        return ""
    conn = _get_connection()
    try:
        row = conn.execute(
            f"SELECT {lang} FROM {TABLE} WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def translate_by_en(en_text: str) -> str:
    """根据英文文本查找中文翻译（反向查找）。

    Args:
        en_text: 英文文本

    Returns:
        中文翻译，未找到返回空字符串
    """
    if not DB_PATH.exists():
        return ""
    conn = _get_connection()
    try:
        row = conn.execute(
            f"SELECT zh FROM {TABLE} WHERE en = ? LIMIT 1", (en_text,)
        ).fetchone()
        return row[0] if row and row[0] else ""
    finally:
        conn.close()


def search_zh(keyword: str, limit: int = 50) -> list[dict]:
    """全文搜索中文翻译。

    Args:
        keyword: 搜索关键词
        limit: 返回数量上限

    Returns:
        [{"key": ..., "en": ..., "zh": ..., "category": ...}, ...]
    """
    if not DB_PATH.exists():
        return []
    conn = _get_connection()
    try:
        rows = conn.execute(
            f"SELECT key, en, zh, category FROM {TABLE} "
            "WHERE zh LIKE ? OR en LIKE ? "
            "LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        return [
            {"key": r[0], "en": r[1], "zh": r[2], "category": r[3]} for r in rows
        ]
    finally:
        conn.close()


def get_categories() -> list[str]:
    """获取所有分类名。"""
    if not DB_PATH.exists():
        return []
    conn = _get_connection()
    try:
        rows = conn.execute(
            f"SELECT DISTINCT category FROM {TABLE} ORDER BY category"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_stats() -> dict:
    """获取翻译数据统计信息。"""
    if not DB_PATH.exists():
        return {"exists": False}
    conn = _get_connection()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        cats = conn.execute(
            f"SELECT COUNT(DISTINCT category) FROM {TABLE}"
        ).fetchone()[0]
        sources = conn.execute(
            f"SELECT source, COUNT(*) FROM {TABLE} GROUP BY source"
        ).fetchall()
        return {
            "exists": True,
            "total": total,
            "categories": cats,
            "sources": {s: c for s, c in sources},
            "db_path": str(DB_PATH),
        }
    finally:
        conn.close()


def is_db_ready() -> bool:
    """检查翻译数据是否可用。"""
    if not DB_PATH.exists():
        return False
    try:
        conn = _get_connection()
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


# ============================================================
# 提供 game_terms.py 兼容的翻译接口
# ============================================================
def translate_term(en_text: str, term_type: str = "auto") -> str:
    """通用的游戏术语翻译接口。

    优先使用数据库翻译，数据库未命中时回退到 game_terms.py 硬编码映射。

    Args:
        en_text: 英文术语
        term_type: 术语类型 (planet/mission/rarity/enemy/source/auto)

    Returns:
        中文翻译，未找到返回原文本
    """
    if not en_text:
        return en_text

    # 先尝试数据库
    if is_db_ready():
        zh = translate_by_en(en_text)
        if zh:
            return zh

    # 回退到 game_terms 硬编码
    from data.game_terms import (
        PLANET_CN,
        GAMEMODE_CN,
        RARITY_CN,
        ENEMY_CN,
        SOURCE_TYPE_CN,
        BOUNTY_CN,
    )

    if term_type in ("planet", "auto"):
        if en_text in PLANET_CN:
            return PLANET_CN[en_text]
    if term_type in ("mission", "auto"):
        if en_text in GAMEMODE_CN:
            return GAMEMODE_CN[en_text]
    if term_type in ("rarity", "auto"):
        if en_text in RARITY_CN:
            return RARITY_CN[en_text]
    if term_type in ("enemy", "auto"):
        if en_text in ENEMY_CN:
            return ENEMY_CN[en_text]
    if term_type in ("source", "auto"):
        if en_text in SOURCE_TYPE_CN:
            return SOURCE_TYPE_CN[en_text]
        if en_text in BOUNTY_CN:
            return BOUNTY_CN[en_text]

    return en_text


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ("--stats", "-s"):
            stats = get_stats()
            if stats["exists"]:
                print(f"数据库: {stats['db_path']}")
                print(f"  总记录数: {stats['total']:,}")
                print(f"  分类数:   {stats['categories']}")
                print(f"  来源:")
                for src, cnt in stats["sources"].items():
                    print(f"    {src}: {cnt:,}")
            else:
                print("翻译数据不存在")
        elif cmd in ("--search", "-q") and len(sys.argv) > 2:
            for r in search_zh(sys.argv[2]):
                print(f"  [{r['category']}] {r['en']} -> {r['zh']}")
        elif cmd in ("--translate", "-t") and len(sys.argv) > 2:
            zh = translate_by_en(sys.argv[2])
            print(f"  {sys.argv[2]} -> {zh}" if zh else f"  未找到: {sys.argv[2]}")
        elif cmd in ("--categories", "-c"):
            for c in get_categories():
                print(f"  {c}")
        else:
            print("用法:")
            print("  python translator.py --stats           查看翻译数据统计")
            print("  python translator.py --search <词>      搜索翻译")
            print("  python translator.py --translate <英文>  翻译英文术语")
            print("  python translator.py --categories       查看分类")
    else:
        ready = is_db_ready()
        print(f"[translator] 翻译数据: {'可用' if ready else '不可用'}")
