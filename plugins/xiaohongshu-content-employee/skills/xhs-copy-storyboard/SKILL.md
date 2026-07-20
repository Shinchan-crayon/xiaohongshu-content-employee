---
name: xhs-copy-storyboard
description: Compose Worker 在唯一一次 compose 模型调用中生成完整小红书文案、候选标题和可追溯轮播结构。
---

# Xiaohongshu Copy Storyboard

本 Skill 与 `$xhs-visual-planner` 在同一个无历史 Compose Worker、同一次
compose 模型调用中执行。只读取 `material.json` 和 `evidence.json`，不得读取
`task.json`、主对话、其他 Worker 对话或未声明产物。Compose Worker 只输出
`content.json` 和 `visual.json`，随后销毁上下文。

## Input Contract

```yaml
material:
  schema_version: 1
  run_id: string
  product_identity: object
  product_reference_pack: [object]
  selling_points: [object]
evidence:
  schema_version: 1
  run_id: string
  claims: [object]
  sources: [object]
  topic_candidates: [object]
  selected_topic_id: topic-*
```

## Output Contract

```yaml
schema_version: 1
run_id: string
titles: [string]
post: string
post_selling_point_ids: [sp-*]
post_claim_ids: [claim-*]
carousel_blocks:
  - id: page-*
    text: string
    selling_point_ids: [sp-*]
    claim_ids: [claim-*]
```

## Method

1. 在同一次 compose 中生成完整小红书文案、候选标题、轮播结构、全部最终生图
   Prompt 和每页参考图对应关系，不允许拆成第二次模型调用。
2. 只写 `selected_topic_id` 指向的方向，不重新选题，不新增事实。
3. `titles` 至少生成 5 个候选标题，并在收益、问题、场景、对比、结果五类角度中
   覆盖至少 4 类；少于 5 个不得提交。
4. `post` 必须是可直接发布的最终正文字符串。禁止把 `briefing`、`claim`、
   `claim_ids`、卖点追溯字段或其他内部结构化对象当作正文。
5. 候选标题、正文和轮播块只使用已声明的 `claim_ids` 与
   `selling_point_ids`。
6. 正文使用 `post_selling_point_ids` 和 `post_claim_ids` 记录完整追溯关系。
   所有 `must_use: true` 的卖点必须同时进入正文追溯字段，并至少被一个
   `carousel_blocks` 项引用。
7. `locked_wording` 不得改义；`forbidden_expansions` 中的夸大、替换和未证实
   扩写不得出现。`locked_terms` 只要求在提及时保持准确，不要求全部写入标题、
   正文或轮播；`unresolved_fields` 中的值不得自行补全。
8. 产品名称、型号、规格和变体一旦出现，必须与 `product_identity` 保持一致；
   官方页面标题、货号和内部身份字段仅在消费者确实需要时才写入成稿。
9. 将事实改写成用户场景，将产品特征改写成具体收益，将限制条件改写成自然的
   购买或使用建议。不要照抄证据句，不要把参数逐条列成产品说明书。
10. 标题、正文和轮播不得出现“先锁定产品身份”“官方页面标题”“来源台账”
   “事实边界”等内部工作流语言，也不得输出字段名或审核过程。
11. 正文保持自然编辑节奏，不虚构第一人称实测经历，不固定使用三选一 CTA；
   禁止机械套用“表面上……但背后……”对照、强行升华或反复总结同一结论。
12. 标题候选保持不同切入点，但都必须与正文和选题一致。
13. 每个轮播块只承担一个信息任务，页数取最小必要集合。
14. 每个轮播块默认只提供 2 组、最多 3 组短中文文案。未经用户或选题明确要求，
   禁止自行创造“第一关”“第二关”“闯关”“关卡”“步骤一”等阶段标签，也
   不得把参数拆成 4 到 5 行技术清单。
15. 文案和全部最终 Prompt 必须在同一次 compose 调用中完成；本 Skill 输出
   `content.json`，同一调用同时由 `$xhs-visual-planner` 输出 `visual.json`。

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书内容规范/标签规则.md`
- `../../references/小红书内容规范/账号语气配置.md`
