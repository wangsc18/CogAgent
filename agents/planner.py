# agents/planner.py
import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from state import AgentState
from utils.helpers import log_message

MAX_FILE_CONTENT_CHARS = 12000

async def run_planner(state: AgentState, llm, tools_config: dict, user_habits: dict, executable_tools: dict) -> AgentState:
    """
    核心决策节点。它能处理标准文本和多模态输入，
    并会结合用户的长期习惯和【由后台服务持续更新的实时状态】进行决策。
    """
    log_message("--- Planner ---")
    state['log'].append("Planner node started.")

    # --- 0. 准备所有文本上下文，无论输入是什么类型 ---
    user_state = state.get("user_state", {})
    cognitive_context_str = f"\n# 用户当前实时状态:\n{json.dumps(user_state, indent=2, ensure_ascii=False)}\n" if user_state else ""
    user_habits_str = f"\n# 用户长期偏好:\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}\n" if user_habits else ""

    messages = state['messages']
    last_message = messages[-1]

    # --- 1. 记忆检索 ---
    memory_context_str = ""
    if isinstance(last_message, HumanMessage) and last_message.content:
        log_message("Planner performing memory retrieval...")
        search_tool = executable_tools.get("search_nodes")
        if search_tool:
            try:
                # 使用用户的最新消息作为查询，搜索相关的记忆节点
                query = last_message.content
                search_results = await search_tool.ainvoke({"query": query})
                
                if search_results:
                    log_message(f"Found relevant memories: {search_results}")
                    # 将搜索结果格式化，以便注入到Prompt中
                    memory_context_str = f"""
# 相关记忆:
以下是我根据你当前的问题，从记忆中找到的关于你的相关工作习惯和信息。我将利用这些信息来更好地帮助你。
```json
{json.dumps(search_results, indent=2, ensure_ascii=False)}
"""
                else:
                    log_message("No relevant memories found for the current query.")
            except Exception as e:
                log_message(f"Error during memory retrieval: {e}")
    
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
你是一个能够感知用户实时状态、并且拥有长期记忆的、有同理心的对话助手。你的行为必须精确、高效，并且永远以最少的交互次数解决用户问题为目标。

# 你的思考流程 (Thinking Process):
你必须严格遵循以下三个步骤进行思考和决策。

**步骤 1: 意图与信息评估 (Intent & Information Assessment)**

1.  **分析意图**: 仔细分析用户的最新请求和整个对话历史，理解用户的真实意图或问题。
2.  **评估信息完整性**: 在此基础上，判断你当前拥有的全部信息（对话历史、相关记忆、附加文件等）是否**完全足够**你做出一个明确的、可执行的行动（调用工具或给出最终答案）。
    *   **检查点**: 是否缺少关键信息？例如：用户说“总结这个文件”但没有附加文件；用户说“给Alice发邮件”但你不知道邮件内容或Alice的邮箱地址。
    *   **决策**:
        *   **如果信息不足**: 你的**唯一任务**就是向用户提问，以获取缺失的关键信息。**立即停止后续步骤**，并使用 `response` 格式输出你的问题。
        *   **如果信息充足**: 继续执行步骤 2。

**步骤 2: 行动决策 (Action Decision)**

*此步骤仅在信息充足时执行。*

1.  **【工具优先原则】**: 首先，将用户意图与【可用工具列表】进行匹配。
    *   **如果存在一个或多个可以直接满足用户意图的工具**:
        *   你的**唯一行动**就是生成一个或多个 `tool_call`。
        *   **行动指令**: **直接输出工具调用JSON。绝不要**用自然语言回复说“好的，我将要……”或描述你的计划。
        *   **立即停止**并输出 `tool_call`。

2.  **【直接回答原则】**: 仅当**不存在**任何合适的工具来满足用户意图时，才执行此步骤。
    *   你的行动是生成一个直接的、最终的回复。
    *   **行动指令**: **直接输出包含最终答案的完整回复。绝不要**返回任何确认性或计划性的中间回复，例如“好的，我将为您分析...”。
    *   输出 `response`。

**步骤 3: 遵循特定规则 (按优先级排序)**

*在生成最终的 `tool_call` 或 `response` 时，你必须遵循以下规则：*

*   **【处理附加文件/图片】**: 如果有附加信息，你的决策必须优先基于这些信息。
*   **【处理工具结果】**: 如果上一条消息是 `tool` 类型，你的任务是总结工具结果并告知用户。
*   **【遵循用户偏好】**: 你的沟通风格应始终参考用户的长期偏好（`user_habits`）和从【相关记忆】中检索到的信息。

{user_habits_str}
{cognitive_context_str}
{memory_context_str}
{current_file_context_str}
# 对话历史:
{history_str}
# 可用工具列表:
{json.dumps(tools_config, indent=2, ensure_ascii=False)}

# 输出格式指令:
你的最终输出**必须**严格遵循以下JSON格式之一，不包含任何其他文字。
格式1 (调用工具): {{"tool_call": {{...}}}} 或 {{"tool_calls": [{{...}}, {{...}}]}}
格式2 (直接回复/提问): {{"response": "..."}}
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
        if "tool_call" in parsed_response or "tool_calls" in parsed_response:
            # 兼容单个工具调用和多个工具调用两种情况
            raw_tool_calls = parsed_response.get("tool_call") or parsed_response.get("tool_calls")
            
            # 确保我们处理的是一个列表
            if not isinstance(raw_tool_calls, list):
                raw_tool_calls = [raw_tool_calls]
            
            # 准备一个列表来存放格式化后的工具调用
            valid_tool_calls = []

            # 遍历所有原始工具调用
            for tool_call in raw_tool_calls:
                if not isinstance(tool_call, dict):
                    log_message(f"Skipping invalid tool call item: {tool_call}")
                    continue
                
                # 字段名转换，兼容 LLM 误输出
                formatted_call = {
                    "name": tool_call.get("name") or tool_call.get("tool_name"),
                    "args": tool_call.get("args") or tool_call.get("parameters") or {}, # 确保args是字典
                    "id": tool_call.get("id", f"tool_call_{len(state['messages'])}_{len(valid_tool_calls)}")
                }
                valid_tool_calls.append(formatted_call)
            
            if valid_tool_calls:
                log_message(f"Planner decided to call tools: {valid_tool_calls}")
                # 将所有有效的工具调用放入一条 AIMessage 的 tool_calls 列表中
                state['messages'].append(AIMessage(content="", tool_calls=valid_tool_calls))
            else:
                # 如果LLM声称要调用工具，但格式完全错误，则提供一个回复
                log_message(f"Planner found tool_call key but failed to parse any valid tools. Raw: {raw_tool_calls}")
                state['messages'].append(AIMessage(content=f"我试图调用一个工具，但收到了无法解析的指令。"))

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