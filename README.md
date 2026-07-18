# 小红书内容员工

![小红书内容员工](assets/plugin-icon.png)

面向个人创作者的小红书图文工作流。一个仓库同时支持 Codex、Claude Code
和 Hermes，共用同一套 Skill、知识库、生图工具与 HTML 交付模板。

当前版本：`1.9.0`

## 能做什么

- 整理用户提供的产品资料、网页链接和图片素材。
- 素材不足时按需调研，并建立事实来源台账。
- 生成候选标题、正文、标签、封面文案和轮播脚本。
- 选择已有图片或 AI 生图渠道，并发生成整组 3:4 图片。
- 输出可编辑标题与正文、可切换图片和预览封面的独立 HTML。
- 在用户同意时沉淀可复用的账号偏好和内容经验。

公开入口始终是 `xhs-content-employee`，其余六个 Skill 由入口按需调用。

## 安装

### Codex

把本仓库添加为 Marketplace，再安装插件：

```bash
codex plugin marketplace add Shinchan-crayon/xiaohongshu-content-employee --ref main
codex plugin add xiaohongshu-content-employee@xiaohongshu-content-employee
```

安装后可在 Codex 插件页面看到“小红书内容员工”的名称、Logo 和介绍。

### Claude Code

把本仓库添加为 Marketplace，再安装插件：

```bash
claude plugin marketplace add Shinchan-crayon/xiaohongshu-content-employee
claude plugin install xiaohongshu-content-employee@xiaohongshu-content-employee
```

未全局安装 Claude Code 时，可把命令中的 `claude` 换成
`npx -y @anthropic-ai/claude-code`。

### Hermes

克隆仓库后运行通用安装器：

```bash
python3 scripts/安装工具/install_skills.py --runtime hermes
```

安装器会把七个 Skill 安装为自包含目录。已有同名 Skill 时不会覆盖；确认
需要升级时追加 `--force`。

### 自定义安装目录

Codex 和 Hermes 都可以指定 Skill 目录：

```bash
python3 scripts/安装工具/install_skills.py --target PATH
```

## 使用

在 Codex、Claude Code 或 Hermes 中直接说：

```text
请使用 xhs-content-employee，根据我提供的产品资料制作一套小红书图文内容。

内容目标：介绍产品的核心使用场景
产品或服务：填写产品名称和基本说明
产品图片：填写图片文件或网页链接
已有文案：填写原始资料
参考内容：填写文件路径或网页地址
目标用户：填写目标人群
账号语气：填写表达偏好
```

首次使用会选择：

1. `existing_only`：只使用已有图片。
2. `ai_assist`：选择图片渠道、模型、尺寸和质量。

后续任务会先提示本次沿用的图片设置。付费生图前保留一次整批批准。

## 工作流

`prepare -> evidence -> compose -> produce -> deliver -> completed`

| 阶段 | 结果 |
| --- | --- |
| `prepare` | 整理输入、图片设置和任务状态 |
| `evidence` | 汇总事实来源、受众洞察和内容方向 |
| `compose` | 生成文案、轮播和生图 Prompt |
| `produce` | 并发生成全部图片，失败页独立重试 |
| `deliver` | 生成独立 HTML 并交付 |
| `completed` | 保存最终结果并停止 |

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

## 图片规则

- 首图可以绑定清晰的官方产品参考图。
- 图片中的中文文字由图片模型直接生成，代码不在纯色背景上排字。
- 默认一次并发全部待生成页面，没有固定页数上限。
- 每页最多尝试三次，成功页不重复生成。
- API Key、鉴权信息和本机配置路径不会进入状态文件或 HTML。

## 输出

- 产品材料和事实来源台账
- 标题、正文、标签、封面文案和轮播脚本
- 生图 Prompt、生成状态和模型原始图片
- 可独立打开和编辑的 HTML

## 能力边界

- 不自动发布到小红书。
- 不把没有来源的产品事实写成确定结论。
- 不保存密码、访问令牌或 API Key。
- 图片渠道不可用时不私自切换渠道或模式。
- 已达到三次尝试的失败页不会继续付费重试。
