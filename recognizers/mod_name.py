"""
Mod 名称识别器

从截图中识别英文 Mod 名称（可能跨行、窄字体），
通过 warframe.db 模糊匹配 → 翻译为中文。

重构后继承 BaseOCR，消除重复的 OCR 样板代码。
"""

import re
import time
import numpy as np

from recognizers.base_ocr import BaseOCR


class ModNameRecognizer(BaseOCR):
    """从截图中识别英文 Mod 名称并翻译为中文。"""

    # Mod 名特征：首字母大写英文词，长度合理（≥3字符）
    CANDIDATE_PATTERN = re.compile(r'^[A-Z][A-Za-z\-\'\.\s]{2,}$')

    TRASH_PATTERN = re.compile(
        r'^[xX]\d+$|'
        r'^\d+$|'
        r'^(RANK|RANK\s*\d+|MAX|MAXED)$|'
        r'^(DRAIN|COST|CAPACITY)\b|'
        r'^(POLARITY|AURA|STANCE)\b|'
        r'^(INTACT|EXCEPTIONAL|FLAWLESS|RADIANT)$|'
        r'^(OWNED|EQUIP|UPGRADE|FUSION|SOLD|SELL)\b|'
        r'^(CONFIG|LOADOUT|APPEARANCE)\b|'
        r'^(ALL|SEARCH|REFINEMENT|EXIT|VOID|RELICS)\b|'
        r'^[A-Z]$|^[A-Z]{1,2}$',
        re.IGNORECASE
    )

    RELIC_PATTERN = re.compile(
        r'(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s*[A-Za-z0-9]{2,3}\s*Relic',
        re.IGNORECASE
    )

    def _filter_text(self, text: str) -> bool:
        """过滤：排除垃圾、遗物名、非英文 Mod 名的行。"""
        if self.TRASH_PATTERN.match(text):
            return False
        if self.RELIC_PATTERN.search(text):
            return False
        return bool(self.CANDIDATE_PATTERN.match(text))

    # ---- 主识别流程 ----

    def recognize_all_with_boxes(self, image: np.ndarray) -> list[tuple[str, list]]:
        t0 = time.perf_counter()

        result, scale = self._run_ocr(image)
        if result is None:
            return []

        lines = self._iter_ocr_lines(result, scale)

        # 合并相邻行（Mod 名可能跨行，如 "Primed\nFlow"）
        merged = self.merge_adjacent_lines(lines)

        elapsed = (time.perf_counter() - t0) * 1000
        print(f"[Mod OCR] 原始行={len(lines)}, 合并后={len(merged)}, 耗时={elapsed:.0f}ms", flush=True)
        if merged:
            for text, _ in merged[:5]:
                print(f"  -> \"{text}\"", flush=True)
            if len(merged) > 5:
                print(f"  ... 还有 {len(merged) - 5} 个", flush=True)
        return merged


# ============================================================
# 翻译函数
# ============================================================

def _split_camel_case(text: str) -> str:
    """将驼峰粘连文本拆分为空格分隔。"""
    result = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return result


def translate_mods(recognized: list[tuple[str, list]]) -> list[dict]:
    """将识别到的英文 Mod 名翻译为中文。

    Args:
        recognized: [(en_name, box), ...]

    Returns:
        list[dict]: [{en_name, zh_name, box, match_quality, category}, ...]
    """
    if not recognized:
        return []

    from data.item_index import suggest_items

    results = []
    for en_name, box in recognized:
        search_name = _split_camel_case(en_name)
        if search_name != en_name:
            print(f"  [驼峰拆分] '{en_name}' -> '{search_name}'", flush=True)

        suggestions = suggest_items(search_name, limit=3)
        best = None

        sug_strs = [f"{s.get('en_name','?')}->{s.get('zh_name','?')}[{s.get('match_quality','?')}]"
                    for s in suggestions[:3]]
        print(f"  [翻译] \"{en_name}\" -> 建议: {sug_strs if sug_strs else '无'}", flush=True)

        # 优先精确匹配 Mod 分类
        for s in suggestions:
            if s.get('match_quality') == 'exact' and 'Mod' in s.get('category', ''):
                best = s
                break

        # 其次前缀匹配（限定 Mods 分类）
        if not best:
            for s in suggestions:
                if 'Mod' in s.get('category', ''):
                    best = s
                    break

        # 最后取第一个结果
        if not best and suggestions:
            best = suggestions[0]

        results.append({
            'en_name': en_name,
            'zh_name': best['zh_name'] if best else en_name,
            'category': best.get('category', '') if best else '',
            'match_quality': best.get('match_quality', 'none') if best else 'none',
            'box': box,
        })

    return results
