"""
中英文对照翻译数据库模块 (v2.0)

数据来源:
  - WFCD/warframe-items/All.json       → 物品英文名(name) + 唯一标识(uniqueName)
  - WFCD/warframe-items/i18n.json      → uniqueName → 中文名(zh.name)
  - 备用: AdminRoc/Warframe-Chinese-English-Bilingual (可交易物品)

关联方式: uniqueName 精确关联，不再依赖语言猜测

数据库表结构 (v2):
  translations: 中英对照核心表 (支持来源追踪)
  translation_meta: 数据库元信息

用法:
  python translation_db.py --build       从本地文件构建
  python translation_db.py --build-remote  从网络拉取并构建
"""

import json
import os
import sqlite3
import urllib.request
import re
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QObject

# ===== 路径 =====
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'translation.db')
DICT_PATH = os.path.join(BASE_DIR, 'zh_en_dict.json')
I18N_PATH = os.path.join(BASE_DIR, 'i18n.json')
ALL_ITEMS_PATH = os.path.join(BASE_DIR, 'all_items.json')  # warframe-items 的 All.json

# ===== 数据源 URL =====
WFCD_ALL_URL = 'https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json'
WFCD_I18N_URL = 'https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json'
ADMINROC_URL = 'https://raw.githubusercontent.com/AdminRoc/Warframe-Chinese-English-Bilingual/main/index.html'

SOURCE_NAMES = {
    'wfcd': 'WFCD warframe-items (官方API全物品)',
    'adminroc': 'AdminRoc (可交易物品中英对照)',
    'local': '本地文件 (All.json + i18n.json)',
}

# ===== 数据库表结构 (v2) =====
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zh_name TEXT NOT NULL,
    en_name TEXT NOT NULL,
    unique_name TEXT,                -- 游戏内部唯一标识 (如 /Lotus/Weapons/...)
    category TEXT,                   -- 物品分类
    source TEXT DEFAULT 'wfcd',      -- 数据来源: wfcd / adminroc
    item_type TEXT,                  -- 物品类型: Warframe/Primary/Secondary/Melee/Mod/Relic/...
    is_tradable INTEGER DEFAULT 0,   -- 是否可交易
    UNIQUE(zh_name, en_name)
);

CREATE INDEX IF NOT EXISTS idx_zh ON translations(zh_name);
CREATE INDEX IF NOT EXISTS idx_en ON translations(en_name);
CREATE INDEX IF NOT EXISTS idx_category ON translations(category);
CREATE INDEX IF NOT EXISTS idx_unique ON translations(unique_name);
CREATE INDEX IF NOT EXISTS idx_item_type ON translations(item_type);

