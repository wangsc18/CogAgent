# agents/planner.py
import re
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
# Agent角色与行为准则
你是一个顶级的“AI认知伙伴”，具备**共情能力、长期记忆和对用户心智状态的深刻洞察力**。你的核心准则是**尊重并解决用户的每一个直接请求**，同时运用心智理论（ToM）来**预见并服务于用户更深层次的目标**，最终以最小化用户的认知努力和情感负担为目标。

# 你的心智理论驱动的思考流程 (ToM-driven Thinking Process):
你必须严格遵循以下三个步骤进行思考和决策。

**步骤 1: 意图层次化分析 (Hierarchical Intent Analysis)**

1.  **识别用户的显性意图 (Explicit Intent)**: 准确识别用户最新请求中的**直接任务或问题 (A)**。这是你必须首先解决的核心。
    *   *ToM思考: "用户明确要求我做什么？这个任务的边界是什么？"*

2.  **推断用户的隐性目标 (Implicit Goal)**: 结合对话历史、附加上下文以及`cognitive_context`，推断出驱动用户提出显性意图A的**更深层次的目标 (B)**。
    *   *ToM思考: "用户完成任务A，是为了实现哪个更大的目标B？例如，用户要求‘写一个Python函数来读取CSV’(A)，其隐性目标可能是‘完成数据分析报告’(B)。"*

3.  **判断信息缺口 (Information Gap Assessment)**:
    -   基于你对用户**显性意图(A)和隐性目标(B)**的层次化理解，判断你当前拥有的信息是否足以同时满足这两个层面。
    -   **决策**:
        *   **如果信息不足以完成显性意图(A)**: 你的任务是**提问以补全完成A所需的核心信息**。**立即停止**并使用 `response` 格式输出问题。
        *   **如果信息足以完成A，但不足以更好地服务于B**: 在完成A的同时，**可以提供一个“可选的”深化步骤**来探寻B。继续执行步骤2。
        *   **如果信息完全充足**: 继续执行步骤2。

**步骤 2: 层次化行动决策 (Hierarchical Action Decision)**

*此步骤仅在信息足以完成显性意图(A)时执行。*

1.  **【核心任务解决】**: 首先，聚焦于**完全满足用户的显性意图(A)**。
    *   **工具优先**: 检查是否有工具能直接、高效地完成任务A。如果存在，**优先生成 `tool_call`**。
    *   **直接回答**: 如果没有合适的工具，则生成一个**直接、精准的 `response`** 来回答问题A。

2.  **【目标导向增强 (可选)】**: 在制定了解决A的方案后，思考是否能**“多走一步”**来帮助用户达成隐性目标(B)。
    *   **ToM思考**: *"既然我已经帮用户解决了读取CSV(A)的问题，我是否可以主动提供下一步的数据可视化(B)建议，或者询问他是否需要帮助分析数据？"*
    *   **决策**: 如果存在增强方案，并且你判断用户的认知状态良好（非高负荷），可以在你的`response`中**附加一个开放性的、非强制的建议**。例如：“代码已生成。顺便问一下，您接下来是需要对这些数据进行分析或可视化吗？我也可以提供帮助。” 如果你选择调用工具，可以在工具执行后的`response`中提出这个建议。

**步骤 3: 遵循特定规则 (按优先级排序)**

*在生成最终的 `tool_call` 或 `response` 时，你必须遵循以下规则：*

*   **【处理附加信息】**: 如果有文件或图片，你的决策必须优先处理这些**用户主动提供的“焦点”信息**。
*   **【处理工具结果】**: 如果上一轮是 `tool` 结果，你的任务是**解读结果并将其转化为对用户最有价值的洞察**，而不仅仅是简单总结。
*   **【遵循用户心智模型】**: 你的沟通风格和行为模式应始终与你对用户的长期心智模型（`user_habits` 和 `memory_context`）保持一致，**提供一种连贯且可预测的交互体验**。
*   **【考虑用户认知状态】**: 在做出决策时，考虑用户当前的认知负荷，高认知负荷下回答应尽量简短，由一句回答与一句必要的理由组成。

