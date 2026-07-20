---
name: xhs-visual-planner
description: Compose Worker 在同一次 compose 模型调用中生成全部最终生图 Prompt、参考图映射和 visual.json。
---

# Xiaohongshu Visual Planner

本 Skill 与 `$xhs-copy-storyboard` 在同一个无历史 Compose Worker、同一次
compose 模型调用中执行。只读取 `material.json` 和 `evidence.json`，并使用本次
调用内共同生成的文案建立 `visual.json`。不得读取主对话、其他 Worker 对话或
未声明产物。

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
```

## Output Contract

```yaml
schema_version: 1
run_id: string
style_anchor:
  name: string
  palette: [string]
  typography: string
  visual_language: string
pages:
  - id: page-*
    information_task: string
    page_role: cover | product_focus | scene_story | information_card
    shot_type: string
    subject_position: string
    subject_scale: string
    background_scene: string
    text_zone: string
    prompt: string
    product_subject: boolean
    product_view: string
    reference_image_ids: [ref-*]
    reference_image_paths: [path]
    selling_point_ids: [sp-*]
    claim_ids: [claim-*]
```

## Product Fidelity

1. 每一个以产品为主体的页面都必须设置 `product_subject: true`，并绑定一张或
   多张真实产品参考图；该要求不只限于首图。
2. `reference_image_ids` 与 `reference_image_paths` 必须按相同顺序对应
   `material.json` 中的 `product_reference_pack`。
3. `product_view` 只能选所绑定参考图 `supported_views` 明确支持的视角。
4. 不得虚构产品背面、包装或内部结构。只有一个可靠视角时保持该视角，通过
   场景、景别、位置和信息任务变化画面。
5. 不以产品为主体的情境页或信息页可以使用空参考图数组，但不得画出一个无法
   由参考图支持的产品外观。

## Style And Composition

1. 全批只使用一个共享 `style_anchor`，锁定配色、字体气质和视觉语言。
2. 每页只承担一个独立信息任务，页数取最小必要集合。
3. 相邻产品页面必须在 `page_role`、`shot_type`、`subject_position`、
   `subject_scale`、`background_scene`、`text_zone` 中至少变化一项，不能把
   同一构图只替换文字后重复生成。
4. 构图变化不能改变产品身份、包装、Logo、颜色、比例或来源支持的产品视角。
5. 不用代码加字、抠图、叠图、背景替换、裁切或合成。
6. 每页选择一个真实感场景或清晰视觉方向，不把画面设计成参数表、流程图或
   纯色文字底板。

## Prompt Rule

最终 Prompt 采用阿道夫成品图的简洁写法，只保留：

1. 真实产品参考图和产品身份；非产品页不伪造产品外观。
2. 当前页的单一信息任务。
3. 一个真实感场景或清晰视觉方向。
4. 默认 2 组、最多 3 组短中文文案，以及简短的字体气质。
5. `3:4` 小红书成品图。
6. “其余构图和场景自由发挥”与“避免纯色信息卡”。

不得要求每张图生成 4 到 5 行精确中文，不得把规格、步骤或卖点逐条排成技术
清单。标题也直接由生图模型生成，HTML 不叠加任何标题或正文图片文字。

结构化字段只用于内部规划，不得逐项复述进最终 Prompt。尤其不得在最终 Prompt
中罗列 `style_anchor`、`page_role`、`shot_type`、`subject_position`、`subject_scale`、`text_zone`。
只把这些字段归纳成一句自然的场景和审美描述。

产品主体页使用真实参考图约束产品外观，但最终 Prompt 只简洁说明产品身份和
需要保持的识别特征，不复述参考图 ID、路径、`supported_views` 或内部字段名。

文案完成时，全部最终生图 Prompt、每页参考图对应关系和轮播结构也必须成为最终
版本。完整小红书文案、候选标题、轮播结构、全部最终生图 Prompt 和每页参考图
对应关系必须在同一次 compose 调用中完成。

## Prompt Package And Approval

Compose Worker 输出后，由薄主控展示完整 Prompt 包。展示内容包含共享
`style_anchor`，以及每页 `page_id`（取 `pages[].id`）、完整 Prompt、
`reference_image_ids`、`reference_image_paths` 和承担的信息任务。

运行时对上述稳定内容计算 `prompt_hash`，写入 `approval.json` 并等待用户批准。
只有 `approval.json` 中的批准哈希与当前 Prompt 包一致时，Produce Executor 才能
启动。Prompt、页面或参考图映射变化后必须生成新的哈希并重新获得用户批准。

## Required References

- `../../references/小红书生图知识/产品真实性.md`
- `../../references/小红书生图知识/提示词结构.md`
- `../../references/小红书生图知识/中文文字与信息卡.md`
- `../../references/小红书生图知识/封面设计.md`
- `../../references/小红书生图知识/轮播叙事.md`
