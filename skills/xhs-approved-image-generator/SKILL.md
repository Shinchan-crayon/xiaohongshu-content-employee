---
name: xhs-approved-image-generator
description: 只执行用户已明确确认的图片 Prompt，并把结果合成为 1080x1440 小红书成品图。
---

# Xiaohongshu Approved Image Generator

## Input Contract

```yaml
visual_plan: object
provider: string
model: string
size: string
quality: string
prompt_review: confirmed
approval_digest: string
output_root: path
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
```

## Execution Rules

1. 只有 `prompt_review` 已完成且用户明确确认当前 Prompt、渠道、模型、尺寸和质量后，才允许执行。
2. 使用 `approval_digest` 校验当前执行条件；任何字段改变都必须退回审核。
3. 真实产品图不得重绘。AI 只生成场景或背景，随后由图片合成工具叠加真实产品图和精确中文文字。
4. 每张付费生成请求只发送一次。网络错误或结果不确定时不得自动重试，状态写为 `uncertain`。
5. 最终输出必须由图片合成工具生成 1080x1440 PNG，不得把模型原图直接当成小红书成品。
6. 图片文件必须写入用户任务输出目录，不得写入插件目录。

## Runtime

- 渠道清单：`../../assets/image_providers.json`
- 配置示例：`../../config.example.json`
- Python 依赖：`../../requirements.txt`
- Prompt 审核哈希：`../../scripts/生图工具/approval_hash.py`
- 渠道配置：`../../scripts/生图工具/configure_provider.py`
- 本地预检：`../../scripts/生图工具/provider_preflight.py`
- 已批准生图：`../../scripts/生图工具/generate_image.py`
- 竖版合成：`../../scripts/图片合成工具/render_carousel.py`

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/生图审核清单.md`
