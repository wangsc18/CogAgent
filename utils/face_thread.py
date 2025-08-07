# utils/face_thread.py
import threading
import os
from utils.realtime_detection.realtime_detection import RealtimeCognitiveLoadDetector

class CognitiveLoadThread(threading.Thread):
    def __init__(self, model_path="utils/realtime_detection/best_resnet3d.pth"):
        super().__init__()
        self.model_path = model_path
        self.detector = None
        self.current_result = None  # 💡 新增共享变量
        self._stop_event = threading.Event()

    def run(self):
        if not os.path.exists(self.model_path):
            print(f"[错误] 模型文件 {self.model_path} 不存在，请先训练模型")
            return

        print("[信息] 启动实时视觉认知负荷检测线程")
        self.detector = RealtimeCognitiveLoadDetector(self.model_path)

        # 使用生成器版本
        for result in self.detector.run_detection():
            self.current_result = result  # 你可以把它保存进共享状态或发信号出去
            print(f"[视觉] 当前认知负荷状态：{result['cognitive_load']} @ {result['timestamp']}")
            if hasattr(self, "_stop_event") and self._stop_event.is_set():
                break


    def get_latest_load(self):
        return self.current_result

    def stop(self):
        self._stop_event.set()

visual_detector = CognitiveLoadThread()