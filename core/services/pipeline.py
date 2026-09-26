"""
[L-Service] 数据更新流水线（新版本）

从 data/data_pipeline.py 迁移而来，统一使用 PySide6 信号。
提供 WFCD 源数据拉取 → warframe.db 构建的完整流水线。

用法:
    from core.services.pipeline import DataPipelineWorker
    worker = DataPipelineWorker()
    worker.step_changed.connect(...)
    worker.log.connect(...)
    worker.progress_pct.connect(...)
    worker.finished.connect(...)
    threading.Thread(target=worker.run, daemon=True).start()

## AI 硬约束 — 修改本文件前必读
归属层:    [L-Service] (core/services/)
允许依赖:  Python 标准库 + data/* + core.hotkey_config 等纯模块
禁止依赖:  PySide6 / QtWidgets / QtGui / QtCore(Signal 除外)
           core.widgets/* / core.pages/* / core.recognizers/*
必读规范:  .trae/rules/开发规范.md §6.2

本文件相关红线:
- 禁止 import PySide6 → Service 是纯逻辑,不能碰 UI
- 禁止返回 Qt 对象 → 只能返回 dict / list / str / int / bool
- 禁止在 Service 中发信号调用 widget → 状态走 core.state / EventBus
- 禁止未捕获的 IO/网络异常冒泡 → 必须 try/except 降级
- 禁止在 Service 中持有 widget 引用

OPTIONS: 有疑义先读 .trae/rules/开发规范.md §6.2。
"""

import sys
import time
import traceback

from core.services._event_emitter import EventEmitter

# ============================================================
# 路径常量
# ============================================================
# 路径常量(打包/开发环境自适应,见 core.paths)
from core.paths import app_root as _app_root, ensure_user_file as _ensure_db_file
WARFRAME_DB_PATH = _ensure_db_file("warframe.db")


