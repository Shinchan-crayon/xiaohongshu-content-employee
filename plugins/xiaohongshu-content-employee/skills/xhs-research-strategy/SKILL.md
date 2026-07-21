---
name: xhs-research-strategy
description: Research Worker 的证据与选题契约；在同一次商品研究调用中生成 evidence.json。
---

# Xiaohongshu Research Strategy

本 Skill 与 `$product-material-intake` 在同一个无历史 Research Worker、同一次
模型调用中执行。它只读取 `task.json` 声明的产品链接、图片和素材，以及同一次
调用内形成的 `material.json` 内容和 `allowed_source_urls`；负责输出
`evidence.json`。不得读取主对话、其他 Worker 对话或未声明产物。阶段结束后
销毁上下文。

## Input Contract

```yaml
material:
  schema_version: 1
  run_id: string
  product_identity: object
  product_reference_pack: [object]
  selling_points: [object]
  conflicts: [object]
  missing_material: [string]
  allowed_source_urls: [url]
query_date: YYYY-MM-DD
```

## Output Contract

```yaml
schema_version: 1
run_id: string
claims:
  - id: claim-*
    text: string
    allowed_wording: [string]
    source_ids: [source-*]
sources:
  - id: source-*
    title: string
    url: https://...
selected_topic_id: topic-*
selected_topic_direction: parameter_comparison | scenario_seeding
selected_topic_claim_ids: [claim-*]
backup_topic_brief: string | null
learning_candidates:
  - value: string
    source: string
    observed_at: YYYY-MM-DD
    status: pending
```

字段规则：`schema_version` 必须为 `1`，`run_id` 必须沿用输入值；ID 使用契约中
声明的 `claim-*`、`source-*` 和 `topic-*` 前缀。`allowed_wording` 与 `source_ids`
均不可为空，`selected_topic_claim_ids` 至少引用一个已建立的 claim；运行时负责
格式、数量和引用关系校验。

## Method

1. 读取当前阶段允许访问的产品链接和来源，优先产品官网、页面原文、权威资料和
   可追溯原文，不越过 `allowed_source_urls` 白名单。公开且容易识别的产品默认读取
   产品概览页，以及技术规格页或官方支持页，默认最多两个官方页面；只有核心事实或
   限制仍无法确认时才增加第三个来源。
2. 数字、日期、价格、型号、功能、效果、认证、归属、因果、比较和引用使用稳定
   `claim-*` ID，并通过 `source_ids` 绑定来源。输出 4-6 条原子事实：一个独立可
   核实的功能、数字、条件或限制单独成 claim，不把 ANC、通透、Adaptive Audio 等
   多个事实塞进同一条 claim。
3. `allowed_wording` 只保存来源真正支持的口径，不把搜索摘要直接当产品事实。
4. `material.json` 中每个产品参考图和卖点的 `source_claim_ids` 必须在
   `claims` 中存在；缺失时不能进入 `evidenced`。
5. 确保 `material.json` 有 3-4 个卖点；每个卖点同时包含产品特征、用户问题、用户
   收益、使用场景和边界/禁止扩写，并绑定对应 claim。至少覆盖产品身份、核心功能、
   适用条件或限制、规格或购买边界。
6. 把官方页面未确认但容易被误写的术语、兼容条件、续航口径或视角记录到
   `missing_material`，不要用相近产品知识补齐。
7. 只输出一个确定的 `selected_topic_id`、一个方向
   (`parameter_comparison` 或 `scenario_seeding`) 和对应 `selected_topic_claim_ids`。
   最多补充一句 `backup_topic_brief`，不生成完整标题候选；标题由 Compose Worker
   负责。
8. 核心事实不足时停止本 Worker 并报告缺失字段，不生成无来源内容；非核心未知
   项不写入成稿。
9. 可跨任务复用的发现写入 `learning_candidates`，必须保留来源和
   `observed_at`，并在 Research Worker 完成后存入插件外部用户数据区的
   `pending`。候选不得直接写入已批准知识，也不阻塞或延长本次直出链路。

## Prohibited

- 不替换 `product_identity`，不借用竞品或相似型号卖点。
- 不补写无来源的热度、销量、效果、趋势、规格、价格或认证。
- 不要求用户为来源列表逐项确认。

## Content Enrichment（为高质量正文提供素材）

Research Worker 的产出不仅是事实校验表，还要成为 Compose Worker 的素材库。以下内容直接影响正文的「厚度」和可读性：

### 每卖点必收集

在建立每个 `selling_point` 时，同时收集以下写作素材，写入 `evidence.json` 对应 claim 的 `allowed_wording`：

1. **物理可感知数据** — 重量、尺寸、厚度、材质触感、颜色选项等能让人「看到/摸到」的数字
2. **对比锚点** — 与上一代或同价位产品的关键差异值（如「比上代轻 19g」「续航多 3 小时」）
3. **典型场景速写** — 这个卖点在什么日常情境下被感知（如「地铁单手回消息」「健身房放口袋里」「出差高铁上」）
4. **用户习惯变化** — 用了之后生活会有什么不同（如「不再带充电宝」「一根线充所有设备」）

### 禁止贫瘠输入

以下情况会导致 Compose Worker 产出单薄正文，Research Worker 需避免：

- 卖点的 `usage_scenario` 只写了一个抽象的类别词（如 "日常使用"）→ 应写具体情境
- `locked_wording` 照抄了技术规格书原文 → 应改写为人话，但仍保持事实准确
- `user_benefit` 和 `user_problem` 是同义反复 → 必须是从问题到收益的真链路
- 多个卖点使用了同一场景描述 → 每个卖点应有不同的情境切入

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/虚构内容禁止规则.md`
- `../../references/小红书内容规范/产品种草规范.md`

## Schema Self-Check（提交前自检）

在写入 `evidence.json` 前，确认以下字段全部满足：

- [ ] `claims` 至少 4 条原子事实
- [ ] `selected_topic_direction` 字段存在，且只能是 `"parameter_comparison"` 或 `"scenario_seeding"`
- [ ] `selected_topic_claim_ids` 字段存在，至少包含 1 个已声明的 claim ID
- [ ] `backup_topic_brief` 必须是**纯字符串**，不是对象 `{topic_id, direction}`。格式：一句描述备用方向，末尾可附 `"备用选题：topic-xxx"`
- [ ] `learning_candidates` 如无发现，设为 `[]`
