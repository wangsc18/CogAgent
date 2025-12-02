# agents/planner_brain.py
"""
规划脑（慢想系统）- 基于用户反馈的策略优化Agent + 战略对话分析

负责：
1. 接收用户反馈（接受/拒绝主动服务）
2. 分析触发时的用户状态和决策参数
3. 使用LLM智能调整规则参数（权重、阈值）
4. 更新动态规则配置
5. 【新增】定期分析对话历史，提取长期意图和任务模式
6. 【新增】生成战略指导，指导执行脑的主动服务方向

调用频率：低频（用户反馈后 + 定期对话分析）
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.language_models import BaseLanguageModel
from utils.dynamic_rules import DynamicRulesManager
from utils.helpers import log_message
from agents.prompts import (
    get_planner_brain_strategy_update_prompt,
    get_strategic_conversation_analysis_prompt
)


class PlannerBrain:
    """
    规划脑（慢想系统）：负责基于用户反馈分析并更新动态规则策略，以及定期战略对话分析。

    两大功能：
    1. 战术反馈优化：在主动服务触发后，根据用户反馈调整权重和阈值
    2. 战略对话分析：定期分析对话历史，理解用户长期意图，指导执行脑的服务方向
    """
    def __init__(self, llm: BaseLanguageModel, rules_manager: DynamicRulesManager):
        """
        Args:
            llm: 用于策略分析的大语言模型（通常是更强大的模型，如gemini-2.5-pro）
            rules_manager: 动态规则管理器实例
        """
        self.llm = llm
        self.rules_manager = rules_manager
        self.last_strategic_analysis_time = None  # 上次战略分析时间

    async def analyze_and_update_strategy(
        self,
        user_accepted: bool,
        trigger_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        基于用户反馈分析并更新策略规则

        Args:
            user_accepted: 用户是否接受了主动服务
            trigger_context: 触发时的完整上下文（包括用户状态、分数等）

        Returns:
            更新结果字典
        """
        # 记录反馈
        self.rules_manager.record_feedback(user_accepted)

        # 获取当前规则
        current_weights = self.rules_manager.get_weights()
        current_threshold = self.rules_manager.get_threshold()

        # 获取历史数据
        total_count = self.rules_manager.rules.get("total_feedback_count", 0)
        acceptance_rate = self.rules_manager.rules.get("acceptance_rate", 0.0)
        recent_history = self.rules_manager.rules.get("adjustment_history", [])[-5:]

        # 【使用prompts模块】构建规划脑的分析prompt
        planner_prompt = get_planner_brain_strategy_update_prompt(
            current_weights=current_weights,
            current_threshold=current_threshold,
            trigger_context=trigger_context,
            total_count=total_count,
            acceptance_rate=acceptance_rate,
            recent_history_count=len(recent_history),
            user_accepted=user_accepted
        )

        try:
            log_message("=" * 60)
            log_message("【规划脑启动】分析用户反馈并更新策略")
            log_message(f"用户反馈: {'接受 ✓' if user_accepted else '拒绝 ✗'}")
            log_message(f"当前接受率: {acceptance_rate:.1%} ({total_count}次触发)")

            # 调用LLM进行策略分析
            response = await self.llm.ainvoke([HumanMessage(content=planner_prompt)])
            response_content = response.content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

            log_message(f"规划脑原始响应: {response_content}")

            # 解析LLM响应
            strategy_update = json.loads(response_content)

            # 提取关键决策字段
            adjustment_needed = strategy_update.get("adjustment_needed", True)
            reasoning = strategy_update.get("reasoning", "无理由")
            new_weights = strategy_update.get("new_weights", current_weights)
            new_threshold = strategy_update.get("new_threshold", current_threshold)
            expected_impact = strategy_update.get("expected_impact", "未知")
            confidence = strategy_update.get("confidence", 0.5)

            log_message("=" * 60)
            log_message("【策略更新分析】")
            log_message(f"是否需要调整: {adjustment_needed}")
            log_message(f"分析理由: {reasoning}")
            log_message(f"误判类型: {strategy_update.get('misclassification_type', 'unknown')}")
            log_message(f"用户模式: {strategy_update.get('pattern_observed', 'N/A')}")
            log_message(f"阈值变化: {current_threshold} → {new_threshold} ({new_threshold - current_threshold:+.1f})")
            log_message(f"权重变化:")
            for key in current_weights:
                old_val = current_weights[key]
                new_val = new_weights.get(key, old_val)
                change = new_val - old_val
                log_message(f"  - {key}: {old_val:.2f} → {new_val:.2f} ({change:+.2f})")
            log_message(f"预期影响: {expected_impact}")
            log_message(f"置信度: {confidence:.1%}")
            log_message("=" * 60)

            # 如果需要调整，则更新规则
            if adjustment_needed:
                update_context = {
                    "feedback_type": "user_accepted" if user_accepted else "user_rejected",
                    "cognitive_state": trigger_context.get('cognitive_state', 'unknown'),
                    "total_score": trigger_context.get('total_score', 0),
                    "old_weights": current_weights
                }

                self.rules_manager.update_rules(
                    new_weights=new_weights,
                    new_threshold=new_threshold,
                    reasoning=reasoning,
                    trigger_context=update_context
                )

                log_message("✓ 规则已更新并保存")
            else:
                log_message("○ 规则无需调整，保持当前策略")

            return {
                "success": True,
                "adjustment_made": adjustment_needed,
                "reasoning": reasoning,
                "new_threshold": new_threshold,
                "new_weights": new_weights,
                "expected_impact": expected_impact,
                "confidence": confidence
            }

        except Exception as e:
            log_message(f"【规划脑错误】{e}")
            import traceback
            traceback.print_exc()

            return {
                "success": False,
                "error": str(e),
                "adjustment_made": False
            }

    async def analyze_conversation_strategy(
        self,
        messages: List[BaseMessage],
        user_activity: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        【战略情境分析】深度分析当前工作情境，理解用户正在做什么以及需要什么帮助

        Args:
            messages: 对话消息列表（最近10条）
            user_activity: 用户实时活动数据（认知负荷、键鼠活动、窗口信息等）

        Returns:
            战略分析结果字典
        """
        try:
            # 获取当前战略指导
            current_guidance = self.rules_manager.get_strategic_guidance()

            # 导入截屏工具
            from utils.helpers import take_screenshot
            import asyncio

            # 获取屏幕截图
            screenshot_b64 = await asyncio.to_thread(take_screenshot)

            # 【使用prompts模块】构建战略分析prompt
            strategic_prompt_text = get_strategic_conversation_analysis_prompt(
                messages=messages,
                user_activity=user_activity,
                current_guidance=current_guidance
            )

            # 构建多模态消息（文本 + 截图）
            multimodal_content = [
                {"type": "text", "text": strategic_prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}}
            ]

            analyzer_message = HumanMessage(content=multimodal_content)

            log_message("=" * 60)
            log_message("【规划脑-战略分析】启动多模态情境分析")
            log_message(f"分析消息数: {len(messages)} 条")
            log_message(f"用户认知负荷: {user_activity.get('cognitive_load', 'unknown')}")
            log_message(f"打开应用: {user_activity.get('window_titles', [])}")

            # 调用LLM进行战略分析
            response = await self.llm.ainvoke([analyzer_message])
            response_content = response.content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

            log_message(f"战略分析原始响应: {response_content[:500]}...")

            # 解析LLM响应
            strategic_analysis = json.loads(response_content)

            # 提取关键信息
            work_context = strategic_analysis.get("current_work_context", {})
            issues = strategic_analysis.get("identified_issues", [])
            recommended_services = strategic_analysis.get("recommended_proactive_services", [])
            reasoning = strategic_analysis.get("reasoning", "")

            log_message("=" * 60)
            log_message("【战略分析结果】")
            log_message(f"用户正在做: {work_context.get('what_user_is_doing', 'N/A')}")
            log_message(f"当前任务: {work_context.get('current_task', 'N/A')}")
            log_message(f"主要应用: {work_context.get('working_environment', {}).get('primary_app', 'N/A')}")
            log_message(f"识别问题数: {len(issues)}")
            log_message(f"推荐服务数: {len(recommended_services)}")
            log_message(f"分析理由: {reasoning[:200]}...")
            log_message("=" * 60)

            # 构建新的战略指导
            new_guidance = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "analysis_context": {
                    "recent_messages_count": len(messages),
                    "user_activity_summary": {
                        "cognitive_load": user_activity.get("cognitive_load", "unknown"),
                        "confidence": user_activity.get("confidence", 0.0),
                        "keyboard_hz": user_activity.get("keyboard_freq_hz", 0),
                        "mouse_hz": user_activity.get("mouse_freq_hz", 0),
                        "window_titles": user_activity.get("window_titles", [])
                    },
                    "analysis_timestamp": datetime.now().isoformat()
                },
                "current_work_context": work_context,
                "identified_issues": issues,
                "recommended_proactive_services": recommended_services,
                "reasoning": reasoning
            }

            # 更新战略指导
            self.rules_manager.update_strategic_guidance(new_guidance)
            self.last_strategic_analysis_time = datetime.now()

            log_message("✓ 战略指导已更新并保存")

            return {
                "success": True,
                "strategic_guidance": new_guidance,
                "reasoning": reasoning
            }

        except Exception as e:
            log_message(f"【战略分析错误】{e}")
            import traceback
            traceback.print_exc()

            return {
                "success": False,
                "error": str(e)
            }
