#!/usr/bin/env python3
"""
测试 utils.py 的测试用例
"""

import unittest
from utils import fibonacci, fibonacci_generator, fibonacci_list


class TestFibonacci(unittest.TestCase):
    """测试斐波那契数列相关函数的测试类"""

    def test_fibonacci_base_cases(self):
        """测试基本情况"""
        self.assertEqual(fibonacci(0), 0)
        self.assertEqual(fibonacci(1), 1)
        self.assertEqual(fibonacci(2), 1)

    def test_fibonacci_small_numbers(self):
        """测试小数字"""
        self.assertEqual(fibonacci(3), 2)
        self.assertEqual(fibonacci(5), 5)
        self.assertEqual(fibonacci(10), 55)

    def test_fibonacci_large_number(self):
        """测试较大数字"""
        self.assertEqual(fibonacci(20), 6765)

    def test_fibonacci_negative_input(self):
        """测试负数输入应该抛出异常"""
        with self.assertRaises(ValueError):
            fibonacci(-1)

    def test_fibonacci_generator(self):
        """测试斐波那契生成器"""
        gen = fibonacci_generator(5)
        self.assertEqual(list(gen), [0, 1, 1, 2, 3, 5])

    def test_fibonacci_list(self):
        """测试斐波那契列表"""
        self.assertEqual(fibonacci_list(0), [0])
        self.assertEqual(fibonacci_list(1), [0, 1])
        self.assertEqual(fibonacci_list(5), [0, 1, 1, 2, 3, 5])
        self.assertEqual(fibonacci_list(10), [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55])


if __name__ == "__main__":
    unittest.main()
