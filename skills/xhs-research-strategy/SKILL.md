---
name: xhs-research-strategy
description: 分析客户参考材料与可选外部调研，建立来源台账并生成适合小红书的选题候选。
---

# Xiaohongshu Research Strategy

## Input Contract

```yaml
material_record: object
customer_references: [path_or_url]
external_research_allowed: boolean
query_date: YYYY-MM-DD
```

## Output Contract

```yaml
source_ledger: [object]
competitor_patterns: [object]
audience_pains: [object]
topic_candidates:
  - title: string
    angle: string
    evidence_labels: [FACT | INFERENCE | ASSUMPTION | UNKNOWN]
    fit_score: integer
    risk: string
research_limitations: [string]
```

## Method

1. 先分析客户提供的竞品和参考内容。
2. 将可借鉴的结构与不可复制的事实、评价、数据分开。
3. 外部调研是可选项；记录 URL、来源名、查询日期和支持的声称。
4. 查询失败时不得阻塞主流程：基于客户材料继续，并明确调研限制。
5. 生成 2-5 个选题，评估目标匹配、素材支撑、视觉可执行性和宣传风险。

## Prohibited

- 不复制竞品独有体验和用户评价。
- 不把热度、销量、效果或趋势写成没有来源的事实。
- 主流程不依赖 MCP。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/小红书内容规范/标题规则.md`
- `../../references/行业模板/通用消费品.md`
