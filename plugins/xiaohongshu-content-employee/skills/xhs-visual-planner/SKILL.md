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

1. `reference_image_strategy: local_reference` 时，每一个以产品为主体的页面都
   必须设置 `product_subject: true`，并绑定一张或多张真实产品参考图；该要求不只
   限于首图。`public_product_identity` 时，产品主体页可使用
   `product_view: identity-only`，并保持两个参考图数组为空。
2. `reference_image_ids` 与 `reference_image_paths` 必须按相同顺序对应
   `material.json` 中的 `product_reference_pack`。
3. `product_view` 只能选所绑定参考图 `supported_views` 明确支持的视角；身份-only
   页面不选择具体参考图视角，只保持公开产品身份。
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

## Cover Strategy（封面策略）

封面是小红书笔记的第一视觉钩子，直接决定点击率。以下规则强制封面质量：

### 背景禁止

- **绝对禁止纯色背景**——纯白、纯灰、纯黑、单色渐变底在缩略图中没有辨识度
- **绝对禁止空无一物的素底**——哪怕放了一台手机，如果背景是纯白墙面或抽象渐变，不通过
- 封面必须包含至少 2 个可辨识的环境元素（桌面材质、窗光、绿植、咖啡杯、书本、手部等）

### 推荐场景类型（按优先级）

1. **手持实景**（最高优先级）——一只手拿着产品出镜，背景是自然室内环境。让人感觉「有人正在用」
2. **桌面场景**——产品放在有生活气息的桌面上（木纹/大理石/织物），搭配 1-2 个氛围道具
3. **户外实景**——自然环境光下的产品，如咖啡店露台、公园长椅、城市街景
4. **产品特写 + 氛围光**——暗背景 + 柔和定向光照亮产品轮廓和关键材质（钛金属、玻璃等）

### 构图要求

- `subject_scale` 使用字符串描述约 `45%` 到 `65%` 的画面占比——产品不能过小（看不清）也不能过大（撑满无呼吸感）
- `text_zone` 统一设在「上方 1/3」或「下方 1/3」，给标题留出干净背景区
- 标题文字区不能落在产品表面上，也不能落在复杂的背景纹理上

### 开篇信息

封面的 `information_task` 必须包含两层信息：产品身份认知 + 本篇核心情绪。例如：
- ✅ "展示钛金属 iPhone 15 Pro Max 正面，咖啡馆暖光中手持实景，传达一个月使用的真实从容感"
- ❌ "展示产品正面外观，建立品牌认知"——太抽象，没有氛围

## Page-Level Quality（页级质量标准）

### 每张轮播图的视觉叙事

1. **页面间必须是「推进」关系**，不是同场景换文字。翻页时读者应看到新信息或新视角：
   - 封面 → 「这是什么东西」（场景 + 情绪）
   - 第 2 页 → 「上手第一感受」（手握/近距离）
   - 第 3 页 → 「核心功能场景」（使用中的姿态）
   - 第 4 页 → 「细节特写」（材质、工艺、接口）
   - 第 5 页 → 「使用场景」（环境中的产品）
   - 第 6 页 → 「收束信息」（品牌感或对比）

2. **产品可见性检查**：每张以产品为主体的页面中，产品在被缩略到 2cm 宽时仍应可辨认品牌和大致形态。如果缩略后只看到一团暗色，构图不通过。

3. **场景差异化**：全批保持共享配色与统一色温，同时使用 2-3 个协调的明暗或辅助色变化，避免每页都是完全相同的暖黄或冷白背景。

4. **文字安全区**：`text_zone` 指定的文字区域对应的画面位置，不能是有复杂纹理、杂乱物体或过亮/过暗的区域。

## Prompt Rule

最终 Prompt 采用阿道夫成品图的简洁写法，只保留：

1. 真实产品参考图和产品身份；非产品页不伪造产品外观。
2. 当前页的单一信息任务。
3. 一个真实感场景或清晰视觉方向。
4. 默认 2 组、最多 3 组短中文文案，以及简短的字体气质。
5. 必须在最终 Prompt 中明确写入 `3:4` 小红书成品图比例；这是发送给生图模型的
   Prompt 内容，不依赖代码在返回图片后补救尺寸。
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

## Schema Self-Check（提交前自检）

在写入 `visual.json` 前，确认以下字段全部满足：

- [ ] `style_anchor` 含 `palette`（数组，至少 3 个颜色）、`typography`、`visual_language`
- [ ] `pages` 每项含全部必填字段：`id`(`page-*`)、`page_role`、`shot_type`、`subject_position`、`subject_scale`、`background_scene`、`text_zone`、`information_task`、`prompt`、`product_subject`、`product_view`、`reference_image_ids`、`reference_image_paths`、`selling_point_ids`、`claim_ids`
- [ ] `reference_image_strategy: local_reference` 且 `product_subject: true` 的页面必须绑定参考图；`public_product_identity` 的产品主体页可使用 `product_view: identity-only` 和两个空参考图数组
- [ ] `prompt` 中明确写入 `3:4` 小红书比例
- [ ] 相邻产品页面在 `page_role`、`shot_type`、`subject_position`、`subject_scale`、`background_scene`、`text_zone` 中至少变化一项
