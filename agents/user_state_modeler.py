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
            "cognitive_load": 0.6, # 认知负荷作为基础分的权重，提升至60%
            "stuck_bonus": 1.5,  # “卡壳信号”的奖励乘数，非常重要
            "flow_signal": 0.5, # “心流”状态下的惩罚乘数
            "window_switch": 0.4 # “分心信号”（窗口切换）的权重
        }
        self.proactive_threshold = 50 # 阈值

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

        # b) “卡壳”信号分 (Stuck Signal Score)
        is_stuck = (scores["cognitive_load"] > 60) and (avg_keyboard_hz < 0.5 and avg_mouse_hz < 0.5)
        scores["stuck_signal"] = 100 if is_stuck else 0 # 如果卡壳，信号分为满分100

        # c) “心流”信号分 (Flow Signal Score)
        # 将键盘和鼠标活动归一化到一个0-100的“心流”分数
        keyboard_flow = min(100, (avg_keyboard_hz / 8.0) * 100)
        mouse_flow = min(100, (avg_mouse_hz / 5.0) * 50) # 鼠标权重较低
        scores["flow_signal"] = (keyboard_flow * 0.7) + (mouse_flow * 0.3) # 键盘占70%
        
        # d) 窗口切换得分 (线性映射, 超过5次为满分)
        scores["window_switch"] = min(100, (changed_windows_count / 5.0) * 100)
        
        # --- 3. 计算加权总分 ---
        total_score = (
            scores["cognitive_load"] * self.weights["cognitive_load"] +
            scores["stuck_signal"] * self.weights["stuck_bonus"] +
            scores["window_switch"] * self.weights["window_switch"] -
            scores["flow_signal"] * self.weights["flow_signal"]
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
                "changed_windows_count": changed_windows_count,
                "is_stuck": is_stuck
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
你是一个专业的“AI认知伙伴”。你的核心能力是运用**心智理论（Theory of Mind）**来**建模和推断**用户的内在状态，包括他们的**意图、目标、知识状态和认知负荷**。你的最终目标是基于这个心智模型，从可用工具中建议一个最能**预判用户需求、减轻其心智负担**的具体行动。

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

# 你的任务: 运用心智理论进行决策
请严格遵循以下思考步骤，构建一个关于用户心智状态的假设，并据此形成你的最终建议。

**步骤 1: 行为解读与意图推断 (Belief & Intention Inference)**
1.  **识别用户的显性任务 (Task Identification)**: 结合屏幕截图和窗口标题，全面分析并列出用户当前正在处理的**所有任务**。
2.  **推断用户的隐性意图 (Intent Inference)**: 思考：“用户做这些任务，**最终想达成什么目标？**” (例如：用户在VS Code中编码并在Chrome中查文档，其意图是“完成一个特定的编程功能”或“修复一个bug”)。
3.  **评估用户的认知状态 (Cognitive State Assessment)**: 结合**“推断的认知状态”**和**行为指标**，判断用户当前是**流畅、专注**，还是**卡顿、分心、或高负荷**？

**步骤 2: 生成建议的决策框架 (ToM-driven Decision Making)**
请严格遵循以下优先级顺序来生成你的建议：

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
  "user_intent": "对用户当前**核心意图**的简短推断 (基于步骤1.2)。",
  "user_tasks": "一个对用户正在处理的**所有主要任务**的简短、综合性描述。",
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
                "user_tasks": "无法识别用户当前任务",
                "suggestion_text": "抱歉，我在分析您的情况时遇到了一个内部错误。",
                "recommended_tool": None,
                "reasoning": str(e)
            }