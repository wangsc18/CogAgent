# agents/user_state_modeler.py
import json
import asyncio
from datetime import datetime
from utils.helpers import take_screenshot, log_message
from langchain_core.messages import HumanMessage
from langchain_core.language_models import BaseLanguageModel
from typing import Dict, Any

class UserStateModeler:
    """
    用户建模器，使用一个加权分数模型来判断是否需要主动服务。
    同时作为一个“分析器Agent”，能够在用户确认后分析其意图并提出建议。
    """
    def __init__(self, observation_period_seconds=30, history_limit=6):
        self.history = []
        self.period = observation_period_seconds
        self.limit = history_limit
        # 【核心】定义分数模型的权重和阈值
        self.weights = {
            "cognitive_load": 0.5, # 认知负荷分数占 50% 权重
            "keyboard": 0.25,      # 键盘行为占 25% 权重
            "mouse": 0.1,        # 鼠标行为占 10% 权重
            "window_switch": 0.15 # 窗口切换占 15% 权重
        }
        self.proactive_threshold = 10 # 当总分超过 50 (满分100) 时，触发主动服务

    def log_current_state_from_data(self, activity: dict):
        """从外部接收活动数据并记录。"""
        timestamp = datetime.now().isoformat()
        self.history.append({"timestamp": timestamp, "activity": activity})
        if len(self.history) > self.limit:
            self.history.pop(0)

    def calculate_proactive_score(self) -> dict:
        """
        计算并返回当前周期的主动服务分数和明细。
        所有单项分数都归一化到 0-100 的范围。
        """
        # --- 1. 获取基础指标 ---
        last_activity = self.history[-1]['activity']
        cognitive_load = last_activity.get("cognitive_load", "low_load")
        confidence = last_activity.get("confidence", 0.0)

        avg_keyboard_hz = sum(item['activity']['keyboard_freq_hz'] for item in self.history) / len(self.history)
        avg_mouse_hz = sum(item['activity']['mouse_freq_hz'] for item in self.history) / len(self.history)
        start_titles = set(self.history[0]['activity'].get('window_titles', []))
        end_titles = set(self.history[-1]['activity'].get('window_titles', []))
        changed_windows_count = len(start_titles.symmetric_difference(end_titles))

        scores = {}
        
        # --- 2. 计算各分项得分 ---
        
        # a) 认知负荷得分 (考虑置信度)
        if cognitive_load == "Low Load":
            # 低负荷：0~33
            scores["cognitive_load"] = int(confidence * 33)
        elif cognitive_load == "Medium Load":
            # 中负荷：34~66
            scores["cognitive_load"] = int(34 + confidence * (66 - 34))
        elif cognitive_load == "High Load":
            # 高负荷：67~100
            scores["cognitive_load"] = int(67 + confidence * (100 - 67))
        else:
            scores["cognitive_load"] = 0

        # b) 键盘得分 (线性映射, 超过8Hz为满分)
        scores["keyboard"] = min(100, (avg_keyboard_hz / 8.0) * 100)

        # c) 鼠标得分 (线性映射, 超过5Hz为满分)
        scores["mouse"] = min(100, (avg_mouse_hz / 5.0) * 100)
        
        # d) 窗口切换得分 (线性映射, 超过5次为满分)
        scores["window_switch"] = min(100, (changed_windows_count / 5.0) * 100)
        
        # --- 3. 计算加权总分 ---
        total_score = (
            scores["cognitive_load"] * self.weights["cognitive_load"] +
            scores["keyboard"] * self.weights["keyboard"] +
            scores["mouse"] * self.weights["mouse"] +
            scores["window_switch"] * self.weights["window_switch"]
        )

        return {
            "total_score": round(total_score, 2),
            "breakdown": {k: round(v, 2) for k, v in scores.items()},
            "is_above_threshold": total_score > self.proactive_threshold,
            "raw_metrics": {
                "cognitive_load": cognitive_load,
                "confidence": confidence,
                "avg_keyboard_hz": avg_keyboard_hz,
                "avg_mouse_hz": avg_mouse_hz,
                "changed_windows_count": changed_windows_count
            }
        }

    def analyze_and_decide(self) -> dict:
        """
        基于分数模型进行分析和决策。
        """
        if len(self.history) < self.limit:
            return {"needs_inquiry": False}

        score_result = self.calculate_proactive_score()

        log_message("--- User State Score ---")
        log_message(f"Total Score: {score_result['total_score']} / {self.proactive_threshold}")
        log_message(f"Breakdown: {json.dumps(score_result['breakdown'])}")
        
        history_to_return = self.history.copy()
        self.history = []

        if not score_result["is_above_threshold"]:
            return {"needs_inquiry": False}

        reason_for_inquiry = f"系统综合评分 ({score_result['total_score']:.0f}) 超过了阈值，表明用户可能需要帮助。"
        
        return {
            "needs_inquiry": True,
            "inquiry_text": "看起来您现在正忙，需要一些帮助吗？",
            "context": {
                "reason": reason_for_inquiry,
                "activity_summary": {
                    "proactive_score": score_result['total_score'],
                    "avg_keyboard_hz": round(score_result['raw_metrics']['avg_keyboard_hz'], 2),
                    "avg_mouse_hz": round(score_result['raw_metrics']['avg_mouse_hz'], 2),
                    "changed_windows_count": score_result['raw_metrics']['changed_windows_count'],
                    "final_cognitive_load": score_result['raw_metrics']['cognitive_load'],
                    "final_confidence": round(score_result['raw_metrics']['confidence'], 2)
                },
                "activity_log": history_to_return
            }
        }

    @staticmethod
    async def analyze_user_context_and_suggest(
        context: Dict[str, Any],
        llm: BaseLanguageModel,
        tools_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        【新增】这是分析器Agent的核心。
        它接收用户确认后的上下文，并调用LLM来分析意图和建议行动。
        """
        log_message("--- Analyzer Agent Started ---")
        summary = context.get("activity_summary", {})
        reason = context.get("reason", "注意到用户似乎很忙。")
        screenshot_b64 = await asyncio.to_thread(take_screenshot)

        analyzer_prompt_text = f"""
你是一个专业的“情境分析与任务建议”AI。你的唯一目标是分析用户的当前状态和屏幕截图，然后从一个给定的工具列表中，建议一个最能帮助用户、降低其认知负荷的具体行动。

# 你的分析依据:
1.  **系统分析报告**: {reason}
2.  **用户活动数据**:
    - 主动服务综合评分: {summary.get('proactive_score', 'N/A')}
    - 最终认知状态判断: {summary.get('final_cognitive_load', 'N/A')} (置信度: {summary.get('final_confidence', 0.0):.0%})
    - 平均键盘/鼠标活动: {summary.get('avg_keyboard_hz', 'N/A')} Hz / {summary.get('avg_mouse_hz', 'N/A')} Hz
    - 窗口变化数: {summary.get('changed_windows_count', 'N/A')}
3.  **用户的屏幕截图**: 附在下面的图片中，展示了用户正在进行的具体工作。
4.  **可用的工具集**:
    ```json
    {json.dumps(tools_config, indent=2, ensure_ascii=False)}
    ```
# 你的任务:
仔细观察屏幕截图，并结合所有文字信息，回答以下问题：
1.  这个用户最有可能在做什么？（例如：正在编写Python代码、阅读一篇长篇PDF报告、调试一个Web应用...）
2.  根据用户的任务，哪一个“可用工具”能够最直接地帮助他/她？
3.  你应该如何向用户提出这个建议？

# 输出格式:
请严格按照以下JSON格式返回你的分析结果，不要包含任何其他解释性文字。
{{
  "user_intent": "一个对用户正在做的事情的简短描述。",
  "suggestion_text": "一句具体、友好的话，告诉用户你可以如何帮助他。例如：'看起来您正在阅读一份很长的PDF，需要我帮您总结一下要点吗？'",
  "recommended_tool": "从工具列表中选择的最合适的工具的名称，例如 'summarize_document'。",
  "reasoning": "解释为什么你推荐这个工具的简短理由。"
}}
"""
        multimodal_content = [
            {"type": "text", "text": analyzer_prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
        ]
        
        # 将多模态内容包装在HumanMessage中，然后传递给LLM
        analyzer_message = HumanMessage(content=multimodal_content)
        
        try:
            log_message("Analyzer Agent invoking LLM...")
            response = await llm.ainvoke([analyzer_message])
            response_content = response.content.strip().lstrip("```json").rstrip("```").strip()
            log_message(f"Analyzer Agent LLM Raw Response: {response_content}")
            
            parsed_response = json.loads(response_content)
            return parsed_response

        except Exception as e:
            log_message(f"Analyzer Agent failed: {e}")
            return {
                "user_intent": "分析失败",
                "suggestion_text": "抱歉，我在分析您的情况时遇到了一个内部错误。",
                "recommended_tool": None,
                "reasoning": str(e)
            }