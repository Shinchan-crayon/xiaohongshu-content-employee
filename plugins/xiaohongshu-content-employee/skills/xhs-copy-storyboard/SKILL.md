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
  selected_topic_id: topic-*
  selected_topic_direction: parameter_comparison | scenario_seeding
  selected_topic_claim_ids: [claim-*]
  backup_topic_brief: string | null
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
2. 只写 `selected_topic_id` 和 `selected_topic_direction` 指向的方向，不重新选题，
   不新增事实；`backup_topic_brief` 仅作为备用方向提示，不扩写成第二篇方案。
3. `titles` 至少生成 5 个候选标题，并在收益、问题、场景、对比、结果五类角度中
   覆盖至少 4 类；少于 5 个不得提交。
4. `post` 必须是可直接发布的最终正文字符串。禁止把 `briefing`、`claim`、
   `claim_ids`、卖点追溯字段或其他内部结构化对象当作正文。
5. 候选标题、正文和轮播块只使用已声明的 `claim_ids` 与
   `selling_point_ids`。
6. 正文使用 `post_selling_point_ids` 和 `post_claim_ids` 记录完整追溯关系。
   所有 `must_use: true` 的卖点必须同时进入正文追溯字段，并至少被一个
   `carousel_blocks` 项引用。
7. `locked_terms`、`locked_wording` 和 `forbidden_expansions` 是编辑护栏，不是
   正文素材清单。`locked_wording` 用于校对事实含义和表达边界，不要求逐字写入，
   也不得被逐项枚举、照抄限定语或改写成可见的免责声明；提及相关事实时仍不得
   改义。`forbidden_expansions` 只用于阻止夸大、替换和未证实扩写，不得反向写成
   “不能理解为……”或同类免责句。`locked_terms` 只要求在提及时保持准确，不要求
   全部写入标题、正文或轮播；`unresolved_fields` 中的值不得自行补全。
8. 产品名称、型号、规格和变体一旦出现，必须与 `product_identity` 保持一致；
   官方页面标题、货号和内部身份字段仅在消费者确实需要时才写入成稿。
9. 正文以用户场景、具体收益和有事实依据的编辑判断组织信息，保持真人分享式的
   自然表达，不按护栏字段逐项解释产品。限制条件默认留在编辑校对中；只有当它
   直接影响适用资格、安全、核心功能或购买决策时才写入正文，并将同类条件合并成
   最多 1 至 2 句人话，例如“开降噪单次最长 4 小时，长通勤记得把充电盒带上”。
   每个卖点按“用户场景 -> 受支持的正向事实 -> 对用户的意义”写完即止；不要为了
   显得严谨，再用“但”“并非”“不是”“不等于”“无法”或“不能”另起一句描述
   `forbidden_expansions` 中的禁止项。不要照抄证据句，不要把参数逐条列成产品说明书。
10. 标题、正文和轮播禁止使用“需满足”“不能理解为”“按……口径看”“所列出的
   兼容条件”等产品文档、审核记录或法律免责声明式表述，也不得用同义句逐项反向
   解释编辑护栏。
11. 标题、正文和轮播不得出现“先锁定产品身份”“官方页面标题”“来源台账”
   “事实边界”等内部工作流语言，也不得输出字段名或审核过程。
12. 正文保持自然编辑节奏，不虚构第一人称实测经历，不固定使用三选一 CTA；
   禁止机械套用“表面上……但背后……”对照、强行升华或反复总结同一结论。
13. 标题候选保持不同切入点，但都必须与正文和选题一致。
14. 每个轮播块只承担一个信息任务，页数取最小必要集合。
15. 每个轮播块默认只提供 2 组、最多 3 组短中文文案。未经用户或选题明确要求，
   禁止自行创造“第一关”“第二关”“闯关”“关卡”“步骤一”等阶段标签，也
   不得把参数拆成 4 到 5 行技术清单。
16. 文案和全部最终 Prompt 必须在同一次 compose 调用中完成；本 Skill 输出
   `content.json`，同一调用同时由 `$xhs-visual-planner` 输出 `visual.json`。

