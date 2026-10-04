# 移动端表格（`mobile-table`）

总方案与清单归类见 `docs/移动端表格问题归类与适配方案.md`。这里记逐步落地的改动。

## 第一步：两个模板（2026-10-03）

`模板:衍生作品导航` + 新建 `模板:衍生作品导航/styles.css`（源文件 `模板_衍生作品导航_styles.css`）、`模板:Code` · 脚本 `scripts/mobile_table_apply.py`

状态：**已上线**（2026-10-03 10:34，BotCathPalug；`模板:衍生作品导航/styles.css` r433343、`模板:衍生作品导航` r433344、`模板:Code` r433345）。
沙箱先落地（r420768–r420770）。上线后用 `scripts/purge_embeddedin.py` 清了全部嵌入页的解析缓存（衍生作品导航 433 页、Code 117 页，失败 0）。
线上抽测：`Runaway`、`Renegade`（新皮肤 390：最窄内容格 364、表高 6874、整页 390；1280 下手机版表格仍隐藏、整页 1280）、`m.prts.wiki/w/Runaway`（Minerva：358、4948）、`沉沦者的黑流树海/零件`（代码框 366、整页 390），与沙箱一致。主域匿名页面另受 CDN 缓存（最多 5 h）。

覆盖清单 357 / 799 条：衍生作品导航 353 条、`模板:Code` 4 条。

### 衍生作品导航

#### 问题

音乐 / 衍生作品条目底部的导航（429 个页面嵌入）是 `nomobile` / `nodesktop` 双份写法：桌面是 `{{Navbox}}`，手机是一张手写的
wikitable。手机版表头最多叠 4 级（音乐 › OST › 危机合约 › 经典赛季），新皮肤 390 宽下列宽 35 / 48 / 87 / 133 / 65，
「经典赛季」那一格只剩 65px、749px 高，链接两三个字一行；整张表默认展开，13811px 高。

不能直接让手机也用桌面版 Navbox：条目是 `{{dot}}` 隔开的裸链接而不是 `<li>`，navbox-narrow 的换行规则管不到，390 下宽 517。

#### 改法

- 模板：手机版表格加 `derivative-nav` 类；`<templatestyles>` 放进手机版第一格（标题）——模板第一行就是 `{|`，前面不能插东西，
  放在第一格里样式排在其余各行之前。
- `styles.css`，只在 <640：`tbody` 改块、每个 `tr` 改 `flex-wrap`，同一行里的几级表头横排成一条（第二级起前面加 `›`，
  最后一级补满整行连成一条底色），内容 `flex-basis:100%` 占满下一行。

  格子不再是表格单元格，`border-collapse` 不起作用，所以只留下边线，颜色沿用各皮肤给单元格的边框色；`width:auto` 盖掉 th 上的
  `width="60px"` / `"80px"` 属性。
- 表格本身的 `display` 不动（行内 `display:table` 保留）：旧 Vector 用 `.nodesktop { display: none }` 藏这张表，样式里改 `display`
  会把它放出来。

#### 验证（沙箱，Chrome 移动模拟）

`Runaway`，同一页面去掉 / 加上 `derivative-nav` 类对比：

| 视口 | 改前 表宽 × 高 | 改前 最窄内容格 | 改后 表宽 × 高 | 改后 最窄内容格 | 整页宽（前 → 后） |
| ---: | --- | --- | --- | --- | --- |
| 360 | 368 × 13811 | 65 × 749 | 336 × 7210 | 334 × 56 | 380 → 360 |
| 390 | 368 × 13811 | 65 × 749 | 366 × 6874 | 364 × 35 | 390 → 390 |
| 430 | 406 × 13538 | 65 × 749 | 406 × 6433 | 404 × 35 | 430 → 430 |
| 639 | 615 × 7595 | 90 × 539 | 615 × 5173 | 613 × 35 | 639 → 639 |
| 640 | 手机版隐藏，显示桌面 Navbox | | 不变 | | |

360 下改前整页多出 20px：表格内容的最小宽度 368 大于正文宽 336。

- `衍生作品`（默认折叠）：折叠时只剩标题行 41px；展开 50 行都是 flex、整页 390；再折叠回 1 行。折叠按钮仍在标题格里。
- 暗色：表头底色、边线跟随主题。
- 旧皮肤：旧 Vector、Vector 2022 在 390 下这张表本来就是 `display:none`，不受影响。Minerva 沙箱里没有，在现网 `m.prts.wiki/w/Runaway`
  注入同样的样式：最窄内容格 38px（836px 高）→ 全部 358px，表高 12505 → 4948，整页 390 不变。
- ≥640 不在媒体查询里，各皮肤不变。

截图：`build/shots/derivative-nav-before-390.png` / `derivative-nav-after-390.png` / `derivative-nav-after-390-dark.png` /
`derivative-nav-minerva-390-after.png`。

### 模板:Code

#### 问题

代码框写死 `width:80%; min-width:600px`（外加 10px 内边距、2px 边框），容器不到 624px 时整个框撑出去：手机上模板文档页整页 636–653 宽，
代码行右侧被切。106 处嵌入，82 处直接调用全在行首（块级上下文），没有嵌在表格或 inline-block 里。

#### 改法

`min-width:600px` → `min-width:min(600px, 100% - 24px)`。减掉内边距和边框的 24px，最窄时整个框正好贴满容器。
容器 ≥624px 时就是 600px，与原来相同。

#### 验证（沙箱，`沉沦者的黑流树海/零件`，同一页面改回 `min-width:600px` 对比）

| 视口 | 正文宽 | 代码框 前 → 后 | 整页宽 前 → 后 |
| ---: | ---: | --- | --- |
| 390 | 366 | 624 → 366 | 636 → 390 |
| 640 | 550 | 624 → 550 | 669 → 640 |
| 768 | 678 | 624 → 624 | 768 → 768 |
| 1280 | 934 | 771 → 771 | 1280 → 1280 |

### 落地命令

