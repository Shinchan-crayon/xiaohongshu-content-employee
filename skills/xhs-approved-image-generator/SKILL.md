---
name: xhs-approved-image-generator
description: 在 produce 阶段一次并发生成全部已批准页面，失败页最多重试三次，直接交付模型原图。
---

# Xiaohongshu Approved Image Generator

## Input Contract

```yaml
batch_file: path
output_root: path
max_workers: integer | null
```

每个 `items[]` 至少包含：

```yaml
id: string
page: integer
prompt: string
generation_batch_approval: confirmed
provider: string
model: string
size: string
quality: string
approval_digest: string
reference_image_path: string
reference_image_sha256: string
```

Seedream 产品生图必须绑定官网参考图。参考图哈希属于批准摘要的一部分。

## Output Contract

```yaml
generated_images:
  - page: integer
    generation_status: complete | omitted_similar | failed
    attempts: integer
    source_path: path | null
    final_path: path | null
    duplicate_of: string | null
    error: string | null
generation_status: complete | blocked
generation_state_json: path
failed_pages: [object]
```

## Execution Rules

1. 付费请求前校验整批批准、渠道、模型、尺寸、质量、Prompt 和参考图哈希。
2. 默认一次并发提交全部待生成页面，没有 3 页或 8 页上限。`max_workers: 0` 表示全部并发。
3. 每页独立执行，失败或结果不确定时只重试该页，最多三次。
4. 成功页面不重试。恢复时继续未满三次的失败页。
5. 三次仍失败时记录准确页码、尝试次数和最后错误，并反馈给用户。
6. 模型返回的 PNG、JPEG 或 WebP 原字节直接复制到 `final/`。
7. 禁止代码加字、裁切、抠图、产品叠加、背景替换和图片合成。
8. 生成后删除高度相似的冗余图片，标记为 `omitted_similar`。
9. 轻微伪品牌文字或局部乱码允许交付。

## Runtime Command

```bash
python3 ../../scripts/生图工具/batch_generate.py \
  --batch-file "<BATCH_JSON>" \
  --output-root "<USER_TASK_DIRECTORY>" \
  --execute
```

## Runtime

- 渠道清单：`../../assets/image_providers.json`
- 配置示例：`../../config.example.json`
- Python 依赖：`../../requirements.txt`
- Prompt 批准哈希：`../../scripts/生图工具/approval_hash.py`
- 渠道配置：`../../scripts/生图工具/configure_provider.py`
- 本地预检：`../../scripts/生图工具/provider_preflight.py`
- 单图生成：`../../scripts/生图工具/generate_image.py`
- 批量生成：`../../scripts/生图工具/batch_generate.py`

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
