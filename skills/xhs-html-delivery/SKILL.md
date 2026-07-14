---
name: xhs-html-delivery
description: 校验结构化内容包并生成支持复制、图片预览下载和审核展示的独立 HTML 交付页。
---

# Xiaohongshu HTML Delivery

## Input Contract

UTF-8 JSON 文件，字段遵循 `../../assets/delivery-schema.json`。

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
- 所有本地图片存在。
- 文案、轮播页和图片 ID 对应。
- 交付 JSON 不含敏感密钥。

## Failure Rules

- 缺少必需字段：停止，不生成半成品。
- 缺少本地图片：停止并列出路径。
- 图片服务不可用：使用已有真实产品图与 HTML/CSS 信息卡，不阻塞交付。

## Required References

- `../../references/审核规则/最终审核清单.md`
- `../../templates/HTML交付模板/delivery.html`
