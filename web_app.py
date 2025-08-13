# web_app.py (最终的、架构统一的正确版本)
import os
import sys
import json
import uuid
import queue
import base64
import asyncio
import tempfile
import threading
import traceback
from functools import partial
from flask import Flask, render_template, request, jsonify, Response
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage

from utils.activity_monitor import monitor
from utils.face_thread import visual_detector
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader

# --- 路径和模块导入 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir
sys.path.append(project_root)

from state import AgentState
from agents.planner import run_planner
from agents.tool_manager import run_tool_manager
from agents.user_state_modeler import UserStateModeler
from proactive_service import proactive_monitoring_loop
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from utils.mcp_config_loader import load_mcp_servers_config
from utils.helpers import setup_logging, load_user_habits

# --- 全局变量 ---
core_agent_app = None
SESSIONS = {}
message_queue = queue.Queue()
pending_assistance_requests = {}
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")

# --- 消息序列化和反序列化辅助函数 ---
def message_to_dict(message: BaseMessage) -> dict:
    return message.to_json()

def dict_to_message(data: dict) -> BaseMessage:
    message_type = data.get("type")
    content = data.get("content")
    if message_type == "human": return HumanMessage(content=content)
    if message_type == "ai": return AIMessage(content=content, tool_calls=data.get("tool_calls", []))
    if message_type == "tool": return ToolMessage(content=content, tool_call_id=data.get("tool_call_id"))
    if message_type == "system": return SystemMessage(content=content)
    return HumanMessage(content=str(data))

# --- 初始化函数 ---
def initialize_system():
    global core_agent_app
    print("--- System Initializing ---")
    monitor.start() # 键鼠进程
    visual_detector.start() # 视觉线程
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)
    setup_logging()
    os.environ['HTTP_PROXY'] = "http://127.0.0.1:7890"
    os.environ['HTTPS_PROXY'] = "http://127.0.0.1:7890"
    server_config = load_mcp_servers_config()
    mcp_client = MultiServerMCPClient(server_config["mcpServers"])
    print("Discovering MCP tools...")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    discovered_tools = loop.run_until_complete(mcp_client.get_tools())
    print(f"Discovered {len(discovered_tools)} tools.")
    tools_config = {tool.name: {"description": tool.description, "args_schema": tool.args_schema} for tool in discovered_tools}
    # for tool in discovered_tools:
    #     print(tool)
    executable_tools = {tool.name: tool for tool in discovered_tools}
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro")
    user_habits = load_user_habits()
    workflow = StateGraph(AgentState)
    planner_node = partial(run_planner, llm=llm, tools_config=tools_config, user_habits=user_habits)
    tool_manager_node = partial(run_tool_manager, executable_tools=executable_tools)
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
    core_agent_app = workflow.compile()
    print("--- Core Dialogue Agent Initialized Successfully ---")

