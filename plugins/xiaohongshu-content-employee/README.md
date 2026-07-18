# 小红书内容员工

面向个人创作者的小红书图文工作流。它把产品素材、事实来源、文案、配图和
独立 HTML 交付串成一个可恢复的内容流程。

当前版本：`1.9.0`

## 使用

```text
请使用 $xhs-content-employee，根据我提供的产品资料制作一套小红书图文内容。

内容目标：
产品或服务：
产品图片或素材链接：
已有文案：
参考内容：
目标用户：
账号语气：
```

首次使用会引导选择：

1. `existing_only`：只使用已有图片。
2. `ai_assist`：选择图片渠道、模型、尺寸和质量。

## 核心流程

`prepare -> evidence -> compose -> produce -> deliver -> completed`

- 整理用户提供的产品资料、网页和图片素材。
- 素材不足时按需检索，并建立事实来源记录。
- 生成候选标题、正文、标签、封面文案和轮播脚本。
- 使用已有图片，或经确认后并发生成整组配图。
- 输出可编辑标题正文、切换图片和预览封面的独立 HTML。

## Skill 组成

| Skill | 作用 |
| --- | --- |
| `xhs-content-employee` | 唯一公开入口和流程状态管理 |
| `product-material-intake` | 整理产品事实与素材 |
| `xhs-research-strategy` | 建立来源记录和选题候选 |
| `xhs-copy-storyboard` | 生成文案与轮播 |
| `xhs-visual-planner` | 生成参考图生图方案 |
| `xhs-approved-image-generator` | 并发生成和失败页重试 |
| `xhs-html-delivery` | 生成独立 HTML |

## 能力边界

- 不自动发布到小红书。
- 不把没有来源的产品事实写成确定结论。
- 不保存密码、访问令牌或 API Key。
- 图片渠道不可用时不私自切换渠道。
