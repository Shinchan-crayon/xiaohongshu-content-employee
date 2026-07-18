---
name: xhs-html-delivery
description: 在 deliver 阶段一次生成可复制、预览和下载图片的独立 HTML，命令成功后立即交付，不追加检查链。
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

生成脚本在同一次本地执行中校验：

- `content_digest` 格式有效。
- 所有图片存在。
- AI 图片记录 `source_type`、`provider`、`model`、`width` 和 `height`。
- AI 图片为原生 3:4 竖图，不强制 1080x1440。
- 轮播页码与图片 ID 对应。
- 交付 JSON 不含敏感配置。

不运行文案风险、质量、自然化、AI 特征或品牌乱码检测。

## Final Delivery Contract

严格按以下顺序执行：

1. 写入 `delivery.json`，运行一次生成脚本并生成 HTML。
2. 生成命令返回成功后，立即向用户发送绝对 HTML 路径，并将状态写为 `completed`。
3. 交付后立即结束，不再启动检查、安装、发布或环境诊断。

生成脚本内置输入与资源校验，这是生成动作本身，不是独立审查步骤。命令成功后不得追加文件存在性复查、路径复查、完整状态校验、二次 Schema 校验、额外敏感信息扫描、资源扫描、Git 检查或发布检查。

## Inspection Limits

- 不打开生成图片，不打开浏览器，不调用 Playwright，不截图，不执行视觉验收；用户明确要求页面显示测试时除外。
- 不复审 Prompt，不执行文案终审、内容安全审计或最终检查清单。
- 不安装任何依赖，不因可选校验器缺失而寻找替代工具或执行降级验证链。
- 不调用任何可选校验器；生成命令成功即交付。
- 不执行 commit、push、Marketplace 同步或插件安装，除非用户明确提出这些操作。

## Failure Rules

- 生成脚本返回失败：留在 `deliver / BLOCKED`，反馈脚本返回的实际错误。
- 生成脚本已经成功时，非阻断警告不得撤回交付、延迟通知或触发额外检查。
- 不在本阶段润色、改标题、改文案或加工图片。
- 图片服务不可用时不自动切换模式或渠道。

## Required References

- `../../templates/HTML交付模板/delivery.html`
