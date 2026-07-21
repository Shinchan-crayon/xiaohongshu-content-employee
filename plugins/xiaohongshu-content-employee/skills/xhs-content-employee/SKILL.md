---
name: xhs-content-employee
description: 唯一公开入口；用薄主控、三个无历史模型 Worker 和两个 Python Executor 完成商品研究、文案自然化、Prompt 批准、并发生图、内嵌图片 HTML 与独立运行日志交付。
---

# Xiaohongshu Content Employee

## Fixed Pipeline

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

目标完成时间为 5 至 10 分钟，产品准确性和内容质量优先。
文案和全部最终 Prompt 必须在同一次 compose 调用中完成。每次内容任务都必须展示 Prompt 并
等待批准；用户批准后，固定执行并发生图、图片内嵌 HTML、独立运行日志生成和交付。

## Thin Controller

主控只保留：

- `run_id`
- 任务摘要
- 当前阶段
- 用户批准状态
- 默认生图渠道和模型
- 各结构化产物的文件地址
- Worker 会话标识
- 最终交付物地址

主控通过读取 `runtime.json` 调度下一阶段。主控不得长期加载完整 Skill 文档、
完整产品资料、完整证据、完整文案、完整 Prompt 或 Worker 对话历史。
运行状态只写入插件和交付目录之外的 `run_dir`。

Research Worker、Compose Worker 和 Humanize Worker 都是模型 Worker。三者必须以
`fork_context=false` 创建独立无历史会话，使用不同的 `worker_session_id`，
不得读取主对话、另一 Worker 的对话或契约未声明的产物。每个 Worker 在当前
阶段只创建一次、等待一次、关闭一次，阶段结束后销毁上下文。

Produce Executor 和 Deliver Executor 是 Python 程序执行器，不创建会话、不加载
模型 Skill、不接受 `worker_session_id`，两阶段的 `model_calls` 都必须为 `0`。

## Normal Content Mode

正常内容任务禁止进入开发模式。除非用户明确要求开发、调试或测试插件，否则：

- 不得扫描完整仓库。
- 不得创建开发计划。
- 不得运行插件测试。
- 不得解释插件架构。
- 不得读取运行时代码。
- 不得检查模板、清单或与本次内容无关的文件。
- 不得进行 Prompt 二次复审、评分、改写或新增模型调用。
- 不得打开 HTML 或验图。
- 不得运行浏览器、调用 Playwright。
- 不得截图验收。
- 不得为证明流程正确而重复读取产物、重复校验或执行无关自检。

商品页研究、产品身份锁定、来源证据和真实参考图属于内容生产本身，不属于开发式
检查，必须在 Research Worker 内完成。Compose 完成后只做一次程序校验后立即展示 Prompt，
不增加人工或模型复审阶段。

## First Image Setup

首次生图设置必须列出当前可用的：

- 生图渠道
- 具体模型
- 是否支持参考图
- 默认尺寸
- 配置状态

运行：

```bash
python3 ../../scripts/生图工具/configure_provider.py --list
```

用户选择后保存默认渠道和模型。后续任务直接复用已保存配置，只有用户明确要求
时才切换。每次内容任务仍需展示本次最终 Prompt 包并等待批准。

## Runtime Creation

主控先创建 `task.json` 和外部 `run_dir`：

```bash
python3 ../../scripts/工作流工具/workflow_runtime.py create \
  --plugin-root "../.." \
  --delivery-root "<USER_OUTPUT_DIRECTORY>" \
  --task-file "<TEMP_TASK_JSON>"
```

所有结构化产物都包含 `schema_version: 1` 和 `run_id`：

- `task.json`
- `material.json`
- `evidence.json`
- `content.json`
- `visual.json`
- `approval.json`
- `generation.json`
- `delivery.json`
- `runtime.json`

字段、ID、Worker 白名单、模型调用次数和下一阶段可读取字段以
`../../assets/workflow-contracts.json` 为准。

## Research Worker

Research Worker 在一次模型调用中同时加载
`product-material-intake` 和 `xhs-research-strategy`。它只读取 `task.json`
中契约声明的字段，以及其中声明的
产品链接、图片和素材；只输出 `material.json` 和 `evidence.json`。

同一次调用内先研究商品页并锁定准确产品身份，再提取来源证据、卖点和选题：

- 记录页面标题、品牌、名称、型号、变体、类别、识别词、未解决字段、锁定词和
  禁止替换项。
