# macOS 安装指南

本指南将帮助你在 macOS 系统上安装和运行 PACE 系统。

## 系统要求

- macOS 10.15+ (推荐 macOS 12+)
- Python 3.9+
- 摄像头（用于认知负荷检测）
- 至少 4GB 可用内存

## 安装步骤

### 1. 克隆项目

```bash
cd /path/to/your/projects
git clone <your-repo-url>
cd CogAgent
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
# 使用 macOS 专用的依赖文件
pip install -r requirements-macos.txt
```

### 4. 配置环境变量

创建 `.env` 文件并填写必要的 API 密钥：

```bash
cp .env.example .env  # 如果有示例文件
# 或直接创建
touch .env
```

在 `.env` 文件中添加：

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

# MCP 服务器目录（可选）
MCP_SERVERS_DIR=/path/to/mcp/servers
```

### 5. 授予权限

macOS 需要授予以下权限才能正常运行：

#### a) 辅助功能权限（用于键鼠监控）

1. 打开 **系统偏好设置** > **安全性与隐私** > **隐私**
2. 选择 **辅助功能**
3. 点击左下角锁形图标解锁
4. 添加你的终端应用（Terminal.app 或 iTerm.app）
5. 确保勾选框被选中

#### b) 屏幕录制权限（用于窗口信息获取）

1. 在 **系统偏好设置** > **安全性与隐私** > **隐私**
2. 选择 **屏幕录制**
3. 添加你的终端应用
4. 确保勾选框被选中

#### c) 摄像头权限

1. 在 **系统偏好设置** > **安全性与隐私** > **隐私**
2. 选择 **摄像头**
3. 添加你的终端应用
4. 确保勾选框被选中

### 6. 准备认知负荷检测模型

如果你有训练好的模型文件：

```bash
# 将模型文件放到指定位置
cp /path/to/your/best_resnet3d.pth utils/realtime_detection/
```

如果没有模型文件，系统仍可运行，但不会有认知负荷检测功能。

### 7. 运行应用

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 启动服务器
hypercorn web_app:app --bind 0.0.0.0:5001
```

### 8. 访问应用

在浏览器中打开：
```
http://127.0.0.1:5001
```

## 平台特性说明

### GPU 加速

- **Apple Silicon (M1/M2/M3)**: 自动使用 MPS (Metal Performance Shaders) 加速
- **Intel Mac**: 使用 CPU（因为不支持 CUDA）
- 系统会在启动时自动检测并选择最佳设备

### 键鼠监控

macOS 使用 `pynput` 库进行键鼠监控。确保授予了辅助功能权限。

### 窗口管理

macOS 使用 Quartz 框架获取窗口信息。确保授予了屏幕录制权限。

## 常见问题

### Q1: 提示 "Operation not permitted"

**A**: 需要授予辅助功能和屏幕录制权限。参见步骤5。授予权限后需要重启终端。

### Q2: 摄像头无法打开

**A**:
1. 确保摄像头没有被其他应用占用
2. 检查是否授予了摄像头权限
3. 尝试重启终端

### Q3: PyObjC 安装失败

**A**:
```bash
# 尝试单独安装
pip install --upgrade pip setuptools wheel
pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa
```

### Q4: torch 在 Apple Silicon 上运行缓慢

**A**: 确保安装了支持 MPS 的 PyTorch 版本：
```bash
pip install --upgrade torch torchvision
```

### Q5: 键盘/鼠标监控在某些应用中不工作

**A**: 某些应用（如系统偏好设置）由于安全限制可能无法被监控，这是正常现象。

## 卸载

```bash
# 停用虚拟环境
deactivate

# 删除虚拟环境
rm -rf .venv

# 撤销权限：在系统偏好设置中手动移除终端应用的权限
```

## 开发建议

### 使用 VS Code

如果使用 VS Code，建议安装以下扩展：
- Python
- Pylance
- Jupyter (如果需要调试模型)

### 调试模式

```bash
# 设置环境变量启用调试
export QUART_APP=web_app:app
export QUART_ENV=development
quart run --host 0.0.0.0 --port 5001
```

## 性能优化

### 对于 Apple Silicon Mac

系统会自动使用 MPS 加速。如果遇到兼容性问题，可以强制使用 CPU：

```python
# 在 realtime_detection.py 中修改
self.device = torch.device('cpu')  # 强制使用 CPU
```

### 降低内存占用

如果内存不足，可以调整以下参数：

```python
# 在初始化 RealtimeCognitiveLoadDetector 时
detector = RealtimeCognitiveLoadDetector(
    model_path=model_path,
    segment_seconds=15,  # 减少片段长度（默认30）
    predict_interval=60  # 增加预测间隔（默认30）
)
```

## 技术支持

如有问题，请提交 Issue 或查看项目文档。

---

**注意**: 本系统会收集键鼠活动、窗口信息和视频数据用于认知负荷分析。所有数据均在本地处理，不会上传到云端。请确保遵守相关隐私法规。
