@echo off
REM 数学游戏启动脚本 (Windows)

cd /d "%~dp0"

echo ========================================
echo   小学数学竞赛游戏
echo ========================================
echo.

REM 检查 Python 是否可用
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    python3 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python3
    ) else (
        echo 错误：未找到 Python 解释器
        echo 请先安装 Python 3
        pause
        exit /b 1
    )
)

echo 使用 Python:
%PYTHON_CMD% --version
echo.

REM 检查是否有虚拟环境，如果没有则创建
if not exist "venv" (
    echo 创建虚拟环境...
    %PYTHON_CMD% -m venv venv
)

REM 激活虚拟环境
echo 激活虚拟环境...
call venv\Scripts\activate.bat

REM 启动服务器
echo.
echo 启动游戏服务器...
%PYTHON_CMD% server.py

pause
