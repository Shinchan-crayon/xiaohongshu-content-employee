# 已知坑与解决方案

## 1. finished_at 残留锁死

**现象**：finish-worker 校验失败后，再次 finish-worker 报"阶段已经完成"

**原因**：workflow_runtime.py 的 finish_stage() 中 finished_at 在 1838 行写入并落盘（1844 行），但 content 校验在 1852-1853 行 transition() 中才执行。校验失败时 finished_at 已残留。

**解决**：清除 runtime.json 对应 stage 的 finished_at：

```python
import json
p = '<run_dir>/runtime.json'
r = json.load(open(p))
del r['stage_metrics']['<worker_name>']['finished_at']
json.dump(r, open(p, 'w'), indent=2, ensure_ascii=False)
```

## 2. produce 阶段锁死

**现象**：continue 报"阶段已经启动：produce-executor"或"阶段已经启动：deliver-executor"

**原因**：executor 启动后失败（如缺少 provider 配置），但 stage_metrics 已创建，再次 continue 被锁。

**解决**：清除 executor 状态并回退阶段：

```python
import json
p = '<run_dir>/runtime.json'
r = json.load(open(p))
for key in list(r['stage_metrics'].keys()):
    if 'executor' in key:
        del r['stage_metrics'][key]
r['stage'] = 'prompt_approved'
json.dump(r, open(p, 'w'), indent=2, ensure_ascii=False)
```

## 3. forbidden_replacements 子串误判

**现象**：forbidden_replacements 含"iPhone 15 Pro"，title 含"iPhone 15 Pro Max"被拦截

**原因**：workflow_runtime.py:638 使用 Python `in` 子串匹配

**解决**：material.json 的 forbidden_replacements 不使用正确产品名的子串。如产品是"iPhone 15 Pro Max"，forbidden 应写"iPhone 14 Pro"而非"iPhone 15 Pro"。

## 4. 审批哈希不匹配

**现象**：approve 报"批准哈希与当前 Prompt 包不匹配"

**原因**：visual.json 在审批展示后又修改过

**解决**：再次 continue 重新生成 prompt_hash → 用户再次 approve

## 5. backup_topic_brief 格式错误

**现象**：continue 报"backup_topic_brief 必须是字符串"

**原因**：Research Worker 将 backup_topic_brief 写成了 `{topic_id, direction}` 对象

**解决**：改为纯字符串，格式：`"一句描述方向。备用选题：topic-xxx"`

## 6. post 字段是对象不是字符串

**现象**：deliver 报"post 必须是最终正文字符串"

**原因**：Compose Worker 将 post 写成了 `{"body": "...", "hook": "..."}`

**解决**：改为纯字符串，hook + body 拼接

## 7. product_subject=true 无参考图

**现象**：finish-worker 报"产品主体页必须绑定真实产品参考图"

**原因**：visual.json 中 product_subject: true 但 reference_image_ids/paths 为空

**解决**：无参考图时设 product_subject: false
