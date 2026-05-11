#!/usr/bin/env python3
"""
数学题目生成器
根据10种比例题型生成100道数学题
"""

import json
import random
from typing import List, Dict, Any


class MathProblemGenerator:
    def __init__(self):
        self.problems = []
        self.problem_id = 1

    def generate_all_problems(self, count_per_type: int = 10) -> List[Dict[str, Any]]:
        """生成所有类型的题目"""
        generators = [
            self.generate_type1_ratio_distribution,
            self.generate_type2_scale_problem,
            self.generate_type3_direct_proportion,
            self.generate_type4_inverse_proportion,
            self.generate_type5_ratio_change,
            self.generate_type6_compound_ratio,
            self.generate_type7_capital_distribution,
            self.generate_type8_ratio_area,
            self.generate_type9_road_repair,
            self.generate_type10_salt_mixture,
        ]

        for generator in generators:
            for _ in range(count_per_type):
                problem = generator()
                self.problems.append(problem)
                self.problem_id += 1

        random.shuffle(self.problems)
        return self.problems

    def generate_type1_ratio_distribution(self) -> Dict[str, Any]:
        """类型1：比例分配"""
        total = random.randint(200, 1000)
        ratio1 = random.randint(1, 5)
        ratio2 = random.randint(2, 8)
        item1 = random.choice(["苹果", "梨", "橘子", "香蕉", "桃子", "葡萄"])
        item2 = random.choice(["梨", "苹果", "橘子", "香蕉", "桃子", "葡萄"])
        while item2 == item1:
            item2 = random.choice(["梨", "苹果", "橘子", "香蕉", "桃子", "葡萄"])

        answer1 = total * ratio1 // (ratio1 + ratio2)
        answer2 = total * ratio2 // (ratio1 + ratio2)

        return {
            "id": self.problem_id,
            "type": 1,
            "type_name": "比例分配",
            "question": f"小明家今年收获了{item1}和{item2}共{total}千克，{item1}和{item2}的质量比是{ratio1}:{ratio2}。请问{item1}和{item2}各收获了多少千克？",
            "options": [
                f"{answer1}千克，{answer2}千克",
                f"{answer2}千克，{answer1}千克",
                f"{answer1+50}千克，{answer2-50}千克",
                f"{answer1-50}千克，{answer2+50}千克"
            ],
            "correct_index": 0,
            "explanation": f"总份数：{ratio1}+{ratio2}={ratio1+ratio2}\n每份：{total}÷{ratio1+ratio2}={total//(ratio1+ratio2)}千克\n{item1}：{total//(ratio1+ratio2)}×{ratio1}={answer1}千克\n{item2}：{total//(ratio1+ratio2)}×{ratio2}={answer2}千克"
        }

    def generate_type2_scale_problem(self) -> Dict[str, Any]:
        """类型2：比例尺问题"""
        scale_denominator = random.choice([500000, 1000000, 2000000, 5000000, 10000000])
        actual_distance = random.randint(50, 500)
        map_distance = actual_distance * 100000 // scale_denominator

        return {
            "id": self.problem_id,
            "type": 2,
            "type_name": "比例尺问题",
            "question": f"在一幅地图上，比例尺是1:{scale_denominator}。如果两地的实际距离是{actual_distance}千米，那么在地图上应该画多少厘米？",
            "options": [
                f"{map_distance}厘米",
                f"{map_distance*2}厘米",
                f"{map_distance//2}厘米",
                f"{map_distance*10}厘米"
            ],
            "correct_index": 0,
            "explanation": f"{actual_distance}千米 = {actual_distance}×100000厘米\n地图距离 = {actual_distance}×100000 ÷ {scale_denominator} = {map_distance}厘米"
        }

    def generate_type3_direct_proportion(self) -> Dict[str, Any]:
        """类型3：正比例应用题"""
        hours1 = random.randint(2, 5)
        distance1 = hours1 * random.randint(40, 80)
        hours2 = random.randint(3, 8)
        speed = distance1 // hours1
        distance2 = speed * hours2

        return {
            "id": self.problem_id,
            "type": 3,
            "type_name": "正比例应用题",
            "question": f"一辆汽车{hours1}小时行驶了{distance1}千米。照这样的速度，从甲地到乙地共行驶了{hours2}小时，甲乙两地相距多少千米？",
            "options": [
                f"{distance2}千米",
                f"{distance2+50}千米",
                f"{distance2-50}千米",
                f"{distance2*2}千米"
            ],
            "correct_index": 0,
            "explanation": f"速度：{distance1}÷{hours1}={speed}千米/小时\n距离：{speed}×{hours2}={distance2}千米"
        }

    def generate_type4_inverse_proportion(self) -> Dict[str, Any]:
        """类型4：反比例应用题"""
        load1 = random.randint(3, 6)
        trucks1 = random.randint(10, 20)
        load2 = random.randint(4, 10)
        trucks2 = (load1 * trucks1) // load2

        return {
            "id": self.problem_id,
            "type": 4,
            "type_name": "反比例应用题",
            "question": f"一批货物，如果每车装{load1}吨，需要{trucks1}辆车。如果每车装{load2}吨，需要多少辆车？",
            "options": [
                f"{trucks2}辆车",
                f"{trucks2+2}辆车",
                f"{trucks2-2}辆车",
                f"{trucks2*2}辆车"
            ],
            "correct_index": 0,
            "explanation": f"货物总量：{load1}×{trucks1}={load1*trucks1}吨\n需要车辆：{load1*trucks1}÷{load2}={trucks2}辆"
        }

    def generate_type5_ratio_change(self) -> Dict[str, Any]:
        """类型5：比例变化问题"""
        ratio1 = random.randint(2, 6)
        ratio2 = random.randint(3, 8)
        add_boys = random.randint(4, 12)
        add_girls = random.randint(5, 15)
        new_ratio1 = ratio1 * 2 + add_boys
        new_ratio2 = ratio2 * 2 + add_girls

        for i in range(min(new_ratio1, new_ratio2), 1, -1):
            if new_ratio1 % i == 0 and new_ratio2 % i == 0:
                new_ratio1 = new_ratio1 // i
                new_ratio2 = new_ratio2 // i
                break

        return {
            "id": self.problem_id,
            "type": 5,
            "type_name": "比例变化问题",
            "question": f"某班男生和女生的人数比是{ratio1}:{ratio2}，如果男生增加{add_boys}人，女生增加{add_girls}人，那么新的男生和女生人数比是多少？",
            "options": [
                f"{new_ratio1}:{new_ratio2}",
                f"{new_ratio2}:{new_ratio1}",
                f"{ratio1}:{ratio2}",
                f"{ratio1+1}:{ratio2+1}"
            ],
            "correct_index": 0,
            "explanation": f"假设原来男生有{ratio1*2}人，女生有{ratio2*2}人\n增加后男生：{ratio1*2}+{add_boys}={ratio1*2+add_boys}人\n增加后女生：{ratio2*2}+{add_girls}={ratio2*2+add_girls}人\n新比例：{ratio1*2+add_boys}:{ratio2*2+add_girls} = {new_ratio1}:{new_ratio2}"
        }

    def generate_type6_compound_ratio(self) -> Dict[str, Any]:
        """类型6：复合比例"""
        pumps1 = random.randint(2, 5)
        hours1 = random.randint(6, 12)
        pumps2 = random.randint(3, 8)
        hours2 = (pumps1 * hours1) / pumps2

        return {
            "id": self.problem_id,
            "type": 6,
            "type_name": "复合比例",
            "question": f"用{pumps1}台水泵抽水，{hours1}小时可以抽干一池水。照这样计算，{pumps2}台同样的水泵抽水，多少小时可以抽干这池水？",
            "options": [
                f"{hours2:.1f}小时",
                f"{hours2+1:.1f}小时",
                f"{hours2-1:.1f}小时",
                f"{hours2*2:.1f}小时"
            ],
            "correct_index": 0,
            "explanation": f"工作总量：{pumps1}×{hours1}={pumps1*hours1}台·小时\n需要时间：{pumps1*hours1}÷{pumps2}={hours2:.1f}小时"
        }

    def generate_type7_capital_distribution(self) -> Dict[str, Any]:
        """类型7：按比例分配资金"""
        ratio1 = random.randint(1, 4)
        ratio2 = random.randint(2, 5)
        ratio3 = random.randint(3, 7)
        total_profit = random.randint(10, 30)
        total_ratio = ratio1 + ratio2 + ratio3
        profit1 = total_profit * ratio1 / total_ratio
        profit2 = total_profit * ratio2 / total_ratio
        profit3 = total_profit * ratio3 / total_ratio

        return {
            "id": self.problem_id,
            "type": 7,
            "type_name": "按比例分配资金",
            "question": f"甲、乙、丙三人合伙做生意，投资金额的比是{ratio1}:{ratio2}:{ratio3}。年终共获利{total_profit}万元，按照投资比例分配，三人各分得多少万元？",
            "options": [
                f"甲{profit1:.1f}万，乙{profit2:.1f}万，丙{profit3:.1f}万",
                f"甲{profit2:.1f}万，乙{profit1:.1f}万，丙{profit3:.1f}万",
                f"甲{profit3:.1f}万，乙{profit2:.1f}万，丙{profit1:.1f}万",
                f"甲{profit1+1:.1f}万，乙{profit2+1:.1f}万，丙{profit3+1:.1f}万"
            ],
            "correct_index": 0,
            "explanation": f"总份数：{ratio1}+{ratio2}+{ratio3}={total_ratio}\n甲：{total_profit}×{ratio1}/{total_ratio}={profit1:.1f}万\n乙：{total_profit}×{ratio2}/{total_ratio}={profit2:.1f}万\n丙：{total_profit}×{ratio3}/{total_ratio}={profit3:.1f}万"
        }

    def generate_type8_ratio_area(self) -> Dict[str, Any]:
        """类型8：比例与面积"""
        ratio_length = random.randint(3, 7)
        ratio_width = random.randint(2, 5)
        perimeter = random.randint(40, 100) * 2
        half_perimeter = perimeter // 2
        length = half_perimeter * ratio_length // (ratio_length + ratio_width)
        width = half_perimeter * ratio_width // (ratio_length + ratio_width)
        area = length * width

        return {
            "id": self.problem_id,
            "type": 8,
            "type_name": "比例与面积",
            "question": f"长方形的长和宽的比是{ratio_length}:{ratio_width}，周长是{perimeter}厘米。求这个长方形的面积是多少平方厘米？",
            "options": [
                f"{area}平方厘米",
                f"{area+50}平方厘米",
                f"{area-50}平方厘米",
                f"{area*2}平方厘米"
            ],
            "correct_index": 0,
            "explanation": f"长+宽：{perimeter}÷2={half_perimeter}厘米\n长：{half_perimeter}×{ratio_length}/({ratio_length}+{ratio_width})={length}厘米\n宽：{half_perimeter}×{ratio_width}/({ratio_length}+{ratio_width})={width}厘米\n面积：{length}×{width}={area}平方厘米"
        }

    def generate_type9_road_repair(self) -> Dict[str, Any]:
        """类型9：比例应用题（修路）"""
        ratio1 = random.randint(1, 2)
        ratio2 = random.randint(3, 6)
        new_ratio1 = random.randint(1, 2)
        new_ratio2 = random.randint(2, 4)
        repair_length = random.randint(200, 500)

        denominator = (new_ratio1 * (ratio1 + ratio2)) - (ratio1 * (new_ratio1 + new_ratio2))
        total_length = repair_length * (ratio1 + ratio2) * (new_ratio1 + new_ratio2) // denominator

        return {
            "id": self.problem_id,
            "type": 9,
            "type_name": "比例应用题",
            "question": f"修一条路，已修的和未修的长度比是{ratio1}:{ratio2}。如果再修{repair_length}米，已修的和未修的长度比就是{new_ratio1}:{new_ratio2}。这条路全长多少米？",
            "options": [
                f"{total_length}米",
                f"{total_length+200}米",
                f"{total_length-200}米",
                f"{total_length*2}米"
            ],
            "correct_index": 0,
            "explanation": f"原来已修占全长的{ratio1}/({ratio1}+{ratio2})\n后来已修占全长的{new_ratio1}/({new_ratio1}+{new_ratio2})\n全长：{repair_length}÷({new_ratio1}/({new_ratio1}+{new_ratio2})-{ratio1}/({ratio1}+{ratio2}))={total_length}米"
        }

    def generate_type10_salt_mixture(self) -> Dict[str, Any]:
        """类型10：比例与混合物"""
        salt_percent1 = random.randint(5, 10)
        salt_percent2 = random.randint(15, 25)
        salt_water_weight = random.randint(30, 60)
        original_salt = salt_water_weight * salt_percent1 // 100
        water = salt_water_weight - original_salt
        new_salt = water * salt_percent2 // (100 - salt_percent2)
        add_salt = new_salt - original_salt

        return {
            "id": self.problem_id,
            "type": 10,
            "type_name": "比例与混合物",
            "question": f"有含盐{salt_percent1}%的盐水{salt_water_weight}千克，要配制成含盐{salt_percent2}%的盐水，需要加盐多少千克？",
            "options": [
                f"{add_salt}千克",
                f"{add_salt+2}千克",
                f"{add_salt-2}千克",
                f"{add_salt*2}千克"
            ],
            "correct_index": 0,
            "explanation": f"原有盐：{salt_water_weight}×{salt_percent1}%={original_salt}千克\n水：{salt_water_weight}-{original_salt}={water}千克\n加盐后水占{100-salt_percent2}%\n加盐后总质量：{water}÷{100-salt_percent2}%={water*100//(100-salt_percent2)}千克\n加盐：{water*100//(100-salt_percent2)}-{salt_water_weight}={add_salt}千克"
        }

    def save_to_json(self, filename: str):
        """保存题目到JSON文件"""
        data = {
            "title": "小学6年级比例数学题",
            "description": "100道比例相关数学题目",
            "total_count": len(self.problems),
            "problems": self.problems
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已生成{len(self.problems)}道题目，保存到{filename}")


def main():
    generator = MathProblemGenerator()
    generator.generate_all_problems(count_per_type=10)
    generator.save_to_json("examples/math_game/math_problems.json")


if __name__ == "__main__":
    main()
