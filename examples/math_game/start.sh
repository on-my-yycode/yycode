#!/bin/bash
#
# 数学游戏启动脚本 (Unix/Linux/macOS)
#

cd "$(dirname "$0")"

echo "========================================"
echo "  小学数学竞赛游戏"
echo "========================================"
echo ""

# 检查 Python 是否可用
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "错误：未找到 Python 解释器"
    echo "请先安装 Python 3"
    exit 1
fi

echo "使用 Python: $($PYTHON_CMD --version)"
echo ""

# 检查是否有虚拟环境，如果没有则创建
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    $PYTHON_CMD -m venv venv
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 启动服务器
echo ""
echo "启动游戏服务器..."
$PYTHON_CMD server.py