class DataPipelineWorker:
    """后台线程：按依赖顺序执行数据库更新。

    事件:
        step_changed(int, str): 当前步骤 (步骤号, 描述)
        log(str, str): 日志消息 (level, msg)
        progress_pct(int): 总体进度百分比 (0-100)
        progress_detail(str, int, int): 子步骤进度 (stage, current, total)
        finished(dict): 完成 (汇总结果)
        error(str): 致命错误
        repo_progress(str, int, str): 分仓库进度 (repo_name, pct, status_text)
    """

    def __init__(self, skip_download: bool = False,
                 close_connections_fn=None):
        super().__init__()
        self._cancelled = False
        self._skip_download = skip_download
        self._close_connections_fn = close_connections_fn

        self.step_changed = EventEmitter()
        self.log = EventEmitter()
        self.progress_pct = EventEmitter()
        self.progress_detail = EventEmitter()
        self.repo_progress = EventEmitter()
        self.finished = EventEmitter()
        self.error = EventEmitter()

    def cancel(self):
        """请求 Pipeline 取消:worker 线程在下一轮询发现 _cancelled 后退出。"""
        self._cancelled = True

    def _emit_log(self, level: str, msg: str):
        """发射日志信号到 UI 日志面板（统一日志出口，不再散落 print）。

        Args:
            level: 日志级别 ("info" / "error" / "warning")
            msg: 日志消息
        """
        if not self._cancelled:
            self.log.emit(level, msg)

    def _emit_step(self, step: int, desc: str):
        """发射步骤变更信号（用于更新 UI 进度显示）。"""
        if not self._cancelled:
            self.step_changed.emit(step, desc)

    def _emit_progress(self, pct: int):
        """发射整体进度信号。"""
        if not self._cancelled:
            self.progress_pct.emit(pct)

    def _step_progress(self, stage: str, cur: int, total: int):
        """发射分步骤进度信号（如 git clone 的文件数）。"""
        if not self._cancelled:
            self.progress_detail.emit(stage, cur, total)

    def run(self):
        """执行完整流水线。

        skip_download=True 时跳过步骤1（拉取源数据），
        直接从 external/ 目录中已有的 JSON 文件构建数据库。
        """
        results = {}
        start_time = time.time()

        try:
            # ============================================================
            # 基础数据模式: 源数据 → warframe.db
            # ============================================================
            total_steps = 2
            step_num = 0

            # ============================================================
            # 步骤 1: 拉取源数据（3 个上游仓库 → external/）
            #    skip_download 时跳过此步，直接使用本地已有文件
            # ============================================================
            if not self._skip_download:
                step_num += 1
                self._emit_log("info", "=" * 50)
                self._emit_log("info", f"[{step_num}/{total_steps}] 拉取源数据")
                self._emit_step(step_num, "拉取源数据")

                step_pct_start = int((step_num - 1) / total_steps * 100)
                step_pct_end = int(step_num / total_steps * 100)

                download_ok = self._run_step_download(step_pct_start, step_pct_end)
                results["download"] = "ok" if download_ok else "failed"

                if not download_ok:
                    self._emit_log("error", "=" * 50)
                    self._emit_log("error", "源数据拉取失败，请检查网络后重试")
                    self._emit_log("error", "=" * 50)
                    results["success"] = False
                    results["error"] = "源数据拉取失败"
                    results["elapsed"] = time.time() - start_time
                    self.finished.emit(results)
                    return
            else:
                step_num += 1  # 占位，保持步骤编号一致
                self._emit_log("info", "=" * 50)
                self._emit_log("info", f"[{step_num}/{total_steps}] 跳过拉取（使用本地文件）")
                self._emit_step(step_num, "跳过拉取（使用本地文件）")

            # ============================================================
            # 步骤 2: 构建统一数据库 warframe.db
            # ============================================================
            step_num += 1
            self._emit_log("info", "")
            self._emit_log("info", f"[{step_num}/{total_steps}] 构建统一数据库 (warframe.db)")
            self._emit_step(step_num, "构建统一数据库")

            step2_pct_start = int((step_num - 1) / total_steps * 100)
            step2_pct_end = int(step_num / total_steps * 100)

            build_stats = self._run_step_build_db(step2_pct_start, step2_pct_end)
            if not build_stats:
                # 构建失败（如缺少依赖），已通过 error 信号报告，直接结束
                elapsed = time.time() - start_time
                results["elapsed"] = elapsed
                results["success"] = False
                results.setdefault("error", "数据库构建失败")
                self.finished.emit(results)
                return

            results["build"] = build_stats

            # ============================================================
            # 完成
            # ============================================================
            elapsed = time.time() - start_time
            self._emit_progress(100)
            self._emit_log("ok", "")
            self._emit_log("ok", "=" * 50)
            self._emit_log("ok", f"数据更新完成! 总耗时: {elapsed:.0f}s")
            self._emit_log("ok", "=" * 50)
            results["elapsed"] = elapsed
            results["success"] = True
            self.finished.emit(results)

        except Exception as e:
            tb = traceback.format_exc()
            # 通过统一日志通道输出（UI 日志面板 + 控制台）
            self._emit_log("error", f"流水线执行失败: {e}")
            self._emit_log("error", tb)
            results["success"] = False
            results["error"] = f"{e}\n\n{tb}"
            self.error.emit(str(e))
            self.finished.emit(results)

    # ============================================================
    # 步骤实现
    # ============================================================

    def _run_step_download(self, pct_start: int, pct_end: int) -> bool:
        """步骤1: 拉取源数据（3 个上游仓库稀疏检出）。返回是否成功。"""
        try:
            # 新版本：从 core/services 导入
            from core.services.repo_puller import (
                init_items_sparse_checkout,
                update_items_existing,
                init_drop_data_sparse_checkout,
                update_drop_data_existing,
                init_i18n_sparse_checkout,
                update_i18n_existing,
                ITEMS_OUTPUT_FILES,
            )

            def _wfcd_log(level: str, msg: str):
                self._emit_log(level, msg)

            def _wfcd_progress(*args):
                if len(args) == 1 and isinstance(args[0], int):
                    step_local_pct = args[0]
                    global_pct = pct_start + int(step_local_pct / 100 * (pct_end - pct_start))
                    self._emit_progress(global_pct)
                elif len(args) == 3:
                    stage, cur, total = args
                    self.progress_detail.emit(stage, cur, total)

            external_dir = _app_root() / "external"
            sparse_repos = [
                ("warframe-items", "遗物/物品", "warframe-items_sparse",
                 ITEMS_OUTPUT_FILES,
                 external_dir / "warframe-items_sparse" / "data" / "json",
                 init_items_sparse_checkout, update_items_existing),
                ("warframe-drop-data", "掉落数据", "warframe-drop-data_sparse",
                 ["all.json"],
                 external_dir / "warframe-drop-data_sparse" / "data",
                 init_drop_data_sparse_checkout, update_drop_data_existing),
                ("warframe-public-export-plus", "翻译数据", "warframe-i18n_sparse",
                 ["dict.en.json", "dict.zh.json"],
                 external_dir / "warframe-i18n_sparse",
                 init_i18n_sparse_checkout, update_i18n_existing),
            ]

            from core.proxy_config import (
                get_sorted_mirrors, resolve_url, get_repo_defs,
                update_test_result,
            )

            all_ok = True
            for repo_idx, (repo_key, repo_name, repo_dir_name, files, output_dir,
                           init_fn, update_fn) in enumerate(sparse_repos):
                self._emit_log("info", f"")
                self._emit_log("info", f"--- {repo_name}: {repo_dir_name} ---")
                repo_dir = _app_root() / "external" / repo_dir_name

                self.repo_progress.emit(repo_name, 0, "准备中...")

                # ── 直连优先:先试 GitHub 官方地址,失败后再用镜像兜底 ──
                owner, repo = get_repo_defs()[repo_key]
                direct_url = f"https://github.com/{owner}/{repo}.git"

                # 镜像列表中剔除官方直连(避免重复尝试);并记录直连模板的原索引
                fallback_mirrors = []
                direct_idx_orig = None
                for orig_idx, mirror_template in get_sorted_mirrors(repo_key):
                    if resolve_url(repo_key, mirror_template) == direct_url:
                        direct_idx_orig = orig_idx
                    else:
                        fallback_mirrors.append((orig_idx, mirror_template))

                # 尝试序列: (URL, 镜像原索引);原索引为 None 表示直连
                attempts = [(direct_url, direct_idx_orig)]
                for orig_idx, mirror_template in fallback_mirrors:
                    mirror_url = resolve_url(repo_key, mirror_template)
                    if mirror_url:
                        attempts.append((mirror_url, orig_idx))
                    else:
                        self._emit_log("warn", f"  镜像 [{orig_idx}] 无法解析，跳过")

                is_update = repo_dir.exists() and (repo_dir / ".git").exists()
                if is_update:
                    self._emit_log("info", f"仓库已存在，删除后重新初始化...")
                    self.repo_progress.emit(repo_name, 0, "删除旧仓库...")

                self._emit_log(
                    "info",
                    f"先直连 GitHub 官方,失败再试 {len(fallback_mirrors)} 个镜像...",
                )
                ok = False
                total_attempts = len(attempts)
                for attempt_idx, (clone_url, orig_idx) in enumerate(attempts):
                    if self._cancelled:
                        break
                    is_direct = attempt_idx == 0
                    tag = "直连官方" if is_direct else f"镜像[{orig_idx}]"

                    self._emit_log(
                        "info",
                        f"  [{attempt_idx + 1}/{total_attempts}] {tag}",
                    )
                    self.repo_progress.emit(
                        repo_name,
                        int(attempt_idx / total_attempts * 80),
                        f"git clone... {tag}",
                    )

                    if is_update and attempt_idx == 0:
                        ok = update_fn(
                            log_callback=_wfcd_log,
                            progress_callback=_wfcd_progress,
                            clone_url=clone_url,
                        )
                    else:
                        ok = init_fn(
                            log_callback=_wfcd_log,
                            progress_callback=_wfcd_progress,
                            clone_url=clone_url,
                        )
                    if ok:
                        # 直连模板若存在于镜像列表(默认列表中就有),同步记录状态
                        if orig_idx is not None:
                            update_test_result(repo_key, orig_idx, True)
                        self._emit_log("ok", f"  [OK] {tag} 成功")
                        self.repo_progress.emit(repo_name, 100, f"[OK] {tag} 成功")
                        break
                    else:
                        if orig_idx is not None:
                            update_test_result(repo_key, orig_idx, False)
                        tail = "，尝试下一个..." if attempt_idx + 1 < total_attempts else ""
                        self._emit_log("warn", f"  [X] {tag} 失败{tail}")

                if not ok:
                    self.repo_progress.emit(repo_name, 100, "[X] 直连和所有镜像均失败")

                if ok:
                    for f in files:
                        dest = output_dir / f
                        if dest.exists():
                            size_mb = dest.stat().st_size / (1024 * 1024)
                            self._emit_log("ok", f"  {f} ({size_mb:.1f} MB)")
                else:
                    existing = [f for f in files if (output_dir / f).exists()]
                    if len(existing) == len(files):
                        self._emit_log("warn", f"拉取失败，使用本地缓存")
                        self.repo_progress.emit(repo_name, 100, "[!] 使用本地缓存")
                    else:
                        missing = [f for f in files if f not in existing]
                        self._emit_log("error", f"拉取失败且缺少: {missing}")
                        all_ok = False

            return all_ok

        except Exception as e:
            tb = traceback.format_exc()
            # 通过统一日志通道输出（UI 日志面板 + 控制台）
            self._emit_log("error", f"拉取源数据失败: {e}")
            self._emit_log("error", tb)
            return False

    def _run_step_build_db(self, pct_start: int, pct_end: int) -> dict:
        """步骤2: 构建统一数据库 warframe.db。"""
        # 新版本：从 core/services 导入
        try:
            from core.services.db_builder import build
            from core.services.market_builder import build_market_items
        except ImportError as e:
            missing = str(e)
            if "pypinyin" in missing:
                hint = ("缺少依赖 pypinyin，请在终端执行:\n"
                        "  pip install pypinyin\n"
                        "然后重新启动程序。\n\n"
                        f"当前 Python: {sys.executable}\n"
                        f"sys.path: {sys.path[:3]}...")
            else:
                hint = f"缺少依赖: {e}"
            self._emit_log("error", f"构建数据库失败: {hint}")
            self.error.emit(hint)
            return {}

        def _build_log(msg: str):
            self._emit_log("info", msg)

        def _build_progress(stage: str, cur: int, total: int):
            self._step_progress(stage, cur, total)
            if total > 0:
                global_pct = pct_start + int(cur / total * (pct_end - pct_start))
                self._emit_progress(min(global_pct, pct_end))

        stats = build(
            log_callback=_build_log,
            progress_callback=_build_progress,
            skip_wm=True,
            close_connections_fn=self._close_connections_fn,
        )
        self._emit_log("ok", f"  items: {stats.get('items', 0):,} 条")
        self._emit_log("ok", f"  relics: {stats.get('relics', 0):,} 个")
        self._emit_log("ok", f"  relic_rewards: {stats.get('relic_rewards', 0):,} 条")
        self._emit_log("ok", f"  game_translations: {stats.get('game_translations', 0):,} 条")

        self._emit_log("info", "  构建 market_items 表...")
        mi_result = build_market_items(
            log_callback=lambda msg: self._emit_log("info", f"    {msg}"),
        )
        stats['market_items'] = mi_result.get('inserted', 0)
        self._emit_log("ok", f"  market_items: {stats['market_items']:,} 条")

        self._emit_log("ok", f"  耗时: {stats.get('elapsed_sec', 0):.1f}s")
        return stats