```bash
uv run python scripts/mobile_table_apply.py --dry-run   # 先看 diff
uv run python scripts/mobile_table_apply.py
uv run python scripts/purge_embeddedin.py 模板:衍生作品导航   # 脚本只 purge 四个代表页，其余等任务队列太慢
uv run python scripts/purge_embeddedin.py 模板:Code
```

### 没解决的

- （已解决，见 `../derivative-nav/README.md`：手机版改成手风琴，`styles.css` 整页替换，本目录的源文件只留作记录。）
  导航整张表在音乐条目上仍是默认展开、近 7000px 高。手机上默认折叠要么改 `mw-collapsed` 的条件（会连带桌面以外的旧皮肤），
  要么等并回单份 Navbox 时一起处理。
- 长期按 `docs/nomobile-nodesktop响应式迁移方案.md` G 类并回单份 Navbox，前提是条目改成 `<li>`。
- `模板:Code` 里的 `magin:5px` 是笔误，从来没生效过，没动。

## 第二、三步：皮肤给正文表格包横滑外壳、放宽竖条（2026-10-03）

状态：**沙箱验证，未上线**。复测后不再作为主方案，只给真二维和归不了类的表兜底，上不上待定（见 `docs/移动端表格问题归类与适配方案.md` §4、§5）。
改动都没提交，收在两个仓库的 `git stash` 里（`table-fit: 手机正文表格横滑外壳 + 竖条放宽…`）：

- `prts-design`：新建 `packages/css/src/table-fit.js`（皮肤与预览共用，无依赖，ES5，同 `sidebar-tree.js` 的做法）；
  `packages/css/src/chrome/responsive.css` ≤639 那条 `table.wikitable { display:block }` 改写；参考皮肤 `skin/`（`skin.json`、
  `resources/skin.js`、`resources/table-fit.js` 软链）接上；文档 `site/content/tables.md`、`site/chrome/responsive.md`。
- `mediawiki-skins-Arknights`：`scripts/sync-design-system.sh` 的 FILES 加 `table-fit.js` 后同步；新建
  `resources/skins.arknights.scripts/tableFit.js`（`require` 设计系统脚本 + `wikipage.content` 时重扫），`skin.json` 的
  `packageFiles`、`skin.js` 各加一行。同步时顺带拷进来的上游别的改动（95aecdb 头图令牌、e37cd07 `.ak-body--flat`）已从皮肤工作区还原，
  只留表格这部分；`resources/design-system/README.md` 记的上游修订因此是同步时的 HEAD，提交前重新同步一次即可。

### 改法

只在 ≤639 生效，桌面不改 DOM：

1. **外壳**：`.mw-parser-output` 里的顶层表格包进 `div.ak-table-fit`（`overflow-x:auto; max-width:100%`），表格保持 `display:table`，
   超宽时在外壳里横滑。内容里的行内 `display:table`、`min-width:750px`、非 `.wikitable` 都管得住——原先的
   `table.wikitable { display:block; overflow-x:auto }` 让表格自己当滚动容器，被行内 `display:table` 一顶就失效（清单里 W 组 86 页中 81 页）。
   外壳接过表格的上下外边距（行内写在外壳上），表格自己的清零，与相邻元素照旧折叠。

   不包：单元格里的表、浮动 / 绝对定位、父元素是 flex / grid、作者已经单独包了横滑容器（只装着这一张表的 `overflow-x:auto` 祖先，
   如 `.ak-table-scroll`、`模板:敌方情报` 的 `.stage-enemy-table-scroll`）、`.navbox`（`模板:Navbox/styles.css` 的
   `table.navbox + table.navbox` 靠兄弟关系共用边线）、设计系统组件表（带 `ak-` 类而不是 `wikitable`）、Vue 挂载的子树、
   本身 `display:none`、`.ak-table-nofit` 及其内部。TabberNeue 的 `.tabber__panel` 虽然也是 `overflow-x:auto`，但装着别的内容，
   里面的表照包（不包的话整个面板跟着横滑，表格照样是竖条）。

   没包上的表（无 JS、被跳过的）仍走原来的 `table.wikitable { display:block }`：`.mw-parser-output table.wikitable:not(.ak-table-fit > table)`。
2. **宽度**（只写表格行内的 `width` / `max-width`，原值记在元素上）：
   - 行内百分比宽度不到 100%（`width:75%`）拉满；
   - **竖条**：有格子文字区不到 5em、可见文字 ≥5 个字、却自动折行 ≥2 次，就把表格放宽到外壳的 1.5 / 2 / 3 倍，直到没有竖条或到顶
     （不超过内容最大宽度）。折行按文本节点各自数行盒：手写的 `<br>`、列表项各占一行不算（`#09<br>2023年<br>10月7日` 这种日期格不是竖条），
     `display:none` 的悬浮说明没有行盒，也不算。
3. **重新量**：`ResizeObserver` 看外壳，宽度变了或高度变了（折叠展开、tabber 切换、图片加载）就在下一帧重量；只读阶段和写阶段分开批量做。
   转到 ≥640 时外壳 `display:contents`、改过的宽度还原；再转回来重新量。

### 验证（沙箱 Arknights 皮肤，Chrome，390 宽）

同一页面先量改后，再拆掉外壳、还原宽度量改前（即原来的 `display:block` 规则）。折叠全部展开。「竖条」= 上面的判据。

