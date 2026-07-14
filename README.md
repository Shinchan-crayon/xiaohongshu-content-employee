# xiaohongshu-content-employee

一套面向 Codex 的小红书内容工作流。它把客户提供的产品资料转成经过事实核对、选题确认、文案审核和结构校验的内容包，并生成可独立打开的 HTML 交付页。

当前版本：`1.1.0`

## 适用场景

- 产品种草与功能介绍
- 软件、服务和通用消费品内容
- 需要保留事实来源与人工确认节点的内容生产
- 需要标题、正文、标签、封面和轮播脚本的一体化交付
- 需要在中断后继续执行的长流程任务

## 工作流

工作流由一个公开入口驱动，共 7 个阶段：

1. `intake`：读取产品资料、图片和参考内容，区分事实、推断、假设与未知信息。
2. `research`：分析参考材料，按需进行外部调研，形成 2-5 个选题候选。
3. `angle_confirmation`：等待用户人工确认选题方向。
4. `drafting`：生成标题、正文、标签、封面文案、轮播脚本和图片使用方案。
5. `review`：依次检查事实、宣传风险、内容一致性、完整性、自然表达和 AI 写作模式。
6. `delivery`：校验结构化数据和图片资源，生成独立 HTML 交付页。
7. `completed`：保存最终文件、审核结论和关键确认记录。

流程状态保存在 `workflow-state.json` 中。材料补充、选题确认、审核阻断和任务恢复都有明确状态，不依赖一次对话完成全部步骤。

## Skill 组成

| Skill | 作用 | 调用方式 |
| --- | --- | --- |
| `xhs-content-employee` | 维护状态并编排完整工作流 | 唯一公开入口 |
| `product-material-intake` | 整理事实、图片、卖点和缺失材料 | 内部阶段 |
| `xhs-research-strategy` | 建立来源记录并生成选题候选 | 内部阶段 |
| `xhs-copy-storyboard` | 生成文案、封面和轮播脚本 | 内部阶段 |
| `xhs-humanize-review` | 执行事实、风险和自然表达审核 | 内部阶段 |
| `xhs-html-delivery` | 生成独立 HTML 交付页 | 内部阶段 |

## 安装

要求：

- 已安装 Git 或 GitHub CLI
- 已安装 Python 3
- 已安装并可使用 Codex

克隆仓库：

```bash
gh repo clone Shinchan-crayon/xiaohongshu-content-employee
cd xiaohongshu-content-employee
```

安装 6 个 Skills：

```bash
python3 scripts/安装工具/install_codex_skills.py
```

安装脚本默认使用 Codex 的 Skills 目录。需要指定其他位置时：

```bash
python3 scripts/安装工具/install_codex_skills.py --target ./custom-skills
```

目标位置已存在同名 Skill 时，安装会停止以保护现有文件。确认需要替换后再使用：

```bash
python3 scripts/安装工具/install_codex_skills.py --force
```

安装完成后重新启动 Codex。

## 使用

在 Codex 中从唯一公开入口开始：

```text
请使用 $xhs-content-employee，根据我提供的产品资料制作一套小红书图文内容。

内容目标：介绍产品的核心使用场景
产品或服务：填写产品名称和基本说明
产品图片：填写本地图片路径
已有文案：填写客户提供的原始资料
参考内容：填写文件路径或网页地址
目标用户：填写目标人群
账号语气：填写账号的人设与表达偏好
```

工作流会先整理材料和待确认问题，不会直接跳到最终文案。用户至少需要参与以下人工确认：

- 补充或确认关键产品事实
- 确认最终选题方向
- 决定是否保留假设或未知信息
- 确认是否使用可选的 AI 补图

## 输入

主入口接受以下信息：

```yaml
content_goal: string
product_or_service: string
product_images: [path]
existing_copy: string | null
references: [path_or_url]
target_audience: string | null
account_voice: object | null
```

## 输出

完整执行后会得到：

- `workflow-state.json`：可恢复的流程状态
- 结构化素材记录和来源记录
- 已确认选题
- 标题、正文、标签、封面文案和轮播脚本
- 图片使用方案与事实映射
- 审核结果
- 交付 JSON
- 可独立打开的 HTML 交付页

## 能力边界

- 不自动发布到小红书。
- 不把缺少来源的销量、效果、认证、趋势或用户评价写成事实。
- 外部调研不可用时会明确记录限制，并基于客户材料继续工作。
- 图片服务不可用时优先使用真实产品图和 HTML/CSS 信息卡。
- 审核未通过、必需字段缺失或图片资源不可访问时，不生成最终交付页。

## 目录结构

```text
plugin-manifest/  产品清单与入口声明
skills/           6 个可安装的 Codex Skills
references/       内容规范、审核规则和行业模板
templates/        HTML 交付模板
scripts/          安装工具和 HTML 生成工具
assets/           流程状态与交付数据结构
```