# ============================================================
# 状态概要
# ============================================================

def get_pipeline_summary() -> dict:
    """获取当前数据文件状态的概要信息。"""
    external_dir = _app_root() / "external"
    wfcd_dir = external_dir / "warframe-items_sparse" / "data" / "json"
    drop_dir = external_dir / "warframe-drop-data_sparse" / "data"
    i18n_dir = external_dir / "warframe-i18n_sparse"

    # 旧 All.json 已拆分为分类文件:全部存在才记 True
    from core.services.repo_puller import _ITEMS_CATEGORY_FILES
    category_present = all((wfcd_dir / name).exists() for name in _ITEMS_CATEGORY_FILES)

    info = {
        "category_json": category_present,
        "Relics.json": (wfcd_dir / "Relics.json").exists(),
        "i18n.json": (wfcd_dir / "i18n.json").exists(),
        "all.json": (drop_dir / "all.json").exists(),
        "dict.en.json": (i18n_dir / "dict.en.json").exists(),
        "dict.zh.json": (i18n_dir / "dict.zh.json").exists(),
        "warframe.db": WARFRAME_DB_PATH.exists(),
    }

    sizes = {}
    # 分类文件大小汇总(同名前缀,便于 UI 展示)
    cat_total = 0
    for name in _ITEMS_CATEGORY_FILES:
        p = wfcd_dir / name
        if p.exists():
            cat_total += p.stat().st_size
    if cat_total:
        sizes["category_json"] = cat_total
    for name, path in [
        ("i18n.json", wfcd_dir / "i18n.json"),
        ("all.json", drop_dir / "all.json"),
        ("dict.en.json", i18n_dir / "dict.en.json"),
        ("dict.zh.json", i18n_dir / "dict.zh.json"),
        ("warframe.db", WARFRAME_DB_PATH),
    ]:
        if path.exists():
            sizes[name] = path.stat().st_size

    info["sizes"] = sizes
    return info
