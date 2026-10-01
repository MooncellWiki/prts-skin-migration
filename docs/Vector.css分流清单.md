# MediaWiki:Vector.css 分流清单

状态：**落地中**（2026-09-28 盘点；落地进度见 §7）

## 1. 为什么要分流

`MediaWiki:Vector.css`（46.3 KB，2026 行，321 条规则）只在 Vector 皮肤下加载。
实测两套皮肤下发的 `site.styles`：

| skin | 体积 | `navbox` 规则 | `pathnav2` 规则 | `hlist` 规则 |
| --- | --- | --- | --- | --- |
| vector | 33.9 KB | 44 | 3 | 20+ |
| arknights | 5.5 KB（只有 Common.css） | 0 | 0 | 0 |

粗算 321 条里只有约 56 条真正针对 Vector 的 chrome（`#mw-panel` `#p-personal` `.vector-menu-tabs` …），
其余约 265 条是**正文样式**。`首页迁移盘点.md` §3 把整页列为「随皮肤退役」，只对 chrome 那部分成立，
正文部分不分流就会像大家族 navbox / pathnav2 那样在新皮肤下静默塌掉。

用量数据来源：`cache/`（沙箱库 1929 个模板 / 微件 / 模块 / MediaWiki 页）+ 沙箱库主名字空间 18 506 个非重定向条目全文扫描。

## 2. 分流原则

| 去向 | 什么放这里 |
| --- | --- |
| **Common.css** | 跨模板 / 微件 / 站点 JS 共用的正文类（hlist、plainlist、lazyload …），或由 Common.js / 小工具动态插入的元素 |
| **TemplateStyles** | 只被一个模板族用到的类，挂在该模板（或模块 `frame:extensionTag`）上，随模板加载、随模板退役 |
| **皮肤** | 新皮肤已经接管同一件事、只差补一两条的（折叠表格 toggle 定位、navbox 宽度） |
| **作废** | Vector chrome、0 用量的 Wikipedia 遗留、皮肤已有等价实现的 |
| **待确认** | 功能层面要人拍板的（见 §4） |

Common.css 在 Vector 下也加载，所以**分流可以在切皮肤之前就落地**：规则加到 Common.css / TemplateStyles 后先和 Vector.css 并存（重复无害），确认新皮肤下正常再从 Vector.css 删除。

## 3. 逐段清单

行号对应线上 `MediaWiki:Vector.css` 当前版本。用量列格式：`条目 / 模板 / 微件`（只列非零项）。

### 3.1 作废

「作废」分三种情况，性质不同，删除时的风险也不同：

- **A · 死 CSS**：选择器在全站找不到对应 DOM。判定依据是沙箱库全量文本扫描（模板 / 微件 / 模块 / MediaWiki 名字空间 1929 页 + 其余所有名字空间 69 557 个非重定向页），类名一次都没出现。删掉没有任何可见影响。
- **B · Vector chrome**：DOM 只在 Vector 皮肤里存在（`#mw-panel` `#p-personal` `.vector-menu-tabs-legacy` …）。换皮肤后自然无处匹配。
- **C · 皮肤已接管**：DOM 在新皮肤下仍然存在、规则也会命中，但新皮肤对同一件事已有自己的设计（wikitable、行高、标题、折叠 toggle）。这类是**主动放弃 Vector 的做法**，不是无效 CSS；要是觉得皮肤做得不对，应该改皮肤而不是把 Vector 规则搬过去。

#### A · 死 CSS（全站无 DOM）

| 行 | 内容 | 扫描结果 |
| --- | --- | --- |
| 508–519 | `.custom-img-comment` | 0 |
| 643–1111 | mbox 全家：ambox / imbox / cmbox / tmbox / fmbox / dmbox / compact-ambox、`div.mw-warning-*`、`#siteNotice div` `#wpSummary` | `class="ambox…dmbox"` 全部 0；只有 `模板:Ombox/core` 自己带 `ombox`，而 `{{Ombox}}` 全站 0 次调用 → 连模板一起删（§4 第 5 条） |
| 1113–1130 | `.nonumtoc` | 0 |
| 1131–1144 | `.toclimit-*` | 主名字空间 0；只有 8 个用户页（ns 2，ZheiZhei / 洛零 的沙盒）在用，可接受 |
| 1146–1182 | `.copyvio-*` | 0 |
| 1225–1229 | `.centertable` | 0 |
| 1251–1254 | `.vega .canvas` | `class="vega"` 0，Graph 扩展已停用 |
| 1276–1281 | `.tl-splink` | 0（只在 Vector.css / Mobile.css 里互相引用） |
| 1378–1429 | `.tbui-paginator` | 0 |
| 1469–1508 | 注释掉的热门评论 / 圣诞帽 | 注释块 |
| 1510–1564 | `.infobox` 全套 | `class="infobox"` 0 |
| 1605–1635 | `.references-2column`、`div.columns` | 0 |
| 1768–1770 | `.same-bg` | 0（只在 gadget CSS 里互相引用） |
| 1924–1928 | `.spine-background` | 只有 `微件:Garansandbox2` 和一个用户 common.css |
| 1930–1945 | 全站灰阶（注释） | 注释块 |

