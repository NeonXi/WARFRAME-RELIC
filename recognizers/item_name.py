"""
可交易物品名称识别器

从截图中 OCR 识别英文物品名 + 中文部件词，
中文部件词映射为英文后缀，输出纯英文名称。

OCR 纠错策略:
  1. 常见 OCR 混淆字符替换: I↔l↔1, O↔0, S↔5, B↔8, G↔6, Z↔2
  2. 驼峰粘连拆分: ArchonStretch → Archon Stretch
  3. Warframe 专有名词白名单纠错

重构后继承 BaseOCR，匹配逻辑已迁移至 recognizers.matcher。
"""

import os
import re
import time
import numpy as np

from recognizers.base_ocr import BaseOCR


# ============================================================
# 中文部件词 → 英文后缀映射
#
# 按物品类型分为三组:
#   战甲部件:  机体/系统/头部神经光元
#   武器部件:  枪管/枪机/握柄/握把/枪托/刀刃/护手/锤头/绳索/下弓臂/上弓臂
#   守护部件:  外壳/头部/系统
#   通用:      蓝图
# ============================================================

# ── 战甲部件（中文 → 英文） ──
_WARFRAME_PART_CN = {
    '机体':          'Chassis',
    '系统':          'Systems',
    '头部神经光元':   'Neuroptics',
    '头部':          'Neuroptics',
    '神经光元':       'Neuroptics',
}

# ── 武器部件（中文 → 英文） ──
_WEAPON_PART_CN = {
    '枪管':  'Barrel',
    '枪机':  'Receiver',
    '握柄':  'Handle',
    '握把':  'Grip',
    '枪托':  'Stock',
    '刀刃':  'Blade',
    '护手':  'Guard',
    '锤头':  'Head',
    '绳索':  'String',
    '下弓臂': 'Lower Limb',
    '上弓臂': 'Upper Limb',
}

# ── 守护部件（中文 → 英文） ──
_SENTINEL_PART_CN = {
    '外壳':  'Carapace',
    '头部':  'Cerebrum',
    '系统':  'Systems',
}

# ── 全部中文部件 → 英文（含 Blueprint 后缀） ──
PART_CN_TO_EN = {}

# 战甲部件 + Blueprint
for cn, en in _WARFRAME_PART_CN.items():
    PART_CN_TO_EN[cn] = f'{en} Blueprint'

# 武器部件（不含 Blueprint）
for cn, en in _WEAPON_PART_CN.items():
    PART_CN_TO_EN[cn] = en

# 守护部件（不含 Blueprint）
for cn, en in _SENTINEL_PART_CN.items():
    PART_CN_TO_EN[cn] = en

# 通用蓝图
PART_CN_TO_EN['蓝图'] = 'Blueprint'


# ── 英文后缀 → 中文名（用于反向翻译显示） ──
PART_EN_TO_CN = {
    'Chassis Blueprint':     '机体蓝图',
    'Systems Blueprint':     '系统蓝图',
    'Neuroptics Blueprint':  '头部神经光元蓝图',
    'Blueprint':             '蓝图',
    'Barrel':      '枪管',
    'Receiver':    '枪机',
    'Handle':      '握柄',
    'Grip':        '握把',
    'Stock':       '枪托',
    'Blade':       '刀刃',
    'Guard':       '护手',
    'Head':        '锤头',
    'String':      '绳索',
    'Lower Limb':  '下弓臂',
    'Upper Limb':  '上弓臂',
    'Carapace':    '外壳',
    'Cerebrum':    '头部',
}

# ── 所有中文部件字符集合（用于 is_all_cjk 等判断） ──
_PART_CHARS = set('机体系统部神经光元蓝图枪握柄把刀刃锤绳弓臂管托手头外壳')

# ============================================================
# OCR 纠错配置
# ============================================================
OCR_CONFUSION_MAP = {
    '0': 'O', '1': 'l', '5': 'S', '8': 'B', '6': 'G', '2': 'Z',
    'l': 'I',
    # ★ 常见 OCR 英文字符混淆对（双向，让 matcher 验证）
    'n': 'h', 'h': 'n',
}

# ★ 中文 OCR 形近字映射（RapidOCR 常见误识别）
#   key: OCR 可能输出的错误字符, value: 正确的候选字符
#   例如 "董击" 中的 "董" 可能是 "重" 的误识别
_CJK_OCR_SIMILAR_MAP: dict[str, list[str]] = {
    '董': ['重'],
    '重': ['董'],
    '土': ['士'],
    '士': ['土'],
    '未': ['末'],
    '末': ['未'],
    '干': ['千'],
    '千': ['干'],
    '日': ['曰'],
    '曰': ['日'],
    '人': ['入'],
    '入': ['人'],
    '已': ['己', '巳'],
    '己': ['已', '巳'],
    '巳': ['已', '己'],
    '刀': ['刃'],
    '刃': ['刀'],
    '大': ['太'],
    '太': ['大'],
    '天': ['夫'],
    '夫': ['天'],
    '牛': ['午'],
    '午': ['牛'],
    '王': ['玉', '主'],
    '玉': ['王'],
    '主': ['王'],
    '鸟': ['乌'],
    '乌': ['鸟'],
    '免': ['兔'],
    '兔': ['免'],
    '爪': ['瓜'],
    '瓜': ['爪'],
    '拨': ['拔'],
    '拔': ['拨'],
    '侯': ['候'],
    '候': ['侯'],
    '梁': ['粱'],
    '粱': ['梁'],
    '栗': ['粟'],
    '粟': ['栗'],
    '淮': ['准'],
    '准': ['淮'],
    '睛': ['晴'],
    '晴': ['睛'],
    '冶': ['治'],
    '治': ['冶'],
    '钩': ['钓', '鈎'],
    '钓': ['钩'],
    '椎': ['堆'],
    '堆': ['椎'],
    '推': ['堆'],
    '徒': ['徙'],
    '徙': ['徒'],
    '载': ['栽'],
    '栽': ['载'],
    '浙': ['淅'],
    '淅': ['浙'],
    '壁': ['璧'],
    '璧': ['壁'],
    '篮': ['蓝'],
    '蓝': ['篮'],
    '蜜': ['密'],
    '密': ['蜜'],
    '崇': ['祟'],
    '祟': ['崇'],
    '寇': ['冠'],
    '冠': ['寇'],
    '盲': ['育'],
    '育': ['盲'],
    '管': ['菅'],
    '菅': ['管'],
    '响': ['晌'],
    '晌': ['响'],
    '倍': ['陪'],
    '陪': ['倍'],
    '班': ['斑'],
    '斑': ['班'],
    '冈': ['岗'],
    '岗': ['冈'],
    '厉': ['历'],
    '历': ['厉'],
    '磨': ['摩'],
    '摩': ['磨'],
    '具': ['俱'],
    '俱': ['具'],
    '受': ['爱'],
    '爱': ['受'],
}


def _generate_cjk_variants(text: str) -> list[str]:
    """生成中文 OCR 形近字纠错变体。

    对文本中每个字符查找 _CJK_OCR_SIMILAR_MAP，生成所有单字符替换的变体。
    例如 "董击" → ["重击"]
    """
    variants = []
    for i, ch in enumerate(text):
        for alt in _CJK_OCR_SIMILAR_MAP.get(ch, []):
            variant = text[:i] + alt + text[i+1:]
            variants.append(variant)
    return variants


# ★ 高频变体词列表：Warframe 专有词（Prime/Primed/Arcane等）
# 这些词会在无数物品名中反复出现，修复一次即可覆盖全部。
_WARFRAME_VARIANT_WORDS = [
    'Prime', 'Primed', 'Arcane', 'Galvanized', 'Amalgam',
    'Prisma', 'Exodia', 'Virtuos', 'Wraith', 'Vandal',
    'Orokin', 'Kavasa', 'Ayatan', 'Necramech', 'Kuva',
    'Tenet', 'Mara', 'Dex', 'Umbra',
]