## Content Depth（正文深度要求）

正文不是卖点概要，是真实分享。以下规则保证每段都够厚：

### 段落结构

每个卖点对应的正文段落，按四步展开（不是机械套模板，而是自然包含这四层信息）：

1. **场景锚点** — 在什么具体情境下能感受到（如"高铁上临时剪一段视频时…"）；只有用户素材或证据明确支持真实经历时才写成第一人称亲历
2. **具体细节** — 发生了什么、看到了什么、数据/对比/质感（不是"很轻"，是"221g，单手回微信小拇指不再撑手机"）
3. **体验判断** — 写清使用反应、情绪和预期差异；没有真实体验证据时不虚构"我用了两周"等个人经历
4. **延伸价值** — 这一点对目标受众来说意味着什么（"如果你经常出差/拍照/打游戏…"）

### 篇幅底线

- 每个卖点段落 ≥ 120 字（约 3-4 句完整表达）
- 全文（不含标题）≥ 600 字
- 禁止出现只有 1-2 句话的卖点段落——那不够

### 差异化深度

相邻卖点段落的写法不能雷同。使用不同场景、问题或信息密度切入；只有来源明确支持真实使用周期或个人经历时，才写"上手第一天"、"用了两周"或"有次出差"。

### 可感知细节（必含至少 3 处）

段落中必须包含具体的、读者能"看见"的细节，例如：

- 物理数据（221g、29 小时、5 倍）
- 场景画面（高铁窗边、演唱会第二排、午休工位）
- 对比参照（比上代 X、和同事的 Y 对比、和预期不一样）
- 有证据支持的使用习惯变化（一根线可连接多个兼容设备、减少额外线材等）

纯抽象概括（"体验很好""值得购买""各方面都升级了"）不能作为段落主体，只能作为末尾收束。

### 正文结构模板

```
[开篇 hook：1 句话抛出核心感受，制造期待]

[卖点段落 1：场景切入 → 细节 → 感受 → 延伸。4-7 句]

[卖点段落 2：不同时间/场景切入 → 细节 → 感受 → 延伸。4-7 句]

[卖点段落 3-N：同上，每段保持不同切入角度。4-7 句/段]

[收尾：分情况总结，带购买建议或人群匹配。3-5 句]
```

收尾不喊口号，不给三选一 CTA。写「如果你在 XX 情况，可以考虑」「对 YY 用户来说最大的变化是」这种有信息量的判断。

### 输出质量门

提交前自查：

- [ ] 平均每卖点段落 ≥ 120 字
- [ ] 全文 ≥ 600 字
- [ ] 没有 1-2 句话就结束的卖点段
- [ ] 至少 3 处可感知的具体细节（数字/场景/对比/习惯变化）
- [ ] 至少 2 个卖点段落的切入时间/场景不完全相同
- [ ] 收尾不是空泛口号，是对具体人群的有判断量的建议

## Required References

- `../../references/小红书内容规范/标题规则.md`
- `../../references/小红书内容规范/正文规则.md`
- `../../references/小红书内容规范/封面与轮播规则.md`
- `../../references/小红书内容规范/标签规则.md`
- `../../references/小红书内容规范/账号语气配置.md`

## Schema Self-Check（提交前自检）

在写入 `content.json` 前，确认以下字段全部满足：

- [ ] `titles` 数量 ≥ 5，覆盖至少 4 类角度（收益/问题/场景/对比/结果）
- [ ] `post` 必须是**纯字符串**，不能是 `{"body": "...", "hook": "..."}` 对象
- [ ] `carousel_blocks` 每项字段名用 `id`（不是 `page_id`），且含 `selling_point_ids`、`claim_ids`
- [ ] 所有 `must_use: true` 的卖点 ID 同时出现在 `post_selling_point_ids` 和至少一个 `carousel_blocks` 项的 `selling_point_ids` 中
- [ ] 标题、正文、轮播文本中不包含 `material.product_identity.forbidden_replacements` 里的任何词（注意是**完整独立词**匹配，产品名包含的字串不应误判）
