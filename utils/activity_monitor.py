# utils/activity_monitor.py

import threading
import time
import platform
from pynput import keyboard, mouse

# 根据平台导入不同的窗口管理模块
PLATFORM = platform.system()

if PLATFORM == "Darwin":  # macOS
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        from AppKit import NSWorkspace
        MACOS_AVAILABLE = True
    except ImportError:
        print("警告: macOS窗口管理模块未安装。请运行: pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa")
        MACOS_AVAILABLE = False
elif PLATFORM == "Windows":
    try:
        import pygetwindow as gw
        from pygetwindow import PyGetWindowException
        WINDOWS_AVAILABLE = True
    except ImportError:
        print("警告: Windows窗口管理模块未安装。请运行: pip install pygetwindow")
        WINDOWS_AVAILABLE = False
else:
    print(f"警告: 不支持的平台 {PLATFORM}")

class InputWindowMonitor:
    def __init__(self, interval=2.0):
        self.interval = interval
        self.keyboard_count = 0
        self.mouse_count = 0
        self.keyboard_freq = 0.0
        self.mouse_freq = 0.0
        self.open_apps_count = 0
        self.window_titles = []

        self.lock = threading.Lock()
        self._stop_event = threading.Event()

    def _keyboard_on_press(self, key):
        with self.lock:
            self.keyboard_count += 1

    def _mouse_on_click(self, x, y, button, pressed):
        if pressed:
            with self.lock:
                self.mouse_count += 1

    def _get_windows_macos(self):
        """获取macOS上的窗口列表"""
        if not MACOS_AVAILABLE:
            return []

        try:
            # 获取所有在屏幕上的窗口
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID
            )

            visible_windows = []
            for window in window_list:
                # 获取窗口标题和所属应用
                window_name = window.get('kCGWindowName', '')
                owner_name = window.get('kCGWindowOwnerName', '')
                layer = window.get('kCGWindowLayer', 0)

                # 过滤系统窗口（layer=0表示普通应用窗口）
                if layer == 0 and window_name and owner_name:
                    # 组合应用名和窗口名
                    full_title = f"{window_name} - {owner_name}" if window_name != owner_name else owner_name
                    visible_windows.append(full_title)

            return visible_windows
        except Exception as e:
            print(f"获取macOS窗口列表失败: {e}")
            return []

    def _get_windows_windows(self):
        """获取Windows上的窗口列表"""
        if not WINDOWS_AVAILABLE:
            return []

        try:
            windows = []
            for w in gw.getWindowsWithTitle(""):
                try:
                    _ = w.left  # 强制访问一下属性以触发潜在异常
                    windows.append(w)
                except (OSError, PyGetWindowException):
                    # 无效窗口，跳过
                    continue
            visible = [w for w in windows if w.title.strip() and not w.isMinimized]
            return [w.title for w in visible]
        except Exception as e:
            print(f"获取Windows窗口列表失败: {e}")
            return []

    def _update_loop(self):
        while not self._stop_event.is_set():
            time.sleep(self.interval)
            with self.lock:
                self.keyboard_freq = round(self.keyboard_count / self.interval, 1)
                self.mouse_freq = round(self.mouse_count / self.interval, 1)
                self.keyboard_count = 0
                self.mouse_count = 0

                # 根据平台获取窗口列表
                if PLATFORM == "Darwin":
                    self.window_titles = self._get_windows_macos()
                elif PLATFORM == "Windows":
                    self.window_titles = self._get_windows_windows()
                else:
                    self.window_titles = []

                self.open_apps_count = len(self.window_titles)

    def start(self):
        self.k_listener = keyboard.Listener(on_press=self._keyboard_on_press)
        self.m_listener = mouse.Listener(on_click=self._mouse_on_click)
        self.k_listener.start()
        self.m_listener.start()
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        self.k_listener.stop()
        self.m_listener.stop()
        self.thread.join()

    def get_latest_data(self):
        with self.lock:
            return {
                "keyboard_freq_hz": self.keyboard_freq,
                "mouse_freq_hz": self.mouse_freq,
                "open_apps_count": self.open_apps_count,
                "window_titles": self.window_titles.copy()
            }

# 单例：项目启动时导入一次即可全局使用
monitor = InputWindowMonitor()
