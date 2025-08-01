# utils/activity_monitor.py

import threading
import time
from pynput import keyboard, mouse
import pygetwindow as gw

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

    def _update_loop(self):
        while not self._stop_event.is_set():
            time.sleep(self.interval)
            with self.lock:
                self.keyboard_freq = round(self.keyboard_count / self.interval, 1)
                self.mouse_freq = round(self.mouse_count / self.interval, 1)
                self.keyboard_count = 0
                self.mouse_count = 0

                windows = gw.getWindowsWithTitle("")
                visible = [w for w in windows if w.title.strip() and not w.isMinimized]
                self.open_apps_count = len(visible)
                self.window_titles = [w.title for w in visible]

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
