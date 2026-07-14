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
    findings: [object]
revised_content_package: object
changed_claims: [object]
blocking_questions: [string]
```

## Mandatory Order

1. 事实一致性
2. 宣传风险
3. 标题正文一致性
4. 图片文案一致性
5. 信息完整性
6. 中文自然化
7. AI 模式检查

不得先改写再核实事实。自然化不得改变数字、型号、颜色、功能、效果、价格、认证和适用范围。

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
- `../../references/审核规则/最终审核清单.md`
