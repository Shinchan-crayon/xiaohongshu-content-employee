---
name: xhs-visual-planner
description: 在 compose 阶段把文案规划为最小必要图片集合和简洁、开放的参考图生图 Prompt，不调用生图接口。
---

# Xiaohongshu Visual Planner

## Input Contract

```yaml
content_package: object
visual_mode: existing_only | ai_assist
official_reference_images: [object]
selected_provider: string | null
selected_model: string | null
selected_size: string | null
selected_quality: string | null
```

## Output Contract

```yaml
visual_plan:
  mode: existing_only | ai_assist
  pages:
    - page_type: cover | product_focus | scene_story | information_card
      task: string
      exact_text: [string]
      font_mood: string
      prompt: string | null
      reference_image_path: string | null
      reference_image_sha256: string | null
prompt_packages: [object]
open_questions: [string]
```

## Method

1. 每页只承担一个独立信息任务。
2. 页数不设固定目标，只生成内容和视觉意图明显不同的最小必要集合。
3. `existing_only` 直接使用已有图片，不生成 Prompt，不加工图片。
4. `ai_assist` 只为首图选择清晰的官网产品图作为参考图，记录本地路径和 SHA-256；第二页起 `reference_image_path` 和 `reference_image_sha256` 两个字段必须为空。
5. Prompt 保持简短，只写：
   - 本页要表达什么；
   - 产品或品牌名称；
   - 首图以官网产品参考图为产品外观依据，后续页不写参考图要求；
   - 必须出现的中文文字；
   - 字体的大致气质；
   - 3:4 小红书成品图。
6. 不逐项指定构图、镜头、灯光、材质、配色、道具或背景细节，让图片模型自由完成视觉创意。
7. 首图不要求模型复刻参考图背景，只参考产品包装、Logo、图标、颜色和识别特征。
8. 不规划代码加字、抠图、产品叠加、背景替换、裁切或合成。
9. 允许图片模型产生轻微伪品牌文字或局部乱码，不把这类小问题设为交付门禁。
10. 所有页面按 3:4 竖版成品图规划，一次输出全部 Prompt。
11. 同一批次内每条 Prompt 的最终文本必须不同，不得输出 100% 完全相同的 Prompt。

## Prompt Pattern

首图：

```text
参考图片主体为{品牌和产品}，参考官网图片，其余构图和场景自由发挥。为小红书制作一张 3:4 成品图，表达{页面任务}，自然呈现中文“{精确文字}”，字体气质为{字体气质}。
```

第二页起：

```text
为小红书制作一张 3:4 成品图，表达{页面任务}，自然呈现中文“{精确文字}”，字体气质为{字体气质}。其余视觉创意、构图和场景自由发挥。
```

可根据页面删减句子，不继续堆叠摄影参数和负面词列表。

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/轮播叙事.md`
