# proactive_service.py
import time
import asyncio
import uuid
from datetime import datetime, timedelta
from agents.executor_brain import UserStateModeler  # 【更新】使用新的执行脑模块
from utils import activity_monitor, face_thread
from utils.helpers import get_real_time_user_activity, log_message  # 确保 log_message 被导入

UPDATE_INTERVAL_SECONDS = 5

# 【核心修复】创建一个全局标志来跟踪监控器是否已启动
_monitors_started = False

async def proactive_monitoring_loop(sessions_dict, msg_queue, request_cache, llm=None, llm_planner=None, decision_mode="heuristic"):
    """
    监控循环。

    Args:
        sessions_dict: 会话字典
        msg_queue: 消息队列
        request_cache: 请求缓存
        llm: LangChain LLM实例，用于执行脑的LLM决策模式（可选）
        llm_planner: LangChain LLM实例，用于规划脑的策略分析（推荐使用更强大的模型）
        decision_mode: 决策模式 "heuristic"（推荐） 或 "llm" (默认: "heuristic")
    """
    global _monitors_started # 声明我们要修改的是全局变量

    # 【战略分析】跟踪变量
    last_strategic_analysis_time = {}  # 记录每个会话的上次战略分析时间
    consecutive_triggers = {}  # 记录连续触发次数
    high_load_duration = {}  # 记录高负荷持续时长

    # 检查全局标志，如果监控器尚未启动，则启动它们
    if not _monitors_started:
        log_message("--- Monitors have not been started yet. Starting them now... ---")
        try:
            activity_monitor.monitor.start()
            face_thread.visual_detector.start()

            # 启动成功后，立即将标志置为 True
            _monitors_started = True
            log_message("--- Monitors started successfully. ---")

        except Exception as e:
            log_message(f"FATAL: Error starting monitors: {e}. Proactive service cannot run.")
            # 如果监控器启动失败，这个后台任务就没有意义了，直接退出。
            return

    # 创建用户状态建模器（执行脑），传递LLM和规划脑的LLM
    log_message(f"--- Initializing UserStateModeler (ExecutorBrain) with decision_mode={decision_mode} ---")
    modeler = UserStateModeler(
        observation_period_seconds=30,
        history_limit=6,
        llm=llm,  # 用于LLM决策模式（可选）
        llm_planner=llm_planner,  # 【新增】用于规划脑策略分析
        decision_mode=decision_mode
    )

    print(f"--- Proactive Service Thread Started. Updating state every {UPDATE_INTERVAL_SECONDS}s. ---")
    print(f"--- Strategic Analysis will trigger at key moments (errors, consecutive triggers, high load). ---")

    while True:
        try:
            # --- 1. 获取一次实时数据 ---
            current_activity = await asyncio.to_thread(get_real_time_user_activity)

            # --- 2. 更新所有后端活动会话的 user_state ---
            for session_id, session_state in list(sessions_dict.items()):
                session_state['user_state'] = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "keyboard_hz": current_activity.get("keyboard_freq_hz", 0),
                    "mouse_hz": current_activity.get("mouse_freq_hz", 0),
                    "open_apps": current_activity.get("open_apps_count", 0),
                    "window_titles": current_activity.get("window_titles", "N/A"),
                    "cognitive_load": current_activity.get("cognitive_load", "waiting..."),
                    "confidence": current_activity.get("confidence", 0.0)
                }

                # 【智能触发战略分析】在关键时刻触发，而不是定期触发
                if modeler.planner_brain is not None:
                    should_analyze = False
                    reason = ""

                    # 初始化会话的跟踪变量
                    if session_id not in consecutive_triggers:
                        consecutive_triggers[session_id] = 0
                    if session_id not in high_load_duration:
                        high_load_duration[session_id] = 0

                    # 获取消息和活动数据
                    messages = session_state.get('messages', [])
                    cognitive_load = current_activity.get('cognitive_load', 'Low Load')

                    # === 触发条件1: 首次分析（有足够对话后） ===
                    if session_id not in last_strategic_analysis_time and len(messages) >= 5:
                        should_analyze = True
                        reason = "首次分析（消息数>=5）"

                    # === 触发条件2: 检测到错误关键词 ===
                    elif len(messages) > 0:
                        last_msg = messages[-1]
                        error_keywords = ['error', 'exception', 'failed', 'bug', '错误', '失败', '报错']
                        last_content = str(last_msg.content).lower()
                        if any(keyword in last_content for keyword in error_keywords):
                            time_since_last = None
                            if session_id in last_strategic_analysis_time:
                                time_since_last = datetime.now() - last_strategic_analysis_time[session_id]
                            # 如果从未分析过，或者距上次分析超过2分钟，则触发
                            if time_since_last is None or time_since_last > timedelta(minutes=2):
                                should_analyze = True
                                reason = "检测到错误关键词"

                    # === 触发条件3: 高认知负荷持续一段时间 ===
                    if 'High Load' in cognitive_load:
                        high_load_duration[session_id] += UPDATE_INTERVAL_SECONDS
                        # 持续高负荷超过60秒，触发分析
                        if high_load_duration[session_id] >= 60:
                            time_since_last = None
                            if session_id in last_strategic_analysis_time:
                                time_since_last = datetime.now() - last_strategic_analysis_time[session_id]
                            if time_since_last is None or time_since_last > timedelta(minutes=3):
                                should_analyze = True
                                reason = f"高负荷持续{high_load_duration[session_id]}秒"
                                high_load_duration[session_id] = 0  # 重置计数器
                    else:
                        high_load_duration[session_id] = 0  # 重置计数器

                    # === 触发战略分析 ===
                    if should_analyze:
                        try:
                            log_message(f"[Session {session_id}] 触发战略分析 - {reason}")
                            log_message(f"[Session {session_id}] 当前有 {len(messages)} 条消息")

                            # 异步调用规划脑进行战略分析（传递user_activity）
                            asyncio.create_task(
                                modeler.planner_brain.analyze_conversation_strategy(
                                    messages=messages,
                                    user_activity=current_activity
                                )
                            )
                            last_strategic_analysis_time[session_id] = datetime.now()
                            consecutive_triggers[session_id] = 0  # 重置连续触发计数
                        except Exception as e:
                            log_message(f"[Session {session_id}] 战略分析失败: {e}")

            # --- 3. 将这份实时数据推送到前端队列，用于更新图表 ---
            state_update_payload = {
                "type": "state_update",
                "data": {
                    "timestamp": time.strftime("%H:%M:%S"),
                    "apps": current_activity.get("open_apps_count", 0),
                    "keyboard": current_activity.get("keyboard_freq_hz", 0),
                    "mouse": current_activity.get("mouse_freq_hz", 0),
                    "cognitive_load": current_activity.get("cognitive_load", "waiting..."),
                    "confidence": current_activity.get("confidence", 0.0),
                }
            }
            await msg_queue.put(state_update_payload)

            # --- 4. 将刚刚获取的数据用于主动服务决策 ---
            modeler.log_current_state_from_data(current_activity)

            if len(modeler.history) >= modeler.limit:
                analysis_result = modeler.analyze_and_decide()
                if analysis_result.get("needs_inquiry"):
                    log_message(f"--- Proactive Service: Detected high load. Caching context and pushing inquiry. ---")
                    request_id = str(uuid.uuid4())
                    request_cache[request_id] = analysis_result.get("context")
                    inquiry_payload = {
                        "type": "inquiry",
                        "text": analysis_result["inquiry_text"],
                        "request_id": request_id
                    }
                    await msg_queue.put(inquiry_payload)

                    # 【跟踪连续触发】记录主动服务触发
                    for session_id in sessions_dict.keys():
                        if session_id in consecutive_triggers:
                            consecutive_triggers[session_id] += 1

            await asyncio.sleep(UPDATE_INTERVAL_SECONDS)

        except Exception as e:
            import traceback
            log_message(f"An error occurred in the proactive monitoring loop: {e}")
            traceback.print_exc()
            await asyncio.sleep(UPDATE_INTERVAL_SECONDS)