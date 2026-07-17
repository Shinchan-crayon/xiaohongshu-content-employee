# xiaohongshu-content-employee

面向 Codex 的小红书图文工作流。它由主 Agent 有界并行处理独立调研任务，一次生成文案、最小必要轮播和简洁生图 Prompt，使用官网产品参考图并发生成模型原图，最后输出独立 HTML。

当前版本：`1.8.3`

## 核心流程

`prepare -> evidence -> compose -> produce -> deliver -> completed`

1. `prepare`：完成或复用图片渠道设置，整理输入并按需启动一次并行调研。
2. `evidence`：主 Agent 汇总最多三个子 Agent 的结构化结果，建立来源台账。
3. `compose`：生成标题、正文、标签、最小必要轮播和全部短 Prompt。
4. `produce`：一次并发提交全部页面，失败页最多重试三次。
5. `deliver`：校验资源、3:4 比例和图片映射，生成 HTML。
6. `completed`：保存最终交付。

本版本不运行文案风险、质量、自然化或 AI 特征检测。

## 并行规则

- 仅在存在至少两个独立调研任务且运行环境支持时创建子 Agent。
- 每次内容任务最多分派一轮、最多三个子 Agent。
- 子 Agent 只读同一份任务快照，只返回产品事实、来源、受众洞察或内容方向。
- 只有主 Agent 可以修改 `workflow-state.json`、材料记录和交付文件。
- 子 Agent 不发起付费生图、不生成 HTML、不继续创建子 Agent。
- 单项失败只由主 Agent 补做缺失项；整轮失败立即回到原有顺序流程。
- 文案定稿、生图批准、整批生图和 HTML 交付保持集中执行。

## 图片规则

- 仅首图绑定清晰的官网产品参考图，第二页起不再传参考图。
- 首图参考图哈希加入批次批准摘要；参考图变化后旧批准失效。
- 首图 Prompt 前置产品主体和官网参考图要求；后续 Prompt 只保留页面目标、必须出现的中文文字、字体气质和 3:4 比例。
- 构图、场景、光线、道具、配色和视觉创意交给图片模型自由发挥。
- 图片中的中文文字由模型直接生成，代码不加字。
- 不运行裁切、抠图、产品叠加、背景替换或图片合成。
- 模型返回的 PNG、JPEG 或 WebP 原字节直接交付。
- 默认一次并发全部待生成页面，没有固定 3 页或 8 页上限。
- 每页独立重试，最多三次；成功页不重试。
- 三次仍失败时返回准确页码和错误。
- 同一批次内不允许出现 100% 完全相同的 Prompt。
- 不执行生成后图片相似度自检、删除或重生成。
- 轻微伪品牌文字或局部乱码允许交付。

## Prompt 示例

```text
参考图片主体为资生堂洁面膏，参考官网图片，其余构图和场景自由发挥。为小红书制作一张 3:4 成品图，表达温和清洁后的清透肤感，自然呈现中文“洗完干净，不必紧绷”，字体气质清爽。
```

不要继续追加复杂摄影参数或长负面词列表。

## 首次图片设置

首次使用选择：

1. `existing_only`：直接使用已有图片。
2. `ai_assist`：选择图片渠道、模型、尺寸和质量。

API Key 通过隐藏输入保存。后续任务提示“本次沿用：模式 / 渠道 / 模型”，不重复询问。密钥、鉴权头和本机配置路径不会写入状态、日志或 HTML。

付费生图前仍保留一次整批批准。来源列表、自动选题、图片规划、Prompt 和 HTML 不单独等待确认。

## Skill 组成

| Skill | 作用 |
| --- | --- |
| `xhs-content-employee` | 唯一公开入口和流程状态管理 |
| `product-material-intake` | 整理产品事实与素材 |
| `xhs-research-strategy` | 建立来源台账和选题候选 |
| `xhs-copy-storyboard` | 生成文案与最小必要轮播 |
| `xhs-visual-planner` | 生成简洁、开放的参考图 Prompt |
| `xhs-approved-image-generator` | 全量并发生成和失败页重试 |
| `xhs-html-delivery` | 生成独立 HTML |

## 安装

```bash
codex plugin marketplace add Shinchan-crayon/xiaohongshu-content-employee-marketplace --ref main
codex plugin add xiaohongshu-content-employee@xiaohongshu-content-employee
```

离线 Skill 安装：

```bash
python3 scripts/安装工具/install_codex_skills.py
```

## 使用

```text
请使用 $xhs-content-employee，根据我提供的产品资料制作一套小红书图文内容。

内容目标：介绍产品的核心使用场景
产品或服务：填写产品名称和基本说明
产品图片：填写官网产品参考图的本地路径
已有文案：填写原始资料
参考内容：填写文件路径或网页地址
目标用户：填写目标人群
账号语气：填写表达偏好
```

## 输出

- `workflow-state.json`
- 产品材料和来源台账
- 标题、正文、标签、封面文案和轮播脚本
- 首图简洁 Prompt 与官网参考图绑定
- 模型原始 3:4 图片和生成状态
- 交付 JSON
- 可独立打开的 HTML

## 能力边界

- 不自动发布到小红书。
- 不把没有来源的产品事实写成确定结论。
- 不保存密码、访问令牌或 API Key。
- 图片渠道不可用时不自动切换渠道或模式。
- 已达到三次尝试的失败页不会继续付费重试。
