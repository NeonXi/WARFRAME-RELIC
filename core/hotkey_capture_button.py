"""
HotkeyCaptureButton - 快捷键捕获按钮
点击后进入"监听"状态，实时显示按下的键，松开时记录组合键。
支持 modifier + key 组合键格式（如 ctrl+shift+p）。

交互逻辑：
- 点击按钮 → 进入捕获状态，显示"按下组合键..."
- 按下修饰键（ctrl/alt/shift/win）→ 实时显示，如"ctrl"
- 继续按下更多键 → 累加显示，如"ctrl+shift" → "ctrl+shift+a"
- 松开任意键 → 记录当前累积的组合键，退出捕获状态
- 按 Esc → 取消捕获，恢复原值
"""

from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent


# 修饰键的显示顺序（固定，保证输出一致性）
_MODIFIER_ORDER = ["ctrl", "alt", "shift", "win"]

# 修饰键 Qt.Key → 显示名
_MODIFIER_KEYS: dict[int, str] = {
    Qt.Key.Key_Control: "ctrl",
    Qt.Key.Key_Alt: "alt",
    Qt.Key.Key_Shift: "shift",
    Qt.Key.Key_Meta: "win",
}

# 修饰键集合（用于快速判断）
_MODIFIER_KEY_SET = set(_MODIFIER_KEYS.keys())

# 普通键名称映射（Qt.Key → 字符串）
_KEY_NAME_MAP: dict[int, str] = {
    Qt.Key.Key_F1: "f1", Qt.Key.Key_F2: "f2", Qt.Key.Key_F3: "f3",
    Qt.Key.Key_F4: "f4", Qt.Key.Key_F5: "f5", Qt.Key.Key_F6: "f6",
    Qt.Key.Key_F7: "f7", Qt.Key.Key_F8: "f8", Qt.Key.Key_F9: "f9",
    Qt.Key.Key_F10: "f10", Qt.Key.Key_F11: "f11", Qt.Key.Key_F12: "f12",
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
    Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "pageup", Qt.Key.Key_PageDown: "pagedown",
    Qt.Key.Key_Escape: "esc",
    Qt.Key.Key_CapsLock: "capslock",
}


def _key_to_display_name(key: int) -> str | None:
    """将 Qt.Key 转为显示名称。"""
    if key in _MODIFIER_KEYS:
        return _MODIFIER_KEYS[key]
    name = _KEY_NAME_MAP.get(key)
    if name is not None:
        return name
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key).lower()
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key)
    # 尝试枚举名
    try:
        raw = Qt.Key(key).name
        if raw:
            s = raw.decode() if isinstance(raw, bytes) else raw
            return s.lower().removeprefix("key_")
    except Exception:
        pass
    return None


class HotkeyCaptureButton(QLineEdit):
    """快捷键捕获控件。

    点击后进入"监听"状态：
    - keyPressEvent: 累积按下的键，实时更新显示
    - keyReleaseEvent: 记录最终组合键，退出捕获
    - Esc: 取消，恢复原值
    - 失去焦点: 取消，恢复原值
    """

    hotkey_changed = pyqtSignal(str)

    def __init__(self, hotkey: str = "", parent=None):
        super().__init__(parent)
        self._hotkey = hotkey          # 已保存的快捷键
        self._capturing = False        # 是否处于捕获状态
        self._saved_hotkey = hotkey    # 进入捕获前的值（Esc 恢复用）
        self._pressed_keys: dict[int, str] = {}  # 当前按下的键 {Qt.Key: 显示名}

        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_display()

    # ==================== 显示 ====================

    def _update_display(self):
        if self._capturing:
            if self._pressed_keys:
                self.setText(self._build_current_combo())
            else:
                self.setText("按下组合键...")
        elif self._hotkey:
            self.setText(self._hotkey.upper())
        else:
            self.setText("点击设置")

    def _build_current_combo(self) -> str:
        """根据 _pressed_keys 构建当前显示字符串。
        修饰键按固定顺序在前，普通键在后。
        """
        mods = []
        keys = []
        for name in self._pressed_keys.values():
            if name in _MODIFIER_ORDER:
                mods.append(name)
            else:
                keys.append(name)
        # 去重保持顺序
        ordered_mods = [m for m in _MODIFIER_ORDER if m in mods]
        return "+".join(ordered_mods + keys)

    # ==================== 公开 API ====================

    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, hotkey: str):
        self._hotkey = hotkey
        self._capturing = False
        self._pressed_keys.clear()
        self._update_display()

    # ==================== 鼠标 ====================

    def mousePressEvent(self, event: QMouseEvent | None):
        if event is None:
            return
        if not self._capturing:
            self._enter_capture()

    def mouseReleaseEvent(self, event: QMouseEvent | None):
        pass  # 吞掉

    def mouseDoubleClickEvent(self, event: QMouseEvent | None):
        pass  # 吞掉

    # ==================== 焦点 ====================

    def focusInEvent(self, event):
        if not self._capturing:
            self._enter_capture()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        if self._capturing:
            self._cancel_capture()
        super().focusOutEvent(event)

    # ==================== 捕获状态管理 ====================

    def _enter_capture(self):
        self._capturing = True
        self._saved_hotkey = self._hotkey
        self._pressed_keys.clear()
        self._update_display()
        self.setFocus()

    def _commit_capture(self):
        """记录当前组合键并退出捕获。"""
        combo = self._build_current_combo()
        if combo:  # 至少按了一个键
            self._hotkey = combo
            self._capturing = False
            self._pressed_keys.clear()
            self._update_display()
            self.hotkey_changed.emit(combo)
            self.clearFocus()
        # 如果 combo 为空（不太可能，松开事件前一定有按键），保持捕获

    def _cancel_capture(self):
        """取消捕获，恢复原值。"""
        self._hotkey = self._saved_hotkey
        self._capturing = False
        self._pressed_keys.clear()
        self._update_display()

    # ==================== 键盘事件 ====================

    def keyPressEvent(self, event):
        if not self._capturing:
            event.ignore()
            return

        key = event.key()

        # Esc: 取消
        if key == Qt.Key.Key_Escape:
            self._cancel_capture()
            self.clearFocus()
            return

        name = _key_to_display_name(key)
        if name is None:
            return  # 无法识别的键，忽略

        # 记录按下的键（支持同键重复按下时覆盖）
        self._pressed_keys[key] = name
        self._update_display()

        # 阻止默认行为（如 Tab 切换焦点）
        event.accept()

    def keyReleaseEvent(self, event):
        if not self._capturing:
            event.ignore()
            return

        key = event.key()

        # 忽略修饰键的松开（用户可能在调整修饰键组合）
        if key in _MODIFIER_KEY_SET:
            event.accept()
            return

        # Esc 在 press 已处理，这里忽略
        if key == Qt.Key.Key_Escape:
            event.accept()
            return

        # 普通键松开 → 提交
        self._commit_capture()
        event.accept()
