"""
游戏术语中英对照数据库构建模块。

数据来源:
  1. warframe-public-export-plus (calamity-inc) — 基于 DE 官方 Public Export，持续更新
     - dict.en.json: 英文翻译
     - dict.zh.json: 中文翻译
  2. WFCD/warframe-items — 现有 i18n.json（作为交叉验证）

数据库: data/game_i18n.db
  - translations 表: key(唯一标识), en(英文), zh(中文), category(分类), source(来源), verified(校验状态)
"""

import json
import sqlite3
import time
import urllib.request
import urllib.error
from pathlib import Path

# ============================================================
# 镜像支持
# ============================================================
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from core.hotkey_config import resolve_github_url, load_github_mirror
    _HAS_MIRROR = True
except ImportError:
    _HAS_MIRROR = False

# ============================================================
# 配置
# ============================================================
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/calamity-inc/warframe-public-export-plus/senpai"
DICT_EN_URL = f"{GITHUB_RAW_BASE}/dict.en.json"
DICT_ZH_URL = f"{GITHUB_RAW_BASE}/dict.zh.json"

# @wfcd/items i18n.json — 第三数据源（物品多语言翻译，无英文字段）
WFCD_ITEMS_I18N_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/HEAD/data/json/i18n.json"

# 本地文件路径
DATA_DIR = Path(__file__).resolve().parent  # data/
DB_PATH = DATA_DIR / "game_i18n.db"
I18N_JSON_PATH = DATA_DIR / "i18n.json"


# ============================================================
# 数据库操作
# ============================================================
def _get_connection() -> sqlite3.Connection:
    """获取数据库连接，自动创建表结构。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            key       TEXT PRIMARY KEY,
            en        TEXT NOT NULL,
            zh        TEXT NOT NULL,
            category  TEXT DEFAULT '',
            source    TEXT DEFAULT 'public-export-plus',
            verified  INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_category ON translations(category)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_source ON translations(source)
    """)
    conn.commit()
    return conn


def _extract_category(key: str) -> str:
    """从 key 路径中提取分类名。

    例: /Lotus/Language/Missions/MissionName_Crossfire → Missions
        /Lotus/Language/Items/BlueprintAndItem → Items
        /Lotus/Language/Relics/VoidProjectionName → Relics
    """
    parts = key.split("/")
    if len(parts) >= 4 and parts[1] == "Lotus" and parts[2] == "Language":
        return parts[3] if len(parts) > 3 else ""
    # 兼容其他格式
    if len(parts) >= 3:
        return parts[2] if parts[2] else parts[1]
    return ""


