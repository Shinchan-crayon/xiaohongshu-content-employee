# 小红书内容员工

面向个人创作者的小红书图文插件，当前版本：`2.0.0`。

## 使用

```text
请使用 $xhs-content-employee，根据我提供的资料制作一套小红书图文内容。

内容目标：
产品或服务：
产品图片或素材链接：
已有文案：
参考内容：
目标用户：
账号语气：
```

## 唯一执行流程

`首次使用选择生图模型并保存 -> 选题已定 -> 一次生成文案和最终 Prompt -> Prompt 全批并发发送给所选模型 -> 图片返回 -> 立即生成 HTML -> 交付 HTML`

选题确定后不再展示或复审 Prompt，不执行质检、安全审计、验图、截图、浏览器
预览、状态台账、自动重试或中途确认。

## 首次选择生图模型

第一次使用时，插件会列出 ThinkAI Image 2、ThinkAI Nano、火山引擎
Seedream、OpenAI GPT Image、Google Nano Banana 和自定义渠道，并同时显示
具体模型与默认尺寸。用户选择并配置后保存为默认项，后续直接复用。

手动查看列表：

```bash
python3 scripts/生图工具/configure_provider.py --list
```

配置保存在 `config.json`，该文件不会进入仓库。

## Skill 组成

| Skill | 作用 |
| --- | --- |
| `xhs-content-employee` | 唯一公开入口和直接执行编排 |
| `product-material-intake` | 整理产品事实与素材 |
| `xhs-research-strategy` | 补充必要公开信息并确定选题 |
| `xhs-copy-storyboard` | 生成标题、正文、标签和轮播 |
| `xhs-visual-planner` | 一次生成全部最终 Prompt |
| `xhs-approved-image-generator` | 使用首次选择的模型全批并发生图 |
| `xhs-html-delivery` | 图片返回后立即生成 HTML |

## 能力边界

- 不自动发布到小红书。
- 不保存 API Key 到仓库。
- 不自动切换模型或图片渠道。
- 不为失败页面自动重试或补图。