| 页面 | 外壳 | 拉满 / 放宽 | 整页宽 前 → 后 | 页高 前 → 后 | 竖条 前 → 后 |
| --- | ---: | --- | --- | --- | --- |
| 卫戍协议/2024/敌人一览/冰原武装 | 17 | 1 / 13（1098） | 696 → 390 | 11703 → 9092 | 62 → 0 |
| 危机合约/寻昼行动 | 5 | — | 762 → 390 | 7648 → 7646 | 0 → 0 |
| 异常效果图鉴/恐惧 | 4 | 3 / 1（732） | 390 → 390 | 7139 → 4199 | 14 → 0 |
| 切尔诺伯格_荒废工厂/历史合约 | 11 | — | 439 → 390 | 5302 → 5282 | 0 → 0 |
| 角色真名 | 14 | — | 751 → 390 | 21139 → 21321 | 0 → 0 |
| 乌萨斯的孩子们家具收藏包 | 2 | — | 471 → 465 ¹ | 8948 → 8885 | 0 → 0 |
| BF-1_这是第一关 | 9 | 0 / 4 | 549 → 390 | 7934 → 6762 | 9 → 3 ² |
| Runaway | 3 | — | 390 → 390 | 9792 → 7730 | 0 → 0 |
| 卡池一览/常驻标准寻访/2024 | 1 | 0 / 1（549） | 390 → 390 | 6330 → 6288 | 27 → 0 |
| 作战机制 | 22 | 0 / 6 | 587 → 390 | 69892 → 63454 | 44 → 0 |
| 黍的试验田/剧情 | 12 | — | 812 → 390 | 7836 → 7836 | 0 → 0 |
| 明日方舟：冬隐归路 | 6 | 0 / 1（1098） | 474 → 390 | 23880 → 20125 | 15 → 0 |
| 日暮寻路/活动公告 | 1 | 0 / 1（549） | 530 → 390 | 7576 → 7506 | 1 → 0 |
| 潘乔·萨拉斯 | 5 | 0 / 4 | 390 → 390 | 8055 → 6245 | 12 → 0 |
| 箱形恐鱼(装置) | 3 | — | 390 → 390 | 2540 → 2260 | 2 → 0 |
| CW-7_空中楼阁 | 4 | — | 390 → 390 | 4079 → 3886 | 1 → 0 |
| 阿米娅 | 18 | 0 / 2 | 2060 → 2060 ³ | 18626 → 17891 | 3 → 2 |
| 干员剧情一览/六星干员 | 8 | 0 / 7（1098） | 390 → 390 | 98555 → 36568 | 75 → 1 |

1. 剩下的 465 是道具导航 Navbox（453px）：沙箱的 `模板:Navbox/styles.css` 是旧版，没有 navbox-narrow 那段，线上已修。
2. 剩下 3 个是沙箱里「创建缩略图出错」的报错文字。
3. 立绘舞台的 `canvas`（未缩放 2048 宽、`transform:scale(0.25)`），与表格无关。

- **耗时**：拆掉外壳后整页重扫 + 量一遍，最慢 89ms（六星干员），其余 ≤40ms；只量不包 ≤5ms。第一版边包边读外边距，
  每包一张整页重排一次，角色真名要 254ms，改成先读后写后 5ms。
- **桌面不动**：1280 直接打开 0 个外壳。同一页先 390 包好、放宽，再把 iframe 拉到 1280：外壳 `display:contents`、14 处宽度全部还原，
  18 张表的位置尺寸与直接 1280 打开逐一相同。
- **tabber**：作战机制的表在 `.tabber__panel` 里，包上后面板不再整块横滑（scrollWidth 366），竖条清零。

截图：`build/shots/table-fit-kongju-before-390.png` / `table-fit-kongju-after-390.png`（恐惧 · 敌人能力表，75% 宽 → 拉满再放宽到 732）。

### 没解决的 / 要注意的

- **只测了 Blink**。`table-fixed-width` 当初是在 iOS WebKit 上出的事，上线前要在 Safari / iOS 上补测，尤其是外壳里的定宽表和 `display:contents`。
- 放宽后的表里，两三个字的短格仍可能一字一行（「其他」「普通」）：自动表格布局按各列内容最大宽度的比例分多出来的宽度，短列分不到。
  单元格上的 `min-width` Chrome 不认，`width` 又会把长文字列也当定宽，没处理。判据要求 ≥5 个字，有意不管它们。
- 没有 JS 之前（模块加载完成前）表格还是原来的样子：行内 `display:table` 的照旧撑宽，JS 跑完收回来。只是横向变化，不推挤下方内容。
- 包外壳会移动表格节点：表格里的 `<iframe>` 会重新加载；以 `table.parentNode` 为锚往前后插东西的站点脚本会插进外壳里。
  遇到个别页面有问题，给表格或外层容器加 `ak-table-nofit`。
- 上线路径：两个仓库提交 → 皮肤 vendor 进 `../mw` 重建镜像（同 `docs/nomobile-nodesktop响应式迁移方案.md` §4.1）。

## 第四步：撑破页面的表格包横滑外壳，写在内容里（2026-10-04）

脚本 `scripts/mobile_table_scroll_apply.py`（取稿 / 改写 / 写入）+ `scripts/mobile_table_scroll_measure.mjs`（浏览器里量）·
页面清单 `scroll-pages.txt`

状态：**已上线**（2026-10-04，BotCathPalug）。第一轮 09:49–09:57：86 个页面 210 张表、5 个模板；
第二轮 10:31（只在 WebKit 上撑破的）：再包 11 张表（新增 `推与拉` 一页），`保全派驻` 改一处模板参数。合计 87 个页面 221 张表。

不改皮肤。第二、三步的 table-fit 是皮肤脚本给全站表格包外壳，这里改成只在**量出来真撑破的那几张表**外面，
在 wikitext 里写一层 `<div class="ak-table-scroll">`（皮肤 `base/tables.css` 已有：`overflow-x:auto; max-width:100%`）。
表格本身一个字不动：行内 `display:table`、`min-width:750px`、定宽都留着，只是超宽时在外壳里横滑，不再把整页撑宽。

- 服务端输出，没有 table-fit 那几个问题：不依赖 JS，加载后不跳，不挪节点（表里的 iframe 不重载）；
- 旧皮肤不认这个类，外壳就是一个没有内外边距的普通块，Vector / Minerva 渲染不变；
- 只解决撑破，**不解决竖条**：表格进了外壳照样被压到内容最小宽度（预演里 24 页的外壳内还有竖条格）。
  竖条归 `docs/移动端表格问题归类与适配方案.md` §5 的换版式（下面第五步是第一个）。

