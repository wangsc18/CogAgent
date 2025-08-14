# proactive_service.py
import time
import asyncio
import uuid
from agents.user_state_modeler import UserStateModeler
from utils import activity_monitor, face_thread
from utils.helpers import get_real_time_user_activity, log_message # 确保 log_message 被导入

UPDATE_INTERVAL_SECONDS = 5

# 【核心修复】创建一个全局标志来跟踪监控器是否已启动
_monitors_started = False

async def proactive_monitoring_loop(sessions_dict, msg_queue, request_cache):
    """
    监控循环。
    使用全局标志来确保监控器只被启动一次。
    """
    global _monitors_started # 声明我们要修改的是全局变量

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

    modeler = UserStateModeler(observation_period_seconds=30, history_limit=6)
    
    print(f"--- Proactive Service Thread Started. Updating state every {UPDATE_INTERVAL_SECONDS}s. ---")
    
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

            await asyncio.sleep(UPDATE_INTERVAL_SECONDS)

        except Exception as e:
            import traceback
            log_message(f"An error occurred in the proactive monitoring loop: {e}")
            traceback.print_exc()
            await asyncio.sleep(UPDATE_INTERVAL_SECONDS)