- 无法确认的字段进入 `unresolved_fields`，后续阶段不得自行补全。
- 每个卖点建立“产品特征 -> 用户问题 -> 用户收益 -> 使用场景”四段链。
- 使用 `source_claim_ids` 连接卖点、`claims` 与 `sources`。
- 搜集产品主体页需要的真实产品参考图和明确支持的视角。

Research Worker 的 `model_calls` 必须恰好为 `1`。两个产物写入并通过 Schema
校验后，由运行时连续执行：

```text
created -> prepared
prepared -> evidenced
```

## Compose Worker

Compose Worker 只加载 `xhs-copy-storyboard` 和 `xhs-visual-planner`，只读取
`material.json` 和 `evidence.json`，只输出 `content.json` 和 `visual.json`。

Compose Worker 必须在同一次 compose 模型调用中生成：

- 完整小红书文案
- 至少 5 个候选标题
- 轮播结构
- 全部最终生图 Prompt
- 每页参考图对应关系

`stage-finish` 必须记录 `model_calls: 1`。缺少 `evidence.json` 禁止进入 compose。
完成两个产物并通过校验后执行：

```text
evidenced -> composed
```

`content.json.post` 必须是可直接发布的最终正文字符串，不能把 `briefing`、
`claim`、追溯 ID 或其他内部结构化字段当作成稿。追溯信息只能保存在专用 ID
字段中，不能混入候选标题、正文或轮播文案。Compose 必须把事实转成用户场景、
把特征转成具体收益、把限制转成自然建议；不得写成产品说明书，不得虚构实测，
也不得使用机械对照、强行升华或重复结论。`locked_terms` 只约束提及时不能写错，
不要求逐项进入成稿。

## Humanize Worker

Humanize Worker 只加载 `$xhs-humanize-review`（Skill 名为
`xhs-humanize-review`），只读取 `material.json`、`evidence.json` 和 `content.json`，
只覆写 `content.json`。它不读取或修改 `visual.json`，只改可见文字，不改变 JSON
结构、ID、数组顺序或既有段落格式。

这是一次文本编辑阶段，不是 Prompt 二次复审。它允许在标题、正文和轮播文案中
使用账号口吻、虚构生活场景、个人体验或引流表达；不生成检测分数、报告产物、重试
或第二次改写。`stage-finish` 必须记录 `model_calls: 1`。

Compose 完成后先执行：

```bash
python3 ../../scripts/工作流工具/workflow_runtime.py compose-finish \
  --run-dir "<RUN_DIR>" \
  --metrics-file "<COMPOSE_METRICS_JSON>"
```

主控随后以新的无历史会话启动并等待 Humanize Worker，写回 `content.json` 后执行：

```bash
python3 ../../scripts/工作流工具/workflow_runtime.py humanize-present \
  --run-dir "<RUN_DIR>" \
  --metrics-file "<HUMANIZE_METRICS_JSON>"
```

状态依次为：

```text
composed -> humanizing
humanizing -> humanized
humanized -> prompt_pending_approval
```

## Prompt Display And Approval

主控只在 Humanize Worker 写回 `content.json` 并完成一次程序校验后展示 Prompt 包，
同时写入待批准状态。Prompt 包始终来自未被 Humanize Worker 读取或修改的
`visual.json`。

展示 Prompt 包必须包含：

- `style_anchor`
- 每页 `page_id`
- 每页完整 Prompt
- 每页 `reference_image_ids`
- 每页 `reference_image_paths`
- 每页承担的信息任务

运行时对上述稳定内容计算 SHA-256，并写入 `approval.json`。用户批准时运行：

```bash
python3 ../../scripts/工作流工具/workflow_runtime.py approval-approve \
  --run-dir "<RUN_DIR>" \
  --approved-by "<APPROVER>"
python3 ../../scripts/工作流工具/workflow_runtime.py approval-validate --run-dir "<RUN_DIR>"
python3 ../../scripts/工作流工具/workflow_runtime.py approval-status --run-dir "<RUN_DIR>"
```

状态顺序为：

```text
humanized -> prompt_pending_approval
prompt_pending_approval -> prompt_approved
```

批准哈希必须与当前 Prompt 包一致。Prompt、页面或参考图映射发生变化时，批准
失效，状态回到 `prompt_pending_approval`，并生成新的 Prompt 哈希。

## Produce Executor

验证有效批准后先执行：

```text
prompt_approved -> producing
```

