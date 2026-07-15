---
name: xhs-visual-planner
description: 把审核通过的小红书内容包规划为可确认的封面、轮播页面与图片任务，不调用生图接口。
---

# Xiaohongshu Visual Planner

## Input Contract

```yaml
content_package: object
review_result: object
visual_mode: existing_only | ai_assist
real_image_inventory: [object]
selected_provider: string | null
```

## Output Contract

```yaml
visual_plan:
  mode: existing_only | ai_assist
  pages:
    - page_type: cover | product_focus | scene_story | information_card
      task: string
      layout: product_focus | scene_story | information_card
      real_image_id: string | null
      exact_text: object
      prompt: string | null
prompt_packages: [object]
open_questions: [string]
```

## Method

1. 每页必须“一页一个任务”，并从 `cover`、`product_focus`、`scene_story`、`information_card` 中选择页面类型。
2. 先盘点真实产品图。真实产品图用于包装、颜色、材质、接口、标签和比例等外观事实，AI 不得重绘真实产品。
3. `existing_only` 只使用真实图片、纯色背景和确定性信息卡，不生成 Prompt。
4. `ai_assist` 只让 AI 生成场景、背景和辅助视觉；真实产品图由合成器叠加。
5. 所有页面按 3:4 竖版规划，并在四周保留安全区。
6. 品牌名、参数、数字和精确中文文字不得交给图片模型绘制，必须放入 `exact_text` 交由确定性排版。
7. Prompt 必须说明主体、场景、构图、光线、色彩、留白和禁止项，并为真实产品图预留位置。
8. 输出规划后停止，等待用户确认，不调用任何图片生成接口。

## Required References

- `../../references/小红书生图知识/视觉模式与边界.md`
- `../../references/小红书生图知识/封面设计.md`
- `../../references/小红书生图知识/轮播叙事.md`
- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/构图与安全区.md`
- `../../references/小红书生图知识/中文文字与信息卡.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/生图审核清单.md`
