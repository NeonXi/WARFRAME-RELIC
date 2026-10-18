"""
[L-Service] core.mode_handlers — 截图功能模式处理器

从 AppCore 拆分出来的功能处理逻辑(纯函数式),无状态。

职责:
- 出入库状态查询 (handle_check_status)
- 遗物内容查询 (handle_query_parts)
- 中文→英文部件名映射 (_get_merged_cn_to_en, _translate_cn_to_en)

依赖: Python 标准库 + data/ 模块 + core.constants + core.annotation(纯数据类)
禁止: PySide6 / QtWidgets / QtGui (Signal 除外)
被谁用: core.services.screenshot_pipeline.py (作为回调)

## AI 硬约束 — 修改本文件前必读
归属层:    [L-Service] (core/ 根目录,跨层桥接/全局管理器)
允许依赖:  视文件而定(本层可持有 widget 引用作桥接,但不实现绘制)
禁止依赖:  根目录 .py 不允许做业务实现 → 业务放 core/services/
必读规范:  .trae/rules/开发规范.md §6.2

本文件相关红线:
- 禁止根目录 .py 持有 widget 绘制逻辑 → 视觉交给 core/widgets/
- 禁止硬编码资源路径 → 必须 core.constants 取
- 禁止在根目录定义业务类 → 业务放对应层
- 禁止反向调用 UI(从 Service → Widget) → 单向数据流
- 禁止 try/except: pass 吞错 → 必须记录到日志或抛给上层

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.2,别走捷径。
"""

from typing import Optional
from pathlib import Path
from core.constants import (
    COLOR_VAULTED, COLOR_AVAILABLE, COLOR_UNKNOWN,
    COLOR_GOLD, COLOR_SILVER, COLOR_COPPER, FALLBACK_COLOR,
)
from core.annotation import Annotation
from data.ui_strings import S


# ---- 精炼标签过滤正则 ----
import re

_REFINEMENT_RE = re.compile(
    r'\s*[\[(（【]?\s*(完好|优良|优异|无瑕|卓越|光辉|INTACT|EXCEPTIONAL|FLAWLESS|RADIANT)\s*[\])）】]?\s*$',
    re.IGNORECASE
)


def strip_refinement(name: str) -> str:
    """去除遗物名称末尾的精炼标签，返回基础名称。"""
    return _REFINEMENT_RE.sub('', name).strip()


# ================================================================
# 出入库状态查询
# ================================================================

def handle_check_status(last_relics, relic_db, last_region, dpi, overlay):
    """出入库查询：识别遗物 → 标注出入库状态。"""
    annotations = []

    for name, box in last_relics:
        base_name = strip_refinement(name)
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)
        info = relic_db.find(base_name)
        if info:
            if info.get('vaulted', False):
                color, label = COLOR_VAULTED, f"{base_name} [{S('overlay', 'relic_vaulted')}]"
            else:
                color, label = COLOR_AVAILABLE, f"{base_name} [{S('overlay', 'relic_available')}]"
        else:
            color, label = COLOR_UNKNOWN, S.format("overlay", "relic_no_parts_info", name=base_name)
        annotations.append(Annotation.create(label, sx, sy, duration_ms=8000, color=color))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=8000, interval_ms=30, batch_size=2)
    overlay.display(
        S.format("overlay", "annotations_shown", count=len(annotations)), auto_hide_ms=5000)


# ================================================================
# 遗物内容查询
# ================================================================

def handle_query_parts(last_relics, relic_db, last_region, dpi, overlay):
    """遗物内容查询：匹配遗物内容 → 标注掉落物品 + 稀有度颜色。"""
    annotations = []
    matched = 0
    unmatched_names = []

    for name, box in last_relics:
        base_name = strip_refinement(name)
        sx = int(last_region[0] + box[0][0] / dpi)
        sy = int(last_region[1] + box[0][1] / dpi - 28)
        info = relic_db.find(base_name)
        if not info:
            unmatched_names.append(base_name)
            annotations.append(
                Annotation.create(S.format("overlay", "relic_no_parts_info", name=base_name),
                                  sx, sy, duration_ms=10000, color=FALLBACK_COLOR))
            continue

        matched += 1
        parts = info.get('parts', [])
        vaulted = info.get('vaulted', False)
        status_color = COLOR_VAULTED if vaulted else COLOR_AVAILABLE
        status = S("overlay", "relic_vaulted") if vaulted else S("overlay", "relic_available")

        lines = [f"{base_name} [{status}]"]
        line_colors = [status_color]
        sorted_parts = sorted(parts, key=lambda p: p.get('chance', 0))
        chances = sorted(set(p.get('chance', 0) for p in sorted_parts))
        extra_lines, extra_colors = _map_rarity_colors(chances, sorted_parts)
        lines.extend(extra_lines)
        line_colors.extend(extra_colors)
        label = "\n".join(lines)
        annotations.append(Annotation.create(label, sx, sy, duration_ms=10000, color=status_color, line_colors=line_colors))

    overlay.show_annotations_stream(
        annotations, auto_hide_ms=10000, interval_ms=35, batch_size=1)

    return matched, len(last_relics), unmatched_names


