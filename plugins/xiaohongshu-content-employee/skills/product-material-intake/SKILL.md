---
name: product-material-intake
description: Research Worker 的商品身份与素材契约；在一次研究调用中从 task.json 锁定产品身份、真实参考图和卖点，写入 material.json。
---

# Product Material Intake

本 Skill 与 `$xhs-research-strategy` 在同一个无历史 Research Worker、同一次
模型调用中执行。它只读取 `task.json` 中契约声明的字段，以及其中声明的产品
链接、图片和素材；负责形成同一外部 `run_dir` 的 `material.json`。Research
Worker 同一调用还输出 `evidence.json`。不得读取主对话、其他 Worker 对话、
其他 JSON 产物或其他运行目录。阶段结束后销毁上下文。

## Input Contract

```yaml
schema_version: 1
run_id: string
summary: string
content_goal: string
product_links: [url]
product_images: [path]
material_paths: [path]
target_audience: string | null
account_voice: object | null
```

## Output Contract

```yaml
schema_version: 1
run_id: string
product_identity:
  source_url: string
  exact_page_title: string
  brand: string
  name: string
  model: string
  variant: string
  category: string
  identifying_terms: [string]
  unresolved_fields: [string]
  locked_terms: [string]
  forbidden_replacements: [string]
reference_image_strategy: local_reference | public_product_identity
visual_identity:
  visible_colors: [string]
  visible_forms: [string]
  distinguishing_features: [string]
product_reference_pack:
  - id: ref-*
    path: path
    role: front | three_quarter | package | detail | official_scene
    supported_views: [string]
    source_claim_ids: [claim-*]
selling_points:
  - id: sp-*
    product_feature: string
    user_problem: string
    user_benefit: string
    usage_scenario: string
    source_claim_ids: [claim-*]
    locked_wording: string
    priority: integer
    must_use: boolean
    forbidden_expansions: [string]
conflicts: [object]
missing_material: [string]
```

## Product Identity

1. 读取产品链接后，先锁定页面对应的准确产品身份，再整理参考图和卖点。
2. `source_url` 和 `exact_page_title` 保存实际页面身份；品牌、名称、型号、
   变体、类别和识别词必须来自用户素材或页面证据。
3. `locked_terms` 保存已核实且提及时不得改写的品牌、产品名、型号、变体和关键
   命名；它是身份准确性护栏，不是正文关键词清单，后续文案不需要逐项出现。
   `exact_page_title` 单独保存为内部来源身份，货号、页面标题等仅在对消费者有用时
   才进入成稿。容易混淆的其他产品、旧款或竞品进入
   `forbidden_replacements`。
4. 无法确认的字段写入 `unresolved_fields`，后续 Worker 不得自行补全，也不得\n   用相似产品型号、规格或变体补位。

## 身份锁定分级

Research Worker 按以下优先级处理产品身份，未满足当前级别时不得强行进入下一级：

1. **品牌 + 品类（必须确认）** — 品牌名和产品类型必须来自可验证来源。只有品牌或品类完全无法确认时，才停止 Research Worker 并报告缺失信息。
2. **型号/口味/规格（尽量确认）** — 优先从来源页面提取。无法核实时写入 `unresolved_fields`，不阻止流程继续。
3. **配料/包装/产地/重量（可选）** — 有则记录，无则留空或不写入 selling_points。

"口味不确认就不能继续"的情况不应发生。只要品牌和品类能锁定（如"良品铺子 无骨鸡爪"），Research Worker 就必须继续产出 selling_points 和 evidence，缺少的口味/规格标为 `unresolved_fields`。
5. 用户素材、页面资料或可靠来源发生冲突时写入 `conflicts`，不得自行选择更好写
   的版本。

## Reference Pack

1. 用户提供的真实产品图优先；不足时只补充可靠官方来源的产品图。
2. 每张图记录稳定 `ref-*` ID、实际路径、图片角色和肉眼可见的
   `supported_views`。
3. `supported_views` 只写参考图真实支持的正面、45 度、包装、细节或官方场景，
   不推测背面、盒内结构、配件或未展示角度。
4. 同一图片可以支持多个明确可见视角，但不能为了后续生图方便虚增视角。

## Selling Points

1. 每个卖点使用稳定 `sp-*` ID，完整记录“产品特征 -> 用户问题 -> 用户收益 ->
   使用场景”四段链，并通过 `source_claim_ids` 声明同一次 Research Worker 必须建立的
   事实。
2. `locked_wording` 保存不能被改义的口径；`forbidden_expansions` 保存容易产生
   夸大、产品替换或无证据因果的扩写。
3. 用户明确要求出现或内容决策必需的卖点标记 `must_use: true`。后续
   `content.json` 必须引用全部必用卖点 ID。
4. 营销形容词不自动当作事实。无法核实的内容进入 `missing_material` 或冲突记录。

## Material Source Rule

- 只读取 `task.json.product_links` 声明的产品链接。
- 用户图片和素材路径必须来自 `task.json.product_images` 与
  `task.json.material_paths`。
- 需要扩展来源时，只在 `material.json.allowed_source_urls` 中声明，并由同一次
  Research Worker 内的 `$xhs-research-strategy` 继续读取；不增加第二次模型调用。

## Required References

- `references/审核规则/事实来源规则.md`
- `references/审核规则/虚构内容禁止规则.md`
- `references/小红书内容规范/产品种草规范.md`
- `references/小红书内容规范/个性化学习规则.md`

## Schema Self-Check（提交前自检）

在写入 `material.json` 前，确认以下字段全部满足：

- [ ] `product_identity.variant` 字段存在（可为 `null`）；为 `null` 时 `unresolved_fields` 必须包含 `"variant"`
- [ ] `visual_identity` 字段存在，含 `visible_colors`、`visible_forms`、`distinguishing_features`
- [ ] `reference_image_strategy` 字段存在；使用本地真实参考图时写 `"local_reference"`，公开且容易识别、无需下载参考图时写 `"public_product_identity"`
- [ ] `selling_points` 至少 3 条，每条含 `id`（`sp-*`）、`product_feature`、`user_problem`、`user_benefit`、`usage_scenario`、`source_claim_ids`、`locked_wording`、`priority`、`must_use`、`forbidden_expansions`
- [ ] `forbidden_replacements` 中的词不得为正确产品名的子串（如产品是"iPhone 15 Pro Max"，则不得将"iPhone 15 Pro"列入禁用）
