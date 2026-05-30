"""
独立物品匹配引擎

将 match_and_price / match_and_translate 的公共匹配逻辑抽取为 match_items()，
消除 80% 重复代码。两个公开函数变为薄封装。

匹配策略（4 轮降级）:
  1. 精确匹配 en_name
  2. 模糊匹配（单词合理性验证）
  3. 纠错候选逐个尝试
  4. 部件蓝图直通（本地 DB 无部件数据，直接查 WM API）
"""

from typing import Optional
from data.items_i18n import search_items
import sqlite3
import os


# ============================================================
# 辅助函数
# ============================================================

# 所有武器/Warframe/守护 部件后缀（不含 Blueprint）
_PART_SUFFIXES = [
    'Blade', 'Barrel', 'Receiver', 'Handle', 'Grip', 'Stock',
    'Head', 'Guard', 'String', 'Lower Limb', 'Upper Limb',
    'Chassis', 'Systems', 'Neuroptics',
    'Carapace', 'Cerebrum',  # 守护部件
]


def _is_warframe_part(name: str) -> bool:
    """判断名称是否是 Warframe/武器部件（含 Blueprint 和非 Blueprint 部件）。"""
    if 'Blueprint' in name:
        return True
    # 检查是否以武器部件后缀结尾（如 Dual Zoren Prime Blade）
    name_lower = name.lower()
    for suffix in _PART_SUFFIXES:
        suffix_lower = suffix.lower()
        if name_lower.endswith(' ' + suffix_lower) or name_lower == suffix_lower:
            return True
    return False


def _en_part_to_cn(en_name: str) -> str:
    """将英文部件蓝图名翻译为中文显示名。"""
    from recognizers.item_name import PART_EN_TO_CN
    for en_suffix in sorted(PART_EN_TO_CN, key=len, reverse=True):
        if en_suffix in en_name:
            base = en_name.replace(f' {en_suffix}', '').strip()
            cn_suffix = PART_EN_TO_CN[en_suffix]
            return f"{base} {cn_suffix}"
    return en_name


