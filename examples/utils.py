def fibonacci(n):
    """
    计算斐波那契数列的第 n 项
    :param n: 非负整数，表示要计算的项数
    :return: 斐波那契数列的第 n 项
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("n 必须是非负整数")
    
    if n == 0:
        return 0
    elif n == 1:
        return 1
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def fibonacci_generator(n):
    """
    生成斐波那契数列的前 n+1 项（从第0项开始）
    :param n: 非负整数，表示要生成到第 n 项
    :return: 生成器，产生斐波那契数列
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("n 必须是非负整数")
    
    a, b = 0, 1
    for _ in range(n + 1):
        yield a
        a, b = b, a + b


def fibonacci_list(n):
    """
    生成斐波那契数列的前 n+1 项（从第0项开始）
    :param n: 非负整数，表示要生成到第 n 项
    :return: 包含前 n+1 项斐波那契数的列表
    """
    return list(fibonacci_generator(n))
