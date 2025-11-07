#!/bin/bash
# 启动 CogAgent Web 服务器

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "==========================================="
echo "  CogAgent Web Server"
echo "==========================================="
echo ""

# 检查端口是否已被占用
if lsof -Pi :5001 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  端口 5001 已被占用"
    echo "请先运行 ./stop_server.sh 停止现有服务器"
    exit 1
fi

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 虚拟环境不存在，请先创建："
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements-macos.txt"
    exit 1
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source .venv/bin/activate

# 启动服务器
echo "启动服务器在 http://127.0.0.1:5001"
echo "按 Ctrl+C 停止服务器"
echo ""

hypercorn web_app:app --bind 0.0.0.0:5001