#### B · Vector chrome（DOM 只在 Vector 存在）

| 行 | 内容 |
| --- | --- |
| 3–24 | `.mw-body` 背景、用户页 / 提交页背景 |
| 26–37 | Echo 通知图标 / `#p-personal` 标题颜色 |
| 39–63 | `#MenuSidebar` 二级菜单、`#ca-talk` 橙色 |
| 124–134 | `#pt-uls` 图标反色、`#searchInput` 白底 |
| 135–239 | `nav.vector-menu-tabs-legacy` 全站 Tabs、`#mw-head`、`#mw-panel`、body 背景、`#p-personal` |
| 1184–1187 | `#page-content #catlinks` |
| 1345–1348 | `#p-personal ul` |
| 1946–1948 | `#ca-talk` |
| 1961–1966 | `#footer-poweredbyico` |
| 1968–2026 | `body.skin-vector-2022` 专用块（equip-selector、wikitable refresh） |

#### C · 皮肤已接管（DOM 存在，新皮肤另有设计）

| 行 | 内容 | 皮肤里对应的位置 |
| --- | --- | --- |
| 360–366 | `table.wikitable th` 半透明底、`--color-base` | `design-system/base/tables.css` |
| 503–506 | `.mw-collapsible-toggle { z-index:50 }` | `design-system/base/collapsible.css`；若发现 toggle 被盖住再在皮肤里补 |
| 553–556 | `#mw-content-text { line-height:1.6 }` | `typography.css` `--ak-lh-body` |
| 558–566 | `li.toclevel-1` / `h2` 加粗 | `typography.css` 标题层级 |
| 576–583 | 隐藏首页 `h1.firstHeading` | `mainpage.less` `.ak-layout--mainpage .ak-page-heading`；差别是只管真正首页的 view，不再覆盖 `首页_sandbox` 与 submit 预览 |
| 1212–1223 | `.mw-datatable.TablePager`、`.wikitable{max-width;display}` | `tables.css`、`skinStyles/mediawiki/special/` |
| 1242–1249 | `.iteminfo` `.itemhover` | 不是皮肤，是 `模板:显示弹出/styles.css` 已有带 `.display-popup` 作用域的等价规则。`微件:ShopList` 自己输出 `itemhover` 但没有 `display-popup` 容器，要给它补容器类，否则这两条退到 Common.css |
| 1283–1343 | MultimediaViewer 半透明 / 信息栏 | 扩展 UI；要主题化走 `skinStyles/` |
| 1350–1355 | wikitable MD 化阴影圆角 | `tables.css` |
| 1578–1581 | `.flow-ui-load-overlay { pointer-events:none }` | 移动端修正，Minerva 退役 |
| 1583–1601（部分） | `ol.references` 90% 字号、`li:target` 高亮 | `design-system/base/references.css`；其余见 §3.3 Reflist |

### 3.2 进 Common.css

