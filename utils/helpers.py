# utils/helpers.py
import os
import sys
import json
import random
import logging
import base64
import io
from PIL import ImageGrab, Image
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

def optimize_image_for_llm(image: Image.Image, max_width: int = 1280, quality: int = 80) -> str:
    """
    优化图片以减少LLM token消耗。

    优化策略：
    1. 降低分辨率（最大宽度1280px，保持宽高比）
    2. 转换为JPEG格式（比PNG小3-5倍）
    3. 调整质量参数（80%是token和质量的最佳平衡点）

    Args:
        image: PIL Image对象
        max_width: 最大宽度（默认1280px，适合大多数LLM）
        quality: JPEG质量（1-100，默认80）

    Returns:
        优化后的base64编码字符串
    """
    try:
        # 1. 计算缩放比例
        width, height = image.size
        if width > max_width:
            scale = max_width / width
            new_width = max_width
            new_height = int(height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logging.info(f"[图片优化] 分辨率从 {width}x{height} 缩放到 {new_width}x{new_height}")

        # 2. 转换为RGB模式（JPEG不支持透明度）
        if image.mode in ('RGBA', 'LA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        # 3. 保存为JPEG到内存
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)

        # 4. 编码为base64
        encoded = base64.b64encode(buffer.read()).decode('utf-8')

        # 计算压缩比例
        original_size = width * height * 3 / 1024  # 估算原始RGB大小（KB）
        compressed_size = len(encoded) * 0.75 / 1024  # base64解码后的实际大小（KB）
        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

        logging.info(f"[图片优化] 压缩比例: {compression_ratio:.1f}% (估算 {original_size:.1f}KB → {compressed_size:.1f}KB)")

        return encoded

    except Exception as e:
        logging.error(f"[图片优化] 错误: {e}")
        # 降级方案：返回PNG格式
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')


def take_screenshot() -> str:
    """
    截取当前桌面并返回优化后的Base64编码字符串。

    优化措施：
    - 裁剪右侧1000px（去除辅助界面）
    - 降低分辨率到1280px宽度
    - 转换为JPEG格式
    - 质量设为80%

    这些优化可以减少约70-80%的token消耗。
    """
    logging.info("[截图] 正在截取当前桌面...")
    try:
        screenshot = ImageGrab.grab()
        width, height = screenshot.size
        logging.info(f"[截图] 原始尺寸: {width}x{height}")

        # 裁剪：保留左侧 width-1000 区域
        crop_width = max(width - 1000, 1)
        cropped = screenshot.crop((0, 0, crop_width, height))
        logging.info(f"[截图] 裁剪后尺寸: {crop_width}x{height}")

        # 使用优化函数处理图片
        optimized_b64 = optimize_image_for_llm(cropped, max_width=1280, quality=80)

        # 可选：保存一份副本用于调试
        # cropped.save("desktop_screenshot_debug.png")

        return optimized_b64

    except Exception as e:
        logging.error(f"[截图] 错误：无法截图 - {e}")
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
    """实时监测用户活动。"""
    # logging.info("正在监测用户活动...")
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
    
    # log_message_str = (
    #     f"活动数据: "
    #     f"{activity['open_apps_count']}个应用, "
    #     f"键盘频率 {activity['keyboard_freq_hz']}Hz, "
    #     f"鼠标频率 {activity['mouse_freq_hz']}Hz, "
    #     f"认知负荷: {activity['cognitive_load']} (置信度: {activity['confidence']:.2f})"
    # )
    # logging.info(f"{log_message_str}")

    return activity