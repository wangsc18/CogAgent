# proactive_service.py
import time
import threading
import uuid
from agents.user_state_modeler import UserStateModeler
from utils.helpers import get_real_time_user_activity

MONITORING_INTERVAL_SECONDS = 30
UPDATE_INTERVAL_SECONDS = 5 # 每5秒更新一次状态

def proactive_monitoring_loop(sessions_dict, msg_queue, request_cache):
    """
    监控循环。核心职责：
    1. 持续更新所有活动会话的 user_state。
    2. 将每次的状态更新都推送到前端图表。
    3. 周期性地分析并决定是否推送询问。
    """
    modeler = UserStateModeler(observation_period_seconds=30, history_limit=6)
    
    print(f"--- Proactive Service Thread Started. Updating state every {UPDATE_INTERVAL_SECONDS}s. ---")
    
    while True:
        try:
            # --- 1. 获取一次实时数据 ---
            current_activity = get_real_time_user_activity()
            
            # --- 2. 更新所有后端活动会话的 user_state ---
            for session_id, session_state in list(sessions_dict.items()):
                session_state['user_state'] = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "keyboard_hz": current_activity.get("keyboard_freq_hz", 0),
                    "mouse_hz": current_activity.get("mouse_freq_hz", 0),
                    "open_apps": current_activity.get("open_apps_count", 0),
                    "window_titles": current_activity.get("window_titles", "N/A"),
                    # 视觉认知负荷状态
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
                    # 视觉认知负荷状态
                    "cognitive_load": current_activity.get("cognitive_load", "waiting..."),
                    "confidence": current_activity.get("confidence", 0.0),
                }
            }
            msg_queue.put(state_update_payload)

            # --- 4. 将刚刚获取的数据用于主动服务决策 ---
            modeler.log_current_state_from_data(current_activity) 
            
            # 只有在 modeler 的历史记录满了之后才做决策
            if len(modeler.history) >= modeler.limit:
                analysis_result = modeler.analyze_and_decide()
                if analysis_result.get("needs_inquiry"):
                    print(f"--- Proactive Service: Detected high load. Caching context and pushing inquiry. ---")
                    request_id = str(uuid.uuid4())
                    request_cache[request_id] = analysis_result.get("context")
                    msg_queue.put({
                        "type": "inquiry", 
                        "text": analysis_result["inquiry_text"],
                        "request_id": request_id
                    })
            
            time.sleep(UPDATE_INTERVAL_SECONDS)

        except Exception as e:
            import traceback
            print(f"An error occurred in the proactive monitoring loop: {e}")
            traceback.print_exc()
            time.sleep(MONITORING_INTERVAL_SECONDS)