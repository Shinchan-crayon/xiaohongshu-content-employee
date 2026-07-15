---
name: xhs-html-delivery
description: 校验结构化内容包并生成支持复制、图片预览下载和审核展示的独立 HTML 交付页。
---

# Xiaohongshu HTML Delivery

## Input Contract

UTF-8 JSON 文件，字段遵循 `../../assets/delivery-schema.json`。

同时接收视觉阶段摘要：

```yaml
visual_status:
  mode: existing_only | ai_assist
  stage: visuals
  substage: complete
visual_plan: object
generated_images: [object] | null
```

## Output Contract

```yaml
delivery_json: path
delivery_html: path
asset_check:
  status: PASS | FAIL
  missing: [path]
```

## Execution

```bash
python3 scripts/HTML生成工具/generate_delivery.py INPUT.json OUTPUT.html
```

生成前必须确认：

- 审核状态不是 `BLOCKED`。
- 主流程已达到 `visuals / complete`。
- `existing_only` 已确认图片规划，且规划中引用的真实图片全部可访问。
- `ai_assist` 已完成 `generated_images`；每张 AI 成品必须记录 `source_type`、`provider`、`model`，并且实际尺寸为 1080x1440。
- 所有本地图片存在。
- 文案、轮播页和图片 ID 对应。
- 交付 JSON 不含敏感密钥。

## Failure Rules

- 缺少必需字段：停止，不生成半成品。
- 缺少本地图片：停止并列出路径。
- `ai_assist` 尚未完成或生成结果未验证：停止并回到视觉阶段，不得把模型原图直接交付。
- 图片服务不可用：由主流程询问用户是否改选 `existing_only`；本 Skill 不自动切换模式。

## Required References

- `../../references/审核规则/最终审核清单.md`
- `../../templates/HTML交付模板/delivery.html`
