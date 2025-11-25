# agents/meta_controller.py
import re
import ast
import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from state import AgentState
from utils.helpers import log_message
from agents.prompts import get_meta_controller_decision_prompt, get_meta_controller_decision_prompt_ablation

MAX_FILE_CONTENT_CHARS = 12000

async def run_meta_controller(state: AgentState, llm, tools_config: dict, user_habits: dict, executable_tools: dict) -> AgentState:
    """
    核心决策节点（元控制器）。它能处理标准文本和多模态输入，
    并会结合用户的长期习惯和【由后台服务持续更新的实时状态】进行决策。
    """
    log_message("--- MetaController ---")
    state['log'].append("MetaController node started.")

    # --- 0. 准备所有文本上下文，无论输入是什么类型 ---
    user_state = state.get("user_state", {})
    cognitive_context_str = f"\n# 用户当前实时状态:\n{json.dumps(user_state, indent=2, ensure_ascii=False)}\n" if user_state else ""
    user_habits_str = f"\n# 用户长期偏好:\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}\n" if user_habits else ""

    messages = state['messages']
    last_message = messages[-1]

    # --- 1. 记忆检索 ---
    memory_context_str = ""
    if isinstance(last_message, HumanMessage) and last_message.content:
        log_message("MetaController performing memory retrieval...")
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

    # --- 3. 【使用prompts模块】构建统一的"思考指令" Prompt ---
    decision_prompt_text = get_meta_controller_decision_prompt(
        user_habits_str=user_habits_str,
        cognitive_context_str=cognitive_context_str,
        memory_context_str=memory_context_str,
        current_file_context_str=current_file_context_str,
        history_str=history_str,
        tools_config=tools_config
    )

    # 如需消融实验，使用以下版本（不包含认知状态感知）：
    # decision_prompt_text = get_meta_controller_decision_prompt_ablation(
    #     user_habits_str=user_habits_str,
    #     memory_context_str=memory_context_str,
    #     current_file_context_str=current_file_context_str,
    #     history_str=history_str,
    #     tools_config=tools_config
    # )

    # --- 4. 根据输入类型，决定发送给 LLM 的最终数据格式 ---
    is_multimodal = isinstance(last_message.content, list)

    if is_multimodal:
        log_message("MetaController preparing structured multimodal input.")
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
            response = await llm.ainvoke([HumanMessage(content=decision_prompt_text)])
    else:
        log_message("MetaController preparing standard text input.")
        # 对于纯文本/文档，直接发送"思考指令"
        response = await llm.ainvoke([HumanMessage(content=decision_prompt_text)])

    # --- 5. 统一处理 LLM 的 JSON 输出 (逻辑不变) ---
    response_str = response.content
    print("meta_controller:", response_str)
    json_str = None
    # json_str 的提取逻辑保持不变
    match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", response_str, re.DOTALL)
    if match: json_str = match.group(1)
    else:
        match = re.search(r'\{[\s\S]*\}', response_str)
        if match: json_str = match.group(0)

    if not json_str:
        log_message("No JSON object found in the response. Treating as a direct reply.")
        state['messages'].append(AIMessage(content=response_str))
        return state
    
    try:
        parsed_response = json.loads(json_str)
        
        valid_tool_calls = []
        action_taken = False

        # --- 决策逻辑：按优先级顺序检查所有可能的格式 ---

        # 优先级 1: 检查标准 'tool_call' 或 'tool_calls'
        if "tool_call" in parsed_response or "tool_calls" in parsed_response:
            action_taken = True
            raw_tool_calls = parsed_response.get("tool_call") or parsed_response.get("tool_calls")
            if not isinstance(raw_tool_calls, list): raw_tool_calls = [raw_tool_calls]
            for tool_call in raw_tool_calls:
                # 标准校验逻辑
                if isinstance(tool_call, dict) and isinstance(tool_call.get("name"), str):
                    valid_tool_calls.append({ "name": tool_call["name"], "args": tool_call.get("args") or {}, "id": tool_call.get("id", f"tool_call_{len(state['messages'])}_{len(valid_tool_calls)}") })

        # 优先级 2: 检查 'tool_code' 格式
        elif "tool_code" in parsed_response:
            action_taken = True
            # ast解析逻辑
            try:
                code_str = parsed_response['tool_code']
                if code_str.strip().startswith("print("): code_str = code_str.strip()[6:-1]
                tree = ast.parse(code_str)
                call_node = tree.body[0].value
                if isinstance(call_node, ast.Call):
                    tool_name = getattr(call_node.func, 'attr', getattr(call_node.func, 'id', None))
                    if tool_name:
                        args = {kw.arg: ast.literal_eval(kw.value) for kw in call_node.keywords}
                        valid_tool_calls.append({ "name": tool_name, "args": args, "id": f"tool_call_{len(state['messages'])}_parsed" })
            except Exception as e:
                log_message(f"Failed to parse 'tool_code': {e}")
                state['messages'].append(AIMessage(content=f"收到了无法解析的工具代码: `{parsed_response['tool_code']}`"))

        # 【核心修复】优先级 3: 检查“裸露”的工具调用格式
        elif isinstance(parsed_response, dict) and "name" in parsed_response and "args" in parsed_response:
            action_taken = True
            log_message("Detected and correcting a 'naked' tool call object.")
            tool_name = parsed_response.get("name")
            if tool_name and isinstance(tool_name, str):
                valid_tool_calls.append({
                    "name": tool_name,
                    "args": parsed_response.get("args") or {},
                    "id": parsed_response.get("id", f"tool_call_{len(state['messages'])}_naked")
                })

        # 优先级 4: 检查 'response'
        elif "response" in parsed_response:
            action_taken = True
            log_message(f"MetaController decided to respond directly: {parsed_response['response']}")
            state['messages'].append(AIMessage(content=parsed_response['response']))

        # --- 统一处理最终结果 ---
        if valid_tool_calls:
            log_message(f"MetaController decided to call tools: {valid_tool_calls}")
            state['messages'].append(AIMessage(content="", tool_calls=valid_tool_calls))
        elif not action_taken:
            # 如果所有检查都失败了，这才是真正的"意外结构"
            log_message(f"MetaController returned unexpected JSON structure: {json_str}")
            state['messages'].append(AIMessage(content=f"收到了意外的规划结果: ```json\n{json_str}\n```"))

    except json.JSONDecodeError:
        log_message(f"Failed to decode JSON. Raw response: {response_str}")
        state['messages'].append(AIMessage(content=response_str))

    state['log'].append("MetaController node finished.")
    return state