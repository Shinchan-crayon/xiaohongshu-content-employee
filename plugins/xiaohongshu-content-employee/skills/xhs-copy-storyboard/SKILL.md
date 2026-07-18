---
name: xhs-copy-storyboard
description: 在唯一一次 compose 调用中自动选择证据支持的选题，并生成标题、正文、标签、封面、轮播和视觉任务。
---

# Xiaohongshu Copy Storyboard

## Input Contract

```yaml
material_record: object
strategy_brief: object
selected_topic: object | null
topic_confirmation_requested: boolean | null
account_voice: object | null
carousel_page_limit: integer | null
```

## Output Contract

```yaml
topics: [object]
titles: [object]
post:
  hook: string
  body: [string]
  cta: string
structure_choice: string
voice_fingerprint:
  stance: string
  sentence_style: string
  preferred_expressions: [string]
  forbidden_expressions: [string]
  cta_style: question | suggestion | none
tags: [string]
cover:
  headline: string
  subheadline: string
carousel: [object]
images: [object]
claim_map: [object]
visual_brief:
  page_tasks: [object]
  real_image_inventory: [object]
complete_content_package: object
```

## Method

本 Skill 与 `$xhs-visual-planner` 在一次 compose 调用中共同应用：先形成事实约束和页面任务，再在同一份输出中完成文案与 Prompt，不进行第二轮串行转写。

1. 用户未明确要求选题确认时，从 `strategy_brief.topic_candidates` 自动选择证据最强且最贴合目标用户的方向。
2. 先建立 `claim_map`，每个事实性表达绑定来源和证据标签。
3. 根据 `account_voice`、目标用户和选题写出 `voice_fingerprint`。没有账号语气时只确定编辑态度、句式偏好和 CTA 方式，不虚构个人经历。
4. 从“参数直入、误区纠正、使用决策、编辑判断”中选择最适合本次内容的 `structure_choice`。结构由素材决定，不得连续使用同一种正文骨架。
5. 写正文时打破平均分配：不要求每段都同时包含事实、解释、风险和建议；允许某段只给判断，下一段再补证据。
6. 产品安全、健康和使用步骤必须保留，但不要把全文写成从参数到注意事项依次讲解的说明书。
7. 生成利益型、问题型、场景型、对比型、结果型标题候选；只选择与正文一致的方向。
8. CTA 可以是问题、建议或直接结束。不得固定使用“三选一问题”收尾。
9. 封面只承诺正文能兑现的信息。
10. 轮播每页只承担一个信息任务，并记录对应图片 ID；只保留明显不同的信息和视觉任务，不追求固定页数。
11. 图片方案优先使用客户真实产品图；信息图只表达结构，不改变产品事实。
12. 在同一次输出中提供 `visual_brief`，供 `$xhs-visual-planner` 规则生成 Prompt，不调用生图接口。
13. 将文案、封面、轮播和视觉任务合并为 `complete_content_package`，不得在此后分批追加语义内容。

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书内容规范/标签规则.md`
- `../../references/小红书内容规范/账号语气配置.md`
