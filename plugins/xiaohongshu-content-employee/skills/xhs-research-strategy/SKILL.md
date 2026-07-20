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
topic_candidates:
  - id: topic-*
    title: string
    claim_ids: [claim-*]
selected_topic_id: topic-*
learning_candidates:
  - value: string
    source: string
    observed_at: YYYY-MM-DD
    status: pending
```

## Method

1. 逐个读取当前阶段允许访问的产品链接和来源，优先产品官网、页面原文、权威
   资料和可追溯原文，不越过 `allowed_source_urls` 白名单。
2. 数字、日期、价格、型号、功能、效果、认证、归属、因果、比较和引用使用稳定
   `claim-*` ID，并通过 `source_ids` 绑定来源。
3. `allowed_wording` 只保存来源真正支持的口径，不把搜索摘要直接当产品事实。
4. `material.json` 中每个产品参考图和卖点的 `source_claim_ids` 必须在
   `claims` 中存在；缺失时不能进入 `evidenced`。
5. 只生成有事实支撑的选题候选，并在当前 Worker 内直接确定
   `selected_topic_id`，不增加来源确认或选题确认轮次。
6. 核心事实不足时停止本 Worker 并报告缺失字段，不生成无来源内容；非核心未知
   项不写入成稿。
7. 可跨任务复用的发现写入 `learning_candidates`，必须保留来源和
   `observed_at`，并在 Research Worker 完成后存入插件外部用户数据区的
   `pending`。候选不得直接写入已批准知识，也不阻塞或延长本次直出链路。

## Prohibited

- 不替换 `product_identity`，不借用竞品或相似型号卖点。
- 不补写无来源的热度、销量、效果、趋势、规格、价格或认证。
- 不要求用户为来源列表逐项确认。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/虚构内容禁止规则.md`
- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/个性化学习规则.md`
- `../../references/行业模板/通用消费品.md`
