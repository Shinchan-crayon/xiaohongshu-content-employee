---
name: xhs-html-delivery
description: Deliver Executor 的 Python 执行规范；只在全部计划图片完成后生成默认内嵌图片的小红书内容 HTML、独立运行日志和 delivery.json。
---

# Xiaohongshu HTML Delivery

本 Skill 定义 Deliver Executor 的 Python 执行规范。该阶段不创建 Worker、不
加载模型上下文、不接受 `worker_session_id`，`model_calls` 必须为 `0`。程序只
读取 `content.json`、`visual.json` 和 `generation.json`；只输出小红书内容
HTML、独立运行日志和内部 `delivery.json`。

## Input Contract

使用临时 UTF-8 JSON 作为生成器输入，字段遵循
`../../assets/delivery-schema.json`。临时 JSON 不属于交付物，HTML 生成后立即
删除。

`generation.json` 必须已存在于外部 `run_dir`。其中全部计划图片的
`request_status` 都必须为 `complete`，每个图片文件都必须实际存在。任何图片
缺失、`failed`、`uncertain` 或 `download_pending` 时都禁止启动 Deliver
Executor。

## Output

```yaml
schema_version: 1
run_id: string
html_path: path
runtime_log_path: path
generation_status: complete
completed_at: string
```

## Execute

```bash
python3 ../../scripts/HTML生成工具/generate_delivery.py \
  "<TEMP_INPUT_JSON>" \
  "<OUTPUT_HTML>" \
  --run-dir "<RUN_DIR>" \
  --embed-images
```

1. Produce Executor 完成且全部计划图片通过交付门禁后，运行一次 HTML 生成命令。
2. 使用 `content.json` 的文案追溯、`visual.json` 的页面与参考图映射，以及
   `generation.json` 的完整图片结果生成小红书内容 HTML。
3. `--embed-images` 为默认行为；命令中显式写出，确保 HTML 不依赖外部图片路径。
4. 使用已有运行数据生成与 HTML 同目录、同名的 `.run-log.md`，不得为了日志增加
   模型调用、素材搜索、重复读取或额外检查；未返回的 Token 或费用不估算。
5. 在外部 `run_dir` 写入 `delivery.json`。内容 HTML、运行日志和 `delivery.json`
   真实存在后才可完成 `producing -> delivered -> completed`。
6. `--run-log` 作为兼容参数保留；无论是否传入，均生成独立运行日志。
7. 命令成功后只把小红书内容 HTML 和独立运行日志作为用户交付物。
8. 删除临时输入 JSON，结束任务。
9. 不打开 HTML，不打开图片，不运行浏览器，不调用 Playwright，不截图。
10. 不做文案质检、安全审计、图片验收、Prompt 复审或最终检查。
11. 不把 `delivery.json`、原始状态、完整请求记录或其他内部运行信息展示给
    用户。

HTML 生成器为完成页面生成和状态迁移所做的字段读取及文件写入属于生成动作，
不得扩展为独立检查步骤。

## Failure

HTML、运行日志或 `delivery.json` 缺失时不得标记 `completed`。
生成命令失败时只返回实际错误，也不启动替代生成器、诊断链或复审流程。

## Required References

- `../../templates/HTML交付模板/delivery.html`
