# CogAgent: 一个基于用户认知状态进行主动服务的Agent对话框架

## 1. 整体概述
本框架的设计核心在于认知状态建模与主动服务模块的“解耦”，对用户的认知状态建模的模块运行于后台，与agent对话框架完全分离，当识别到用户认知负荷高需要主动服务时，将发起对用户的询问，得到确认后分析当前任务环境，生成prompt触发agent的后续服务，该模块可以将任意一个被动响应式agent转化为一个能实时获取用户认知状态，并发起主动服务的proactive agent。

## 2. 代码结构
/
|-- agents/
|   |-- __init__.py
|   |-- planner.py            # 包含两个planner：核心对话和主动服务
|   |-- tool_manager.py       # 工具执行器 (异步)
|   |-- user_state_modeler.py # 专门用于主动服务的状态建模器
|-- static/
|   |-- style.css
|   |-- chart.js
|-- templates/
|   |-- index.html            # 前端页面
|-- utils/
|   |-- helpers.py            # 辅助函数 (截图等)
|   |-- mcp_config_loader.py  # MCP配置加载器
|-- config/
|   |-- mcpServers.json       # MCP服务器定义
|   |-- user_habits.json      # 用户习惯配置
|-- .env                      # 环境变量 (API密钥)
|-- core_agent.py             # 构建核心对话Agent图
|-- proactive_service.py      # 构建主动服务模块
|-- state.py                  # 定义AgentState
|-- web_app.py                # 主应用，Flask服务器
|-- requirements.txt          # Python依赖

## 3. 安装与运行
** 1. 创建虚拟环境 **
```bash
python -m venv .venv
.venv\Scripts\activate
```

** 2. 安装依赖库 **
```bash
pip install -r requirements.txt
```

** 3. 配置环境 **
创建.env文件，配置GOOGLE_API_KEY, BAIDU_MAP_API_KEY, GITHUB_TOKEN等需要的API
如果需要开启代理，在web_app.py中配置os.environ对应的代理

** 4. 通过ASGI服务器启动异步web应用 **
```bash
hypercorn web_app:app --bind 0.0.0.0:5001
```
打开浏览器访问http://127.0.0.1:5001

## 4. 模块详解

### 核心文件

*   **`web_app.py`**
    *   **职责**: 应用的**主入口和HTTP服务器**。
    *   **内容**:
        *   Flask 应用的实例化。
        *   定义所有 API 端点 (路由)，如 `/chat`, `/listen`, `/request_assistance`。
        *   管理**会话状态**的加载 (`get_session_state`) 和保存 (`save_session_state`)，实现了本地 JSON 持久化。
        *   在启动时调用 `initialize_system` 来构建 Agent 图，并启动后台服务线程。
    *   **注意**: 这是一个**异步 Flask 应用**，所有与 Agent 交互的路由都是 `async def`，并使用 `await` 调用 Agent。

*   **`proactive_service.py`**
    *   **职责**: **后台监控与主动服务触发器**。
    *   **内容**:
        *   包含一个在独立线程中无限循环的 `proactive_monitoring_loop` 函数。
        *   周期性地调用 `UserStateModeler` 来分析用户状态。
        *   当满足触发条件时，它**不直接调用 Agent**，而是将一个“询问”消息和上下文 ID 放入一个线程安全的**内存队列** (`queue.Queue`) 中。

### Agent 核心 (`agents/`)

*   **`planner.py` (`run_planner`)**
    *   **职责**: Agent 的**决策核心节点**。
    *   **内容**: 接收当前的会话状态，构建一个包含历史记录、可用工具和（可选的）用户习惯的 Prompt，然后调用 LLM。LLM 的输出决定了下一步是调用工具，还是直接生成回复。这是 Agent “思考”的地方。

*   **`tool_manager.py` (`run_tool_manager`)**
    *   **职责**: **工具执行节点**。
    *   **内容**: 接收来自 Planner 的工具调用指令，在 `executable_tools` 字典中找到对应的工具实例，并异步执行它 (`_arun`)。然后将执行结果（成功或失败）包装成 `ToolMessage` 返回到工作流中。

*   **`user_state_modeler.py` (`UserStateModeler` 类)**
    *   **职责**: **用户状态建模与分析**。
    *   **内容**:
        *   `log_current_state`: 记录由 `helpers.py` 提供的用户活动快照。
        *   `analyze_and_decide`: 根据一段时间内的历史快照，应用预设的规则来判断用户是否处于“高负荷”状态。
        *   `format_prompt_after_confirmation`: 在用户确认需要帮助后，负责生成最终的、包含截图和历史分析的多模态 Prompt。

### 辅助模块 (`utils/`)

*   **`helpers.py`**
    *   **职责**: 提供项目范围内的**通用辅助函数**。
    *   **内容**: 包含 `take_screenshot` (模拟或真实截图)、`get_real_time_user_activity` (模拟或真实的用户活动数据) 和 `load_user_habits` (从 JSON 文件加载用户偏好) 等。

### 前端与配置

*   **`templates/index.html`**
    *   **职责**: **用户界面**。
    *   **内容**: 包含了页面的所有 HTML 结构、CSS 样式和 JavaScript 逻辑。通过 `fetch` API 与后端的 `/chat` 和 `/request_assistance` 交互，并通过 `EventSource` API 监听 `/listen` 端点以接收实时数据（图表更新）和主动服务询问。

*   **`user_habit.json`**
    *   **职责**: **静态用户画像**。
    *   **内容**: 一个简单的 JSON 文件，用于定义用户的长期偏好。它在每个新会话开始时被读取一次，并作为 `SystemMessage` 注入到对话的初始上下文中。
