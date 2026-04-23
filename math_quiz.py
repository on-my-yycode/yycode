#!/usr/bin/env python3
import random
import sys

# 数学题目和答案
math_problems = [
    {
        "question": "小明家今年收获了苹果和梨共800千克，苹果和梨的质量比是3:5。请问苹果和梨各收获了多少千克？",
        "answer": "苹果300千克，梨500千克",
        "keywords": ["300", "500"]
    },
    {
        "question": "在一幅地图上，比例尺是1:5000000。如果两地的实际距离是200千米，那么在地图上应该画多少厘米？",
        "answer": "4厘米",
        "keywords": ["4"]
    },
    {
        "question": "一辆汽车2小时行驶了120千米。照这样的速度，从甲地到乙地共行驶了5小时，甲乙两地相距多少千米？",
        "answer": "300千米",
        "keywords": ["300"]
    },
    {
        "question": "一批货物，如果每车装5吨，需要16辆车。如果每车装8吨，需要多少辆车？",
        "answer": "10辆车",
        "keywords": ["10"]
    },
    {
        "question": "某班男生和女生的人数比是4:5，如果男生增加8人，女生增加10人，那么新的男生和女生人数比是多少？",
        "answer": "4:5（比例不变）",
        "keywords": ["4:5"]
    },
    {
        "question": "用3台水泵抽水，8小时可以抽干一池水。照这样计算，5台同样的水泵抽水，多少小时可以抽干这池水？",
        "answer": "4.8小时",
        "keywords": ["4.8"]
    },
    {
        "question": "甲、乙、丙三人合伙做生意，投资金额的比是2:3:5。年终共获利12万元，按照投资比例分配，三人各分得多少万元？",
        "answer": "甲2.4万，乙3.6万，丙6万",
        "keywords": ["2.4", "3.6", "6"]
    },
    {
        "question": "长方形的长和宽的比是5:3，周长是64厘米。求这个长方形的面积是多少平方厘米？",
        "answer": "240平方厘米",
        "keywords": ["240"]
    },
    {
        "question": "修一条路，已修的和未修的长度比是1:5。如果再修300米，已修的和未修的长度比就是1:2。这条路全长多少米？",
        "answer": "1800米",
        "keywords": ["1800"]
    },
    {
        "question": "有含盐8%的盐水40千克，要配制成含盐20%的盐水，需要加盐多少千克？（提示：利用比例关系解决）",
        "answer": "6千克",
        "keywords": ["6"]
    }
]

def main():
    print("=" * 60)
    print("           📐 小学6年级比例数学题测验 📐")
    print("=" * 60)
    print(f"\n共有 {len(math_problems)} 道题目，满分100分")
    print("请认真作答，按回车键提交答案\n")
    
    # 打乱题目顺序
    shuffled_problems = math_problems.copy()
    random.shuffle(shuffled_problems)
    
    score = 0
    total = len(shuffled_problems)
    
    for i, problem in enumerate(shuffled_problems, 1):
        print("-" * 60)
        print(f"题目 {i}/{total}")
        print()
        print(problem["question"])
        print()
        
        user_answer = input("你的答案：").strip()
        
        # 检查答案是否包含关键词
        correct = False
        for keyword in problem["keywords"]:
            if keyword in user_answer:
                correct = True
                break
        
        if correct:
            print("✅ 回答正确！")
            score += 1
        else:
            print(f"❌ 回答错误。正确答案是：{problem['answer']}")
        
        print()
    
    # 计算最终分数
    final_score = int((score / total) * 100)
    
    print("=" * 60)
    print("                      📊 测验结果 📊")
    print("=" * 60)
    print(f"\n你答对了 {score}/{total} 题")
    print(f"最终得分：{final_score} 分")
    
    # 评价
    if final_score == 100:
        print("🎉 太棒了！满分！你是数学小天才！")
    elif final_score >= 80:
        print("👏 优秀！继续保持！")
    elif final_score >= 60:
        print("👍 及格了，再接再厉！")
    else:
        print("💪 还需要多练习哦！")
    print()

if __name__ == "__main__":
    main()
