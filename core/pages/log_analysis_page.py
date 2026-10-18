"""
[L2] LogAnalysisPage — 游戏日志分析页面

依赖: widgets/ (card, button), services/ (log_parser_service)
职责: 解析 Warframe 客户端日志(EE.log),展示最新战斗详情 + 完成任务记录

展示内容:
  - 顶部: 日志文件选择 + 解析按钮
  - 最近一场战斗(核心展示): 类型/节点/时长/派系/倒地/队员(带段位)
  - 完成任务记录列表: 任务类型 | 时长 | 队员(带段位)

## AI 硬约束
归属层:    [L2] (core/pages/)
允许依赖:  core.widgets/*, core.services/*(读), PySide6
禁止依赖:  core.tokens/* 直接调用(只能间接), 任何反向依赖 widgets
必读规范:  .trae/rules/开发规范.md §6.5

红线:
- ✗ 禁止 setStyleSheet(f"...") → 必须用 Token 或继承自 CyberWidget
- ✗ 禁止重写 paintEvent → 视觉交给 Widget
- ✗ 禁止业务逻辑在 Page 内实现 → 走 LogParserService
- ✗ 禁止硬编码颜色 / 尺寸 → 必须 token / space
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QFileDialog, QScrollArea,
)
from PySide6.QtCore import Qt, QThread, QCoreApplication, Signal as QtSignal
from PySide6.QtGui import QFont

from core.pages.base_page import PageBase
from core.widgets.card import CyberCard
from core.widgets.button import CyberButton
from core.services.log_parser_service import (
    LogParserService, LogAnalysisResult, ParseCancelled,
)


# ── 日志解析工作线程(避免 25MB 日志阻塞 UI) ──
class _ParseWorker(QThread):
    """后台解析日志线程。

    信号:
        parse_finished(object): 解析完成（LogAnalysisResult | None）
        cancelled():            被主动取消（程序退出时）

    注意：**不覆写 QThread 内置的 finished 信号**。重名会遮蔽 Qt 自己
    "线程已结束" 的信号，让「线程结束」与「拿到结果」两件事语义混淆。
    """
    parse_finished = QtSignal(object)
    cancelled = QtSignal()

    def __init__(self, log_path: str, parent=None):
        super().__init__(parent)
        self._log_path = log_path
        self._cancel_event = threading.Event()
        # 应用退出时先置取消标志，让 run() 在检查点尽快返回；
        # worker 销毁时 Qt 会自动断开该连接。
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.cancel)

    def cancel(self) -> None:
        """请求中止解析（线程安全，可从主线程调用）。"""
        self._cancel_event.set()

    def run(self):
        try:
            result = LogParserService.parse(
                self._log_path,
                should_cancel=self._cancel_event.is_set,
            )
        except ParseCancelled:
            self.cancelled.emit()
            return
        except Exception:
            # parse() 内部已记录堆栈；这里兜底，避免异常冒泡到 Qt 线程边界
            result = None
        self.parse_finished.emit(result)


class LogAnalysisPage(PageBase):
    """游戏日志分析页面(page_id='log_analysis')。"""

    page_id = "log_analysis"
    page_title = ""  # 由 nav token 动态获取
    page_icon = "nav_log"

    def __init__(self):
        # 必须在 super().__init__() 之前设置(build_content 会在基类 __init__ 中调用)
        self._result: LogAnalysisResult | None = None
        self._worker: _ParseWorker | None = None
        # 默认日志路径: %LOCALAPPDATA%\Warframe\EE.log(Warframe 客户端默认日志位置)
        local_app = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        self._default_log_path = str(Path(local_app) / "Warframe" / "EE.log")
        self._current_log_path = self._default_log_path

        super().__init__()
        self.page_title = self._copy("nav.log_analysis", "日志分析")

    # ── 生命周期 ──

    def on_enter(self) -> None:
        """页面进入时,若已有结果则刷新;否则尝试解析默认日志。"""
        super().on_enter()
        if self._result is None:
            self._auto_parse()

    # ══════════════════════════════════
    #  页面构建
    # ══════════════════════════════════

    def build_content(self) -> QWidget:
        """构建日志分析页主内容。

        页面结构(精简版):
          1. 顶部工具栏(文件选择 + 解析按钮)
          2. 最近一场战斗(大卡片,详细信息)
          3. 完成任务记录列表(类型/时间/人员)
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)

        # ── 标题 + 文件选择 ──
        layout.addWidget(self._build_header())

        # ── 最近一场战斗(最新任务)详情卡片(核心展示) ──
        self._latest_card = CyberCard(title="最近一场战斗")
        self._latest_layout = self._latest_card.content_layout()
        self._latest_layout.setContentsMargins(24, 20, 24, 20)
        self._latest_layout.setSpacing(self._spacing("md", 12))
        layout.addWidget(self._latest_card)

        # ── 完成任务记录列表 ──
        layout.addWidget(self._build_mission_list_card())

        layout.addStretch()

        # 初始渲染空状态
        self._render_empty()

        return container

    def _build_header(self) -> QWidget:
        """构建标题 + 文件选择工具栏。"""
        card = CyberCard()
        layout = card.content_layout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(self._spacing("md", 12))

        # 标题
        title = QLabel("游戏日志分析")
        title.setFont(QFont("Iceberg", self._font_size("lg", 16)))
        self._style(title, color="accent.primary")
        layout.addWidget(title)

        # 文件路径 + 按钮行
        row = QHBoxLayout()
        row.setSpacing(self._spacing("md", 12))

        self._path_label = QLabel(self._current_log_path)
        self._style(self._path_label, color="text.secondary")
        self._path_label.setWordWrap(True)
        row.addWidget(self._path_label, stretch=1)

        select_btn = CyberButton(text="选择日志", variant="outlined")
        select_btn.clicked.connect(self._on_select_file)
        row.addWidget(select_btn)

        parse_btn = CyberButton(text="解析日志", variant="solid")
        parse_btn.clicked.connect(self._on_parse)
        row.addWidget(parse_btn)

        layout.addLayout(row)

        # 解析状态
        self._status_label = QLabel("等待解析...")
        self._style(self._status_label, color="text.tertiary", font_size="micro")
        layout.addWidget(self._status_label)

        return card

    def _build_mission_list_card(self) -> QWidget:
        """构建完成任务记录列表卡片(可滚动)。"""
        card = CyberCard(title="完成任务记录")
        layout = card.content_layout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(self._spacing("sm", 8))

        self._mission_list = QFrame()
        self._mission_list_layout = QVBoxLayout(self._mission_list)
        self._mission_list_layout.setSpacing(self._spacing("xs", 4))
        self._mission_list_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(360)
        self._style(scroll, transparent=True)
        scroll.setWidget(self._mission_list)
        layout.addWidget(scroll)

        return card

    # ══════════════════════════════════
    #  事件处理
    # ══════════════════════════════════

    def _on_select_file(self):
        """打开文件选择对话框选择 EE.log。"""
        current = Path(self._current_log_path)
        start_dir = str(current.parent) if current.exists() else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择游戏日志文件 (EE.log)",
            start_dir,
            "Log Files (*.log);;All Files (*)",
        )
        if file_path:
            self._current_log_path = file_path
            self._path_label.setText(file_path)

    def _on_parse(self):
        """用户点击解析按钮。"""
        self._start_parse(self._current_log_path)

    def _auto_parse(self):
        """自动解析默认日志(若存在)。"""
        if Path(self._default_log_path).exists():
            self._current_log_path = self._default_log_path
            self._path_label.setText(self._default_log_path)
            self._start_parse(self._default_log_path)

    def _start_parse(self, log_path: str):
        """启动后台解析线程。

        worker 以本页为 parent：页面销毁时 Qt 一并回收，避免悬空线程对象；
        结束回调里显式置空引用，否则下次 isRunning() 会访问已释放对象。
        """
        if self._worker is not None and self._worker.isRunning():
            return
        self._status_label.setText("正在解析日志,请稍候...")
        self._worker = _ParseWorker(log_path, self)
        self._worker.parse_finished.connect(self._on_parse_finished)
        self._worker.parse_finished.connect(self._on_worker_finished)
        self._worker.cancelled.connect(self._on_parse_cancelled)
        self._worker.cancelled.connect(self._on_worker_finished)
        self._worker.start()

    def _on_parse_cancelled(self):
        """解析被主动取消（通常是程序退出）：不提示失败。"""
        self._status_label.setText("解析已取消")

    def _on_worker_finished(self, _result=None):
        """线程结束后释放 worker 引用（对象本身由 deleteLater 回收）。"""
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()

    def _on_parse_finished(self, result: LogAnalysisResult | None):
        """解析完成回调。"""
        if result is None:
            self._status_label.setText("解析失败:文件不存在或格式错误")
            self._render_empty()
            return
        self._result = result
        self._status_label.setText(
            f"解析完成 · {result.total_missions} 个任务 · "
            f"{result.log_size_mb}MB · 耗时 {result.parse_seconds}s"
        )
        self._render_result(result)

    # ══════════════════════════════════
    #  渲染
    # ══════════════════════════════════

    def _render_empty(self):
        """渲染空状态(无数据)。"""
        # 清空最新任务卡片
        self._clear_layout(self._latest_layout)
        empty_hint = QLabel("暂无任务数据")
        self._style(empty_hint, color="text.tertiary", font_size="sm")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._latest_layout.addWidget(empty_hint)
        # 清空任务列表
        self._clear_layout(self._mission_list_layout)
        hint = QLabel("选择 EE.log 文件并点击「解析日志」开始分析")
        self._style(hint, color="text.tertiary")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mission_list_layout.addWidget(hint)

    def _render_result(self, r: LogAnalysisResult):
        """渲染分析结果:最新战斗详情 + 完成任务列表。"""
        # ── 最近一场战斗(最新任务) ──
        self._clear_layout(self._latest_layout)
        if r.missions:
            self._render_latest_mission(r.missions[-1])

        # ── 完成任务列表(只展示已完成的,排除进行中的) ──
        self._clear_layout(self._mission_list_layout)
        completed = [m for m in r.missions if not m.is_ongoing]
        for m in reversed(completed):  # 最新完成的在最上面
            self._mission_list_layout.addWidget(self._build_mission_row(m))
        if not completed:
            hint = QLabel("暂无已完成的任务记录")
            self._style(hint, color="text.tertiary")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._mission_list_layout.addWidget(hint)

    def _render_latest_mission(self, m) -> None:
        """渲染「最近一场战斗」卡片 — 最后一个任务的详情(核心展示)。"""
        lay = self._latest_layout

        # ── 第一行: 任务类型(大字) + 状态标记 ──
        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        type_text = m.mission_type_name
        type_lbl = QLabel(type_text)
        type_lbl.setFont(QFont("Iceberg", self._font_size("xl", 20)))
        self._style(type_lbl, color="accent.primary")
        title_row.addWidget(type_lbl)

        # 钢铁之路 / 裂缝纪元 标签
        if m.is_steel_path:
            sp_lbl = QLabel("钢铁之路")
            self._style(sp_lbl, color="alias.accent.tertiary", font_size="sm")
            title_row.addWidget(sp_lbl)
        if m.is_void_fissure:
            fissure_lbl = QLabel(f"{m.void_tier_name}裂缝")
            self._style(fissure_lbl, color="accent.secondary", font_size="sm")
            title_row.addWidget(fissure_lbl)

        # 进行中 / 结果
        if m.is_ongoing:
            status_text = "● 进行中"
            status_color = "accent.secondary"
        elif m.success:
            status_text = "✓ 已完成"
            status_color = "accent.secondary"
        else:
            status_text = "✗ 失败"
            status_color = "text.tertiary"
        status_lbl = QLabel(status_text)
        self._style(status_lbl, color=status_color, font_size="sm")
        title_row.addWidget(status_lbl)
        title_row.addStretch()
        lay.addLayout(title_row)

        # ── 第二行: 节点名 ──
        node_lbl = QLabel(m.node_name)
        self._style(node_lbl, color="text.primary", font_size="md")
        lay.addWidget(node_lbl)

        # ── 第三行: 时长(大字突出) ──
        dur_row = QHBoxLayout()
        dur_row.setSpacing(16)
        dur_text = f"{m.duration_min:g} 分钟"
        dur_lbl = QLabel(dur_text)
        dur_lbl.setFont(QFont("Iceberg", self._font_size("lg_xl", 22)))
        self._style(dur_lbl, color="accent.primary")
        dur_row.addWidget(dur_lbl)
        dur_row.addStretch()
        lay.addLayout(dur_row)

        # ── 第四行: 标签信息(派系/倒地) ──
        tags = [
            ("派系", m.enemy_name or "未知"),
            ("倒地", str(m.downed_count)),
        ]
        tag_row = QHBoxLayout()
        tag_row.setSpacing(24)
        for label, value in tags:
            tag_row.addWidget(self._info_item(label, value))
        tag_row.addStretch()
        lay.addLayout(tag_row)

        # ── 第五行: 组队成员 ──
        if m.squad_members:
            squad_text = "组队成员: " + "   ·   ".join(m.squad_members)
        else:
            squad_text = "组队成员: 单人"
        squad_lbl = QLabel(squad_text)
        self._style(squad_lbl, color="text.tertiary", font_size="xs")
        squad_lbl.setWordWrap(True)
        lay.addWidget(squad_lbl)

    def _info_item(self, label: str, value: str) -> QWidget:
        """构建一个「标签: 值」的紧凑信息块。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(self._spacing("sm", 8))
        lbl = QLabel(f"{label}:")
        self._style(lbl, color="text.tertiary", font_size="sm")
        val = QLabel(value)
        self._style(val, color="text.primary", font_size="sm")
        h.addWidget(lbl)
        h.addWidget(val)
        return w

    def _build_mission_row(self, m) -> QWidget:
        """构建单条完成任务记录行: 任务类型 | 时长 | 人员。"""
        row = QFrame()
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(12, 8, 12, 8)
        row_lay.setSpacing(16)

        # ── 任务类型(带钢铁/裂缝标记) ──
        type_text = m.mission_type_name
        tags = []
        if m.is_steel_path:
            tags.append("钢铁")
        if m.is_void_fissure:
            tags.append(m.void_tier_name)
        if tags:
            type_text += f" [{'+'.join(tags)}]"
        type_lbl = QLabel(type_text)
        self._style(type_lbl, color="accent.secondary", font_size="sm")
        type_lbl.setFixedWidth(120)
        row_lay.addWidget(type_lbl)

        # ── 时长(时间) ──
        dur_lbl = QLabel(f"{m.duration_min:g} 分钟")
        self._style(dur_lbl, color="text.primary", font_size="sm")
        dur_lbl.setFixedWidth(92)
        row_lay.addWidget(dur_lbl)

        # ── 人员(队员) ──
        if m.squad_members:
            squad_text = "  ·  ".join(m.squad_members)
        else:
            squad_text = "单人"
        squad_lbl = QLabel(squad_text)
        self._style(squad_lbl, color="text.tertiary", font_size="sm")
        squad_lbl.setWordWrap(True)
        row_lay.addWidget(squad_lbl, stretch=1)

        return row

    # ── 工具 ──

    @staticmethod
    def _clear_layout(layout):
        """清空布局内所有 widget。"""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                LogAnalysisPage._clear_layout(item.layout())