### 哪张表要包：量出来的，不靠猜

1. `prepare`：取线上 wikitext，找出源码里的全部表格（`{|`、`{{{!}}`、`<table>`，含嵌套），给每张表的开头加
   `data-mt="序号"`，用 parse API 渲染（不保存）；
2. `detect`：把渲染结果换进现网页面（`?useskin=arknights`），在 390、360 两个宽度下找「最外层的、右边伸出正文栏、
   又没被滚动容器裁掉的元素」。带 `data-mt` 的表就是要包的；不带的是模板或嵌入页生成的，另行处理；
3. `fix`：只给量出来的顶层表格包外壳，再渲染一次；
4. `verify`：360 / 390 / 1280 下把「改前」「改后」两份渲染先后换进同一页面比对——手机上包过的表不再伸出、整页不变宽、
   外壳没有纵向滚动；1280 下每张表的位置尺寸、正文高度都不变；
5. `apply`：只写 verify 通过的页面，带 `baserevid`。

外壳有两种：

- `<div class="ak-table-scroll">`：外壳自带 `--ak-space-4` 的上下外边距，并把里面 `.wikitable` 的外边距清零，对普通
  wikitable 正好抵消，行距不变；
- `<div class="ak-table-scroll" style="margin:0">`：表格算出来的外边距不是 16px 的（不是 wikitable、行内写了 `margin`）用这种，
  外壳不再加边距，留表格自己的。27 张。

不自动包：嵌在别的表里的、浮动表、带 `ak-sticky-head` 的、开头不在行首的（列表缩进里的 `: {|`）、已经在外壳里的。

detect 量不出来的三页（表里的内容靠脚本生成——音频播放器、拼图样片，换进去的静态 HTML 不够宽）在真实页面上量过后写进脚本的
`EXTRA`：`音乐鉴赏/游戏内音乐一览`、`模板:音乐一览/doc`、`揭幕者们/筹委会委托`。

### 模板（`templates` 子命令）

表格由模板生成的，外壳写进模板：

| 模板 | 嵌入页 | 说明 |
| --- | ---: | --- |
| `敌方情报/pure` | 5 | 卫戍协议敌人一览，每页 13 张 14 列表 |
| `敌方情报/敌袭` | 4 | 沙洲遗闻 / 沙中之火的敌袭记录（`沙洲遗闻/战争浪潮` 嵌入自 `沙洲遗闻/敌袭记录`） |
| `特殊敌方情报` | 5 | IM-2、VS-2 等 |
| `家具主题总览` | 140 | 两张定高大图并排，手机上 716–775px 宽；本来放得下的主题页不受影响 |
| `推荐间隔/yostar` | 1 | |

沙箱验证（24 页，先还原模板 + purge 量基线，同一状态量两次确认稳定，再改 + purge 量）：手机上整页宽全部回到视口宽
（如冰原武装 696 → 390、丹青阁 787 → 390），新皮肤 1280、旧 Vector 1280 下每张表的位置尺寸、正文高度全部不变。

### 落地命令

```bash
uv run python scripts/mobile_table_scroll_apply.py prepare
node scripts/mobile_table_scroll_measure.mjs detect
uv run python scripts/mobile_table_scroll_apply.py fix
node scripts/mobile_table_scroll_measure.mjs verify
uv run python scripts/mobile_table_scroll_apply.py apply --dry-run -v
uv run python scripts/mobile_table_scroll_apply.py apply
uv run python scripts/mobile_table_scroll_apply.py templates            # -c config.sandbox.toml 先在沙箱跑
uv run python scripts/purge_embeddedin.py 模板:家具主题总览              # 其余四个模板同理
node scripts/mobile_table_scroll_measure.mjs live before|after          # 真实页面落地前后各量一遍
```

中间文件在 `build/mts/`（`prep/`、`detect.jsonl`、`fix/`、`verify.jsonl`、`live/`）。

### 悬浮说明

合约矩阵、作战机制等表里的 `.mc-tooltips`（tippy）挂在 `body` 上，不在外壳里，不会被 `overflow` 裁掉；
真实页面上包外壳前后各触发一遍，气泡的挂载位置、尺寸相同。

### 第二轮：只在 WebKit 上撑破的表

第一轮的 detect 只用了 Chromium。上线后用 Playwright 的 WebKit 在 390 下复测，114 页里还有 3 页被撑宽
（作战机制 432、保全派驻 862、月行水上 512），都是**写了定长宽度**的表（`width:30em`、类样式里的 500px、模板参数 `宽度=850px`）：
Blink 让皮肤 <640 的 `max-width:100%` 压住了，WebKit 把定长宽度当最小宽度——就是 `table-fixed-width` 当初那个问题，
那次迁移只改了行内的 px 宽度，em、类样式、模板参数里的没碰到。

detect 加了 `ENGINE=webkit MERGE=1`（在 Chromium 的结果上取并集），量出来再包：`月行水上/今日答案！` 8 张、`剧情角色一览` 1 张、
`推与拉` 2 张（嵌入到 `作战机制`）。`保全派驻` 的表由 `{{保全派驻周期任务|宽度=850px}}` 生成，按 `table-fixed-width` 的写法把参数改成
`min(850px, 100%)`（脚本里的 `MANUAL`）。

```bash
node scripts/mobile_table_scroll_measure.mjs detect
ENGINE=webkit MERGE=1 node scripts/mobile_table_scroll_measure.mjs detect
ENGINE=webkit WIDTHS=390,360 OUT=verify-webkit.jsonl node scripts/mobile_table_scroll_measure.mjs verify
```

### 上线后复测（真实页面）

- **整页宽**：落地前后各量一遍清单页 + 嵌入它们的页 + 模板嵌入页共 155 页（新皮肤 390，Chromium）：整页比视口宽的 115 页 → 6 页。
  两轮都落地后再量 116 页，Chromium、WebKit 结果相同：390 下只剩 `岁的界园志异/藏钱木盒`（412）；360 下另有
  `墟/PRTS御影手记`（385）、`游戏数据基础`（380–386）。外壳都没有出现纵向滚动。
