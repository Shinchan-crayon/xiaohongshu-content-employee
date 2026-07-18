---
name: xhs-research-strategy
description: 在 evidence 阶段读取用户链接或执行内部搜索，建立来源台账、高风险事实核查和选题候选，不增加来源确认轮次。
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
fact_check:
  - claim: string
    original_context: string
    source: string
    can_use: YES | WITH_NOTE | NO
    allowed_wording: string
fact_check_status: PASS | BLOCKED
competitor_patterns: [object]
audience_pains: [object]
topic_candidates: [object]
research_limitations: [string]
learning_candidates:
  - value: string
    source: string
    observed_at: string
    status: pending
```

## Method

1. `user_links` 逐个读取用户提供的链接，不得执行内部搜索或自动扩展网页。
2. `internal_search` 必须执行内部搜索，优先官方页面、权威资料和可追溯原文。
3. 记录 URL、标题、来源、查询日期、内容类型、核心信息和支持的声称。
4. 自动生成 `source_review_table`，但不等待用户确认完整来源列表，也不设置 `source_confirmed` 门禁。
5. 只核查数字、日期、价格、功能、效果、认证、归属、因果、比较和引用等高风险事实。
6. 有可靠来源且口径一致的写 `YES`；需要限定的写 `WITH_NOTE` 和 `allowed_wording`；无法核实或冲突的写 `NO`。
7. 核心 `NO` 项使 `fact_check_status: BLOCKED`；非核心未知项作为限制，禁止写入成稿。
8. 事实通过后生成 2-5 个证据支持的选题候选，交给 `compose` 自动选择。
9. 可跨任务复用的外部结论必须带来源和 `observed_at`，仅作为 `pending` 学习候选，不得直接写入已批准知识，也不阻塞本次交付。

## Failure Rules

- 内部搜索不可用但现有材料足以完成任务：记录限制后继续。
- 搜索不可用且核心事实不足：返回 `BLOCKED`，不得用无来源内容补齐。
- 新发现材料冲突：保留冲突来源和受影响声称，交主控在 `evidence` 处理。

## Prohibited

- 不复制竞品独有体验和评价。
- 不把搜索摘要直接当成产品事实。
- 不补写无来源的热度、销量、效果、趋势、规格、价格或认证。
- 不要求用户为来源中的全部声称背书。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/个性化学习规则.md`
- `../../references/行业模板/通用消费品.md`
