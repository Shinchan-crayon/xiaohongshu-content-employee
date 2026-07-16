---
name: xhs-html-delivery
description: 在 deliver 阶段执行资源和映射校验，生成可复制、预览和下载图片的独立 HTML。
---

# Xiaohongshu HTML Delivery

## Input Contract

UTF-8 JSON 文件，字段遵循 `../../assets/delivery-schema.json`：

```yaml
content_digest: string
image_runtime:
  mode: existing_only | ai_assist
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
python3 ../../scripts/HTML生成工具/generate_delivery.py INPUT.json OUTPUT.html
```

生成前只执行技术校验：

- `content_digest` 格式有效。
- 所有图片存在。
- AI 图片记录 `source_type`、`provider`、`model`、`width` 和 `height`。
- AI 图片为原生 3:4 竖图，不强制 1080x1440。
- 轮播页码与图片 ID 对应。
- `omitted_similar` 图片已经从交付图片和轮播列表移除。
- 交付 JSON 不含敏感配置。

不运行文案风险、质量、自然化、AI 特征或品牌乱码检测。

## Failure Rules

- 缺字段、缺文件、比例错误或映射错误：留在 `deliver / BLOCKED`。
- 不在本阶段润色、改标题、改文案或加工图片。
- 图片服务不可用时不自动切换模式或渠道。

## Required References

- `../../templates/HTML交付模板/delivery.html`
