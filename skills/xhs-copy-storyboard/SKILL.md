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
2. 生成利益型、问题型、场景型、对比型、结果型标题候选；只选择与正文一致的方向。
3. 正文使用“小场景或问题 -> 产品相关事实 -> 使用边界 -> 行动建议”的自然推进。
4. 封面只承诺正文能兑现的信息。
5. 轮播每页只承担一个信息任务，并记录对应图片 ID。
6. 图片方案优先使用客户真实产品图；信息图只表达结构，不改变产品事实。

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书内容规范/标签规则.md`
- `../../references/小红书内容规范/账号语气配置.md`
