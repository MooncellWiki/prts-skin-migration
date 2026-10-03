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
