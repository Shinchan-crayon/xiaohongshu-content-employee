# xiaohongshu-content-employee

一套面向 Codex 的小红书内容工作流。它把产品资料转成经过事实核对、选题确认和自然化审核的内容包，还可以在用户确认后生成 1080x1440 小红书视觉成品，最后输出可独立打开的 HTML 交付页。

当前版本：`1.5.0`

## 适用场景

- 产品种草与功能介绍
- 软件、服务和通用消费品内容
- 需要保留事实来源与人工确认节点的内容生产
- 需要标题、正文、标签、封面和轮播脚本的一体化交付
- 需要复用真实产品图，并可选择 AI 补充场景或背景
- 需要在中断后继续执行的长流程任务

## 工作流

工作流由一个公开入口驱动，共 8 个阶段：

1. `intake`：读取产品资料、图片和参考内容，区分事实、推断、假设与未知信息。
2. `research`：分析参考材料，按需进行外部调研，形成 2-5 个选题候选。
3. `angle_confirmation`：等待用户人工确认选题方向。
4. `drafting`：生成标题、正文、标签、封面文案、轮播脚本和图片使用方案。
5. `review`：依次检查事实、宣传风险、内容一致性、完整性、自然表达和 AI 写作模式。
6. `visuals`：选择视觉模式，确认图片规划；需要 AI 补图时再选择渠道和模型、审核 Prompt 并生成成品图。
7. `delivery`：校验结构化数据和图片资源，生成独立 HTML 交付页。
8. `completed`：保存最终文件、审核结论和关键确认记录。

流程状态保存在 `workflow-state.json` 中。材料补充、选题确认、审核阻断和任务恢复都有明确状态，不依赖一次对话完成全部步骤。

## 素材获取方式

开始制作前，工作流会让用户在两个方案中选择：

1. **用户提供素材链接**：用户提交文章或产品页面链接，插件只读取这些链接，不自行扩展搜索。
2. **插件内部搜索**：用户不需要准备链接，插件根据产品、内容目标和目标用户调用内部调研 Skill 搜索素材，并记录来源。

对应输入字段为：

```yaml
material_source_mode: user_links | internal_search
material_links: [url]
```

如果没有填写 `material_source_mode`，工作流会先展示两个方案并等待选择。内部搜索不可用或没有找到可靠来源时，不会编造素材，而是请用户重试或改为提供链接。

无论选择哪一种方式，插件都会先列出来源、链接和核心信息，等用户确认素材范围后再生成选题。涉及数字、归属、因果、效果、认证或引用时，只维护一张高风险事实核查表，并在最终审核时继续复用。

## 图片制作方式

文案审核通过后，工作流会让用户选择以下一种方式：

1. **只用现有素材 `existing_only`**：使用用户提供的真实产品图、纯色背景和确定性信息卡，不调用图片模型。
2. **AI 辅助 `ai_assist`**：AI 只生成场景或背景，再由本地合成工具叠加真实产品图和精确中文文字。

选择 `ai_assist` 后，用户会继续选择图片渠道和模型。插件支持 ThinkAI Image 2、ThinkAI Nano、火山引擎 Seedream、OpenAI GPT Image、Google Nano Banana 和受限自定义渠道。

图片生成前有两次人工确认：

- **图片规划确认**：确认每一页要表达什么、使用哪张真实图片、哪些部分由 AI 补充。
- **Prompt 确认**：确认实际 Prompt、渠道、模型、尺寸和质量。

Prompt、渠道、模型、尺寸或质量发生变化时，之前的批准立即失效，必须重新确认。付费生成请求不会自动重试。

真实产品的包装、颜色、材质、接口、标签和比例不会交给 AI 重绘。精确中文、数字、参数和品牌名称由本地工具排版，最终图片统一输出为 1080x1440 PNG。

## Skill 组成

| Skill | 作用 | 流程角色 |
| --- | --- | --- |
| `xhs-content-employee` | 维护状态并编排完整工作流 | 唯一公开入口 |
| `product-material-intake` | 整理事实、图片、卖点和缺失材料 | 由主流程调用 |
| `xhs-research-strategy` | 建立来源记录并生成选题候选 | 由主流程调用 |
| `xhs-copy-storyboard` | 生成文案、封面和轮播脚本 | 由主流程调用 |
| `xhs-humanize-review` | 执行事实、风险和自然表达审核 | 由主流程调用 |
| `xhs-visual-planner` | 规划封面、轮播任务和真实图片使用方式 | 由主流程调用 |
| `xhs-approved-image-generator` | 执行已批准的 Prompt 并合成视觉成品 | 由主流程调用 |
| `xhs-html-delivery` | 生成独立 HTML 交付页 | 由主流程调用 |

“由主流程调用”表示正常使用时由 `xhs-content-employee` 按阶段显式调用。它们随插件一起安装，用户也可以手动指定；`allow_implicit_invocation: false` 只是不允许 Codex 在没有明确指令时自动选中。

## 安装

推荐通过“小红书内容员工”Marketplace 安装：

```bash
codex plugin marketplace add Shinchan-crayon/xiaohongshu-content-employee-marketplace --ref main
codex plugin add xiaohongshu-content-employee@xiaohongshu-content-employee
```

安装完成后重新打开 Codex，在“插件 > 个人”中找到“小红书内容员工”。

### 旧版 Skill 安装方式

Python 安装工具暂时保留用于旧版或离线环境。先克隆源码仓库：

```bash
gh repo clone Shinchan-crayon/xiaohongshu-content-employee
cd xiaohongshu-content-employee
python3 scripts/安装工具/install_codex_skills.py
```

需要指定其他位置时：

```bash
python3 scripts/安装工具/install_codex_skills.py --target ./custom-skills
```

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
- 选择 `existing_only` 或 `ai_assist`
- 确认图片规划
- 使用 AI 补图时确认渠道和模型，以及最终 Prompt、尺寸和质量

## 输入

主入口接受以下信息：

```yaml
content_goal: string
product_or_service: string
product_images: [path]
existing_copy: string | null
material_source_mode: user_links | internal_search
material_links: [url]
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
- 已确认的图片规划
- 可选的 1080x1440 PNG 视觉成品及渠道、模型记录
- 审核结果
- 交付 JSON
- 可独立打开的 HTML 交付页

## 能力边界

- 不自动发布到小红书。
- 不把缺少来源的销量、效果、认证、趋势或用户评价写成事实。
- 外部调研不可用时会明确记录限制，并基于客户材料继续工作。
- 图片服务不可用时不会自动重试或自动切换渠道，用户可以改选 `existing_only`。
- AI 不负责重绘真实产品，也不负责输出精确中文和参数。
- 审核未通过、必需字段缺失或图片资源不可访问时，不生成最终交付页。
- 外部检测出现高 AI 特征时，正文必须结构性重写并重新审核，不能只替换几个词。

## 目录结构

```text
xiaohongshu-content-employee/
├── .codex-plugin/
├── README.md
├── plugin-manifest/
├── skills/
├── references/
│   ├── 小红书内容规范/
│   ├── 审核规则/
│   ├── 小红书生图知识/
│   └── 行业模板/
├── templates/
│   └── HTML交付模板/
├── scripts/
│   ├── HTML生成工具/
│   ├── 图片合成工具/
│   ├── 生图工具/
│   ├── 审核工具/
│   └── 安装工具/
└── assets/
```