def _upsert_part_to_db(item: dict) -> None:
    """将部件直通发现的新物品写入 items_i18n.db（增量补充）。

    写入前会尝试从 zh_en_dict.json 查找官方中文名，找不到则用程序拼接的中文名。
    这样下次 OCR 识别时就能直接精确匹配，无需再走 part_direct 路径。

    注意：不写入非 Prime 战甲/守护部件（它们不可交易，一定是 OCR 漏了 Prime）。
    """
    en_name = item.get('en_name', '')
    zh_name = item.get('zh_name', '')
    category = item.get('category', 'Warframe Parts')
    if not en_name:
        return

    # ★ 拒绝写入不含 Prime 的战甲/守护部件（必为 OCR 错误）
    if 'Prime' not in en_name and category in ('Warframe Parts', 'Sentinel Parts'):
        print(f"[DB-补充] ✗ 跳过非 Prime 部件（OCR 可能漏了 Prime）: \"{en_name}\"", flush=True)
        return

    try:
        db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        db_path = os.path.join(db_dir, 'items_i18n.db')
        if not os.path.exists(db_path):
            return

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 检查是否已存在（避免重复写入）
        cur.execute("SELECT id FROM items WHERE en_name = ?", (en_name,))
        if cur.fetchone():
            conn.close()
            return

        # 尝试从 zh_en_dict.json 获取更好的中文名
        zh_dict_path = os.path.join(db_dir, 'zh_en_dict.json')
        if os.path.exists(zh_dict_path):
            try:
                import json
                with open(zh_dict_path, 'r', encoding='utf-8') as f:
                    zh_en_list = json.load(f)
                en_lower = en_name.lower()
                for entry in zh_en_list:
                    if isinstance(entry, list) and len(entry) >= 2:
                        if entry[1].strip().lower() == en_lower:
                            zh_name = entry[0].strip()
                            break
            except Exception:
                pass

        # 构造 unique_name
        slug = en_name.lower().replace(' ', '_').replace("'", "").replace('-', '_')
        unique_name = f"/Lotus/Supplement/{slug}"

        is_prime = 1 if 'Prime' in en_name else 0
        is_tradable = 1
        rarity = 'Prime' if is_prime else ''

        cur.execute(
            """INSERT OR IGNORE INTO items
               (unique_name, zh_name, en_name, category, item_type,
                is_tradable, is_prime, rarity, mr_requirement, image_name,
                description_zh, description_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (unique_name, zh_name, en_name, category, '',
             is_tradable, is_prime, rarity, 0, '', '', '')
        )
        conn.commit()
        conn.close()
        print(f"[DB-补充] ✓ 已写入数据库: \"{en_name}\" → \"{zh_name}\"", flush=True)
    except Exception as e:
        print(f"[DB-补充] ✗ 写入失败: {e}", flush=True)


def _split_camel_case(text: str) -> str:
    """驼峰拆分: ArchonStretch → Archon Stretch"""
    import re
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', text)
    text = re.sub(r'(?<=\d)(?=[a-zA-Z])', ' ', text)
    return text


def _is_part_prime_only(en_name: str) -> bool:
    """检查部件直通名称的基础名是否只有 Prime 变体可交易。

    策略：
      - 战甲/守护：通过部件词判断（Chassis/Systems/Neuroptics/Carapace/Cerebrum），
        非 Prime 不可交易，所以必含 Prime。
      - 武器：数据库查询确认所有可交易条目都含 Prime。

    例如 "Ash Neuroptics Blueprint" → True（Ash 是战甲，必 Prime）
        "Dual Zoren Prime Blade" → False（已含 Prime）
        "Guandao Blade" → False（武器，非 Prime 也可能可交易）
    """
    if not en_name or 'Prime' in en_name:
        return False

    try:
        import sqlite3

        db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        db_path = os.path.join(db_dir, 'items_i18n.db')
        if not os.path.exists(db_path):
            return False

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # 提取基础名（前 1~2 个单词）
        words = en_name.split()
        for n in range(min(2, len(words)), 0, -1):
            base = ' '.join(words[:n])
            sql = "SELECT en_name FROM items WHERE is_tradable = 1 AND en_name LIKE ?"
            rows = conn.execute(sql, (f"{base} %",)).fetchall()

            if rows:
                _WARFRAME_PARTS = {'Chassis', 'Systems', 'Neuroptics'}
                _SENTINEL_PARTS = {'Carapace', 'Cerebrum'}

                has_prime = any('Prime' in r['en_name'] for r in rows)
                if not has_prime:
                    conn.close()
                    return False

                # 检查部件词类型
                all_parts = set()
                for r in rows:
                    for w in r['en_name'].split():
                        if w in _WARFRAME_PARTS:
                            all_parts.add('warframe')
                        elif w in _SENTINEL_PARTS:
                            all_parts.add('sentinel')

                # 战甲/守护 → Prime-only
                if 'warframe' in all_parts or 'sentinel' in all_parts:
                    conn.close()
                    return True

                # 武器：所有条目都含 Prime
                all_prime = all('Prime' in r['en_name'] for r in rows)
                conn.close()
                return all_prime

        conn.close()
        return False

    except Exception as e:
        print(f"[PRIME-CHECK] 检查失败: {e}", flush=True)
        return False


def _insert_prime_before_part(en_name: str) -> str:
    """在部件词前插入 Prime。

    例如 "Ash Neuroptics Blueprint" → "Ash Prime Neuroptics Blueprint"
        "Carrier Carapace" → "Carrier Prime Carapace"
        "Dual Zoren Blade" → "Dual Zoren Prime Blade"
    """
    # 部件词列表（含 Blueprint）
    part_words = [
        'Neuroptics', 'Chassis', 'Systems',
        'Barrel', 'Receiver', 'Handle', 'Grip', 'Stock',
        'Blade', 'Guard', 'Head', 'String',
        'Lower Limb', 'Upper Limb',
        'Carapace', 'Cerebrum',
        'Blueprint',
    ]

    words = en_name.split()
    for i, w in enumerate(words):
        if w in part_words:
            # 在此部件词前插入 Prime
            words.insert(i, 'Prime')
            return ' '.join(words)

    # 没找到部件词 → 在末尾加 Prime
    return en_name + ' Prime'


def _match_one_item(
    ocr_text: str,
    variants: list[str],
) -> tuple[Optional[dict], str]:
    """对单个 OCR 文本执行 4 轮降级匹配。

    Args:
        ocr_text: OCR 识别的英文文本
        variants: 纠错候选列表

    Returns:
        (matched_item_dict_or_None, match_quality_str)
    """
    matched = None
    match_quality = 'none'
    search_text = _split_camel_case(ocr_text)

    print(f"[匹配-开始] OCR=\"{ocr_text}\" | 搜索=\"{search_text}\" | 候选={variants}", flush=True)

    # ---- 第1轮: 精确匹配 ----
    items = search_items(search_text, is_tradable=True, limit=5)
    for item in items:
        if item.get('en_name', '').lower() == search_text.lower():
            matched = item
            match_quality = 'exact'
            print(f"[匹配-精确] ✓ \"{item['en_name']}\"", flush=True)
            break

    # ---- 第2轮: 模糊匹配 ----
    if not matched and items:
        best = _fuzzy_match(search_text, items)
        if best:
            matched = best
            match_quality = 'fuzzy'
            print(f"[匹配-模糊] ✓ \"{matched['en_name']}\"", flush=True)
        else:
            print(f"[匹配-模糊] ✗ 无合理匹配: {[i['en_name'] for i in items[:5]]}", flush=True)

    # ---- 第3轮: 纠错候选 ----
    if not matched and variants:
        matched, match_quality = _try_variants(ocr_text, variants)
        if matched:
            print(f"[匹配-候选] ✓ \"{matched['en_name']}\" (quality={match_quality})", flush=True)

    # ---- 第4轮: 部件蓝图直通 ----
    if not matched and _is_warframe_part(ocr_text):
        # 尝试用纠正后的 variant 作为 en_name，优先选包含完整信息的
        best_name = ocr_text
        if variants:
            # 优先选：包含 "Neuroptics" / "Blueprint" 等特征词的纠正版
            for v in variants:
                if v != ocr_text and _is_warframe_part(v):
                    # 纠正版更长（含更多单词）优先
                    if len(v.split()) >= len(best_name.split()):
                        best_name = v

        # ★ 自动补全 Prime：OCR 可能漏掉 "Prime" 字样
        #    当物品名不含 Prime 且基础名是 Prime-only 时，插入 "Prime"
        if 'Prime' not in best_name and _is_part_prime_only(best_name):
            # 在部件词前插入 Prime（如 "Ash Neuroptics Blueprint" → "Ash Prime Neuroptics Blueprint"）
            best_name = _insert_prime_before_part(best_name)
            print(f"[匹配-部件直通] 自动补全 Prime: \"{ocr_text}\" → \"{best_name}\"", flush=True)

        matched = {
            'en_name': best_name,
            'zh_name': _en_part_to_cn(best_name),
            'category': 'Warframe Parts',
        }
        match_quality = 'part_direct'
        print(f"[匹配-部件直通] ✓ \"{best_name}\" → zh=\"{matched['zh_name']}\"", flush=True)

        # ★ 将新发现的部件同步写入数据库，下次就能精确匹配
        _upsert_part_to_db(matched)

    if not matched:
        print(f"[匹配-失败] ✗ \"{ocr_text}\" 所有轮次均失败", flush=True)

    return matched, match_quality


def _fuzzy_match(search_text: str, items: list[dict]) -> Optional[dict]:
    """模糊匹配：按单词合理性筛选，取最短名优先（排除 Glyph/Sigil/Emblem）。

    匹配策略（逐级降级）：
      1. 前缀匹配（en 以 search 开头）
      2. 包含匹配（search 的所有单词都在 en 中）
      3. 编辑距离匹配（允许少量 OCR 字符错误）
    """
    st_lower = search_text.lower()
    st_words = st_lower.split()

    reasonable = []
    for item in items:
        en = item.get('en_name', '').lower()
        if not en:
            continue
        words = en.replace("'", " ").replace("-", " ").split()
        # 前缀匹配优先
        if en.startswith(st_lower):
            reasonable.append(item)
            continue
        # 所有搜索词都在结果中
        if all(w in words for w in st_words):
            # 单单词搜索词不能只匹配结果末尾
            if len(st_words) == 1 and words.index(st_words[0]) == len(words) - 1:
                continue
            reasonable.append(item)

    if reasonable:
        reasonable.sort(key=lambda x: len(x.get('en_name', '')))
        for item in reasonable:
            if item.get('category', '') in ('Glyph', 'Sigil', 'Emblem', 'Glyphs'):
                continue
            return item
        return reasonable[0]

    # ---- 第3级: 编辑距离容错 ----
    # 适用于 OCR 字符混淆（如 PNme→Prime, RevenantPNme→Revenant Prime）
    # 对搜索词和每个候选的 en_name 做 Levenshtein 距离比较
    best_item = None
    best_dist = float('inf')
    for item in items:
        en = item.get('en_name', '').lower()
        if not en:
            continue
        dist = _levenshtein(st_lower, en)
        # 允许的最大编辑距离 = max(3, len(st_lower) // 4)
        max_dist = max(3, len(st_lower) // 4)
        if dist <= max_dist and dist < best_dist:
            best_dist = dist
            best_item = item

    if best_item:
        print(f"[匹配-编辑距离] ✓ \"{best_item['en_name']}\" (dist={best_dist})", flush=True)
    return best_item


def _levenshtein(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离（Levenshtein distance）。"""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # 插入、删除、替换的代价
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def _try_variants(ocr_text: str, variants: list[str]) -> tuple[Optional[dict], str]:
    """尝试纠错候选：先精确，再模糊。"""
    ocr_lower = ocr_text.lower()
    ocr_words = set(ocr_lower.split())

    for variant in variants:
        if variant == ocr_text:
            continue
        v_items = search_items(variant, is_tradable=True, limit=5)
        # 精确
        for v_item in v_items:
            if v_item.get('en_name', '').lower() == variant.lower():
                return v_item, 'variant'
        # 模糊
        if v_items:
            v_lower = variant.lower()
            v_words = v_lower.split()
            for v_item in v_items:
                en = v_item.get('en_name', '').lower()
                if not en:
                    continue
                words = en.replace("'", " ").replace("-", " ").split()
                if en.startswith(v_lower):
                    # ★ 检查 OCR 中有多少单词在 en_name 中找到
                    # 防止 "Revenant Prime" 匹配到 "Revenant Prime Theme"
                    # 而 OCR 中还有 "Neuroptics Blueprint" 这些词
                    en_word_set = set(words)
                    covered = sum(1 for w in ocr_words if w in en_word_set)
                    missing = len(ocr_words) - covered
                    # 缺失的单词数不能超过 OCR 总单词数的 50%
                    if missing <= len(ocr_words) * 0.5:
                        return v_item, 'variant_fuzzy'
                    else:
                        continue
                if all(w in words for w in v_words):
                    if len(v_words) == 1 and words.index(v_words[0]) == len(words) - 1:
                        continue
                    return v_item, 'variant_fuzzy'

    return None, 'none'


# ============================================================
# 公开 API
# ============================================================

def match_items(
    recognized: list[tuple[str, list, list[str]]]
) -> list[dict]:
    """将识别到的英文物品名匹配本地数据库（不含价格查询）。

    Args:
        recognized: [(english_name, box, [variants]), ...]

    Returns:
        list[dict]: [{
            'ocr_text', 'en_name', 'zh_name', 'category',
            'box', 'match_quality'
        }, ...]
    """
    results = []
    for ocr_text, box, variants in recognized:
        matched, match_quality = _match_one_item(ocr_text, variants)

        results.append({
            'ocr_text': ocr_text,
            'en_name': matched.get('en_name', ocr_text) if matched else ocr_text,
            'zh_name': matched.get('zh_name', '') if matched else '',
            'category': matched.get('category', '') if matched else '',
            'box': box,
            'match_quality': match_quality,
        })

    return results


def match_and_price(
    recognized: list[tuple[str, list, list[str]]]
) -> list[dict]:
    """将识别到的英文物品名匹配本地数据库并查询价格。

    先调用 match_items() 匹配，然后通过 PriceService 统一查询价格。

    Returns:
        list[dict]: [{
            'ocr_text', 'matched_name', 'zh_name', 'category',
            'box', 'price', 'match_quality', '_price_source'
        }, ...]
    """
    from core.price_service import get_price_service

    base_results = match_items(recognized)
    svc = get_price_service()
    return svc.query_prices_batch(base_results)


def match_and_translate(
    recognized: list[tuple[str, list, list[str]]]
) -> list[dict]:
    """将识别到的英文名匹配翻译为中文（不含价格查询）。

    直接使用 match_items()，仅日志前缀不同。
    """
    return match_items(recognized)
