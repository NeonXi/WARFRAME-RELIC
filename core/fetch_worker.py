"""
数据拉取 Worker —— 后台线程从 GitHub 下载最新 all.json 和 i18n.json，精细化进度反馈。
"""

import json
import os
import socket
import time
import urllib.request
import urllib.error
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QObject


GITHUB_RAW_BASE = "https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data"
ALLJSON_URL = f"{GITHUB_RAW_BASE}/all.json"
RELIC_URL = f"{GITHUB_RAW_BASE}/relics.json"

# i18n 多语言翻译数据（来自 warframe-items 仓库）
I18N_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/i18n.json"

# i18n 清洗: 仅保留的语言代码
I18N_KEEP_LANGS = {'zh', 'en'}


class FetchWorker(QObject):
    """后台线程：从 GitHub 下载最新 all.json 和 i18n.json，精细化进度反馈"""

    # ---- 信号定义 ----
    step_changed = pyqtSignal(int, str)       # 当前步骤 (1~10), 步骤描述
    log = pyqtSignal(str, str)                # 日志: (类型: ok/warn/error/info, 消息)
    progress_pct = pyqtSignal(int)             # 下载进度 0~100
    finished = pyqtSignal(str)                # 下载完成 → 携带 all.json 保存路径
    error = pyqtSignal(str)                   # 致命错误

    def __init__(self, save_path: str, url: str = ALLJSON_URL, max_retries: int = 2):
        super().__init__()
        self.save_path = save_path
        self.url = url
        self.max_retries = max_retries

    # ------------------------------------------------------------
    # 核心执行流程
    # ------------------------------------------------------------
    def run(self):
        start_time = time.time()

        # ===== 步骤 1: 解析 URL，检测网络环境 =====
        self.step_changed.emit(1, "解析目标地址")
        self.log.emit("info", f"目标: {self.url}")
        try:
            parsed = urllib.request.urlparse(self.url)
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except Exception as e:
            self.log.emit("error", f"URL 解析失败: {e}")
            self.error.emit(f"URL 解析失败: {e}")
            return

        self.log.emit("info", f"主机: {host}:{port}")
        self.log.emit("info", f"路径: {parsed.path}")
        self.log.emit("info", f"协议: {parsed.scheme.upper()}")

        # ===== 步骤 2: DNS 解析 =====
        self.step_changed.emit(2, "DNS 解析")
        self.log.emit("info", f"正在解析 {host} ...")
        try:
            ip = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            ip_str = ip[0][4][0] if ip else "未知"
            self.log.emit("ok", f"DNS 解析成功 → {ip_str}")
        except socket.gaierror as e:
            self.log.emit("error", f"DNS 解析失败: {e}")
            self.log.emit("error", "可能原因: 网络未连接 / DNS 服务器无响应 / 域名被屏蔽")
            self.error.emit(f"DNS 解析失败: {e}\n请检查网络连接")
            return

        # ===== 步骤 3: TCP 连接 + SSL 握手（带重试）=====
        self.step_changed.emit(3, "建立安全连接")
        self.log.emit("info", "正在建立 HTTPS 连接...")
        resp = None
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                self.log.emit("info", f"第 {attempt} 次重试...")
                time.sleep(2)
            try:
                req = urllib.request.Request(
                    self.url,
                    headers={"User-Agent": "WARFRAME-RELIC/1.0"}
                )
                conn_start = time.time()
                resp = urllib.request.urlopen(req, timeout=15)
                conn_time = (time.time() - conn_start) * 1000
                self.log.emit("ok", f"HTTPS 连接成功 (耗时 {conn_time:.0f} ms)")
                break
            except urllib.error.HTTPError as e:
                last_error = (f"HTTP {e.code}: {e.reason}", e)
                if e.code == 404:
                    self.log.emit("error", "文件不存在，可能是 GitHub 路径已变更")
                elif e.code == 403:
                    self.log.emit("error", "访问被拒绝 (403)，可能被 GitHub 限流")
                break  # HTTP 错误不重试
            except urllib.error.URLError as e:
                last_error = (f"连接失败: {e.reason}", e)
                reason = str(e.reason)
                self.log.emit("warn", f"连接失败 (第 {attempt}/{self.max_retries} 次): {reason}")
                if "timed out" in reason.lower():
                    self.log.emit("warn", "连接超时，可能原因: 防火墙阻止 / 网络不稳定")
            except Exception as e:
                last_error = (str(e), e)
                self.log.emit("warn", f"未知连接错误 (第 {attempt}/{self.max_retries} 次): {e}")
        else:
            msg, exc = last_error or ("未知错误", Exception("unknown"))
            self.log.emit("error", f"{msg}（已重试 {self.max_retries} 次）")
            self.log.emit("error", "建议: 使用 Watt Toolkit 加速 GitHub 或手动下载")
            self.error.emit(f"{msg}\n已重试 {self.max_retries} 次，仍然失败。\n请尝试手动下载或使用网络加速工具。")
            return

        try:
            # ===== 步骤 4: 获取文件信息 =====
            self.step_changed.emit(4, "获取文件信息")
            content_length = resp.headers.get("Content-Length")
            content_type = resp.headers.get("Content-Type", "未知")
            content_encoding = resp.headers.get("Content-Encoding", "无")
            last_modified = resp.headers.get("Last-Modified", "未知")
            self.log.emit("info", f"Content-Type: {content_type}")
            self.log.emit("info", f"Content-Encoding: {content_encoding}")
            self.log.emit("info", f"Last-Modified: {last_modified}")
            if content_length:
                size_kb = int(content_length) / 1024
                size_mb = size_kb / 1024
                if size_mb >= 1:
                    self.log.emit("info", f"文件大小: {size_mb:.2f} MB ({int(content_length):,} bytes)")
                else:
                    self.log.emit("info", f"文件大小: {size_kb:.0f} KB ({int(content_length):,} bytes)")
            else:
                self.log.emit("warn", "服务器未提供 Content-Length，无法显示下载进度")

            # ===== 步骤 5: 下载数据（带进度） =====
            self.step_changed.emit(5, "下载数据")
            self.log.emit("info", "开始下载 all.json 数据文件...")
            self.log.emit("info", f"每次读取块大小: 8 KB | 连接超时: 15s")
            chunks = []
            downloaded = 0
            total = int(content_length) if content_length else 0
            last_pct = -1
            dl_start = time.time()

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
                        if pct % 20 == 0 and pct != last_pct:
                            elapsed = time.time() - dl_start
                            speed = (downloaded / 1024 / elapsed) if elapsed > 0 else 0
                            self.log.emit("info", f"下载进度: {pct}% ({downloaded/1024:.0f}/{total/1024:.0f} KB, {speed:.0f} KB/s)")
                        last_pct = pct
            content = b"".join(chunks)
        except Exception as e:
            self.log.emit("error", f"下载中断: {e}")
            self.error.emit(f"下载中断: {e}")
            return
        finally:
            # 确保响应对象被关闭，防止连接泄漏
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

        dl_time = time.time() - dl_start
        dl_kb = len(content) / 1024
        dl_mb = dl_kb / 1024
        speed = dl_kb / dl_time if dl_time > 0 else 0
        if dl_mb >= 1:
            self.log.emit("ok", f"下载完成 → {dl_mb:.2f} MB (耗时 {dl_time:.1f}s, 平均 {speed:.0f} KB/s)")
        else:
            self.log.emit("ok", f"下载完成 → {dl_kb:.0f} KB (耗时 {dl_time:.1f}s, 平均 {speed:.0f} KB/s)")
        self.progress_pct.emit(100)

        # ===== 步骤 6: 验证数据格式 =====
        self.step_changed.emit(6, "验证数据格式")
        self.log.emit("info", "正在验证 JSON 数据格式...")
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                key_count = len(data)
                top_keys = list(data.keys())
                key_preview = ', '.join(top_keys[:8])
                if len(top_keys) > 8:
                    key_preview += f' ... 等 {len(top_keys)} 个字段'
                self.log.emit("ok", f"JSON 格式正确 (顶层 {key_count} 个字段)")
                self.log.emit("info", f"  字段列表: {key_preview}")
            elif isinstance(data, list):
                self.log.emit("ok", f"JSON 格式正确 (数组, {len(data)} 个元素)")
            else:
                self.log.emit("ok", "JSON 格式正确")
        except json.JSONDecodeError as e:
            self.log.emit("error", f"JSON 解析失败: {e}")
            self.log.emit("error", "下载的文件可能损坏或不完整")
            self.log.emit("error", f"错误位置: 第 {e.lineno} 行, 第 {e.colno} 列")
            self.error.emit(f"数据格式错误: {e}")
            return

        # ===== 步骤 7: 保存文件 =====
        self.step_changed.emit(7, "保存文件")
        save_path = Path(self.save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # 备份旧文件
        if save_path.exists():
            backup = save_path.with_suffix('.json.bak')
            try:
                save_path.replace(backup)
                self.log.emit("info", f"旧文件已备份: {backup.name}")
            except Exception as e:
                self.log.emit("warn", f"备份旧文件失败: {e}")

        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log.emit("ok", f"文件已保存（已格式化）: {save_path}")
        except Exception as e:
            self.log.emit("error", f"保存文件失败: {e}")
            self.error.emit(f"保存文件失败: {e}")
            return

        # ================================================================
        # 阶段 2: 下载 i18n.json（多语言翻译数据）
        # ================================================================
        self._download_i18n(save_path)

        total_time = time.time() - start_time
        self.log.emit("ok", f"========== 全部完成 (总耗时 {total_time:.1f}s) ==========")
        self.finished.emit(str(save_path))

    # ------------------------------------------------------------
    # 下载 i18n.json 并清洗（仅保留 zh/en）
    # ------------------------------------------------------------
    def _download_i18n(self, alljson_save_path: str):
        """下载 i18n.json，清洗后保存到 data/i18n.json。"""
        save_dir = Path(alljson_save_path).parent
        i18n_path = save_dir / 'i18n.json'

        # ===== 步骤 8: 下载 i18n.json =====
        self.step_changed.emit(8, "下载 i18n 翻译数据")
        self.log.emit("info", "")
        self.log.emit("info", "--- 阶段 2: 下载 i18n.json (多语言翻译) ---")
        self.log.emit("info", f"源地址: {I18N_URL}")
        self.log.emit("info", f"保存到: {i18n_path}")

        try:
            resp = None
            for attempt in range(1, self.max_retries + 1):
                if attempt > 1:
                    self.log.emit("info", f"第 {attempt} 次重试...")
                    time.sleep(2)
                try:
                    req = urllib.request.Request(
                        I18N_URL,
                        headers={"User-Agent": "WARFRAME-RELIC/1.0"}
                    )
                    resp = urllib.request.urlopen(req, timeout=30)
                    break
                except urllib.error.HTTPError as e:
                    self.log.emit("warn", f"i18n.json HTTP {e.code}: {e.reason}")
                    if e.code == 404:
                        break
                except urllib.error.URLError as e:
                    self.log.emit("warn", f"i18n.json 连接失败 (第 {attempt}/{self.max_retries} 次): {e.reason}")
            else:
                self.log.emit("warn", "i18n.json 下载失败，将跳过翻译数据更新")
                self.log.emit("info", "  提示: 可稍后手动下载 i18n.json 放入 data 目录")
                return

            # 下载
            dl_start = time.time()
            chunks = []
            content_length = resp.headers.get("Content-Length")
            total = int(content_length) if content_length else 0
            if total:
                self.log.emit("info", f"文件大小: {total/1024/1024:.1f} MB")

            while True:
                chunk = resp.read(32768)
                if not chunk:
                    break
                chunks.append(chunk)
                if total > 0:
                    pct = min(int(sum(len(c) for c in chunks) * 100 / total), 100)
                    self.progress_pct.emit(pct)

            content = b"".join(chunks)
            dl_time = time.time() - dl_start
            self.log.emit("ok", f"i18n.json 下载完成 ({len(content)/1024/1024:.1f} MB, 耗时 {dl_time:.1f}s)")

        except Exception as e:
            self.log.emit("warn", f"i18n.json 下载失败: {e}")
            self.log.emit("info", "  提示: 可稍后手动下载 i18n.json 放入 data 目录")
            return
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

        # ===== 步骤 9: 清洗 i18n.json（仅保留 zh/en）=====
        self.step_changed.emit(9, "清洗 i18n 翻译数据")
        self.log.emit("info", "正在清洗 i18n.json，移除多余语言...")

        try:
            data = json.loads(content)
            orig_langs = set()
            stripped_count = 0
            kept_langs = set()

            for unique_name, translations in data.items():
                if not isinstance(translations, dict):
                    continue
                for lang in translations:
                    orig_langs.add(lang)

                new_translations = {}
                for lang in I18N_KEEP_LANGS:
                    if lang in translations:
                        new_translations[lang] = translations[lang]
                        kept_langs.add(lang)

                if len(new_translations) < len(translations):
                    stripped_count += 1

                data[unique_name] = new_translations

            langs_removed = orig_langs - kept_langs
            self.log.emit("ok", f"清洗完成: {len(data)} 个条目, 保留 {sorted(kept_langs)}, "
                          f"移除 {sorted(langs_removed)}, 修改 {stripped_count} 条")
        except Exception as e:
            self.log.emit("error", f"i18n.json 清洗失败: {e}")
            return

        # ===== 步骤 10: 保存 i18n.json =====
        self.step_changed.emit(10, "保存 i18n 翻译数据")
        self.log.emit("info", "正在保存 i18n.json...")

        # 备份旧文件
        if i18n_path.exists():
            backup = i18n_path.with_suffix('.json.bak')
            try:
                i18n_path.replace(backup)
                self.log.emit("info", f"旧 i18n.json 已备份: {backup.name}")
            except Exception as e:
                self.log.emit("warn", f"备份旧 i18n.json 失败: {e}")

        try:
            with open(i18n_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            size = os.path.getsize(i18n_path)
            self.log.emit("ok", f"i18n.json 已保存（已清洗+格式化）: {i18n_path} ({size/1024/1024:.1f} MB)")
        except Exception as e:
            self.log.emit("error", f"i18n.json 保存失败: {e}")
            return