| 行 | 内容 | 用量 | 说明 |
| --- | --- | --- | --- |
| 348–358 | `table.logo` / `table.logo-top` 水印 | 模板 6 / 微件 8 | 跨模板微件，含 `media.prts.wiki` 图片 |
| 568–574 | `body.ns-2600` 隐藏评论 | — | Comments 扩展 × Flow 名字空间，皮肤无关 |
| 585–597 · 1756–1766 | `.plainlist` | 模板 2 / 模块 8 | `模块:Navbox` `NavboxV2` 输出 |
| 1231–1240 | `.spoiler` | 条目 7 / 模板 4 / 微件 2 | `蚀刻章展示`、`防剧透`、`MedalShowcase` 三家共用，TemplateStyles 要写三份 |
| 1266–1274 | `.tl-idnav a` 白字 | 模板 4 | `Pathnav2/core`、`Navigator/plot`、`Navigator/enemy` 两个模板族共用；备选：都 `src=` 同一个 `Pathnav2/styles.css` |
| 1573–1576 | `section.lst{display:none}` | 条目 2 | LST 标签兜底，1 行 |
| 1643–1673 | `.nowrap` `.nowraplinks` | 模块 3 | `模块:Navbox` 输出 `nowraplinks` |
| 1675–1755 | `.hlist` `.hnum` 全套 | 条目 546 / 模板 25 / 模块 4 | navbox 横排链接的根基。**皮肤 `catlinks.css:57` 已有一条简版 `.hlist li::after`，与这套冲突，建议皮肤删掉那一条** |
| 1908–1912 | `.noedit .mw-editsection` | 模块 1 | `模块:Navbar` 输出 |
| 1914–1922 | `.lazyload` 渐入 | 条目 7 / 微件 9 | `Crisis v2`、`Collapsible-block/lazyload` |
| 1946–1953 | `.mw-collapsible-dark th` / `.mw-collapsible-text` | 条目 57 / 模板 14 | 并入 Common.css 205 行已有的 `.mw-collapsible-dark` 块 |
| 1955–1959 | 反馈板 Flow 下拉刷新图标 | — | 皮肤无关（已拍板：需要） |
| 240–286 | `.uls-language-list` 裁剪语言列表、隐藏搜索框 | — | ULS 扩展 UI，皮肤无关（已拍板：需要） |
| 1431–1467 | `.tbui-popupdialog` `#tbui-popupclose` 全站弹窗 | 0 | 已拍板：需要。但注意 `MediaWiki:PopupNotice` 目前没有任何页面或脚本引用它（全站扫描只有它自己和 Vector.css），等于停用状态，进 Common.css 只是保证以后启用时不缺样式 |

`Gadget-Vector2022LayoutFixes.css` 16–124 行已有 nowrap / hlist / plainlist 的现成版本，去掉 `body.skin-vector-2022` 前缀即可用。

### 3.3 进 TemplateStyles

| 行 | 内容 | 用量 | 目标页 | 说明 |
| --- | --- | --- | --- | --- |
| 336–346 | `.fuzzy` | 条目 95 | `模板:模糊/styles.css`（新建） | `Vector-2022.css` 240 行也补过一份，一并作废 |
| 521–551 | `.template-semicollapse*` | 条目 1 / 模板 2 / 微件 1 | `模板:半折叠/styles.css`（新建，`半折叠/before` 挂） | |
| 599–641 | `.heimu` 黑幕基础态 | 条目 29（`{{黑幕}}`）/ 模板 2 | `模板:黑幕/styles.css`（新建） | **不能**并进 `Gadget-heimu-toggle.css`：它是 `type=general` 异步加载，会先露出剧透再变黑。切换态（`body.heimu_toggle_on`）留在 gadget 里不动 |
| 1256–1264 | `.pathnav2-center a` 白字 | 条目 4135 | `模板:Pathnav2/styles.css`（已存在，只有夜间模式） | 图 2 的直接原因 |
| 1566–1571 | `.cbox-autonarrow` | 条目 1 / 模板 1 | `模板:Cbox2/styles.css`（已存在，缺这条） | |
| 1586–1604（部分） | `div.reflist ol.references{font-size:100%}`、`list-style-type:inherit` | 条目 111 | `模板:Reflist/styles.css`（新建） | 皮肤 `references.css` 只管 `ol.references` 本身 |
| 1772–1907 | navbox / navbar / collapseButton | 模板 7 / 模块 4 / 微件 1 | `模板:Navbox/styles.css`（已存在，只有夜间模式） | 由 `模块:Navbox` 用 `frame:extensionTag('templatestyles')` 输出，`NavboxV2`、`Hydrogina/Navbox` 同样处理。布局部分（`width:100%`、inner/subgroup 100%、`.collapseButton` 浮动、`.navbox-title .navbar`）直接搬；**配色部分待拍板**（§4）。`Vector2022LayoutFixes.css` 61–124 行有去前缀即可用的版本 |

### 3.4 进 MediaWiki:Arknights.css（皮肤作用域的站内兜底）

已拍板：这三条不进皮肤仓库（`design-system/` 是从 prts-design 同步来的只读副本，要改得走上游 + 同步 + 发版），直接写 `MediaWiki:Arknights.css`。它和 Vector.css 同一机制（`site.styles` 按 skin 加载），只影响 Arknights，不污染其他皮肤。`MediaWiki:Arknights.js` 不需要：rightToc / backToTop 去了 Vector.js，没有东西要在新皮肤下跑。
皮肤 `catlinks.css:57` 那条简版 hlist 也不用删：它只给非末项加 ` · `，和 Common.css 完整版的输出一致，两者并存无冲突。

