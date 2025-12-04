# agents/pum_baseline.py
"""
PUM基线模块（对照组）- 用于对比实验

特点：
1. 固定规则参数（不会动态调整）
2. 简单的是/否干预决策（无LLM推理）
3. 通用的帮助询问（无个性化内容）
4. 无认知效益分析（无深度意图推断）

用途：作为对照组，评估"动态规则"和"认知效益策略"的实际效果
"""

from datetime import datetime
from typing import Dict, Any
from utils.helpers import log_message


class PUMBaseline:
    """
    PUM基线模型（对照组）

    使用固定规则参数进行主动服务决策，不进行动态学习和个性化分析。
    """

    def __init__(self, observation_period_seconds=30, history_limit=6):
        """
        Args:
            observation_period_seconds: 观察周期（秒）
            history_limit: 历史记录数量限制
        """
        self.history = []
        self.period = observation_period_seconds
        self.limit = history_limit

        # 【固定规则参数】这些参数在对照组中永不改变
        self.FIXED_WEIGHTS = {
            "cognitive_load": 0.50,    # 认知负荷权重
            "stuck_bonus": 0.30,       # 卡壳信号权重
            "window_switch": 0.10,     # 窗口切换权重
            "flow_signal": 0.20        # 心流信号权重（负向）
        }

        self.FIXED_THRESHOLD = 40.0    # 固定阈值

        # 【通用询问文本】对照组使用固定的、通用的询问
        self.GENERIC_INQUIRY = "看起来您现在正忙，需要一些帮助吗？"

        log_message("=" * 60)
        log_message("【PUM基线模块已启动 - 对照组模式】")
        log_message(f"固定阈值: {self.FIXED_THRESHOLD}")
        log_message(f"固定权重: {self.FIXED_WEIGHTS}")
        log_message(f"通用询问: {self.GENERIC_INQUIRY}")
        log_message("注意：对照组不会进行动态学习和个性化分析")
        log_message("=" * 60)

    def log_current_state_from_data(self, activity: dict):
        """从外部接收活动数据并记录"""
        timestamp = datetime.now().isoformat()
        self.history.append({"timestamp": timestamp, "activity": activity})
        if len(self.history) > self.limit:
            self.history.pop(0)

    def calculate_proactive_score(self) -> dict:
        """
        【固定规则评分】计算主动服务分数

        与实验组的区别：
        - 使用固定的权重参数（不会被规划脑更新）
        - 使用固定的阈值（不会动态调整）
        """
        # 获取基础指标
        last_activity = self.history[-1]['activity']
        cognitive_load = last_activity.get("cognitive_load", "low_load")
        confidence = last_activity.get("confidence", 0.0)

        avg_keyboard_hz = sum(item['activity']['keyboard_freq_hz'] for item in self.history) / len(self.history)
        avg_mouse_hz = sum(item['activity']['mouse_freq_hz'] for item in self.history) / len(self.history)
        start_titles = set(self.history[0]['activity'].get('window_titles', []))
        end_titles = set(self.history[-1]['activity'].get('window_titles', []))
        changed_windows_count = len(start_titles.symmetric_difference(end_titles))

        scores = {}

        # 计算各分项得分（与实验组相同的计算逻辑）

        # a) 认知负荷得分
        if cognitive_load == "Low Load":
            scores["cognitive_load"] = int(confidence * 33)
        elif cognitive_load == "Medium Load":
            scores["cognitive_load"] = int(34 + confidence * (66 - 34))
        elif cognitive_load == "High Load":
            scores["cognitive_load"] = int(67 + confidence * (100 - 67))
        else:
            scores["cognitive_load"] = 0

        # b) "卡壳"信号分
        is_stuck = (scores["cognitive_load"] > 60) and (avg_keyboard_hz < 0.5 and avg_mouse_hz < 0.5)
        scores["stuck_signal"] = 100 if is_stuck else 0

        # c) "心流"信号分
        keyboard_flow = min(100, (avg_keyboard_hz / 8.0) * 100)
        mouse_flow = min(100, (avg_mouse_hz / 5.0) * 50)
        scores["flow_signal"] = (keyboard_flow * 0.7) + (mouse_flow * 0.3)

        # d) 窗口切换得分
        scores["window_switch"] = min(100, (changed_windows_count / 5.0) * 100)

        # 【关键差异】使用固定权重计算总分
        total_score = (
            scores["cognitive_load"] * self.FIXED_WEIGHTS["cognitive_load"] +
            scores["stuck_signal"] * self.FIXED_WEIGHTS["stuck_bonus"] +
            scores["window_switch"] * self.FIXED_WEIGHTS["window_switch"] -
            scores["flow_signal"] * self.FIXED_WEIGHTS["flow_signal"]
        )

        return {
            "total_score": round(total_score, 2),
            "breakdown": {k: round(v, 2) for k, v in scores.items()},
            "is_above_threshold": total_score > self.FIXED_THRESHOLD,
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
        【对照组决策】基于固定规则进行简单的二元决策

        与实验组的区别：
        1. 不使用LLM进行推理
        2. 不进行战略分析
        3. 不个性化询问内容
        4. 不进行认知效益分析
        """
        if len(self.history) < self.limit:
            return {"needs_inquiry": False}

        score_result = self.calculate_proactive_score()

        log_message("--- PUM Baseline Score (对照组-固定规则) ---")
        log_message(f"Total Score: {score_result['total_score']} / {self.FIXED_THRESHOLD}")
        log_message(f"Breakdown: {score_result['breakdown']}")
        log_message(f"Fixed Weights: {self.FIXED_WEIGHTS}")
        log_message(f"Decision: {'INTERVENE' if score_result['is_above_threshold'] else 'WAIT'}")

        history_to_return = self.history.copy()
        self.history = []

        if not score_result["is_above_threshold"]:
            return {"needs_inquiry": False}

        # 【关键差异】使用通用的固定询问文本，不进行个性化
        inquiry_text = self.GENERIC_INQUIRY

        reason_for_inquiry = (
            f"【对照组】系统评分 ({score_result['total_score']:.0f}) "
            f"超过了固定阈值 ({self.FIXED_THRESHOLD})，触发主动服务。"
        )

        return {
            "needs_inquiry": True,
            "inquiry_text": inquiry_text,  # 通用询问
            "context": {
                "reason": reason_for_inquiry,
                "experiment_group": "baseline",  # 标记为对照组
                "activity_summary": {
                    "proactive_score": score_result['total_score'],
                    "fixed_threshold": self.FIXED_THRESHOLD,
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
    def generate_simple_suggestion(context: Dict[str, Any] = None) -> Dict[str, str]:
        """
        【对照组帮助生成】生成简单的通用帮助建议

        与实验组的区别：
        1. 不进行认知效益分析
        2. 不使用LLM推理用户意图
        3. 不考虑用户认知状态
        4. 返回通用的、固定的帮助内容

        Args:
            context: 用户上下文（对照组不使用，仅保持接口一致）

        Returns:
            包含通用建议的字典
        """
        # 显式标记context未使用（对照组不需要上下文信息）
        _ = context
        log_message("=" * 60)
        log_message("【PUM基线 - 对照组帮助生成】")
        log_message("注意：对照组不进行认知效益分析，返回通用帮助")
        log_message("=" * 60)

        # 【固定的通用帮助内容】
        generic_response = {
            "user_task": "用户任务（对照组不分析）",
            "user_intent": "用户意图（对照组不推断）",
            "obstacle": "未分析",
            "candidate_interventions": [],
            "selected_intervention": {
                "suggestion_text": (
                    "我注意到您可能需要帮助。以下是一些通用建议：\n"
                    "1. 如果遇到技术问题，可以尝试查看文档或搜索相关资料\n"
                    "2. 如果需要数据分析，可以使用表格或图表工具\n"
                    "3. 如果需要整理信息，可以使用笔记或文档工具\n\n"
                    "请告诉我具体需要什么帮助。"
                ),
                "recommended_tool": None,
                "intervention_type": "generic_baseline",
                "offloading_benefit": 0,  # 对照组不计算
                "interaction_cost": 0,    # 对照组不计算
                "success_probability": 0.0,  # 对照组不计算
                "net_cognitive_benefit": 0   # 对照组不计算
            },
            "reasoning": "【对照组模式】使用固定的通用帮助内容，不进行个性化分析",
            "experiment_group": "baseline"
        }

        log_message("✓ 已返回通用帮助建议（对照组）")

        return generic_response