- **外壳是不是空操作**：114 个真实页面，同一次加载里带外壳量一遍、页内拆掉外壳再量一遍。旧 Vector 1280、Minerva 390（章节全部展开）
  每张表的位置尺寸、正文高度、整页宽**全部相同**。新皮肤 1280 有 3 页正文高度差几像素：`月行水上/今日答案！` +8、`黍的试验田/剧情` +24、
  `游戏数据基础/en` −6——外壳是独立的格式化上下文，表格自己的外边距不再和相邻段落折叠（前两页的表不是 wikitable，用的是 `margin:0` 的外壳）。
- `采购中心`：517 → 390（页内 2 张 + 嵌入的 `采购中心/凭证交易所` 1 张）。

### 没解决的 / 要注意的

- **缩进里的表**（`: {|`、`:: {|`）没包：`岁的界园志异/藏钱木盒` 的「升级通宝」、`墟/PRTS御影手记` 的「最低兴味-倍率对照表」。
  外壳要另起一行，会把表格移出缩进，得连同列表结构一起改。
- **不是表格的**：`关卡一览/活动关卡`、`关卡一览/曲谱/sandbox`（402，`transform: scaleX(1.2)` 的标题）、`模板:敌人信息/level`、
  `模板:敌方情报pro`（418，130px 的 svg）、`岁的界园志异/钱盒预览`（614，定宽的行内块）。
- `特殊地形`、`特殊机制` 量不了：页面加载后会自己跳转一次，脚本的执行环境被销毁。`游戏数据基础` 360 下剩的 20 多像素多半来自它们。
- **只覆盖清单里的页面**。以后新写的同款表不会自动修好；要全站兜底还是得皮肤来（第二、三步）。
- **竖条没动**：进了外壳的表照样是内容最小宽度。预演里 24 页的外壳内还有竖条格（`模板:详细敌人一览`、`剧情角色一览`、`作战机制` 最多），归 §5 换版式。
- 外壳里 `position:sticky` 的表头会改为相对外壳吸顶；这批表里没有带 `ak-sticky-head` 的。
- WebKit 是 Playwright 的桌面 WebKit，不是真机 iOS Safari。

## 第五步：家具一览主题表改卡片（2026-10-04）

`模板:家具一览/styles.css`（新建，源文件 `模板_家具一览_styles.css`）、`家具一览` · 脚本 `scripts/furniture_list_cards_apply.py`

状态：**已上线**（2026-10-04 10:07，BotCathPalug；`模板:家具一览/styles.css` r434070、`家具一览` r434071）。沙箱先落地（r420828–r420829）。

### 问题

`家具一览` 的 9 张主题表（`.furniture-table`，8 张按年份的宿舍 / 活动室主题 + 会客室主题）有 7 列：
图标 / 名称 / 描述 / 实装时间 / 获取途径 / 整套氛围值 / 家具零件需求。390 宽下描述列只有 49–67px，一格二三十行（最长 40 行），
9 张表共 496 个竖条格，单张表最高 11743px。不撑破页面，所以横滑外壳帮不上；是 §5 归到「卡片」的那一类。

### 改法

页面在已有的 `{{#widget:style}}` 前加一行 `<templatestyles src="家具一览/styles.css" />`，表格的 wikitext 一个字不改。样式只在 <768 生效：

- 表格、`thead`、`tbody` 改块，每个 `tr` 是一张带边框的卡，用 grid 排：图标（100px）在左，名称（加粗）+「实装 日期」在右；
  描述占满一行；获取途径、整套氛围值、家具零件需求各一行，列名用 `::before` 写在左边（列是固定的，不需要脚本抄表头）。
- 表题行（`colspan` 那一格，折叠按钮在里面）保持一整条；列名行隐藏。两行表头在 tablesorter 跑完后会从 `tbody` 搬进 `thead`，
  选择器两种状态都写了（`thead > tr:nth-child(2)` / `:not(.jquery-tablesorter) > tbody > tr:nth-child(2)`）。
- 常驻主题那一行的淡绿渐变（页内 `.perm`）还在，变成卡片左侧的底色。
- 断点用 767 而不是皮肤的 639：640–767 之间正文栏 550–677px，描述列只有 104–150px，照样是竖条。
- 颜色用皮肤变量带回落值（`var(--ak-border, #c8ccd1)`），旧皮肤里也能用。

### 验证

| 环境 | 竖条格 前 → 后 | 9 张表的高度 前 → 后 |
| --- | --- | --- |
| 新皮肤 390（线上真实页面） | 496 → 0 | 63831 → 33237 |
| 新皮肤 360（线上真实页面） | 496 → 0 | 65091 → 33741 |
| Minerva 390（m.prts.wiki，线上真实页面） | 357 → 0 | 35618 → 30909 |
| 新皮肤 640 / 767（沙箱） | 313 → 0（640） | — |
| 新皮肤 768、1280，旧 Vector 1280 | 不在媒体查询里 | 1280 下 9 张表的高度与落地前逐张相同 |

- 暗色：边框、表题底色跟随主题。
- 手机上表头隐藏了，不能点列名排序；折叠照常。
- 图片是懒加载，卡片里图标位先占 100px。

截图：`build/shots/mts/furn-ak390-before.png`（改前）、`furn-live390-real.png`、`furn-ak360-guest-dark.png`、`furn-minerva390.png`。

### 没做的

- `家具一览/sandbox`、`家具商店` 等别的页面里同样结构的表没引这份样式；要用的话给表加 `furniture-table` 类并引入同一个样式页
  （列数、列序要和这里一致，列名是按第 4–7 列写死的）。
- 640–767 之间卡片是单列，比较高；要省高度可以在这个区间排两列。
- 页内 `{{#widget:style}}` 里的 `.perm` / `.flex-group` / `.furniture-table` 样式没并进样式页。

