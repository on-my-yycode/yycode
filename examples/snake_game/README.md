# 贪吃蛇游戏 (Snake Game)

一个使用 Python 和 Pygame 开发的经典贪吃蛇游戏。

## 功能特性

- 🎮 经典贪吃蛇游戏玩法
- 🐍 蛇身增长机制
- 🍎 随机生成食物
- ⚡ 计分系统
- 🎯 游戏结束判定
- 🔄 重新开始功能
- ⏸️ 暂停功能

## 安装要求

- Python 3.7+
- Pygame

## 安装步骤

1. 克隆或下载项目
2. 安装依赖：

```bash
pip install pygame
```

或者使用 requirements.txt：

```bash
pip install -r requirements.txt
```

## 运行游戏

```bash
python snake.py
```

## 游戏控制

- **↑ / W** - 向上移动
- **↓ / S** - 向下移动
- **← / A** - 向左移动
- **→ / D** - 向右移动
- **P** - 暂停/继续游戏
- **R** - 重新开始游戏（游戏结束后）
- **ESC** - 退出游戏

## 游戏规则

1. 使用方向键控制蛇的移动
2. 吃到红色食物可以得分并增加蛇的长度
3. 撞到墙壁或自己的身体游戏结束
4. 游戏结束后按 R 键重新开始

## 文件结构

```
snake_game/
├── snake.py          # 游戏主文件
├── test_snake.py     # 游戏测试文件
├── requirements.txt  # 项目依赖
└── README.md         # 项目说明文档
```

## 测试

运行测试：

```bash
python -m pytest test_snake.py -v
```

## 游戏截图

（运行游戏后可查看实际效果）

## 开发者说明

游戏主要类和函数：

- `Snake` 类：管理蛇的状态和行为
  - `__init__()`: 初始化蛇
  - `change_direction()`: 改变移动方向
  - `move()`: 移动蛇
  - `grow()`: 蛇增长
  - `check_collision()`: 检查碰撞
  - `get_head_position()`: 获取蛇头位置
  - `get_body()`: 获取蛇身
  - `reset()`: 重置蛇

- `Food` 类：管理食物
  - `__init__()`: 初始化食物
  - `generate()`: 生成新食物
  - `get_position()`: 获取食物位置

- `SnakeGame` 类：主游戏类
  - `__init__()`: 初始化游戏
  - `handle_events()`: 处理事件
  - `update()`: 更新游戏状态
  - `draw()`: 绘制游戏画面
  - `show_game_over()`: 显示游戏结束画面
  - `reset_game()`: 重置游戏
  - `run()`: 运行游戏

## 许可证

MIT License

作者: 张磊, zlhxd, yoyofx, zl.hxd@hotmail.com, vvvv
