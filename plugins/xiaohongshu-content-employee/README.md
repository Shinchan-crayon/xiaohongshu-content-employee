# 小红书内容员工

面向个人创作者的小红书图文插件，当前版本：`2.1.2`。

## 使用

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

## 唯一执行流程

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
Prompt 和每页参考图关系。随后 Humanize 阶段只改写 `content.json` 的可见文字一次，
不改变 JSON 结构、现有排版或 `visual.json`。主控展示完整 Prompt 包并计算稳定 SHA-256，用户
批准的哈希必须与当前 Prompt 包一致；Prompt、页面或参考图映射变化后重新进入
待批准状态。

产品身份和证据仍会先锁定，但这些是内部事实护栏，不是成稿模板。Compose 会把
事实转成用户场景、把特征转成具体收益、把限制转成自然建议；型号和变体只在提及
时保持准确，官方页面标题、货号和内部审核字段不会为满足校验而塞进正文。

薄主控会自动调度三个相互独立、无历史的模型 Worker 和两个 Python Executor：

- `Research Worker`：一次调用内研究商品页、锁定产品身份并提取证据和卖点，输出 `material.json` 与 `evidence.json`
- `Compose Worker`：同一次调用输出 `content.json` 和 `visual.json`
- `Humanize Worker`：一次调用内只改写 `content.json` 的标题、正文和轮播可见文字，不读取或修改 `visual.json`
- `Produce Executor`：校验批准后用 Python 并发生图，输出 `generation.json`
- `Deliver Executor`：全部计划图片完成后用 Python 输出默认内嵌图片的内容 HTML、独立运行日志和内部 `delivery.json`

三个 Worker 使用不同的 `worker_session_id`，以 `fork_context=false` 创建，每个只
创建一次、等待一次、关闭一次，阶段结束后销毁上下文。两个 Executor 不创建
Worker，也不调用内容模型。每个产品主体页都会绑定真实产品参考图，同时沿用统一
`style_anchor` 并变化构图。

正常内容任务禁止进入开发模式：不扫描完整仓库、不制定工程实施方案、不运行插件测试、
不解释插件架构、不读取运行时代码、不做 Prompt 二次复审，也不打开 HTML、验图
或截图。商品页研究仍正常执行；Compose 后固定执行一次文本自然化，不做检测、报告、
重试或二次复审，再展示 Prompt。

## 状态与结构化交接

```text
created
-> prepared
-> evidenced
-> composed
-> humanizing
-> humanized
-> prompt_pending_approval
-> prompt_approved
-> producing
-> delivered
-> completed
```

阶段间只通过 `task.json`、`material.json`、`evidence.json`、`content.json`、
`visual.json`、`approval.json`、`generation.json`、`delivery.json` 和
`runtime.json` 交接。图片缺失、失败或状态不确定时不能交付；内容 HTML 不存在
或运行日志不存在时不能完成。运行日志只汇总已有数据，不为补齐统计增加模型调用、
素材搜索、重复读取或额外检查。

## 首次选择生图模型

第一次使用时，插件会列出 ThinkAI GPT Image 2 4K、ThinkAI Nano、火山引擎
Seedream、OpenAI GPT Image、Google Nano Banana 和自定义渠道，并同时显示
具体模型与默认尺寸。用户选择并配置后保存为默认项，后续直接复用。

当前只有 Seedream 支持真实产品参考图。产品任务使用 Seedream 时，会让每个
产品主体页参考真实产品图，并只使用参考图支持的视角；其他渠道暂不声明产品
保真能力。

手动查看列表：

```bash
python3 scripts/生图工具/configure_provider.py --list
```

配置保存在 `config.json`，该文件不会进入仓库。

## Skill 组成

| Skill | 作用 |
| --- | --- |
| `xhs-content-employee` | 唯一公开入口和薄主控编排 |
| `product-material-intake` | 锁定产品身份并整理素材 |
| `xhs-research-strategy` | 提取证据、卖点和选题 |
| `xhs-copy-storyboard` | 生成标题、正文、标签和轮播 |
| `xhs-visual-planner` | 同一次 Compose 调用生成全部最终 Prompt 与参考图关系 |
| `xhs-humanize-review` | 一次自然化改写标题、正文和轮播可见文字，保留格式、JSON 结构与视觉 Prompt |
| `xhs-approved-image-generator` | 校验 Prompt 批准哈希后全批并发生图 |
| `xhs-html-delivery` | 全部计划图片完成后生成默认内嵌图片的 HTML、独立运行日志和交付记录 |

## 能力边界

- 不自动发布到小红书。
- 不保存 API Key 到仓库。
- 不自动切换模型或图片渠道。
- 不为失败页面自动重试或补图。
