# agents/planner.py
import json
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from state import AgentState
from utils.helpers import log_message

MAX_FILE_CONTENT_CHARS = 12000

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

    # --- 2. 格式化完整的历史记录 ---
    last_message = state['messages'][-1]
    
    current_file_context_str = ""
    file_info = {}
    # 【核心修正】从 additional_kwargs 中安全地获取文件信息
    if isinstance(last_message, HumanMessage) and last_message.additional_kwargs and "file" in last_message.additional_kwargs:
        file_info = last_message.additional_kwargs["file"]
        content = file_info.get("text_content")
        
        if content:
            file_name = file_info.get('name', 'N/A')
            if len(content) > MAX_FILE_CONTENT_CHARS:
                content = content[:MAX_FILE_CONTENT_CHARS] + f"\n\n[... 文件 '{file_name}' 内容过长，已被截断 ...]"
            
        current_file_context_str = f"""
        # 附加的文件内容 (来自文件: {file_name}):
        --- START OF FILE CONTENT ---
        {content}
        --- END OF FILE CONTENT ---
        """

    # 使用健壮的、能处理多种消息类型的历史记录格式化逻辑
    formatted_history = []
    for msg in state['messages']:
        # HumanMessage 的 content 现在保证是字符串
        content_str = str(msg.content)
        
        # 检查是否有附加文件，并在历史记录中进行标注
        if isinstance(msg, HumanMessage) and msg.additional_kwargs and "file" in msg.additional_kwargs:
            file_name = msg.additional_kwargs["file"].get("name")
            content_str += f" [附加文件: {file_name}]"

        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            content_str += f" (Tool Call: {json.dumps(msg.tool_calls)})"
            
        formatted_history.append(f"{msg.type}: {content_str}")
    history_str = "\n".join(formatted_history)

    user_habits_str = f"\n# 用户长期偏好:\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}\n" if user_habits else ""

    # --- 3. 判断场景 ---
    # --- 场景一：最后一条消息是工具结果，我们的目标是“总结陈词” ---
    if isinstance(last_message, ToolMessage):
        log_message("Planner detected a tool result. Focusing on presenting the result.")
        prompt = f"""
        你是一个对话的总结者。你的前一步行动（调用工具）已经完成，现在你的唯一任务是将工具返回的结果呈现给用户。

        # 对话历史:
        {history_str}

        # 你的任务:
        1.  查看对话历史中的最后一条 `tool` 消息。
        2.  生成一段友好的、人性化的文本，将这条 `tool` 消息的内容清晰地告知用户。

        严格按照以下JSON格式输出：
        {{"response": "给用户的、包含了工具结果的回答内容"}}
        """

    # --- 场景二：最后一条消息是用户输入（包括多模态），我们的目标是“决策行动” ---
    else:
        log_message("Planner processing a user request. Deciding next action.")
        
        # 多模态内容的增强逻辑
        is_multimodal = isinstance(last_message.content, list)
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
    
    
# 需要根据habits修改主动服务生成内容的风格

        prompt = f"""
        你是一个能够感知用户实时状态的、有同理心的对话助手。
        {user_habits_str}
        {cognitive_context_str}
        {current_file_context_str}
        # 对话历史:
        {history_str}
        # 可用工具列表:
        {json.dumps(tools_config, indent=2, ensure_ascii=False)}

        # 你的核心任务指令:
        1.  **分析意图**: 首先，仔细分析用户的最新请求和整个对话历史，理解用户的真实意图。
        2.  **决策**: 根据意图，在以下行动中选择一个：
            a. **调用工具**: 如果用户的请求需要外部信息或特定功能，请选择调用相应的工具。
            b. **直接回复**: 如果你可以直接回答，请直接生成回复。
        3.  **遵循特定规则 (按优先级排序)**:
            *   **【处理附加文件】**: 如果“附加的文件内容”部分存在，并且用户的请求与该文件内容相关（例如“总结一下”、“这个文档讲了什么？”），你的**首要任务**是基于该文件内容生成回答。只有当用户的请求是关于文件本身的操作（如“转换格式”）时，才考虑调用工具。
            *   **【处理工具结果】**: 如果对话历史的最后一条消息是 `tool` 类型，你的任务就是生成一段友好的文本，将这条 `tool` 消息的内容清晰地告知用户。
            *   **【感知用户状态】**: 如果用户的实时状态（`user_state`）显示高负荷（例如 `keyboard_hz > 5.0`），你的**所有文本回复都必须极其简洁**，最好是一句话或要点列表。
            *   **【遵循用户偏好】**: 总是优先考虑用户的长期偏好（`user_habits`）来决定你的沟通风格。
        """

        prompt += """
        严格按照以下JSON格式之一输出...
        格式1 (调用工具): {"tool_call": {"name": "工具名称", "args": "工具参数对象", "id": "工具调用ID"}}
        格式2 (直接回复): {"response": "..."}
        """
    
    response_str = llm.invoke(prompt).content
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