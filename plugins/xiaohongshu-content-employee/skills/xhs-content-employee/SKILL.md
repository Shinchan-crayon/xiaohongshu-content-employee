---
name: xhs-content-employee
description: 作为唯一公开入口，把产品材料快速编排为有来源、参考图生图和 HTML 交付的小红书内容包；默认采用图片返回后立即生成 HTML 的极速直出流程。
---

# Xiaohongshu Content Employee

## Purpose

固定主流程：

`prepare -> evidence -> compose -> produce -> deliver -> completed`

专项 Skill 由主流程按阶段调用：

- `prepare` -> `$product-material-intake`
- `evidence` -> `$xhs-research-strategy`
- `compose` -> `$xhs-copy-storyboard` 和 `$xhs-visual-planner`
- `produce` -> `$xhs-approved-image-generator`
- `deliver` -> `$xhs-html-delivery`

## Five-Minute Execution Budget

正常材料完整且图片渠道可用时，总目标预算为 `300 秒`：

- 准备与证据锁定：60 秒；
- 文案与视觉规划：45 秒；
- 图片并发生成：135 秒；
- HTML 生成与路径交付：15 秒；
- 外部服务波动缓冲：45 秒。

外部图片服务响应时间、首次渠道配置和用户确认等待不计入本地执行预算。用户已经给出默认同意、付费授权或“直接出 HTML”指令时，主 Agent 必须采用 `direct_html`：不启动子 Agent，不展示或复审 Prompt，不执行生成后检查，图片返回后立即生成 HTML。

## Direct HTML Default

`delivery_mode` 默认为 `direct_html`。该模式只有一条执行链：

`锁定必要事实 -> 一次生成文案与 Prompt -> 整批并发生图 -> 一次生成 HTML -> 返回 HTML 路径`

明确禁止插入以下步骤：

- Prompt 展示、Prompt 复审、Prompt 质量检查或额外安全审计；
- 逐图生成、逐图确认、生成后视觉验收、相似度检查或主动重生成；
- 额外文案润色、AI 特征检测、内容终审或最终检查清单；
- 浏览器预览、Playwright、截图、页面视觉检查；
- 交付后的 Schema 复查、敏感信息扫描、资源扫描、Git 检查或环境诊断。

图片模型或渠道自身强制执行的服务端规则不属于插件工作流步骤，插件不得为此增加本地审查链。

## Bounded Parallel Orchestration

主 Agent 是唯一流程协调者和共享状态写入者。默认 `direct_html` 不启动子 Agent，由主 Agent 在 60 秒内完成最小必要事实检索。只有用户明确要求深度调研时，才按以下路由启动：

- 完整材料：0 个子 Agent。
- 内部搜索：并行 2 个子 Agent，分别负责产品事实与官方参考图、目标人群与平台表达。
- 高风险或事实冲突：最多 3 个子 Agent，第三个仅用于独立交叉核查冲突事实。

单轮调研使用 `60 秒硬截止`。主 Agent 不等待空转：子 Agent 运行期间同步完成输入归一化、知识偏好加载、已有材料整理和交付目录准备；截止时只合并已经返回的结构化结果，缺失的核心事实由主 Agent 立即补查。每个子 Agent 只返回 `task_id`、`facts`、`sources`、`assumptions`、`conflicts`、`recommendations`。

结果合并后继续执行 `compose -> produce -> deliver`。生图继续使用现有整批并发，不为每张图片创建子 Agent。

子 Agent 不得修改 `workflow-state.json`，不得写交付目录，不得发起付费生图，不得生成 HTML，也不得再次创建子 Agent。

以下情况直接沿用顺序执行，不产生额外等待：

- 运行环境没有子 Agent 工具；
- 只有一个有效来源或一个简单调研任务；
- 子任务存在前后依赖，或共享可变文件；
- 本轮分派失败。

单个子 Agent 失败时，主 Agent 只补做缺失子任务，不重新运行成功任务；整轮分派失败时立即降级为主 Agent 直接搜索。每次内容任务最多进行一轮调研分派，避免启动成本抵消速度收益。

