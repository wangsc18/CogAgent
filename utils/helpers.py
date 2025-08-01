# utils/helpers.py
import os
import sys
import json
import random
import logging
import base64
from PIL import ImageGrab
from utils.activity_monitor import monitor
from utils.face_thread import visual_detector

def setup_logging():
    os.makedirs('memory', exist_ok=True)  # 自动创建memory目录
    """配置日志记录到文件和控制台。"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('memory/workflow_run.log', mode='w', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def log_message(message: str):
    """
    一个简单的日志记录函数，只负责打印到日志。
    它不再修改state对象，以避免依赖和错误。
    """
    logging.info(message)

def load_user_habits() -> dict:
    """
    加载并返回用户习惯的JSON数据。
    如果文件不存在或内容为空，则返回一个空字典。
    """
    habit_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "user_habits.json")
    print(f"Loading user habits from {habit_file_path}")
    if os.path.exists(habit_file_path):
        with open(habit_file_path, 'r', encoding='utf-8') as f:
            try:
                print(f"Loading user habits from {habit_file_path}")
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON from {habit_file_path}. No user habits will be loaded.")
                return {}
    return {}

def take_screenshot() -> str:
    """截取当前桌面并返回Base64编码的字符串（去掉右侧750px）。"""
    logging.info("[截图] 正在截取当前桌面...")
    try:
        path = "desktop_screenshot.png"
        screenshot = ImageGrab.grab()
        width, height = screenshot.size
        # 裁剪：保留左侧 width-750 区域
        crop_width = max(width - 750, 1)
        cropped = screenshot.crop((0, 0, crop_width, height))
        cropped.save(path)
        logging.info(f"[截图] 截图已保存到 {path}")
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logging.error(f"错误：无法截图 - {e}")
        return ""
    

def get_visual_cognitive_load():
    if visual_detector and visual_detector.get_latest_load():
        return visual_detector.get_latest_load()
    else:
        return {
            "cognitive_load": "waiting...",
            "confidence": 0.0
        }

def get_real_time_user_activity() -> dict:
    """模拟实时监测用户活动，数据带有一定随机性。"""
    logging.info("[模拟] 正在监测用户活动...")
    # 键鼠数据
    data = monitor.get_latest_data()
    # 视觉数据
    vision_data = get_visual_cognitive_load()
    cognitive_load = vision_data["cognitive_load"]
    confidence = vision_data["confidence"]

    # # 随机生成应用数量、键盘和鼠标频率
    # open_apps_count = random.randint(8, 15)
    # keyboard_freq_hz = round(random.uniform(3.0, 8.0), 1)
    # mouse_freq_hz = round(random.uniform(1.0, 4.0), 1)

    # # 随机选择窗口标题
    # all_titles = [
    #     "main.py - CogAgent - Visual Studio Code",
    #     "Terminal - pwsh.exe - Visual Studio Code",
    #     "Google Chrome - LangChain AgentState Documentation",
    #     "WeChat",
    #     "File Explorer - C:\\Users\\...",
    #     "Spotify - Now Playing",
    #     "PowerPoint - 会议汇报.pptx",
    #     "Word - 论文.docx",
    #     "Outlook - 邮箱",
    #     "QQ",
    #     "Notepad++ - notes.txt"
    # ]
    # window_titles = random.sample(all_titles, k=random.randint(3, 6))

    # activity = {
    #     "open_apps_count": open_apps_count,
    #     "keyboard_freq_hz": keyboard_freq_hz,
    #     "mouse_freq_hz": mouse_freq_hz,
    #     "window_titles": window_titles
    # }



    activity = {
            "open_apps_count": data["open_apps_count"],
            "keyboard_freq_hz": data["keyboard_freq_hz"],
            "mouse_freq_hz": data["mouse_freq_hz"],
            "window_titles": data["window_titles"],
            "cognitive_load": cognitive_load,
            "confidence": confidence
        }
    
    log_message_str = (
        f"活动数据: "
        f"{activity['open_apps_count']}个应用, "
        f"键盘频率 {activity['keyboard_freq_hz']}Hz, "
        f"鼠标频率 {activity['mouse_freq_hz']}Hz, "
        f"认知负荷: {activity['cognitive_load']} (置信度: {activity['confidence']:.2f})"
    )
    logging.info(f"[模拟] {log_message_str}")

    return activity