## 第六步：可露希尔推荐的台词表改两格上下排（2026-10-04）

`模板:采购中心/可露希尔推荐/styles.css`（新建，源文件 `模板_采购中心_可露希尔推荐_styles.css`）、`采购中心/可露希尔推荐` ·
脚本 `scripts/closure_lines_stack_apply.py`

状态：**已上线**（2026-10-04 14:04，BotCathPalug；`模板:采购中心/可露希尔推荐/styles.css` r434246、`采购中心/可露希尔推荐` r434247）。
沙箱先落地（r420839–r420840，沙箱页面先同步到线上 r434043）。

### 问题

`采购中心/可露希尔推荐` 是四张同款的两列表（通用 / 组合包 / 时装 / 家具）：行头是商品名，另一格是日文 + 中文两段台词。
「时装」那张的行头里有 `珊瑚海岸/II/III/IV/V/VI/VIII/IX/XI/XII/XIV/XVII/XIX/XXII` 这种串——Blink、WebKit 都不在 `/` 和拉丁字母之间断行，
整串是一个不可断的词，行头列的最小宽度就是 326px。390 宽下表格 449px（第四步已经包了横滑外壳，页面没被撑宽），
台词列只剩 121px：109 行里有 133 段超过 6 行，最长一段 24 行，整张表 33282px 高；横滑过去看到的是一大片空的行头和一条窄台词。
就是第四步「只管撑破不管竖条」剩下的那种，§5 归在「两格上下排」。

另外三张不撑破，台词列 224–297px，能读但也偏窄（组合包那张有 4 段超过 6 行）。

### 改法

页首加一行 `<templatestyles src="采购中心/可露希尔推荐/styles.css" />`，四张表加 `closure-lines` 类，别的一个字不改
（「时装」外面第四步包的 `ak-table-scroll` 留着：表不再超宽，外壳不起作用）。样式只在 <640 生效：

- `tbody`、`tr`、`th`、`td` 都改块：商品名是一条（靠左，底色沿用各皮肤的表头底色），台词占满下一行；
- 表格本身不动（行内 `display:table`、`width:min(835px, 100%)` 保留）；
- 格子不再是表格单元格，`border-collapse` 不起作用，只留下边线（同 `衍生作品导航`）；
- 行头 `overflow-wrap:anywhere`：屏幕比最长那串还窄时允许断开，不撑宽表格；
- 四张一起改，同一页的版式保持一致。

断点用皮肤的 639 而不是 `家具一览` 的 767：640 以上另外三张按表格排更省高度（639 下上下排比表格高 30% 左右），只有「时装」吃亏，见「没解决的」。

### 验证

沙箱真实页面，同一次加载里先量现状、再摘掉 `closure-lines` 类量一遍（= 落地前）。「台词列」是四张表里最窄的，「最长」是单段台词的行数。

| 环境 | 整页宽 前 → 后 | 「时装」台词列 前 → 后 | 「时装」最长 前 → 后 | 「时装」表高 前 → 后 | 正文高 前 → 后 |
| --- | --- | --- | --- | --- | --- |
| 新皮肤 360 | 360 → 360 | 121 → 334 | 24 → 7 | 33282 → 16907 | 69964 → 54551 |
| 新皮肤 390 | 390 → 390 | 121 → 364 | 24 → 7 | 33282 → 16367 | 66947 → 52211 |
| 新皮肤 639 | 639 → 639 | 279 → 613 | 9 → 4 | 15264 → 12893 | 38335 → 42244 |
| 新皮肤 390，WebKit | 390 → 390 | 121 → 364 | 24 → 7 | 33498 → 16385 | 65621 → 52337 |
| 新皮肤 360，WebKit | 360 → 360 | 121 → 334 | 24 → 7 | 33498 → 16907 | 68759 → 54569 |
| Minerva 390（m.prts.wiki，线上页面注入同样的样式） | 394 → 390 | 96 → 358 | 24 → 6 | 33264 → 14277 | 62427 → 46090 |
| 新皮肤 640 / 768 / 1280，旧 Vector 1280，WebKit 640 / 1280 | 不在媒体查询里：四张表的宽高、两列宽度、正文高度全部相同 | | | | |

- **线上真实页面复测**（上线后，同样的量法）：新皮肤 390 / 360 / 1280、旧 Vector 1280、WebKit 390、Minerva 390 六组数字与上表逐项相同（Minerva 这次是真实落地的样式，不是注入）。主域匿名页面另受 CDN 缓存（最多 5 h）。
- 落地前后的正文高度也和改之前的基线一致（新皮肤 390：66947；新皮肤 1280：29877；旧 Vector 1280：27229）——页首的 `<templatestyles>` 没有多出空段落。
- 行头里的 `{{简易折叠}}`（部分龙门币礼包等）收起、展开都正常；`{{popup}}` 照旧。暗色下底色、边线跟随主题。
- 旧 Vector 不是响应式的，390 下正文栏只有 165px：整页 644 → 406，不是目标环境。

截图：`build/shots/closure/`（`ak390-before.png` / `ak390-after.png` 线上页面注入前后，`sb390-fold-open.png`、`sb360-longhead.png`、
`sb390-longhead-dark.png`、`minerva390-after.png`）。量和截图的脚本：`build/closure/measure.mjs`、`shots.mjs`。

### 落地命令

```bash
uv run python scripts/closure_lines_stack_apply.py --dry-run               # 先看 diff
uv run python scripts/closure_lines_stack_apply.py -c config.sandbox.toml  # 沙箱（WIKI_USERNAME=Akdev）
uv run python scripts/closure_lines_stack_apply.py
```

### 没解决的

- **640–767**：「时装」还是表格，行头列 332–338px，台词列 217–339px，最长一段 11 行（640）。能读，但行头列一大半是空的。
  根子是行头里的不可断串，桌面 1280 下行头列同样占了 835px 里的 347px；要治本得改内容（`/` 后面加 `<wbr>`，或把 `/II/III/…` 改成带空格的写法）。
