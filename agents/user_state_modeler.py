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
    - 所有打开的窗口标题: {json.dumps(context.get("activity_summary", {}).get("window_titles", []), ensure_ascii=False)}
3.  **用户的屏幕截图**: 附在下面的图片中，展示了用户正在进行的具体工作。
4.  **可用的工具集**:
    ```json
    {json.dumps(tools_config, indent=2, ensure_ascii=False)}
    ```
# 你的任务:
请严格遵循以下思考步骤来形成你的最终建议。

1.  **识别所有任务**: 结合屏幕截图和**所有打开的窗口标题**，全面分析并列出用户当前可能正在处理的**所有任务**。（例如：正在VS Code中编写Python代码、同时在Chrome中查阅API文档、并且后台开着腾讯会议）。

2.  **决策建议逻辑 (三级决策树)**: 请严格遵循以下优先级顺序来生成你的建议：

    **a. 优先级 1: 寻找直接工具解决方案**
       - 遍历你识别出的所有任务，检查**可用工具集**中是否有任何一个工具能够**直接地、完整地**帮助完成其中**一项任务**。
       - **如果找到**，你的建议**必须**聚焦于使用这个工具来解决该特定任务。这是最高优先级。立即形成建议并进入输出格式步骤。

    **b. 优先级 2: 建议任务优先级**
       - **仅当优先级1不满足时**，评估用户是否明显在进行**多项需要高度专注的、不同类型**的任务（例如：编码 + 会议 + 阅读长文档）。
       - **如果用户处于这种高并行状态**，你的建议应该是**帮助用户进行任务优先级排序**。提出一个你认为应该优先处理的任务，并给出简短的理由（例如：“您似乎正在同时编码和开会，建议您先专注于会议以确保有效沟通。”）。
       - 形成此建议后，立即进入输出格式步骤。

    **c. 优先级 3: 提供通用帮助 (最终回退策略)**
       - **仅当优先级1和2都不满足时**（例如，用户只在进行一项无法被工具解决的任务），检查这项任务是否涉及可以被**文件分析**所帮助的活动（例如：编写代码、阅读PDF文档、查看长文本）。
       - **如果发现此类活动**，你的建议应该是**邀请用户上传相关文件**，以便你进行分析、总结或提供帮助。

# 输出格式:
请严格按照以下JSON格式返回你的分析结果，不要包含任何其他解释性文字。
{{
  "user_intent": "一个对用户正在处理的**所有主要任务**的简短、综合性描述。",
  "suggestion_text": "根据你在步骤2中决策出的最终建议，生成一句具体、友好的话告诉用户你可以如何帮助他。",
  "recommended_tool": "如果你的建议是基于**优先级1**（直接工具解决方案），请在此处填写对应的工具名称。如果建议是基于**优先级2或3**，请将此字段的值设为 `null`。",
  "reasoning": "解释你为什么会提出这个建议的简短理由，并明确指出你的决策是基于【优先级1: 工具解决】、【优先级2: 任务排序】还是【优先级3: 文件辅助】。"
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