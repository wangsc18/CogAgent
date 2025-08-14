# agents/planner.py
import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from state import AgentState
from utils.helpers import log_message

MAX_FILE_CONTENT_CHARS = 12000

async def run_planner(state: AgentState, llm, tools_config: dict, user_habits: dict) -> AgentState:
    """
    核心决策节点。它能处理标准文本和多模态输入，
    并会结合用户的长期习惯和【由后台服务持续更新的实时状态】进行决策。
    """
    log_message("--- Planner ---")
    state['log'].append("Planner node started.")

    # --- 1. 准备所有文本上下文，无论输入是什么类型 ---
    user_state = state.get("user_state", {})
    cognitive_context_str = f"\n# 用户当前实时状态:\n{json.dumps(user_state, indent=2, ensure_ascii=False)}\n" if user_state else ""
    user_habits_str = f"\n# 用户长期偏好:\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}\n" if user_habits else ""

    messages = state['messages']
    last_message = messages[-1]
    
    # --- 2. 准备文件上下文和对话历史 ---
    current_file_context_str = ""
    if isinstance(last_message, HumanMessage) and last_message.additional_kwargs and "file" in last_message.additional_kwargs:
        file_info = last_message.additional_kwargs["file"]
        content = file_info.get("text_content")
        if content:
            file_name = file_info.get('name', 'N/A')
            if len(content) > MAX_FILE_CONTENT_CHARS:
                content = content[:MAX_FILE_CONTENT_CHARS] + f"\n\n[... 文件 '{file_name}' 内容过长，已被截断 ...]"
            current_file_context_str = f"\n# 附加的文件内容 (来自文件: {file_name}):\n--- START OF FILE CONTENT ---\n{content}\n--- END OF FILE CONTENT ---\n"
    
    formatted_history = []
    for msg in messages:
        content_str = ""
        # 统一处理 content，无论是 str, list 还是 dict
        if isinstance(msg.content, str):
            content_str = msg.content
        elif isinstance(msg.content, list):
            text_parts = [part['text'] for part in msg.content if part['type'] == 'text']
            content_str = "\n".join(text_parts) + " [附带一张图片]"
        elif isinstance(msg.content, dict): # 兼容旧的文件上传格式
             content_str = msg.content.get("text", str(msg.content))
        
        if isinstance(msg, HumanMessage) and msg.additional_kwargs and "file" in msg.additional_kwargs:
            content_str += f" [附加文件: {msg.additional_kwargs['file'].get('name')}]"
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            content_str += f" (Tool Call: {json.dumps(msg.tool_calls)})"
        formatted_history.append(f"{msg.type}: {content_str}")
    history_str = "\n".join(formatted_history)
    
    # --- 3. 构建统一的“思考指令” Prompt ---
    decision_prompt_text = f"""
你是一个能够感知用户实时状态的、有同理心的对话助手。

# 你的核心任务指令:
1.  **分析意图**: 首先，仔细分析用户的最新请求和整个对话历史，理解用户的真实意图或问题。
2.  **决策**: 根据意图，在以下行动中选择一个：
    a. **调用工具**: 如果用户的请求需要外部信息或特定功能，请选择调用相应的工具。
    b. **直接回复**: 如果你可以直接回答，请直接生成回复。
3.  **遵循特定规则 (按优先级排序)**:
    *   **【处理附加文件/图片】**: 如果上下文中存在文件内容或图片，并且用户的请求与此相关，你的**首要任务**是基于这些附加信息生成回答。
    *   **【处理工具结果】**: 如果对话历史的最后一条消息是 `tool` 类型，你的任务就是生成一段友好的文本，将这条 `tool` 消息的内容清晰地告知用户。
    *   **【感知用户状态】**: 如果用户的实时状态（`user_state`）显示高负荷（High Load），你的**所有文本回复都必须极其简洁**，最好是一句话或要点列表。
    *   **【遵循用户偏好】**: 总是优先考虑用户的长期偏好（`user_habits`）来决定你的沟通风格。

{user_habits_str}
{cognitive_context_str}
{current_file_context_str}
# 对话历史:
{history_str}
# 可用工具列表:
{json.dumps(tools_config, indent=2, ensure_ascii=False)}

严格按照以下JSON格式之一输出，不要有任何其他文字。
格式1 (调用工具): {{"tool_call": {{"name": "...", "args": {{...}}}}}}
格式2 (直接回复): {{"response": "..."}}
"""
    
    # --- 4. 根据输入类型，决定发送给 LLM 的最终数据格式 ---
    is_multimodal = isinstance(last_message.content, list)
    
    if is_multimodal:
        log_message("Planner preparing structured multimodal input.")
        # 提取图片部分
        image_part = next((part for part in last_message.content if part.get("type") == "image_url"), None)
        
        if image_part:
            # 将“思考指令”作为文本部分，与图片部分打包
            multimodal_content = [
                {"type": "text", "text": decision_prompt_text},
                image_part
            ]
            # 为了确保上下文完整，我们发送包含 SystemMessage 的历史 + 新的 HumanMessage
            llm_input = [msg for msg in messages[:-1] if isinstance(msg, SystemMessage)] + [HumanMessage(content=multimodal_content)]
            response = await llm.ainvoke(llm_input)
        else: # 如果列表里没有图片，按文本处理
            response = await llm.ainvoke(decision_prompt_text)
    else:
        log_message("Planner preparing standard text input.")
        # 对于纯文本/文档，直接发送“思考指令”
        response = await llm.ainvoke(decision_prompt_text)

    # --- 5. 统一处理 LLM 的 JSON 输出 (逻辑不变) ---
    response_str = response.content
    cleaned_response = response_str.strip().lstrip("```json").rstrip("```").strip()
    
    try:
        parsed_response = json.loads(cleaned_response)
        if "tool_call" in parsed_response:
            tool_call = parsed_response['tool_call']
            # 字段名转换，兼容 LLM 误输出
            tool_call = {
                "name": tool_call.get("name") or tool_call.get("tool_name"),
                "args": tool_call.get("args") or tool_call.get("parameters"),
                "id": tool_call.get("id", f"tool_call_{len(state['messages'])}")
            }
            log_message(f"Planner decided to call tool: {tool_call}")
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