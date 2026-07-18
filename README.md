<p align="center">
  <img src="plugins/xiaohongshu-content-employee/assets/plugin-icon.png" width="128" alt="小红书内容员工">
</p>

<h1 align="center">小红书内容员工</h1>

<p align="center">
  把产品资料、事实来源、文案、配图和 HTML 交付串成一套可直接使用的小红书图文工作流。
</p>

<p align="center">
  ThinkAI · Codex / Claude Code / Hermes · 当前版本 <code>1.9.0</code>
</p>

## 效果预览

最终交付不是一堆零散文本，而是一份可以直接打开、继续编辑的独立 HTML：
上方整理图片，左侧编辑候选标题和正文，右侧同步预览笔记与封面。

![小红书内容交付效果预览：Air Feel](assets/previews/delivery-preview-air-feel.png)

![小红书内容交付效果预览：洗发水](assets/previews/delivery-preview-shampoo.png)

## 直接开始

把下面这段话和产品资料一起发给 Codex：

```text
请安装并使用“小红书内容员工”：
https://github.com/Shinchan-crayon/xiaohongshu-content-employee

根据我提供的产品资料制作一套小红书图文内容。
```

安装完成后，可在 Codex 的“插件 > 个人”中看到“小红书内容员工”的名称、
Logo 和介绍。

已经安装时，可以直接说：

```text
请使用 $xhs-content-employee，根据我提供的产品资料制作一套小红书图文内容。

内容目标：
产品或服务：
产品图片或素材链接：
已有文案：
参考内容：
目标用户：
账号语气：
```

资料不完整也可以开始。插件会明确告诉你缺少什么，并让你选择：

1. 使用你提供的网页、图片和产品资料。
2. 调用可用的搜索能力补充公开素材和事实来源。

## 你会得到什么

- 经过分级的产品事实与来源记录
- 可横向选择的候选标题
- 可继续编辑的小红书正文和标签
- 封面文案与最小必要轮播脚本
- 已有图片方案，或经确认后生成的整组 3:4 配图
- 可切换图片、编辑标题正文、预览笔记与封面的独立 HTML

插件不会把没有来源的信息写成确定事实，也不会自动发布到小红书。

## 图片怎么处理

首次使用会引导选择图片方式：

1. `existing_only`：只使用已有图片。
2. `ai_assist`：选择可用的图片渠道、模型、尺寸和质量。

后续任务会先展示本次沿用的图片设置。需要付费生图时，整组 Prompt 和设置
确认后才会生成；全部页面一次并发提交，失败页单独重试，不重复消耗成功页。

产品图可以绑定清晰的官方参考图。生成结果使用模型原图，不再通过 Python
在纯色背景上排字，也不额外执行抠图、贴图或伪造产品界面。

## 包含的能力

- 产品素材整理与事实分级
- 公开资料搜索与来源核查
- 小红书选题、标题、正文、标签和轮播规划
- 官方产品参考图约束与简洁生图 Prompt
- 多图并发生成和失败页独立重试
- 可编辑、可缩放、可独立打开的 HTML 交付
- 保存用户明确表达的账号偏好，经确认后复用于后续内容

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

安装器会安装同一套七个 Skill。已有同名 Skill 时默认不覆盖；确认升级时追加
`--force`。

## 工作流程

`整理输入 -> 核查事实 -> 生成文案与图片方案 -> 并发生成 -> HTML 交付`

公开入口始终是 `xhs-content-employee`。其余六个 Skill 在流程内部按需协作，
用户不需要逐个调用。

## 能力边界

- 不自动发布到小红书。
- 不保存密码、访问令牌或 API Key。
- 图片渠道不可用时，不会私自更换渠道或产生额外费用。
- 达到重试上限的失败页会明确返回页码和错误。
- 用户没有确认的外部内容规律，不会被当作长期偏好保存。

## 开发者

ThinkAI
