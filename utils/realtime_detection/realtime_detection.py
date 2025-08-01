import cv2
import torch
import numpy as np
import time
from collections import deque
from torchvision import transforms
from utils.realtime_detection.model import get_resnet3d

import threading

import os
import sys
from pathlib import Path
import site
# # 手动添加 DLL 路径
# dll_path = Path(sys.prefix)  # sys.prefix 通常就是 .venv 目录
# os.add_dll_directory(str(dll_path))
site_packages = next(p for p in sys.path if "site-packages" in p)
dll_path = Path(site_packages) / "pywin32_system32"

if not dll_path.exists():
    raise FileNotFoundError(f"❌ DLL 路径不存在: {dll_path}")
else:
    os.add_dll_directory(str(dll_path))

import win32gui
import win32con
import win32api

class InputMonitor:
    """统计鼠标和键盘输入次数"""
    def __init__(self):
        self.reset()
        self.running = False

    def reset(self):
        self.mouse_clicks = 0
        self.key_presses = 0

    def start(self):
        self.running = True
        threading.Thread(target=self._monitor, daemon=True).start()

    def stop(self):
        self.running = False

    def _monitor(self):
        import keyboard
        import mouse
        mouse.hook(lambda e: self._on_mouse(e))
        keyboard.hook(lambda e: self._on_key(e))
        while self.running:
            time.sleep(0.1)

    def _on_mouse(self, event):
        if event.event_type == 'down':
            self.mouse_clicks += 1

    def _on_key(self, event):
        if event.event_type == 'down':
            self.key_presses += 1

def get_active_window_info():
    """获取当前活跃窗口标题和坐标"""
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    rect = win32gui.GetWindowRect(hwnd)
    return {'title': title, 'rect': rect}

class RealtimeCognitiveLoadDetector:
    def __init__(self, model_path, face_detector_path='utils/realtime_detection/models/face_detector', 
                 segment_seconds=30, sample_frames=32, frame_size=112):
        self.segment_seconds = segment_seconds
        self.sample_frames = sample_frames
        self.frame_size = frame_size
        self.fps = 25  # 假设摄像头25fps
        self.frames_per_segment = int(self.fps * segment_seconds)
        self.input_monitor = InputMonitor()
        
        # 加载认知负荷检测模型
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
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
        except Exception as e:
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
        
        print("实时认知负荷检测已启动")
        print("按 'q' 键退出")
        
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
                
                # 每30秒进行一次预测
                current_time = time.time()
                if (len(self.frame_buffer) >= self.frames_per_segment and 
                    current_time - last_prediction_time >= self.segment_seconds):
                    
                    # 预处理帧
                    frames_tensor = self.preprocess_frames(list(self.frame_buffer))
                    if frames_tensor is not None:
                        # 预测
                        predicted_class, confidence = self.predict_cognitive_load(frames_tensor)
                        current_load = self.label_names[predicted_class]
                        current_confidence = confidence
                        last_prediction_time = current_time
                        
                        print(f"检测结果: {current_load} (置信度: {confidence:.3f})")
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
                        print("结构化认知负荷与环境描述：", result)

                        yield result  # 返回结果

                        # 重置输入统计
                        self.input_monitor.reset()
                
                # 在画面上显示结果
                # 绘制检测框
                if self.face_detector is not None:
                    face_frame, face_box = self.detect_and_crop_face(frame)
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
        
        finally:
            self.input_monitor.stop()
            cap.release()
            cv2.destroyAllWindows()

if __name__ == "__main__":
    import os
    
    # 检查模型文件
    model_path = 'best_resnet3d.pth'
    if not os.path.exists(model_path):
        print(f"错误：模型文件 {model_path} 不存在")
        print("请先训练模型并保存为 best_resnet3d.pth")
    else:
        detector = RealtimeCognitiveLoadDetector(model_path)
        detector.run_detection() 