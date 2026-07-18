---
name: xhs-content-employee
description: 作为唯一公开入口，把素材整理、选题、所选模型并发生图和 HTML 交付串成一条不中断的直出流程。
---

# Xiaohongshu Content Employee

## 唯一执行规则

选题确定后，只允许执行这一条链：

`选题已定 -> 一次生成文案和最终 Prompt -> Prompt 直接并发发送给已选择的生图模型 -> 图片返回 -> 立即生成 HTML -> 把 HTML 发给用户`

文案和全部最终 Prompt 必须在同一次 compose 调用中完成。选题确定后不得再向用户展示 Prompt、解释计划、创建交付目录说明或插入任何检查步骤。

## 公开入口

本 Skill 是插件唯一公开入口。内部按需应用：

- 素材整理：`$product-material-intake`
- 选题与必要事实：`$xhs-research-strategy`
- 文案和轮播：`$xhs-copy-storyboard`
- 最终 Prompt：`$xhs-visual-planner`
- 所选模型并发生图：`$xhs-approved-image-generator`
- HTML 直出：`$xhs-html-delivery`

默认由当前 Agent 顺序完成，不启动子 Agent。

## 首次生图设置

每个安装环境第一次使用时，先检查插件根目录 `config.json` 是否存在且包含
非空的 `default_provider`。

如果尚未设置，必须先运行：

```bash
python3 ../../scripts/生图工具/configure_provider.py --list
```

把命令列出的渠道、具体模型和默认尺寸完整展示给用户，让用户选择一次。当前
内置选项包括：

1. ThinkAI Image 2：`gpt-image-2`
2. ThinkAI Nano：`nano-banana-2`
3. 火山引擎 Seedream：`doubao-seedream-5-0-lite-260128`
4. OpenAI GPT Image：`gpt-image-2`
5. Google Nano Banana：`gemini-3.1-flash-image`
6. 其他渠道：用户自定义模型

用户选择并提供对应配置后，运行
`../../scripts/生图工具/configure_provider.py` 保存为默认渠道。以后直接复用
该默认项，不再重复询问。用户明确要求更换模型时，重新运行配置工具并覆盖
默认项。

首次模型选择发生在内容执行前，不属于选题确定后的中途确认。

## 输入

```yaml
content_goal: string
product_or_service: string
product_images: [path]
existing_copy: string | null
material_source_mode: user_links | internal_search | null
material_links: [url]
references: [path_or_url]
target_audience: string | null
account_voice: object | null
topic: string | null
```

有用户链接时读取用户材料；没有链接时按需搜索公开事实和可用素材。只在选题确定前补齐写作必需信息，不创建来源确认轮次。

## 直接执行

### 1. 选题确定前

1. 完成首次生图设置；已有默认项时直接复用。
2. 整理用户材料和不可改写事实。
3. 素材不足时使用可用搜索能力补齐必要事实。
4. 用户没有指定选题时，直接选择最适合目标用户且有材料支撑的选题。
5. 用户已经指定选题时，立即进入下一步。

### 2. 一次生成文案和最终 Prompt

在一次模型调用中同时完成：

- 候选标题、正文、标签、封面文案和轮播脚本；
- 每一页最终生图 Prompt；
- 首图需要时绑定产品参考图，其他页面不强制绑定。

Prompt 在这一刻就是最终版本，不展示、不复审、不评分、不改写。

### 3. 直接发所选模型并发生图

立即调用：

```bash
python3 ../../scripts/生图工具/batch_generate.py \
  --batch-file "<TEMP_BATCH_JSON>" \
  --output-root "<USER_OUTPUT_DIRECTORY>"
```

- 使用 `config.json` 中已保存的默认图片渠道和模型。
- Prompt 固定写明 `3:4` 小红书成品图，请求尺寸使用该渠道的默认竖版参数。
- 全部 Prompt 一次并发提交。
- 不运行渠道预检，不计算审批哈希，不等待付费确认。
- 不自动重试，不切换模型，不切换渠道。
- 不打开图片，不读取图片内容，不评价图片，不删除或重生成。
- 批次 JSON 只作为临时命令输入，命令结束后删除，不写生成状态文件。

### 4. 图片返回后立即生成 HTML

图片调用结束后，不论全部成功还是部分成功，都立即使用已经返回的图片调用 `$xhs-html-delivery`。只有一张图片都没有返回时，才停止并把所选渠道的实际错误直接告诉用户。

HTML 生成命令成功后，立即把 HTML 文件发送给用户并结束。

## 明确禁止

整个内容任务禁止：

- 质检、质量评分、质量门禁或最终检查清单；
- 安全审计、内容审计、品牌审计或风险扫描；
- 验图、打开图片、图片相似度检查、乱码检查或视觉评价；
- 浏览器预览、Playwright、截图或页面复查；
- Prompt 展示、Prompt 复审、Prompt 审批、Prompt 哈希或二次改写；
- `workflow-state.json`、`generation-state.json`、checkpoint、transition log 或任何状态台账；
- 请求/响应快照、调试日志、测试报告或开发记录；
- 中途确认、进度汇报、方案说明或额外交付说明。

图片渠道自身在服务端执行的规则不属于插件步骤，插件不得因此增加本地审查链。

## 允许阻断

只允许以下实际执行错误阻断：

- 首次使用尚未选择生图模型或对应 API Key 未配置；
- 所选图片渠道请求失败且没有返回任何图片；
- HTML 生成命令失败。

阻断时只反馈实际错误，不启动诊断、审计、替代模型或补救工作流。

## 输出

```yaml
delivery_html: path
generated_images: [path]
failed_pages: [object]
```

最终回复以 HTML 文件为主。不要附加测试报告、检查结论、状态记录或执行过程。

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/轮播叙事.md`
