import cv2
import torch
import numpy as np
import time
import platform
from collections import deque
from torchvision import transforms
from utils.realtime_detection.model import get_resnet3d

import os
import sys
from pathlib import Path

# 根据平台导入不同的模块
PLATFORM = platform.system()

if PLATFORM == "Windows":
    try:
        import site
        site_packages = next(p for p in sys.path if "site-packages" in p)
        dll_path = Path(site_packages) / "pywin32_system32"
        if dll_path.exists():
            os.add_dll_directory(str(dll_path))

        import win32gui
        WINDOWS_AVAILABLE = True
    except Exception as e:
        print(f"警告: Windows API 加载失败: {e}")
        WINDOWS_AVAILABLE = False
elif PLATFORM == "Darwin":  # macOS
    try:
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        MACOS_AVAILABLE = True
    except ImportError:
        print("警告: macOS窗口管理模块未安装")
        MACOS_AVAILABLE = False
else:
    print(f"警告: 平台 {PLATFORM} 可能不完全支持")

# 键鼠监控使用跨平台的库 pynput (支持 macOS/Windows/Linux)
try:
    from pynput import keyboard, mouse
    INPUT_MONITOR_AVAILABLE = True
except ImportError:
    print("警告: pynput 模块未安装，输入监控将不可用")
    print("请运行: pip install pynput")
    INPUT_MONITOR_AVAILABLE = False

class InputMonitor:
    """统计鼠标和键盘输入次数 (使用 pynput 实现跨平台监控)"""
    def __init__(self):
        self.reset()
        self.running = False
        self.keyboard_listener = None
        self.mouse_listener = None

    def reset(self):
        self.mouse_clicks = 0
        self.key_presses = 0

    def start(self):
        if not INPUT_MONITOR_AVAILABLE:
            print("输入监控不可用，跳过启动")
            return
        self.running = True

        # 启动键盘监听器
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self.keyboard_listener.start()

        # 启动鼠标监听器
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self.mouse_listener.start()

    def stop(self):
        self.running = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()

    def _on_key_press(self, _key):
        """键盘按键按下事件处理"""
        if self.running:
            self.key_presses += 1

    def _on_mouse_click(self, _x, _y, _button, pressed):
        """鼠标点击事件处理"""
        if self.running and pressed:  # 只统计按下事件，不统计释放
            self.mouse_clicks += 1

def get_active_window_info():
    """获取当前活跃窗口标题和坐标（跨平台）"""
    if PLATFORM == "Windows" and WINDOWS_AVAILABLE:
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            return {'title': title, 'rect': rect}
        except Exception as e:
            print(f"获取Windows窗口信息失败: {e}")
            return {'title': 'Unknown', 'rect': (0, 0, 0, 0)}
    elif PLATFORM == "Darwin" and MACOS_AVAILABLE:
        try:
            # 获取最前面的窗口
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID
            )
            if window_list:
                # 第一个通常是最前面的窗口
                front_window = window_list[0]
                title = front_window.get('kCGWindowName', 'Unknown')
                owner = front_window.get('kCGWindowOwnerName', '')
                bounds = front_window.get('kCGWindowBounds', {})
                rect = (
                    int(bounds.get('X', 0)),
                    int(bounds.get('Y', 0)),
                    int(bounds.get('X', 0) + bounds.get('Width', 0)),
                    int(bounds.get('Y', 0) + bounds.get('Height', 0))
                )
                full_title = f"{title} - {owner}" if title and owner else (title or owner or 'Unknown')
                return {'title': full_title, 'rect': rect}
        except Exception as e:
            print(f"获取macOS窗口信息失败: {e}")
            return {'title': 'Unknown', 'rect': (0, 0, 0, 0)}
    else:
        return {'title': 'Unknown (Platform not supported)', 'rect': (0, 0, 0, 0)}

