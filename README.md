<p align="center">
  <img src="plugins/xiaohongshu-content-employee/assets/plugin-icon.png" width="128" alt="小红书内容员工">
</p>

<h1 align="center">小红书内容员工</h1>

<p align="center">
  面向个人创作者，把素材、选题、文案、多模型配图和 HTML 交付串成一条直接执行的小红书图文工作流。
</p>

<p align="center">
  ThinkAI · Codex / Claude Code / Hermes · 当前版本 <code>2.1.0</code>
</p>

## 效果预览

最终交付是一份可以直接打开和继续编辑的独立 HTML：上方整理图片，左侧
编辑候选标题和正文，右侧同步预览笔记与封面。

![小红书内容交付效果预览：Air Feel](assets/previews/delivery-preview-air-feel.png)

![小红书内容交付效果预览：洗发水](assets/previews/delivery-preview-shampoo.png)

## 直接开始

把仓库链接和产品资料一起发给 Codex：

```text
请安装并使用“小红书内容员工”：
https://github.com/Shinchan-crayon/xiaohongshu-content-employee

根据我提供的资料制作一套小红书图文内容。第一次使用时先列出可用生图渠道
和具体模型供我选择并保存；生成文案和最终 Prompt 后，先展示完整 Prompt 与
参考图关系供我批准，再并发生图；全部图片完成后生成图片内嵌的内容 HTML 并
生成独立运行日志，然后完成交付。
```

已经安装时，直接说：

```text
请使用 $xhs-content-employee，根据我提供的资料制作一套小红书图文内容。

内容目标：
产品或服务：
产品图片或素材链接：
已有文案：
参考内容：
目标用户：
账号语气：
```

资料不完整时，插件会在选题确定前使用可用搜索能力补充必要公开信息。

## 固定执行流程

```text
创建任务
-> 锁定产品身份
-> 提取证据和卖点
-> 生成文案与最终 Prompt
-> 文案自然化
-> 展示 Prompt 和参考图关系
-> 用户批准
-> 并发生图
-> 生成图片内嵌的内容 HTML
-> 生成独立运行日志
-> 完成交付
```

Compose 阶段在同一次模型调用中生成完整文案、至少 5 个候选标题、轮播结构、全部最终
Prompt 和每页参考图关系。随后 Humanize 阶段只对 `content.json` 的可见文字进行一次
自然化改写，不改变 JSON 结构、现有排版或 `visual.json`。主控再展示完整 Prompt 包并计算稳定 SHA-256；
只有用户批准的哈希与当前 Prompt 包一致，才能进入付费生图。Prompt、页面或
参考图映射变化后必须重新展示并批准。

产品身份和证据仍会先锁定，但这些是内部事实护栏，不是成稿模板。Compose 会把
事实转成用户场景、把特征转成具体收益、把限制转成自然建议；型号和变体只在提及
时保持准确，官方页面标题、货号和内部审核字段不会为满足校验而塞进正文。

执行时由薄主控调度两个相互独立、无历史的模型 Worker 和两个 Python Executor：

- `Research Worker`：一次调用内研究商品页、锁定产品身份、提取证据和卖点，输出 `material.json` 与 `evidence.json`
- `Compose Worker`：一次调用内生成文案、轮播和全部最终 Prompt，输出 `content.json` 与 `visual.json`
- `Produce Executor`：校验批准后用 Python 并发生成全部计划图片和 `generation.json`
- `Deliver Executor`：全部计划图片均为 `complete` 后，用 Python 输出默认内嵌图片的内容 HTML、独立运行日志和内部 `delivery.json`

两个 Worker 使用不同的 `worker_session_id`，均以 `fork_context=false` 创建，每个
只创建一次、等待一次、关闭一次，阶段结束后销毁上下文。两个 Executor 不创建
Worker，也不调用内容模型。薄主控只通过 `runtime.json` 保存阶段、批准状态、
结构化产物地址、Worker 会话标识和最终交付物地址。

正常内容任务不按代码工程执行：不扫描完整仓库、不创建开发计划、不运行插件测试、
不解释插件架构、不读取运行时代码、不做 Prompt 二次复审，也不打开 HTML、验图
或截图。商品页研究仍会完整执行；Compose 后只做一次程序校验并立即展示 Prompt。

## 状态与结构化交接

工作流按代码级状态机严格执行：