def _levenshtein_distance(s1: str, s2: str) -> int:
    """编辑距离（Levenshtein distance）。"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _fuzzy_fix_variant_words(text: str) -> str:
    """用编辑距离自动纠正 OCR 文本中与高频变体词相似的子串。

    策略：收集所有可能的替换 → 按位置从后往前替换（避免索引偏移）。
    优先匹配编辑距离更小、窗口更长、位置更靠后的替换。

    边界检测：匹配的子串必须在驼峰边界或文本边缘处开始/结束，
    避免 "ArcaneEnergize" 中 "cane" 被误匹配为 "Arcane"。
    """
    def _is_word_start(i: int) -> bool:
        """子串起始位置 i 是否在驼峰/文本边界。"""
        if i == 0:
            return True
        prev = text[i - 1]
        # 前一个字符是小写字母，当前字符是大写 → 驼峰边界
        if prev.islower() and text[i].isupper():
            return True
        # 前一个字符不是字母 → 单词边界
        if not prev.isalpha():
            return True
        return False

    def _is_word_end(i: int) -> bool:
        """子串结束位置 i 是否在驼峰/文本边界。"""
        if i == len(text):
            return True
        curr = text[i]
        # 当前字符是大写 → 下一个单词开始
        if curr.isupper():
            return True
        if not curr.isalpha():
            return True
        return False

    # 变体词小写集合，用于快速检查子串是否已经是正确词
    _VARIANT_LOWER = {w.lower() for w in _WARFRAME_VARIANT_WORDS}

    # 收集所有候选替换: (start, end, correct_word, distance)
    candidates: list[tuple[int, int, str, int]] = []
    for word in _WARFRAME_VARIANT_WORDS:
        wl = len(word)
        for win_len in range(max(2, wl - 2), min(len(text) + 1, wl + 3)):
            for i in range(len(text) - win_len + 1):
                sub = text[i:i + win_len]
                # 跳过已是正确变体词的子串（避免 Prime→Primed 误纠正）
                if sub.lower() in _VARIANT_LOWER:
                    continue
                if sub[0].lower() != word[0].lower():
                    continue
                # 边界检测：必须在驼峰/文本边界
                if not _is_word_start(i) or not _is_word_end(i + win_len):
                    continue
                max_dist = 2 if wl <= 6 else 3  # 短词2，长词3（长词OCR错误累积更多）
                dist = _levenshtein_distance(sub.lower(), word.lower())
                if dist <= max_dist:
                    candidates.append((i, i + win_len, word, dist))

    if not candidates:
        return text

    # 按位置从后往前排序，优先替换距离小、窗口长的
    candidates.sort(key=lambda c: (c[0], -c[3], c[1] - c[0]), reverse=True)

    # 过滤重叠区间：从后往前，只保留不重叠的
    selected: list[tuple[int, int, str]] = []
    last_end = len(text) + 1
    for start, end, word, dist in candidates:
        if end <= last_end:
            selected.append((start, end, word))
            last_end = start

    # 从后往前替换（selected 已经是按 start 降序）
    fixed = text
    for start, end, word in selected:
        fixed = fixed[:start] + word + fixed[end:]

    return fixed


# 保留一个空的占位，兼容旧代码中对 WF_FIXES 的引用
WF_FIXES: dict[str, str] = {}

# ============================================================
# 正则
# ============================================================
_RE_EN_NAME = re.compile(r"^[A-Z][A-Za-z0-9'\-&\.\s]{2,}$")

_RE_TRASH = re.compile(
    r'^[xX]\d+$|'
    r'^\d+$|'
    r'^(RANK|RANK\s*\d+|MAX|MAXED)$|'
    r'^(DRAIN|COST|CAPACITY)\b|'
    r'^(POLARITY|AURA|STANCE)\b|'
    r'^(INTACT|EXCEPTIONAL|FLAWLESS|RADIANT)$|'
    r'^(OWNED|EQUIP|UPGRADE|FUSION|SOLD|SELL|BUY|TRADE)\b|'
    r'^(CONFIG|LOADOUT|APPEARANCE|MODS|ARSENAL)\b|'
    r'^(ALL|SEARCH|REFINEMENT|EXIT|VOID|RELICS|MARKET)\b|'
    r'^(BLUEPRINT|PRICE|PLATINUM|CREDITS|DAMAGE)\b|'
    r'^[A-Z]{1,2}$',
    re.IGNORECASE
)

_RE_RELIC = re.compile(
    r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s*[A-Za-z0-9]{2,3}\s*(Relic|Exceptional|Flawless|Intact|Radiant)?',
    re.IGNORECASE
)

_RE_NOT_ITEM = re.compile(
    r'^[a-z]|^\d|^\+|%$|^[A-Z][a-z]{1,4}$'
)

# 中文部件词集合（用于判断文本是否含有效部件词，允许通过过滤）
_PART_CN_SET = set(PART_CN_TO_EN.keys())


def _contains_part_cn(text: str) -> bool:
    """检查文本是否包含已知的中文部件词（允许通过过滤）。"""
    for cn in _PART_CN_SET:
        if cn in text:
            return True
    return False


def _is_valid_item_text(text: str) -> bool:
    """判断文本是否为有效物品相关文本（英文名/中文部件/中英混合）。"""
    # 1. 纯中文文本：只要包含已知部件词就算有效
    if _is_all_cjk(text):
        return _contains_part_cn(text)

    # 2. 纯英文文本：用原有规则
    if not _has_cjk(text):
        return bool(_RE_EN_NAME.match(text) and not _RE_TRASH.search(text))

    # 3. 中英混合文本（如 "AshPrime头部"）：检查是否含英文名+中文部件
    #    分离英文和中文部分分别检查
    #    至少含有一个大写字母开头的英文词 + 一个已知中文部件词
    has_en = bool(_RE_EN_NAME.match(text) or re.search(r'[A-Z][a-zA-Z]{2,}', text))
    has_part = _contains_part_cn(text)
    return has_en and has_part


# ============================================================
# 辅助函数
# ============================================================

def _is_all_cjk(s: str) -> bool:
    s_clean = s.replace(' ', '')
    if not s_clean:
        return False
    return all('\u4e00' <= c <= '\u9fff' or c in _PART_CHARS for c in s_clean)


def _has_cjk(s: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' for c in s)


def _cjk_to_en(text: str) -> str | None:
    """将中文部件词翻译为英文后缀（最长匹配优先）。"""
    for cn in sorted(PART_CN_TO_EN, key=len, reverse=True):
        if cn in text:
            return PART_CN_TO_EN[cn]
    return None


# ============================================================
# ★ 三类规则化正则：战甲 / 武器 / 守护
# ============================================================
#
# OCR 识别出的文本结构为:
#   战甲:  [英文特有名称] [Prime] [机体/系统/头部神经光元] [蓝图]
#   武器:  [中文特有名称] [Prime] [枪管/枪机/握把/刀刃/...]
#   守护:  [中文特有名称] [Prime] [外壳/头部/系统] [蓝图]
#
# 通用模式: 特有名称 + 变体(可选) + 部件 + 蓝图(可选)
# ─────────────────────────────────────────────────────────────

# 变体前缀
_RE_VARIANT = r'(?:\s*(?:Prime|Prisma|Wraith|Vandal|Mara|Dex|Umbra|Kuva|Tenet))?'

# 战甲部件正则（"机体"可能跟"蓝图"连写，如"机体蓝图"） 
_RE_WARFRAME_PART = (
    r'\s*(?:机体|系统|头部神经光元|头部|神经光元)(?:\s*蓝图)?'
)

# 武器部件正则（不含蓝图）
_RE_WEAPON_PART = (
    r'\s*(?:枪管|枪机|握柄|握把|枪托|刀刃|护手|锤头|绳索|下弓臂|上弓臂)'
)

# 守护部件正则（"外壳"可能跟"蓝图"连写，如"外壳蓝图"）
_RE_SENTINEL_PART = (
    r'\s*(?:外壳|头部|系统)(?:\s*蓝图)?'
)


# ── 编译三类匹配正则 ──
# 格式: 特有名称(英文/中文) + 变体 + 部件 + 蓝图?
# 战甲: 特有名称是英文（如 Ash），所以用 [A-Za-z]+ 匹配
# 武器: 特有名称是中文（如 关刀），所以用 [\u4e00-\u9fff]+ 匹配
# 守护: 特有名称是中文（如 搬运者），所以用 [\u4e00-\u9fff]+ 匹配

_RE_WARFRAME_MATCH = re.compile(
    r'^([A-Z][A-Za-z0-9\'\-\s]+?)'   # 英文特有名称（最少匹配）
    + _RE_VARIANT                      # Prime/Prisma 等变体
    + _RE_WARFRAME_PART                # 机体/系统/头部神经光元 蓝图
    + r'\s*$'
)

_RE_WEAPON_MATCH = re.compile(
    r'^([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+)'  # 中文特有名称
    + _RE_VARIANT                                      # Prime/Prisma 等变体
    + _RE_WEAPON_PART                                  # 武器部件
    + r'\s*$'
)

_RE_SENTINEL_MATCH = re.compile(
    r'^([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+)'  # 中文特有名称
    + _RE_VARIANT                                      # Prime/Prisma 等变体
    + _RE_SENTINEL_PART                                # 守护部件
    + r'\s*$'
)

# ── 通用纯英文匹配（兜底：OCR 结果本身就是纯英文） ──
# 策略: 接受任何以大写字母开头 + 字母/数字/空格/引号/连字符的文本
# 匹配后通过 _extract_features 内部的词条提取逻辑分离部件和变体
_RE_PURE_EN_MATCH = re.compile(
    r'^([A-Z][A-Za-z0-9\'\-\s]+)'       # 英文特有名称（贪婪，匹配整行）
    + r'\s*$'
)

# ── 用于从匹配文本中提取具体部分的辅助正则 ──
_RE_PRIME = re.compile(r'\b(Prime|Prisma|Wraith|Vandal|Mara|Dex|Umbra|Kuva|Tenet)\b', re.IGNORECASE)

# 所有中文部件词（按长度降序，用于从匹配文本中提取）
_ALL_PART_CN_SORTED = sorted(PART_CN_TO_EN.keys(), key=len, reverse=True)


def _extract_features(text: str) -> tuple[str, list[str]]:
    """从 OCR 文本中提取 特有名称 + 特征词列表。

    使用三类规则化正则匹配:
      1. 战甲模式: Ash Prime 机体蓝图 → en_name="Ash", features=["Prime", "Chassis Blueprint"]
      2. 武器模式: 关刀 Prime 刀刃     → en_name="关刀", features=["Prime", "Blade"]
      3. 守护模式: 搬运者 Prime 外壳    → en_name="搬运者", features=["Prime", "Carapace"]
      4. 纯英文兜底: Dual Zoren Prime Blade → en_name="Dual Zoren", features=["Prime", "Blade"]

    返回的 features 已按正确顺序排列: [变体前缀, 部件后缀, 蓝图后缀]
    """
    text = text.strip()
    if not text:
        return '', []

    # ── 尝试四类匹配 ──
    match = None
    match_type = None

    # 优先级: 战甲 > 守护 > 武器 > 纯英文
    # （守护在武器之前，因为守护部件"头部"也可能被武器模式误匹配）

    m = _RE_WARFRAME_MATCH.match(text)
    if m:
        match = m
        match_type = 'warframe'

    if not match:
        m = _RE_SENTINEL_MATCH.match(text)
        if m:
            match = m
            match_type = 'sentinel'

    if not match:
        m = _RE_WEAPON_MATCH.match(text)
        if m:
            match = m
            match_type = 'weapon'

    if not match:
        m = _RE_PURE_EN_MATCH.match(text)
        if m:
            match = m
            match_type = 'pure_en'

    if not match:
        # 所有正则都不匹配，回退到旧逻辑（通用分词法）
        print(f"[EXTRACT] 无规则匹配，回退通用分词: \"{text}\"", flush=True)
        return _extract_features_fallback(text)

    print(f"[EXTRACT] 类型={match_type} 匹配: \"{text}\"", flush=True)

    # ── 提取特有名称 ──
    unique_name = match.group(1).strip()

    # ── 提取特征词 ──
    # 从匹配的完整文本中提取变体、部件、蓝图
    matched_text = match.group(0)
    features = []

    # 1. 变体前缀 (Prime/Prisma 等)
    variant_m = _RE_PRIME.search(matched_text)
    if variant_m:
        features.append(variant_m.group(1))
        # 从文本中移除变体部分，便于后续提取部件
        matched_text = matched_text.replace(variant_m.group(0), '', 1).strip()

    # 2. 中文部件词 → 英文
    for cn_part in _ALL_PART_CN_SORTED:
        if cn_part in matched_text:
            en_part = PART_CN_TO_EN.get(cn_part)
            if en_part:
                # 检查去重: 不重复添加已有特征的子集
                en_words = set(en_part.split())
                is_dup = False
                for existing in features:
                    existing_words = set(existing.split())
                    if en_words <= existing_words:
                        is_dup = True
                        break
                    elif existing_words <= en_words:
                        features.remove(existing)
                        break
                if not is_dup:
                    features.append(en_part)
                matched_text = matched_text.replace(cn_part, '', 1).strip()
                break  # 最长匹配，找到就停

    # 2b. 英文部件词提取（用于 pure_en 模式兜底）
    #     从 matched_text 中检测已知英文部件词
    _EN_PART_WORDS = [
        'Chassis', 'Systems', 'Neuroptics', 'Lower Limb', 'Upper Limb',
        'Barrel', 'Receiver', 'Handle', 'Grip', 'Stock',
        'Blade', 'Guard', 'Head', 'String', 'Carapace', 'Cerebrum',
        'Blueprint',
    ]
    for en_part in sorted(_EN_PART_WORDS, key=len, reverse=True):
        # 使用词边界匹配，避免 "Head" 匹配到 "Headline"
        pattern = re.compile(r'\b' + re.escape(en_part) + r'\b')
        if pattern.search(matched_text):
            # 检查去重
            en_words = set(en_part.split())
            is_dup = False
            for existing in features:
                existing_words = set(existing.split())
                if en_words <= existing_words:
                    is_dup = True
                    break
                elif existing_words <= en_words:
                    features.remove(existing)
                    break
            if not is_dup:
                features.append(en_part)
            matched_text = pattern.sub('', matched_text, count=1).strip()
            # 不 break，继续提取剩余部件词

    # 3. 蓝图后缀（仅战甲部件需要 Blueprint，武器和守护不需要）
    #    战甲部件翻译已经自带 Blueprint（如 "Chassis Blueprint"），
    #    此处只处理战甲模式下"蓝图"未合并到部件翻译中的情况
    if '蓝图' in matched_text and not any('Blueprint' in f for f in features):
        # 仅战甲模式需要追加 Blueprint
        if match_type == 'warframe':
            features.append('Blueprint')

    # ── 对于 pure_en 模式：从 unique_name 中减去已提取的特征词 ──
    if match_type == 'pure_en':
        remaining = unique_name
        for f in features:
            pattern = re.compile(r'\b' + re.escape(f) + r'\b')
            remaining = pattern.sub('', remaining, count=1)
        unique_name = ' '.join(remaining.split()).strip()

    # ── 排序特征词: 变体前缀 → 部件 → 蓝图 ──
    _VARIANT_SET = {'Prime', 'Prisma', 'Wraith', 'Vandal', 'Mara', 'Dex', 'Umbra', 'Kuva', 'Tenet'}
    features.sort(key=lambda f: (
        f not in _VARIANT_SET,        # 变体排前
        f == 'Blueprint',              # 蓝图排最后
    ))

    print(f"[EXTRACT] 特有名称=\"{unique_name}\" 特征词={features}", flush=True)
    return unique_name, features


def _extract_features_fallback(text: str) -> tuple[str, list[str]]:
    """通用分词法兜底：遍历所有特征词剥离。

    当规则化正则无法匹配时使用（处理异常格式的 OCR 文本）。
    """
    remaining = text
    hits = []

    # 所有特征词按长度降序
    # 注意："蓝图"单独添加需要特殊处理（仅战甲模式需要）
    all_features = sorted(
        list(PART_CN_TO_EN.keys()) + ['Prime', 'Prisma', 'Wraith', 'Vandal', 'Mara'],
        key=len, reverse=True
    )

    # 武器/守护部件词集合（不含 Blueprint），用于判断是否应该跳过"蓝图"
    _NON_WARFRAME_PARTS = {
        'Barrel', 'Receiver', 'Handle', 'Grip', 'Stock',
        'Blade', 'Guard', 'Head', 'String', 'Lower Limb', 'Upper Limb',
        'Carapace', 'Cerebrum',
    }

    for fw in all_features:
        idx = remaining.find(fw)
        if idx < 0:
            continue
        en = PART_CN_TO_EN.get(fw, fw)

        # ★ 蓝图只在战甲模式下才需要
        #    如果已提取的特征中有武器/守护部件词，跳过"蓝图"
        if fw == '蓝图':
            has_non_warframe_part = any(
                set(e.split()) & _NON_WARFRAME_PARTS
                for _, e in hits
            )
            if has_non_warframe_part:
                remaining = remaining[:idx] + remaining[idx + len(fw):]
                continue

        en_words = set(en.split())
        is_duplicate = False
        for _, existing_en in hits:
            existing_words = set(existing_en.split())
            if en_words <= existing_words:
                is_duplicate = True
                break
            elif existing_words <= en_words:
                hits = [(p, e) for p, e in hits if e != existing_en]
                break

        if is_duplicate:
            remaining = remaining[:idx] + remaining[idx + len(fw):]
            continue

        hits.append((idx, en))
        remaining = remaining[:idx] + remaining[idx + len(fw):]

    unique_part = ' '.join(remaining.split()).strip()

    # 兜底：如果特有名以英文特征词结尾，剥离
    for fw in ['Blueprint', 'Chassis', 'Systems', 'Neuroptics',
               'Barrel', 'Receiver', 'Handle', 'Grip', 'Stock',
               'Blade', 'Guard', 'Head', 'String', 'Lower Limb', 'Upper Limb',
               'Carapace', 'Cerebrum']:
        if unique_part.endswith(' ' + fw):
            unique_part = unique_part[:-(len(fw)+1)].strip()
            hits.insert(0, (0, fw))

    # 排序: 变体 → 部件
    variant_set = {'Prime', 'Prisma', 'Wraith', 'Vandal', 'Mara'}
    part_set = set(fw)
    hits.sort(key=lambda h: (
        h[1] not in variant_set,
        h[1] in part_set,
        h[0],
    ))

    features = [h[1] for h in hits]
    return unique_part, features


def _fuzzy_search_cn_in_db(cn_name: str, max_distance: int = 2) -> str | None:
    """用数据库模糊搜索纠正 OCR 识别错误的中文物品名。

    策略：
      1. 用 OCR 识别到的中文名做 LIKE 模糊查询（SQLite）
      2. 对返回的候选中文名计算编辑距离
      3. 取编辑距离最小的匹配（≤ max_distance 且 ≤ 名称长度的 40%）

    这样不需要手动维护形近字映射表，利用全物品数据库自动纠错。
    """
    if not cn_name or len(cn_name) < 2:
        return None

    try:
        import sqlite3
        from data.items_i18n import DB_PATH

        if not os.path.exists(DB_PATH):
            return None

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # ★ 用每个字符做模糊搜索，取候选集
        #    例如 "暮新" → zh_name LIKE '%暮%' AND zh_name LIKE '%新%'
        #    这样能大幅缩小候选范围
        conditions = []
        params = []
        for ch in cn_name:
            conditions.append("zh_name LIKE ?")
            params.append(f"%{ch}%")

        sql = "SELECT zh_name, en_name FROM items WHERE " + " AND ".join(conditions)
        # 额外限定：候选长度与 OCR 结果相近（±3 字）
        name_len = len(cn_name)
        sql += f" AND LENGTH(zh_name) BETWEEN ? AND ?"
        params.extend([max(1, name_len - 3), name_len + 3])

        sql += " LIMIT 30"

        rows = conn.execute(sql, params).fetchall()

        # ★ 如果全字符 AND 无候选（OCR 误识别导致某字符不在库中），
        #    降级为 OR 查询 + 编辑距离筛选（至少一个字符命中即可）
        if not rows and len(cn_name) >= 2:
            or_conditions = []
            or_params = []
            for ch in cn_name:
                or_conditions.append("zh_name LIKE ?")
                or_params.append(f"%{ch}%")
            or_sql = ("SELECT zh_name, en_name FROM items WHERE ("
                      + " OR ".join(or_conditions) + ")")
            or_sql += f" AND LENGTH(zh_name) BETWEEN ? AND ?"
            or_params.extend([max(1, name_len - 3), name_len + 3])
            or_sql += " LIMIT 50"
            rows = conn.execute(or_sql, or_params).fetchall()

        conn.close()

        if not rows:
            print(f"[OCR-FUZZY] 模糊搜索无候选: \"{cn_name}\"", flush=True)
            return None

        print(f"[OCR-FUZZY] LIKE粗筛获得 {len(rows)} 个候选: "
              f"{[(r['zh_name'], r['en_name']) for r in rows[:8]]}", flush=True)

        # ★ 编辑距离精排
        best = None
        best_dist = max_distance + 1
        threshold = max(max_distance, int(name_len * 0.4))

        for row in rows:
            zh = row['zh_name']
            # 跳过明显不匹配的（含 Blueprint 但 OCR 名没有 Blueprint）
            dist = _levenshtein_distance(cn_name, zh)
            if dist <= best_dist and dist <= threshold:
                # 如果距离相同，优先选更短的（更可能是基础名而非部件名）
                if dist < best_dist or (dist == best_dist and best and len(zh) < len(best['zh_name'])):
                    best_dist = dist
                    best = dict(row)

        if best:
            en_result = best['en_name']
            # 跳过 "XXX Set" 条目（整套物品，游戏内不会显示）
            if en_result.endswith(' Set'):
                # 尝试找下一个非 Set 的候选
                for row in rows:
                    zh = row['zh_name']
                    dist = _levenshtein_distance(cn_name, zh)
                    if dist <= threshold and not row['en_name'].endswith(' Set'):
                        best = dict(row)
                        en_result = best['en_name']
                        break
                else:
                    print(f"[OCR-FUZZY] 所有候选均为 Set 套装，跳过: \"{cn_name}\"", flush=True)
                    return None
            print(f"[OCR-FUZZY] 最佳匹配: \"{cn_name}\" → \"{best['zh_name']}\""
                  f" → \"{en_result}\" (距离={best_dist})", flush=True)
            return en_result
        else:
            print(f"[OCR-FUZZY] 无满足距离阈值的匹配: \"{cn_name}\"", flush=True)
            return None

    except Exception as e:
        print(f"[OCR-FUZZY] 模糊搜索异常: {e}", flush=True)
        return None


def _fuzzy_search_cn_in_db_with_dist(cn_name: str, max_distance: int = 2) -> tuple[int, str | None]:
    """与 _fuzzy_search_cn_in_db 相同，但返回 (编辑距离, en_name)。

    用于比较原始文本和形近字变体的匹配质量。
    """
    if not cn_name or len(cn_name) < 2:
        return (999, None)

    try:
        import sqlite3
        from data.items_i18n import DB_PATH

        if not os.path.exists(DB_PATH):
            return (999, None)

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []
        for ch in cn_name:
            conditions.append("zh_name LIKE ?")
            params.append(f"%{ch}%")

        sql = "SELECT zh_name, en_name FROM items WHERE " + " AND ".join(conditions)
        name_len = len(cn_name)
        sql += f" AND LENGTH(zh_name) BETWEEN ? AND ?"
        params.extend([max(1, name_len - 3), name_len + 3])
        sql += " LIMIT 30"

        rows = conn.execute(sql, params).fetchall()

        if not rows and len(cn_name) >= 2:
            or_conditions = []
            or_params = []
            for ch in cn_name:
                or_conditions.append("zh_name LIKE ?")
                or_params.append(f"%{ch}%")
            or_sql = ("SELECT zh_name, en_name FROM items WHERE ("
                      + " OR ".join(or_conditions) + ")")
            or_sql += f" AND LENGTH(zh_name) BETWEEN ? AND ?"
            or_params.extend([max(1, name_len - 3), name_len + 3])
            or_sql += " LIMIT 50"
            rows = conn.execute(or_sql, or_params).fetchall()

        conn.close()

        if not rows:
            return (999, None)

        best = None
        best_dist = max_distance + 1
        threshold = max(max_distance, int(name_len * 0.4))

        for row in rows:
            zh = row['zh_name']
            dist = _levenshtein_distance(cn_name, zh)
            if dist <= best_dist and dist <= threshold:
                if dist < best_dist or (dist == best_dist and best and len(zh) < len(best['zh_name'])):
                    best_dist = dist
                    best = dict(row)

        if best:
            en_result = best['en_name']
            if en_result.endswith(' Set'):
                for row in rows:
                    zh = row['zh_name']
                    dist = _levenshtein_distance(cn_name, zh)
                    if dist <= threshold and not row['en_name'].endswith(' Set'):
                        best = dict(row)
                        en_result = best['en_name']
                        break
                else:
                    return (best_dist, None)
            return (best_dist, en_result)

        return (999, None)

    except Exception as e:
        print(f"[OCR-FUZZY-DIST] 异常: {e}", flush=True)
        return (999, None)


# ── 过滤无效翻译候选 ──
# 游戏内实际显示的道具名称不应包含这些词
_INVALID_EN_SUFFIXES = (
    ' Set',        # 整套物品（如 "Guandao Prime Set"）
    ' Glyph',      # 浮印
)
_INVALID_EN_WORDS = (
    'Glyph',       # 浮印
    ' Skin',       # 外观
    ' Helmet',     # 头盔（非可交易部件）
    ' Prex',       # Prex 卡片
)
_INVALID_ZH_PATTERNS = (
    '浮印',        # Glyph
    '外观',        # Skin
    '头盔',        # Helmet
)


def _filter_valid_translations(query: str, items: list[dict]) -> list[str]:
    """从 search_items 结果中筛选有效的英文名，按优先级排序。

    排除: Set 套装、Glyph 浮印、Skin 外观、Helmet 头盔。
    优先级: 精确 zh_name 匹配 > 精确 en_name 匹配 > 最短不含部件的基础名。
    """
    results = []
    for item in items:
        en = item.get('en_name', '')
        zh = item.get('zh_name', '')
        if not en:
            continue

        # 排除无效条目
        if en.endswith(_INVALID_EN_SUFFIXES):
            continue
        if any(w in en for w in _INVALID_EN_WORDS):
            continue
        if any(p in zh for p in _INVALID_ZH_PATTERNS):
            continue

        # 计算优先级分数（越小越优先）
        score = 0

        # 精确匹配中文名加分
        if zh == query:
            score -= 100
        # 精确匹配英文名加分
        elif en.lower() == query.lower():
            score -= 50
        # 中文名包含部件词（如"外壳""刀刃"）减分
        for cn_part in _ALL_PART_CN_SORTED:
            if cn_part in zh:
                score += 20
                break
        # 英文名包含 Blueprint 减分
        if 'Blueprint' in en:
            score += 10
        # 英文名过长减分（基础名通常较短）
        score += len(en)

        results.append((score, en))

    results.sort(key=lambda x: x[0])
    return [en for _, en in results]


def _is_prime_only_base(en_name: str) -> bool:
    """检查一个基础物品名是否只有 Prime 变体可交易。

    策略：
      - 战甲/守护：所有非 Prime 部件不可交易（只通过任务掉落），
        所以任何战甲/守护的部件必定是 Prime 变体。
      - 武器：数据库查询，判断是否所有可交易条目都含 Prime。

    例如 "Ash" → True（战甲，必 Prime）
        "Carrier" → True（守护，必 Prime）
        "Burston" → False（武器，有非 Prime 可交易部件）
    """
    if not en_name or 'Prime' in en_name:
        return False

    try:
        import sqlite3
        from data.items_i18n import DB_PATH

        if not os.path.exists(DB_PATH):
            return False

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # 搜索以此名为前缀的可交易条目
        sql = "SELECT en_name FROM items WHERE is_tradable = 1 AND en_name LIKE ?"
        rows = conn.execute(sql, (f"{en_name} %",)).fetchall()
        conn.close()

        if not rows:
            return False

        # ★ 判断是否是战甲/守护部件（通过部件词判断，不依赖 category）
        #    战甲部件: Chassis, Systems, Neuroptics
        #    守护部件: Carapace, Cerebrum
        _WARFRAME_PART_WORDS = {'Chassis', 'Systems', 'Neuroptics'}
        _SENTINEL_PART_WORDS = {'Carapace', 'Cerebrum'}

        has_prime = any('Prime' in r['en_name'] for r in rows)
        if not has_prime:
            return False

        # 检查可交易条目中的部件词类型
        all_parts = set()
        for r in rows:
            for word in r['en_name'].split():
                if word in _WARFRAME_PART_WORDS:
                    all_parts.add('warframe')
                elif word in _SENTINEL_PART_WORDS:
                    all_parts.add('sentinel')

        # 战甲/守护部件 → 只有 Prime 可交易
        if 'warframe' in all_parts or 'sentinel' in all_parts:
            part_type = '战甲' if 'warframe' in all_parts else '守护'
            print(f"[PRIME-CHECK] \"{en_name}\" 是{part_type}"
                  f" → 自动补全 Prime", flush=True)
            return True

        # 武器类：需要所有可交易条目都含 Prime
        all_prime = all('Prime' in r['en_name'] for r in rows)
        if all_prime:
            print(f"[PRIME-CHECK] \"{en_name}\" 武器仅 Prime 可交易 → 自动补全 Prime", flush=True)
            return True

        return False

    except Exception as e:
        print(f"[PRIME-CHECK] 检查失败: {e}", flush=True)
        return False


def _translate_cn_unique_name(cn_name: str) -> str | None:
    """将中文特有名称翻译为英文（使用 i18n 数据库）。

    支持整体翻译和逐词翻译两种策略：
    1. 整体匹配（优先）
    2. 数据库模糊搜索 + 编辑距离纠错（利用全物品数据自动纠错）
    3. 逐词翻译（兜底：当特有名包含多个混合中文片段时）

    注意：自动过滤 Set（整套）、Glyph（浮印）、Skin（外观）等非道具条目。
    """
    try:
        from data.items_i18n import search_items
        # 策略1: 整体翻译（仅对含中文的查询执行数据库搜索）
        if re.search(r'[\u4e00-\u9fff]', cn_name):
            # 1a: 原始查询精确搜索
            items = search_items(cn_name, is_tradable=False, limit=30)
            valid = _filter_valid_translations(cn_name, items)
            if valid:
                return valid[0]

            # 1b: 形近字变体精确搜索（OCR 字符误识别纠正）
            for variant in _generate_cjk_variants(cn_name):
                items_v = search_items(variant, is_tradable=False, limit=30)
                valid_v = _filter_valid_translations(variant, items_v)
                if valid_v:
                    print(f"[OCR-CN-FIX] 形近字精确匹配: \"{cn_name}\" → \"{variant}\""
                          f" → \"{valid_v[0]}\"", flush=True)
                    return valid_v[0]
    except Exception:
        pass

    # 策略2: 数据库模糊搜索 + 编辑距离纠错
    if re.search(r'[\u4e00-\u9fff]', cn_name):
        # 同时尝试原始文本和形近字变体，选编辑距离最小的
        best_result = None
        best_dist = 999

        # 2a: 原始文本
        dist, result = _fuzzy_search_cn_in_db_with_dist(cn_name)
        if result and dist < best_dist:
            best_dist = dist
            best_result = result

        # 2b: 形近字变体
        for variant in _generate_cjk_variants(cn_name):
            dist, result = _fuzzy_search_cn_in_db_with_dist(variant)
            if result and dist < best_dist:
                best_dist = dist
                best_result = result
                print(f"[OCR-CN-FIX] 形近字纠错: \"{cn_name}\" → \"{variant}\""
                      f" → \"{result}\" (距离={dist})", flush=True)

        if best_result:
            return best_result
    if not cn_name or not re.search(r'[\u4e00-\u9fff]', cn_name):
        return None

    parts = cn_name.split()
    translated_parts = []
    changed = False
    for part in parts:
        if re.search(r'[\u4e00-\u9fff]', part):
            translated = _translate_one_cn_part(part)
            if translated:
                translated_parts.append(translated)
                changed = True
                continue
        translated_parts.append(part)

    result = ' '.join(translated_parts) if changed else None
    # ★ 最后防线：永远不要返回 Set（套装）
    if result and result.endswith(' Set'):
        return None
    return result


def _translate_one_cn_part(part: str) -> str | None:
    """翻译单个含中文的片段，去除嵌入的英文/数字后再尝试。

    例如 "关刀Prime刀刃" → 剥离已知部件词和英文 → "关刀" → 翻译为 "Guandao"
    """
    try:
        from data.items_i18n import search_items

        def _pick_first_non_set(items, cn_clean):
            """从结果中选最合适的非 Set 条目。

            优先级：精确 zh_name 匹配 > 不含部件词的基础名 > 任意非 Set 条目。
            """
            if not items:
                return None
            non_set = [it for it in items
                       if it.get('en_name', '') and not it.get('en_name', '').endswith(' Set')]
            if not non_set:
                return None
            # 优先：zh_name 精确匹配（基础名）
            for it in non_set:
                if it.get('zh_name', '') == cn_clean:
                    return it['en_name']
            # 其次：不含部件词（Blueprint/Stock/Receiver/Barrel/String/Link/Blade/Handle 等）
            PART_EN_WORDS = ('Blueprint', 'Stock', 'Receiver', 'Barrel',
                            'String', 'Link', 'Blade', 'Handle', 'Guard',
                            'Head', 'Chassis', 'Systems', 'Neuroptics')
            for it in non_set:
                en = it.get('en_name', '')
                if not any(w in en for w in PART_EN_WORDS):
                    return en
            # 兜底：第一个非 Set
            return non_set[0]['en_name']

        # 先去除非中文字符，用纯中文名搜索
        cn_clean = re.sub(r'[^\u4e00-\u9fff\s]', '', part).strip()
        if cn_clean:
            items = search_items(cn_clean, is_tradable=False, limit=10)
            result = _pick_first_non_set(items, cn_clean)
            if result:
                return result

        # 纯中文搜索失败 → 剥离已知中文部件词后再试
        # 例如 "关刀刀刃" → 去掉"刀刃" → "关刀"
        if cn_clean:
            # 按长优先排序的部件词列表剥离
            sorted_parts = sorted(PART_CN_TO_EN.keys(), key=len, reverse=True)
            for cn_part in sorted_parts:
                if cn_clean.endswith(cn_part) and len(cn_clean) > len(cn_part):
                    cn_base = cn_clean[:-len(cn_part)].strip()
                    if cn_base:
                        items = search_items(cn_base, is_tradable=False, limit=10)
                        result = _pick_first_non_set(items, cn_base)
                        if result:
                            return result
                    break
    except Exception:
        pass
    return None


def _is_warframe_part(name: str) -> bool:
    return 'Blueprint' in name


def _en_part_to_cn(en_name: str) -> str:
    """将英文部件蓝图名翻译为中文显示名。"""
    for en_suffix in sorted(PART_EN_TO_CN, key=len, reverse=True):
        if en_suffix in en_name:
            base = en_name.replace(f' {en_suffix}', '').strip()
            cn_suffix = PART_EN_TO_CN[en_suffix]
            return f"{base} {cn_suffix}"
    return en_name


# ============================================================
# ItemNameRecognizer
# ============================================================

class ItemNameRecognizer(BaseOCR):
    """从截图中识别可交易物品英文名。

    流程:
      1. RapidOCR 识别所有文本（继承 BaseOCR 管线）
      2. 过滤垃圾（UI按钮、遗物名、纯数字等）
      3. 分离英文名称行和中文部件行
      4. 合并跨行碎片
      5. 中文部件词 → 英文后缀映射
      6. 输出纯英文名称 + 纠错候选
    """

    TRASH_PATTERN = _RE_TRASH
    MERGE_SEPARATOR = ' '

    # ---- OCR 纠错 ----

    @staticmethod
    def _split_camel_case(text: str) -> str:
        """驼峰拆分: ArchonStretch → Archon Stretch"""
        text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
        text = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', text)
        text = re.sub(r'(?<=\d)(?=[a-zA-Z])', ' ', text)
        return text

    @staticmethod
    def _fix_ocr_confusions(text: str) -> list[str]:
        """生成多个纠错候选。"""
        candidates = [text]

        # 1. 高频变体词自动纠错（编辑距离，无需硬编码）
        fixed = _fuzzy_fix_variant_words(text)
        if fixed != text:
            candidates.append(fixed)

        # 2. 混淆字符替换
        for ch in set(text):
            if ch in OCR_CONFUSION_MAP:
                variant = text.replace(ch, OCR_CONFUSION_MAP[ch])
                if variant != text and variant not in candidates:
                    candidates.append(variant)

        # 3. 驼峰拆分
        camel = ItemNameRecognizer._split_camel_case(text)
        if camel != text and camel not in candidates:
            candidates.append(camel)

        # 4. 驼峰拆分 + 变体词纠错
        if camel != text:
            camel_fixed = _fuzzy_fix_variant_words(camel)
            if camel_fixed != camel and camel_fixed not in candidates:
                candidates.append(camel_fixed)

        return candidates

    # ---- 自定义过滤 ----

    def _filter_text(self, text: str) -> bool:
        """返回 True 保留该文本行。允许英文名、中文部件词、中英混合。"""
        if _RE_RELIC.search(text):
            return False
        if _RE_TRASH.search(text):
            return False
        if _RE_NOT_ITEM.search(text):
            return False
        return _is_valid_item_text(text)

    # ---- 合并行（自定义分隔符：CJK 不加空格） ----

    def _merge_adjacent_lines_cjk(
        self, candidates: list[tuple[str, list]]
    ) -> list[tuple[str, list]]:
        """合并相邻行，CJK 碎片不加空格分隔。"""
        if len(candidates) <= 1:
            return list(candidates)

        sorted_cands = sorted(candidates, key=lambda c: (c[1][0][1], c[1][0][0]))
        merged = []
        used = [False] * len(sorted_cands)

        for i in range(len(sorted_cands)):
            if used[i]:
                continue

            text_i, box_i = sorted_cands[i]
            y_top_i, y_bot_i = box_i[0][1], box_i[2][1]
            x_left_i, x_right_i = box_i[0][0], box_i[1][0]
            height_i = y_bot_i - y_top_i

            best_j = -1
            best_overlap = 0

            for j in range(i + 1, len(sorted_cands)):
                if used[j]:
                    continue

                text_j, box_j = sorted_cands[j]
                y_top_j, y_bot_j = box_j[0][1], box_j[2][1]
                x_left_j, x_right_j = box_j[0][0], box_j[1][0]
                height_j = y_bot_j - y_top_j

                vertical_gap = y_top_j - y_bot_i
                avg_height = (height_i + height_j) / 2

                if vertical_gap < 0 or vertical_gap > avg_height * 1.2:
                    continue

                overlap_left = max(x_left_i, x_left_j)
                overlap_right = min(x_right_i, x_right_j)
                overlap_width = overlap_right - overlap_left
                if overlap_width <= 0:
                    continue

                min_width = min(x_right_i - x_left_i, x_right_j - x_left_j)
                overlap_ratio = overlap_width / max(min_width, 1)

                if overlap_ratio > 0.3 and overlap_width > best_overlap:
                    best_overlap = overlap_width
                    best_j = j

            if best_j >= 0:
                text_j, box_j = sorted_cands[best_j]
                sep = '' if (_is_all_cjk(text_i) and _is_all_cjk(text_j)) else ' '
                merged_text = f"{text_i}{sep}{text_j}"
                merged_box = self._merge_box(box_i, box_j)
                merged.append((merged_text, merged_box))
                used[i] = True
                used[best_j] = True
            else:
                merged.append((text_i, box_i))
                used[i] = True

        return merged

    # ---- 主识别流程 ----

    def recognize_all_with_boxes(
        self, image: np.ndarray
    ) -> list[tuple[str, list, list[str]]]:
        """识别截图中所有物品名称。

        使用位置启发式分组识别。
        """
        t0 = time.perf_counter()

        result, scale = self._run_ocr(image)
        if result is None:
            return []

        # -- 收集所有 OCR 行 --
        lines = []
        for item in result:
            if len(item) != 3:
                continue
            box, text, score = item
            if not isinstance(text, str):
                continue
            text = text.strip().rstrip('!?.,;:\'"\\')
            if not text:
                continue
            box = self._scale_box(box, scale)
            lines.append((text, box))

        raw_texts = [t for t, _ in lines]
        print(f"[OCR-RAW] 全部 {len(raw_texts)} 行: {raw_texts}", flush=True)

        if not lines:
            return []

        slots = self._group_by_slot(lines)
        print(f"[OCR-SLOTS] 识别到 {len(slots)} 个格子", flush=True)

        results = self._process_slots(slots)

        elapsed = (time.perf_counter() - t0) * 1000
        names = [r[0] for r in results]
        print(f"[OCR-RESULT] 最终 {len(results)} 个物品: {names} (耗时={elapsed:.0f}ms)", flush=True)
        return results

    @staticmethod
    def _process_slots(
        slots: list[tuple[list[str], list]]
    ) -> list[tuple[str, list, list[str]]]:
        """处理位置分组的结果（提取特征词、翻译等）。"""
        results = []
        for idx, (slot_texts, slot_box) in enumerate(slots):
            if not slot_texts:
                continue

            print(f"\n{'─'*50}", flush=True)
            print(f"[OCR-PROCESS][格子{idx+1}] ── 开始处理 ──", flush=True)
            print(f"[OCR-PROCESS][格子{idx+1}] 原始文本行: {slot_texts}", flush=True)

            if len(slot_texts) == 1:
                slot_text = slot_texts[0]
            else:
                slot_text = ' '.join(slot_texts)
                slot_text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', slot_text)

            print(f"[OCR-PROCESS][格子{idx+1}] 合并后文本: \"{slot_text}\"", flush=True)

            en_name, features = _extract_features(slot_text)
            print(f"[OCR-PROCESS][格子{idx+1}] 提取特有名: \"{en_name}\"", flush=True)
            print(f"[OCR-PROCESS][格子{idx+1}] 提取特征词: {features}", flush=True)

            translation_failed = False
            if en_name and re.search(r'[\u4e00-\u9fff]', en_name):
                translated = _translate_cn_unique_name(en_name)
                if translated:
                    # ★ 永远不要翻译成 Set（套装）
                    if translated.endswith(' Set'):
                        print(f"[OCR-PROCESS][格子{idx+1}] 翻译特有名: \"{en_name}\" → \"{translated}\" (排除套装)", flush=True)
                        translation_failed = True
                    else:
                        print(f"[OCR-PROCESS][格子{idx+1}] 翻译特有名: \"{en_name}\" → \"{translated}\"", flush=True)
                        en_name = translated
                else:
                    print(f"[OCR-PROCESS][格子{idx+1}] 翻译特有名: \"{en_name}\" → 翻译失败!", flush=True)
                    translation_failed = True

            # ★ 自动补全 Prime：OCR 可能漏掉 "Prime" 字样
            #    当物品名是 Prime-only 基础名（如 Ash）且 features 中没有 Prime 时，
            #    自动在 features 最前面插入 "Prime"
            if en_name and 'Prime' not in features and _is_prime_only_base(en_name):
                features.insert(0, 'Prime')
                print(f"[OCR-PROCESS][格子{idx+1}] 自动补全 Prime → 特征词: {features}", flush=True)

            if en_name:
                assembled = ' '.join([en_name] + features)
            else:
                assembled = ' '.join(features)

            # ★ 如果翻译失败且 assembled 仍含中文，尝试对整个 assembled 做模糊搜索
            if translation_failed and re.search(r'[\u4e00-\u9fff]', assembled):
                fuzzy_full = _fuzzy_search_cn_in_db(slot_text)
                if fuzzy_full:
                    print(f"[OCR-PROCESS][格子{idx+1}] 整体模糊搜索: \"{slot_text}\" → \"{fuzzy_full}\"", flush=True)
                    assembled = fuzzy_full
                    # 重新提取特有名（用纠正后的纯英文结果）
                    en_name, features = _extract_features(fuzzy_full)
                    if en_name:
                        assembled = ' '.join([en_name] + features)

            print(f"[OCR-PROCESS][格子{idx+1}] 最终拼接: \"{assembled}\"", flush=True)

            variants = ItemNameRecognizer._fix_ocr_confusions(en_name) if en_name else []
            print(f"[OCR-PROCESS][格子{idx+1}] OCR纠错候选(特有名): {variants}", flush=True)
            # ★ 也生成完整拼接的纠正版本（特征词不变，只纠正特有名部分）
            assembled_variants = []
            for v in variants:
                if v != en_name:
                    assembled_variants.append(' '.join([v] + features))
            if assembled_variants:
                print(f"[OCR-PROCESS][格子{idx+1}] OCR纠错候选(完整): {assembled_variants}", flush=True)

            all_variants = variants + assembled_variants
            print(f"[OCR-PROCESS][格子{idx+1}] 最终结果: \"{assembled}\" | 候选: {all_variants}", flush=True)

            results.append((assembled, slot_box, all_variants))

        return results

    def _group_by_slot(
        self, lines: list[tuple[str, list]]
    ) -> list[tuple[list[str], list]]:
        """按格子（位置）分组：2D 网格聚类。

        策略：
          1. 按 y 坐标将所有 OCR 行分组到"水平行"(rows)
          2. 每个 row 内按 x 坐标分割成"列"(columns)
          3. 跨 row 合并同列索引的文本到同一个 slot

        这样从根本上解决了水平相邻物品分不开的问题：
        即使两个物品在 x 方向上非常接近，只要它们在不同列
        （由 y 行内的 x 间距决定），就能正确分开。
        """
        if not lines:
            return []
        if len(lines) == 1:
            return [([lines[0][0]], lines[0][1])]

        def _center_x(box):
            xs = [p[0] for p in box]
            return sum(xs) / len(xs)

        def _center_y(box):
            ys = [p[1] for p in box]
            return sum(ys) / len(ys)

        def _width(box):
            xs = [p[0] for p in box]
            return max(xs) - min(xs)

        def _height(box):
            ys = [p[1] for p in box]
            return max(ys) - min(ys)

        # ============================================================
        # Step 1: 按 y 坐标分"水平行" (rows)
        # ============================================================
        y_sorted = sorted(lines, key=lambda l: _center_y(l[1]))
        y_centers = [_center_y(b) for _, b in y_sorted]
        heights = [_height(b) for _, b in y_sorted]
        avg_height = sum(heights) / len(heights) if heights else 0

        # 计算 y 方向间距，找行边界
        y_gaps = [y_centers[i+1] - y_centers[i] for i in range(len(y_centers)-1)]
        # 行间距阈值：显著大于行高的一半（同一物品内的文本垂直间距通常很小）
        y_threshold = avg_height * 1.0

        rows = []  # list[list[(text, box)]]
        current_row = [y_sorted[0]]
        for i, gap in enumerate(y_gaps):
            if gap > y_threshold:
                rows.append(current_row)
                current_row = [y_sorted[i+1]]
            else:
                current_row.append(y_sorted[i+1])
        rows.append(current_row)

        # 每个 row 内部按 x 排序
        for row in rows:
            row.sort(key=lambda l: _center_x(l[1]))

        print(f"[OCR-GROUP] y方向分 {len(rows)} 行: 每行{['/'.join(t for t,_ in r) for r in rows]}", flush=True)

        # ============================================================
        # Step 2: 在每个 row 内按 x 坐标分"列" (columns)
        # ============================================================
        # 收集所有 row 的列边界（x 坐标的分界点），取并集作为全局列边界
        all_split_xs = []  # 所有行内 x 分界点的 x 坐标

        for row in rows:
            if len(row) <= 1:
                continue
            centers = [_center_x(b) for _, b in row]
            widths = [_width(b) for _, b in row]
            gaps = [centers[i+1] - centers[i] for i in range(len(centers)-1)]
            avg_w = sum(widths) / len(widths) if widths else 0
            median_gap = sorted(gaps)[len(gaps)//2] if gaps else 0
            mean_gap = sum(gaps) / len(gaps) if gaps else 0

            # 列间距阈值：取平均宽度的倍数和间距统计值中最大的
            row_threshold = max(avg_w * 0.6, median_gap * 1.8, mean_gap * 1.3)

            for i, gap in enumerate(gaps):
                if gap > row_threshold:
                    # 分界点在 centers[i] 和 centers[i+1] 之间
                    split_x = (centers[i] + centers[i+1]) / 2
                    all_split_xs.append(split_x)
                    print(f"[OCR-GROUP] 行内分界: x≈{split_x:.0f}, 间距={gap:.0f} > 阈值={row_threshold:.0f}", flush=True)

        # 合并相近的列边界（容差 = 平均宽度 * 0.5）
        all_split_xs.sort()
        merged_splits = []
        if all_split_xs:
            avg_w = sum(_width(b) for _, b in lines) / len(lines)
            merge_tolerance = avg_w * 0.5
            for sx in all_split_xs:
                if not merged_splits or sx - merged_splits[-1] > merge_tolerance:
                    merged_splits.append(sx)

        # 如果没有找到自然分界点但有多行文本，强制检测列数
        if not merged_splits:
            total_texts = sum(len(row) for row in rows)
            if total_texts >= 4 and len(rows) >= 2:
                # 统计每行的文本数，取众数作为列数
                row_counts = [len(row) for row in rows]
                from collections import Counter
                col_count = Counter(row_counts).most_common(1)[0][0]
                if col_count >= 2:
                    # 按 x 全局排序，取 (col_count-1) 个最大间距
                    all_x_sorted = sorted(lines, key=lambda l: _center_x(l[1]))
                    all_centers = [_center_x(b) for _, b in all_x_sorted]
                    all_gaps = [(all_centers[i+1] - all_centers[i], i)
                                for i in range(len(all_centers)-1)]
                    all_gaps.sort(key=lambda x: x[0], reverse=True)
                    avg_w = sum(_width(b) for _, b in lines) / len(lines)
                    print(f"[OCR-GROUP] 无自然列分界，根据行众数={col_count}强制分列", flush=True)
                    forced = []
                    for gap, idx in all_gaps[:col_count - 1]:
                        if gap > avg_w * 0.25:
                            sx = (all_centers[idx] + all_centers[idx+1]) / 2
                            forced.append(sx)
                            print(f"[OCR-GROUP] 强制列分界: x≈{sx:.0f}, 间距={gap:.0f}", flush=True)
                    merged_splits = sorted(forced)

        print(f"[OCR-GROUP] 全局列边界: {['%.0f' % s for s in merged_splits]}", flush=True)

        # ============================================================
        # Step 3: 用全局列边界把每个 row 的文本分配到列
        # ============================================================
        num_cols = len(merged_splits) + 1
        # columns[j] = 所有 row 中属于第 j 列的文本行列表
        columns = [[] for _ in range(num_cols)]

        for row in rows:
            for text, box in row:
                cx = _center_x(box)
                # 找到 cx 所在的列
                col_idx = 0
                for si, sx in enumerate(merged_splits):
                    if cx > sx:
                        col_idx = si + 1
                    else:
                        break
                columns[col_idx].append((text, box))

        # ============================================================
        # Step 4: 构建 slot 结果（每列 = 一个 slot）
        # ============================================================
        slots = []
        for col_items in columns:
            if not col_items:
                continue
            # 按 y 排序，确保同一 slot 内的文本从上到下排列
            col_items.sort(key=lambda l: _center_y(l[1]))
            texts = [t for t, _ in col_items]
            boxes = [b for _, b in col_items]
            merged_box = self._merge_all_boxes(boxes)
            slots.append((texts, merged_box))

        print(f"[OCR-GROUP] 最终分 {len(slots)} 组: {[g[0] for g in slots]}", flush=True)
        return slots

    @staticmethod
    def _merge_all_boxes(boxes: list[list]) -> list:
        """合并多个包围框为一个外接矩形。"""
        xs = [p[0] for box in boxes for p in box]
        ys = [p[1] for box in boxes for p in box]
        return [[min(xs), min(ys)], [max(xs), min(ys)],
                [max(xs), max(ys)], [min(xs), max(ys)]]


# ============================================================
# 向后兼容：重导出匹配函数
# ============================================================

from recognizers.matcher import match_and_price, match_and_translate  # noqa: E402, F401
