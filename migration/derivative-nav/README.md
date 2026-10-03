# 衍生作品导航手机版改手风琴（`derivative-nav`）

2026-10-03 · 机器人账号 BotCathPalug · 脚本 `scripts/derivative_nav_apply.py`

状态：**已上线**（21:14；新建 `模块:衍生作品导航` r433652、`模板:衍生作品导航/styles.css` r433653、`模板:衍生作品导航` r433654）。
沙箱先落地（`-c config.sandbox.toml --from-live`）。上线后用 `scripts/purge_embeddedin.py` 清了全部 433 个嵌入页的解析缓存，失败 0。

接在 `../mobile-table/README.md` 第一步后面：那一步把手机版表格的内容列从 65px 救了回来，但整张表仍然全部展开。

## 问题

`Runaway`（新皮肤 390）：手机版导航 50 行全展开，6874px 高，占整页 10035px 的 68%，而读者在这里多半只想看同组的其它作品。

- 表头路径只出现在每个 rowspan 的第一行，后面的行看不出属于哪个大类；出版物、音乐下各有一个「衍生作品」，长得一样。
- 条目是 `{{dot}}` 隔开的裸链接，会断在中间（`CRACK IN THE / ARK`），国旗和分隔点跟条目分家。

## 改法

手机版从 wikitable 改成手风琴，**只展开当前页面所在的那条路径**；桌面版 Navbox 一字未动。

- **模板**：手机版那张表按表头的 rowspan 还原成树，改写成 `{{#invoke:衍生作品导航|main|…}}`，写法同 `{{Navbox}}`
  （`groupN` / `listN`，子层 `listN` 里写 `{{#invoke:衍生作品导航|child|…}}`，没有 `groupN` 的 `listN` 是这一层自己的条目）。
  条目原样搬过去，脚本校验转换前后逐格一致。`<templatestyles>` 挪到模板最前面。
- **模块**（`模块_衍生作品导航.lua`）：
  - 展开状态在服务端算：在分组名和条目的 wikitext 里找指向当前页的 `[[链接]]`，路径上的各层不带 `mw-collapsed`。
    带 `#` 的章节链接不算（`Zone 10⁻⁸` 只展开 EP › 2019，不展开黑胶唱片）；大类总览页（`衍生作品/音乐`）展开对应大类。
    没有闪动，不依赖皮肤脚本。`<details>` 本站解析器不放行，折叠用 `mw-collapsible` 的自带开关位。
  - 五个大类总是折叠行；一组的内容超过 500 字，它的子组也各自折叠（音乐、EP、OST、单曲、出版物），
    不超过的平铺成「小标题 + 列表」（影像、游戏、线下活动、专辑）。自动判断，编者不用标。
  - 条目按 `{{dot}}` 切开各包一层 `.dnav-item`（inline-block），整项换行。
- **样式**（`模板_衍生作品导航_styles.css`，整页替换）：对齐 PRTS Design 的 Accordion（`.ak-details`）——标题左侧强调色的 + / −，
  展开的标题行换底色；记号用 Panel 同款的两条渐变拼，不依赖字体。整行是开关（44 / 40 / 36px 高），
  大类名本身是蓝链，点链接跳总览页、点行内其它位置开合。当前条目加底色和下划线。
  TemplateStyles 不收嵌套的 `var()`、`font-family: var()`、`:focus-visible`，写法都绕开了。
- 最外层的 `[折叠]` 去掉：全部收起只有 265px。根元素仍带 `nodesktop`，各皮肤的显隐规则照旧。

## 验证

新皮肤 390 宽，导航高度：

| 页面 | 展开的路径 | 改前 | 改后 |
| --- | --- | ---: | ---: |
| `Runaway` | 音乐 › 单曲 › 纪念曲 | 6874 | 1215 |
| `Summer Calling` | 音乐 › EP › 2026 | 同上 | 973 |
| `衍生作品` | 无（全部收起） | 39（整表折叠） | 265 |

- 展开路径：沙箱 15 页、线上 13 页（单曲 / EP 各年 / OST / 危机合约 / 出版物 / 影像 / 游戏 / 线下活动 / 总览页，
  含标题带括号、`&`、撇号的），展开的那一组都正好是当前条目所在的组；每页 454 个链接、40 个折叠行，无 Lua 报错。
- 交互：点行开合，`aria-expanded`、+ / − 跟着变；点标题里的链接不触发开合；回车可开合。
- 整页不撑宽（390）；`Runaway` 整页高 10035 → 4374。亮色、暗色都看过。
- ≥640：手机版隐藏、桌面 Navbox 照常（新皮肤、旧 Vector 1280）。旧 Vector 390 下 `.nodesktop` 本来就隐藏，不变。
- Minerva（`m.prts.wiki/w/Summer_Calling`，线上实测）：948px 高、整页 390、开合可用；`--ak-accent` 没有，记号回退成 `#36c`。
- Vector 2022 在 <720 下手机版、桌面版都不显示：Common.css 的兼容层一直如此（`.nodesktop` 恒隐藏），这次没动。

截图：`build/shots/derivative-nav-accordion-390-dark.png` / `derivative-nav-accordion-390-light-ep.png` /
`derivative-nav-accordion-minerva-390.png`，改前 `derivative-nav-redesign-current-390-top.png`。

## 落地命令

```bash
uv run python scripts/derivative_nav_apply.py --dry-run   # 先看 diff
uv run python scripts/derivative_nav_apply.py
uv run python scripts/purge_embeddedin.py 模板:衍生作品导航
```

## 没解决的

- 手机版和桌面版仍是两份手抄的数据，已经对不上（手机版 2023 年的 `Stained`、合作曲的 `Ripples` 各写了两遍，桌面版多几个空分组）。
  模块的参数写法和 Navbox 一致，下一步可以让桌面也由同一份参数输出，去掉 `nomobile` / `nodesktop` 双份。
- 「超过 500 字就折叠子组」是按字数估的：线下活动现在 440 字左右，再加几条就会从平铺变成两个折叠行。
