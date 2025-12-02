# utils/dynamic_rules.py
"""
动态规则管理器 - "快思慢想"系统的数据层

负责加载、保存和管理主动服务的规则参数。
执行脑（快思）读取规则进行快速决策，规划脑（慢想）基于用户反馈更新规则。
"""

import json
import os
from datetime import datetime
from utils.helpers import log_message


class DynamicRulesManager:
    """
    动态规则管理器，负责加载、保存和管理主动服务的规则参数。
    这是"快思慢想"系统的核心数据层。
    """
    def __init__(self, config_path: str = None, strategic_guidance_path: str = None):
        if config_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            config_path = os.path.join(project_root, "config", "dynamic_rules.json")

        if strategic_guidance_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            strategic_guidance_path = os.path.join(project_root, "config", "strategic_guidance.json")

        self.config_path = config_path
        self.strategic_guidance_path = strategic_guidance_path
        self.rules = self._load_rules()
        self.strategic_guidance = self._load_strategic_guidance()

    def _load_rules(self) -> dict:
        """从配置文件加载规则，如果文件不存在则返回默认规则"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                    log_message(f"[DynamicRules] 已加载动态规则，版本={rules.get('version')}, 接受率={rules.get('acceptance_rate', 0):.1%}")
                    return rules
        except Exception as e:
            log_message(f"[DynamicRules] 加载规则失败: {e}，使用默认规则")

        # 默认规则
        return {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "total_feedback_count": 0,
            "acceptance_rate": 0.0,
            "weights": {
                "cognitive_load": 0.6,
                "stuck_bonus": 1.5,
                "flow_signal": 0.5,
                "window_switch": 0.4
            },
            "thresholds": {
                "proactive_threshold": 100,
                "min_threshold": 60,
                "max_threshold": 150
            },
            "adjustment_history": [],
            "user_preferences": {
                "preferred_intervention_states": [],
                "avoid_intervention_states": []
            }
        }

    def save_rules(self) -> bool:
        """保存规则到配置文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
            log_message(f"[DynamicRules] 规则已保存，接受率={self.rules.get('acceptance_rate', 0):.1%}")
            return True
        except Exception as e:
            log_message(f"[DynamicRules] 保存规则失败: {e}")
            return False

    def get_weights(self) -> dict:
        """获取当前权重"""
        return self.rules.get("weights", {})

    def get_threshold(self) -> float:
        """获取当前阈值"""
        return self.rules.get("thresholds", {}).get("proactive_threshold", 100)

    def update_rules(self, new_weights: dict, new_threshold: float, reasoning: str, trigger_context: dict):
        """
        更新规则参数并记录历史

        Args:
            new_weights: 新的权重配置
            new_threshold: 新的阈值
            reasoning: 更新理由
            trigger_context: 触发上下文（用于历史记录）
        """
        old_threshold = self.get_threshold()

        # 更新权重和阈值
        self.rules["weights"] = new_weights
        self.rules["thresholds"]["proactive_threshold"] = new_threshold
        self.rules["last_updated"] = datetime.now().isoformat()

        # 记录调整历史
        adjustment_record = {
            "timestamp": datetime.now().isoformat(),
            "trigger": trigger_context.get("feedback_type", "unknown"),
            "old_threshold": old_threshold,
            "new_threshold": new_threshold,
            "old_weights": trigger_context.get("old_weights", {}),
            "new_weights": new_weights,
            "reasoning": reasoning,
            "cognitive_state": trigger_context.get("cognitive_state", "unknown"),
            "total_score": trigger_context.get("total_score", 0)
        }

        self.rules["adjustment_history"].append(adjustment_record)

        # 只保留最近20条历史记录
        if len(self.rules["adjustment_history"]) > 20:
            self.rules["adjustment_history"] = self.rules["adjustment_history"][-20:]

        self.save_rules()

    def record_feedback(self, accepted: bool):
        """记录用户反馈并更新接受率"""
        self.rules["total_feedback_count"] = self.rules.get("total_feedback_count", 0) + 1

        # 使用移动平均计算接受率（给最近的反馈更高权重）
        current_rate = self.rules.get("acceptance_rate", 0.5)
        alpha = 0.2  # 学习率
        new_rate = current_rate * (1 - alpha) + (1.0 if accepted else 0.0) * alpha
        self.rules["acceptance_rate"] = new_rate

        self.save_rules()

    def _load_strategic_guidance(self) -> dict:
        """从配置文件加载战略指导，如果文件不存在则返回默认结构"""
        try:
            if os.path.exists(self.strategic_guidance_path):
                with open(self.strategic_guidance_path, 'r', encoding='utf-8') as f:
                    guidance = json.load(f)
                    log_message(f"[DynamicRules] 已加载战略指导，最后更新={guidance.get('last_updated')}")
                    return guidance
        except Exception as e:
            log_message(f"[DynamicRules] 加载战略指导失败: {e}，使用默认结构")

        # 默认战略指导（聚焦当前任务和情境）
        return {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "analysis_context": {
                "recent_messages_count": 0,
                "user_activity_summary": {},
                "analysis_timestamp": datetime.now().isoformat()
            },
            "current_work_context": {
                "what_user_is_doing": "未分析",
                "current_task": "未知",
                "working_environment": {
                    "primary_app": "",
                    "open_windows": [],
                    "tools_in_use": []
                },
                "confidence": 0.0
            },
            "identified_issues": [],
            "recommended_proactive_services": [],
            "reasoning": ""
        }

    def save_strategic_guidance(self) -> bool:
        """保存战略指导到配置文件"""
        try:
            os.makedirs(os.path.dirname(self.strategic_guidance_path), exist_ok=True)
            with open(self.strategic_guidance_path, 'w', encoding='utf-8') as f:
                json.dump(self.strategic_guidance, f, ensure_ascii=False, indent=2)
            log_message(f"[DynamicRules] 战略指导已保存")
            return True
        except Exception as e:
            log_message(f"[DynamicRules] 保存战略指导失败: {e}")
            return False

    def update_strategic_guidance(self, new_guidance: dict):
        """
        更新战略指导

        Args:
            new_guidance: 新的战略指导配置
        """
        self.strategic_guidance = new_guidance
        self.strategic_guidance["last_updated"] = datetime.now().isoformat()
        self.save_strategic_guidance()

    def get_strategic_guidance(self) -> dict:
        """获取当前战略指导"""
        # 每次获取时重新加载，确保是最新的
        self.strategic_guidance = self._load_strategic_guidance()
        return self.strategic_guidance
