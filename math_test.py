#!/usr/bin/env python3
import random
import sys

class MathTest:
    def __init__(self):
        self.problems = [
            {
                'question': '小明家今年收获了苹果和梨共800千克，苹果和梨的质量比是3:5。请问苹果和梨各收获了多少千克？',
                'answer': '苹果300千克，梨500千克'
            },
            {
                'question': '在一幅地图上，比例尺是1:5000000。如果两地的实际距离是200千米，那么在地图上应该画多少厘米？',
                'answer': '4厘米'
            },
            {
                'question': '一辆汽车2小时行驶了120千米。照这样的速度，从甲地到乙地共行驶了5小时，甲乙两地相距多少千米？',
                'answer': '300千米'
            },
            {
                'question': '一批货物，如果每车装5吨，需要16辆车。如果每车装8吨，需要多少辆车？',
                'answer': '10辆车'
            },
            {
                'question': '某班男生和女生的人数比是4:5，如果男生增加8人，女生增加10人，那么新的男生和女生人数比是多少？',
                'answer': '4:5'
            },
            {
                'question': '用3台水泵抽水，8小时可以抽干一池水。照这样计算，5台同样的水泵抽水，多少小时可以抽干这池水？',
                'answer': '4.8小时'
            },
            {
                'question': '甲、乙、丙三人合伙做生意，投资金额的比是2:3:5。年终共获利12万元，按照投资比例分配，三人各分得多少万元？',
                'answer': '甲2.4万，乙3.6万，丙6万'
            },
            {
                'question': '长方形的长和宽的比是5:3，周长是64厘米。求这个长方形的面积是多少平方厘米？',
                'answer': '240平方厘米'
            },
            {
                'question': '修一条路，已修的和未修的长度比是1:5。如果再修300米，已修的和未修的长度比就是1:2。这条路全长多少米？',
                'answer': '1800米'
            },
            {
                'question': '有含盐8%的盐水40千克，要配制成含盐20%的盐水，需要加盐多少千克？',
                'answer': '6千克'
            }
        ]
        self.score = 0

    def run_test(self):
        print("=" * 60)
        print("           📚 六年级比例数学测试")
        print("=" * 60)
        print(f"共有 {len(self.problems)} 道题目，每题 10 分")
        print("让我们开始吧！")
        print("=" * 60)
        
        # 打乱题目
        random.shuffle(self.problems)
        
        for i, problem in enumerate(self.problems, 1):
            print(f"\n🎯 第 {i} 题：")
            print("-" * 60)
            print(problem['question'])
            print("-" * 60)
            
            user_answer = input("\n你的答案：").strip()
            
            # 简单答案检查
            print(f"\n✅ 正确答案：{problem['answer']}")
            
            is_correct = input("你的答案是否正确？(y/n)：").strip().lower()
            
            if is_correct == 'y':
                self.score += 10
                print("🎉 太棒了！+10分")
            else:
                print("💪 继续加油！")
        
        # 显示最终结果
        self.show_result()

    def show_result(self):
        print("\n" + "=" * 60)
        print("                    📊 测试结果")
        print("=" * 60)
        print(f"你的得分：{self.score} / 100")
        
        percentage = self.score
        if percentage >= 90:
            grade = "🌟 优秀！"
        elif percentage >= 80:
            grade = "👍 良好！"
        elif percentage >= 60:
            grade = "📝 及格，继续努力！"
        else:
            grade = "💪 需要更多练习！"
            
        print(f"评价：{grade}")
        
        if self.score == 100:
            print("\n🏆 完美！全部答对！")
        elif self.score >= 60:
            print(f"\n你答对了 {self.score//10} 道题！")
        else:
            print(f"\n别灰心，建议再复习一下比例相关知识。")
        
        print("=" * 60)

if __name__ == "__main__":
    test = MathTest()
    test.run_test()
