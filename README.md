# PACE: 基于用户认知状态的主动服务对话框架

## 1. 项目简介
PACE 是一个支持主动服务的智能对话系统。它通过独立的用户认知状态建模模块，实时感知用户负荷，并在需要时主动发起服务建议。框架将认知建模与对话逻辑解耦，支持多模态输入（文本、文件、图片），可扩展多种工具服务。

## 2. 代码结构
```
/
|-- agents/
|   |-- planner.py            # Agent决策核心
|   |-- tool_manager.py       # 工具执行器
|   |-- user_state_modeler.py # 用户状态建模与分析
|   |-- memory_agent.py       # 记忆总结Agent
|-- config/
|   |-- mcpServers.json       # MCP工具服务器配置
|   |-- user_habits.json      # 用户习惯配置
|-- static/
|   |-- style.css
|   |-- chart.js
|-- templates/
|   |-- index.html            # 前端页面
|-- utils/
|   |-- helpers.py            # 辅助函数
|   |-- mcp_config_loader.py  # MCP配置加载器
|   |-- activity_monitor.py   # 键鼠输入监控
|-- core_agent.py             # Agent图构建入口
|-- proactive_service.py      # 主动服务监控与触发
|-- state.py                  # AgentState定义
|-- web_app.py                # 主应用（异步Flask/Quart服务器）
|-- requirements.txt          # Python依赖
|-- .env                      # 环境变量（API密钥等）
```

## 3. 安装与运行

1. 创建虚拟环境
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. 安装依赖
   ```bash
   python -m pip install -r requirements.txt
   ```

3. 配置环境变量  
   新建 `.env` 文件，填写所需 API 密钥（如 GOOGLE_API_KEY、GITHUB_TOKEN 等）。

4. 启动服务
   ```bash
   hypercorn web_app:app --bind 0.0.0.0:5001
   ```
   浏览器访问 [http://127.0.0.1:5001](http://127.0.0.1:5001)

## 4. 主要模块说明

### agents/

- **planner.py**  
  Agent的决策核心，负责根据会话状态、用户习惯和工具配置，生成下一步行动（回复或工具调用）。

- **tool_manager.py**  
  工具执行节点，异步调用 MCP 工具，将结果反馈给 Agent。

- **user_state_modeler.py**  
  用户状态建模器，分析用户活动快照，判断认知负荷，生成主动服务建议。

- **memory_agent.py**  
  记忆总结Agent，负责会话结束后的知识提炼与存储。

### config/

- **mcpServers.json**  
  定义 MCP 工具服务器的启动方式和参数。

- **user_habits.json**  
  用户长期习惯和偏好，作为 SystemMessage 注入对话上下文。

### utils/

- **helpers.py**  
  通用辅助函数，如截图、活动采集、习惯加载等。

- **mcp_config_loader.py**  
  加载 MCP 服务器配置。

- **activity_monitor.py**  
  实时监控用户键鼠输入频率。

### web_app.py

- 项目主入口，异步 HTTP 服务器（Quart）。
- 路由包括 `/chat`（对话）、`/listen`（事件流）、`/request_assistance`（主动服务）、`/end_chat`（记忆总结）。
- 管理会话状态的加载与保存，支持多模态输入（文本、图片、文件）。

### proactive_service.py

- 后台线程，周期性分析用户状态，主动触发服务建议并与主 Agent 协作。

### 前端

- **templates/index.html**  
  用户界面，包含聊天窗口、认知负荷与任务类型图表、文件/图片上传等功能。

- **static/**  
  前端样式与图表脚本。

## 5. 典型流程

1. 用户输入文本或上传文件/图片，前端通过 `/chat` 路由与后端交互。
2. 后端根据输入和当前状态，决策回复或工具调用。
3. 后台主动服务模块监控用户状态，必要时通过 `/request_assistance` 发起服务建议。
4. 会话结束时，自动调用记忆Agent进行知识总结。

## 6. 其他说明

- MCP工具服务支持多种类型（如PPT、图表、文件系统等），可在 `config/mcpServers.json` 配置。
- 用户习惯和偏好可在 `config/user_habits.json` 定义，支持个性化服务。
- 所有会话状态自动保存于 `sessions/` 目录，支持断点续聊。

---

如需详细开发文档或二次开发接口说明，请参考各模块源码注释。