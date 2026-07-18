---
name: xhs-approved-image-generator
description: 在 produce 阶段一次并发生成全部已批准页面，仅对安全瞬时错误重试一次，直接交付模型原图。
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

Seedream 批次仅首图绑定官网参考图。首图参考图哈希属于批准摘要的一部分，第二页起两个参考图字段必须为空。

## Output Contract

```yaml
generated_images:
  - page: integer
    generation_status: complete | failed | uncertain
    attempts: integer
    source_path: path | null
    final_path: path | null
    error: string | null
generation_status: complete | blocked
generation_state_json: path
failed_pages: [object]
```

## Execution Rules

1. 付费请求前校验整批批准、渠道、模型、尺寸、质量、Prompt 和参考图哈希。
2. 同一批次的 Prompt 不能完全相同；发现重复时整批停止，不发送任何付费请求。
3. 仅首图允许绑定官网参考图；第二页起不得传参考图。
4. 默认一次并发提交全部待生成页面，没有 3 页或 8 页上限。`max_workers: 0` 表示全部并发。
5. 每页独立执行。安全瞬时错误最多重试一次；结果不确定时不得重试。
6. 成功页面不重试。明确失败、结果不确定和恢复时遗留的 `sending` 页面都不得自动重新发送；遗留 `sending` 必须转为 `uncertain`。
7. 最终失败或不确定时记录准确页码、尝试次数和最后错误，并反馈给用户。
8. 模型返回的 PNG、JPEG 或 WebP 原字节直接复制到 `final/`。
9. 禁止代码加字、裁切、抠图、产品叠加、背景替换和图片合成。
10. 不执行生成后图片相似度自检、删除或重生成。
11. 轻微伪品牌文字或局部乱码允许交付。
12. 默认关闭请求与响应 JSON 快照；仅显式调试时允许在用户任务目录生成已脱敏快照，插件成品目录不得保存快照。

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
