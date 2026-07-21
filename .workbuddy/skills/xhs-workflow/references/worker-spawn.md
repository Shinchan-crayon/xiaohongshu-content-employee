# 子 Agent Spawn 指令模板

编排者在每个 Worker 阶段 spawn 一个子 Agent 完成产物写入。以下是精确的 spawn 指令模板。

## research-worker spawn

```
正在运行小红书工作流的 Research Worker。
你的唯一任务：读取输入文件，加载下方列出的 Skill 文件，产出 JSON 产物。

**输入文件**（绝对路径）：
{run_dir}/task.json

**需要加载的 Skill 文件**（用 Read 工具读取全部）：
{plugin_root}/skills/product-material-intake/SKILL.md
{plugin_root}/skills/xhs-research-strategy/SKILL.md
{plugin_root}/references/审核规则/事实来源规则.md
{plugin_root}/references/审核规则/虚构内容禁止规则.md

**你产出的 JSON 文件**（用 Write 工具写入）：
{run_dir}/material.json
{run_dir}/evidence.json

**schema 参考**：
{plugin_root}/assets/workflow-contracts.json

**Schema Self-Check 要求**：
- material.json 必须含 reference_image_strategy、visual_identity
- product_identity.variant 为 null 时 unresolved_fields 必须含 "variant"
- selling_points ≥ 3 条，每条含完整四段链
- evidence.json 的 backup_topic_brief 必须是纯字符串
- selected_topic_direction、selected_topic_claim_ids 必须存在

**汇报格式**：
完成后回复：material.json ({bytes} bytes) done, evidence.json ({bytes} bytes) done
如果有任何字段不确定或缺失，在回复中明确列出。
```

## compose-worker spawn

```
正在运行小红书工作流的 Compose Worker。
你的唯一任务：读取输入文件，加载下方列出的 Skill 文件，产出 JSON 产物。

**输入文件**（绝对路径）：
{run_dir}/material.json
{run_dir}/evidence.json

**需要加载的 Skill 文件**（用 Read 工具读取全部）：
{plugin_root}/skills/xhs-copy-storyboard/SKILL.md
{plugin_root}/skills/xhs-visual-planner/SKILL.md
{plugin_root}/references/小红书内容规范/标题规则.md
{plugin_root}/references/小红书内容规范/正文规则.md
{plugin_root}/references/小红书内容规范/封面与轮播规则.md
{plugin_root}/references/小红书生图知识/产品真实性.md
{plugin_root}/references/小红书生图知识/封面设计.md
{plugin_root}/references/小红书生图知识/轮播叙事.md

**你产出的 JSON 文件**（用 Write 工具写入）：
{run_dir}/content.json
{run_dir}/visual.json

**schema 参考**：
{plugin_root}/assets/workflow-contracts.json

**内容深度要求**（来自 SKILL.md 的 Content Depth 章节）：
- titles ≥ 5 个，覆盖 ≥ 4 类角度
- post 必须是纯字符串
- 每个卖点段落 ≥ 120 字，全文 ≥ 600 字
- ≥ 3 处可感知的具体细节（数字/场景/对比）
- carousel_blocks 用 id（不是 page_id）字段名

**视觉质量要求**（来自 SKILL.md 的 Cover Strategy / Page Quality 章节）：
- 封面禁止纯色背景，≥ 2 个环境元素
- 家具场景优先级：手持 > 桌面 > 户外 > 氛围光
- 产品占比 45%-65%
- 6 页色调 ≥ 2-3 种
- 翻页有明显视觉变化

**汇报格式**：
完成后回复：content.json ({bytes} bytes) done, visual.json ({bytes} bytes) done
如果有任何字段不确定，在回复中明确列出。
```

## humanize-worker spawn

```
正在运行小红书工作流的 Humanize Worker。
你的唯一任务：读取 content.json，按 Humanize 规则自然化改写，覆写同一文件。

**输入文件**（绝对路径）：
{run_dir}/material.json
{run_dir}/evidence.json
{run_dir}/content.json

**需要加载的 Skill 文件**（用 Read 工具读取全部）：
{plugin_root}/skills/xhs-humanize-review/SKILL.md

**你产出的 JSON 文件**（覆写，用 Write 工具写入）：
{run_dir}/content.json

**关键规则**：
- post 保持纯字符串
- 不删除 Composer 建立的场景锚点句
- 不引入 forbidden_replacements 中的词
- 不引入内部工作流术语

**汇报格式**：
完成后回复：content.json ({bytes} bytes) humanized done
```

## 变量替换

spawn 前，将模板中的以下变量替换为实际路径：

| 变量 | 来源 |
|------|------|
| `{run_dir}` | `continue` 返回的 run_dir（runtime.json 中的 run_id 目录） |
| `{plugin_root}` | runtime.json 中的 `plugin_root` 字段 |
