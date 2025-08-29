# web_app.py (最终的、架构统一的正确版本)
import os
import sys
import json
import uuid
import base64
import asyncio
import tempfile
import threading
import traceback
from functools import partial
from quart import Quart, render_template, request, jsonify, Response
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage

from utils.activity_monitor import monitor
from utils.face_thread import visual_detector
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader

# --- 路径和模块导入 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir
sys.path.append(project_root)

from datetime import datetime
from state import AgentState
from agents.planner import run_planner
from agents.tool_manager import run_tool_manager
from agents.user_state_modeler import UserStateModeler
from agents.memory_agent import run_memory_agent
from proactive_service import proactive_monitoring_loop
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from utils.mcp_config_loader import load_mcp_servers_config
from utils.helpers import setup_logging, load_user_habits, log_message, get_real_time_user_activity

from dotenv import load_dotenv
load_dotenv()

# --- 全局变量 ---
llm = None  # <--- 将llm设为全局变量
tools_config = {} # <--- 将tools_config设为全局变量
executable_tools = {} # <--- 将executable_tools设为全局变量
core_agent_app = None
memory_agent = None
SESSIONS = {}
message_queue = asyncio.Queue()
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
    global core_agent_app, memory_agent_app, llm, tools_config, executable_tools
    print("--- System Initializing ---")
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)
    setup_logging()
    # os.environ['HTTP_PROXY'] = "http://127.0.0.1:7890"
    # os.environ['HTTPS_PROXY'] = "http://127.0.0.1:7890"
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
    executable_tools = {tool.name: tool for tool in discovered_tools}

    # llm = AzureChatOpenAI(
    #     temperature=0,
    #     # AzureChatOpenAI 会自动从环境变量读取这些值，但显式传递更清晰
    #     api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    #     api_version=os.getenv("OPENAI_API_VERSION"),
    #     azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    #     azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"), 
    # )
    llm = ChatOpenAI(model='gemini-2.5-pro', temperature=0)

    user_habits = load_user_habits()
    workflow = StateGraph(AgentState)
    planner_node = partial(run_planner, llm=llm, tools_config=tools_config, user_habits=user_habits, executable_tools=executable_tools)
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

    # --- 构建和编译记忆Agent工作流 ---
    print("--- Building Memory Agent ---")
    memory_workflow = StateGraph(AgentState)

    # 筛选出只用于记忆的工具
    memory_tool_names = [
        "create_entities", "create_relations", "add_observations",
        "delete_entities", "delete_observations", "delete_relations",
        "read_graph", "search_nodes", "open_nodes"
    ]
    memory_tools_config = {name: tools_config[name] for name in memory_tool_names if name in tools_config}
    
    memory_agent_node = partial(run_memory_agent, llm=llm, tools_config=memory_tools_config)
    
    # 记忆Agent只需要两个节点：提炼节点 和 执行所有工具的节点
    memory_workflow.add_node("memory_agent", memory_agent_node)
    
    # 复用现有的 tool_manager 节点
    memory_tool_manager_node = partial(run_tool_manager, executable_tools=executable_tools)
    memory_workflow.add_node("tool_manager", memory_tool_manager_node)
    
    memory_workflow.set_entry_point("memory_agent")
    
    # 记忆Agent提炼完工具调用后，直接交给 tool_manager 执行，然后结束
    memory_workflow.add_edge("memory_agent", "tool_manager")
    memory_workflow.add_edge("tool_manager", END)
    
    memory_agent_app = memory_workflow.compile()
    print("--- Memory Agent Initialized Successfully ---")

# --- 会话状态函数 ---
async def get_session_state(session_id: str) -> dict: # 1. 改为 async def
    if session_id in SESSIONS: return SESSIONS[session_id]
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    
    if os.path.exists(session_file):
        try:
            # 2. 将同步的IO操作放入后台线程执行
            def _read_file():
                with open(session_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            data = await asyncio.to_thread(_read_file)
            
            state = {
                "messages": [dict_to_message(msg) for msg in data.get("messages", [])],
                "log": data.get("log", []),
                "user_state": data.get("user_state", {})
            }
            SESSIONS[session_id] = state
            return state
        except (json.JSONDecodeError, TypeError, IOError):
             pass # 如果读取或解析失败，则继续执行下面的逻辑来创建新状态

    # 创建新会话的逻辑保持不变
    user_habits = load_user_habits()
    initial_messages = []
    if user_habits:
        habit_prompt = f"这是一个新对话的开始。请在整个对话中，始终记住并遵循以下关于我的个人信息和偏好：\n\n{json.dumps(user_habits, indent=2, ensure_ascii=False)}"
        initial_messages.append(SystemMessage(content=habit_prompt))
    new_state = {"messages": initial_messages, "log": [], "user_state": {}}
    SESSIONS[session_id] = new_state
    # 第一次创建时，我们也可以异步地保存它
    await save_session_state(session_id, new_state) 
    return new_state

async def save_session_state(session_id: str, state: dict): # 1. 改为 async def
    SESSIONS[session_id] = state
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    
    try:
        data_to_save = {
            "messages": [message_to_dict(msg) for msg in state.get("messages", [])],
            "log": state.get("log", []),
            "user_state": state.get("user_state", {})
        }
        
        # 2. 将同步的IO操作放入后台线程执行
        def _write_file():
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write_file)

    except Exception as e:
        print(f"Error saving session '{session_id}' to file: {e}")

