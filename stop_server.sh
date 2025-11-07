#!/bin/bash
# 停止 CogAgent Web 服务器

echo "正在查找 hypercorn 进程..."

# 查找进程
PID=$(lsof -ti :5001)

if [ -z "$PID" ]; then
    echo "未找到运行在端口 5001 的进程"
    exit 0
fi

echo "找到进程 PID: $PID"
echo "正在终止进程..."

# 先尝试优雅关闭
kill $PID

# 等待 5 秒
sleep 5

# 检查进程是否还在运行
if ps -p $PID > /dev/null 2>&1; then
    echo "进程未响应，强制终止..."
    kill -9 $PID
fi

echo "✓ 服务器已停止"
