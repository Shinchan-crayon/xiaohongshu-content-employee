---
name: xhs-html-delivery
description: 图片返回后立即生成可编辑、可预览和可下载图片的独立 HTML，并直接交付给用户。
---

# Xiaohongshu HTML Delivery

## 输入

使用临时 UTF-8 JSON 作为生成器输入，字段遵循
`../../assets/delivery-schema.json`。临时 JSON 不属于交付物，HTML 生成后立即删除。

## 输出

```yaml
delivery_html: path
```

## 执行

```bash
python3 ../../scripts/HTML生成工具/generate_delivery.py \
  "<TEMP_INPUT_JSON>" \
  "<OUTPUT_HTML>"
```

规则：

1. 图片批次返回后立即运行一次 HTML 生成命令。
2. 使用全部已返回图片；部分页面失败时不等待、不重试、不补图。
3. 命令成功后立即把 HTML 文件发送给用户。
4. 删除临时输入 JSON，结束任务。
5. 不打开 HTML，不打开图片，不运行浏览器，不调用 Playwright，不截图。
6. 不做文案质检、安全审计、图片验收、Schema 复审或最终检查。
7. 不写状态文件、检查报告、调试日志或交付台账。

HTML 生成器为完成页面生成所做的字段读取和文件写入属于生成动作，不得再扩展为独立检查步骤。

## 失败

生成命令失败时只返回实际错误，不启动替代生成器、诊断链或复审流程。

## Required References

- `../../templates/HTML交付模板/delivery.html`
