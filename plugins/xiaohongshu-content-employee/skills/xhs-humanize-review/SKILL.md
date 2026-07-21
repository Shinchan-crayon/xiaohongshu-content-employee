---
name: xhs-humanize-review
description: 对小红书标题、正文和轮播文案降低 AI 痕迹，保留既有 JSON 结构、排版和追溯字段，只改可见文字。
---

# Humanize Xiaohongshu Copy

## Scope

Humanize Worker receives `material.json`, `evidence.json`, and an existing
`content.json` after Compose. It rewrites `content.json` in place exactly once.

Only edit these visible-copy fields:

- `titles[]`
- `post`
- `carousel_blocks[].text`

Do not change the JSON shape, add or remove fields, reorder arrays, alter
paragraph formatting, or modify any IDs, including `post_selling_point_ids`,
`post_claim_ids`, `carousel_blocks[].selling_point_ids`, and
`carousel_blocks[].claim_ids`. Do not read or modify `visual.json`.

## Rewrite Rules

Remove mechanical structures such as "表面上...但背后...", "看似...实则...",
"不仅...更...", "不只是...更是...", "总的来说", "综上所述",
"首先...其次...最后...", "需要注意的是", and "值得一提的是". Keep the
meaning, express points directly, and stop on concrete information instead of
adding a forced concluding uplift.

Replace or remove inflated wording such as "极致", "非凡", "卓越", "前所未有",
"惊艳", "完美解决", "彻底改变", "颠覆", "革命性", "赋能", "加持",
"升级体验", "焕新", "不可否认", "毋庸置疑", "毫无疑问", "绝绝子",
"yyds", "简直是", "堪称", "闭眼入", "无脑冲", and "必入". Prefer
specific everyday use, a plain judgment, or a direct product benefit.

Vary repeated openings and sentence patterns: do not leave more than three
consecutive sentences beginning with "你", more than two consecutive rhetorical
questions, or a mechanically fixed CTA ending. Reduce repeated em dashes and
repeated "但" or "但是" within a paragraph where doing so improves fluency.
Do not impose sentence-length limits, punctuation rules, paragraph splitting,
or any other formatting normalization.

Visible copy may freely use an account voice, invented everyday scenes,
first-person experience, social proof, comparisons, opinions, or engagement
hooks when these make the text feel more lived-in. When the draft uses "很多人",
"大家都", or "不少人反映", it may be rewritten as "我周围有朋友" as an
account-voice engagement device. There is no evidence gate for rewriting text.

## Preserve

Keep all existing fields, IDs, array order, and paragraph layout intact. Do not
change the JSON structure or visual Prompt. Natural subjective language,
invented personal experience, and one or more closing questions may remain.

Use concrete life scenes over abstract claims, keep each paragraph's existing
format, and make no detector score, report artifact, retry, or second review.
