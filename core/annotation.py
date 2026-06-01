"""
标注数据模型 — 强类型替代变长元组。

用法:
    from core.annotation import Annotation

    # 单行标注
    a = Annotation(text="Lith P1 [出库]", x=100, y=200, expire_ms=8000, color="#00FF00")

    # 多行标注（每行独立颜色）
    a = Annotation(text="Meso A2\n  ● Nekros Prime", x=100, y=200,
                   expire_ms=10000, color="#FFFF00",
                   line_colors=["#FFFF00", "#FFD700"])
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Annotation:
    """单条覆盖层标注。

    字段说明:
        text:       标注文本（支持 \\n 多行）
        x, y:       标注左上角逻辑坐标
        expire_ms:  过期时间戳（毫秒，int(time.time()*1000) + duration_ms）
        color:      默认文字颜色（单行时使用，多行时作为 fallback）
        line_colors: 多行文本的逐行颜色列表（可选，长度应与行数一致）
    """
    text: str
    x: int
    y: int
    expire_ms: int
    color: str
    line_colors: Optional[list[str]] = None

    def is_expired(self, now_ms: int) -> bool:
        """判断标注是否已过期。"""
        return self.expire_ms <= now_ms

    @property
    def line_count(self) -> int:
        """返回文本行数。"""
        return self.text.count('\n') + 1

    @property
    def is_multiline(self) -> bool:
        """是否为多行文本。"""
        return '\n' in self.text

    def get_line_color(self, index: int) -> str:
        """获取第 index 行的颜色（0-based），没有则回退到默认颜色。"""
        if self.line_colors and index < len(self.line_colors):
            return self.line_colors[index]
        return self.color

    @staticmethod
    def create(
        text: str,
        x: int,
        y: int,
        duration_ms: int = 5000,
        color: str = "#FFFF00",
        line_colors: Optional[list[str]] = None,
    ) -> Annotation:
        """工厂方法：从相对时长创建标注（自动计算绝对过期时间）。

        Args:
            text: 标注文本
            x, y: 坐标
            duration_ms: 显示时长（毫秒，从当前时间起算）
            color: 颜色
            line_colors: 多行逐行颜色
        """
        import time
        return Annotation(
            text=text,
            x=x,
            y=y,
            expire_ms=int(time.time() * 1000) + duration_ms,
            color=color,
            line_colors=line_colors,
        )
