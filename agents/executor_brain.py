# agents/executor_brain.py
"""
执行脑（快思系统）- 高频用户状态监测与决策Agent

负责：
1. 接收用户活动数据（每5秒）
2. 基于动态规则进行快速评分和决策（每30秒）
3. 判断是否需要触发主动服务
4. 提供用户意图分析和建议生成

调用频率：高频（每30秒一次决策）
决策方式：基于规则的启发式计算 或 LLM智能判断
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage
from langchain_core.language_models import BaseLanguageModel

from utils.helpers import take_screenshot, log_message
from utils.dynamic_rules import DynamicRulesManager
from agents.planner_brain import PlannerBrain
from agents.prompts import (
    get_executor_llm_decision_prompt,
    get_cognitive_benefit_analyzer_prompt
)


class UserStateModeler:
    """
    用户状态建模器（执行脑）- "快思慢想"系统中的快思部分
    
    支持两种决策模式：
    - 启发式模式 (heuristic): 基于动态规则参数的加权分数模型，速度快、成本低（推荐）
    - LLM模式 (llm): 使用大语言模型进行认知状态推理，准确度高但成本高
    
    同时提供"分析器"功能，在用户确认后进行深度意图分析和建议生成。
    """
    
    def __init__(self, observation_period_seconds=30, history_limit=6,
                 llm=None, decision_mode="heuristic", llm_planner=None):
        """
        Args:
            observation_period_seconds: 观察周期（秒）
            history_limit: 历史记录数量限制
            llm: LangChain LLM实例，用于LLM决策模式
            decision_mode: 决策模式 "heuristic"（推荐） 或 "llm"
            llm_planner: 用于规划脑的LLM实例（通常是更强大的模型）
        """
        self.history = []
        self.period = observation_period_seconds
        self.limit = history_limit
        self.llm = llm
        self.decision_mode = decision_mode

        # 初始化动态规则管理器
        self.rules_manager = DynamicRulesManager()

        # 初始化规划脑（如果提供了LLM）
        self.planner_brain = None
        if llm_planner is not None:
            self.planner_brain = PlannerBrain(llm=llm_planner, rules_manager=self.rules_manager)
            log_message("[ExecutorBrain] 规划脑已启用（慢想系统）")
        else:
            log_message("[ExecutorBrain] 规划脑未启用，将使用固定规则参数")

        # 从动态规则加载权重和阈值
        self.weights = self.rules_manager.get_weights()
        self.proactive_threshold = self.rules_manager.get_threshold()

        log_message(f"[ExecutorBrain] 决策模式: {decision_mode}")
        log_message(f"[ExecutorBrain] 当前阈值: {self.proactive_threshold}")
        log_message(f"[ExecutorBrain] 当前权重: {json.dumps(self.weights, ensure_ascii=False)}")

    def log_current_state_from_data(self, activity: dict):
        """从外部接收活动数据并记录"""
        timestamp = datetime.now().isoformat()
        self.history.append({"timestamp": timestamp, "activity": activity})
        if len(self.history) > self.limit:
            self.history.pop(0)

    def calculate_proactive_score(self) -> dict:
        """
        计算并返回当前周期的主动服务分数和明细
        所有单项分数都归一化到 0-100 的范围
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
        
        # 计算各分项得分
        
        # a) 认知负荷得分 (考虑置信度)
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
        
        # 计算加权总分
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
        基于配置的决策模式进行分析和决策
        支持两种模式：启发式 (heuristic) 和 LLM决策 (llm)
        """
        if len(self.history) < self.limit:
            return {"needs_inquiry": False}

        # 根据决策模式选择不同的决策方法
        if self.decision_mode == "heuristic":
            return self._heuristic_analyze_and_decide()
        elif self.decision_mode == "llm":
            return self._llm_analyze_and_decide()
        else:
            log_message(f"Warning: Unknown decision_mode '{self.decision_mode}', falling back to heuristic")
            return self._heuristic_analyze_and_decide()

    def _heuristic_analyze_and_decide(self) -> dict:
        """
        【启发式模式 - 执行脑/快思】基于动态规则参数的分数模型进行快速决策
        """
        # 每次决策前重新加载最新规则（以防规划脑已更新）
        self.weights = self.rules_manager.get_weights()
        self.proactive_threshold = self.rules_manager.get_threshold()

        score_result = self.calculate_proactive_score()

        log_message("--- User State Score (Heuristic Mode / 执行脑-快思) ---")
        log_message(f"Total Score: {score_result['total_score']} / {self.proactive_threshold}")
        log_message(f"Breakdown: {json.dumps(score_result['breakdown'])}")
        log_message(f"Current Weights: {json.dumps(self.weights)}")

        history_to_return = self.history.copy()
        self.history = []

        if not score_result["is_above_threshold"]:
            return {"needs_inquiry": False}

        reason_for_inquiry = f"系统综合评分 ({score_result['total_score']:.0f}) 超过了阈值 ({self.proactive_threshold})，表明用户可能需要帮助。"

        # 保存完整的触发上下文，用于规划脑后续分析
        trigger_context = {
            "timestamp": datetime.now().isoformat(),
            "total_score": score_result['total_score'],
            "threshold": self.proactive_threshold,
            "weights": self.weights.copy(),
            "breakdown": score_result['breakdown'],
            "raw_metrics": score_result['raw_metrics'],
            "cognitive_state": score_result['raw_metrics']['cognitive_load'],
            "activity_log": history_to_return
        }

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
                "activity_log": history_to_return,
                # 保存触发上下文用于规划脑
                "trigger_context_for_planner": trigger_context
            }
        }

    def _llm_analyze_and_decide(self) -> dict:
        """
        【LLM模式 - 快思】使用大语言模型进行智能决策

        关键改进：LLM的判断会参考由慢想（planner_brain）学习的动态规则参数
        这样LLM模式和启发式模式都能享受规划脑的学习成果
        """
        if self.llm is None:
            log_message("ERROR: LLM mode enabled but no LLM instance provided. Falling back to heuristic.")
            return self._heuristic_analyze_and_decide()

        # 【关键】加载最新的规则参数（慢想学习的成果）
        self.weights = self.rules_manager.get_weights()
        self.proactive_threshold = self.rules_manager.get_threshold()
        acceptance_rate = self.rules_manager.rules.get("acceptance_rate", 0.5)

        # 准备数据
        history_to_return = self.history.copy()
        self.history = []

        # 计算统计指标
        last_activity = history_to_return[-1]['activity']
        avg_keyboard_hz = sum(item['activity']['keyboard_freq_hz'] for item in history_to_return) / len(history_to_return)
        avg_mouse_hz = sum(item['activity']['mouse_freq_hz'] for item in history_to_return) / len(history_to_return)

        # 窗口切换分析
        start_titles = set(history_to_return[0]['activity'].get('window_titles', []))
        end_titles = set(history_to_return[-1]['activity'].get('window_titles', []))
        changed_windows_count = len(start_titles.symmetric_difference(end_titles))

        # 【新增】如果启用了规划脑，计算启发式分数作为LLM的参考
        heuristic_score = None
        if self.planner_brain:
            # 临时构建完整历史用于计算分数
            temp_history = history_to_return.copy()
            self.history = temp_history
            score_result = self.calculate_proactive_score()
            heuristic_score = score_result['total_score']
            self.history = []  # 清空临时历史

        # 【使用prompts模块】构建注入动态规则参数的认知状态推断prompt
        decision_prompt = get_executor_llm_decision_prompt(
            period=self.period,
            last_activity=last_activity,
            avg_keyboard_hz=avg_keyboard_hz,
            avg_mouse_hz=avg_mouse_hz,
            changed_windows_count=changed_windows_count,
            history=history_to_return,
            proactive_threshold=self.proactive_threshold,
            weights=self.weights,
            acceptance_rate=acceptance_rate,
            total_feedback_count=self.rules_manager.rules.get('total_feedback_count', 0),
            heuristic_score=heuristic_score
        )

        try:
            log_message("--- LLM Decision Mode (with Dynamic Rules): Invoking LLM for proactive service decision ---")
            log_message(f"Current Rules: threshold={self.proactive_threshold}, weights={json.dumps(self.weights)}")
            if heuristic_score:
                log_message(f"Heuristic Reference: score={heuristic_score:.1f}, suggest={'INTERVENE' if heuristic_score > self.proactive_threshold else 'WAIT'}")

            # 调用LLM
            try:
                loop = asyncio.get_running_loop()
                response = loop.run_until_complete(self.llm.ainvoke([HumanMessage(content=decision_prompt)]))
            except RuntimeError:
                response = self.llm.invoke([HumanMessage(content=decision_prompt)])

            response_content = response.content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            log_message(f"LLM Decision Raw Response: {response_content}")

            # 解析LLM响应
            parsed_decision = json.loads(response_content)

            # 提取核心决策字段
            cognitive_state = parsed_decision.get("state", "未知状态")
            psychological_inference = parsed_decision.get("psychological", "无法推断心理状态")
            needs_intervention = parsed_decision.get("needs_intervention", False)
            llm_confidence = parsed_decision.get("confidence", 0.0)
            reasoning = parsed_decision.get("reasoning", "LLM未提供理由")
            inquiry_text = parsed_decision.get("inquiry", "看起来您现在正忙，需要一些帮助吗？")
            key_behavioral_indicators = parsed_decision.get("indicators", [])
            heuristic_alignment = parsed_decision.get("heuristic_alignment", "not_available")

            # 记录详细的推断结果
            log_message("=" * 60)
            log_message("【LLM认知状态推断】（基于慢想学习的动态规则）")
            log_message(f"状态: {cognitive_state}")
            log_message(f"心理: {psychological_inference}")
            log_message(f"干预: {needs_intervention} (置信度: {llm_confidence:.2%})")
            log_message(f"理由: {reasoning}")
            log_message(f"指标: {key_behavioral_indicators}")
            if heuristic_score:
                log_message(f"与启发式一致性: {heuristic_alignment}")
            log_message("=" * 60)

            if not needs_intervention:
                return {"needs_inquiry": False}

            # 【新增】构建触发上下文用于规划脑学习（与启发式模式保持一致）
            trigger_context = {
                "timestamp": datetime.now().isoformat(),
                "total_score": heuristic_score if heuristic_score else 0,  # LLM模式下也提供参考分数
                "threshold": self.proactive_threshold,
                "weights": self.weights.copy(),
                "breakdown": {},  # LLM模式没有分项分数
                "raw_metrics": {
                    "cognitive_load": last_activity.get("cognitive_load", "unknown"),
                    "confidence": last_activity.get("confidence", 0.0),
                    "avg_keyboard_hz": avg_keyboard_hz,
                    "avg_mouse_hz": avg_mouse_hz,
                    "changed_windows_count": changed_windows_count,
                    "is_stuck": False  # LLM模式通过state判断
                },
                "cognitive_state": cognitive_state,
                "activity_log": history_to_return,
                "decision_mode": "llm_with_dynamic_rules"
            }

            return {
                "needs_inquiry": True,
                "inquiry_text": inquiry_text,
                "context": {
                    "reason": f"【状态】{cognitive_state}\n【心理】{psychological_inference}\n【理由】{reasoning}",
                    "llm_confidence": llm_confidence,
                    "cognitive_state": cognitive_state,
                    "psychological_inference": psychological_inference,
                    "key_behavioral_indicators": key_behavioral_indicators,
                    "activity_summary": {
                        "decision_mode": "llm_with_dynamic_rules",
                        "avg_keyboard_hz": round(avg_keyboard_hz, 2),
                        "avg_mouse_hz": round(avg_mouse_hz, 2),
                        "changed_windows_count": changed_windows_count,
                        "final_cognitive_load": last_activity.get("cognitive_load", "unknown"),
                        "final_confidence": round(last_activity.get("confidence", 0.0), 2),
                        "heuristic_score": heuristic_score if heuristic_score else None,
                        "heuristic_alignment": heuristic_alignment
                    },
                    "activity_log": history_to_return,
                    # 【关键】保存触发上下文用于规划脑
                    "trigger_context_for_planner": trigger_context
                }
            }

        except Exception as e:
            log_message(f"LLM Decision Error: {e}")
            import traceback
            traceback.print_exc()
            log_message("Falling back to heuristic mode due to LLM error")
            self.history = history_to_return
            return self._heuristic_analyze_and_decide()

    async def process_user_feedback(
        self,
        user_accepted: bool,
        trigger_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理用户反馈并触发规划脑更新策略（慢想系统）

        Args:
            user_accepted: 用户是否接受了主动服务
            trigger_context: 触发时保存的完整上下文（来自_heuristic_analyze_and_decide）

        Returns:
            规划脑的更新结果
        """
        if self.planner_brain is None:
            log_message("[ExecutorBrain] 规划脑未启用，跳过策略更新")
            # 即使没有规划脑，也记录反馈用于统计
            self.rules_manager.record_feedback(user_accepted)
            return {
                "success": False,
                "reason": "planner_brain_not_enabled",
                "feedback_recorded": True
            }

        log_message(f"[ExecutorBrain] 触发规划脑更新策略（用户{'接受' if user_accepted else '拒绝'}）")

        # 调用规划脑进行策略分析和更新
        result = await self.planner_brain.analyze_and_update_strategy(
            user_accepted=user_accepted,
            trigger_context=trigger_context
        )

        # 如果规则已更新，重新加载到当前实例
        if result.get("adjustment_made", False):
            self.weights = self.rules_manager.get_weights()
            self.proactive_threshold = self.rules_manager.get_threshold()
            log_message(f"[ExecutorBrain] 已加载最新规则: 阈值={self.proactive_threshold}, 权重={json.dumps(self.weights)}")

        return result

    @staticmethod
    async def analyze_user_context_and_suggest(
        context: Dict[str, Any],
        llm: BaseLanguageModel,
        tools_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        基于认知效益效用函数的主动服务决策
        
        核心公式：净认知效益 = (卸载效益 × 成功概率) - 交互成本
        
        根据用户认知状态动态调整服务形式
        """
        log_message("=" * 60)
        log_message("【认知效益分析器启动】")

        summary = context.get("activity_summary", {})
        reason = context.get("reason", "注意到用户似乎很忙。")
        cognitive_state = context.get("cognitive_state", "未知状态")
        psychological_inference = context.get("psychological_inference", "")

        log_message(f"用户认知状态: {cognitive_state}")
        log_message(f"心理推断: {psychological_inference}")

        # 根据认知状态确定干预策略参数
        intervention_profile = UserStateModeler._get_intervention_profile(cognitive_state)
        log_message(f"干预策略: {intervention_profile['strategy_name']}")
        log_message(f"最大交互成本限制: {intervention_profile['max_interaction_cost']}")
        log_message(f"基础成功概率: {intervention_profile['base_success_prob']:.2%}")

        screenshot_b64 = await asyncio.to_thread(take_screenshot)

        # 【使用prompts模块】构建基于认知效益的分析prompt
        analyzer_prompt_text = get_cognitive_benefit_analyzer_prompt(
            cognitive_state=cognitive_state,
            psychological_inference=psychological_inference,
            reason=reason,
            summary=summary,
            intervention_profile=intervention_profile,
            tools_config=tools_config
        )

        multimodal_content = [
            {"type": "text", "text": analyzer_prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}}
        ]

        analyzer_message = HumanMessage(content=multimodal_content)

        try:
            log_message("【调用LLM进行认知效益分析】")
            response = await llm.ainvoke([analyzer_message])
            response_content = response.content.strip().lstrip("```json").rstrip("```").strip()

            parsed_response = json.loads(response_content)

            # 提取关键信息并记录
            selected = parsed_response.get("selected_intervention", {})
            log_message("=" * 60)
            log_message("【认知效益分析结果】")
            log_message(f"用户任务: {parsed_response.get('user_task', 'N/A')}")
            log_message(f"用户意图: {parsed_response.get('user_intent', 'N/A')}")
            log_message(f"主要障碍: {parsed_response.get('obstacle', 'N/A')}")
            log_message(f"卸载效益: {selected.get('offloading_benefit', 0)}/100")
            log_message(f"交互成本: {selected.get('interaction_cost', 0)}/100")
            log_message(f"成功概率: {selected.get('success_probability', 0.0):.2%}")
            log_message(f"净认知效益: {selected.get('net_cognitive_benefit', 0)}")
            log_message(f"干预类型: {selected.get('intervention_type', 'unknown')}")
            log_message(f"决策理由: {parsed_response.get('reasoning', 'N/A')}")
            log_message("=" * 60)

            return parsed_response

        except Exception as e:
            log_message(f"【分析失败】{e}")
            import traceback
            traceback.print_exc()
            return {
                "user_task": "分析失败",
                "user_intent": "无法推断",
                "obstacle": None,
                "candidate_interventions": [],
                "selected_intervention": {
                    "suggestion_text": "抱歉，我在分析您的情况时遇到了技术问题。",
                    "recommended_tool": None,
                    "intervention_type": "error",
                    "offloading_benefit": 0,
                    "interaction_cost": 0,
                    "success_probability": 0.0,
                    "net_cognitive_benefit": 0
                },
                "reasoning": str(e)
            }

    @staticmethod
    def _get_intervention_profile(cognitive_state: str) -> Dict[str, Any]:
        """根据用户认知状态返回干预策略配置"""
        state_id = cognitive_state[0] if cognitive_state else "E"

        profiles = {
            "A": {  # 心流状态
                "strategy_name": "最小化干扰策略",
                "description": "用户处于心流状态，任何打断都会造成巨大损失。只在背景处理次要任务，不主动呈现信息。",
                "max_interaction_cost": 15,
                "base_success_prob": 0.3,
                "complexity_level": "极简（仅关键词或延迟到合适时机）"
            },
            "B": {  # 深度思考
                "strategy_name": "观察等待策略",
                "description": "用户正在深度思考，这是正常的问题解决过程。观察但不打扰，除非有明确的快捷方式。",
                "max_interaction_cost": 20,
                "base_success_prob": 0.4,
                "complexity_level": "极简（1句话提示）"
            },
            "C": {  # 卡壳状态
                "strategy_name": "核心提示策略",
                "description": "用户遇到困难且迷茫。提供1句话核心提示 + 1个具体可行动的建议，避免冗长方案增加负担。",
                "max_interaction_cost": 40,
                "base_success_prob": 0.85,
                "complexity_level": "简洁（1-2句话 + 1个具体建议）"
            },
            "D": {  # 认知过载
                "strategy_name": "任务卸载策略",
                "description": "用户认知超负荷。帮助简化或代办任务，减少信息量而不是增加新信息。",
                "max_interaction_cost": 35,
                "base_success_prob": 0.7,
                "complexity_level": "简洁（提供卸载方案，不要额外信息）"
            },
            "E": {  # 探索状态
                "strategy_name": "中等支持策略",
                "description": "用户在正常探索中。提供2-3个简洁选项，让用户自主选择。",
                "max_interaction_cost": 60,
                "base_success_prob": 0.6,
                "complexity_level": "中等（2-3个选项，每个1句话）"
            },
            "F": {  # 低负荷
                "strategy_name": "完整信息策略",
                "description": "用户认知负荷低。可以提供较完整的信息和多个选项。",
                "max_interaction_cost": 80,
                "base_success_prob": 0.5,
                "complexity_level": "完整（可以提供详细方案和多个选项）"
            }
        }

        return profiles.get(state_id, profiles["E"])  # 默认返回探索状态配置
