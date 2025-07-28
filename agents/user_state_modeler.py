# agents/user_state_modeler.py (最终正确版)
import json
from datetime import datetime
from utils.helpers import get_real_time_user_activity, take_screenshot

class UserStateModeler:
    """
    用户建模器，它会利用历史数据，并在需要时触发一个带上下文的用户确认。
    """
    def __init__(self, observation_period_seconds=30, history_limit=6):
        self.history = []
        self.period = observation_period_seconds
        self.limit = history_limit

    def log_current_state_from_data(self, activity: dict):
        """从外部接收活动数据并记录。"""
        timestamp = datetime.now().isoformat()
        self.history.append({"timestamp": timestamp, "activity": activity})
        if len(self.history) > self.limit:
            self.history.pop(0)

    def analyze_and_decide(self) -> dict:
        """
        分析历史数据。如果需要，返回一个包含决策和【历史上下文】的字典。
        """
        if len(self.history) < self.limit:
            return {"needs_inquiry": False}

        avg_keyboard_hz = sum(item['activity']['keyboard_freq_hz'] for item in self.history) / len(self.history)
        start_titles = set(self.history[0]['activity']['window_titles'])
        end_titles = set(self.history[-1]['activity']['window_titles'])
        changed_windows_count = len(start_titles.symmetric_difference(end_titles))

        needs_inquiry = False
        if avg_keyboard_hz > 5.0 and changed_windows_count >= 4:
            needs_inquiry = True

        history_to_return = self.history.copy()
        self.history = [] # 清空历史，为下个周期做准备

        if not needs_inquiry:
            return {"needs_inquiry": False}

        # 【关键修正】如果需要询问，我们返回决策和完整的历史上下文
        return {
            "needs_inquiry": True,
            "inquiry_text": "看起来您现在正忙，需要一些帮助吗？",
            "context": {
                "activity_summary": {
                    "period_seconds": self.period,
                    "avg_keyboard_hz": round(avg_keyboard_hz, 2),
                    "changed_windows_count": changed_windows_count
                },
                "activity_log": history_to_return
            }
        }

    @staticmethod
    def format_prompt_after_confirmation(context: dict) -> list:
        """
        【关键修正】这是一个静态方法，它接收包含历史数据的上下文，
        然后进行截图，并生成最终的多模态Prompt。
        """
        print("User confirmed. Taking screenshot and generating full prompt with historical context.")
        summary = context.get("activity_summary", {})
        screenshot_b64 = take_screenshot()
        
        text_prompt = f"""
我刚刚确认了需要帮助。

根据对我过去 {summary.get('period_seconds', '30')} 秒活动的分析，我的状态如下：
- 我的平均打字速度很快 (大约 {summary.get('avg_keyboard_hz', 'N/A')} Hz)。
- 我似乎在不同的任务窗口间频繁切换 (大约有 {summary.get('changed_windows_count', 'N/A')} 个窗口发生了变化)。

这是我当前屏幕的截图，它展示了我正在做的事情。请结合上述的活动上下文和这张截图，综合分析我当前的情况，并提供一些具体的建议。
"""
        
        multimodal_content = [
            {"type": "text", "text": text_prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
            }
        ]
        return multimodal_content