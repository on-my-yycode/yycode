# Examples 项目

这是一个示例 Python 项目，包含两个实用模块：问候功能和斐波那契数列工具。

## 项目结构

```
examples/
├── hello.py          # 问候功能模块
├── utils.py          # 斐波那契数列工具模块
├── test_hello.py     # hello.py 的测试文件
├── test_utils.py     # utils.py 的测试文件
├── requirements.txt  # 项目依赖
├── CODE_REVIEW.md    # 代码审查报告
└── README.md         # 项目说明文档
```

## 功能说明

### hello.py - 问候功能

提供简单的问候生成功能：

- `say_hello(name: str) -> str`: 为单个名字生成问候语
- `greet_everyone(names: List[str]) -> List[str]`: 为多个名字生成问候语列表

**使用示例**:

```python
from hello import say_hello, greet_everyone

# 单个问候
print(say_hello("Alice"))  # 输出: "Hello, Alice!"

# 多个问候
names = ["Alice", "Bob", "Charlie"]
print(greet_everyone(names))
# 输出: ["Hello, Alice!", "Hello, Bob!", "Hello, Charlie!"]
```

### utils.py - 斐波那契数列工具

提供三种斐波那契数列的使用方式：

- `fibonacci(n: int) -> int`: 计算斐波那契数列的第 n 项
- `fibonacci_generator(n: int) -> Generator[int, None, None]`: 生成斐波那契数列的生成器
- `fibonacci_list(n: int) -> List[int]`: 生成斐波那契数列列表

**使用示例**:

```python
from utils import fibonacci, fibonacci_generator, fibonacci_list

# 计算第10项
print(fibonacci(10))  # 输出: 55

# 使用生成器
for num in fibonacci_generator(5):
    print(num)  # 输出: 0, 1, 1, 2, 3, 5

# 获取列表
print(fibonacci_list(5))  # 输出: [0, 1, 1, 2, 3, 5]
```

## 安装和运行

### 环境要求

- Python 3.7+

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行测试

使用 pytest 运行所有测试：

```bash
pytest test_hello.py -v
```

使用 unittest 运行 utils 测试：

```bash
python test_utils.py
```

### 运行示例代码

```bash
python hello.py
```

## 代码审查

详细的代码审查报告请参考 [CODE_REVIEW.md](./CODE_REVIEW.md)。

## 许可证

本项目仅作为学习和示例使用。
