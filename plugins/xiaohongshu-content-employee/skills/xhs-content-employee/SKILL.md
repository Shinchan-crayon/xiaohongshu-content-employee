---
name: xhs-content-employee
description: 作为唯一公开入口，把产品材料快速编排为有来源、参考图生图和 HTML 交付的小红书内容包；首次使用先完成图片能力设置，后续自动复用。
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

## Bounded Parallel Orchestration

主 Agent 是唯一流程协调者和共享状态写入者。运行环境提供子 Agent 工具，且任务包含至少两个互不依赖的调研子任务时，使用一次有界 fan-out / fan-in：

1. 完成首次图片设置、输入归一化和知识偏好加载。
2. 主 Agent 创建同一份只读任务快照，一次并行分派最多三个子 Agent：
   - 产品事实与官网参考图；
   - 目标人群、痛点和使用场景；
   - 内容角度、平台表达和视觉方向。
3. 每个子 Agent 只返回结构化结果：`task_id`、`facts`、`sources`、`assumptions`、`conflicts`、`recommendations`。
4. 主 Agent 等待本轮任务结束，只合并一次；发现事实冲突时按事实来源规则处理，然后统一写入材料记录、来源台账和 `workflow-state.json`。
5. 合并后继续顺序执行 `compose -> produce -> deliver`。生图继续使用现有整批并发，不为每张图片创建子 Agent。

子 Agent 不得修改 `workflow-state.json`，不得写交付目录，不得发起付费生图，不得生成 HTML，也不得再次创建子 Agent。

以下情况直接沿用顺序执行，不产生额外等待：

- 运行环境没有子 Agent 工具；
- 只有一个有效来源或一个简单调研任务；
- 子任务存在前后依赖，或共享可变文件；
- 本轮分派失败。

单个子 Agent 失败时，主 Agent 只补做缺失子任务，不重新运行成功任务；整轮分派失败时立即降级为原有顺序流程。每次内容任务最多进行一轮调研分派，避免启动成本抵消速度收益。

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
```

`material_source_mode` 为空时，有链接就采用 `user_links`，没有链接就采用 `internal_search`。

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

每次阶段变化都更新 `workflow-state.json`，并符合 `../../assets/workflow-state-schema.json`。

- `checkpoint.sequence` 单调递增。
- `transition_log` 记录前进、阻断、恢复和回退。
- `next_action` 指明下一责任人。
- `provider_model_selection` 与 `generation_batch_approval` 是两条独立确认。
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
- 输入归一化后判断是否满足有界并行条件；满足时创建只读任务快照并启动唯一一轮调研分派。
- 锁定核心事实、官方产品参考图、不可改写项和目标受众。
- 只有核心事实缺失、材料冲突、用户要求选题确认或首次设置未完成时才等待用户。

### 2. evidence

- 调用 `$xhs-research-strategy`。`user_links` 只读用户链接；`internal_search` 执行内部搜索。已启动调研分派时，由主 Agent 在此等待并合并结构化结果。
- 自动生成来源台账并一次性锁定事实边界，不单独请求素材确认，不在后续阶段重复审核。
- 核心事实没有来源或来源冲突时才阻断。
- 证据就绪后直接进入 `compose`。

### 3. compose

- 自动选择最合适的选题，除非用户明确要求确认。
- 调用 `$xhs-copy-storyboard` 生成标题、正文、标签和最小必要页数的轮播。
- 调用 `$xhs-visual-planner` 生成每页短 Prompt。
- 首图 Prompt 前置“参考图片主体为{品牌和产品}，参考官网图片，其余构图和场景自由发挥”，并绑定官网参考图；第二页起不再写参考图约束。
- 构图、场景、光线、道具和视觉创意交给图片模型自由发挥。
- 同一批次内每条 Prompt 必须不同；100% 完全相同的 Prompt 不得进入付费生图。
- AI 模式只给首图绑定 `reference_image_path` 和 `reference_image_sha256`，第二页起两个字段必须为空。
- 对完整语义内容计算小写 SHA-256 `content_digest`。本流程不运行文案风险、质量、自然化或 AI 特征检测。

### 4. produce

- 发起付费请求前展示整批页数、渠道、模型、尺寸、质量和批次摘要，记录一次 `generation_batch_approval`。
- 批准后调用 `$xhs-approved-image-generator`，一次并发提交全部待生成页面。
- 每页失败后只重试该页，最多三次；成功页面不重试。
- 三次仍失败时停止该页并向用户返回准确页码和最后错误。
- 模型原图直接作为成品，不运行代码加字、裁切、抠图、产品叠加或图片合成。
- 不执行生成后图片相似度自检、删除或重生成。
- 明显但轻微的伪品牌文字或局部乱码不阻断交付。

### 5. deliver

- 调用 `$xhs-html-delivery` 生成 `delivery.json` 和 HTML；生成脚本自带的本地输入校验属于生成动作，不得在生成后重复运行。
- HTML 写入后只做可用性门禁：HTML 文件存在且非空，交付页引用的图片文件存在。
- 可用性门禁通过后，必须立即向用户发送绝对 HTML 路径，并明确说明“HTML 已生成，可先查看；我只做一次轻量收尾检查。”不得等到状态、Schema、敏感信息或 Git 检查结束后再交付。
- 路径发出后最多执行一次轻量收尾检查，只核对交付路径与 `workflow-state.json` 记录一致；随后立即进入 `completed`。
- 不运行内容审核，不请求内容确认。
- HTML 为空或引用图片缺失时留在 `deliver / BLOCKED` 修复；已经发出的 HTML 不因非阻断警告被撤回或延迟。

### 6. completed

- 轻量收尾检查结束后写入 `COMPLETED` 并立即停止执行，不继续做发布、仓库或环境检查。

## Delivery-First Guardrails

- 禁止在内容交付任务中打开浏览器、调用 Playwright 或执行视觉验收，除非用户明确要求测试页面显示效果。
- 禁止为了交付后检查安装 Python、Node 或浏览器依赖。
- 可选校验器缺失时记录为 `skipped`，不得寻找替代校验器、补装依赖或启动降级验证链。
- 禁止在 HTML 路径发出后重复执行 Schema 校验、敏感信息扫描、资源扫描或 Git 检查。
- 发布验证、commit、push、Marketplace 同步和插件安装只在用户明确要求时执行，不属于内容交付流程。
- 任何轻量收尾警告都不得阻止用户先查看已生成且可用的 HTML。

## Confirmation Budget

只允许以下阻塞式确认：

- 首次图片模式，以及 AI 模式的渠道与模型设置。
- 核心事实缺失或冲突。
- 用户明确要求的选题确认。
- 付费批量生图的一次批准。

来源列表、自动选题、图片规划、Prompt 和 HTML 不单独等待确认。

付费请求前的批次授权、Prompt 完整性和参考图哈希校验属于一次性执行门禁，不是内容自检；通过后不在每张图片上重复校验。`deliver` 只允许一次可用性门禁和路径发出后最多一次轻量收尾检查，不执行其他中间或生成后自检。

## Recovery Rules

- 恢复时先验证状态文件。
- 图片批次恢复时跳过 `complete` 页面。
- `failed` 页面仅在总尝试次数少于三次时继续。
- Prompt、渠道、模型、尺寸、质量或参考图哈希变化会使旧批次批准失效。
- 图片渠道不可用时，只有用户明确选择后才能切换模式或渠道。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/小红书内容规范/个性化学习规则.md`
