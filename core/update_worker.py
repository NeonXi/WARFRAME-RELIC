"""
数据更新 Worker —— 后台线程执行数据库更新，通过信号通知 UI。
"""

import sys
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QObject


class UpdateWorker(QObject):
    """在后台线程执行数据库更新，通过信号通知 UI"""
    progress = pyqtSignal(str)       # 进度文本
    finished = pyqtSignal(dict)      # 完成统计
    error = pyqtSignal(str)          # 错误信息

    def __init__(self, json_path: str, db_path: str):
        super().__init__()
        self.json_path = json_path
        self.db_path = db_path

    def run(self):
        try:
            data_dir = str(Path(self.db_path).parent)
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from update_db import update_from_alljson, _finalize_db

            self.progress.emit("正在读取数据文件...")
            stats = update_from_alljson(self.json_path, self.db_path)
            _finalize_db(self.db_path)

            self.progress.emit("更新完成!")
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))