# --- 在全局作用域执行初始化和后台线程启动 ---
initialize_system()
app = Quart(__name__)

@app.before_serving
async def startup_background_tasks():
    print("--- Starting background tasks ---")
    app.add_background_task(
        proactive_monitoring_loop,
        sessions_dict=SESSIONS,
        msg_queue=message_queue,
        request_cache=pending_assistance_requests
    )
    
# --- 路由定义 ---
@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/chat', methods=['POST'])
async def chat():
    try:
        data = await request.get_json()
        user_input_text = data.get('message', '') # 确保有默认值
        session_id = data.get('session_id', 'default_session')
        file_data = data.get('file')
        
        current_state = await get_session_state(session_id)
        
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

            current_state = await get_session_state(session_id)
            # 1. 'content' 只包含用户的纯文本输入
            # 2. 所有附加信息都放入 'additional_kwargs'
            current_state['messages'].append(
                HumanMessage(content=user_input_text, additional_kwargs=additional_context)
            )
        
        final_state = await core_agent_app.ainvoke(current_state, {"recursion_limit": 10})
        await save_session_state(session_id, final_state)
        return jsonify({"response": final_state['messages'][-1].content})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"An error occurred: {e}"}), 500
    

@app.route('/listen')
async def listen():
    async def event_stream():
        while True:
            try:
                message = await message_queue.get()
                yield f"data: {json.dumps(message)}\n\n"
            except asyncio.CancelledError:
                break
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/request_assistance', methods=['POST'])
async def request_assistance():
    if not core_agent_app: return jsonify({"error": "Agent is not ready."}), 503
    try:
        data = await request.get_json()
        request_id, session_id = data.get("request_id"), data.get("session_id")
        if not session_id: return jsonify({"error": "No active session ID provided."}), 400
        context_to_process = pending_assistance_requests.pop(request_id, None)
        if not context_to_process: return jsonify({"error": "Invalid or expired assistance request."}), 404

        # 1. 调用 Analyzer Agent 进行分析
        analysis_result = await UserStateModeler.analyze_user_context_and_suggest(
            context=context_to_process,
            llm=llm, # 使用全局的、支持视觉的LLM
            tools_config=tools_config # 传递可用的工具
        )

        if not analysis_result.get("recommended_tool"):
            # 如果分析失败或没有建议，直接返回错误信息
            return jsonify({"response": analysis_result.get("suggestion_text", "分析失败，无法提供建议。")})
        
        # 2. 基于分析结果，构建一个清晰的 "Handoff" 消息给主Agent
        handoff_prompt = f"""
我刚刚确认需要帮助。我的主动式助理分析了我的情况，并给出了以下建议：

- **它认为我正在做**: {analysis_result['user_intent']}
- **它建议的操作**: {analysis_result['suggestion_text']}
- **它建议使用的工具**: `{analysis_result['recommended_tool']}`
- **理由**: {analysis_result['reasoning']}

请根据这个建议继续操作。如果这是一个工具调用，请直接准备并执行它。
"""

        # 3. 将这个 Handoff 消息作为用户的最新输入，送入主工作流
        state = await get_session_state(session_id)
        state['messages'].append(HumanMessage(content=handoff_prompt))
        
        final_state = await core_agent_app.ainvoke(state, {"recursion_limit": 10})
        await save_session_state(session_id, final_state)

        return jsonify({
                "analysis_message": f"系统分析完成，正在执行建议...\n\n---\n{analysis_result['suggestion_text']}\n理由: {analysis_result['reasoning']}",
                "response": final_state['messages'][-1].content
            })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/manual_trigger_assistance', methods=['POST'])
