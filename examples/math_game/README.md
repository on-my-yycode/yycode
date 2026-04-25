# 小学数学竞赛游戏

一个交互式的数学练习游戏，包含100道比例相关题目。

## 问题解决

**问题**：直接用浏览器打开 `index.html` 时，由于浏览器的 CORS（跨域资源共享）策略，会无法加载 `math_problems.json` 文件。

**解决方案**：提供一个简单的 HTTP 服务器来托管这些文件。

## 快速开始

### 方法1：使用启动脚本（推荐）

#### Windows 用户
双击运行 `start.bat` 文件

#### macOS/Linux 用户
在终端运行：
```bash
chmod +x start.sh
./start.sh
```

### 方法2：直接运行 Python 服务器

```bash
cd examples/math_game
python3 server.py
```

### 方法3：使用 Python 内置服务器（不推荐）

虽然也可以使用，但我们的自定义服务器更好：

```bash
cd examples/math_game
python3 -m http.server 8080
```
然后在浏览器访问 `http://localhost:8080/index.html`

## 文件说明

- `index.html` - 游戏主页面
- `math_problems.json` - 100道数学题目数据
- `server.py` - 自定义 HTTP 服务器（添加了 CORS 支持）
- `generate_problems.py` - 题目生成脚本
- `start.sh` - Unix/Linux/macOS 启动脚本
- `start.bat` - Windows 启动脚本

## 游戏特性

- 10种不同类型的比例题目
- 自动计分系统
- 每道题都有详细的解题思路
- 进度条显示
- 随机排序题目

## 端口说明

默认使用端口 8080，如果端口被占用，可以：
1. 停止占用该端口的程序
2. 或者修改 `server.py` 中的 `PORT` 变量使用其他端口
