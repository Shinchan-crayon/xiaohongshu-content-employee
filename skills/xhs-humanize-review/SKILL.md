---
name: xhs-humanize-review
description: 按事实、宣传风险、一致性、完整性、自然表达和 AI 模式顺序审核小红书内容。
---

# Xiaohongshu Humanize Review

## Input Contract

```yaml
material_record: object
content_package: object
source_ledger: [object]
account_voice: object | null
```

## Output Contract

```yaml
status: PASS | PASS_WITH_NOTES | BLOCKED
checks:
  - name: string
    status: PASS | WARN | FAIL
    findings:
      - hit_id: string
        summary: string
revised_content_package: object
changed_claims:
  - claim: string
    before: string
    after: string
    source_refs: [string]
    reason: string
naturalization_report:
  scanned_patterns: [string]
  hits:
    - id: string
      location: string
      severity: FATAL | HIGH | MEDIUM
      pattern: string
      evidence: string
      source_refs: [string]
      resolution: OPEN | RESOLVED | ACCEPTED
  changes:
    - hit_ids: [string]
      location: string
      before: string
      after: string
      reason: string
  preserved_claims:
    - claim: string
      source_refs: [string]
      verification: PASS | FAIL
  unresolved:
    - hit_id: string
      reason: string
      blocking: true | false
blocking_questions: [string]
```

## Mandatory Order

1. 事实一致性
2. 宣传风险
3. 标题正文一致性
4. 图片文案一致性
5. 信息完整性
6. 中文自然化与 AI 模式复检

不得先改写再核实事实。自然化不得改变数字、型号、颜色、功能、效果、价格、认证和适用范围。

## Fact Check Reuse

审核时直接复用调研阶段的同一张 `fact_check`，不再新建第二份报告。逐项检查标题、正文、封面和轮播中的数字、归属、因果、效果、认证、比较和引用：

- 写法超出 `allowed_wording` 时改回允许口径。
- 新增高风险事实但未记录来源时，状态为 `BLOCKED`。
- `fact_check` 中标记为 `NO` 的内容不得保留。

## Naturalization Procedure

完成事实、风险、一致性与完整性检查后，严格按以下顺序执行：

1. 从 `material_record` 和 `source_ledger` 提取不可变事实及来源编号，写入 `preserved_claims`。
2. 查结构层：空洞开场、提纲式骨架、机械分段、重复总结、强行升华。
3. 查句式层：连续对照句、三段式排比、模板化反问、相同句型连续出现。
4. 查词汇层：机械连接词、模糊归因、抽象程度词、客服腔和无证据判断。
5. 查节奏层：句长、段长、标点和段尾是否高度一致；只修影响阅读的单调，不套固定比例。
6. 查账号语气：用词、专业度、情绪强度和称呼是否符合 `account_voice`。
7. 查小红书载体：标题、正文、封面、轮播、CTA 和标签之间是否自然且一致。
8. 为每个命中项分配 `id`，记录位置、证据、来源和解决状态；修改记录必须通过 `hit_ids` 关联命中项。
9. 修改完成后复核不可变事实及跨载体一致性，更新 `resolution` 和 `verification`，再决定状态。

未填写完整 `naturalization_report` 时，不得声称“自然化已完成”。

## Status Gate

- `PASS`：所有命中均为 `RESOLVED`，不可变事实均为 `PASS`，跨载体复核通过，无未解决项。
- `PASS_WITH_NOTES`：不存在事实或宣传风险阻断，仅有中风险命中标记为 `ACCEPTED`，并在 `unresolved` 说明原因。
- `BLOCKED`：存在 `OPEN` 的致命级或高风险命中、来源不足、事实冲突、宣传风险未解除，或不可变事实复核失败。

## Review Principles

- 删除空洞铺垫、机械连接词、翻译腔、重复总结和无信息比喻。
- 长短句变化只作为阅读提示，不采用固定比例门槛。
- 口语程度由账号语气与目标用户决定。
- 不编造体验、朋友、读者反馈、对话、错别字或人格痕迹。
- 不使用检测器分数作为发布标准。

## Required References

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/宣传风险规则.md`
- `../../references/审核规则/内容一致性规则.md`
- `../../references/审核规则/中文自然化规则.md`
- `../../references/审核规则/AI写作模式.md`
- `../../references/审核规则/小红书自然化执行手册.md`
- `../../references/审核规则/最终审核清单.md`