class RealtimeCognitiveLoadDetector:
    def __init__(self, model_path, face_detector_path='utils/realtime_detection/models/face_detector',
                 segment_seconds=30, sample_frames=32, frame_size=112, predict_interval=30, headless=False):
        self.predict_interval = predict_interval
        self.sample_frames = sample_frames
        self.frame_size = frame_size
        self.fps = 25  # 假设摄像头25fps
        self.frames_per_segment = int(self.fps * segment_seconds)
        self.input_monitor = InputMonitor()
        self.headless = headless  # headless 模式不显示 GUI 窗口
        self._stop_event = None  # 用于外部控制停止

        # 加载认知负荷检测模型 - 支持 CUDA, MPS (Apple Silicon), 或 CPU
        if torch.cuda.is_available():
            self.device = torch.device('cuda')
            print("使用 CUDA GPU")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            self.device = torch.device('mps')
            print("使用 Apple Silicon MPS")
        else:
            self.device = torch.device('cpu')
            print("使用 CPU")

        self.model = get_resnet3d(num_classes=3, pretrained=False).to(self.device)
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval()

        # 加载人脸检测模型
        self.face_detector = self.load_face_detector(face_detector_path)

        # 图像预处理
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((frame_size, frame_size)),
            transforms.ToTensor()
        ])

        # 帧缓存
        self.frame_buffer = deque(maxlen=self.frames_per_segment)

        # 标签映射
        self.label_names = {0: 'Low Load', 1: 'Medium Load', 2: 'High Load'}

        mode_str = "headless 模式（无 GUI）" if self.headless else "GUI 模式"
        print(f"实时认知负荷检测初始化完成 ({mode_str})")

    def load_face_detector(self, face_detector_path):
        """加载OpenCV DNN人脸检测模型"""
        try:
            prototxt_path = f"{face_detector_path}/deploy.prototxt"
            model_path = f"{face_detector_path}/res10_300x300_ssd_iter_140000.caffemodel"
            if not (os.path.exists(prototxt_path) and os.path.exists(model_path)):
                print("警告：人脸检测模型文件不存在")
                return None
            net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
            print("人脸检测模型加载成功")
            return net
        except Exception as e:
            print(f"人脸检测模型加载失败：{e}")
            return None

    def detect_and_crop_face(self, frame):
        """检测并裁剪人脸区域，返回人脸区域和边界框坐标"""
        if self.face_detector is None:
            return frame, None

        try:
            blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0), False, False)
            self.face_detector.setInput(blob)
            detections = self.face_detector.forward()

            max_confidence = 0
            best_face = None
            best_box = None

            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                if confidence > 0.5:
                    if confidence > max_confidence:
                        max_confidence = confidence
                        h, w = frame.shape[:2]
                        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                        x1, y1, x2, y2 = box.astype(int)
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        if x2 > x1 and y2 > y1:
                            best_face = frame[y1:y2, x1:x2]
                            best_box = (x1, y1, x2, y2)

            return best_face if best_face is not None else frame, best_box
        except Exception:
            return frame, None

    def preprocess_frames(self, frames):
        """预处理帧序列"""
        if len(frames) < self.sample_frames:
            return None

        # 等间隔采样
        indices = np.linspace(0, len(frames)-1, self.sample_frames, dtype=int)
        sampled_frames = []

        for idx in indices:
            frame = frames[int(idx)]  # 确保索引为int类型
            # 人脸检测与裁剪
            face_frame, _ = self.detect_and_crop_face(frame)
            # 预处理
            face_frame = cv2.cvtColor(face_frame, cv2.COLOR_BGR2RGB)
            face_frame = self.transform(face_frame)
            sampled_frames.append(face_frame)

        return torch.stack(sampled_frames)  # [32, 3, 112, 112]

    def predict_cognitive_load(self, frames_tensor):
        """预测认知负荷"""
        with torch.no_grad():
            frames_tensor = frames_tensor.unsqueeze(0).to(self.device)  # [1, 32, 3, 112, 112]
            frames_tensor = frames_tensor.permute(0, 2, 1, 3, 4)  # [1, 3, 32, 112, 112]
            logits = self.model(frames_tensor)
            probabilities = torch.softmax(logits, dim=1)
            predicted_class = int(torch.argmax(logits, dim=1).item())  # 确保为int类型
            confidence = probabilities[0, predicted_class].item()

            return predicted_class, confidence

    def run_detection(self):
        """运行实时检测"""
        cap = cv2.VideoCapture(0)  # 打开摄像头

        if not cap.isOpened():
            print("无法打开摄像头")
            return

        if self.headless:
            print("实时认知负荷检测已启动 (headless 模式)")
            print("通过外部信号或线程控制停止")
        else:
            print("实时认知负荷检测已启动")
            print("按 'q' 键退出")

        self.input_monitor.start()  # 启动输入监控

        last_prediction_time = 0
        current_load = "Waiting for data..."
        current_confidence = 0.0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("无法读取摄像头画面")
                    break

                # 添加帧到缓存
                self.frame_buffer.append(frame.copy())

                # 每predict_interval秒进行一次预测
                current_time = time.time()
                if (len(self.frame_buffer) >= self.frames_per_segment and
                    current_time - last_prediction_time >= self.predict_interval):

                    # 取最近的 frames_per_segment 帧
                    frames_tensor = self.preprocess_frames(list(self.frame_buffer)[-self.frames_per_segment:])
                    if frames_tensor is not None:
                        predicted_class, confidence = self.predict_cognitive_load(frames_tensor)
                        current_load = self.label_names[predicted_class]
                        current_confidence = confidence
                        last_prediction_time = current_time

                        # 获取活跃窗口信息
                        window_info = get_active_window_info()
                        # 获取输入统计
                        mouse_clicks = self.input_monitor.mouse_clicks
                        key_presses = self.input_monitor.key_presses

                        # 结构化输出
                        result = {
                            "cognitive_load": current_load,
                            "confidence": round(confidence, 3),
                            "active_window": window_info,
                            "mouse_clicks": mouse_clicks,
                            "key_presses": key_presses,
                            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
                        }

                        yield result

                        self.input_monitor.reset()

                # 在画面上显示结果 (仅在非 headless 模式)
                if not self.headless:
                    # 绘制检测框
                    if self.face_detector is not None:
                        _, face_box = self.detect_and_crop_face(frame)
                        if face_box is not None:  # 检测到人脸
                            x1, y1, x2, y2 = face_box
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # 显示文本信息
                    cv2.putText(frame, f"Cognitive Load: {current_load}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.putText(frame, f"Confidence: {current_confidence:.3f}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (147,20,255), 2)
                    cv2.putText(frame, f"Buffer: {len(self.frame_buffer)}/{self.frames_per_segment}", (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

                    # 显示画面
                    cv2.imshow('Real-time cognitive load detection', frame)

                    # 检查按键
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                else:
                    # headless 模式：检查停止信号
                    if self._stop_event is not None and self._stop_event.is_set():
                        break
                    # 添加小延迟避免 CPU 占用过高
                    time.sleep(0.01)

        finally:
            self.input_monitor.stop()
            cap.release()
            if not self.headless:
                cv2.destroyAllWindows()

if __name__ == "__main__":
    import os

    # 检查模型文件
    model_path = 'utils/realtime_detection/best_resnet3d.pth'
    if not os.path.exists(model_path):
        print(f"错误：模型文件 {model_path} 不存在")
        print("请先训练模型并保存为 best_resnet3d.pth")
    else:
        detector = RealtimeCognitiveLoadDetector(model_path)
        for _ in detector.run_detection():
            pass