-- 元信息表
CREATE TABLE IF NOT EXISTS translation_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# ===== 优化后的分类规则 =====
CATEGORY_RULES = [
    # 战甲及部件（精确匹配优先）
    ("战甲", [
        " Prime", "一套", " Set",
        "头盔", "Helmet", "系统", "Systems", "机体", "Chassis",
        "视光器", "Neuroptics",
        "蓝图", "Blueprint",
    ]),
    # 遗物
    ("核桃", [
        "遗物", "Relic", "古纪", "前纪", "中纪", "后纪",
    ]),
    # 武器 - 按类型细分
    ("主武器", [
        "步枪", "Rifle", "霰弹", "Shotgun", "狙击枪", "Sniper",
        "弓", "Bow", "发射器", "Launcher", "弩", "Crossbow",
        "射线", "Beam", "矛枪", "Speargun",
    ]),
    ("副武器", [
        "手枪", "Pistol", "双枪", "Dual", "投掷", "Thrown",
    ]),
    ("近战武器", [
        "剑", "Sword", "刀", "锤", "Hammer", "斧", "Axe",
        "鞭", "Whip", "棍", "Staff", "镰", "Scythe",
        "爪", "Claw", "拳", "Fist", "匕首", "Dagger",
        "长柄", "Polearm", "巨刃", "Heavy", "双剑", "Dual Sword",
        "战刃", "Glaive", "镰刀", "枪刃", "Gunblade",
        "细剑", "Rapier", "扇", "Fan", "搏击", "Sparring",
        "侍刃", "Nikana", "钩", "Hook",
    ]),
    # 武器部件（独立于成品武器）
    ("武器部件", [
        "枪机", "Receiver", "枪管", "Barrel", "枪托", "Stock",
        "刀刃", "Blade", "握柄", "Handle", "连接器", "Link",
        "上部", "Upper", "下部", "Lower", "蓝图", "Blueprint",
    ]),
    # Mod
    ("Mod", [
        " Prime Mod", "赋能", "Arcane", "Mod", "弹头",
        "Prime Chamber", "振幅晶体",
    ]),
    # 外观
    ("外观", [
        "外观", "皮肤", "Skin", "披饰", "Syandana", "护甲", "Armor",
        "头盔", "装饰", "饰品", "纹章", "Sigil", "浮印", "Glyph",
    ]),
    # 同伴
    ("同伴", [
        "守护", "Sentinel", "库娃", "Kavat", "库狛", "Kubrow",
        "狐帕菲拉", "Vulpaphyla", "铁甲", "Predasite",
        "赫利俄斯", "Helios", "搬运者", "Carrier", "死亡魔方", "Deathcube",
        "阴影", "Shade", "引灵", "Wyrm", "电气浮囊", "Diriga",
    ]),
    # Archwing
    ("Archwing", [
        "Odonata", "Elytron", "Amesha", "Itzal", "Archwing",
        "Arch-Gun", "Arch-Melee",
    ]),
    # 飞船
    ("飞船", [
        "飞船", "Liset", "Mantis", "Scimitar", "Xiphos", "登陆艇",
        "航道星舰", "Railjack",
    ]),
    # 道具
    ("道具", [
        "钥匙", "Key", "Forma", "福马", "Orokin", "催化剂", "Catalyst",
        "反应堆", "Reactor", "Exilus", "连接器", "Adapter",
        "雕像", "塑像", "星币", "Credits", "内融核心", "Endo",
    ]),
    # 紫卡
    ("紫卡", [
        "紫卡", "Riven",
    ]),
]


def classify_item(zh_name: str, en_name: str) -> str:
    """根据中英文名称推断物品类别（优化版：优先长关键词匹配）。"""
    combined = f"{zh_name} {en_name}"
    best_match = None
    best_len = 0

    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in combined.lower():
                if len(kw) > best_len:
                    best_match = category
                    best_len = len(kw)

    return best_match or "其他"


# ============================================================
# 核心：从 All.json + i18n.json 提取精确中英对照
# ============================================================

def extract_pairs_from_wfcd(all_items_path: str = None,
                            i18n_path: str = None) -> list[tuple]:
    """从 WFCD warframe-items 数据文件中提取精确中英对照。

    Args:
        all_items_path: All.json 路径，None 使用默认
        i18n_path: i18n.json 路径，None 使用默认

    Returns:
        [(zh_name, en_name, unique_name, item_type, is_tradable), ...]
    """
    all_path = all_items_path or ALL_ITEMS_PATH
    i18n_path = i18n_path or I18N_PATH

    # 1. 加载 All.json → {uniqueName: {name, category, tradable, ...}}
    print(f"  加载 All.json: {all_path}")
    if not os.path.exists(all_path):
        raise FileNotFoundError(f"All.json 不存在: {all_path}")

    with open(all_path, 'r', encoding='utf-8') as f:
        all_data = json.load(f)

    if not isinstance(all_data, list):
        raise ValueError(f"All.json 应为数组，实际为 {type(all_data).__name__}")

    print(f"    All.json 包含 {len(all_data)} 个物品")

    # 构建 uniqueName → item info 映射
    item_map = {}
    for item in all_data:
        un = item.get('uniqueName', '')
        if un:
            item_map[un] = {
                'name': item.get('name', ''),
                'category': item.get('category', ''),
                'type': item.get('type', ''),
                'tradable': item.get('tradable', False),
            }

    print(f"    有效 uniqueName: {len(item_map)}")

    # 2. 加载 i18n.json → {uniqueName: {zh: {name: ...}}}
    print(f"  加载 i18n.json: {i18n_path}")
    if not os.path.exists(i18n_path):
        raise FileNotFoundError(f"i18n.json 不存在: {i18n_path}")

    with open(i18n_path, 'r', encoding='utf-8') as f:
        i18n_data = json.load(f)

    print(f"    i18n.json 包含 {len(i18n_data)} 条翻译")

    # 3. 通过 uniqueName 关联
    pairs = []
    matched = 0
    unmatched = 0
    no_zh = 0

    for unique_name, i18n_val in i18n_data.items():
        if not isinstance(i18n_val, dict):
            continue

        # 获取中文名
        zh_val = i18n_val.get('zh', '')
        if isinstance(zh_val, dict):
            zh_name = zh_val.get('name', '').strip()
        elif isinstance(zh_val, str):
            zh_name = zh_val.strip()
        else:
            no_zh += 1
            continue

        if not zh_name:
            no_zh += 1
            continue

        # 从 item_map 获取英文名和元信息
        item_info = item_map.get(unique_name)
        if item_info and item_info['name']:
            en_name = item_info['name'].strip()
            if zh_name != en_name:  # 跳过完全相同的（未翻译的）
                pairs.append((
                    zh_name,
                    en_name,
                    unique_name,
                    item_info.get('category', ''),
                    item_info.get('tradable', False),
                ))
                matched += 1
        else:
            unmatched += 1

    print(f"    匹配成功: {matched}, 无物品信息: {unmatched}, 无中文: {no_zh}")

    # 去重
    seen = set()
    unique = []
    for p in pairs:
        k = (p[0].lower(), p[1].lower())
        if k not in seen:
            seen.add(k)
            unique.append(p)

    print(f"    去重后: {len(unique)} 条")
    return unique


