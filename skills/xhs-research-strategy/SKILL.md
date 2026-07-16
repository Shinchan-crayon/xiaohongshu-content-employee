---
name: xhs-research-strategy
description: 分析客户参考材料与可选外部调研，建立来源台账并生成适合小红书的选题候选。
---

# Xiaohongshu Research Strategy

## Input Contract

```yaml
material_record: object
material_source_mode: user_links | internal_search
material_links: [url]
customer_references: [path_or_url]
query_date: YYYY-MM-DD
learning_context: object | null
```

## Output Contract

```yaml
source_ledger: [object]
search_queries: [string]
search_status: NOT_REQUESTED | COMPLETED | LIMITED
source_review_table:
  - source: string
    url: string
    core_information: string
source_confirmed: boolean
fact_check:
  - claim: string
    original_context: string
    source: string
    can_use: YES | WITH_NOTE | NO
    allowed_wording: string
fact_check_status: PASS | BLOCKED
competitor_patterns: [object]
audience_pains: [object]
topic_candidates:
  - title: string
    angle: string
    evidence_labels: [FACT | INFERENCE | ASSUMPTION | UNKNOWN]
    fit_score: integer
    risk: string
research_limitations: [string]
learning_candidates:
  - kind: fact | operating_pattern | content_pattern
    statement: string
    source: string
    observed_at: YYYY-MM-DD
    status: pending
```

## Material Source Modes

本 Skill 是插件内部的素材搜索与来源整理入口，但必须服从用户已经确认的模式：

- `user_links`：读取并分析用户提供的 `material_links`。可以打开这些链接获取正文，但不得执行内部搜索，也不得自动寻找其他网页。
- `internal_search`：必须执行内部搜索。根据 `product_or_service`、`content_goal`、`target_audience` 和材料记录构造查询，搜索可追溯的文章或产品素材。

两种模式不能在同一次调研中混用。用户要求切换模式时，回退到 `intake` 更新 `material_source_selection`。

## Method

1. 校验 `material_source_mode`，并在 `source_ledger` 中记录本次选择。
2. `user_links` 模式逐个读取用户链接；记录 URL、页面标题、来源名、查询日期、内容类型和支持的声称。
3. `internal_search` 模式先生成 `search_queries`，再使用当前 Codex 可用的网页搜索或浏览能力寻找来源；优先产品官方页面、权威资料和可追溯的原始文章。
4. 将可借鉴的结构与不可复制的事实、评价、数据分开，不把搜索摘要直接当成产品事实。
5. `user_links` 模式完成后写入 `search_status: NOT_REQUESTED`；`internal_search` 找到可验证来源后写入 `COMPLETED`。
6. 内部搜索能力不可用、结果为空或来源无法验证时，写入 `search_status: LIMITED` 和 `research_limitations`，回退到 `intake`，请用户重试或改为提供链接。
7. 搜集结束后生成 `source_review_table`，向用户展示全部来源、链接和核心信息，并把 `source_confirmed` 设为 `false`。
8. 等待用户明确回复“确认”或“继续”。未确认前不得生成选题；用户要求补充或删除来源时，更新表格后重新展示。
9. 用户确认后把 `source_confirmed` 设为 `true`。只核查高风险事实：数字、日期、价格、功能、效果、认证、归属、因果、比较和引用，填写同一张 `fact_check`。
10. 有可靠来源且口径一致的可以写；需要限定的写入 `allowed_wording`；无法核实或来源冲突的标记为 `NO`。
11. 存在核心 `NO` 项时写入 `fact_check_status: BLOCKED`；处理完成后写入 `PASS`，再生成 2-5 个选题。
12. 仅将可跨任务复用、能够说明来源和 `observed_at` 的结论放入 `learning_candidates`，状态固定为 `pending`。

## Source Confirmation Gate

来源确认表至少包含：

| 来源 | 链接 | 核心信息 |
|---|---|---|

这个门禁只确认素材覆盖是否完整，不代表用户替插件为事实背书。

## Fact Check Gate

`fact_check` 只记录高风险事实，保留原始口径、来源、能否使用和正文允许写法。普通描述不重复建表。

## Learning Candidate Gate

- 外部事实、运营规律和内容模式必须保留来源与 `observed_at`。
- 所有新候选默认是 `pending`，不得直接写入已批准知识。
- 搜索摘要、竞品原文、单条无法复核的观点和仅适用于本次产品的规格不进入长期知识候选。
- 候选项可以用于本次任务的事实核查或策略判断，但后续任务只有在用户批准后才能复用。

## Prohibited

- 不复制竞品独有体验和用户评价。
- 不把热度、销量、效果或趋势写成没有来源的事实。
- 不根据搜索结果补写未经产品来源确认的规格、价格、认证或效果。
- 不把用户确认来源清单等同于用户确认其中所有声称为事实。
- 不在 `source_confirmed: false` 或 `fact_check_status: BLOCKED` 时生成选题。
- 主流程不依赖 MCP。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/个性化学习规则.md`
- `../../references/行业模板/通用消费品.md`
