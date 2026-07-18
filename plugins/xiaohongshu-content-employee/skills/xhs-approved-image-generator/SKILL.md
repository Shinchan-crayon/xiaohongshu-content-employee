---
name: xhs-approved-image-generator
description: 把整批最终 Prompt 直接并发发送给用户首次选择的生图模型，返回图片路径后立即交给 HTML 生成。
---

# Xiaohongshu Direct Image Generator

## 输入

```yaml
batch_file: path
output_root: path
max_workers: integer | null
```

`batch_file`：

```yaml
schema_version: 1
items:
  - id: string
    page: integer
    prompt: string
    reference_image_path: string | null
```

## 输出

```yaml
status: complete | partial | failed
provider: string
generated_images:
  - id: string
    page: integer
    path: string
    provider: string
    model: string
    width: integer
    height: integer
failed_pages: [object]
```

## 执行

```bash
python3 ../../scripts/生图工具/batch_generate.py \
  --batch-file "<TEMP_BATCH_JSON>" \
  --output-root "<USER_OUTPUT_DIRECTORY>"
```

执行规则：

1. 使用 `config.json` 中保存的默认图片渠道和模型。
2. 所有页面一次并发提交，`max_workers: 0` 表示全部并发。
3. Prompt 原样发送，不展示、不复审、不计算审批哈希。
4. 不运行本地预检、质检、安全审计或图片检查。
5. 不打开图片，不截图，不评价，不删除，不重生成。
6. 每页只请求一次，不自动重试。
7. 不写 `generation-state.json`、checkpoint、请求响应快照或调试日志。
8. 运行时只保留最终图片；临时下载目录自动删除。
9. 图片返回后立即把结果交给 `$xhs-html-delivery`。

首次使用时，如果 `config.json` 不存在或没有 `default_provider`，先运行：

```bash
python3 ../../scripts/生图工具/configure_provider.py --list
```

把完整的渠道和模型列表展示给用户。用户选择并完成配置后保存默认项，以后
直接复用，不再重复询问。切换模型只在用户明确要求时执行。

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
