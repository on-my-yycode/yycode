# Confirmed Plan: Tower Defense Game Improvements

## User Goal
修改塔防游戏：美术风格化防御塔和怪物、放大画布和UI、将EMP塔改为范围伤害塔并改名。

## Confirmed Requirements
1. **美术风格化防御塔**：每种塔有独特的Canvas绘图（火炮、冰晶、狙击镜等）
2. **美术风格化怪物**：添加眼睛、轮廓、类型差异化特征
3. **画布/UI放大**：Canvas 800×500 → 1000×600，UI栏 800px → 1000px
4. **EMP改范围伤害塔**：移除slow减速 → 添加splash范围伤害，改名"震荡塔"

## Scope
- 文件：`examples/html5_canvas_tower_defense/index.html`

## Non-Goals
- 不改核心逻辑（路径、波次、金币）
- 不改中文语言
- 不新增塔/怪物类型

## Implementation Plan
1. 扩大画布和所有UI尺寸
2. 重写防御塔render绘制（美术化）
3. 重写怪物render绘制（美术化）
4. 修改EMP塔配置和UI标签

## Verification
- 浏览器打开确认画布尺寸
- 确认每种塔和怪物有独特外观
- 确认震荡塔有范围伤害无减速