# --- 会话状态函数 ---
def get_session_state(session_id: str) -> dict:
    if session_id in SESSIONS: return SESSIONS[session_id]
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(session_file):
        with open(session_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                state = {
                    "messages": [dict_to_message(msg) for msg in data.get("messages", [])],
                    "log": data.get("log", []),
                    "user_state": data.get("user_state", {})
                }
                SESSIONS[session_id] = state
                return state
            except (json.JSONDecodeError, TypeError): pass
    user_habits = load_user_habits()
    initial_messages = []
    if user_habits:
        habit_prompt = f"这是一个新对话的开始。请在整个对话中，始终记住并遵循以下关于我的个人信息和偏好：\n\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}"
        initial_messages.append(SystemMessage(content=habit_prompt))
    new_state = {"messages": initial_messages, "log": [], "user_state": {}}
    SESSIONS[session_id] = new_state
    save_session_state(session_id, new_state)
    return new_state

def save_session_state(session_id: str, state: dict):
    SESSIONS[session_id] = state
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    try:
        data_to_save = {
            "messages": [message_to_dict(msg) for msg in state.get("messages", [])],
            "log": state.get("log", []),
            "user_state": state.get("user_state", {})
        }
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving session '{session_id}' to file: {e}")

# --- 在全局作用域执行初始化和后台线程启动 ---
initialize_system()
app = Flask(__name__)
proactive_thread = threading.Thread(
    target=proactive_monitoring_loop, 
    args=(SESSIONS, message_queue, pending_assistance_requests),
    daemon=True
)
proactive_thread.start()

# --- 路由定义 ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
async def chat():
    try:
        data = request.get_json()
        user_input_text = data.get('message', '') # 确保有默认值
        session_id = data.get('session_id', 'default_session')
        file_data = data.get('file')
        
        current_state = get_session_state(session_id)
        
        # --- 根据附件类型决定如何构建 HumanMessage ---
        if file_data and file_data.get('type') == 'image':
            # --- 场景一：附件是图片（来自粘贴） ---
            print("Processing a pasted image...")
            multimodal_content = [
                {"type": "text", "text": user_input_text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{file_data['content']}"}}
            ]
            current_state['messages'].append(HumanMessage(content=multimodal_content))
            
        else:
            # --- 场景二：附件是文档（来自文件上传）或没有附件 ---
            extracted_text_content = None
            if file_data and file_data.get('content'):
                file_name = file_data.get('name', '')
                file_extension = os.path.splitext(file_name)[1].lower()
                
                try:
                    decoded_bytes = base64.b64decode(file_data['content'])
                    
                    # 对于非纯文本格式，我们需要将其写入临时文件
                    if file_extension not in [".txt", ".md", ".py", ".json", ".html", ".css", ".csv"]:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                            temp_file.write(decoded_bytes)
                            temp_file_path = temp_file.name
                    
                    loader = None
                    if file_extension == ".pdf":
                        loader = PyPDFLoader(temp_file_path)
                    elif file_extension == ".docx":
                        loader = Docx2txtLoader(temp_file_path)
                    elif file_extension in [".txt", ".md", ".py", ".json", ".html", ".css", ".csv"]:
                        extracted_text_content = decoded_bytes.decode('utf-8', errors='ignore')
                    else:
                        extracted_text_content = f"错误：不支持的文件类型 '{file_extension}'。我只能读取 .pdf, .docx, 和纯文本文件。"

                    if loader:
                        print(f"Using {type(loader).__name__} for file: {file_name}")
                        documents = await asyncio.to_thread(loader.load) # 异步执行IO密集型操作
                        extracted_text_content = "\n\n".join([doc.page_content for doc in documents])
                        os.unlink(temp_file_path) # 清理临时文件
                    
                    print(f"Successfully extracted text from '{file_name}'. Content length: {len(extracted_text_content)} chars.")

                except Exception as e:
                    print(f"Error processing file content for file '{file_name}': {e}")
                    extracted_text_content = f"错误：处理文件 '{file_name}' 时发生异常: {e}"
        
            additional_context = {}
            if file_data:
                additional_context['file'] = {
                    "name": file_data.get('name'),
                    "content": file_data.get('content'), # Base64 content for tools
                    "text_content": extracted_text_content # Decoded text for LLM
                }

            current_state = get_session_state(session_id)
            # 1. 'content' 只包含用户的纯文本输入
            # 2. 所有附加信息都放入 'additional_kwargs'
            current_state['messages'].append(
                HumanMessage(content=user_input_text, additional_kwargs=additional_context)
            )
        
        final_state = await core_agent_app.ainvoke(current_state, {"recursion_limit": 10})
        save_session_state(session_id, final_state)
        return jsonify({"response": final_state['messages'][-1].content})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"An error occurred: {e}"}), 500
    

@app.route('/listen')
def listen():
    def event_stream():
        while True:
            message = message_queue.get()
            yield f"data: {json.dumps(message)}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/request_assistance', methods=['POST'])
async def request_assistance():
    if not core_agent_app: return jsonify({"error": "Agent is not ready."}), 503
    try:
        data = request.get_json()
        request_id, session_id = data.get("request_id"), data.get("session_id")
        if not session_id: return jsonify({"error": "No active session ID provided."}), 400
        context_to_process = pending_assistance_requests.pop(request_id, None)
        if not context_to_process: return jsonify({"error": "Invalid or expired assistance request."}), 404
        prompt_content = UserStateModeler.format_prompt_after_confirmation(context_to_process)
        state = get_session_state(session_id)
        state['messages'].append(HumanMessage(content=prompt_content))
        final_state = await core_agent_app.ainvoke(state, {"recursion_limit": 10})
        save_session_state(session_id, final_state)
        return jsonify({"response": final_state['messages'][-1].content})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"An error occurred: {e}"}), 500
    
# --- 程序退出时停止后台监听器 ---
import atexit
atexit.register(monitor.stop)