def _map_rarity_colors(chances, sorted_parts):
    """根据概率排名分配稀有度颜色。"""
    if len(chances) >= 3:
        chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_SILVER, chances[2]: COLOR_COPPER}
    elif len(chances) == 2:
        chance_to_color = {chances[0]: COLOR_GOLD, chances[1]: COLOR_COPPER}
    else:
        chance_to_color = {chances[0]: COLOR_SILVER}

    lines, colors = [], []
    for p in sorted_parts:
        ch = p.get('chance', 0)
        clr = chance_to_color.get(ch, COLOR_SILVER)
        prefix = "●" if ch == chances[0] else ("◦" if len(chances) > 1 and ch == chances[-1] else "◈")
        lines.append(f"  {prefix} {p['name']}")
        colors.append(clr)
    return lines, colors


# ================================================================
# 中文→英文部件名映射（反向自 data/wfinfo_relics._PRIME_PART_SUFFIXES）
# ================================================================
#  部件后缀字典（DB 驱动 + 手动补充）
#  用途: 空格修复时识别已知部件名 / 中文→英文翻译
# ================================================================

def _load_part_suffix_dict() -> dict[str, str]:
    """从 game_translations 表加载 Prime 部件后缀的 {中文:英文} 映射。

    数据源: game_translations 表中 relic_rewards.item_name 出现过的部件后缀。
    运行时只查一次，结果缓存为模块级变量。
    """
    import sqlite3
    db_path = _find_db_path()
    if not db_path:
        return {}

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT item_name FROM relic_rewards WHERE item_name != ''"
        ).fetchall()
        en_names = [r[0] for r in rows]
        if not en_names:
            return {}

        placeholders = ','.join('?' * len(en_names))
        gt_rows = conn.execute(
            f"SELECT en, zh FROM game_translations WHERE en IN ({placeholders})",
            en_names,
        ).fetchall()

        result: dict[str, str] = {}
        for en, zh in gt_rows:
            # 提取 "Prime" 之后的部分作为部件后缀
            # "Acceltra Prime Barrel" → "Barrel"
            # "Titania Prime Neuroptics Blueprint" → "Neuroptics Blueprint"
            prime_idx = en.find(' Prime ')
            if prime_idx >= 0:
                suffix_en = en[prime_idx + 7:]  # 跳过 " Prime "
                result[zh] = suffix_en

                # 拆分复合后缀注册子串（启发式按字符数比例）
                sub_parts = suffix_en.split()
                if len(sub_parts) >= 2:
                    for i, sub_en in enumerate(sub_parts):
                        ratio = len(sub_en) / max(len(suffix_en), 1)
                        zh_start = int(len(zh) * sum(len(sub_parts[j]) for j in range(i)) / len(suffix_en))
                        zh_end = zh_start + int(len(zh) * ratio)
                        if 0 <= zh_start < zh_end <= len(zh):
                            sub_zh = zh[zh_start:zh_end]
                            if sub_zh and sub_zh not in result:
                                result[sub_zh] = sub_en
        return result
    finally:
        conn.close()


_part_suffix_cache: dict[str, str] | None = None


def _get_part_suffixes() -> dict[str, str]:
    """获取部件后缀字典（懒加载单例）。"""
    global _part_suffix_cache
    if _part_suffix_cache is None:
        _part_suffix_cache = _load_part_suffix_dict()
    return _part_suffix_cache


# ── 手动补充的部件映射（DB 未覆盖或需覆盖的场景）──
_CN_TO_EN_PARTS: dict[str, str] = {
    '头部神经光元蓝图': 'Neuroptics Blueprint',
    '机体蓝图':     'Chassis Blueprint',
    '系统蓝图':     'Systems Blueprint',
    '蓝图':         'Blueprint',
    '系统':         'Systems',
    '机体':         'Chassis',
    '头部神经光元':  'Neuroptics',
    '头部':         'Cerebrum',
    '外壳':         'Carapace',
    '枪管':         'Barrel',
    '枪机':         'Receiver',
    '枪托':         'Stock',
    '连接器':       'Link',
    '握柄':         'Handle',
    '刀刃':         'Blade',
    '爪刃':         'Blades',
    '拳套':         'Gauntlet',
    '手套':         'Gauntlet',
    '饰物':         'Ornament',
    '锤头':         'Head',
    '弓身':         'Grip',
    '弓弦':         'String',
    '弹袋':         'Pouch',
    '链刃':         'Chain',
}