```text
created
-> prepared
-> evidenced
-> composed
-> prompt_pending_approval
-> prompt_approved
-> producing
-> delivered
-> completed
```

阶段间只通过 `task.json`、`material.json`、`evidence.json`、`content.json`、
`visual.json`、`approval.json`、`generation.json`、`delivery.json` 和
`runtime.json` 交接。图片缺失、失败或状态不确定时不能进入 `delivered`；
内容 HTML 或独立运行日志不存在时不能进入 `completed`。

## 你会得到什么

- 至少 5 个可横向选择和继续编辑的候选标题
- 可继续编辑的小红书正文与标签
- 封面文案和最小必要轮播
- 所选图片模型全批并发生成的 3:4 配图
- 每个产品主体页都绑定搜集到的真实产品参考图，同时保持统一风格和不同构图
- 图片已内嵌、可切换图片、编辑标题正文、预览笔记与封面的独立 HTML
- 汇总已有总耗时、阶段耗时、Token、费用、图片成功率和渠道信息的独立运行日志；不会为了日志增加模型调用或额外检查

## 首次选择生图模型

第一次使用时，插件会先把下列渠道、具体模型和默认尺寸列给用户：

| 渠道 | 模型 | 默认竖版尺寸 | 真实产品参考图 |
| --- | --- | --- | --- |
| ThinkAI Image 2 | `gpt-image-2` | `1536x2048` | 暂不支持 |
| ThinkAI Nano | `nano-banana-2` | `3:4@2K` | 暂不支持 |
| 火山引擎 Seedream | `doubao-seedream-5-0-lite-260128` | `1728x2304` | 支持 |
| OpenAI GPT Image | `gpt-image-2` | `1024x1536` | 暂不支持 |
| Google Nano Banana | `gemini-3.1-flash-image` | `3:4@2K` | 暂不支持 |
| 其他渠道 | 用户自定义 | 用户自定义 | 暂不支持 |

用户选择并配置后，该项会保存为当前安装环境的默认生图模型。后续任务直接
复用，不再重复询问；只有用户明确要求切换时才重新选择。

当前只有 Seedream 支持真实产品参考图。产品任务会把参考图绑定到每个产品主体
页，并只生成参考图明确支持的视角；选择其他渠道时，不会伪装成已支持产品保真。

也可以手动列出并配置：

```bash
python3 plugins/xiaohongshu-content-employee/scripts/生图工具/configure_provider.py --list
python3 plugins/xiaohongshu-content-employee/scripts/生图工具/configure_provider.py seedream
```

配置保存在插件目录的 `config.json`，该文件已被 Git 忽略，不会进入仓库。

## 安装

### Codex

在 Codex 对话中发送仓库链接并要求安装，或使用命令行：

```bash
codex plugin marketplace add Shinchan-crayon/xiaohongshu-content-employee --ref main
codex plugin add xiaohongshu-content-employee@xiaohongshu-content-employee
```

### Claude Code

```bash
claude plugin marketplace add Shinchan-crayon/xiaohongshu-content-employee
claude plugin install xiaohongshu-content-employee@xiaohongshu-content-employee
```

没有全局安装 Claude Code 时，可把命令中的 `claude` 换成
`npx -y @anthropic-ai/claude-code`。

### Hermes

克隆仓库后运行：

```bash
python3 plugins/xiaohongshu-content-employee/scripts/安装工具/install_skills.py --runtime hermes
```

安装器会安装同一套八个 Skill。已有同名 Skill 时默认不覆盖；确认升级时追加
`--force`。

## Skill 组成

| Skill | 作用 |
| --- | --- |
| `xhs-content-employee` | 唯一公开入口和薄主控编排 |
| `product-material-intake` | 锁定产品身份并整理素材 |
| `xhs-research-strategy` | 提取证据、卖点和选题 |
| `xhs-copy-storyboard` | 生成标题、正文、标签和轮播 |
| `xhs-visual-planner` | 同一次 Compose 调用生成全部最终 Prompt 与参考图关系 |
| `xhs-approved-image-generator` | 校验 Prompt 批准哈希后全批并发生图 |
| `xhs-html-delivery` | 全部计划图片完成后生成默认内嵌图片的 HTML、独立运行日志和交付记录 |

## 能力边界

- 不自动发布到小红书。
- 不保存用户的 API Key 到仓库。
- 不自动切换模型或图片渠道。
- 不为失败页面自动重试或补图。

## 开发者

ThinkAI
