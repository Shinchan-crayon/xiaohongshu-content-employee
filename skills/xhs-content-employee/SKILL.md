---
name: xhs-content-employee
description: 作为唯一公开入口，编排产品素材接收、调研、选题确认、文案、审核、可选视觉制作和 HTML 交付的小红书内容员工主控 Skill。
---

# Xiaohongshu Content Employee

## Purpose

把客户材料转成有证据边界、有人工作业点、可恢复的小红书内容包。不要直接跳到写正文。

## Public Entry Contract

`xhs-content-employee` 是整个包的`唯一公开入口`。其职责是维护主流程状态、调用专项 Skill、在需要时请求人工确认，并在交付前完成结构校验。

以下七个专项 Skill 由主流程按阶段调用。它们不是主流程入口，但仍可由用户手动指定：

- `intake` -> `$product-material-intake`
- `research` -> `$xhs-research-strategy`
- `drafting` -> `$xhs-copy-storyboard`
- `review` -> `$xhs-humanize-review`
- `visuals / plan` -> `$xhs-visual-planner`
- `visuals / generate` -> `$xhs-approved-image-generator`
- `delivery` -> `$xhs-html-delivery`

`angle_confirmation` 和 `completed` 由主控 Skill 自身负责，分别用于人工确认选题方向和封存最终状态。

## Input Contract

