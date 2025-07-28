# core_agent.py
from langgraph.graph import StateGraph, END
from functools import partial
from state import AgentState
from agents.planner import run_core_planner
from agents.tool_manager import run_tool_manager
from langchain_core.messages import AIMessage

def build_core_agent_graph(dependencies: dict):
    """构建并返回一个编译好的核心对话Agent图。"""
    
    workflow = StateGraph(AgentState)

    # 使用 partial 绑定依赖
    planner_node = partial(run_core_planner, llm=dependencies["llm_text"], tools_config=dependencies["tools_config"])
    tool_manager_node = partial(run_tool_manager, executable_tools=dependencies["executable_tools"], llm=dependencies["llm_text"])

    workflow.add_node("planner", planner_node)
    workflow.add_node("tool_manager", tool_manager_node)

    workflow.set_entry_point("planner")

    def router(state: AgentState):
        last_message = state['messages'][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tool_manager"
        return END

    workflow.add_conditional_edges("planner", router, {"tool_manager": "tool_manager", "__end__": END})
    workflow.add_edge("tool_manager", "planner")

    return workflow.compile()