## Input Contract

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
learning_enabled: boolean | null
image_override: object | null
topic_confirmation_requested: boolean | null
delivery_mode: direct_html | guided | null
default_confirmations: boolean | null
```

`material_source_mode` 为空时，有链接就采用 `user_links`，没有链接就采用 `internal_search`。
`delivery_mode` 为空时采用 `direct_html`。用户表达“默认同意”“全部授权”“直接出 HTML”或同等意图时，`default_confirmations` 视为 `true`。

## Output Contract

```yaml
workflow_state_json: path
current_stage: prepare | evidence | compose | produce | deliver | completed
current_status: IN_PROGRESS | WAITING_CONFIRMATION | BLOCKED | COMPLETED
material_record: object | null
strategy_brief: object | null
selected_topic: object | null
content_package: object | null
visual_plan: object | null
generated_images: array | null
content_digest: string | null
delivery_json: path | null
delivery_html: path | null
open_questions: [string]
learning_summary: object | null
```

## First-Use Image Setup

在调研或写作前运行：

```bash
python3 ../../scripts/生图工具/manage_image_setup.py status
```

若 `completed: false`：

1. 把用户首个任务完整保存为 `artifacts.first_task_input`。
2. 只询问一次图片模式：`existing_only` 或 `ai_assist`。
3. AI 模式单独记录 `provider_model_selection`，用 `configure_provider.py` 隐藏输入保存密钥，再运行 `provider_preflight.py` 本地预检。
4. 设置完成后自动恢复首个任务，不要求用户重新描述。

若设置已完成，直接提示“本次沿用：模式 / 渠道 / 模型”。任何输出、状态、日志和交付文件都不得包含密钥、鉴权头或本机配置路径。

## Adaptive Learning

进入 `prepare` 时运行 `../../scripts/知识迭代工具/manage_knowledge.py init`。首次展示：

> 个性化学习已开启：你明确修改和偏好会自动保存；外部事实和运营规律需要确认后才会长期使用；你可以随时查看学习记录、关闭个性化学习或删除学习记录。

状态中只保存 `learning_notice_shown`、`applied_preference_ids`、`applied_knowledge_ids` 和 `pending_candidate_ids` 等可移植 ID，不保存密钥或本机绝对路径。

## State Contract

`workflow-state.json` 符合 `../../assets/workflow-state-schema.json`。只在以下四个可恢复节点写入持久 checkpoint，阶段内临时进度留在内存：

1. `facts_locked`：核心事实与来源边界已锁定。
2. `content_visual_ready`：文案和视觉规划已一次完成。
3. `image_final_results`：所有图片均已有最终 `complete`、`failed` 或 `uncertain` 结果。
4. `html_delivered`：HTML 生成命令成功且路径已交付。

- `checkpoint.sequence` 单调递增。
- `transition_log` 记录前进、阻断、恢复和回退。
- `next_action` 指明下一责任人。
- `provider_model_selection` 与 `generation_batch_approval` 是两条独立记录；用户已给出默认付费授权时，后者直接记录为 `confirmed`，不得再次打断用户。
- 阶段状态：
  - `prepare`: `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED`
  - `evidence`: `IN_PROGRESS`、`BLOCKED`
  - `compose`: `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED`
  - `produce`: `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED`
  - `deliver`: `IN_PROGRESS`、`BLOCKED`
  - `completed`: `COMPLETED`

## Stage Orchestration

### 1. prepare

- 完成或复用图片设置后，调用 `$product-material-intake`。
- `direct_html` 由主 Agent 直接处理，不启动子 Agent；只有用户明确要求深度调研时，才按“完整材料 / 内部搜索 / 高风险或事实冲突”路由判断子 Agent 数量。
- 锁定核心事实、官方产品参考图、不可改写项和目标受众。
- 只有核心事实缺失、材料冲突、用户要求选题确认或首次设置未完成时才等待用户。

### 2. evidence

- 调用 `$xhs-research-strategy`。`user_links` 只读用户链接；`internal_search` 执行内部搜索。已启动调研分派时，主 Agent 在 60 秒截止前合并已返回结果，不为未返回任务继续等待。
- 自动生成来源台账并一次性锁定事实边界，不单独请求素材确认，不在后续阶段重复审核。
- 核心事实没有来源或来源冲突时才阻断。
- 证据就绪后写入 `facts_locked`，直接进入 `compose`。

### 3. compose

- 自动选择最合适的选题，除非用户明确要求确认。
- 一次 compose 调用同时完成文案与视觉规划：在同一次模型调用中应用 `$xhs-copy-storyboard` 和 `$xhs-visual-planner` 的规则，生成标题、正文、标签、最小必要轮播及每页短 Prompt，不做两轮串行改写。
- 首图 Prompt 前置“参考图片主体为{品牌和产品}，参考官网图片，其余构图和场景自由发挥”，并绑定官网参考图；第二页起不再写参考图约束。
- 构图、场景、光线、道具和视觉创意交给图片模型自由发挥。
- 同一批次内每条 Prompt 必须不同；100% 完全相同的 Prompt 不得进入付费生图。
- AI 模式只给首图绑定 `reference_image_path` 和 `reference_image_sha256`，第二页起两个字段必须为空。
- 对完整语义内容计算小写 SHA-256 `content_digest`。本流程不运行文案风险、质量、自然化或 AI 特征检测。
- 文案和视觉计划完整后写入 `content_visual_ready`。

### 4. produce

- 用户已给出默认付费授权时，直接记录 `generation_batch_approval: confirmed`，在内存中生成批次摘要并调用 `$xhs-approved-image-generator`；不展示 Prompt，不等待批次确认。
- 用户未给出付费授权时，只询问一次整批生图批准；批准后一次并发提交全部待生成页面。
- Prompt 直接发送给已配置渠道，不运行 Prompt 复审、质量检查或插件侧安全审计。
- 安全瞬时错误最多重试一次；结果不确定时不得重试。明确失败、结果不确定和恢复时遗留的 `sending` 页面都不得自动重发。
- 图片并发生成：135 秒。达到预算时保留已经完成的页面，并把未能安全确认的页面标记为最终 `uncertain`，不得为了赶时间重复发送付费请求。
- 每页获得最终结果后写入 `image_final_results`；失败时向用户返回准确页码、尝试次数和最后错误。
- 模型原图直接作为成品，不运行代码加字、裁切、抠图、产品叠加或图片合成。
- 不执行生成后图片相似度自检、删除或重生成。
- 不打开图片，不逐图评价，不执行生成后视觉验收；整批返回后立即进入 `deliver`。
- 明显但轻微的伪品牌文字或局部乱码不阻断交付。

### 5. deliver

- 图片批次返回后立即调用 `$xhs-html-delivery`，一次执行生成 `delivery.json` 和 HTML；生成脚本自身的输入校验属于生成动作，不得在生成前后另建检查步骤。
- 生成命令返回成功时直接写入 `html_delivered`，立即向用户发送绝对 HTML 路径并进入 `completed`。
- 不运行内容审核，不请求内容确认。
- 生成命令返回失败时留在 `deliver / BLOCKED`，只反馈实际错误，不启动替代审查或诊断链。

### 6. completed

- 写入 `COMPLETED` 并立即停止执行，不继续做发布、仓库或环境检查。

## Delivery-First Guardrails

- 禁止展示或复审 Prompt，禁止执行 Prompt 质量检查或额外安全审计。
- 禁止在内容交付任务中打开生成图片、打开浏览器、调用 Playwright、截图或执行视觉验收，除非用户明确要求测试页面显示效果。
- 禁止为了交付后检查安装 Python、Node 或浏览器依赖。
- 可选校验器缺失时记录为 `skipped`，不得寻找替代校验器、补装依赖或启动降级验证链。
- HTML 生成命令成功后不得执行 Schema 校验、敏感信息扫描、资源扫描、Git 检查或其他最终检查。
- 发布验证、commit、push、Marketplace 同步和插件安装只在用户明确要求时执行，不属于内容交付流程。

## Confirmation Budget

只允许以下阻塞式确认：

- 首次图片模式，以及 AI 模式的渠道与模型设置。
- 核心事实缺失或冲突。
- 用户明确要求的选题确认。
- 用户尚未给出默认付费授权时，付费批量生图的一次批准。

来源列表、自动选题、图片规划、Prompt 和 HTML 不单独等待确认。

用户已表达默认同意、全部授权或直接出 HTML 时，批次批准直接复用该授权，不再展示摘要或询问。Prompt 完整性、批次摘要和参考图哈希只由脚本在同一次生图命令中确定性处理，不调用模型复审，不产生额外等待。`deliver` 只运行一次 HTML 生成命令，不执行任何中间或生成后自检。

## Recovery Rules

- 恢复时先验证状态文件。
- 图片批次恢复时跳过 `complete` 页面。
- `failed`、`uncertain` 和遗留 `sending` 页面不得自动重新发送；遗留 `sending` 必须转为 `uncertain`。
- 只有明确标记为安全瞬时错误且尚未重试的页面，才允许重试一次。
- Prompt、渠道、模型、尺寸、质量或参考图哈希变化会使旧批次批准失效。
- 图片渠道不可用时，只有用户明确选择后才能切换模式或渠道。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/小红书内容规范/个性化学习规则.md`