接收一个对象：

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
detector_feedback: object | null
```

`material_source_mode` 是素材获取方式。若为空，主控必须先展示以下两个方案并等待用户选择，不得自行推断：

- 方案 1：用户提供素材链接 -> `user_links`
- 方案 2：插件内部搜索 -> `internal_search`

`references` 保留用于本地文件、历史参考内容和兼容已有调用；用户选择 `user_links` 时，文章或产品网页应放入 `material_links`。

## Output Contract

输出：

```yaml
workflow_state_json: path
current_stage: intake | research | angle_confirmation | drafting | review | visuals | delivery | completed
current_status: IN_PROGRESS | WAITING_CONFIRMATION | BLOCKED | COMPLETED
material_record: object | null
strategy_brief: object | null
selected_topic: object | null
content_package: object | null
review_result: object | null
visual_plan: object | null
generated_images: array | null
delivery_json: path | null
delivery_html: path | null
material_source_selection: user_links | internal_search | null
open_questions: [string]
```

## State File Contract

主控每次进入、退出或回退阶段时，都要更新一个便携的 `workflow-state.json`。该文件必须符合 `../../assets/workflow-state-schema.json`，至少包含以下字段：

- `workflow_id`: 当前任务的稳定标识。
- `state_version`: 当前状态协议版本。
- `updated_at`: 最近一次状态写入时间。
- `stage`: 当前阶段，必须是 `intake`、`research`、`angle_confirmation`、`drafting`、`review`、`visuals`、`delivery` 或 `completed`。
- `status`: 当前状态，必须是 `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED` 或 `COMPLETED`。
- `artifacts`: 当前已经产出的材料记录、调研摘要、已选角度、文案包、审核结果、交付文件等。
- `blockers`: 任何阻断主流程的问题，包括缺失事实、事实冲突、审核阻断、文件缺失或交付校验失败。
- `confirmations`: 需要人工确认或已完成确认的事项。
- `checkpoint`: 当前可恢复检查点，至少包含 `sequence`、`last_valid_stage`、`resume_from` 和 `artifact_refs`，用于保留最近一个有效阶段和已有产物引用。
- `transition_log`: 阶段迁移历史数组，至少记录 `from`、`to`、`status`、`reason`、`sequence` 等字段，用于追踪前进、阻断、回退与恢复。
- `next_action`: 下一步由谁完成、做什么、依赖什么。

素材获取方式必须写入名为 `material_source_selection` 的确认记录或 artifact，并在恢复执行时继续沿用。用户明确要求切换方案时，才允许更新该记录并重新进入 `intake`。

状态组合必须保持简单且可恢复，只允许以下搭配：

- `intake`: `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED`
- `research`: `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED`
- `angle_confirmation`: `WAITING_CONFIRMATION`
- `drafting`: `IN_PROGRESS`、`BLOCKED`
- `review`: `IN_PROGRESS`、`BLOCKED`
- `visuals`: `IN_PROGRESS`、`WAITING_CONFIRMATION`、`BLOCKED`
- `delivery`: `IN_PROGRESS`、`BLOCKED`
- `completed`: `COMPLETED`

## Stage Orchestration

1. `intake`
   - 启动时写入 `stage: intake`、`status: IN_PROGRESS`。
   - 若 `material_source_mode` 为空，向用户展示“方案 1：用户提供素材链接”和“方案 2：插件内部搜索”，写入待确认的 `material_source_selection`，并切换为 `WAITING_CONFIRMATION`。
   - 用户选择后，把 `user_links` 或 `internal_search` 写入确认记录和恢复检查点；未确认前不得进入 `research`。
   - 调用 `$product-material-intake`，锁定事实、禁止改写项和缺失材料。
   - `user_links` 路径要求至少有一个可读取的 `material_links`；缺失时保持 `WAITING_CONFIRMATION` 并请用户补充链接。
   - `internal_search` 路径允许 `material_links` 为空，由后续 `$xhs-research-strategy` 执行搜索。
   - 若核心事实缺失、图片与文案冲突或存在高风险未知项，写入确认项并切换为 `WAITING_CONFIRMATION`。
   - 若素材本身无法支撑内容目标，记录阻断原因并切换为 `BLOCKED`。
   - 通过后转入 `research`。

2. `research`
   - 调用 `$xhs-research-strategy`，并传入已确认的 `material_source_mode`。
   - `user_links` 路径只读取用户提供的 `material_links` 和 `references`，不得自行扩展内部搜索。
   - `internal_search` 路径由 `$xhs-research-strategy` 根据产品、内容目标和目标用户构造查询并搜索文章或产品素材。
   - 若用户选择内部搜索，但网络或搜索能力不可用、或没有找到可验证来源，则记录限制并回退到 `intake / WAITING_CONFIRMATION`，让用户选择重试或改为提供链接；不得用无来源内容补齐。
   - 搜集完成后保存 `source_review_table`，向用户展示来源、链接和核心信息，写入 `source_confirmation`，并切换为 `research / WAITING_CONFIRMATION`。
   - 用户明确回复“确认”或“继续”后，将 `source_confirmation` 标记为已确认并恢复 `research / IN_PROGRESS`。用户要求补充或删除来源时，更新台账并重新等待确认。
   - 来源未确认前不得生成选题或进入 `angle_confirmation`。来源确认只代表素材覆盖得到认可，不代表其中全部声称自动成为事实。
   - 来源确认后只对数字、归属、因果、比较、功能、效果、认证和引用等高风险事实建立一张 `fact_check`。
   - `fact_check` 为 `BLOCKED` 时保持 `research / BLOCKED`，删除、修正或补充来源后再继续；通过后才生成选题。
   - 若新发现事实冲突，立即回退到 `intake`，保留冲突记录，不允许在当前阶段绕过。
   - 完成后转入 `angle_confirmation`。

3. `angle_confirmation`
   - 主控向用户展示 2-5 个选题及对应证据标签。
   - 当前阶段固定写入 `status: WAITING_CONFIRMATION`，直到用户明确确认一个角度，或要求补充材料后再继续。
   - 若用户否决全部角度，则根据原因回到 `research` 或 `intake`。
   - 一旦确认选题，写入确认结果并转入 `drafting`。

4. `drafting`
   - 调用 `$xhs-copy-storyboard` 生成标题、正文、封面、轮播脚本、图片使用方案和 `claim_map`。
   - 文案包必须包含 `structure_choice` 与 `voice_fingerprint`，不得套用唯一固定正文公式。
   - 若生成内容引用了未确认事实，写入阻断项并回退到 `angle_confirmation` 或 `intake`，不能直接润色掩盖。
   - 完成后转入 `review`。

5. `review`
   - 调用 `$xhs-humanize-review`，传入已有 `detector_feedback`，严格遵守其既定审核顺序。
   - 若返回 `full_rewrite_required: true`，必须保留 `rewrite_proof` 并回退到 `drafting` 做结构性重写，不能在审核阶段只替换词语后直接通过。
   - 若外部检测反馈显示 AI 特征达到或超过 50%，重写后仍停留在 `review / BLOCKED`，等待复测结果；复测前不得进入 `visuals` 或 `delivery`。
   - 若审核结果为 `BLOCKED`，当前工作流写入 `stage: review`、`status: BLOCKED`，并在 `next_action` 中明确需要修复的内容。
   - 审核阻断默认回退到 `drafting` 进行修订；如果阻断源头是事实冲突，则直接回退到 `intake`。
   - 审核通过或带备注通过后转入 `visuals`。

6. `visuals`
   - 固定执行顺序为 `review -> visuals -> delivery`，不得从 `review` 跳过视觉选择直接交付。
   - 进入阶段时写入 `substage: mode_selection` 和 `status: WAITING_CONFIRMATION`，让用户选择：
     - `existing_only`：只使用真实产品图、纯色背景与确定性信息卡。
     - `ai_assist`：允许 AI 生成场景或背景，再叠加真实产品图和精确中文文字。
   - 用户选择 `existing_only` 后，调用 `$xhs-visual-planner` 生成图片规划并展示给用户确认；不选择渠道，不生成 Prompt，不调用图片服务。
   - 用户选择 `ai_assist` 后，依次进入 `provider_selection`、`plan_review` 和 `prompt_review`：
     - `provider_selection`：展示插件支持的图片渠道与模型选项，等待用户选择渠道、模型、尺寸和质量。
     - `plan_review`：调用 `$xhs-visual-planner`，展示每页任务、页面类型、真实图片使用位置和 AI 场景范围，等待用户确认。
     - `prompt_review`：按轮播顺序一次展示全部页面的实际 Prompt、渠道、模型、尺寸和质量，写入待确认记录并保持 `WAITING_CONFIRMATION`。
   - 只有用户明确确认整批 `prompt_review` 后，才为每页计算并保存 `approval_digest`，生成批量执行文件，并把子阶段推进到 `ready`。
   - Prompt、渠道、模型、尺寸或质量任何一项变化，都必须使旧批准失效，清除旧 `approval_digest`，回退到 `prompt_review / WAITING_CONFIRMATION`，不得沿用旧批准。
   - `ready` 之后才允许调用 `$xhs-approved-image-generator`。默认使用 3 个并发任务，可在 1-8 之间调整；页码和交付顺序保持不变。
   - 执行时进入 `generating`。首个任务失败或状态不确定后停止提交新任务，保留已经在途任务的结果；付费请求不得自动重试。
   - 恢复执行时读取批量生成状态并跳过已成功页面。存在 `failed` 或 `uncertain` 时写入 `BLOCKED`，等待用户核对渠道后台并决定后续处理。
   - 真实产品包装、颜色、材质、接口、标签和比例不得由 AI 重绘。AI 仅生成场景或背景，最终由图片合成工具输出 1080x1440 PNG。
   - `existing_only` 的规划确认完成，或 `ai_assist` 的全部成品图生成并验证完成后，写入 `substage: complete`，保存 `visual_plan` 和 `generated_images`，再进入 `delivery`。
   - 用户改变文案、封面文字、轮播内容或真实图片后，视觉规划及其下游产物全部失效，回退到 `plan_review`；用户只改变 Prompt 或执行条件时回退到 `prompt_review`。

7. `delivery`
   - 先确认 `workflow-state.json` 仍符合 `../../assets/workflow-state-schema.json`。
   - 再确认待交付 JSON 符合 `../../assets/delivery-schema.json`。
   - 再确认 `visuals / complete` 已成立；`ai_assist` 必须有已验证的 `generated_images`，`existing_only` 必须有已确认的图片规划和可访问资源。
   - 两项都通过后才允许调用 `$xhs-html-delivery` 生成最终 HTML。
   - 若交付 JSON 缺字段、图片缺失、映射不一致或审核状态重新变为阻断，写入 `blockers` 并切换为 `BLOCKED`。
   - 交付成功后转入 `completed`。

8. `completed`
   - 写入 `stage: completed`、`status: COMPLETED`。
   - `artifacts` 中必须保留最终 `delivery_json`、`delivery_html`、审核结论和关键确认记录。
   - `next_action` 仅描述可选后续，例如再次迭代或归档，不再驱动主流程前进。

## Resume, Recovery And Rollback

- 恢复执行时，先读取最后一个有效的 `workflow-state.json`；若字段不完整或阶段值非法，回退到 `intake` 重新建立状态。
- `IN_PROGRESS` 表示当前阶段正在处理，`WAITING_CONFIRMATION` 表示必须等待人工决策，`BLOCKED` 表示已有明确阻断且不能自动越过，`COMPLETED` 只用于最终封存。
- 所有阶段转换都要先更新 `checkpoint` 和 `transition_log`，保留最近有效阶段与已有 `artifact_refs`，再切换 `stage`、`status`、`artifacts`、`blockers`、`confirmations` 和 `next_action`，避免恢复时丢失已有产物引用。
- `checkpoint.sequence` 必须单调递增；`last_valid_stage` 代表最近一个可恢复阶段，`resume_from` 代表当前应该从哪个阶段继续，`artifact_refs` 保留恢复所需的产物引用。
- `transition_log` 必须记录每次前进、回退、阻断和恢复，包括来源阶段、目标阶段、状态变化、触发原因和序号。
- 发现事实冲突时，必须写入冲突来源、受影响声称和回退原因，并退回 `intake`；不得在 `drafting` 或 `review` 中靠措辞修补。
- 审核阻断时，必须保留最近一次可用文案包和审核发现；修复完成后从 `drafting` 恢复，再重新进入 `review`。
- 视觉阶段中断时，从最后一个有效子阶段恢复；没有当前批准哈希时不得从 `ready` 或 `generating` 恢复。
- 批量生图恢复时必须复用当前 `generation-state.json`，不得重新发送已经成功或状态不确定的付费请求。
- 文案、封面、轮播或真实产品图改变后，已有 `visual_plan`、Prompt 批准和生成结果不得继续作为当前交付依据。
- Prompt、渠道、模型、尺寸或质量改变后，旧批准必须失效并回退到 `prompt_review / WAITING_CONFIRMATION`。
- 人工补齐材料、确认角度或解除阻断后，要新增确认记录并把状态从 `WAITING_CONFIRMATION` 或 `BLOCKED` 恢复为对应阶段的 `IN_PROGRESS`。

## Human Confirmation Gates

- 素材获取方式：用户提供素材链接或插件内部搜索。
- 素材来源确认：查看全部来源与核心信息后，明确回复“确认”或“继续”。
- 核心产品事实缺失或冲突。
- 选题与内容角度。
- `[ASSUMPTION]` 和 `[UNKNOWN]` 是否允许保留。
- 视觉模式：`existing_only` 或 `ai_assist`。
- AI 补图使用的渠道、模型、尺寸和质量。
- 图片规划。
- 最终 Prompt 与执行条件；确认前状态必须是 `WAITING_CONFIRMATION`。

## Delivery Rules

- 最终交付前，必须同时引用并满足 `../../assets/workflow-state-schema.json` 与 `../../assets/delivery-schema.json`。
- 图片服务不可用时，用户可以明确改选 `existing_only`，优先保留真实产品图并使用确定性信息卡完成表达；不得自动替用户切换模式。
- 只有当 `review` 已通过、`visuals / complete`、交付 JSON 完整、资源可访问且 HTML 生成成功时，才能把状态写成 `completed`。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/最终审核清单.md`
