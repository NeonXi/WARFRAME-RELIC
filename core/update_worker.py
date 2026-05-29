"""
数据更新 Worker —— 后台线程执行数据库更新，通过信号通知 UI。
"""
from PyQt6.QtCore import pyqtSignal, QObject

from update_db import update_from_alljson, _finalize_db


class UpdateWorker(QObject):
    """在后台线程执行数据库更新。"""

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, json_path: str, db_path: str):
        super().__init__()
        self.json_path = json_path
        self.db_path = db_path

    def run(self):
        try:
            self.progress.emit("正在读取数据文件...")
            stats = update_from_alljson(self.json_path, self.db_path)
            _finalize_db(self.db_path)
            self.progress.emit("更新完成!")
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))
