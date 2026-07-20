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
4. 无法确认的字段写入 `unresolved_fields`，后续 Worker 不得自行补全，也不得
   用相似产品型号、规格或变体补位。
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

- `../../references/审核规则/事实来源规则.md`
- `../../references/审核规则/虚构内容禁止规则.md`
- `../../references/小红书内容规范/产品种草规范.md`
- `../../references/小红书内容规范/个性化学习规则.md`
