# Test Prompts for YoyoAgent

## 1. Basic Todo Test
```
帮我规划一个简单的任务列表，包括：
1. 创建一个项目
2. 添加一些功能
3. 测试功能
```

## 2. Multi-step Coding Task
```
我需要你帮我：
1. 先创建一个 README.md 文件
2. 然后创建一个 main.py 包含一个 hello world 程序
3. 运行这个程序看看输出

请在开始前用 todo 工具规划一下。
```

## 3. Todo Tracking Test
```
创建一个待办列表，然后每完成一步用 todo 更新状态：
1. 创建一个名为 test.md 的文件
2. 读取这个文件
3. 修改这个文件，添加一些内容
4. 再次读取确认修改成功
```

## 4. Reminder Test (验证3轮提醒功能)
```
先创建一个简单的待办列表，然后：
1. 列出当前目录
2. 读取一个文件
3. 再列出当前目录
4. 再读取另一个文件

注意观察是否会收到 todo 工具的提醒。
```

## 5. Complex Task
```
帮我：
1. 创建一个 Python 项目结构（src/ 目录）
2. 创建一个 utils.py，包含一个计算斐波那契数列的函数
3. 创建一个 main.py 调用这个函数
4. 运行看看效果
5. 创建一个 requirements.txt

请使用 todo 工具跟踪进度。
```

在todo/目录下创建一个 utils.py，包含一个计算斐波那契数列的函数 并编写完成它的测试用例.创建它的 requirements.txt 文件