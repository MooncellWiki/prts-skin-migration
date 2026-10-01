# 悖论模拟改用档案类卡片（`paradox`）

2026-10-01 · `模板:悖论模拟` r403172（源文件 `模板_悖论模拟.wiki`）+ `模板:悖论模拟/styles.css`（源文件 `模板_悖论模拟_styles.css`）+
新建 `微件:AkComponents`（源文件 `微件_AkComponents.wiki`）· 脚本 `scripts/paradox_apply.py`；
黑字另改 `模板:Color` r429737（`scripts/theme_apply.py` 的 dark_mode_fix 一步）

状态：**已上线**（2026-10-01 22:14，BotCathPalug）。

## 问题

[空弦](https://prts.wiki/w/空弦#悖论模拟) 等干员页的「悖论模拟」在 Skin:Arknights 下：

- **暗色**：「解锁方式」小标签写的是 `color:#222; background:var(--prts-page-card-bg)`，变量有暗色值后成了深底深字，完全看不见；
  描述里的关卡效果行写成 `{{color|#000000|…}}`，深底黑字（310 次调用里 165 次，共 255 处，全是 `#000000`）
- **两种主题都有**：标题和描述包在 `<poem>` 里，皮肤 `base/typography.css` 把 `.poem` 画成引用块（左侧细线 + 缩进），
  深灰标题行里也多出一条竖线
- 结构是 Vector 时期的折叠 wikitable：`nomobile` / `nodesktop` 两份「关卡情报」入口（`nomobile-nodesktop响应式迁移方案.md` B 类）、
  首页的死类名 `mp-extranav` `mp-siteinfo` …（`首页迁移盘点.md` 建议顺手摘掉）、写死宽度的绝对定位块

设计系统早就给这个模板准备了替身：[档案类卡片 `.ak-archive`](https://github.com/MooncellWiki/prts-design)（`arknights/archive.css`，
`site/guide/templates.md`「现网模板 → 组件」一表里 `Template:干员密录` · `Template:悖论模拟` 那一行），线上皮肤已加载。

用量：310 页（308 个主名字空间）各调用一次，参数只用到 `name` `description` `精英化` `等级` `报酬内容1` `报酬数量1`；
`zoneName` / `stageName` / `picId` 只有 `/doc` 的示例在用，报酬全是合成玉 ×200；精英二 290、精英一 16、精英零 4。

## 改法

### 模板：照设计稿输出 `.ak-archive`

照设计稿干员页样例（prts-design `preview/_src/pages/operator.html`「悖论模拟」一节，比组件文档 `Archive/Record` 示例更具体）
逐个元素输出 HTML，参数不变，SMW `#set` 与分类原样保留：

```
.ak-archive.ak-not-prose.ak-host.prts-paradox
├─ __head   kicker「Paradox · 悖论模拟」+ 标题 + __req（「解锁方式」+ .ak-elite 精英图标「精英二 Lv1」）
├─ __body   <p>故事</p><p>关卡效果，术语加粗</p>（各段内换行保留：white-space: pre-line）
└─ __foot   .ak-stage 关卡卡片（PARADOX / 关卡情报 · 悖论模拟 · <name> · 前往关卡页 »）链到 悖论模拟_<name>
            +「首次通关奖励」+ .ak-item-list > .ak-item--sm（道具_带框_<名>.png + 数量角标）
```

与设计稿的差别只有两处：标题是 `<span>` 不是 `<h4>`（见下）；外层多了 `ak-not-prose`（`templates.md` 的规则）和 `ak-host` / `prts-paradox`。

- 标题用 `<span>` 不用设计稿的 `<h4>`：wikitext 里的 `<h4>` 会进目录、被包进 `.mw-heading`
- 精英图标按 `templates.md` 的约定用 `<img src="{{filepath:精英_N.png}}">`（现网文件与设计稿 `elite_N.png` 同一张 40×38 白线稿），
  直接做 `.ak-elite` 的子元素，组件的 16px 高度和亮色反相才套得上
- 描述不再包 `<poem>`：`.ak-archive__body p` 自带 `white-space: pre-line`，单换行原样保留；
  `<poem>` 产出的 `<br>\n` 在 pre-line 下会变成两次换行。310 处描述没有空行、没有以空格 / `*` / `#` / `:` 开头的行，不会被解析成别的块
- 故事和关卡效果分段：所有描述都是「故事行在前、`{{color|#000000|…}}` 开头的效果行在后」（108 页只有故事，165 页两者都有，没有交错、
  没有漏包 `{{color}}` 的效果行），内层 `{{#regex:…|/\n(?=<span style="color:[^"]*#000000)/|$0$0|1}}`
  把第一条效果行前的换行复制一份，解析器就断成两段。`#regex` 的替换串里 `\n` 不转义、直接写换行会被裁掉，只能用 `$0$0`
- 术语加粗：设计稿是 `<b>&lt;活性源石&gt;</b>`，条目里对应的是 `{{color|#000000|…}}` 包住的部分（游戏内的高亮色）。
  外层 `#regex` 把这些 span 换成 `<b>`，输出与设计稿逐字相同（样例就是「陈」）。正则里不能写 `|`（会被当成解析器函数的参数分隔，
  现网 parse 直接报 `ArgumentCountError`），所以用 `color:[^"]*#000000` 同时认 `模板:Color` 的新旧两种输出
- 关卡卡片：wikitext 写不出 `<a class>`，`.ak-stage` 写在外层 `<span>` 上，里面是 `[[悖论模拟_<name>|…]]`。
  这是模板写法的问题、不是组件通用样式，所以写在模板自己的 TemplateStyles 里，不进设计稿：链接是真盒子，照抄卡片的网格
  （`display` / 轨道 / 对齐 / 间距 `inherit`），横跨全部列铺满内容区；`::after` 铺满整张卡接点击，同设计稿首页的 `.mp-a`。
  **不能写 `display: contents`**：没有盒子的 `<a>` 在 Chromium / WebKit 里拖不出去（第一次上线的版本就是这么写的，见上线记录）。
  焦点环用皮肤自带的 `:focus-visible`，画在链接盒子上——设计稿 `.mp-a` 用 `:has()` 画在容器上，css-sanitizer 不认 `:has()` 也不认 `:focus-visible`。
  卡片内边距、编号字号照设计稿写在行内：css-sanitizer 不认 `font-size: var(…)`，MediaWiki 的行内样式认
- TemplateStyles 只有上面这一条
- 道具：照设计稿直接输出 `.ak-item`，图是 `{{filepath:道具_带框_<名>.png|80}}`（80px 缩略图，40px 显示，2x 屏清晰），
  `data-ak-tip` 悬停提示道具名；不链到道具页（设计稿也没有）
- `zoneName` / `stageName` 有值时写在关卡卡片的名称上（只有 `/doc` 用到），`picId` 背景图不再支持
- 不再默认折叠：卡片本来就不折叠，正文只有几行

### 其他皮肤：`微件:AkComponents` 用 JS 加载组件样式

Vector / Vector 2022 / Minerva 不加载设计系统组件。解析缓存各皮肤共用，模板输出只能有一份，所以照新首页（`微件:Mpstyle/newskin`）的做法，
抽成一个通用微件：模板根节点标 `ak-host`、写一次 `{{#widget:AkComponents}}`。以后其他模板（如 `干员密录`）直接输出组件时同样能用。

- 非 Arknights 皮肤上用 `RLQ` 的数组形式加载皮肤自己的 `skins.arknights.components` + `skins.arknights.fonts`（gzip 后约 25 KB + 35 KB，
  带版本号长缓存），加载完给 `.ak-host` 加 `ak-scope` 当作用域根。Arknights 皮肤上脚本第一行就返回
- 到位前 `.ak-host` 先 `visibility: hidden`，脚本没跑起来 3 秒后照常显示；无 JS 的访客不藏（看到的是无样式的文字）
- 旧 Vector / Minerva 的 `<html>` 不带 `skin-theme-clientpref-*`，令牌会跟随系统明暗，钉成 `<html data-theme="light">`（同首页）。
  不能钉在 `.ak-scope[data-theme]` 上：那条规则会给作用域根铺画布底色，盖掉卡片自己的 surface 底
- 一页里写多次只输出一份（Smarty 全局计数，同 `微件:SkinSwitchLink`）

结果：所有皮肤下都是同一张卡片。旧 Vector 下卡片占满正文宽（原来的表是 500px）。

### 描述里的黑字：`模板:Color` 加语义变量分支

与 09-29 的红字同一套做法（`主题适配盘点.md` §8）：`black` / `#000` / `#000000` → `color:var(--prts-page-text, 原值)`。
`--prts-page-text` 是 Common.css 已有的正文色变量，浅色 `#202122`（与 `#000` 看不出差别），暗色 / 自动 + 系统暗色 `#f0f0f0`；
旧 Vector 不带主题类，保持浅色值。改动登记在 `theme_apply.py` 的 dark_mode_fix 一步，能认出 09-29 / 09-30 两版底稿。

现网扫描（模板 / 微件 / 模块 / 主名字空间全量）：178 页 927 处用 `{{color|黑}}`（不算两个样式表注释里的写法）：

| 位置 | 处数 | 暗色下 |
| --- | ---: | --- |
| 悖论模拟描述（165 页） | 255 | 深底黑字 → 跟随正文色 |
| 关卡 / 敌人 / 地形 / 干员导航、Navbox 危机合约的分组名 | 514 | 不变：`Navbox/styles.css` 已有「暗底上跟随文字色」的规则 |
| `分析与考据/角色导航` | 142 | 桌面版是 Navbox，同上；手机版表头深底黑字 → 跟随正文色（见下） |
| 集成战略条目（ISW-NO 等）、`可抵抗状态`、`促融共竞计时`（Cbox2 里） | 十余处 | 深底黑字 → 跟随正文色 |

`角色导航` 手机版表头写的是 `background: var(--,#EBF7FE)`：`--` 不是合法变量名，浏览器整条丢掉（`CSS.supports` 为 false），
表头一直是皮肤的表头底色，浅蓝从来没显示过。所以它现网在暗色下本来就是深底黑字，改完反而能读。一度给它加了「固定黑字」，验证时发现是错的，已撤回。

## 验证

沙箱（`config.sandbox.toml`，`--from-live` 以线上正文为底，写入后 purge）：

| 页面 | 皮肤 / 主题 | 结果 |
| --- | --- | --- |
| 空弦 | Arknights 1440 浅色 | 卡片 790px 宽，结构与设计稿干员页样例逐元素一致；故事 / 关卡效果两段，两处术语加粗；精英图标反相为黑；关卡卡片 230×50，角落也点得到链接 |
| 空弦 | Arknights 1440 暗色（自动 + 系统暗色） | 关卡效果 `var(--prts-page-text)` → `#f0f0f0`；头部 `#232425` 底；关卡卡片 `#1a1b1c` 底；脚本不动作 |
| 空弦 | Arknights 390 浅色 | 卡片 366px，不溢出 |
| 空弦 | 旧 Vector 1440 浅色 | 两个模块 ready，加上 `ak-scope`，`<html data-theme="light">`；与 Arknights 浅色同一张卡片，链接无下划线 |
| 空弦 | 旧 Vector 1440 + 系统暗色 | 钉亮色生效：卡片白底 `#1d1f20` 字 |
| 空弦 | Vector 2022 1440 + 系统暗色 | 有 `clientpref-day`，不钉也是亮色 |
| 陈 / 黑角 | — | 陈：两段、1 处加粗；黑角（只有故事、精英零 Lv30）：一段，`#regex` 不改动 |
| 泰拉大典:Index（`角色导航`） | Arknights 390 暗色 | 手机版表头 `#f0f0f0` 字 / `#232425` 底 |
| 模板:悖论模拟/doc | — | `zoneName` / `stageName` 显示为关卡卡片名称「汐斯塔 火山洞窟」 |

截图：`build/shots/paradox-sandbox-arknights-{light,dark,390}-空弦.png`、`paradox-sandbox-vector-js-空弦.png`。

**没验证到的**：沙箱没装 MobileFrontend / Minerva，手机版要上线后在 m.prts.wiki 上看（同一套加载方式在新首页上线时验证过 Minerva）。

## 已知问题

- 窄屏下页脚按 flex 折行，「首次通关奖励」可能和道具图分到两行（设计系统 `.ak-archive__foot` 本身的行为，没在模板里改）
- 同一节上方的 `模板:干员密录` 还是旧的折叠表，设计稿里它也映射到 `.ak-archive`，没在这次一起改
- `模板:悖论模拟/styles.css` 的第一个版本 r432676 是第一版方案（TemplateStyles 手写回退样式）的样式表：那次上线在 21:54 被中断，
  中断前样式表已经建好、模板还没改，期间没有页面引用它。上线时直接覆盖

## 落地

```bash
uv run python scripts/theme_apply.py --only dark_mode_fix --dry-run --show-diff   # 只有 模板:Color 一页要改
uv run python scripts/theme_apply.py --only dark_mode_fix
uv run python scripts/paradox_apply.py --dry-run   # 新建 微件:AkComponents + 模板 diff
uv run python scripts/paradox_apply.py
```

改的是模板，线上会自动排 `htmlCacheUpdate` 刷新嵌入页（`模板:Color` 约 8000 页、`模板:悖论模拟` 310 页）；匿名访客另受 CDN 缓存影响（最多一小时）。
微件不算模板嵌入，但它只被 `模板:悖论模拟` 调用，模板改动会一并刷新这 310 页。

回滚：`模板:悖论模拟` 恢复到 r403172、`模板:Color` 恢复到 r429737；`微件:AkComponents` 留着无害（没人调用就不输出）。

### 上线记录

2026-10-01（UTC+8），按顺序：

| 时间 | 页面 | 修订 | 输出 |
| --- | --- | --- | --- |
| 22:14:30 | `模板:Color` | r429737 → r432680 | `reports/theme-apply/live-run-color-black.log` |
| 22:14:35 | `微件:AkComponents` | 新建 r432681 | `reports/paradox/live-run.log` |
| 22:14:40 | `模板:悖论模拟/styles.css` | r432676 → r432682 | 同上 |
| 22:14:45 | `模板:悖论模拟` | r403172 → r432683 | 同上 |

两个脚本再预演一次都是 0 页要改。purge 了空弦、陈、黑角、安赛尔、夜刀、泰拉大典:Index、ISW-NO 迷惘、`/doc` 8 页，其余靠自动排的 `htmlCacheUpdate`。

线上复测（URL 加随机参数绕过 CDN）：

| 页面 | 皮肤 / 主题 | 结果 |
| --- | --- | --- |
| 空弦 | Arknights 1440 浅色 | 两段、两处术语加粗；关卡卡片 230×50、角落可点；精英图标反相；道具图 80px 缩略图已加载 |
| 空弦 | Arknights 1440 暗色 | 术语 `#f0f0f0`；头部 `#232425`；关卡卡片 `#1a1b1c` |
| 空弦 | 旧 Vector（默认皮肤）1440 | 两个模块 ready、加上 `ak-scope`、`<html data-theme="light">`、kicker 用上 Bender 字体，与 Arknights 浅色一致 |
| 空弦 | Minerva（m.prts.wiki）390 | 同上，卡片 358px 不溢出；术语是 `#000`：手机版不加载 Common.css，变量回落到原值，手机版恒为亮色，符合预期 |

控制台没有这段脚本的报错。截图：`build/shots/paradox-live-{arknights-light,arknights-dark,vector,minerva}-空弦.png`。

**第二轮（22:27）**：用户发现关卡卡片拖不出链接（拖到标签栏开新标签页），设计稿样例能拖。第一轮 TemplateStyles 给链接写的是
`display: contents`，没有盒子的 `<a>` 在 Chromium / WebKit 里不算「按住的链接」；样例里是 `<a class="ak-stage">`，链接本身就是卡片。
改成真盒子（见「改法」），同时把术语加粗从 CSS 改成模板输出 `<b>`，TemplateStyles 只剩链接这一条。
一度考虑把链接写法收进设计稿 `stage.css`，按用户意见——这是模板写法的兜底、不是组件通用样式——留在模板里，prts-design 不改。

| 时间 | 页面 | 修订 | 输出 |
| --- | --- | --- | --- |
| 22:27:29 | `模板:悖论模拟/styles.css` | r432682 → r432690 | `reports/paradox/live-run-2.log` |
| 22:27:34 | `模板:悖论模拟` | r432683 → r432691 | 同上 |

再预演 0 页要改。线上复测（空弦）：链接是 grid 盒子，`dragstart` 落在 `<a>` 上、`text/uri-list` 是关卡页地址；卡片 230×50 与改前一致、角落可点；
描述两段、两处 `<b>`、不剩 span；Arknights 暗色 `<b>` 为 `#f0f0f0`；旧 Vector 同样可拖、链接无下划线。
