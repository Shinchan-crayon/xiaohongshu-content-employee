---
name: xhs-visual-planner
description: 在唯一一次 compose 调用中把文案规划为最小必要图片集合，并直接输出发送给已选择生图模型的全部最终 Prompt。
---

# Xiaohongshu Visual Planner

## 输入

```yaml
content_package: object
official_reference_images: [object]
```

## 输出

```yaml
visual_plan:
  pages:
    - page_type: cover | product_focus | scene_story | information_card
      task: string
      exact_text: [string]
      font_mood: string
      prompt: string
      reference_image_path: string | null
prompt_packages: [object]
```

## 执行

本 Skill 与 `$xhs-copy-storyboard` 在同一次 compose 调用中共同应用。文案完成
时，全部生图 Prompt 也必须成为最终版本，随后直接进入所选模型并发生图。

1. 每页只承担一个独立信息任务。
2. 只生成内容和视觉意图明显不同的最小必要图片集合。
3. 首图需要产品外观依据时绑定清晰的官方产品参考图；其他页面不强制绑定。
4. 每条 Prompt 写清页面任务、品牌或产品、必须出现的中文文字、字体气质和
   `3:4` 小红书成品图。
5. 不用代码加字、抠图、叠图、背景替换、裁切或合成。
6. 同一批次每条 Prompt 必须表达不同的页面任务。
7. 全部 Prompt 一次输出，输出后不展示、不复审、不评分、不改写，直接交给
   `$xhs-approved-image-generator`。

## Prompt Pattern

首图：

```text
参考图片主体为{品牌和产品}，产品外观以参考图为依据。为小红书制作一张 3:4 成品图，表达{页面任务}，自然呈现中文“{精确文字}”，字体气质为{字体气质}。其余视觉创意、构图和场景自由发挥。
```

第二页起：

```text
为小红书制作一张 3:4 成品图，表达{页面任务}，自然呈现中文“{精确文字}”，字体气质为{字体气质}。其余视觉创意、构图和场景自由发挥。
```

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/轮播叙事.md`
