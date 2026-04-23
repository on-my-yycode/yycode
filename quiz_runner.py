#!/usr/bin/env python3
import random

# 数学题目和答案
problems = [
    {
        "question": "小明家今年收获了苹果和梨共800千克，苹果和梨的质量比是3:5。请问苹果和梨各收获了多少千克？",
        "answer": "苹果300千克，梨500千克",
        "short_answer": "300,500"
    },
    {
        "question": "在一幅地图上，比例尺是1:5000000。如果两地的实际距离是200千米，那么在地图上应该画多少厘米？",
        "answer": "4厘米",
        "short_answer": "4"
    },
    {
        "question": "一辆汽车2小时行驶了120千米。照这样的速度，从甲地到乙地共行驶了5小时，甲乙两地相距多少千米？",
        "answer": "300千米",
        "short_answer": "300"
    },
    {
        "question": "一批货物，如果每车装5吨，需要16辆车。如果每车装8吨，需要多少辆车？",
        "answer": "10辆车",
        "short_answer": "10"
    },
    {
        "question": "某班男生和女生的人数比是4:5，如果男生增加8人，女生增加10人，那么新的男生和女生人数比是多少？",
        "answer": "4:5（比例不变）",
        "short_answer": "4:5"
    },
    {
        "question": "用3台水泵抽水，8小时可以抽干一池水。照这样计算，5台同样的水泵抽水，多少小时可以抽干这池水？",
        "answer": "4.8小时",
        "short_answer": "4.8"
    },
    {
        "question": "甲、乙、丙三人合伙做生意，投资金额的比是2:3:5。年终共获利12万元，按照投资比例分配，三人各分得多少万元？",
        "answer": "甲2.4万，乙3.6万，丙6万",
        "short_answer": "2.4,3.6,6"
    },
    {
        "question": "长方形的长和宽的比是5:3，周长是64厘米。求这个长方形的面积是多少平方厘米？",
        "answer": "240平方厘米",
        "short_answer": "240"
    },
    {
        "question": "修一条路，已修的和未修的长度比是1:5。如果再修300米，已修的和未修的长度比就是1:2。这条路全长多少米？",
        "answer": "1800米",
        "short_answer": "1800"
    },
    {
        "question": "有含盐8%的盐水40千克，要配制成含盐20%的盐水，需要加盐多少千克？（提示：利用比例关系解决）",
        "answer": "6千克",
        "short_answer": "6"
    }
]

# 打乱题目
random.shuffle(problems)

print("=" * 60)
print("🎯 小学6年级比例数学题测试")
print("=" * 60)
print(f"共 {len(problems)} 道题，满分100分")
print()

# 显示题目
print("📝 题目列表（已打乱）：")
print("-" * 60)
for i, problem in enumerate(problems, 1):
    print(f"\n第 {i} 题：")
    print(problem["question"])

print("\n" + "=" * 60)
print("📋 答案区域（自己在纸上作答后，对照下面的答案）")
print("=" * 60)

# 显示答案
print("\n✅ 参考答案：")
print("-" * 60)
for i, problem in enumerate(problems, 1):
    print(f"第 {i} 题答案：{problem['answer']}")

print("\n" + "=" * 60)
print("📊 评分说明：")
print("  每道题10分，总共100分")
print("  自己对照答案，计算得分！")
print("=" * 60)
