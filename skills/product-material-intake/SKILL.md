---
name: product-material-intake
description: 整理产品事实、图片、卖点、目标用户、缺失材料和禁止改写项，建立可追溯素材记录。
---

# Product Material Intake

## Input Contract

```yaml
content_goal: string
product_or_service: string
product_images: [path]
existing_copy: string | null
references: [path_or_url]
target_audience: string | null
```

## Output Contract

```yaml
facts:
  - claim: string
    label: FACT | INFERENCE | ASSUMPTION | UNKNOWN
    source: string
immutable_claims: [string]
selling_points: [object]
target_audience: object
image_inventory: [object]
missing_materials: [string]
conflicts: [object]
ready_for_strategy: boolean
```

## Method

1. 逐项读取客户文字和图片，不把营销形容词自动当作事实。
2. 用 `[FACT]`、`[INFERENCE]`、`[ASSUMPTION]`、`[UNKNOWN]` 标记每条信息。
3. 将型号、尺寸、颜色、包装、功能、价格、认证、效果和适用人群列为高风险事实字段。
4. 建立 `immutable_claims`：未经客户确认，后续 Skill 不得修改。
5. 为每张图片记录主体、角度、清晰度、可裁切区域、禁改项和建议用途。
6. 缺少核心事实或产品图与文字冲突时，`ready_for_strategy: false`。

## Image Rule

真实产品图优先。不得用 AI 改变产品外观、颜色、结构、包装、配件数量或功能表现。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/虚构内容禁止规则.md`
- `../../references/小红书内容规范/产品种草规范.md`
