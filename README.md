# PACE: 基于用户认知状态的主动服务对话框架

## 1. 项目简介
PACE 是一个支持主动服务的智能对话系统。它通过独立的用户认知状态建模模块，实时感知用户负荷，并在需要时主动发起服务建议。框架将认知建模与对话逻辑解耦，支持多模态输入（文本、文件、图片），可扩展多种工具服务。

## 2. 平台支持

PACE 现已支持跨平台运行：

- ✅ **macOS** (包括 Apple Silicon M1/M2/M3)
- ✅ **Windows** (Windows 10/11)
- ⚠️ **Linux** (实验性支持)

## 3. 快速开始

### 环境检查

运行环境检查脚本：

```bash
python check_system.py
```

此脚本会检查：
- Python 版本
- 操作系统类型
- 必要依赖
- GPU/MPS 支持
- 摄像头状态
- 模型文件

### macOS 安装

详细安装指南请查看 [INSTALL_MACOS.md](INSTALL_MACOS.md)

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements-macos.txt

# 3. 配置环境变量
cp .env.example .env  # 编辑并填写 API 密钥

# 主动服务决策模式配置（可选）
# 在 .env 文件中添加：
# PROACTIVE_DECISION_MODE=llm  # 使用LLM智能决策（推荐，默认）
# PROACTIVE_DECISION_MODE=heuristic  # 使用启发式规则
# 详见: docs/PROACTIVE_DECISION_MODE.md

# 4. 授予必要权限（辅助功能、屏幕录制、摄像头）
# 在系统偏好设置 > 安全性与隐私 > 隐私 中设置

# 5. 启动服务
hypercorn web_app:app --bind 0.0.0.0:5001
```

### Windows 安装

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
copy .env.example .env  # 编辑并填写 API 密钥

# 4. 启动服务
hypercorn web_app:app --bind 0.0.0.0:5001
```

## 4. GPU 加速支持

系统会自动检测并使用最佳计算设备：

- **NVIDIA GPU**: 自动使用 CUDA 加速
- **Apple Silicon**: 自动使用 MPS (Metal Performance Shaders) 加速
- **CPU**: 自动降级到 CPU 模式

## 5. 代码结构

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
|   |-- activity_monitor.py   # 键鼠输入监控（跨平台）
|   |-- realtime_detection/   # 实时视觉认知负荷检测
|-- proactive_service.py      # 主动服务监控与触发
|-- state.py                  # AgentState定义
|-- web_app.py                # 主应用（异步Quart服务器）
|-- check_system.py           # 系统环境检查脚本
|-- requirements.txt          # Windows依赖
|-- requirements-macos.txt    # macOS依赖
|-- INSTALL_MACOS.md          # macOS详细安装指南
```

## 6. 主要模块说明

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
  实时监控用户键鼠输入频率（支持 Windows 和 macOS）。

- **realtime_detection/**
  实时视觉认知负荷检测模块，支持 CUDA/MPS/CPU。

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

## 7. 典型流程

1. 用户输入文本或上传文件/图片，前端通过 `/chat` 路由与后端交互。
2. 后端根据输入和当前状态，决策回复或工具调用。
3. 后台主动服务模块监控用户状态，必要时通过 `/request_assistance` 发起服务建议。
4. 会话结束时，自动调用记忆Agent进行知识总结。

## 8. 环境变量配置

在项目根目录创建 `.env` 文件：

```bash
# OpenAI / Azure OpenAI
OPENAI_API_KEY=your_openai_key_here
# 或使用 Azure
# AZURE_OPENAI_API_KEY=your_key
# AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
# OPENAI_API_VERSION=2024-02-15-preview
# AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment

# Google AI (如果使用 Gemini)
GOOGLE_API_KEY=your_google_api_key_here

# GitHub (用于某些 MCP 工具)
GITHUB_TOKEN=your_github_token_here
```

## 9. 平台特定注意事项

### macOS

- 需要授予 **辅助功能** 权限（键鼠监控）
- 需要授予 **屏幕录制** 权限（窗口信息获取）
- 需要授予 **摄像头** 权限（认知负荷检测）
- Apple Silicon 自动使用 MPS 加速

详细说明请查看 [INSTALL_MACOS.md](INSTALL_MACOS.md)

### Windows

- 某些杀毒软件可能阻止键鼠监控
- 需要安装 pywin32 用于窗口管理
- NVIDIA GPU 自动使用 CUDA 加速

## 10. 常见问题

### Q: 认知负荷检测模型在哪里？

**A**: 模型文件需要单独训练或获取。将训练好的模型文件 `best_resnet3d.pth` 放到 `utils/realtime_detection/` 目录下。如果没有模型文件，系统仍可运行，但不会有认知负荷检测功能。

### Q: macOS 上提示权限错误？

**A**: 请按照 INSTALL_MACOS.md 中的说明授予必要权限，并重启终端。

### Q: GPU 加速不工作？

**A**: 运行 `python check_system.py` 检查 GPU 支持状态。系统会自动降级到 CPU 模式。

### Q: MCP 工具如何配置？

**A**: 编辑 `config/mcpServers.json` 文件添加或修改工具服务器配置。

## 11. 其他说明

- MCP工具服务支持多种类型（如PPT、图表、文件系统等），可在 `config/mcpServers.json` 配置。
- 用户习惯和偏好可在 `config/user_habits.json` 定义，支持个性化服务。
- 所有会话状态自动保存于 `sessions/` 目录，支持断点续聊。

## 12. 技术架构

- **后端**: Python 3.9+ + Quart (异步)
- **AI框架**: LangChain + LangGraph
- **LLM**: 支持 OpenAI/Azure OpenAI/Google Gemini
- **工具协议**: MCP (Model Context Protocol)
- **深度学习**: PyTorch (支持 CUDA/MPS/CPU)
- **视觉**: OpenCV + ResNet3D
- **前端**: HTML5 + JavaScript + Chart.js

---

如需详细开发文档或二次开发接口说明，请参考各模块源码注释。

**注意**: 本系统会收集键鼠活动、窗口信息和视频数据用于认知负荷分析。所有数据均在本地处理，不会上传到云端。