- 「两格上下排」里的另外 11 页（`后勤技能中间产物一览` 等）没动；这份样式是这一页专用的，没有做成通用的版式类。
- 以后往这页加新表，要带上 `closure-lines` 类才有手机版式。

## 第七步：黍的试验田/剧情 对话表改聊天版式（2026-10-04）

`模板:黍的试验田/剧情/styles.css`（新建，源文件 `模板_黍的试验田_剧情_styles.css`）、`黍的试验田/剧情` · 脚本 `scripts/story_chat_apply.py`

状态：**已上线**（2026-10-04 14:10，BotCathPalug；`模板:黍的试验田/剧情/styles.css` r434248、`黍的试验田/剧情` r434249）。沙箱先落地（14:02）。

### 问题

页面的 12 张对话表（`table.story`，全站只有这一页用）是 3 列：左头像 / 台词 / 右头像，每行只有一侧有头像，中间插通栏的教学提示（`td.tut`）。
页内 `{{#widget:style}}` 把表宽写死 800px。第四步给它包了横滑外壳，页面不再被撑宽，但 390 下只看得到左边 366px：
折叠时标题居中在 400px 处，只露出最后一两个字；展开后台词要横滑着读，右侧说话人的头像和名字在屏幕外。§5 里归在「其他，逐页看」。

### 改法

页面在 `{{#widget:style}}` 前加一行 `<templatestyles src="黍的试验田/剧情/styles.css" />`，表格的 wikitext 不改。

所有宽度：

- 表宽 `min(800px, 100%)`。正文栏不到 800px 时（640–890 的视口）表格收进正文栏，不再横滑；≥ 这个宽度与原来相同。
- 表里的链接、折叠按钮固定用浅色主题的链接色。表格底色写死是浅的，暗色主题下皮肤的链接色（`#5ddcff`）落在黄底上看不清。

<640 改聊天版式：

- 表格、`tbody` 改块，每个 `tr` 是两列网格。有内容的那格头像 `display:contents`，图和名字直接当网格项：头像在说话人那一侧，
  名字在上，台词在下成一个米色气泡（靠头像的那个角是直角）；空着的那格头像隐藏。
- 哪一侧说话认 `tr` 上行内写的浅色底（`tr[style*="background"]`）。不能只写 `[style]`：折叠再展开后 mw-collapsible 会给每个 `tr` 留下空的 `style` 属性。
  浅色底留着，右侧说话的行仍是一条浅色带。
- 教学提示还是通栏的棕色条，字小一号。
- 标题条：标题靠左，折叠按钮靠右。皮肤在展开后把按钮绝对定位到右上角，和折叠时差出一个内边距，这里固定成浮动（两处 `!important`）。
- 横滑外壳（第四步包的）没拆：表格不再超宽，外壳成了空操作。

### 验证

沙箱（真实 TemplateStyles 输出；`min()`、`[style*=]`、`display:contents`、`!important` 都通过了保存校验）。沙箱的页面是包外壳之前的版本，
带外壳的情况在现网页面上注入同一份样式量。Playwright 的 WebKit、Chromium 结果相同（`build/shujq/webkit.mjs`）：

| 视口 | 版式 | 表宽 | 台词宽 | 整页宽 | 伸出表格的元素 |
| ---: | --- | ---: | --- | ---: | ---: |
| 360 | 聊天 | 336 | 气泡 ≤245 | 360 | 0 |
| 390 | 聊天 | 366 | 气泡 ≤275 | 390 | 0 |
| 639 | 聊天 | 615 | 气泡 ≤524 | 639 | 0 |
| 640 | 表格 | 550 | 383 | 640 | 0 |
| 768 | 表格 | 678 | 511 | 768 | 0 |
| 1280 | 表格 | 800 | 633 | 1280 | 0 |

- 现网注入（新皮肤 390，12 张全部展开）：页高 8103 → 10848。台词一行从 39 个字变成 15 个字左右，换来的是不用横滑。折叠时每张表 31 → 49px。
- 桌面不变：现网新皮肤 1200、旧 Vector（手机上布局视口 1120）注入前后，12 张表和 232 个格子的位置尺寸、整页宽高全部相同。
- 640 以前要横滑（表 800、正文栏 550），现在表宽 550。
- 折叠 → 展开一轮后，右侧说话的行仍是 24 行；折叠按钮在两种状态下位置相同。
- Minerva（现网 `?useskin=minerva` 注入，390）：聊天版式正常，整页 390。
- 暗色：表格保持浅色底，名字链接、折叠按钮、脚注角标都是 `#0072a8`。

- **上线后复测**（现网真实页面，带横滑外壳）：WebKit 下新皮肤 360 / 390 / 639 / 640 / 768 / 1280 与上表逐项相同；Minerva 390 聊天版式、整页 390；
  旧 Vector 1280 仍是表格、表宽 800。Chrome 390：整页 390、页高 10848、12 张表宽 366、没有元素伸出表格、没有 TemplateStyles 报错。
  Playwright 的无头 Chromium 打现网取不到正文（换了 UA 也一样），Chromium 这一项用的是真 Chrome。

截图：`build/shots/mts/story-ak390-before.png`（改前）、`story-live390-real.png`（上线后）、`story-ak390-sandbox-webkit.png`、`story-ak360-dark-proto.png`、`story-minerva390-proto.png`。

### 落地命令

```bash
uv run python scripts/story_chat_apply.py --dry-run
WIKI_USERNAME=Akdev WIKI_PASSWORD=prts-sandbox-dev uv run python scripts/story_chat_apply.py -c config.sandbox.toml
uv run python scripts/story_chat_apply.py
```

### 没做的

- 页内 `{{#widget:style}}` 里的底色、边框没并进样式页。
- 横滑外壳没拆。拆掉可以把第四步记的「桌面正文高 +24px」还回去。
- `{{修正}}` 的标记在暗色下是深底浅字（模板自己的暗色规则），落在米色气泡里是一块深色，没动。
- 同一个人连续说几句时每句都重复头像和名字，没合并。

