# Cbox2 整体换成设计系统正文提示框（`cbox2`）

2026-10-02 · `模板:Cbox2/core` r402751 → 源文件 `模板_Cbox2_core.wiki`，`模板:Cbox2` r309596、`模板:Cbox2/styles.css` r429675、
`模板:Cbox2/doc` r262393、`模板:复刻参阅` r402809、`孤星2024` r430674 · 脚本 `scripts/cbox2_apply.py`；
同批退役 `模板:Mbox2`（`scripts/mbox2_retire_apply.py`）

状态：**已上线**（2026-10-02 10:21，BotCathPalug）。

## 问题

`{{Cbox2}}` 是全站最常用的提示框（线上 embeddedin 8051 页；沙箱库直接调用 1397 处 / 702 页，主名字空间 621 处）。
它还是 Vector 时期的写法：整块行内样式、`nomobile` / `nodesktop` 双份渲染、825px 定宽，暗色靠 `Cbox2/styles.css` 里
按五个等级一条条 `!important` 压回去（`theme_apply.py` 的 cbox2 一步）。设计系统早就给它准备了替身：
[正文提示框 `.ak-cbox`](https://github.com/MooncellWiki/prts-design)（`components/cbox.css`，组件文档「与现网模板的对应」一节），线上皮肤已加载。

## 改法

### 模板：输出 `.ak-cbox`

```
.ak-host                                   其他皮肤上 微件:AkComponents 加 .ak-scope（同悖论模拟）
└─ .ak-cbox.prts-cbox2[.ak-cbox--tip|--warning|--danger][.ak-cbox--narrow][boxclass]   role="note"
   ├─ span.ak-cbox__icon                   {{mdi}} / {{fa}}，20px
   └─ div.ak-cbox__body                    div.ak-cbox__title + 正文
```

- **等级**：`lv` 0 → `--tip`、1 → 默认、2 / 3 → `--warning`、4 → `--danger`；`lv` 不填或不认识（现网有 8 处 `lv=5`）时按 `bg` 是不是某级的默认色推，
  都不是就是 1。与组件文档的对应表一致
- **参数原样交给 /core**：`模板:Cbox2` 不再按等级展开颜色和图标，`/core` 拿到的是调用方写的原值，能分辨「没填」和「填了默认值」
- **图标**：继续用 `{{mdi}}` / `{{fa}}`（`mdi=true` 走 MDI，否则 FA，`iconclass` / `moreclass` 照旧），线上两套图标字体在各皮肤都加载。
  组件文档建议的 sprite `<svg><use>` 在 wikitext 里会被转义、其他皮肤上也没有 sprite，用不了。
  不填 `icon` 时按组件的默认图标给 MDI 的对应线稿：tip → `arrow-top-right`、info → `information-outline`、warning / danger → `alert-outline`
  （原来是 FA 的 check / info / exclamation / times）。`line-height: 1` 让 20px 图标的中线对齐正文首行（实测都在 20px）
- **标题**：`.ak-cbox__title`（加粗、等级色），不再是 `<big>'''…'''</big><br/>`
- **正文**：照旧经 `{{#if:…|{{{text}}}}}` 输出——以 `*` `#` 开头的正文靠解析器补的换行成为列表（编辑页「用户页准则」那条就是有序列表）
- **宽度**：默认铺满正文栏；`narrow=1 / yes / true / 是` → `.ak-cbox--narrow`（最宽 640px）。原来的 825px 定宽和 `cbox-autonarrow` 去掉
- **单份 DOM**：去掉 `nomobile` / `nodesktop`，窄屏由组件负责
- 直接调 `/core` 的两处（`复刻参阅`、`孤星2024`）还在用 `content=` 和 `boxclass=`，都保留

### 自定义配色

`bg` 不是五个等级的默认色时（现网 126 处 `bg` / `bgleft` / `iconcolor` 三个一起改，大多是活动主题框：深色底 + 行内白字）：

- 框钉成亮色：`.ak-scope[data-theme="light"]`（设计系统的局部主题），框里的文字、链接用亮色令牌——这些颜色是按浅色方案挑的，
  和旧版暗色规则「自定义配色的框按浅色下的样子显示」一致
- `bg` 写在行内 `background` 上（压过 `.ak-scope[data-theme]` 铺的画布底，渐变也照样用），`bgleft` 写在图标井行内，`iconcolor` → `--_c`（图标与标题色）
- 边框透明：钉成亮色后组件的 1px 边框是亮色的浅灰，暗色页面上成了一圈白框
- 只改 `iconcolor`、`bg` 是默认色（用户页 12 处）：`--_c` 换色，其余跟随等级；只改 `bgleft`（用户页 9 处）不生效，同组件文档「`bgleft` 由 `--_c` 算出」

### 复刻参阅的紫色框

`复刻参阅` 和 `孤星2024` 的专项调查说明是同一个紫色渐变框，原来是行内自定义配色、暗色下再由样式表换成深色渐变。
钉成亮色后暗色版就没了，所以两处都不再传颜色，改由 `Cbox2/styles.css` 的 `.ak-cbox.rerun-reference-box` 给浅色 / 暗色两套（取值照旧），
「您将跳转到首次活动版」小标签暗色下照旧压暗。`孤星2024` 只改那一处调用的参数（`boxclass` 加上 `rerun-reference-box`）。

### 样式表

`模板:Cbox2/styles.css` 整页换掉：等级配色、明暗主题交给组件，只剩自定义配色框的边框、复刻参阅的紫色框、
暗色下正文里为浅色底写的行内深色字（`color:red` / `#9b2c3b` / `#47060f`，取值沿用旧版）。自动偏好（os）分支由 `wikibot/theme_os.py` 机械生成，
与 `theme_apply.py` 的 os_branch 一步结果相同（重跑无改动）。`theme_apply.py` 的 cbox2 一步和 `theme_css/cbox2.css` 已撤，否则重跑会把旧规则写回来。

### 其他皮肤

`{{#widget:AkComponents}}` 写在 `/core` 里，一页只输出一份。旧 Vector / Vector 2022 / Minerva 上用 JS 加载 `skins.arknights.components` +
`skins.arknights.fonts`，到位前 `.ak-host` 先藏（脚本没跑起来 3 秒后照常显示）。编辑页顶部的系统消息（`MediaWiki:Editpage-head-copy-warn`）
里的微件照样输出，模块照样加载。

## 验证（沙箱）

`config.sandbox.toml`，写入后 purge。沙箱页面拿不到 static.prts.wiki 的图标字体（被防机器人验证挡掉），截图时把同一份 MDI / FA 的 CSS 与字体放在本地临时加载。

| 页面 | 皮肤 / 主题 | 结果 |
| --- | --- | --- |
| 模板:Cbox2/doc | Arknights 1280 浅色 / 暗色 | 五个等级、窄版 642px、FA / MDI / 旋转图标、自定义配色框；暗色下等级色由令牌换好，自定义框保持棕底白字、无边框 |
| 模板:Cbox2/doc | 旧 Vector | 两个模块 ready、9 个 `.ak-host` 都加上 `ak-scope`、`<html data-theme="light">`，与 Arknights 浅色一致 |
| 多索雷斯假日2022（复刻参阅） | Vector 2022 暗色 | 深色渐变 `#1f3b46 → #332f56`、图标井 `#4b3c93`、小标签 `#6b1f1f`、正文 `#f0f0f0`、链接浅蓝 |
| 傀影与猩红孤钻 | Arknights 暗色 | 21 个框，3 个自定义配色：`#45260a` 底、白色标题、边框透明 |
| 新建页面的编辑页 | 旧 Vector（登录） | 系统消息里的框在 `.mw-parser-output` 内，组件模块 ready、`ak-scope`、心形图标正常 |
| PRTS:练习条目（Mbox2 改过来的） | Arknights 500 宽 | lv3 黄框，7 条列表，不溢出 |

截图：`build/shots/cbox2-ak-*.png`。

**没验证到的**：沙箱没装 MobileFrontend / Minerva，手机版要上线后在 m.prts.wiki 上看（同一套加载方式在悖论模拟上线时验证过 Minerva）。

## 外观上的变化（有意为之，跟设计系统走）

- 默认铺满正文栏（原 825px），窄版 640px
- 标题不再放大，改为加粗等级色；正文字号是组件的 `--ak-fs-sm`
- 不填 `icon` 的框换成线稿图标
- 1px 边框、不投影（原来是阴影托起）；lv2 / lv3 同为黄色一档（组件文档的约定）

## 旧类名的清理与适配

旧 `/core` 的类名（`.cbox2` `.cbox2-lv-N` `.cbox2-custom-color` `.cbox2-icon` `.cbox2-content` `.cbox2-mobile` `.cbox-autonarrow`）不再输出。
沙箱库全量扫描 + 线上搜索候选 1454 页逐页精确匹配，站内还写着它们的只有下面 7 页（另有一个用户沙盒自己拼的 `class="cbox2"`，不管），
由 `scripts/cbox2_legacy_cleanup_apply.py` 处理（2026-10-02 10:53 上线，`reports/cbox2/live-run-legacy.log`）：

| 页面 | 处理 | 修订 |
| --- | --- | --- |
| `MediaWiki:Common.css` | 删 Vector 2022 窄屏下 `.nodesktop.cbox2-mobile { display: flex }`（同块的 `.nomobile` / `.nodesktop` 规则不动） | r432728 → r432907 |
| `MediaWiki:Gadget-Vector2022Fixes.css` | 同上 | r403350 → r432908 |
| `MediaWiki:Gadget-Vector2022LayoutFixes.css` | 同上 | r410823 → r432909 |
| `MediaWiki:Vector.css` | 删 `div.cbox-autonarrow` 1500px 以下收窄到 640px（连同注释和删空的 `@media`） | r429238 → r432910 |
| `MediaWiki:Gadget-darkModeFix.css` | 删编辑页系统消息里 `.cbox2` 的暗色：同一段复制了 5 份，共 30 条、271 行。组件自带暗色，Vector 2022 暗色下实测正常 | r403842 → r432911 |
| `模板:孤星2024/styles.css` | 删专项调查说明框的两条暗色（改由 `Cbox2/styles.css` 的复刻参阅紫色框给），os 分支按剩下的 night 规则重新生成 | r429600 → r432912 |
| `岁的界园志异/事件一览` | **适配**：页面用 `{{#widget:style}}` 把「如岁：进入传说」等 12 个切换框限宽 35rem，选择器从 `.legend_switch .nomobile.cbox-autonarrow` 换成 `.legend_switch .ak-cbox` | r432775 → r432913 |

脚本只删「每个选择器都只针对旧类名」的规则，删完逐条比对其余规则不变、旧类名一个不剩，否则不写。线上复测：切换框 12 个都回到 560px；
孤星2024 的说明框暗色下是深色渐变、`#4b3c93` 图标井、`#f0f0f0` 正文。

## 遗留

- 三个 Lua 模块（`BaseSkillInfo`、`SplitFormat`、`RhodesFashion`）用 `mw.addWarning("{{Cbox2|…}}")` 在编辑预览里出提示，只有编辑者看得到，没单独看

## 落地

```bash
uv run python scripts/cbox2_apply.py --dry-run          # 6 页
uv run python scripts/cbox2_apply.py
uv run python scripts/mbox2_retire_apply.py --dry-run   # Navbox/doc、PRTS:练习条目 改 {{cbox2}}；删 Mbox2 三页；用户页不动
uv run python scripts/mbox2_retire_apply.py
```

改的是模板，线上会自动排 `htmlCacheUpdate` 刷新嵌入页（约 8000 页）；匿名访客另受 CDN 缓存影响（最多一小时）。
`孤星2024` 页面大，保存可能超过客户端 30 秒超时（沙箱上就是这样，实际已保存），重跑一次确认「已是目标内容」即可。

回滚：各页恢复到上面列的修订；`微件:AkComponents` 不动。

### 上线记录

2026-10-02（UTC+8），按顺序：

| 时间 | 页面 | 修订 | 输出 |
| --- | --- | --- | --- |
| 10:21:44 | `模板:Cbox2/styles.css` | r429675 → r432897 | `reports/cbox2/live-run.log` |
| 10:21:49 | `模板:Cbox2/core` | r402751 → r432898 | 同上 |
| 10:21:54 | `模板:Cbox2` | r309596 → r432899 | 同上 |
| 10:21:59 | `模板:Cbox2/doc` | r262393 → r432900 | 同上 |
| 10:22:04 | `模板:复刻参阅` | r402809 → r432901 | 同上 |
| 10:22:09 | `孤星2024` | r430674 → r432902 | 同上 |
| 10:22:22 | `模板:Navbox/doc` | r135162 → r432904 | `reports/cbox2/live-run-mbox2.log` |
| 10:22:27 | `PRTS:练习条目` | r429930 → r432905 | 同上 |
| 10:22 | 删除 `模板:Mbox2/doc`、`模板:Mbox2/core`、`模板:Mbox2` | — | 同上 |

两个脚本再预演一次都是 0 页要改。purge 了 模板:Cbox2/doc、PRTS:练习条目、多索雷斯假日2022、孤星2024、傀影与猩红孤钻、干员一览、模板:Navbox/doc、危机合约 8 页，
其余靠自动排的 `htmlCacheUpdate`。

线上复测（URL 加随机参数绕过 CDN）：

| 页面 | 皮肤 / 主题 | 结果 |
| --- | --- | --- |
| 模板:Cbox2/doc | Arknights 1280 浅色 | 9 个框的等级类与沙箱一致，图标字体原生加载、9 个都有字形；页面上已没有 `.cbox2` |
| 多索雷斯假日2022 | Arknights 暗色 | 复刻参阅框深色渐变、图标井 `#4b3c93`、小标签 `#6b1f1f`、正文 `#f0f0f0`，斜箭头与小标签里的三角图标都在 |
| 模板:Cbox2/doc | 默认皮肤（旧 Vector，未登录） | 两个模块 ready、9 个 `.ak-host` 都加上 `ak-scope`、`<html data-theme="light">`，与 Arknights 浅色一致 |
| PRTS:练习条目 | Minerva（m.prts.wiki）500 宽 | `ak-scope`、flex、7 条列表、图标在、不溢出；标题下不再多一个空行 |

截图：`build/shots/cbox2-ak-live-*.png`。
