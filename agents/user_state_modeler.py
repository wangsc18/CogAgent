# agents/user_state_modeler.py (最终正确版)
import json
from datetime import datetime
from utils.helpers import take_screenshot, log_message

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
        
        # 获取最近一次的直接认知状态推断
        last_activity = self.history[-1]['activity']
        cognitive_load = last_activity.get("cognitive_load", "low_load")
        confidence = last_activity.get("confidence", 0.0)

        # 计算整个周期的行为指标作为辅助
        avg_keyboard_hz = sum(item['activity']['keyboard_freq_hz'] for item in self.history) / len(self.history)
        avg_mouse_hz = sum(item['activity']['mouse_freq_hz'] for item in self.history) / len(self.history)
        start_titles = set(self.history[0]['activity'].get('window_titles', []))
        end_titles = set(self.history[-1]['activity'].get('window_titles', []))
        changed_windows_count = len(start_titles.symmetric_difference(end_titles))

        # 通过log_message打印到memory中
        log_message_str = (
            f"认知负荷: {cognitive_load} (置信度: {confidence:.2f})",
            f"平均键盘频率: {avg_keyboard_hz:.2f} Hz",
            f"平均鼠标频率: {avg_mouse_hz:.2f} Hz",
            f"窗口变化数: {changed_windows_count}"
        )
        log_message("--- UserState ---")
        log_message(log_message_str)

        needs_inquiry = False
        reason_for_inquiry = ""

        # 规则一：高置信度的高负荷状态 (最强信号)
        if cognitive_load == 'high_load' and confidence > 0.6:
            needs_inquiry = True
            reason_for_inquiry = f"检测到用户可能处于高认知负荷状态（置信度: {confidence:.0%})。"
        
        # 规则二：中等置信度的高负荷，但行为指标也异常 (多个信号佐证)
        elif cognitive_load == 'medium_load' and confidence > 0.6 and (avg_keyboard_hz > 5.0 or avg_mouse_hz > 3.5 or changed_windows_count > 3):
            needs_inquiry = True
            reason_for_inquiry = f"检测到用户可能处于中等认知负荷状态，并且似乎持续处于比较忙碌的状态。"

        elif not needs_inquiry and (avg_keyboard_hz > 5.5 or avg_mouse_hz > 4.0) and changed_windows_count >= 5:
            needs_inquiry = True
            reason_for_inquiry = "检测到用户的键盘活动非常频繁，并且在多个应用间快速切换。"


        history_to_return = self.history.copy()
        self.history = [] # 清空历史，为下个周期做准备

        if not needs_inquiry:
            return {"needs_inquiry": False}

        # 如果需要询问，我们返回决策和完整的历史上下文
        return {
            "needs_inquiry": True,
            "inquiry_text": "看起来您现在正忙，需要一些帮助吗？",
             "context": {
                "reason": reason_for_inquiry, # <-- 将触发原因传递下去
                "activity_summary": {
                    "period_seconds": self.period,
                    "avg_keyboard_hz": round(avg_keyboard_hz, 2),
                    "changed_windows_count": changed_windows_count,
                    "final_cognitive_load": cognitive_load,
                    "final_confidence": round(confidence, 2)
                },
                "activity_log": history_to_return
            }
        }

    @staticmethod
    def format_prompt_after_confirmation(context: dict) -> list:
        """
        这是一个静态方法，它接收包含历史数据的上下文，
        然后进行截图，并生成最终的多模态Prompt。
        """
        print("User confirmed. Taking screenshot and generating full prompt with historical context.")
        summary = context.get("activity_summary", {})
        reason = context.get("reason", "注意到用户似乎很忙。")
        screenshot_b64 = take_screenshot()
        
        text_prompt = f"""
我刚刚确认了需要帮助。

**系统分析**: {reason}

**附加的活动总结**:
- 平均键盘速度: {summary.get('avg_keyboard_hz', 'N/A')} Hz
- 平均鼠标速度: {summary.get('avg_mouse_hz', 'N/A')} Hz
- 窗口变化数: {summary.get('changed_windows_count', 'N/A')}

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