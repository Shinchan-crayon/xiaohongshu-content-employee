---
name: xhs-approved-image-generator
description: 只执行用户已明确确认的图片 Prompt，并把结果合成为 1080x1440 小红书成品图。
---

# Xiaohongshu Approved Image Generator

## Input Contract

```yaml
batch_file: path
output_root: path
max_workers: integer | null
```

`batch_file` 必须是一个 `schema_version: 1` 的 JSON 文件。每个 `items[]` 项目至少包含：

```yaml
id: string
page: integer
prompt: string
prompt_review: confirmed
provider: string
model: string
size: string
quality: string
approval_digest: string
render:
  generated_image_target: background_path
```

## Output Contract

```yaml
generated_images:
  - page: integer
    provider: string
    model: string
    source_path: path
    final_path: path
    width: 1080
    height: 1440
generation_status: complete | blocked | uncertain
generation_state_json: path
```

## Execution Rules

1. 开始任何付费请求前，先校验批次内全部项目。只有用户明确确认整批内容、每项 `prompt_review` 均为 `confirmed`，且 Prompt、渠道、模型、尺寸、质量和 `approval_digest` 全部匹配时，才允许启动整批生成。
2. 默认并发数为 3，可设置为 1-8。并发只用于彼此独立的轮播页，不改变页码和最终交付顺序。
3. 使用受控任务队列逐项提交。出现首个 `failed` 或 `uncertain` 后停止提交新任务，但等待已经在途的任务结束并保留其成功结果。
4. 每张付费生成请求只发送一次。网络错误、执行中断或结果不确定时不得自动重试，状态写为 `uncertain`。
5. 恢复执行时读取 `generation-state.json`，跳过已经成功的页面。`failed` 或 `uncertain` 页面必须先由用户核对渠道后台并明确处理，不能自动重新发送。
6. 真实产品图不得重绘。AI 只生成场景或背景，随后由图片合成工具叠加真实产品图和精确中文文字。
7. 最终输出必须由图片合成工具生成 1080x1440 PNG，不得把模型原图直接当成小红书成品。
8. 图片文件和生成状态必须写入用户任务输出目录，不得写入插件目录。

## Runtime Command

```bash
python3 ../../scripts/生图工具/batch_generate.py \
  --batch-file "<BATCH_JSON>" \
  --output-root "<USER_TASK_DIRECTORY>" \
  --execute \
  --max-workers 3
```

运行结果保存在用户任务目录的 `generation-state.json`、`artifacts/` 和 `final/` 中。

## Runtime

- 渠道清单：`../../assets/image_providers.json`
- 配置示例：`../../config.example.json`
- Python 依赖：`../../requirements.txt`
- Prompt 审核哈希：`../../scripts/生图工具/approval_hash.py`
- 渠道配置：`../../scripts/生图工具/configure_provider.py`
- 本地预检：`../../scripts/生图工具/provider_preflight.py`
- 已批准生图：`../../scripts/生图工具/generate_image.py`
- 批量并发生图：`../../scripts/生图工具/batch_generate.py`
- 竖版合成：`../../scripts/图片合成工具/render_carousel.py`

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/生图审核清单.md`