| 行 | 内容 | 用量 | 目标 | 说明 |
| --- | --- | --- | --- | --- |
| 1357–1367 | `.mw-collapsible:not(.mw-collapsed) tr:first-child > :last-child .mw-collapsible-toggle` 绝对定位 | `mw-collapsible` 条目 1034 | `MediaWiki:Arknights.css` | 皮肤已接管 toggle 浮动，这条是让 toggle 不挤占表头文字，应和皮肤的 toggle 规则放一起 |
| 1369–1376 | `.mw-collapsible-title-center` | 条目 44 / 模板 15 | `MediaWiki:Arknights.css` | 站内约定类，和上一条同一处维护 |
| （1772–1781） | `.navbox{width:100%}` `.navbox-inner,.navbox-subgroup{width:100%}` | — | `MediaWiki:Arknights.css` | 即使走 TemplateStyles，皮肤自己那段 navbox 也该补上宽度，否则 TemplateStyles 未生效的场合（微件直出）仍会塌 |

### 3.5 挪到 MediaWiki:Vector.js / Vector.css（随 Vector 退役）

| 行 | 内容 | 说明 |
| --- | --- | --- |
| 67–122 | `#rightToc` 右侧浮动目录 | 由 `Common.js` 5–39 行注入。现状是 **Vector 和 Minerva 都注入**（Common.js 全皮肤加载），但 Mobile.css 没有对应样式、Minerva 上是裸 DOM。已拍板：把注入代码从 Common.js 挪到 `MediaWiki:Vector.js`（目前只剩一段注释掉的 AntiDev），样式留在 Vector.css 不动，两者随 Vector 一起退役 |
| 1189–1210 | `.backToTop` 回到顶部 | 由 `Common.js` 55 行注入，情况同上。已拍板：同样挪到 Vector.js。新皮肤如需回顶由皮肤自己提供 |

### 3.6 新建小工具 CSS 页

| 行 | 内容 | 目标 | 说明 |
| --- | --- | --- | --- |
| 295–335 | CharInsert / Edittools 编辑框按钮 | `MediaWiki:Gadget-Edittools.css` | `Edittools` 是 default 小工具但只有 js。定义改成 `Edittools[ResourceLoader|default]|Edittools.js|Edittools.css` |
| 368–496 | Filterable 筛选工具（`.filterable-*` `.dropdown-menu` `.btn-group-sm`） | `MediaWiki:Gadget-Filterable.css` | 同上，`Filterable[ResourceLoader|type=general|default|hidden]|Filterable.js|Filterable.css`。Mobile.css 里的副本随 Minerva 退役 |

另有 498–501 `.nodesktop{display:none}` 按 `nomobile-nodesktop响应式迁移方案.md` 处理，不在此单独决定。

## 4. 拍板记录（2026-09-28）

1. **navbox**：TemplateStyles 只放布局（`width:100%`、inner / subgroup 100%、`.collapseButton` 浮动、`.navbox-title .navbar` 定位）。配色由皮肤 `catlinks.css:60-64` 说了算，Vector 的三级蓝不搬。
   **配色部分已于 2026-09-29 改判**：保留 Vector 的三级蓝，另加暗色规则，见 `主题适配盘点.md` §7。布局部分不变。
2. **hlist**：进 Common.css 完整版，皮肤 `catlinks.css:57` 那条简版删掉。
   hlist 是什么：Wikipedia 的 "horizontal list"。加在容器上后，里面的 `<ul>/<li>`（wikitext 里的 `* 项目`）不再竖排带圆点，而是横排、项目之间用 ` · ` 分隔，嵌套列表用括号包起来，`hnum` 变体给有序列表加编号。`模块:Navbox` 给每个 `navbox-list` 单元格都加了 `hlist`，大家族里"0-1 坍塌 · 0-2 守卫 · 0-3 追击 …"那一行就是它排出来的；没有它，每个关卡各占一行带圆点，navbox 高度翻十倍。除 Navbox 外还有 25 个模板直接用（干员导航、内测剧情导航、客户端版本导航 …），条目侧 546 页受影响。
