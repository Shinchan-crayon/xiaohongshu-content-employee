---
name: xhs-copy-storyboard
description: 基于已确认事实和选题生成标题、正文、标签、封面文案、轮播脚本与图片使用方案。
---

# Xiaohongshu Copy Storyboard

## Input Contract

```yaml
material_record: object
strategy_brief: object
selected_topic: object
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
```

## Method

1. 先建立 `claim_map`，每个事实性表达绑定来源和证据标签。
2. 根据 `account_voice`、目标用户和选题写出 `voice_fingerprint`。没有账号语气时只确定编辑态度、句式偏好和 CTA 方式，不虚构个人经历。
3. 从“参数直入、误区纠正、使用决策、编辑判断”中选择最适合本次内容的 `structure_choice`。结构由素材决定，不得连续使用同一种正文骨架。
4. 写正文时打破平均分配：不要求每段都同时包含事实、解释、风险和建议；允许某段只给判断，下一段再补证据。
5. 产品安全、健康和使用步骤必须保留，但不要把全文写成从参数到注意事项依次讲解的说明书。
6. 生成利益型、问题型、场景型、对比型、结果型标题候选；只选择与正文一致的方向。
7. CTA 可以是问题、建议或直接结束。不得固定使用“三选一问题”收尾。
8. 封面只承诺正文能兑现的信息。
9. 轮播每页只承担一个信息任务，并记录对应图片 ID。
10. 图片方案优先使用客户真实产品图；信息图只表达结构，不改变产品事实。

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书内容规范/标签规则.md`
- `../../references/小红书内容规范/账号语气配置.md`