# ============================================================
# 下载与解析
# ============================================================
def _download_json(url: str, timeout: int = 120, mirror: str = None) -> dict:
    """下载 JSON 文件并解析为 dict。

    Args:
        url: 原始 URL
        timeout: 超时时间（秒）
        mirror: 镜像地址（可选，为空时使用配置的镜像）

    Returns:
        解析后的 JSON dict

    Raises:
        urllib.error.URLError: 网络错误
        json.JSONDecodeError: 解析错误
    """
    if _HAS_MIRROR:
        if mirror is None:
            mirror = load_github_mirror()
        url = resolve_github_url(url, mirror)
    req = urllib.request.Request(url, headers={"User-Agent": "WarframeRelicTool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _load_json_file(filename: str) -> dict:
    """从 data 目录加载本地 JSON 文件。

    Args:
        filename: 文件名，如 "dict.en.json"

    Returns:
        解析后的 JSON dict

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: 解析错误
    """
    file_path = DATA_DIR / filename
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_wfcd_value(value) -> str:
    """将 WFCD i18n 值标准化为字符串。

    WFCD i18n.json 中有两种格式:
      - {"zh": "中文文本"}  → 直接取字符串
      - {"zh": {"name": "名称", "description": "描述"}}  → 取 name
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name", "") or value.get("description", "") or ""
    return str(value)


def _load_existing_i18n() -> dict[str, dict[str, str]]:
    """加载本地已有的 i18n.json（WFCD 来源）。"""
    if not I18N_JSON_PATH.exists():
        return {}
    with open(I18N_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _derive_en_from_key(key: str) -> str:
    """从 WFCD key 路径推断英文名称。

    例: /Lotus/Types/Keys/ArchwingQuest/ArchwingQuestKeyChain -> Archwing Quest
         /Lotus/Weapons/Grineer/GrineerPistol -> Grineer Pistol
    """
    import re
    # 取最后一个路径段
    last = key.rstrip("/").rsplit("/", 1)[-1] if "/" in key else key
    # 去掉常见后缀
    for suffix in ("KeyChain", "KeyChainItem", "Item", "Blueprint", "Avatar"):
        if last.endswith(suffix) and len(last) > len(suffix):
            last = last[:-len(suffix)]
            break
    # 去掉末尾的 Key 后缀
    if last.endswith("Key") and len(last) > 3:
        last = last[:-3]
    # 去掉末尾的 Quest 后缀（保留前面的部分）
    if last.endswith("Quest") and len(last) > 5:
        last = last[:-5]
    # 去掉末尾的 Mod 后缀
    if last.endswith("Mod") and len(last) > 3:
        last = last[:-3]
    # 去掉末尾的 Rifle/Pistol/Shotgun 等武器类型后缀
    for weapon_suffix in ("Rifle", "Pistol", "Shotgun", "Melee", "Bow", "Sniper"):
        if last.endswith(weapon_suffix) and len(last) > len(weapon_suffix):
            last = last[:-len(weapon_suffix)]
            break
    # 数字+字母之间插入空格
    result = re.sub(r"(\d)([A-Za-z])", r"\1 \2", last)
    result = re.sub(r"([A-Za-z])(\d)", r"\1 \2", result)
    # 驼峰转空格
    result = re.sub(r"([a-z])([A-Z])", r"\1 \2", result)
    result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", result)
    return result.strip()


def build_database(
    progress_callback=None,
    log_callback=None,
    mirror: str = None,
    use_local_files: bool = False,
) -> dict:
    """下载数据并构建中英对照数据库。

    Args:
        progress_callback: callable(stage, current, total) — 进度回调
        log_callback: callable(level, message) — 日志回调
        use_local_files: bool — 是否直接使用本地已有的 dict.en.json 和 dict.zh.json（跳过下载

    Returns:
        dict: {"total": int, "en_only": int, "zh_only": int, "both": int, "conflicts": int,
               "wfcd_merged": int, "wfcd_new": int,
               "wfcd_items_merged": int, "wfcd_items_new": int}
    """
    def _log(level, msg):
        if log_callback:
            log_callback(level, msg)

    def _progress(stage, cur, total):
        if progress_callback:
            progress_callback(stage, cur, total)

    _log("info", "=" * 50)
    _log("info", "开始构建中英对照翻译数据库")
    _log("info", "=" * 50)

    # ---- 阶段 1: 获取 dict.en.json ----
    if use_local_files:
        _log("info", "[1/6] 加载本地英文翻译文件 (dict.en.json)...")
        _progress("加载英文", 0, 100)
        try:
            en_dict = _load_json_file("dict.en.json")
            _progress("加载英文", 100, 100)
            _log("ok", f"英文翻译: {len(en_dict):,} 条记录")
        except Exception as e:
            _log("error", f"加载英文翻译失败: {e}")
            return {"total": 0, "error": str(e)}
    else:
        _log("info", "[1/6] 下载英文翻译文件 (dict.en.json)...")
        _progress("下载英文", 0, 100)
        try:
            en_dict = _download_json(DICT_EN_URL, mirror=mirror)
            _progress("下载英文", 100, 100)
            _log("ok", f"英文翻译: {len(en_dict):,} 条记录")
        except Exception as e:
            _log("error", f"下载英文翻译失败: {e}")
            return {"total": 0, "error": str(e)}

    # ---- 阶段 2: 获取 dict.zh.json ----
    if use_local_files:
        _log("info", "[2/6] 加载本地中文翻译文件 (dict.zh.json)...")
        _progress("加载中文", 0, 100)
        try:
            zh_dict = _load_json_file("dict.zh.json")
            _progress("加载中文", 100, 100)
            _log("ok", f"中文翻译: {len(zh_dict):,} 条记录")
        except Exception as e:
            _log("error", f"加载中文翻译失败: {e}")
            return {"total": 0, "error": str(e)}
    else:
        _log("info", "[2/6] 下载中文翻译文件 (dict.zh.json)...")
        _progress("下载中文", 0, 100)
        try:
            zh_dict = _download_json(DICT_ZH_URL, mirror=mirror)
            _progress("下载中文", 100, 100)
            _log("ok", f"中文翻译: {len(zh_dict):,} 条记录")
        except Exception as e:
            _log("error", f"下载中文翻译失败: {e}")
            return {"total": 0, "error": str(e)}

    # ---- 阶段 3: 合并 en/zh 数据 ----
    _log("info", "[3/6] 合并英文/中文翻译数据...")
    _progress("合并数据", 0, 100)

    all_keys = set(en_dict.keys()) | set(zh_dict.keys())
    en_only = 0
    zh_only = 0
    both = 0

    merged = {}
    for key in all_keys:
        en_val = en_dict.get(key, "")
        zh_val = zh_dict.get(key, "")
        if en_val and zh_val:
            both += 1
        elif en_val and not zh_val:
            en_only += 1
        elif zh_val and not en_val:
            zh_only += 1
        merged[key] = {"en": en_val, "zh": zh_val, "source": "public-export-plus"}

    _progress("合并数据", 100, 100)
    _log("ok", f"合并结果: {len(merged):,} 条 (中英皆有: {both:,}, 仅英文: {en_only:,}, 仅中文: {zh_only:,})")

    # ---- 阶段 4: 交叉验证 WFCD i18n.json (drop-data) ----
    _log("info", "[4/6] 交叉验证 WFCD i18n.json 数据...")
    _progress("交叉验证", 0, 100)
    wfcd_i18n = _load_existing_i18n()
    wfcd_merged = 0
    wfcd_new = 0
    conflicts = 0

    if wfcd_i18n:
        # 构建反向索引: zh -> en (用于 WFCD-only key 反向查找英文)
        _log("info", "  构建反向索引...")
        reverse_index = {}
        for k, en_val in en_dict.items():
            if k in zh_dict and zh_dict[k] and en_val:
                reverse_index[zh_dict[k]] = en_val
        _log("ok", f"  反向索引: {len(reverse_index):,} 条")

        skipped_non_language = 0
        for key, langs in wfcd_i18n.items():
            # 🔴 关键修复: 只处理 /Lotus/Language/ 开头的翻译 key！
            if not key.startswith("/Lotus/Language/"):
                skipped_non_language += 1
                continue
                
            if key in merged:
                # 补充缺失的翻译
                updated = False
                # WFCD i18n 格式: {"zh": "中文"} 或 {"zh": {"name": "名称", ...}}
                en_from_wfcd = _normalize_wfcd_value(langs.get("en", "")) if isinstance(langs, dict) else ""
                zh_from_wfcd = _normalize_wfcd_value(langs.get("zh", "")) if isinstance(langs, dict) else ""
                if not merged[key]["en"] and en_from_wfcd:
                    merged[key]["en"] = en_from_wfcd
                    updated = True
                if not merged[key]["zh"] and zh_from_wfcd:
                    merged[key]["zh"] = zh_from_wfcd
                    updated = True
                if updated:
                    merged[key]["source"] += ",wfcd-i18n"
                    wfcd_merged += 1
            else:
                # WFCD 独有的 key，直接加入
                en_from_wfcd = _normalize_wfcd_value(langs.get("en", "")) if isinstance(langs, dict) else ""
                zh_from_wfcd = _normalize_wfcd_value(langs.get("zh", "")) if isinstance(langs, dict) else ""
                # 如果 WFCD 没有英文，尝试多种方式补充
                if not en_from_wfcd and zh_from_wfcd:
                    # 1) 直接查找: WFCD key 是否存在于 public-export-plus dict
                    en_from_wfcd = en_dict.get(key, "")
                if not en_from_wfcd and zh_from_wfcd:
                    # 2) 反向索引: 用中文名查找英文
                    en_from_wfcd = reverse_index.get(zh_from_wfcd, "")
                if not en_from_wfcd:
                    # 3) 从 key 路径推断: 取最后一个路径段, 去掉后缀
                    en_from_wfcd = _derive_en_from_key(key)
                merged[key] = {
                    "en": en_from_wfcd,
                    "zh": zh_from_wfcd,
                    "source": "wfcd-i18n",
                }
                wfcd_new += 1
        
        _log("info", f"  过滤掉非翻译 key: {skipped_non_language:,} 条")

    _progress("交叉验证", 100, 100)
    _log("ok", f"WFCD 交叉验证: 补充 {wfcd_merged:,} 条, 新增 {wfcd_new:,} 条")

    # ---- 阶段 5: 交叉验证 @wfcd/items i18n.json (物品多语言) ----
    wfcd_items_merged = 0
    wfcd_items_new = 0
    if not use_local_files:
        # 仅在在线模式下下载 @wfcd/items i18n.json
        _log("info", "[5/6] 交叉验证 @wfcd/items i18n.json 数据...")
        _progress("@wfcd/items", 0, 100)

        try:
            wfcd_items_i18n = _download_json(WFCD_ITEMS_I18N_URL, timeout=180)
            _progress("@wfcd/items", 50, 100)
            _log("ok", f"@wfcd/items i18n.json: {len(wfcd_items_i18n):,} 条记录")

            items_skipped = 0
            for key, langs in wfcd_items_i18n.items():
                # 同样只处理 /Lotus/Language/ 开头的翻译 key！
                if not key.startswith("/Lotus/Language/"):
                    items_skipped += 1
                    continue
                    
                if not isinstance(langs, dict):
                    continue
                # @wfcd/items 格式: {"zh": {"name": "...", "description": "..."}, "de": {...}, ...}
                # 注意: 此数据源没有 en 字段
                zh_from_items = _normalize_wfcd_value(langs.get("zh", "")) if isinstance(langs.get("zh", ""), dict) else ""

                if key in merged:
                    if not merged[key]["zh"] and zh_from_items:
                        merged[key]["zh"] = zh_from_items
                        merged[key]["source"] += ",wfcd-items"
                        wfcd_items_merged += 1
                else:
                    # 新 key: 从 key 路径推断英文，使用 items 的中文翻译
                    en_from_items = _derive_en_from_key(key)
                    merged[key] = {
                        "en": en_from_items,
                        "zh": zh_from_items,
                        "source": "wfcd-items",
                    }
                    wfcd_items_new += 1
            
            _log("info", f"  @wfcd/items 过滤掉非翻译 key: {items_skipped:,} 条")

            _progress("@wfcd/items", 100, 100)
            _log("ok", f"@wfcd/items 交叉验证: 补充 {wfcd_items_merged:,} 条, 新增 {wfcd_items_new:,} 条")
        except Exception as e:
            _log("warn", f"@wfcd/items i18n.json 下载失败 (非致命): {e}")
            wfcd_items_merged = 0
            wfcd_items_new = 0
    else:
        # 本地模式：跳过 @wfcd/items 下载，直接进入下一阶段
        _log("info", "[5/6] 跳过 @wfcd/items 交叉验证 (本地模式)")
        _progress("@wfcd/items", 100, 100)

    # ---- 阶段 6: 写入数据库 ----
    _log("info", "[6/6] 写入数据库...")
    _progress("写入数据库", 0, 100)

    conn = _get_connection()
    conn.execute("DELETE FROM translations")  # 清空旧数据

    batch_size = 5000
    rows = []
    total = len(merged)
    written = 0

    for key, data in merged.items():
        category = _extract_category(key)
        rows.append((
            key,
            data["en"],
            data["zh"],
            category,
            data["source"],
            0,  # verified
        ))

        if len(rows) >= batch_size:
            conn.executemany(
                "INSERT INTO translations (key, en, zh, category, source, verified) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            written += len(rows)
            rows.clear()
            _progress("写入数据库", int(written / total * 100), 100)

    # 写入剩余批次
    if rows:
        conn.executemany(
            "INSERT INTO translations (key, en, zh, category, source, verified) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        written += len(rows)

    conn.commit()
    conn.close()

    _progress("写入数据库", 100, 100)
    _log("ok", f"数据库写入完成: {written:,} 条记录 → {DB_PATH.name}")

    # 统计分类
    _log("info", "-" * 50)
    _log("info", "分类统计 (Top 10):")
    conn = _get_connection()
    cats = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM translations GROUP BY category ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    for cat, cnt in cats:
        _log("info", f"  {cat}: {cnt:,} 条")
    conn.close()

    stats = {
        "total": total,
        "en_only": en_only,
        "zh_only": zh_only,
        "both": both,
        "conflicts": conflicts,
        "wfcd_merged": wfcd_merged,
        "wfcd_new": wfcd_new,
        "wfcd_items_merged": wfcd_items_merged,
        "wfcd_items_new": wfcd_items_new,
    }
    _log("ok", f"构建完成! 总计 {total:,} 条翻译记录")
    return stats


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
            f"SELECT {lang} FROM translations WHERE key = ?", (key,)
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
            "SELECT zh FROM translations WHERE en = ? LIMIT 1", (en_text,)
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
            "SELECT key, en, zh, category FROM translations "
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
            "SELECT DISTINCT category FROM translations ORDER BY category"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_stats() -> dict:
    """获取数据库统计信息。"""
    if not DB_PATH.exists():
        return {"exists": False}
    conn = _get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        cats = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM translations"
        ).fetchone()[0]
        sources = conn.execute(
            "SELECT source, COUNT(*) FROM translations GROUP BY source"
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


# ============================================================
# PyQt6 Worker（后台线程）
# ============================================================

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False


if _HAS_PYQT:

    class GameI18nBuildWorker(QObject):
        """后台线程：构建中英对照翻译数据库。

        信号:
            step_changed(int, str): 步骤变化 (步骤号, 描述)
            log(str, str): 日志消息 (level, msg)
            progress_pct(int): 进度百分比
            progress_detail(str, int, int): 进度详情 (stage, current, total)
            finished(dict): 完成 (结果统计)
            error(str): 错误
        """

        step_changed = pyqtSignal(int, str)
        log = pyqtSignal(str, str)
        progress_pct = pyqtSignal(int)
        progress_detail = pyqtSignal(str, int, int)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, use_local_files: bool = False):
            super().__init__()
            self._cancelled = False
            self._use_local_files = use_local_files

        def cancel(self):
            self._cancelled = True

        def run(self):
            def _log(level, msg):
                if not self._cancelled:
                    self.log.emit(level, msg)

            def _progress(stage, cur, total):
                if not self._cancelled:
                    self.progress_detail.emit(stage, cur, total)
                    if total > 0:
                        self.progress_pct.emit(int(cur * 100 / total))

            try:
                if self._use_local_files:
                    self.step_changed.emit(1, '从本地文件构建中英对照翻译数据库')
                else:
                    self.step_changed.emit(1, '下载并构建中英对照翻译数据库')
                self.progress_pct.emit(0)

                result = build_database(
                    progress_callback=_progress,
                    log_callback=_log,
                    use_local_files=self._use_local_files,
                )

                if self._cancelled:
                    return

                self.step_changed.emit(2, '完成')
                self.progress_pct.emit(100)
                self.finished.emit(result)

            except Exception as e:
                _log('error', f'翻译数据库构建失败: {e}')
                self.error.emit(str(e))


def is_db_ready() -> bool:
    """检查数据库是否已构建。"""
    return DB_PATH.exists() and DB_PATH.stat().st_size > 0


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
    import argparse

    def _cli_log(level, msg):
        prefix = {"ok": "  [OK]", "warn": "[WARN]", "error": "[ERR]", "info": " [INFO]"}
        print(f"{prefix.get(level, '     ')} {msg}")

    def _cli_progress(stage, cur, total):
        bar_len = 30
        filled = int(bar_len * cur / max(total, 1))
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r  [{stage}] [{bar}] {cur}/{total}", end="", flush=True)
        if cur >= total:
            print()

    parser = argparse.ArgumentParser(description="Warframe 中英对照翻译数据库构建工具")
    parser.add_argument("--local", action="store_true", help="使用本地 data 目录下的 dict.en.json 和 dict.zh.json 文件")

    args = parser.parse_args()

    print("Warframe 中英对照翻译数据库构建工具")
    if args.local:
        print("模式: 本地文件模式")
        print("数据源: data/dict.en.json, data/dict.zh.json")
    else:
        print("模式: 在线下载模式")
        print(f"数据源: {GITHUB_RAW_BASE}")
    print(f"目标库: {DB_PATH}")
    print()

    stats = build_database(
        progress_callback=_cli_progress,
        log_callback=_cli_log,
        use_local_files=args.local,
    )

    if "error" in stats:
        print(f"\n构建失败: {stats['error']}")
        sys.exit(1)

    print("\n构建完成!")
    print(f"  总记录数: {stats['total']:,}")
    print(f"  中英皆有: {stats['both']:,}")
    print(f"  仅英文:   {stats['en_only']:,}")
    print(f"  仅中文:   {stats['zh_only']:,}")
    print(f"  WFCD 补充: {stats['wfcd_merged']:,}")
    print(f"  WFCD 新增: {stats['wfcd_new']:,}")
    if "wfcd_items_merged" in stats and "wfcd_items_new" in stats:
        print(f"  物品补充: {stats['wfcd_items_merged']:,}")
        print(f"  物品新增: {stats['wfcd_items_new']:,}")