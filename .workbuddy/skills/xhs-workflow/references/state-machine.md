# 状态机与 Worker 映射

## 完整状态路径

```
created → prepared → evidenced → composed → humanizing → humanized
→ prompt_pending_approval → prompt_approved → producing → delivered → completed
```

## Worker 阶段 & 子 Agent spawn

### research-worker
- **触发 stage**：`created`
- **产出**：`material.json` + `evidence.json`
- **加载 Skills**：
  ```
  plugins/xiaohongshu-content-employee/skills/product-material-intake/SKILL.md
  plugins/xiaohongshu-content-employee/skills/xhs-research-strategy/SKILL.md
  ```
- **输入文件**：`task.json`
- **完成命令**：`finish-worker --run-dir <dir> --tokens <N> --tool-calls <N>`
- **下一 stage**：auto → `prepared` → auto → `evidenced`

### compose-worker
- **触发 stage**：`evidenced`
- **产出**：`content.json` + `visual.json`
- **加载 Skills**：
  ```
  plugins/xiaohongshu-content-employee/skills/xhs-copy-storyboard/SKILL.md
  plugins/xiaohongshu-content-employee/skills/xhs-visual-planner/SKILL.md
  ```
- **输入文件**：`material.json` + `evidence.json`
- **完成命令**：`finish-worker --run-dir <dir> --tokens <N> --tool-calls <N>`
- **下一 stage**：auto → `composed` → auto → `humanizing`

### humanize-worker
- **触发 stage**：`humanizing`
- **产出**：`content.json`（覆盖）
- **加载 Skills**：
  ```
  plugins/xiaohongshu-content-employee/skills/xhs-humanize-review/SKILL.md
  ```
- **输入文件**：`material.json` + `evidence.json` + `content.json`
- **完成命令**：`finish-worker --run-dir <dir> --tokens <N> --tool-calls <N>`
- **下一 stage**：auto → `humanized`

### approve
- **不是 Worker**，是用户审批步骤
- `continue` 到 `prompt_pending_approval` → 展示 prompt 包 → 用户 approve
- 命令：`approve --run-dir <dir> --hash <hash>`

### produce-executor
- **不是 Worker**，是自动 Executor
- 由 `continue` 触发（stage `producing`）
- 调用 `batch_generate.py` 并发生图
- 需要预先配置 provider

### deliver-executor
- **不是 Worker**，是自动 Executor
- 由 `continue` 触发（紧随 produce）
- 调用 `generate_delivery.py` 生成 HTML

## 合法 transition 速查

| 当前 stage | 允许迁移到 |
|-----------|-----------|
| `created` | `prepared` |
| `prepared` | `evidenced` |
| `evidenced` | `composed` |
| `composed` | `humanizing` |
| `humanizing` | `humanized` |
| `humanized` | `prompt_pending_approval` |
| `prompt_pending_approval` | `prompt_approved` |
| `prompt_approved` | `producing` |
| `producing` | `delivered`, `completed` |
| `delivered` | `completed` |
