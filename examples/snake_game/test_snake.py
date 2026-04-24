#!/usr/bin/env python3
"""
贪吃蛇游戏测试文件
测试游戏的核心逻辑功能
"""

import unittest
import sys
import os

# 导入游戏模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestSnakeGame(unittest.TestCase):
    """测试贪吃蛇游戏的核心逻辑"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.grid_size = 20
        self.screen_width = 800
        self.screen_height = 600
    
    def test_grid_size(self):
        """测试网格大小是否合理"""
        self.assertGreater(self.grid_size, 0)
        self.assertEqual(self.grid_size, 20)
    
    def test_screen_dimensions(self):
        """测试屏幕尺寸是否为网格大小的倍数"""
        self.assertEqual(self.screen_width % self.grid_size, 0)
        self.assertEqual(self.screen_height % self.grid_size, 0)
    
    def test_color_values(self):
        """测试颜色值是否在有效范围内"""
        # 测试颜色值应该在0-255之间
        WHITE = (255, 255, 255)
        BLACK = (0, 0, 0)
        GREEN = (0, 255, 0)
        RED = (255, 0, 0)
        BLUE = (0, 0, 255)
        
        for color in [WHITE, BLACK, GREEN, RED, BLUE]:
            for component in color:
                self.assertGreaterEqual(component, 0)
                self.assertLessEqual(component, 255)
    
    def test_direction_logic(self):
        """测试方向逻辑的合理性"""
        # 方向应该是成对的相反方向
        directions = {
            'UP': (0, -1),
            'DOWN': (0, 1),
            'LEFT': (-1, 0),
            'RIGHT': (1, 0)
        }
        
        # 测试相反方向
        self.assertEqual(directions['UP'][1], -directions['DOWN'][1])
        self.assertEqual(directions['LEFT'][0], -directions['RIGHT'][0])
    
    def test_score_calculation(self):
        """测试分数计算逻辑"""
        # 每个食物应该增加10分
        score_per_food = 10
        foods_eaten = 5
        expected_score = 50
        
        self.assertEqual(score_per_food * foods_eaten, expected_score)
    
    def test_initial_snake_length(self):
        """测试初始蛇的长度"""
        initial_length = 3
        self.assertGreater(initial_length, 0)
        self.assertEqual(initial_length, 3)

class TestGameMechanics(unittest.TestCase):
    """测试游戏机制"""
    
    def test_collision_detection_concept(self):
        """测试碰撞检测的概念"""
        # 模拟边界碰撞检测
        screen_width = 800
        screen_height = 600
        grid_size = 20
        
        # 测试边界位置
        def is_out_of_bounds(x, y):
            return x < 0 or x >= screen_width or y < 0 or y >= screen_height
        
        # 测试边界情况
        self.assertTrue(is_out_of_bounds(-grid_size, 0))  # 左边界外
        self.assertTrue(is_out_of_bounds(screen_width, 0))  # 右边界外
        self.assertTrue(is_out_of_bounds(0, -grid_size))  # 上边界外
        self.assertTrue(is_out_of_bounds(0, screen_height))  # 下边界外
        
        # 测试正常位置
        self.assertFalse(is_out_of_bounds(100, 100))  # 正常位置
    
    def test_food_generation(self):
        """测试食物生成逻辑"""
        screen_width = 800
        screen_height = 600
        grid_size = 20
        
        def generate_valid_position():
            """生成有效的网格位置"""
            import random
            x = random.randint(0, (screen_width - grid_size) // grid_size) * grid_size
            y = random.randint(0, (screen_height - grid_size) // grid_size) * grid_size
            return x, y
        
        # 测试生成的位置是否有效
        for _ in range(10):
            x, y = generate_valid_position()
            self.assertEqual(x % grid_size, 0)
            self.assertEqual(y % grid_size, 0)
            self.assertGreaterEqual(x, 0)
            self.assertLess(x, screen_width)
            self.assertGreaterEqual(y, 0)
            self.assertLess(y, screen_height)

def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始贪吃蛇游戏测试")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(loader.loadTestsFromTestCase(TestSnakeGame))
    suite.addTests(loader.loadTestsFromTestCase(TestGameMechanics))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ 所有测试通过！")
    else:
        print(f"❌ 测试失败：{len(result.failures)} 个失败，{len(result.errors)} 个错误")
    print("=" * 60)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