Produce Executor 是 Python 执行器，只读取 `visual.json` 和 `approval.json`、
已保存的生图渠道配置及 `visual.json` 声明的参考图，只输出 `generation.json`
和生成图片。它不创建 Worker、不加载模型上下文，`worker_session_id` 为 `null`，
`model_calls: 0`。

执行：

```bash
python3 ../../scripts/生图工具/batch_generate.py \
  --batch-file "<TEMP_BATCH_JSON>" \
  --output-root "<USER_OUTPUT_DIRECTORY>" \
  --run-dir "<RUN_DIR>"
```

全部 Prompt 一次并发提交，每页只发起一次初始请求。每个请求按以下状态记录：

```text
request_started -> response_received -> download_pending -> complete
```

异常状态为 `failed` 或 `uncertain`。`uncertain` 禁止自动重新请求，必须先在渠道
后台对账；人工确认重发时使用新的 `request_id` 和递增的 `attempt`，并保留原请求
记录。不自动重试，不切换模型，不切换渠道。

## Deliver Executor

Deliver Executor 是 Python 执行器，只读取 `content.json`、`visual.json` 和 `generation.json`，
默认输出图片内嵌的小红书内容 HTML、独立运行日志和内部 `delivery.json`。
它不创建 Worker、不加载模型上下文，`worker_session_id` 为 `null`，
`model_calls: 0`。

只有全部计划图片的 `request_status` 都为 `complete` 时才可启动 Deliver
Executor。执行：

```bash
python3 ../../scripts/HTML生成工具/generate_delivery.py \
  "<TEMP_INPUT_JSON>" \
  "<OUTPUT_HTML>" \
  --run-dir "<RUN_DIR>" \
  --embed-images
```

`--embed-images` 是默认行为，命令中仍显式写出以明确单文件交付。只有用户明确
传入 `--run-log` 时按兼容参数接受；无论是否传入，都必须生成独立运行日志。

图片缺失、失败或状态不确定时禁止进入交付。生成命令完成后依次执行：

```text
producing -> delivered
delivered -> completed
```

`delivery.json` 必须包含 `html_path`、`runtime_log_path`、`generation_status` 和
`completed_at`。`runtime_log_path` 必须指向真实文件；HTML 或运行日志不存在时
禁止进入 `completed`。

## State Machine

完整代码级状态机：

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

运行时必须阻止缺少 `evidence.json` 进入 `composed`、缺少有效批准进入
`producing`、图片缺失进入 `delivered`、HTML 或运行日志不存在进入
`completed`，并阻止跳过阶段、重复迁移和逆向迁移。

## Product Fidelity And Traceability

产品名称、型号、规格和变体一旦在文案、Prompt、参考图映射或 HTML 中出现，
必须与已锁定身份一致。官方页面标题和货号默认只作为内部证据，不为满足校验而
强塞进成稿；`unresolved_fields` 不得自行补全，`forbidden_replacements` 不得
出现在用户可见文案中。每个产品主体页必须记录 `product_subject`、`product_view`、
`reference_image_ids` 和 `reference_image_paths`，并使用真实产品参考图。

所有页面共享同一个 `style_anchor`。相邻产品页面必须在 `page_role`、
`shot_type`、`subject_position`、`subject_scale`、`background_scene` 或
`text_zone` 中至少变化一项。

`content.json` 使用 `post_selling_point_ids` 和 `post_claim_ids` 追溯正文；每个
轮播页面使用 `selling_point_ids` 和 `claim_ids`。所有 `must_use` 卖点必须同时
进入正文追溯字段和至少一个轮播页面。

## Runtime Accounting

正常内容任务使用已有运行数据生成一份独立运行日志，汇总总耗时、阶段耗时、Token、
费用、图片成功率、失败或不确定请求，以及模型和渠道。不得为了补齐日志数据增加
模型调用、素材搜索、工具调用、重复读取或额外检查；宿主或渠道未返回的数据明确
标为未返回，不估算。整个正常内容任务的内容模型调用总数固定为 `2`。

## Final Delivery

正常内容任务只向用户交付图片已内嵌的小红书内容 HTML 和独立运行日志。
`delivery.json`、结构化中间产物、测试报告、调试文件和内部资料不得作为用户交付物。

两个文件生成后立即停止，只返回以下最终回复，不补充测试结果、复审结论、验图结果、
截图或执行过程：

```markdown
已按“内容直出”规则完成，不再执行测试、复审、验图或截图。

- [小红书图文成品 HTML](<HTML_PATH>)
- [独立运行日志](<RUNTIME_LOG_PATH>)
```

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/轮播叙事.md`
