# agents/memory_agent.py

import json
from typing import Dict, List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, BaseMessage
from langchain_core.language_models import BaseLanguageModel
from state import AgentState
from utils.helpers import log_message

def format_conversation_history(messages: List[BaseMessage]) -> str:
    """将消息列表格式化为纯文本对话历史。"""
    history = []
    for msg in messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        # 忽略系统消息和工具消息，只保留对话内容
        if isinstance(msg, (HumanMessage, AIMessage)) and msg.content:
            history.append(f"{role}: {msg.content}")
    return "\n".join(history)

async def run_memory_agent(state: AgentState, llm: BaseLanguageModel, tools_config: Dict) -> AgentState:
    """
    记忆总结Agent的核心节点。
    它接收完整的对话历史，并生成一系列用于更新知识图谱的工具调用。
    """
    log_message("--- Memory Agent Started ---")
    state['log'].append("Memory Agent node started.")
    
    # 获取并格式化完整的对话历史
    conversation_history = format_conversation_history(state['messages'])

    # 构建专门用于记忆提炼的Prompt
    memory_extraction_prompt = f"""
你是一个专业的“用户工作习惯分析师”。你的唯一任务是分析一段完整的用户对话，识别其中与用户【工作内容】和【工作习惯】相关的关键信息，并将其转化为一系列可以更新知识图谱的工具调用。

# 你的核心指令:

1.  **分析焦点**: 你必须**只关注**与 `default_user` 的工作直接相关的信息。忽略闲聊、个人生活或其他与工作无关的话题。

2.  **识别工作实体**: 从对话中识别出用户正在处理的**核心工作对象或主题**。这些通常是文档类型、技术工具、项目名称或工作活动。
    *   **好的实体示例**: "PPT演示文稿", "Python代码审查", "项目Alpha", "客户会议", "数据分析报告"。
    *   **坏的实体示例**: "Alice" (除非Alice是一个重要的工作联系人), "徒步旅行", "下个月"。

3.  **提炼工作习惯**: 围绕识别出的工作实体，提炼出 `default_user` 在处理这些工作时的具体行为、偏好或方法。这些就是需要被记录的“观察结果”。
    *   **示例**: 如果用户上传了一个PPT并要求美化，那么针对“PPT演示文稿”这个实体，一个好的观察结果是：“倾向于寻求AI辅助来美化幻灯片布局和设计”。
    *   **示例**: 如果用户多次要求将代码片段转换为流程图，那么针对“Python代码审查”这个实体，一个好的观察结果是：“习惯于使用流程图来理解和梳理代码逻辑”。

4.  **记忆更新流程**:
    a) **创建实体 (`create_entities`)**: 为每一个你新识别出的核心工作对象创建一个实体。`entityType` 应设为 "工作主题" 或 "工作工具"。
    b) **建立关系 (`create_relations`)**: 使用 `create_relations` 将每一个新创建的工作实体与 `default_user` 连接起来。关系类型应该是描述性的，例如 `处理`、`使用`、`负责`。
    c) **添加观察结果 (`add_observations`)**: 使用 `add_observations` 将你在步骤3中提炼出的具体工作习惯，作为观察结果添加到对应的工作实体上。

# 对话历史:
--- START OF CONVERSATION ---
{conversation_history}
--- END OF CONVERSATION ---

# 可用的记忆工具:```json
{json.dumps(tools_config, indent=2, ensure_ascii=False)}

输出格式:
你的最终输出必须是一个JSON对象，其中包含一个名为 tool_calls 的列表。这个列表可以包含一个或多个你需要执行的工具调用。如果对话中没有任何与工作习惯相关的新信息，请返回一个空的 tool_calls 列表。
输出示例 (基于用户请求美化PPT的对话):
{{
"tool_calls": [
{{
"name": "create_entities",
"args": {{
"entities": [
{{"name": "PPT演示文稿", "entityType": "工作主题", "observations": []}}
]
}}
}},
{{
"name": "create_relations",
"args": {{
"relations": [
{{"from": "default_user", "to": "PPT演示文稿", "relationType": "处理"}}
]
}}
}},
{{
"name": "add_observations",
"args": {{
"observations": [
{{"entityName": "PPT演示文稿", "contents": ["倾向于寻求AI辅助来美化幻灯片布局和设计", "关注幻灯片的视觉呈现效果"]}}
]
}}
}}
]
}}
"""
    
    try:
        response = await llm.ainvoke(memory_extraction_prompt)
        response_content = response.content.strip().lstrip("```json").rstrip("```").strip()
        log_message(f"Memory Agent LLM Raw Response: {response_content}")
        
        parsed_response = json.loads(response_content)
        
        # 将LLM生成的tool_calls转换为LangGraph期望的格式
        tool_calls_for_graph = []
        if "tool_calls" in parsed_response and parsed_response["tool_calls"]:
            for i, tool_call in enumerate(parsed_response["tool_calls"]):
                tool_calls_for_graph.append({
                    "name": tool_call.get("name"),
                    "args": tool_call.get("args", {}),
                    "id": f"memory_tool_call_{i}"
                })

        log_message(f"Memory Agent decided to call tools: {tool_calls_for_graph}")
        # 将所有工具调用放入一条 AIMessage 中
        state['messages'].append(AIMessage(content="", tool_calls=tool_calls_for_graph))

    except Exception as e:
        log_message(f"Memory Agent failed: {e}")
        # 即使失败，也附加一条空消息以正常结束
        state['messages'].append(AIMessage(content="记忆提炼失败。"))

    state['log'].append("Memory Agent node finished.")
    return state