"""
[L-Service] WorldstateService — 虚空裂缝实时数据 业务逻辑

依赖: Python 标准库(json/pathlib/threading) + PySide6.QtCore(QObject/Signal/QTimer)
      core.services.http_client(官方世界状态)
禁止: PySide6.QtWidgets / QtGui、直接操作 widget
职责:
  - 从 DE 官方 worldState.php 拉取世界状态(免登录)
  - 解析 ActiveMissions(虚空裂缝)为结构化 dict
  - 节点名经内置 data/worldstate/solNodes.json 翻译
  - 定时自动刷新 + 手动刷新(后台线程,不阻塞 UI)

数据流:
  后台线程解析 → fissures_changed Signal → 页面更新 UI

错误处理: 网络/解析全部 try/except,失败发 error_occurred,
绝不向 UI 抛异常。
"""

from __future__ import annotations

import json
import re
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from core.paths import resource_dir as _resource_dir
from core.paths import user_data_dir as _user_data_dir
from core.services.game_vocab import MISSION_TYPE_ZH as _MISSION_MAP
from core.services.game_vocab import VOID_TIER as _TIER_MAP

# ── 常量 ──

# DE 官方世界状态(游戏客户端使用同一数据源)
WORLDSTATE_URL = "https://api.warframe.com/cdn/worldState.php"

# 节点翻译表(节点名/派系),内置,无需联网
_NODE_FILE = _resource_dir() / "worldstate" / "solNodes.json"

# 磁盘缓存(上次成功拉取的裂缝列表):启动/进页面先渲染旧数据,
# DE 官方 API 国内访问 10-20s,无缓存会导致每次启动后首进页面白等
_CACHE_FILE = _user_data_dir() / "worldstate_cache.json"

# 自动刷新间隔(秒);裂缝每分钟有变动,60s 足够
AUTO_REFRESH_MS = 60_000

# ── 裂缝纪元修饰符: VoidT1~T6 → (英文, 中文) ──
# 定义在 core/services/game_vocab.py(单一事实源),此处仅按原名引用

# 裂缝列表排序用的纪元顺序: 古 前 中 后 安魂 全能
_TIER_ORDER: dict[str, int] = {
    "Lith": 0, "Meso": 1, "Neo": 2, "Axi": 3, "Requiem": 4, "Omnia": 5,
}

# ── 星球名: 英文 → 中文(节点 value 形如 "Galatea (Neptune)") ──
_PLANET_MAP: dict[str, str] = {
    "Mercury": "水星",
    "Venus": "金星",
    "Earth": "地球",
    "Mars": "火星",
    "Phobos": "火卫一",
    "Deimos": "火卫二",
    "Ceres": "谷神星",
    "Jupiter": "木星",
    "Europa": "欧罗巴",
    "Saturn": "土星",
    "Uranus": "天王星",
    "Neptune": "海王星",
    "Pluto": "冥王星",
    "Sedna": "赛德娜",
    "Eris": "阋神星",
    "Lua": "月球",
    "Void": "虚空",
    "Kuva Fortress": "赤毒要塞",
    "Zariman": "扎里曼",
    "Duviri": "杜威",
    "Veil": "面纱星",
}

# ── 任务类型: MT_XXX → 中文(未列出的回落英文原名) ──
# 定义在 core/services/game_vocab.py(单一事实源),此处仅按原名引用


