# agents/planner.py
import json
from langchain_core.messages import AIMessage, HumanMessage
from state import AgentState
from utils.helpers import log_message

def run_planner(state: AgentState, llm, tools_config: dict, user_habits: dict) -> AgentState:
    """
    核心决策节点。它能处理标准文本和多模态输入，
    并会结合用户的长期习惯和【由后台服务持续更新的实时状态】进行决策。
    """
    log_message("--- Planner ---")
    state['log'].append("Planner node started.")

    # --- 1. 首先，获取由后台服务更新的实时用户状态 ---
    user_state = state.get("user_state", {})
    cognitive_context_str = ""
    if user_state:
        cognitive_context_str = f"""
# 用户当前实时状态:
{json.dumps(user_state, indent=2, ensure_ascii=False)}
"""

    # --- 2. 检查最新的消息是否为多模态输入 ---
    last_message = state['messages'][-1]
    is_multimodal = isinstance(last_message.content, list)
    
    # --- 3. 处理多模态输入（主动服务请求）的逻辑 ---
    if is_multimodal:
        log_message("Planner detected a multimodal proactive request. Directly invoking LLM for analysis.")
        
        # 我们依然将实时状态信息增强到最后一条消息中
        original_multimodal_content = last_message.content
        if original_multimodal_content and original_multimodal_content[0].get("type") == "text":
            original_text = original_multimodal_content[0]["text"]
            combined_text = cognitive_context_str + "\n" + original_text
            original_multimodal_content[0]["text"] = combined_text
        
        response = llm.invoke(state['messages'])
        
        state['messages'].append(AIMessage(content=response.content))
        return state

    # --- 如果不是多模态任务，则执行原来的文本决策逻辑---
    log_message("Planner processing a standard text request.")
    
    # 使用健壮的、能处理多种消息类型的历史记录格式化逻辑
    formatted_history = []
    for msg in state['messages']:
        if isinstance(msg.content, str):
            content_str = msg.content
        elif isinstance(msg.content, list): # 正确处理历史中的多模态消息
            text_parts = [part['text'] for part in msg.content if part['type'] == 'text']
            content_str = "\n".join(text_parts) + " [An image was also provided]"
        else:
            content_str = str(msg.content)
            
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            content_str += f" (Tool Call: {json.dumps(msg.tool_calls)})"
        formatted_history.append(f"{msg.type}: {content_str}")
    history_str = "\n".join(formatted_history)

    user_habits_str = f"\n# 用户长期偏好:\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}\n" if user_habits else ""

# 需要根据habits修改主动服务生成内容的风格

    prompt = f"""
你是一个能够感知用户实时状态的、有同理心的对话助手。

{user_habits_str}
{cognitive_context_str}
# 对话历史:
{history_str}
# 可用工具列表:
{json.dumps(tools_config, indent=2, ensure_ascii=False)}

# 你的任务:
综合分析用户的长期偏好、**当前实时状态**和对话历史，决定下一步行动。
- **特别注意**: 如果用户的'user_state'显示高频率活动（例如 keyboard_hz > 5.0），表明用户可能很忙。在这种情况下，你的**所有**回复都应该**极其简洁**。
- 否则，生成一个符合用户长期偏好的、正常的回复。

严格按照以下JSON格式之一输出...
格式1 (调用工具): {{"tool_call": ...}}
格式2 (直接回复): {{"response": "..."}}
"""
    
    response_str = llm.invoke(prompt).content
    cleaned_response = response_str.strip().lstrip("```json").rstrip("```").strip()
    
    try:
        parsed_response = json.loads(cleaned_response)
        if "tool_call" in parsed_response:
            tool_call = parsed_response['tool_call']
            log_message(f"Planner decided to call tool: {tool_call}")
            tool_call['id'] = f"tool_call_{len(state['messages'])}"
            state['messages'].append(AIMessage(content="", tool_calls=[tool_call]))
        elif "response" in parsed_response:
            log_message(f"Planner decided to respond directly: {parsed_response['response']}")
            state['messages'].append(AIMessage(content=parsed_response['response']))
        else:
            log_message(f"Planner returned unexpected JSON: {cleaned_response}")
            state['messages'].append(AIMessage(content=f"收到了意外的规划结果: {cleaned_response}"))
    except json.JSONDecodeError:
        log_message(f"Planner failed to return JSON. Raw output: {cleaned_response}")
        state['messages'].append(AIMessage(content=cleaned_response))
    
    state['log'].append("Planner node finished.")
    return state