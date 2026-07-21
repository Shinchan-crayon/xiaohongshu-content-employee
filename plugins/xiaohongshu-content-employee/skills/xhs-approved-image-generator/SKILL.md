---
name: xhs-approved-image-generator
description: Produce Executor 的 Python 执行规范；校验 approval.json 后并发执行全部图片请求，并把完整请求历史写入 generation.json。
---

# Xiaohongshu Direct Image Generator

本 Skill 定义 Produce Executor 的 Python 执行规范。该阶段不创建 Worker、不
加载模型上下文、不接受 `worker_session_id`，`model_calls` 必须为 `0`。程序只
读取 `visual.json` 和 `approval.json`、已保存的生图渠道配置，以及
`visual.json` 声明的可选真实产品参考图；只输出 `generation.json` 和生成图片。

## Input Contract

```yaml
run_dir: path
output_root: path
max_workers: integer | null
visual:
  schema_version: 1
  run_id: string
  style_anchor: object
  pages: [object]
approval:
  schema_version: 1
  run_id: string
  status: approved
  prompt_hash: sha256
  approved_at: string
  approved_by: string
```

`batch_file` 由 `visual.json` 直接转换：

```yaml
schema_version: 1
items:
  - id: page-*
    page: integer
    prompt: string
    reference_image_paths: [path]
```

## Output Contract

```yaml
schema_version: 1
run_id: string
status: complete | partial | failed | uncertain
items:
  - request_id: req-*
    page_id: page-*
    provider: string
    model: string
    request_status: request_started | response_received | download_pending | complete | failed | uncertain
    started_at: string
    response_received_at: string | null
    download_started_at: string | null
    completed_at: string | null
    attempt: integer
    token_count: integer | null
    cost_amount: number | null
    cost_currency: string | null
    error: string | null
    path: path | null
```

## Approval Gate

开始任何付费请求前，必须验证 `approval.json.status` 为 `approved`，并确认批准
哈希与当前 Prompt 包的 `prompt_hash` 完全一致。缺少有效批准、批准哈希不匹配
当前 Prompt 包，或 Prompt、页面、参考图映射已经变化时，禁止启动 Produce
Executor。

## Execute

```bash
python3 ../../scripts/生图工具/batch_generate.py \
  --batch-file "<TEMP_BATCH_JSON>" \
  --output-root "<USER_OUTPUT_DIRECTORY>" \
  --run-dir "<RUN_DIR>"
```

1. 使用 `config.json` 保存的默认图片渠道和模型。
2. 所有页面必须并发提交，`max_workers: 0` 表示全部并发；每页只发起一次初始请求。
3. 把每页 `reference_image_paths` 原样传给渠道；数组非空时仅支持参考图的渠道可
   执行，identity-only 页保持空数组。
4. Prompt 原样发送，不在 Produce Executor 中修改已批准内容。
5. 不运行本地预检、质检、安全审计或返回图片的像素尺寸检查；Prompt 中的 `3:4`
   比例由生图模型直接执行。
6. 每个图片请求使用独立 `request_id`，按
   `request_started -> response_received -> download_pending -> complete`
   记录时间和状态；异常状态为 `failed` 或 `uncertain`。
7. 付费请求结果不确定时记录为 `uncertain`，禁止自动重新请求，必须先到渠道
   后台对账。
8. 人工确认需要重新发起时，创建新的 `request_id` 和递增的 `attempt`，保留原请求记录；
   不自动重试，也不自动切换模型或渠道。
9. 已收到图片 URL 但下载失败时记录为 `download_pending`；恢复时只下载已有
   URL，不再次发送付费请求。
10. `generation.json` 只写入外部 `run_dir`，不得写入插件或 HTML 交付目录，
   不把运行状态展示给用户。正常内容任务不从中额外生成运行日志、阶段耗时、
   Token 或费用报告。
11. 只有全部计划图片均为 `complete`，且图片文件实际存在时，才能交给
    `$xhs-html-delivery`。任何图片缺失、失败或状态不确定都禁止交付；不核对返回
    图片的具体像素尺寸。

首次设置必须在内容流程开始前完成。Produce Executor 不得等到 Prompt 已展示或已
批准后才要求用户选择模型或配置 API Key。如果 `config.json` 不存在、没有
`default_provider`，或所选渠道缺少 API Key，停止执行并提示用户返回首次设置完成
模型选择和 API Key 配置：

```bash
python3 ../../scripts/生图工具/configure_provider.py --list
```

把完整渠道、模型、默认尺寸和参考图支持情况展示给用户。用户选择后立即配置并
保存该渠道的 API Key；完成后直接复用，不再重复询问。切换模型只在用户明确要求
时执行。

## Runtime

- 批量生图：`../../scripts/生图工具/batch_generate.py`
- 单图请求：`../../scripts/生图工具/generate_image.py`
- 首次选择：`../../scripts/生图工具/configure_provider.py`
- 渠道清单：`../../assets/image_providers.json`
- 配置示例：`../../config.example.json`
- Python 依赖：`../../requirements.txt`

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
