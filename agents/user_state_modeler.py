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
    用户建模器，支持两种决策模式：
    1. 启发式模式 (heuristic): 使用加权分数模型判断是否需要主动服务
    2. LLM模式 (llm): 使用大语言模型进行智能决策

    同时作为一个"分析器Agent"，能够在用户确认后分析其意图并提出建议。
    """
    def __init__(self, observation_period_seconds=30, history_limit=6,
                 llm=None, decision_mode="llm"):
        """
        Args:
            observation_period_seconds: 观察周期（秒）
            history_limit: 历史记录数量限制
            llm: LangChain LLM实例，用于LLM决策模式
            decision_mode: 决策模式 "heuristic" 或 "llm"
        """
        self.history = []
        self.period = observation_period_seconds
        self.limit = history_limit
        self.llm = llm
        self.decision_mode = decision_mode

        # 【启发式模式】定义分数模型的权重和阈值
        self.weights = {
            "cognitive_load": 0.6, # 认知负荷作为基础分的权重，提升至60%
            "stuck_bonus": 1.5,  # "卡壳信号"的奖励乘数，非常重要
            "flow_signal": 0.5, # "心流"状态下的惩罚乘数
            "window_switch": 0.4 # "分心信号"（窗口切换）的权重
        }
        self.proactive_threshold = 100 # 阈值

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
        基于配置的决策模式进行分析和决策。
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
        【启发式模式】基于分数模型进行分析和决策。
        """
        score_result = self.calculate_proactive_score()

        log_message("--- User State Score (Heuristic Mode) ---")
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

    def _llm_analyze_and_decide(self) -> dict:
        """
        【LLM模式】使用大语言模型进行智能决策。
        LLM会综合分析用户活动数据，判断是否需要主动服务干预。
        """
        if self.llm is None:
            log_message("ERROR: LLM mode enabled but no LLM instance provided. Falling back to heuristic.")
            return self._heuristic_analyze_and_decide()

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

        # 构建精炼版的认知状态推断prompt（优化推理速度和token消耗）
        decision_prompt = f"""
你是AI认知伙伴，运用心智理论推断用户认知状态并决策是否干预。

# 观察数据（过去{self.period}秒）
- 认知负荷: {last_activity.get("cognitive_load", "unknown")} ({last_activity.get("confidence", 0.0):.0%})
- 键盘/鼠标: {avg_keyboard_hz:.2f}Hz / {avg_mouse_hz:.2f}Hz
- 窗口切换: {changed_windows_count}次
- 应用数: {last_activity.get("open_apps_count", 0)}个

# 认知状态分类（基于心流理论+认知负荷理论）

**A. 心流**(Flow): 中高负荷+高频活动(>2Hz)+窗口稳定 → 沉浸状态 → **不打扰**
**B. 深度思考**(Thinking): 高负荷+低活动+短期(<50%观察期) → 正常思考 → **不打扰**
**C. 卡壳**(Stuck): 高负荷+极低活动(<0.5Hz)+持续长(>70%观察期) → 迷茫受挫 → **需要帮助**
**D. 过载**(Overload): 高负荷+无规律活动+频繁切换(>3次) → 认知超负荷 → **需要帮助**
**E. 探索**(Explore): 中负荷+中等活动(1-2.5Hz)+适度切换 → 搜索信息 → **观察**
**F. 休息**(Rest): 低负荷+低活动 → 非工作状态 → **不打扰**

# 核心区分: 心流 vs 卡壳
高认知负荷时必须区分：
- 心流=高活动+稳定节奏 → 技能匹配挑战
- 卡壳=极低活动+持续停滞 → 挑战超出技能

# 时间序列
```json
{json.dumps(history_to_return, indent=2, ensure_ascii=False)}
```

# 输出JSON（无额外文字）
{{
  "state": "A-F其中之一",
  "psychological": "用户心理状态推断(1句话)",
  "needs_intervention": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "关键指标+理论依据(简短)",
  "indicators": ["指标1", "指标2"],
  "inquiry": "干预询问语或null"
}}

# 原则
1. 优先保护心流状态
2. 基于时间趋势而非瞬时状态
3. 宁可少打扰不要误打扰
"""

        try:
            log_message("--- LLM Decision Mode: Invoking LLM for proactive service decision ---")

            # 调用LLM（同步调用）
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # 在事件循环中，使用 run_in_executor
                response = loop.run_until_complete(self.llm.ainvoke([HumanMessage(content=decision_prompt)]))
            except RuntimeError:
                # 没有运行的事件循环，直接同步调用
                response = self.llm.invoke([HumanMessage(content=decision_prompt)])

            response_content = response.content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            log_message(f"LLM Decision Raw Response: {response_content}")

            # 解析LLM响应（精简版字段）
            parsed_decision = json.loads(response_content)

            # 提取核心决策字段（新的简化字段名）
            cognitive_state = parsed_decision.get("state", "未知状态")
            psychological_inference = parsed_decision.get("psychological", "无法推断心理状态")
            needs_intervention = parsed_decision.get("needs_intervention", False)
            llm_confidence = parsed_decision.get("confidence", 0.0)
            reasoning = parsed_decision.get("reasoning", "LLM未提供理由")
            inquiry_text = parsed_decision.get("inquiry", "看起来您现在正忙，需要一些帮助吗？")
            key_behavioral_indicators = parsed_decision.get("indicators", [])

            # 记录详细的推断结果
            log_message("=" * 60)
            log_message("【LLM认知状态推断】")
            log_message(f"状态: {cognitive_state}")
            log_message(f"心理: {psychological_inference}")
            log_message(f"干预: {needs_intervention} (置信度: {llm_confidence:.2%})")
            log_message(f"理由: {reasoning}")
            log_message(f"指标: {key_behavioral_indicators}")
            log_message("=" * 60)

            if not needs_intervention:
                return {"needs_inquiry": False}

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
                        "decision_mode": "llm_theory_driven",
                        "avg_keyboard_hz": round(avg_keyboard_hz, 2),
                        "avg_mouse_hz": round(avg_mouse_hz, 2),
                        "changed_windows_count": changed_windows_count,
                        "final_cognitive_load": last_activity.get("cognitive_load", "unknown"),
                        "final_confidence": round(last_activity.get("confidence", 0.0), 2)
                    },
                    "activity_log": history_to_return
                }
            }

        except Exception as e:
            log_message(f"LLM Decision Error: {e}")
            import traceback
            traceback.print_exc()
            log_message("Falling back to heuristic mode due to LLM error")
            # 恢复历史数据并使用启发式方法
            self.history = history_to_return
            return self._heuristic_analyze_and_decide()

    @staticmethod
    async def analyze_user_context_and_suggest(
        context: Dict[str, Any],
        llm: BaseLanguageModel,
        tools_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        基于认知效益效用函数的主动服务决策。

        核心公式：净认知效益 = (卸载效益 × 成功概率) - 交互成本

        - 卸载效益：主动服务能为用户节省的认知资源（0-100）
        - 交互成本：用户理解和采纳建议所需的认知资源（0-100）
        - 成功概率：用户接受并执行的概率（0.0-1.0）

        根据用户认知状态动态调整服务形式。
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

        # 构建基于认知效益的分析prompt
        analyzer_prompt_text = f"""
你是AI认知伙伴，负责通过**认知效益最大化**来决策主动服务策略。

# 用户认知状态
- **状态**: {cognitive_state}
- **心理**: {psychological_inference}
- **系统分析**: {reason}
- **认知负荷**: {summary.get('final_cognitive_load', 'N/A')} ({summary.get('final_confidence', 0.0):.0%})
- **活动水平**: 键盘{summary.get('avg_keyboard_hz', 'N/A')}Hz / 鼠标{summary.get('avg_mouse_hz', 'N/A')}Hz

# 干预策略约束
基于用户当前认知状态，你必须遵循以下约束：
- **策略类型**: {intervention_profile['strategy_name']}
- **策略原则**: {intervention_profile['description']}
- **交互成本上限**: {intervention_profile['max_interaction_cost']}/100
- **建议复杂度**: {intervention_profile['complexity_level']}

# 认知效益决策框架

你需要评估并选择**最大化净认知效益**的干预方案。

## 效用函数
```
净认知效益 = (卸载效益 × 成功概率) - 交互成本
```

## 参数定义

**卸载效益 (0-100)**: 为用户节省的认知资源
- 完全自动化任务: 90-100
- 提供关键快捷方式: 70-85
- 减少信息搜索: 50-70
- 任务优先级建议: 40-60
- 一般性建议: 20-40

**交互成本 (0-100)**: 用户理解和采纳所需的认知资源
- 1句话核心提示: 10-20
- 2-3句话 + 1个具体建议: 30-50
- 多步骤方案 + 选项: 60-80
- 复杂详尽方案: 80-100
**约束**: 必须 ≤ {intervention_profile['max_interaction_cost']}

**成功概率 (0.0-1.0)**: 用户接受并执行的概率
- 基础概率: {intervention_profile['base_success_prob']:.2f}
- 调整因子:
  * 与用户当前任务直接相关: +0.2
  * 需要额外学习/理解: -0.2
  * 工具自动化执行: +0.1

# 可用工具
```json
{json.dumps(tools_config, indent=2, ensure_ascii=False)}
```

# 你的任务

## 步骤1: 分析用户任务和意图
从屏幕截图中识别：
1. 用户正在做什么（具体任务）
2. 用户的目标是什么（意图）
3. 用户遇到的主要障碍（如果有）

## 步骤2: 生成候选干预方案
列出2-4个可能的干预方案，每个方案包括：
- 具体建议内容
- 估算的卸载效益
- 估算的交互成本
- 估算的成功概率

## 步骤3: 计算并选择最优方案
计算每个方案的净认知效益，选择得分最高的方案。

## 步骤4: 生成适应性建议
根据用户认知状态，生成相应复杂度的建议：
- **心流/专注**: 最小化文字，只给关键词或等待时机
- **卡壳/迷茫**: 1句话 + 1个具体可行动的建议
- **认知过载**: 提供卸载方案，不增加新信息
- **探索状态**: 提供2-3个简洁选项
- **低负荷**: 可以提供完整信息

# 输出JSON（无额外文字）
{{
  "user_task": "用户当前主要任务(简短)",
  "user_intent": "用户目标意图(1句话)",
  "obstacle": "主要障碍(1句话，无则null)",
  "candidate_interventions": [
    {{
      "description": "方案描述",
      "offloading_benefit": 0-100,
      "interaction_cost": 0-100,
      "success_probability": 0.0-1.0,
      "net_benefit": "计算结果"
    }}
  ],
  "selected_intervention": {{
    "suggestion_text": "根据认知状态生成的适应性建议文本",
    "recommended_tool": "工具名或null",
    "intervention_type": "tool_automation/priority_advice/information_support/minimal_disturbance",
    "offloading_benefit": 0-100,
    "interaction_cost": 0-100,
    "success_probability": 0.0-1.0,
    "net_cognitive_benefit": "计算结果"
  }},
  "reasoning": "为何选择此方案的简短理由(必须引用效益计算)"
}}

现在开始分析。
"""
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
        """
        根据用户认知状态返回干预策略配置。

        返回字段：
        - strategy_name: 策略名称
        - description: 策略描述
        - max_interaction_cost: 最大允许交互成本
        - base_success_prob: 基础成功概率
        - complexity_level: 建议复杂度级别
        """
        # 提取状态标识符（A-F）
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