class WorldstateService(QObject):
    """虚空裂缝服务（单例）。

    Signals:
        fissures_changed(list): 裂缝列表已刷新(每项为 dict)
        loading_started():      开始一次加载
        load_failed(str):       加载失败(错误描述)
    """

    fissures_changed = Signal(list)
    loading_started = Signal()
    load_failed = Signal(str)

    _instance: "WorldstateService | None" = None

    @classmethod
    def instance(cls) -> "WorldstateService":
        """单例访问（惰性创建）。"""
        if cls._instance is None:
            cls._instance = WorldstateService()
        return cls._instance

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # 节点翻译表 {SolNodeXX: {value, enemy, ...}}
        self._nodes: dict = self._load_node_table()

        # 当前裂缝缓存(启动时从磁盘缓存恢复,秒显旧数据)
        self._fissures: list[dict] = self._load_disk_cache()

        # 后台线程去重
        self._worker_lock = threading.Lock()
        self._worker_running: bool = False

        # 自动刷新定时器
        self._timer = QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

        # attach 引用计数(页面进入 +1,离开 -1;归零停定时器)
        self._attach_count: int = 0

    # ════════════════════════════════════
    #  生命周期(页面调用)
    # ════════════════════════════════════

    def attach(self) -> None:
        """页面进入:首次立即拉取,并启动自动刷新。"""
        self._attach_count += 1
        if not self._timer.isActive():
            self._timer.start()
        # 有磁盘缓存先发一次信号:页面立即渲染旧数据(进度条按 expiry 算,
        # 过期项 15s 内会被下面的网络刷新覆盖),消除白等
        if self._fissures:
            self.fissures_changed.emit(self.get_fissures())
        # 缓存空则立即拉;有缓存也后台刷新一次保证新鲜
        self.refresh()

    def detach(self) -> None:
        """页面离开:最后一个离开时停止自动刷新。"""
        if self._attach_count > 0:
            self._attach_count -= 1
        if self._attach_count == 0:
            self._timer.stop()

    # ════════════════════════════════════
    #  公开 API
    # ════════════════════════════════════

    def refresh(self) -> None:
        """立即后台刷新一次(去重,不阻塞)。"""
        with self._worker_lock:
            if self._worker_running:
                return
            self._worker_running = True
        self.loading_started.emit()
        thread = threading.Thread(
            target=self._fetch_worker, daemon=True, name="WorldstateFetch"
        )
        thread.start()

    def get_fissures(self) -> list[dict]:
        """返回当前裂缝缓存(只读副本)。"""
        return list(self._fissures)

    # ════════════════════════════════════
    #  内部
    # ════════════════════════════════════

    def _fetch_worker(self) -> None:
        """后台线程:拉取 + 解析,发信号。"""
        try:
            from core.services.http_client import HttpClient
            data = HttpClient.instance().get_json(WORLDSTATE_URL)
            fissures = self._parse_fissures(data)
            self._fissures = fissures
            self._save_disk_cache(fissures)
            self._emit_safely(self.fissures_changed, fissures)
        except Exception as e:
            self._emit_safely(self.load_failed, f"{type(e).__name__}: {e}")
        finally:
            with self._worker_lock:
                self._worker_running = False

    @staticmethod
    def _emit_safely(signal, *args) -> None:
        """向可能已被回收的 QObject 发信号。

        本服务的拉取线程是 daemon：程序退出/测试 teardown 时，单例 QObject
        可能先于线程被回收，此时 PySide6 抛 ``RuntimeError: Signal source has
        been deleted``。这属于关闭期的正常竞态，不应让 traceback 冒泡到
        threading 的默认异常钩子（会污染控制台与测试输出）。
        注意：只吞 RuntimeError，其它异常照常暴露。
        """
        try:
            signal.emit(*args)
        except RuntimeError:
            # 对象已销毁 —— 关闭期竞态，无需也无法再通知订阅者
            pass

    def _parse_fissures(self, data: dict) -> list[dict]:
        """把 ActiveMissions 原始数据解析为 UI 友好的 dict 列表。"""
        raw = data.get("ActiveMissions", [])
        if not isinstance(raw, list):
            return []

        result: list[dict] = []
        for m in raw:
            if not isinstance(m, dict):
                continue
            node_key = str(m.get("Node", ""))
            modifier = str(m.get("Modifier", ""))
            tier_en, tier_zh = _TIER_MAP.get(
                modifier, (modifier.replace("Void", ""), modifier)
            )

            node_info = self._nodes.get(node_key, {})
            node_raw = node_info.get("value", node_key)
            # 节点 value 形如 "Galatea (Neptune)":拆出节点名(英文保留) + 星球(译中文)
            node_name, planet = self._split_node_planet(node_raw)
            faction = node_info.get("enemy", "")

            mt = str(m.get("MissionType", ""))
            mission = _MISSION_MAP.get(mt, mt.replace("MT_", "").title())

            result.append({
                "id": str(m.get("_id", {}).get("$oid", "")),
                "node": node_name,
                "planet": planet,
                "faction": faction,
                "mission": mission,
                "tier_en": tier_en,
                "tier_zh": tier_zh,
                "hard": bool(m.get("Hard", False)),
                "activation": self._to_seconds(m.get("Activation")),
                "expiry": self._to_seconds(m.get("Expiry")),
            })

        # 先按纪元顺序(古/前/中/后/安魂/全能),同纪元内快结束的排前面
        result.sort(key=lambda x: (
            _TIER_ORDER.get(x["tier_en"], 99), x["expiry"]
        ))
        return result

    @staticmethod
    def _to_seconds(value) -> int:
        """官方时间字段 {$date:{$numberLong:毫秒}} → 秒。"""
        try:
            ms = int(value["$date"]["$numberLong"])
            return ms // 1000
        except (TypeError, KeyError, ValueError):
            return 0

    @staticmethod
    def _split_node_planet(raw: str) -> tuple[str, str]:
        """把 "Galatea (Neptune)" 拆成 (节点名, 星球中文名)。

        节点名保留英文,星球名经 _PLANET_MAP 翻译为中文;
        无括号或星球未收录时,星球回落英文名(保持原信息不丢)。
        """
        m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", raw)
        if not m:
            return raw.strip(), ""
        node_name = m.group(1).strip()
        planet_en = m.group(2).strip()
        planet_zh = _PLANET_MAP.get(planet_en, planet_en)
        return node_name, planet_zh

    @staticmethod
    def _load_node_table() -> dict:
        """加载内置节点翻译表(失败返回空 dict,节点回落原始 key)。"""
        try:
            with _NODE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _load_disk_cache() -> list[dict]:
        """读取上次成功拉取的裂缝列表(失败/损坏返回空,静默降级)。"""
        try:
            with _CACHE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            fissures = data.get("fissures", [])
            return fissures if isinstance(fissures, list) else []
        except Exception:
            return []

    @staticmethod
    def _save_disk_cache(fissures: list[dict]) -> None:
        """成功拉取后持久化,供下次启动秒显(失败静默,不影响主流程)。"""
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(
                    {"saved_at": int(time.time()), "fissures": fissures},
                    f, ensure_ascii=False,
                )
        except Exception as e:
            # 缓存写入失败不影响本次展示，但下次启动会失去"秒显"，需留痕
            print(f"[Worldstate] 磁盘缓存写入失败: {e}", flush=True)