def _get_merged_cn_to_en() -> dict[str, str]:
    """返回手动映射 + DB 驱动数据的合并字典（手动优先）。"""
    merged = dict(_CN_TO_EN_PARTS)
    for cn, en in _get_part_suffixes().items():
        if cn not in merged:
            merged[cn] = en
    return merged

# ── 中文名称 → 英文名称（Prime 战甲/武器本体）──
# 这些是游戏中文本地化的 Prime 角色名，OCR 可能识别出中文名
_CN_TO_EN_NAMES: dict[str, str] = {
    # 战甲 (Warframes)
    '陨蜓':       'Caliban',
    '灰烬':       'Ash',
    '阿特拉斯':   'Atlas',
    '班恩':       'Banshee',
    '牛甲':       'Rhino',
    '伏特':       'Volt',
    '喵喵板':     'Valkyr',
    '核热':       'Frost',
    '磁妹':       'Mag',
    '圣剑':       'Excalibur',
    '超能新星':   'Nova',
    '小丑':       'Loki',
    '奶妈':       'Trinity',
    '猴子':       'Wukong',
    '沙甲':       'Inaros',
    '水雷':       'Harrow',
    '玻璃':       'Gara',
    '草泥马':     'Khora',
    '夜灵':       'Revenant',
    '永续':       'Garuda',
    '多边形':     'Baruuk',
    '哈丘':       'Hildryn',
    '赛德娜':     'Wisp',
    '夜幕':       'Xaku',
    '瑟图斯':     'Sevagoth',
    '圣装':       '',  # 前缀标记，不翻译
    '圣装 ':      '',
    # 武器 (Weapons) - 常见简称/译名
    '卡帕压力枪': 'Cappa',
    '阿克斯特莱托': 'Akstiletto',
    '布拉顿':     'Braton',
    '伯斯顿':     'Burston',
    '达克拉':     'Dakra',
    '加拉廷':     'Galatine',
    '格拉姆':     'Gram',
    '拉特龙':     'Latron',
    '雷克斯':     'Lex',
    '索玛':       'Soma',
    '塔苏':       'Tatsu',
    '托里德':     'Torid',
    '瓦斯托':     'Vasto',
    # 弓类 / 补充武器（OCR 常见中文名）
    '大久和弓':   'Daikyu',
    '巴黎':       'Paris',
    '恐惧':       'Dread',
    '科林斯':     'Corinth',
    '拉特昂':     'Latron',      # OCR 变体: 拉特龙/拉特昂
}


def _translate_cn_to_en(text: str) -> str:
    """将 OCR 中文游戏 UI 文本中的中文部件名/角色名替换为英文。

    将中文 OCR 输出转换为接近 DB 英文名的格式，
    供识别管线后续匹配使用。

    Args:
        text: OCR 文本（建议先做空格修复）

    Returns:
        部分或全部翻译为英文的文本
    """
    if not text:
        return ''

    result = text

    # ★ 顺序关键：先翻译武器/战甲本体名，再翻译部件词
    # 原因: 部件词(如"弓""头""管")是武器名的子串，
    #       若先替换部件词，武器名("大久和弓")会被破坏

    # 1. 替换中文名称（角色/武器名）—— 先执行，保护长词完整性
    for cn, en in sorted(_CN_TO_EN_NAMES.items(), key=lambda x: -len(x[0])):
        if cn and en:
            result = result.replace(cn, en)
        elif cn and not en:
            result = result.replace(cn, '')

    # 2. 替换复合部件词（长词优先，使用 DB+手动合并字典）
    for cn, en in sorted(_get_merged_cn_to_en().items(), key=lambda x: -len(x[0])):
        result = result.replace(cn, en)

    # 3. ★ 修复翻译后英文单词粘连：在两个大写单词间补空格
    #    例: "CerebrumNeuroptics" → "Cerebrum Neuroptics"
    result = re.sub(r'([a-z])([A-Z])', r'\1 \2', result)

    # 4. 清理多余空格
    result = re.sub(r' {2,}', ' ', result).strip()

    return result

