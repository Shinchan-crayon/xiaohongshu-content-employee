---
name: xhs-workflow
description: 小红书内容员工编排技能。当用户要求运行小红书内容工作流、生成小红书图文、或操作 xiaohongshu-content-employee 插件时触发。该技能充当薄主控（thin orchestrator），调用 run.py CLI 推进 11 步状态机，在每个 Worker 阶段 spawn 无历史子 Agent。遵守 WorkBuddy × Codex 协作协议（锁文件、不改 state machine/contract、不自动生图）。
agent_created: true
---

# 小红书内容员工编排技能

## 定位

WorkBuddy 在本技能中作为**薄主控**。不做内容决策，不手写 Worker JSON 产物。只通过 `run.py` CLI 命令推进状态机，在每个 Worker 阶段 spawn 无历史子 Agent 完成研究/撰写/改写任务，然后调用 `finish-worker` 收口。机械阶段（produce/deliver）由 `run.py continue` 自动触发 Python 执行器。

## 项目路径

```
repo:   _development/xiaohongshu-content-employee/github-sync/
plugin: plugins/xiaohongshu-content-employee/
```

所有 CLI 命令均在 repo 根目录执行。子 Agent 读取的 Skill 文件路径使用绝对路径指向 `plugins/xiaohongshu-content-employee/skills/` 下对应子目录。

## 前置检查：生图配置

首次使用或缺少 provider 配置时，config.json 不存在或 default_provider 为 null → 在创建运行目录前完成：

```bash
python3 plugins/xiaohongshu-content-employee/scripts/生图工具/configure_provider.py --list
```

用户选择后引导输入 API Key。配置完成前不创建运行目录，不进内容流程。

## 标准执行流程

### Step 1 — Setup

```bash
python3 plugins/xiaohongshu-content-employee/scripts/run.py setup \
  --topic "<话题>" \
  [--product "<产品>"] \
  [--audience "<受众>"] \
  --output <交付目录>
```

记录返回的 `run_dir`。

### Step 2 — Continue 循环

每一步执行：

```bash
python3 plugins/xiaohongshu-content-employee/scripts/run.py continue --run-dir <run_dir>
```

根据返回的 `status` 分叉：

| status | 含义 | 操作 |
|--------|------|------|
| `worker_ready` | Worker 阶段，需 spawn 子 Agent | spawn Worker，等待产物，调 `finish-worker` |
| `advanced` | 中间状态自动推进 | 再次 `continue` |
| `pending_approval` | Prompt 待审批 | 展示 Prompt 包，等用户批准 |
| `completed` | 完成 | 返回最终交付 |
| `error` | 错误 | 查 `references/pitfalls.md` 解决 |

### Step 2a — Research Worker

`continue` 返回 `worker: research-worker` / `stage: created` 时：

spawn 子 Agent（参数见 `references/worker-spawn.md`），告知：
- 输入：`{run_dir}/task.json`
- 加载 Skill：`product-material-intake` + `xhs-research-strategy`
- 输出：`material.json` + `evidence.json`
- 必须加载完整 SKILL.md 和对应 `references/` 参考文件

子 Agent 写入两个 JSON 后，调用：

```bash
python3 plugins/xiaohongshu-content-employee/scripts/run.py finish-worker \
  --run-dir <run_dir> --tokens <N> --tool-calls <N>
```

状态自动推进：`created → prepared → evidenced`

### Step 2b — Compose Worker

`continue` 返回 `worker: compose-worker` / `stage: evidenced` 时：

spawn 子 Agent：
- 输入：`{run_dir}/material.json` + `{run_dir}/evidence.json`
- 加载 Skill：`xhs-copy-storyboard` + `xhs-visual-planner`
- 输出：`content.json` + `visual.json`
- **关键约束**：正文和全部 Prompt 必须在同一次 model call 中完成；`content.json.post` 必须是纯字符串；`carousel_blocks` 用 `id` 字段名

子 Agent 写入两个 JSON 后，调 `finish-worker`。

状态自动推进：`evidenced → composed → humanizing`

### Step 2c — Humanize Worker

`continue` 返回 `worker: humanize-worker` / `stage: humanizing` 时：

spawn 子 Agent：
- 输入：`{run_dir}/material.json` + `{run_dir}/evidence.json` + `{run_dir}/content.json`
- 加载 Skill：`xhs-humanize-review`
- 输出：覆写 `content.json`（只改可见文字，不改结构/追溯字段/visual.json）

子 Agent 写入后，调 `finish-worker`。

状态自动推进：`humanizing → humanized → prompt_pending_approval`

### Step 3 — Prompt 审批

`continue` 到 `prompt_pending_approval` 时，展示：
- `prompt_hash`
- `style_anchor`（palette、typography）
- 每页：`page_id`、完整 `prompt`、`information_task`

用户确认后：

```bash
python3 plugins/xiaohongshu-content-employee/scripts/run.py approve \
  --run-dir <run_dir> --hash <hash>
```

### Step 4 — Produce + Deliver（自动）

`continue` 触发 produce-executor → deliver-executor 自动完成生图和 HTML 生成。若生图 provider 未配置会在 produce 阶段报错，见「前置检查」。

### Step 5 — 完成

`status: completed` 时，只输出两个链接：

```markdown
已按"内容直出"规则完成，不再执行测试、复审、验图或截图。

- [小红书图文成品 HTML](<HTML_PATH>)
- [独立运行日志](<RUNTIME_LOG_PATH>)
```

不打开 HTML，不验图，不截图，不补充测试结论。

## Worker 约束

3 个 Worker 的硬约束（来自 `workflow-contracts.json`）：

- **fork_context: false** — 无历史独立会话
- **create/wait/close 各 1 次** — 结束后销毁
- **model_calls 恰好 1** — 每次 Worker 只能调一次模型
- **不可见主对话、其他 Worker、未声明产物**

Produce Executor 和 Deliver Executor 的 `model_calls: 0`，不创建 Worker。

## Codex 协作协议

1. 开工前发 `[LOCK]`，完成后 `[UNLOCK]`
2. **不改** `workflow_runtime.py` / `run.py` / `workflow-contracts.json` / 状态机
3. 不自动触发真实生图或付费请求（用户明确要求 + provider 已配置时除外）
4. 发布/同步/Git/版本更新 → Codex 收口

## References

- `references/state-machine.md` — 11 步状态机 + Worker 输入/输出/阶段映射
- `references/worker-spawn.md` — 3 个 Worker 的精确 spawn 提示词模板
- `references/pitfalls.md` — 7 个已知坑与解锁方法（finished_at/executor锁/子串等）
- `references/workflow-contracts.gz` — 完整产物 schema（压缩）
- 项目内 `plugins/xiaohongshu-content-employee/skills/` — 所有 Worker Skill 定义（spawn 子 Agent 时加载）
- 项目内 `plugins/xiaohongshu-content-employee/assets/workflow-contracts.json` — 原始 contract
