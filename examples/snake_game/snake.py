import pygame
import random
import sys

# 颜色定义
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

# 游戏设置
CELL_SIZE = 20
GRID_WIDTH = 20
GRID_HEIGHT = 20
SCREEN_WIDTH = CELL_SIZE * GRID_WIDTH
SCREEN_HEIGHT = CELL_SIZE * GRID_HEIGHT
FPS = 10

class Direction:
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

class SnakeGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption('🐍 开心贪吃蛇')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 36)
        self.reset_game()

    def reset_game(self):
        """重置游戏状态"""
        self.snake = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = Direction.RIGHT
        self.next_direction = Direction.RIGHT
        self.food = self.generate_food()
        self.score = 0
        self.game_over = False

    def generate_food(self):
        """生成新的食物位置"""
        while True:
            food = (random.randint(0, GRID_WIDTH - 1), 
                   random.randint(0, GRID_HEIGHT - 1))
            if food not in self.snake:
                return food

    def handle_events(self):
        """处理用户输入事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_SPACE:
                        self.reset_game()
                else:
                    if event.key == pygame.K_UP and self.direction != Direction.DOWN:
                        self.next_direction = Direction.UP
                    elif event.key == pygame.K_DOWN and self.direction != Direction.UP:
                        self.next_direction = Direction.DOWN
                    elif event.key == pygame.K_LEFT and self.direction != Direction.RIGHT:
                        self.next_direction = Direction.LEFT
                    elif event.key == pygame.K_RIGHT and self.direction != Direction.LEFT:
                        self.next_direction = Direction.RIGHT
        
        return True

    def update(self):
        """更新游戏状态"""
        if self.game_over:
            return

        self.direction = self.next_direction
        head_x, head_y = self.snake[0]
        new_head = (head_x + self.direction[0], head_y + self.direction[1])

        # 检查墙壁碰撞
        if (new_head[0] < 0 or new_head[0] >= GRID_WIDTH or
            new_head[1] < 0 or new_head[1] >= GRID_HEIGHT):
            self.game_over = True
            return

        # 检查自身碰撞
        if new_head in self.snake:
            self.game_over = True
            return

        # 移动蛇
        self.snake.insert(0, new_head)

        # 检查是否吃到食物
        if new_head == self.food:
            self.score += 10
            self.food = self.generate_food()
        else:
            self.snake.pop()

    def draw(self):
        """绘制游戏画面"""
        self.screen.fill(BLACK)

        # 绘制蛇
        for segment in self.snake:
            rect = pygame.Rect(segment[0] * CELL_SIZE, segment[1] * CELL_SIZE,
                             CELL_SIZE - 1, CELL_SIZE - 1)
            pygame.draw.rect(self.screen, GREEN, rect)

        # 绘制食物
        food_rect = pygame.Rect(self.food[0] * CELL_SIZE, self.food[1] * CELL_SIZE,
                               CELL_SIZE - 1, CELL_SIZE - 1)
        pygame.draw.rect(self.screen, RED, food_rect)

        # 绘制分数
        score_text = self.font.render(f'分数: {self.score}', True, WHITE)
        self.screen.blit(score_text, (10, 10))

        # 绘制游戏结束提示
        if self.game_over:
            game_over_text = self.font.render('游戏结束! 按空格键重新开始', True, RED)
            text_rect = game_over_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            self.screen.blit(game_over_text, text_rect)

        pygame.display.flip()

    def run(self):
        """运行游戏主循环"""
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    game = SnakeGame()
    game.run()