## 第八步：新人入门的折叠（2026-10-04）

`新人入门` · 脚本 `scripts/novice_akcollapse_apply.py`

状态：AKCollapse 标题**已上线**（2026-10-04 15:10，BotCathPalug，`新人入门` r434329；沙箱先落地）。折叠表格那一半改在设计系统里（`prts-design` 工作区，**未提交、未同步到皮肤**）。

页面上有两种折叠，手机上各有一个问题。

### 折叠表格：收起时标题格只有文字那么宽（设计系统）

「至纯源石」里的两张 `wikitable mw-collapsible mw-collapsed`。皮肤 <640 的 `table.wikitable { display:block }` 让单元格落在按内容收缩的匿名表格里
（`docs/移动端表格问题归类与适配方案.md` §3.1 记过的副作用）。收起时只剩一行标题，标题格就只有文字加按钮那么宽，右边露出表格自己的底色；
展开后内容是长段落，撑满，所以只有收起时难看。

| 390，新皮肤 | 表格 | 标题格（收起） | 标题格（展开） |
| --- | ---: | ---: | ---: |
| 我该怎么用源石？ | 332 | 171 | 329 |
| 我不给游戏充值能获取多少源石？ | 332 | 269 | 329 |
| 常见的基建技能组合参考 | 366 | 213 | 363 |

设计系统 `packages/css/src/chrome/responsive.css` ≤639 那条规则后面加了一条，收起时把行组撑满表格（`site/content/tables.md` 补了一句）：

```css
:where(.mw-parser-output table.wikitable.mw-collapsed) > thead,
:where(.mw-parser-output table.wikitable.mw-collapsed) > tbody { display: table; box-sizing: border-box; width: 100%; }
```

- 不加 `box-sizing: border-box` 的话合并边框多出 1px，表格会出横向滚动条。
- 前缀包在 `:where()` 里，优先级只剩一个标签：模板样式自己改了行组 `display` 的表（`家具一览` 的卡片版式等）照旧归模板管。
  不包的话皮肤这条会盖掉模板给 `thead` / `tbody` 的 `display:block`。

现网注入实测（新皮肤 390，皮肤还没带这条规则）：

| 页面 | 收起的表 | 标题行 前 → 后 | 其他 |
| --- | --- | --- | --- |
| `新人入门` | 3 张 | 标题格 171 / 269 / 213 → 329 / 329 / 363，与展开时同宽 | 「展开」按钮离右缘 170 / 72 / 162 → 12，展开、再收起位置不变 |
| `衍生作品` | 15 张可见（多数是多列表头） | 标题行 161–310 → 363 | 展开着的 8 张不变 |
| `家具一览` | 9 张 `furniture-table`（行组是模板给的 `display:block`），量了第 1 张 | 366，不变 | 行组仍是 `block` |
| `黍的试验田/剧情` | 12 张（不是 `wikitable`） | 不受影响 | |

四页都没有横向溢出，整页 390。带 `caption` 的折叠表没量。stash 里的 table-fit 改写的是同一条 `display:block` 规则，`stash pop` 时这里会冲突，要手工合。

### AKCollapse 标题：长标题压住箭头、掉出标题条（页面，已上线）

「干员职业」那组（`.novice-profession`）。页面自己的 `{{#widget:style}}` 把标题写死 `height:2em`，`微件:AKCollapse` 也没给右侧绝对定位的箭头留位置。
390 下 9 条里 3 条压在箭头上；字号放大到 112.5%（模拟系统大字号的手机）8 条压箭头、7 条折到第二行的字掉到标题条外面。

改法：页面那条 `{{#widget:style}}` 里加一条 <640 的规则，原规则不动——`height:auto; min-height:2em`，右内边距留 2.2em 给箭头（`width` 相应改成
`calc(100% - 2.7em)`，总宽不变），标题改 flex，折行的文字排在职业图标右边。

| 视口 | 压箭头 前 → 后 | 掉出标题条 前 → 后 | 标题条高 前 → 后 |
| ---: | --- | --- | --- |
| 360 | — → 0 | — → 0 | 后：7 条 64、2 条 42 |
| 390 | 3 → 0 | 0 → 0 | 全部 41.6 → 3 条 64、6 条 42 |
| 390，字号 112.5% | 8 → 0 | 7 → 0 | 全部 46.8 → 8 条 72、1 条 46.8 |
| ≥640（量了 845、1280） | 0 | 0 | 41.6，不变 |

- 沙箱里同一页面去掉新规则对比；360 只量了改后。标题条宽度前后相同（390 下 366），整页宽不变；点开、收起正常。
- 沙箱没有 MDI 图标字体，箭头宽 0，「压箭头」按线上箭头的位置（右缘 8.16px、宽 27.2px）算；带箭头的样子是在现网注入同样的规则看的。
- 其余几组 AKCollapse（`.novice-charinfo`、`.novice-charup`，`height:1.5em`）标题短，没出问题，没动。

- **上线后复测**（现网真实页面，新皮肤 390）：压箭头 0、掉出 0，标题条高 3 条 64、6 条 42；字号 112.5% 下同为 0；点开、收起正常；整页 390，没有报错。

截图：`build/shots/novice-akcollapse-before-390.png`、`novice-akcollapse-live-390.png`（上线后）、`novice-collapsed-table-after-390.png`（现网注入）。

### 落地命令

```bash
uv run python scripts/novice_akcollapse_apply.py --dry-run
WIKI_USERNAME=Akdev WIKI_PASSWORD=prts-sandbox-dev uv run python scripts/novice_akcollapse_apply.py -c config.sandbox.toml
uv run python scripts/novice_akcollapse_apply.py
```

### 没做的

- `微件:AKCollapse` 本身没改。33 个页面在用，各自用 `{{#widget:style}}` 覆盖了 `padding` / `height`，统一给箭头留位要逐页看。