{user_habits_str}
{cognitive_context_str}
{memory_context_str}
{current_file_context_str}
# 对话历史:
{history_str}
# 可用工具列表:
{json.dumps(tools_config, indent=2, ensure_ascii=False)}

** 注意 **： 你的所有回复都应该先直接回答用户的问题，绝对不能有“我将进行分析”等未来时的表达，而是直接给出分析结果。

# 输出格式指令:
你的最终输出**必须**严格遵循以下JSON格式之一，不要加任何说明或 markdown 代码块。
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
    json_str = None
    # 优先寻找被 ```json ... ``` 包围的代码块
    match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", response_str, re.DOTALL)
    if match:
        json_str = match.group(1)
        log_message("Found JSON within a markdown code block.")
    else:
        # 如果没有找到代码块，则尝试从字符串中提取第一个有效的JSON对象
        # 这对于处理不带markdown标记的纯JSON输出很有用
        match = re.search(r'\{[\s\S]*\}', response_str)
        if match:
            json_str = match.group(0)
            log_message("Found JSON directly in the response string.")

    # 如果两种方法都找不到JSON，则将整个响应视为直接回复
    if not json_str:
        log_message("No JSON object found in the response. Treating as a direct reply.")
        state['messages'].append(AIMessage(content=response_str))
        state['log'].append("Planner node finished (direct reply).")
        return state
    
    # --- 开始解析提取出的 JSON 字符串 ---
    try:
        parsed_response = json.loads(json_str)
        
        if "tool_call" in parsed_response or "tool_calls" in parsed_response:
            raw_tool_calls = parsed_response.get("tool_call") or parsed_response.get("tool_calls")
            
            if not isinstance(raw_tool_calls, list):
                raw_tool_calls = [raw_tool_calls]
            
            valid_tool_calls = []
            for tool_call in raw_tool_calls:
                if not isinstance(tool_call, dict):
                    log_message(f"Skipping invalid tool call item: {tool_call}")
                    continue
                
                tool_name = tool_call.get("name") or tool_call.get("tool_name")

                # 只有当 tool_name 是一个非空字符串时，才认为这个工具调用是有效的
                if tool_name and isinstance(tool_name, str):
                    formatted_call = {
                        "name": tool_name,
                        "args": tool_call.get("args") or tool_call.get("parameters") or {},
                        "id": tool_call.get("id", f"tool_call_{len(state['messages'])}_{len(valid_tool_calls)}")
                    }
                    valid_tool_calls.append(formatted_call)
                else:
                    # 如果 tool_name 是 None 或无效，则记录日志并跳过
                    log_message(f"Skipping tool call with invalid or missing name: {tool_call}")
            
            if valid_tool_calls:
                log_message(f"Planner decided to call tools: {valid_tool_calls}")
                state['messages'].append(AIMessage(content="", tool_calls=valid_tool_calls))
            else:
                log_message(f"Planner found 'tool_call' key but failed to parse any valid tools. Raw: {raw_tool_calls}")
                state['messages'].append(AIMessage(content="我试图调用一个工具，但收到了无法解析的指令。"))

        elif "response" in parsed_response:
            log_message(f"Planner decided to respond directly: {parsed_response['response']}")
            state['messages'].append(AIMessage(content=parsed_response['response']))
        else:
            log_message(f"Planner returned unexpected JSON structure: {json_str}")
            # 如果JSON结构不符合预期，返回整个JSON作为内容，方便调试
            state['messages'].append(AIMessage(content=f"收到了意外的规划结果: ```json\n{json_str}\n```"))

    except json.JSONDecodeError:
        log_message(f"Failed to decode JSON. The LLM response might be a mix of text and malformed JSON. Raw response: {response_str}")
        # 如果JSON解析失败，说明LLM的输出既不是标准JSON，也不是纯文本
        # 此时，将原始、未裁剪的完整回复返回给用户是最好的选择
        state['messages'].append(AIMessage(content=response_str))
    
    state['log'].append("Planner node finished.")
    return state