async def manual_trigger_assistance():
    """
    【新版】手动触发主动服务，跳过询问，直接进行分析和行动。
    """
    if not core_agent_app:
        return jsonify({"error": "Agent is not ready."}), 503
    
    try:
        # 1. 获取会话ID
        data = await request.get_json()
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({"error": "No session ID provided."}), 400

        log_message(f"--- User manually triggered DIRECT assistance for session: {session_id} ---")

        # 2. 立即获取当前的用户活动状态，以构建上下文
        current_activity = await asyncio.to_thread(get_real_time_user_activity)
        
        # 3. 手动构建一个用于分析的上下文(context)
        context_to_analyze = {
            "reason": "用户手动点击了“我需要帮助”按钮，请求直接分析当前情况。",
            "activity_summary": {
                "proactive_score": "N/A (Manual Trigger)",
                "avg_keyboard_hz": current_activity.get("keyboard_freq_hz", 0),
                "avg_mouse_hz": current_activity.get("mouse_freq_hz", 0),
                "changed_windows_count": len(current_activity.get("window_titles", [])),
                "final_cognitive_load": current_activity.get("cognitive_load", "unknown"),
                "final_confidence": current_activity.get("confidence", 0.0),
                "window_titles": current_activity.get("window_titles", [])
            },
            "activity_log": [{"timestamp": datetime.now().isoformat(), "activity": current_activity}]
        }

        # 4. 【核心】直接调用 Analyzer Agent (UserStateModeler) 进行分析
        analysis_result = await UserStateModeler.analyze_user_context_and_suggest(
            context=context_to_analyze,
            llm=llm,
            tools_config=tools_config
        )

        if not analysis_result or (analysis_result.get("recommended_tool") is None and not analysis_result.get("suggestion_text")):
            # 如果分析失败或没有任何建议
            error_msg = analysis_result.get("suggestion_text", "分析失败，无法提供建议。")
            return jsonify({"analysis_message": "系统分析完成。", "final_response": error_msg})

        # 5. 构建 Handoff 消息并送入主工作流 (与 /request_assistance 路由后半部分完全相同)
        handoff_prompt = f"""
用户刚刚手动请求了帮助。我的主动式助理分析了用户当前的情况，并给出了以下建议：

- **它认为我正在做**: {analysis_result['user_intent']}
- **它建议的操作**: {analysis_result['suggestion_text']}
- **它建议使用的工具**: `{analysis_result.get('recommended_tool', '无')}`
- **理由**: {analysis_result['reasoning']}

请根据这个建议继续操作。
"""
        state = await get_session_state(session_id)
        state['messages'].append(HumanMessage(content=handoff_prompt))
        
        final_state = await core_agent_app.ainvoke(state, {"recursion_limit": 10})
        await save_session_state(session_id, final_state)

        # 6. 返回分析消息和最终执行结果
        return jsonify({
            "analysis_message": f"系统分析完成: {analysis_result['suggestion_text']}",
            "final_response": final_state['messages'][-1].content
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/end_chat', methods=['POST'])
async def end_chat():
    """
    当用户结束会话时，触发记忆总结Agent。
    这是一个后台任务，不需要立即返回结果给用户。
    """
    if not memory_agent_app:
        return jsonify({"status": "error", "message": "Memory Agent not ready."}), 503
    
    try:
        data = await request.get_json()
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({"status": "error", "message": "No session ID provided."}), 400
        
        log_message(f"--- Received request to end and memorize session: {session_id} ---")
        
        # 获取当前会话的完整状态
        current_state = await get_session_state(session_id)
        
        # 【关键】使用 app.add_background_task 在后台异步执行记忆总结
        # 这样可以立刻返回响应给前端，而无需等待记忆过程完成
        async def run_memorization_in_background():
            log_message(f"Starting background memorization for session {session_id}...")
            # 注意：这里的 state 是一个副本，以防主会话状态被意外修改
            memorization_state = {"messages": current_state["messages"][:], "log": []}
            final_memory_state = await memory_agent_app.ainvoke(memorization_state, {"recursion_limit": 5})
            log_message(f"Background memorization finished for session {session_id}.")
            log_message(f"Final memory state log: {final_memory_state.get('log')}")

        app.add_background_task(run_memorization_in_background)

        # 立刻返回成功响应
        return jsonify({"status": "success", "message": "Memory summarization process started in the background."})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"An error occurred: {e}"}), 500
    
# --- 程序退出时停止后台监听器 ---
import atexit
atexit.register(monitor.stop)