def extract_pairs_from_adminroc() -> list[tuple]:
    """从 AdminRoc 主源提取中英对照（兼容旧格式）。"""
    print("  从 AdminRoc 拉取中英文对照数据...")
    resp = urllib.request.urlopen(ADMINROC_URL, timeout=30)
    html = resp.read().decode('utf-8')

    zh_match = re.search(r'<script\s+id="data-zh"[^>]*>(.*?)</script>', html, re.DOTALL)
    en_match = re.search(r'<script\s+id="data-en"[^>]*>(.*?)</script>', html, re.DOTALL)

    if not zh_match or not en_match:
        raise ValueError("无法从 HTML 中提取数据标签")

    zh_lines = [l.strip() for l in zh_match.group(1).strip().split('\n') if l.strip()]
    en_lines = [l.strip() for l in en_match.group(1).strip().split('\n') if l.strip()]

    print(f"  获取到 {len(zh_lines)} 条中文, {len(en_lines)} 条英文")

    # 转为统一格式 (zh, en, None, '', False)
    return [(zh, en, None, '', False) for zh, en in zip(zh_lines, en_lines)]


# ============================================================
# 构建数据库
# ============================================================

def build_translation_db(source: str = 'local',
                         all_items_path: str = None,
                         i18n_path: str = None,
                         merge_adminroc: bool = True) -> dict:
    """构建/重建翻译数据库。

    Args:
        source: 'local' | 'wfcd' | 'adminroc'
        all_items_path: All.json 路径（仅 wfcd）
        i18n_path: i18n.json 路径（仅 wfcd）
        merge_adminroc: 是否合并 AdminRoc 数据补充部件翻译

    Returns:
        dict: {'total': int, 'categories': dict, 'source': str}
    """
    start_time = time.time()

    # 自动检测
    if source == 'local':
        if os.path.exists(ALL_ITEMS_PATH) and os.path.exists(I18N_PATH):
            source = 'wfcd'
        else:
            source = 'adminroc'

    # 提取主数据
    if source == 'wfcd':
        all_path = all_items_path or ALL_ITEMS_PATH
        i18n_path = i18n_path or I18N_PATH
        print(f"数据源: WFCD warframe-items")
        print(f"  All.json: {all_path}")
        print(f"  i18n.json: {i18n_path}")
        raw_pairs = extract_pairs_from_wfcd(all_path, i18n_path)
    else:
        print(f"数据源: AdminRoc")
        raw_pairs = extract_pairs_from_adminroc()
        merge_adminroc = False  # AdminRoc 本身就是主源，不需要再合并

    if not raw_pairs:
        raise ValueError("未能提取到任何中英对照数据")

    # 合并 AdminRoc 补充数据
    adminroc_pairs = []
    if merge_adminroc:
        try:
            adminroc_pairs = extract_pairs_from_adminroc()
            print(f"  AdminRoc 补充: {len(adminroc_pairs)} 条")
        except Exception as e:
            print(f"  AdminRoc 合并失败（将仅使用 WFCD 数据）: {e}")

    # 合并去重
    seen = set()
    merged = []
    for p in raw_pairs:
        k = (p[0].lower(), p[1].lower())
        if k not in seen:
            seen.add(k)
            merged.append(p)

    adminroc_new = 0
    for p in adminroc_pairs:
        k = (p[0].lower(), p[1].lower())
        if k not in seen:
            seen.add(k)
            merged.append(p)
            adminroc_new += 1

    print(f"  合并后总计: {len(merged)} 条 (AdminRoc 新增 {adminroc_new})")

    # 写入数据库
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_V2)
    conn.execute("DELETE FROM translations")

    cur = conn.cursor()
    inserted = 0
    categories_count = {}
    source_label = 'wfcd+adminroc' if merge_adminroc else source

    for item in merged:
        # 统一解包（兼容 5 或 6 元素 tuple）
        zh_name = item[0]
        en_name = item[1]
        unique_name = item[2] if len(item) > 2 else None
        item_type = item[3] if len(item) > 3 else ''
        is_tradable = item[4] if len(item) > 4 else False
        src = item[5] if len(item) > 5 else source

        if not zh_name or not en_name:
            continue

        category = classify_item(zh_name, en_name)
        categories_count[category] = categories_count.get(category, 0) + 1

        try:
            cur.execute(
                """INSERT INTO translations
                   (zh_name, en_name, unique_name, category, source, item_type, is_tradable)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (zh_name, en_name, unique_name, category, src, item_type, int(is_tradable))
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass

    # 写入元信息
    conn.execute(
        "INSERT OR REPLACE INTO translation_meta (key, value) VALUES (?, ?)",
        ('source', source_label))
    conn.execute(
        "INSERT OR REPLACE INTO translation_meta (key, value) VALUES (?, ?)",
        ('total', str(inserted)))
    conn.execute(
        "INSERT OR REPLACE INTO translation_meta (key, value) VALUES (?, ?)",
        ('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()
    conn.close()

    # 缓存 JSON（兼容旧格式）
    simple_pairs = [(zh, en) for zh, en, *_ in merged]
    os.makedirs(os.path.dirname(DICT_PATH), exist_ok=True)
    with open(DICT_PATH, 'w', encoding='utf-8') as f:
        json.dump(simple_pairs, f, ensure_ascii=False, indent=2)

    # 自动跟随更新全物品数据库
    _auto_build_items_db()

    result = {
        'total': inserted,
        'categories': dict(sorted(categories_count.items())),
        'source': SOURCE_NAMES.get(source, source_label),
    }

    elapsed = time.time() - start_time
    print(f"\n翻译数据库构建完成 (耗时 {elapsed:.1f}s)")
    print(f"  总计: {inserted} 条")
    print(f"  数据源: {result['source']}")
    print(f"  分类统计:")
    for cat, count in sorted(categories_count.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count} 条")

    return result


def _auto_build_items_db():
    """自动跟随重建全物品数据库（静默模式，失败不影响主流程）。"""
    try:
        from .items_i18n import auto_rebuild_items_db
        auto_rebuild_items_db(silent=True)
    except Exception:
        pass  # 静默忽略，不影响翻译库构建


# ============================================================
# 查询 API（兼容旧接口）
# ============================================================

def search_cn(query: str, limit: int = 20) -> list[dict]:
    """中文模糊搜索 → 返回英文"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM translations WHERE zh_name LIKE ? ORDER BY zh_name LIMIT ?",
        (f"%{query}%", limit)
    )
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def search_en(query: str, limit: int = 20) -> list[dict]:
    """英文模糊搜索 → 返回中文"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM translations WHERE en_name LIKE ? ORDER BY en_name LIMIT ?",
        (f"%{query}%", limit)
    )
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def translate_cn_to_en(cn: str) -> Optional[str]:
    """精确中文 → 英文"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT en_name FROM translations WHERE zh_name = ? LIMIT 1", (cn,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def translate_en_to_cn(en: str) -> Optional[str]:
    """精确英文 → 中文"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT zh_name FROM translations WHERE en_name = ? LIMIT 1", (en,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_translation_db_stats() -> dict:
    """获取翻译数据库统计信息。"""
    if not os.path.exists(DB_PATH):
        return {'exists': False, 'total': 0, 'categories': {}, 'db_size': 0, 'db_mtime': ''}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 兼容新旧表结构
        cols = [r[1] for r in cur.execute("PRAGMA table_info(translations)").fetchall()]

        total = cur.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        if 'category' in cols:
            cat_rows = cur.execute(
                "SELECT category, COUNT(*) FROM translations GROUP BY category ORDER BY COUNT(*) DESC"
            ).fetchall()
            categories = dict(cat_rows)
        else:
            categories = {}

        # 获取来源信息
        source = ''
        try:
            row = cur.execute("SELECT value FROM translation_meta WHERE key='source'").fetchone()
            if row:
                source = row[0]
        except Exception:
            pass

        conn.close()
        stat = os.stat(DB_PATH)
        return {
            'exists': True,
            'total': total,
            'categories': categories,
            'source': source,
            'db_size': stat.st_size,
            'db_mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception as e:
        return {'exists': False, 'error': str(e)}


# ============================================================
# 后台更新 Worker (v2)
# ============================================================

class TranslationUpdateWorker(QObject):
    """后台线程：拉取数据并重建翻译数据库。

    支持三种模式:
      - 'wfcd': 从 WFCD All.json + i18n.json 提取精确对照
      - 'adminroc': 从 AdminRoc HTML 提取可交易物品对照
      - 'local': 使用本地已有的 All.json + i18n.json

    自动回退: wfcd 失败 → adminroc
    """

    step_changed = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    progress_pct = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, source: str = 'local',
                 all_items_url: str = None,
                 i18n_url: str = None,
                 max_retries: int = 2):
        """
        Args:
            source: 'local' | 'wfcd' | 'adminroc'
            all_items_url: All.json 的 URL（仅 wfcd 模式）
            i18n_url: i18n.json 的 URL（仅 wfcd 模式）
            max_retries: 下载重试次数
        """
        super().__init__()
        self.source = source
        self.all_items_url = all_items_url or WFCD_ALL_URL
        self.i18n_url = i18n_url or WFCD_I18N_URL
        self.max_retries = max_retries
        self._tried_fallback = False

    def run(self):
        start_time = time.time()
        self.log.emit("info", f"数据源: {SOURCE_NAMES.get(self.source, self.source)}")

        if self.source in ('local', 'wfcd'):
            self._run_wfcd(start_time)
        elif self.source == 'adminroc':
            self._run_adminroc(start_time)
        else:
            self.error.emit(f"未知数据源: {self.source}")

    def _run_wfcd(self, start_time: float):
        """WFCD 模式：使用 All.json + i18n.json。"""
        # 如果是 local 模式，直接用本地文件
        if self.source == 'local':
            if not os.path.exists(ALL_ITEMS_PATH):
                self.log.emit("warn", "本地 all_items.json 不存在，切换为网络下载")
                self.source = 'wfcd'

        if self.source == 'wfcd':
            # 步骤 1-2: 下载 All.json
            self.step_changed.emit(1, "下载 All.json (物品数据)")
            try:
                all_data = self._download_file(self.all_items_url, "All.json")
            except ConnectionError as e:
                self._try_fallback(str(e), start_time)
                return

            # 步骤 3: 保存 All.json
            self.step_changed.emit(3, "保存 All.json")
            os.makedirs(os.path.dirname(ALL_ITEMS_PATH), exist_ok=True)
            with open(ALL_ITEMS_PATH, 'wb') as f:
                f.write(all_data)
            self.log.emit("ok", f"All.json 已保存: {ALL_ITEMS_PATH}")

            # 步骤 4: 检查本地 i18n.json
            if not os.path.exists(I18N_PATH):
                self.step_changed.emit(4, "下载 i18n.json (翻译数据)")
                try:
                    i18n_data = self._download_file(self.i18n_url, "i18n.json")
                except ConnectionError as e:
                    self._try_fallback(str(e), start_time)
                    return
                with open(I18N_PATH, 'wb') as f:
                    f.write(i18n_data)
                self.log.emit("ok", f"i18n.json 已保存: {I18N_PATH}")
            else:
                self.step_changed.emit(4, "使用本地 i18n.json")
                self.log.emit("info", f"使用本地 i18n.json: {I18N_PATH}")
        else:
            # local 模式，文件已存在
            self.step_changed.emit(1, "使用本地 All.json")
            self.log.emit("info", f"All.json: {ALL_ITEMS_PATH}")
            self.step_changed.emit(4, "使用本地 i18n.json")
            self.log.emit("info", f"i18n.json: {I18N_PATH}")

        # 步骤 5: 解析并关联
        self.step_changed.emit(5, "解析并关联中英对照数据")
        self.log.emit("info", "正在通过 uniqueName 精确关联中英文...")
        try:
            raw_pairs = extract_pairs_from_wfcd(ALL_ITEMS_PATH, I18N_PATH)
        except Exception as e:
            self.log.emit("error", f"数据解析失败: {e}")
            self._try_fallback(str(e), start_time)
            return

        if not raw_pairs:
            self.log.emit("error", "未能提取到任何中英对照数据")
            self._try_fallback("WFCD 数据源未提取到有效数据", start_time)
            return

        # 尝试合并 AdminRoc 补充部件翻译
        adminroc_pairs = []
        try:
            self.log.emit("info", "正在拉取 AdminRoc 补充部件翻译...")
            adminroc_pairs = extract_pairs_from_adminroc()
            self.log.emit("ok", f"AdminRoc 补充: {len(adminroc_pairs)} 条")
        except Exception as e:
            self.log.emit("warn", f"AdminRoc 补充失败（将仅使用 WFCD 数据）: {e}")

        # 合并去重
        seen = set()
        merged = []
        for p in raw_pairs:
            k = (p[0].lower(), p[1].lower())
            if k not in seen:
                seen.add(k)
                merged.append(p)

        adminroc_new = 0
        for p in adminroc_pairs:
            k = (p[0].lower(), p[1].lower())
            if k not in seen:
                seen.add(k)
                merged.append(p)
                adminroc_new += 1

        self.log.emit("ok", f"合并完成: {len(merged)} 条 (AdminRoc 新增 {adminroc_new})")
        self._build_db_from_pairs(merged, 'wfcd+adminroc', start_time)

    def _run_adminroc(self, start_time: float):
        """AdminRoc 模式：解析 HTML。"""
        # 步骤 1-4: 下载
        self.step_changed.emit(1, "下载 AdminRoc 数据")
        try:
            data = self._download_file(ADMINROC_URL, "AdminRoc")
        except ConnectionError as e:
            self._try_fallback(str(e), start_time)
            return

        # 步骤 5: 解析 HTML
        self.step_changed.emit(5, "解析 HTML 中英文对照")
        html = data.decode('utf-8')
        zh_match = re.search(r'<script\s+id="data-zh"[^>]*>(.*?)</script>', html, re.DOTALL)
        en_match = re.search(r'<script\s+id="data-en"[^>]*>(.*?)</script>', html, re.DOTALL)

        if not zh_match or not en_match:
            self.log.emit("error", "AdminRoc 数据格式已变更")
            self._try_fallback("AdminRoc 格式已变更", start_time)
            return

        zh_lines = [l.strip() for l in zh_match.group(1).strip().split('\n') if l.strip()]
        en_lines = [l.strip() for l in en_match.group(1).strip().split('\n') if l.strip()]
        self.log.emit("ok", f"解析完成: {len(zh_lines)} 条中文, {len(en_lines)} 条英文")

        pairs = [(zh, en, None, '', False) for zh, en in zip(zh_lines, en_lines)]
        self._build_db_from_pairs(pairs, 'adminroc', start_time)

    def _download_file(self, url: str, label: str) -> bytes:
        """通用文件下载（带进度和重试）。"""
        parsed = urllib.request.urlparse(url)
        host = parsed.hostname or ""

        self.step_changed.emit(2, f"DNS 解析 ({label})")
        import socket
        try:
            ip = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            self.log.emit("ok", f"DNS 解析成功 → {ip[0][4][0]}")
        except socket.gaierror as e:
            raise ConnectionError(f"DNS 解析失败: {e}")

        self.step_changed.emit(3, f"建立连接 ({label})")
        resp = None
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                self.log.emit("info", f"第 {attempt} 次重试...")
                time.sleep(2)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "WARFRAME-RELIC/1.0"})
                resp = urllib.request.urlopen(req, timeout=60)
                self.log.emit("ok", f"HTTPS 连接成功")
                break
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                self.log.emit("error", last_error)
                break
            except urllib.error.URLError as e:
                last_error = f"连接失败: {e.reason}"
                self.log.emit("warn", f"连接失败 (第 {attempt}/{self.max_retries} 次): {e.reason}")
            except Exception as e:
                last_error = str(e)
                self.log.emit("warn", f"连接错误 (第 {attempt}/{self.max_retries} 次): {e}")
        else:
            raise ConnectionError(f"{last_error}（已重试 {self.max_retries} 次）")

        # 下载
        self.step_changed.emit(4, f"下载 {label}")
        content_length = resp.headers.get("Content-Length")
        if content_length:
            size_kb = int(content_length) / 1024
            self.log.emit("info", f"文件大小: {size_kb:.0f} KB")

        chunks = []
        downloaded = 0
        total = int(content_length) if content_length else 0
        last_pct = -1
        dl_start = time.time()

        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = min(int(downloaded * 100 / total), 100)
                    if pct != last_pct:
                        self.progress_pct.emit(pct)
                        if pct % 25 == 0:
                            elapsed = time.time() - dl_start
                            speed = (downloaded / 1024 / elapsed) if elapsed > 0 else 0
                            self.log.emit("info", f"下载进度: {pct}% ({downloaded/1024:.0f} KB, {speed:.0f} KB/s)")
                        last_pct = pct
            data = b"".join(chunks)
            dl_time = time.time() - dl_start
            self.log.emit("ok", f"下载完成 → {len(data)/1024:.0f} KB (耗时 {dl_time:.1f}s)")
            self.progress_pct.emit(100)
            return data
        except Exception as e:
            raise ConnectionError(f"下载中断: {e}")
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    def _try_fallback(self, reason: str, start_time: float):
        """当前源失败，尝试回退到备用源。"""
        if self._tried_fallback:
            self.log.emit("error", "所有数据源均已尝试失败")
            self.error.emit(f"所有数据源均无法访问\n最后错误: {reason}")
            return

        self._tried_fallback = True
        fallback_source = 'adminroc' if self.source in ('local', 'wfcd') else 'wfcd'

        self.log.emit("warn", f"━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log.emit("warn", f"主源失败: {reason}")
        self.log.emit("warn", f"自动切换到备用源: {SOURCE_NAMES.get(fallback_source, fallback_source)}")
        self.log.emit("warn", f"━━━━━━━━━━━━━━━━━━━━━━━━")

        self.source = fallback_source
        self.run()

    def _build_db_from_pairs(self, pairs: list, source: str, start_time: float):
        """将 (zh, en, unique_name, item_type, is_tradable) 列表写入数据库。"""
        self.step_changed.emit(6, "构建翻译数据库")

        # 缓存 JSON（兼容旧格式）
        simple_pairs = [(zh, en) for zh, en, *_ in pairs]
        os.makedirs(os.path.dirname(DICT_PATH), exist_ok=True)
        with open(DICT_PATH, 'w', encoding='utf-8') as f:
            json.dump(simple_pairs, f, ensure_ascii=False, indent=2)

        self.log.emit("info", f"共 {len(pairs)} 条对照数据，正在写入数据库...")

        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA_V2)
        conn.execute("DELETE FROM translations")
        cur = conn.cursor()

        inserted = 0
        categories_count = {}

        for item in pairs:
            zh_name, en_name = item[0], item[1]
            unique_name = item[2] if len(item) > 2 else None
            item_type = item[3] if len(item) > 3 else ''
            is_tradable = item[4] if len(item) > 4 else False

            if not zh_name or not en_name:
                continue

            category = classify_item(zh_name, en_name)
            categories_count[category] = categories_count.get(category, 0) + 1

            try:
                cur.execute(
                    """INSERT INTO translations
                       (zh_name, en_name, unique_name, category, source, item_type, is_tradable)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (zh_name, en_name, unique_name, category, source, item_type, int(is_tradable))
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass

        # 元信息
        conn.execute("INSERT OR REPLACE INTO translation_meta (key, value) VALUES ('source', ?)", (source,))
        conn.execute("INSERT OR REPLACE INTO translation_meta (key, value) VALUES ('total', ?)", (str(inserted),))
        conn.execute("INSERT OR REPLACE INTO translation_meta (key, value) VALUES ('updated_at', ?)",
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))

        conn.commit()
        conn.close()

        result = {
            'total': inserted,
            'categories': dict(sorted(categories_count.items())),
            'source': SOURCE_NAMES.get(source, source),
        }

        total_time = time.time() - start_time
        self.log.emit("ok", f"========== 翻译数据库更新完成 (总耗时 {total_time:.1f}s) ==========")
        self.log.emit("ok", f"  数据源: {result['source']}")
        self.log.emit("ok", f"  总计: {inserted} 条")
        for cat, count in sorted(categories_count.items(), key=lambda x: -x[1]):
            self.log.emit("info", f"  {cat}: {count} 条")

        # 自动跟随更新全物品数据库
        try:
            from .items_i18n import auto_rebuild_items_db
            self.log.emit("info", "正在自动更新全物品中英对照数据库...")
            ok = auto_rebuild_items_db(silent=True)
            if ok:
                from .items_i18n import get_db_stats as get_items_stats
                s = get_items_stats()
                self.log.emit("ok", f"全物品数据库已更新: {s['total']} 个物品")
            else:
                self.log.emit("warn", "全物品数据库更新失败（不影响主流程）")
        except Exception:
            pass  # 静默忽略

        self.finished.emit(result)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ('--build', '-b'):
            build_translation_db(source='local')
        elif cmd in ('--build-wfcd', '-w'):
            build_translation_db(source='wfcd')
        elif cmd in ('--build-adminroc', '-a'):
            build_translation_db(source='adminroc')
        elif cmd in ('--search-cn', '-scn') and len(sys.argv) > 2:
            for r in search_cn(sys.argv[2]):
                print(f"  {r['zh_name']}  →  {r['en_name']}  [{r.get('category', '')}]")
        elif cmd in ('--search-en', '-sen') and len(sys.argv) > 2:
            for r in search_en(sys.argv[2]):
                print(f"  {r['en_name']}  →  {r['zh_name']}  [{r.get('category', '')}]")
        elif cmd in ('--stats', '-s'):
            stats = get_translation_db_stats()
            if stats['exists']:
                print(f"翻译数据库: {DB_PATH}")
                print(f"  总条目: {stats['total']}")
                print(f"  文件大小: {stats['db_size']/1024:.1f} KB")
                print(f"  最后更新: {stats['db_mtime']}")
                print(f"  数据源: {stats.get('source', 'N/A')}")
                print(f"  分类统计:")
                for cat, count in stats.get('categories', {}).items():
                    print(f"    {cat}: {count} 条")
            else:
                print("翻译数据库不存在")
        else:
            print("用法:")
            print("  python translation_db.py --build         从本地文件构建 (all_items.json + i18n.json)")
            print("  python translation_db.py --build-wfcd    从网络拉取 WFCD 数据构建")
            print("  python translation_db.py --build-adminroc 从 AdminRoc 构建")
            print("  python translation_db.py --stats         查看数据库统计")
            print("  python translation_db.py --search-cn <关键词>")
            print("  python translation_db.py --search-en <关键词>")
    else:
        if not os.path.exists(DB_PATH):
            print("翻译数据库不存在，正在从本地文件构建...")
            build_translation_db(source='local')
        else:
            stats = get_translation_db_stats()
            print(f"翻译数据库已存在 ({stats['total']} 条记录): {DB_PATH}")
            print("使用 --build 重建, --stats 查看统计")
