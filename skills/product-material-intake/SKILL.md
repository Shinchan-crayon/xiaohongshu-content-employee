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
material_source_mode: user_links | internal_search
material_links: [url]
references: [path_or_url]
target_audience: string | null
learning_context: object | null
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
material_source_mode: user_links | internal_search
material_source_ready: boolean
ready_for_strategy: boolean
applied_learning_ids: [string]
explicit_preference_signals: [object]
```

## Method

1. 逐项读取客户文字和图片，不把营销形容词自动当作事实。
2. 用 `[FACT]`、`[INFERENCE]`、`[ASSUMPTION]`、`[UNKNOWN]` 标记每条信息。
3. 将型号、尺寸、颜色、包装、功能、价格、认证、效果和适用人群列为高风险事实字段。
4. 建立 `immutable_claims`：未经客户确认，后续 Skill 不得修改。
5. 为每张图片记录主体、角度、清晰度、可裁切区域、禁改项和建议用途。
6. 用户选择 `user_links` 时，检查 `material_links` 至少包含一个可读取的文章或产品素材链接；否则 `material_source_ready: false`。
7. 用户选择 `internal_search` 时，允许 `material_links` 为空，并把产品名称、内容目标、目标用户和已有事实整理为搜索上下文。
8. 缺少核心事实、产品图与文字冲突或素材来源路径未就绪时，`ready_for_strategy: false`。
9. 只使用 `learning_context` 中的用户偏好和已批准知识，并把实际采用的记录写入 `applied_learning_ids`。
10. 用户在素材整理时明确表达长期偏好，或修改内容并说明原因时，写入 `explicit_preference_signals` 交给主控保存；不要根据沉默或推测生成偏好。

## Material Source Rule

- `user_links`：只登记和读取用户提供的链接，不在本阶段扩展搜索。
- `internal_search`：本阶段不虚构搜索结果，只准备交给 `$xhs-research-strategy` 的搜索上下文。
- 输入未包含有效 `material_source_mode` 时返回未就绪，由主控请求用户二选一。

## Image Rule

真实产品图优先。不得用 AI 改变产品外观、颜色、结构、包装、配件数量或功能表现。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/虚构内容禁止规则.md`
- `../../references/小红书内容规范/产品种草规范.md`
- `../../references/小红书内容规范/个性化学习规则.md`
