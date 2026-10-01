# 活动页英文副标题（`subname`）

2026-10-01 · 机器人账号 BotCathPalug · `微件:Subname` r275332 → r432625（源文件 `微件_Subname.wiki`）· 脚本 `scripts/subname_apply.py`

状态：**已上线**（2026-10-01 18:36），`模板:副标题` 的 406 个嵌入页已 purge。

## 问题

[集成战略「沉沦者的黑流树海」](https://prts.wiki/w/沉沦者的黑流树海) 在 Skin:Arknights 下标题被拆成
「集 ⟨THE BLACK FLOW OF THE DROWNING SEEKERS⟩ 成战略「沉沦者的黑流树海」」。

调用链：`模板:活动信息` 的 `副标题=` → `模板:副标题` → `微件:Subname`。微件用 JS 往 `#firstHeading` 里
prepend 两份副标题：

- `.fnameheader.nomobile`：`float:right; font-size:1em; white-space:nowrap`——Vector 下标题右侧一行小字；
- `.fnameheader.nodesktop`：半字号斜体，给 Minerva。

新皮肤的 h1 是 32px / 800 字重、正文栏更窄，这个不换行的浮动块有 782px 宽（h1 832px），一行里只剩一个字的位置。
手机（< 640，`legacy-device-classes` 显示 `.nodesktop`）同样不行：`nowrap` 继承下来，长副标题直接溢出屏幕。

用量：406 个页面（405 个主名字空间），SMW `副标题` 属性 391 个值，全是英文；最长的
`IDEAL CITY: CARNIVAL IN THE ENDLESS SUMMER IN RETROSPECT`，部分页面用 `override=` 带 `<br>` 手动断行。

## 改法

微件脚本开头加一个分支：`mw.config.get('skin') === 'arknights'` 时只 **append** 一个
`div.prts-subname.ak-en` 然后返回，不再生成那两份。

- 位置与样式全用皮肤现成的：`page-header.css` 的 `#firstHeading .ak-en`（块级、半字号、`--ak-fg-muted`、
  上边距 2px）+ `decor/type.css` 的 `.ak-en`（展示字体、大写、字距）。标题下方一行，暗色自动跟随。
- 不用 `fnameheader` 类，微件自己的 `div.fnameheader{float:right…}` 和 `Gadget-7thStyle2022` 的规则都碰不到它。
- 仍按 HTML 插入（与原写法同一套转义），`override=` 里的 `<br>` 照常生效。
- 必须在 JS 里分支而不是靠解析结果：解析缓存各皮肤共用。
- 旧皮肤分支一字未改，Vector / Vector 2022 / Minerva 渲染不变。

`text-transform: uppercase` 会把 `音律联觉` 系列等 8 个大小写混排的副标题显示成全大写（`Echoes of TERRA` →
`ECHOES OF TERRA`）。这是设计系统 `.ak-en` 的既定样式，未特意保留原大小写。

## 验证

沙箱（`config.sandbox.toml`，写入后 purge）：

| 页面 | 皮肤 / 宽度 | 结果 |
| --- | --- | --- |
| 沉沦者的黑流树海 | Arknights 1440 浅色 | 标题一行，副标题在下方一行；h1 高 77 → 60px |
| 理想城长夏狂欢季2023（最长 + `<br>`） | Arknights 390 暗色 | 副标题折成三行，`<br>` 生效，`scrollWidth` = 视口 390，无横向溢出 |
| 沉沦者的黑流树海 | Vector 1440 | `#firstHeading` 内 DOM 与线上逐字相同（两份 `.fnameheader`，`nomobile` 右浮动） |

截图：`build/shots/subname-after-arknights-1440.png` / `subname-after-arknights-390-dark.png`。

线上（写入 + purge 后）：沉沦者的黑流树海 Arknights 1440 与沙箱一致（`build/shots/subname-live-arknights-1440.png`）；
Vector 下仍是原来那两份 `.fnameheader`，无 `.prts-subname`。

purge 只清规范 URL 的 CDN 缓存，带 `?useskin=arknights` 的 URL 若事先被访问过，会在边缘缓存里多留最多 1 小时
（`s-maxage=3600`）；登录用户不走 CDN 缓存，立即生效。

## 落地

```bash
uv run python scripts/subname_apply.py --dry-run   # diff 只有新增的 Arknights 分支
uv run python scripts/subname_apply.py
```

微件不算模板嵌入，改完不会触发页面刷新，406 个页面要等解析缓存过期或手动 purge 才拿到新脚本：

```bash
uv run python scripts/purge_embeddedin.py 模板:副标题
```
