# agents/tool_manager.py
from typing import Dict
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage
from state import AgentState
from utils.helpers import log_message

async def run_tool_manager(state: AgentState, executable_tools: Dict[str, BaseTool]) -> AgentState:
    """
    异步执行工具的节点。
    """
    log_message(f"--- Tool Manager ---")
    state['log'].append("Tool Manager node started.")
    
    last_message = state['messages'][-1]
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        log_message("No tool calls found in the last message.")
        return state

    tool_call = last_message.tool_calls[0]
    tool_name = tool_call.get("name")
    tool_params = tool_call.get("args", {})
    tool_call_id = tool_call.get("id")

    log_message(f"Preparing to execute tool: {tool_name} with params: {tool_params}")
    
    tool_to_execute = executable_tools.get(tool_name)
    
    if not tool_to_execute:
        result = f"错误: 找不到名为 '{tool_name}' 的工具。"
        log_message(result)
    else:
        try:
            result = await tool_to_execute.ainvoke(tool_params)
            log_message(f"Tool {tool_name} executed successfully. Result: {result}")
        except Exception as e:
            result = f"错误: 执行工具 '{tool_name}' 时发生异常: {e}"
            log_message(result)

    state['messages'].append(
        ToolMessage(content=str(result), tool_call_id=tool_call_id)
    )
    
    state['log'].append("Tool Manager node finished.")
    return state