3. **Common.js 的 rightToc / backToTop**：挪到 `MediaWiki:Vector.js`，样式留 Vector.css，随 Vector 退役（§3.5）。
4. **Edittools / Filterable**：各新建 `Gadget-*.css` 并挂到 `Gadgets-definition`（§3.6）。
5. **Ombox**：`模板:Ombox`、`模板:Ombox/core` 连同 mbox 全家规则一起删。
6. **ULS 裁剪 / PopupNotice 弹窗 / 反馈板 Flow 图标**：都要，进 Common.css（§3.2）。PopupNotice 目前无人引用，见表内备注。

## 5. 建议落地顺序

按「新皮肤下肉眼可见坏掉」排：

1. `模板:Pathnav2/styles.css` 补白字（4135 条目，1 条规则）
2. navbox 布局进 `模板:Navbox/styles.css` + 模块输出 templatestyles；hlist / nowraplinks / plainlist 进 Common.css（关卡导航、干员导航等全部大家族）
3. `模板:黑幕/styles.css`、`模板:模糊/styles.css`（剧透遮挡，30 + 95 条目）
4. `Gadget-Filterable.css`（筛选面板）
5. `.mw-collapsible-dark`、`.mw-collapsible-title-center`、折叠 toggle 定位（1000+ 折叠表）
6. 其余 Common.css 小项（lazyload、spoiler、logo 水印、tl-idnav、section.lst）
7. Reflist、半折叠、Cbox2 补条
8. 最后从 Vector.css 里删除已分流段落；`Vector-2022.css` 240 行、`Mobile.css` 里的副本同步清

每一步都可在切皮肤前落地，验证方式：`?useskin=arknights` 打开受影响页面对比。

## 6. 顺带发现

- `Gadget-collapsibleTables.js` 76 行注释写着 "Styles are declared in MediaWiki:Common.css"，实际在 Vector.css，本清单落地后注释才对。
- `模板:Navbox/styles.css` 与 `模板:关卡导航` 开头的 `#widget:style` 夜间模式全部限定 `body.skin-vector-2022`，新皮肤夜间模式同样不生效，属于 `hardcoded-skin-name` 规则范围。
- `MediaWiki:Arknights.css` 不存在（404）。原则上不要新建：皮肤专属覆盖应回到皮肤仓库，站点级的进 Common.css。

## 7. 落地进度

脚本：`scripts/vector_split_apply.py`（幂等，`--dry-run` 看 diff，`-c config.sandbox.toml` 先在沙箱演练，`--only` 选步骤）。

| 步骤 | 沙箱 | 线上 | 备注 |
| --- | --- | --- | --- |
| pathnav2 | ✔ | ✔ | |
| navbox（styles.css + 模块:Navbox / NavboxV2 输出 TemplateStyles） | ✔ | ✔ | 第二版补了 `th` 内边距 `1px 1em` 和 `.navbox-list{border-color:transparent}`（模块给每格画的 2px 左边框，Vector 靠 #fdfdfd 背景藏着，新皮肤下会露成黑线） |
| heimu_fuzzy | ✔ | ✔ | |
| misc_templatestyles（半折叠 / Cbox2 / Reflist） | ✔ | ✔ | TemplateStyles 不认 `-webkit-mask-image`，半折叠只留标准 `mask-image` |
| cleanup（PRTS:版权 ombox→cbox2；删 Ombox ×2、PopupNotice ×2） | ✔ | ✔ | |
| common_css | ✔ | ✔ | BotCathPalug 已获 interface-admin |
| gadgets（Edittools.css / Filterable.css / Gadgets-definition） | ✔ | ✔ | |
| arknights_css | ✔ | ✔ | |
| js（Common.js → Vector.js） | ✔ | ✔ | |
| vector_css（删 A 类死 CSS） | ✔ | ✔ | 跑过之后 Vector.css 行号漂移，依赖行号的步骤脚本会拒绝再跑 |

全部落地于 2026-09-28。验证时注意 `load.php?modules=site.styles` 在 CDN 上有 5 分钟缓存，刚改完 Common.css 的几分钟内页面可能还是旧样式（表现为 navbox 被撑到三千多像素宽），强刷即可。

新皮肤下 navbox 与 Vector 仍有的差异只剩配色：Vector 是三级蓝白字，皮肤是灰底加左侧强调条，`·` 分隔符也用皮肤的浅灰细体。

Vector.css 分流后仍保留的段（B / C 类和已复制到别处的段）随 Vector 退役时整页删除。

沙箱验证截图：`reports/sandbox-navbox-arknights.png`、`reports/sandbox-pathnav-arknights.png`。
