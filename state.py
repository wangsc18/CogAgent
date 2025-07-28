# state.py
from typing import TypedDict, List
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    定义核心对话Agent的共享状态。
    所有字段都在会话开始时被初始化。
    """
    # 对话的核心：一个包含所有类型消息的列表
    messages: List[BaseMessage]
    
    # 一个用于调试的日志列表
    log: List[str]

    # 用户状态
    user_state: dict