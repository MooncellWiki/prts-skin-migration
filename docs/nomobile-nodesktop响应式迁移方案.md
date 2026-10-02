# `.nomobile` / `.nodesktop` → 响应式：评估与落地方案

> 数据源：本地沙箱库 `prts-sandbox`（生产备份）· 线上 `jiaxing` 主机（MW 1.43.9 · MobileFrontend 2.4.1 · Arknights 皮肤 0.1.0 已部署但非默认）·
> 皮肤源码 `../mediawiki-skins-Arknights`（本地比线上多 2 个文件、32 处差异）· 盘点日期 2026-09-27

## 0. 结论

| 问题 | 答案 |
| --- | --- |
| 规模 | **484 个页面**，不是之前盘点的 88 个。之前只扫了模板 / 微件 / 模块 / MediaWiki 四个名字空间，**主名字空间还有 344 个**（其中 234 个是同一种敌人条目写法，可机器改） |
| 现在新皮肤下是什么状态 | **两套 DOM 同时显示**。沙箱 `银灰?useskin=arknights`：`nomobile` 15 处、`nodesktop` 15 处，没有任何 CSS 隐藏其中一套（现有规则全部限定在 `body.skin-vector-2022` / `.skin-minerva` / Vector.css）。这是切默认皮肤前的**硬阻塞**，与内容迁不迁移无关 |
| 最省事的平稳方案 | 皮肤先加一段 **8 行的过渡 CSS**，把这两个类从「按 UA / 域名」改成「按视口宽度」；484 个页面第 0 天全部行为正确，然后再分批把类名从内容里真正消掉，最后删过渡 CSS |
| 改造成本 | 皮肤侧半天；机器人可做的部分（234 敌人条目 + 类名批量换名 + 6 个近乎相同的模板）1～2 天；**真正要人合并的约 58 个模板**，一半（29 个）两套只差宽度，另一半里约 10 个结构完全不同要重做；合计约 **12～18 人日**，可以和其它迁移并行 |
| 移动端流量 | Caddy 近 3 小时 `/w/` 页面请求 6971 次，`m.prts.wiki` 占 1907（**27%**），不能出岔子 |

## 1. 今天这两个类是怎么生效的

三层机制叠在一起，任何一层单独看都不完整：

| 层 | 桌面站 `prts.wiki` | 移动站 `m.prts.wiki` |
| --- | --- | --- |
| **Varnish**（`docker-config/prts/varnish/default.vcl` 49–60 行） | UA 命中手机正则且无 `stopMobileRedirect` cookie → 302 到 `m.` | 设 `X-Subdomain: m` 头；响应加 `Vary: User-Agent` |
| **MobileFrontend**（`$wgMFMobileHeader = "X-Subdomain"`，`$wgMFAutodetectMobileView = false`） | 不介入 | 默认 `MFRemovableClasses.base = [".nomobile"]`：**服务端直接从 HTML 里删掉** `.nomobile` 元素，移动端根本收不到桌面版 DOM |
| **CSS** | `MediaWiki:Vector.css` 499 行 `.nodesktop{display:none}`；Vector 2022 走 `Common.css` 191–203 行 + 两个 gadget：`.nodesktop` 恒隐藏，**`≤719px` 时隐藏 `.nomobile`、显示 `.nodesktop.cbox2-mobile`** | `Mobile.css` 247 行 `.skin-minerva .nomobile{display:none}` |

两个值得注意的事实：

- **Vector 2022 那套已经是「按视口」的**（719px 断点），在线上跑了很久没出事。本方案的过渡 CSS 就是把这套做法搬进新皮肤，不是新发明。
- **MobileFrontend 的服务端删节点意味着移动端页面更轻。** 新皮肤单一渲染后，双份内容都会下发，靠 CSS 隐藏。`模板:剧情导航` 正文 216 KB、`衍生作品导航` 43 KB，这类页面在合并完成前移动端会变重，是过渡期要盯的指标。

另外还有一批**不走这两个类、但同样按设备分叉**的东西，退 MobileFrontend 时会一起断：

| 依赖 | 位置 | 后果 |
| --- | --- | --- |
| `mw.config.get('wgMFMode')` | `Gadget-enemyFilter.js` 29 行（移动端默认勾「精简」）、`Gadget-copyUrl.js` 6 行 | 变量消失 → 静默走桌面分支 |
| `Gadget-fixCss.js` | 往 body 插 `.nodesktop` / `.nomobile` 探针，按 `wgMFMode` 判断 Common.css 是否加载失败，失败则跳 `debug=true` | 新皮肤下探针永远判错 → **每个页面都会被重定向到 `debug=true`**。这个 gadget 不在 `Gadgets-definition` 里，需要确认是否还在被引用；在则必须先删 |
| `微件:Mpbutton` 脚本 | `classList.contains("skin-minerva") ? ".nodesktop" : ".nomobile"` | 首页盘点 G4 已定删 |
| `微件:CharinfoV2` | 用 `<link media="(min-width:600px)">` / `(max-width:600px)` 分别加载 `charinfo` / `charinfom` 两份 CSS | **已经是响应式**，不用动；只是断点 600 与站点其它地方的 640 不一致 |
| `MediaWiki:Mobile.css`（22 KB）/ `Minerva.css`（11 KB） | 除了这一条 `.nomobile`，还有大量给内容表格、字号在手机上做的修正 | 随 Minerva 退役，但里面**内容相关**的修正要另审（不在本文范围） |

## 2. 用量盘点

### 2.1 按名字空间

| ns | 页面数 | 说明 |
| --- | ---: | --- |
| 0 主 | **344** | 234 个是敌人条目的同一写法（§2.2 A）；其余 ~110 个是活动、关卡、音乐等条目里手写的 |
| 2 用户 | 47 | 用户自己的页面，**不动**，靠过渡 CSS 兜底 |
| 8 MediaWiki | 9 | 全是定义方（Common.css / Vector.css / Mobile.css / 3 个 gadget CSS / fixCss.js / Sitenotice） |
| 10 模板 | 70 | 其中 56 个成对、12 个只有 `nomobile`、2 个只有 `nodesktop` |
| 274 微件 | 6 | Mpbutton / Subname / CCSMusic / Main14ArcMusic / ScenarioSimulator / 需要我帮你PRTS么 |
| 828 模块 | 3 | MusicTable / VoiceTable（Lua 拼字符串）/ Hydrogina/Navbox（已注释掉） |
| 3000 泰拉大典 | 3 | 集成战略/收藏品（6 处）/ Index / 地理 |
| 合计 | **484** | |

### 2.2 按写法分类（决定谁来改、怎么改）

对 58 个成对的模板 / 微件 / 模块，把两个分支去掉宽度、`display`、`white-space` 之后算了相似度（difflib）：中位数 0.70，**29 个 ≥ 0.7**，即一半的模板两套只差尺寸。

| 类 | 写法 | 量 | 典型 | 处理方式 | 谁做 |
| --- | --- | ---: | --- | --- | --- |
| **A** 敌人缩略图 | `<div class="nomobile">[[文件:Avg …\|缩略图\|…]]</div>` | 234 页（ns 0） | 全部敌人条目 | 拆掉外层 div。`Common.css` 72–90 行已有 `body.skin--responsive` 在 <640 把浮动缩略图改成通栏，新皮肤 body 带 `skin--responsive`，直接生效 | 机器人 |
| **B** 近乎相同的成对 div（相似度 ≥ 0.9） | 两个 div 只差 `width` | 12 个模板 | `Pathnav2` 0.98（6936 次引用）、`关卡报酬` 0.91、`悖论模拟` 0.91、`危机合约赛季导航` 0.99、`Navigator/default`、`CCSMusic`、`Main14ArcMusic`、`音乐鉴赏`、`家具考据`、`异格干员/升变`、`异格干员` | 删一份，宽度改 `max-width:100%` 或进 TemplateStyles `@media` | 机器人出 diff，人过一眼 |
| **C** 差在布局的成对 div / 表（0.5–0.9） | 桌面横排、移动竖排；表格列数不同 | ~20 个 | ~~`Cbox2/core`~~ 0.74（**7230 次**；已换成设计系统 `.ak-cbox` 单份 DOM，见 `migration/cbox2/README.md`）、`活动信息/info`、`登场敌人`、`潜能提升`、`技能升级材料`、`技能`、`技能2`、`能力生效范围`、`分析与考据导航`、`内测剧情导航`、`干员时装`、`合约`、`危机合约词条`、`收藏品考据`、~~`Mbox2/core`~~（主名字空间 0 次，调用改用 Cbox2 后整个模板删除，见 `scripts/mbox2_retire_apply.py`） | 单一 DOM + flex/grid + TemplateStyles `@media (max-width:639px)`；宽表加横向滚动容器而不是转置一份 | 人工，每个 0.5–1 小时 |
| **D** 行内文案分叉 | `<span class="nomobile">将鼠标移至…</span><span class="nodesktop">点击…</span>`；`招聘<br/>合同` vs `招聘合同` | 9 个模板 + 25 个 ns 0 页面 | `相关道具`（425）、`异格干员`、`合约详情`、`活动关卡标题`、`EnemyDataMini`、`维多利亚_浸血焦土` 等关卡页 | 这类分叉的依据是**输入方式**不是视口：统一文案（「悬停 / 点击」），或用 `@media (hover: none)` 的工具类；换行差异交给自然换行 | 人工，极快 |
| **E** 只有桌面版的附加物（`nomobile` 无对应） | 宽导航条、额外列、额外行 | 12 个模板 + 3 个模块位置 + 6 个 ns 0 表格行 | `Navigator/enemy`（1705）/ `Navigator/item`（1367）的 600px 上下条导航、`关卡链接` 的关卡名、`MusicTable` 的专辑封面列、`家具图标/temp`、`Ads/small`、`集成战略/收藏品` | 逐个定：能缩就缩（导航条 `max-width:100%`），确实放不下就换 `.ak-hide-mobile` | 人工 |
| **F** 只有移动版的附加物 | 移动端提示 | 2 个模板 + 1 个 Lua | `剧情模拟器` 的「移动端可能无法播放」提示、`黑话页面导航/mobile`、`异常状态作用范围/敌人` | 提示改按 `(pointer: coarse)` 或干脆去掉；`/mobile` 子模板并回主模板 | 人工 |
| **G** 结构完全不同（相似度 < 0.3） | 两套各写各的 | **约 10 个** | `道具信息` 0.05（**1372 次**）、`衍生作品导航` 0.01（429）、`剧情模拟器` 0.11（2258）、`装置技能` 0.10（618）、`黑话页面导航` 0.05、`MusicTable` 0.20、`显示弹出` 0.14（桌面悬停弹窗 / 移动纯文本）、`EnemyDataMini`、`剧情简介`、`音乐一览` | 按新皮肤组件重做，等同一次小型模板重写 | 人工，每个半天 |
| **H** 定义方与站点脚本 | §1 表 | 9 个 MediaWiki 页面 | — | 过渡期保留，切换后删 | 人工，一次性 |

`wikibot` 现有的 `dual-render` 规则只能定位；`config.toml` 的目标集合**没有 ns 0**，这是它漏掉 344 个页面的原因，加一个 `[targets.content]` 即可。

## 3. 目标写法（迁完之后长什么样）

定一套契约，后面所有合并都照这个来，避免每个模板各想一套：

1. **断点统一 640px**——皮肤 `@ak-bp-tablet`、`Common.css` 现有的响应式规则都是 640；Vector 2022 兼容层的 719 和 CharinfoV2 的 600 是历史遗留，不再新增。
2. **优先单一 DOM**：布局差异用 TemplateStyles 里的 `@media (max-width: 639px)`、flex-wrap / grid、`max-width: 100%` 解决。宽表用横向滚动容器，不再维护一份转置表。
   TemplateStyles 净化器（首页盘点 §8）不认 `clamp()`、`:has()`、部分 `var()` 嵌套，但 `@media`、flex、grid 都没问题。
3. **确实要两套 DOM 时**用皮肤已有的工具类：`.ak-hide-mobile`（<640 隐藏）、`.ak-only-mobile`（≥640 隐藏）、`.ak-hide-tablet`（<1120 隐藏），定义在 `resources/design-system/utilities.css` 33–35 行。**不再写 `nomobile` / `nodesktop`。**
4. **按输入方式分叉的文案**（悬停 / 点击）建议皮肤补两个工具类 `.ak-hide-touch` / `.ak-only-touch`（`@media (hover: none) and (pointer: coarse)`），D 类用它，不用视口宽度冒充触屏判断。
5. **脚本里不再读 `wgMFMode`**，改 `window.matchMedia('(max-width: 639px)')`。

## 4. 皮肤侧改动（小，且是整个方案的前提）

### 4.1 过渡 CSS（第 0 天必须有）

新建 `resources/skins.arknights.styles/common/legacy-device-classes.less`，在 `skin.less` 里引入：

```less
// 过渡期兼容：MobileFrontend 时代按设备分叉的类，改为按视口生效。
// 内容里的 nomobile / nodesktop 清零后删除本文件（见 docs/nomobile-nodesktop响应式迁移方案.md）。
@media ( max-width: @ak-bp-mobile-max ) {
	.skin-arknights .nomobile { display: none !important; }
}
@media ( min-width: @ak-bp-tablet ) {
	.skin-arknights .nodesktop { display: none !important; }
}
```

- 限定 `.skin-arknights`，对 Vector / Minerva 零影响，可以随时发。
- `Cbox2` 那条 `.nodesktop.cbox2-mobile` 例外自动成立（<640 时 `nodesktop` 本来就显示）。
- 断点 640 与 Vector 2022 的 719 有 80px 差距：640–719 的窄平板从此看到桌面版。可接受，也和 `Common.css` 其它规则对齐。
- 发布路径：皮肤是 vendor 进 `../mw` 仓库的 `skins/Arknights`，随镜像 `mooncellwiki/mw:v1.43.9-x` 重建；本地皮肤仓库比线上新 32 处，一起带上。

### 4.2 顺手补的工具类

`design-system/utilities.css` 加：`.ak-hide-touch` / `.ak-only-touch`（§3 第 4 条）、`.ak-table-scroll { overflow-x: auto; max-width: 100%; }`（C 类宽表用）。

### 4.3 旧皮肤共存期的对称措施

在新皮肤成为默认之前，Vector / Minerva 还在线。如果内容里已经开始出现 `.ak-hide-mobile`，旧皮肤不认识它。解决：把同样两条 `@media` 规则（不限定皮肤、不带 `nomobile`）加进 `MediaWiki:Common.css`——它在所有皮肤下都加载。这样机器人换名（§5 阶段 1）可以在切换之前就跑，不必等。

## 5. 分阶段落地

原则沿用首页盘点：**迁移未完成之前不改现网行为**；每一步都有回退；`wikibot scan` 的命中数单调下降。

### 阶段 0 · 皮肤兜底（半天，无风险）

1. 皮肤加 §4.1 过渡 CSS + §4.2 工具类，重建镜像。
2. `Common.css` 加 §4.3 的 `.ak-hide-mobile` / `.ak-only-mobile` 定义。
3. 沙箱验证：`银灰`、`塔露拉`（敌人）、`采购中心/凭证交易所`（42 对）、`首页`，分别在 375 / 768 / 1280 宽度下用 `?useskin=arknights` 看只剩一套。
4. 删掉或改写 `Gadget-fixCss.js`（§1 表）。

完成标志：新皮肤下没有页面同时显示两套内容。这一步做完，**默认皮肤切换就不再被这个问题卡住**；后面的阶段只是还债，节奏可以自己定。

### 阶段 1 · 机器人（1～2 天）

1. `config.toml` 加 `[targets.content]`（ns 0）；`scan -t all` 重跑，拿到 484 的基线。
2. 新规则 `enemy-thumb-nomobile`：A 类 234 页，拆 `<div class="nomobile">` 外壳，`plan` 出 diff，`apply` 走沙箱再走线上。
3. 新规则 `device-class-rename`：`class="… nomobile …"` → `ak-hide-mobile`、`nodesktop` → `ak-only-mobile`，只碰 class 属性里的 token，`<script>` / `<nowiki>` / 注释不动（现有保护区机制）。对 ns 10 / 274 / 828 / 3000 / 0 全跑，**ns 2 不跑**。
   这一步不改任何页面的显示，只是把「设备语义」换成「视口语义」，并让后续人工合并的债务在 scan 里单独可见（`ak-only-mobile` 的剩余数）。
4. B 类 12 个模板：机器人出「删掉第二份 + 宽度改 100%」的 diff，人审后 apply。

### 阶段 2 · 模板人工合并（约 10～14 人日，可并行、可拖长）

按引用数分三档，每个模板在 `/sandbox` 子页面改好、沙箱三档宽度看过再覆盖：

| 档 | 模板 | 类别 | 估时 |
| --- | --- | --- | --- |
| 一档（≥1000 次引用） | `Cbox2/core` `道具信息` `剧情模拟器` `剧情导航` `Navigator/enemy` `Navigator/item` | C / G / G / C / E / E | 3～4 天 |
| 二档（100–1000） | `装置技能` `干员攻击范围` `活动信息/info` `衍生作品导航` `潜能提升` `相关道具` `技能升级材料` `技能` `技能2` `分析与考据导航` `内测剧情导航` `关卡链接` `MusicTable` `登场敌人` `角色立绘考据` `家具图标/temp` | 混合 | 5～6 天 |
| 三档（<100） | 其余约 30 个 + 6 个微件 + VoiceTable | 多为 C / D | 2～3 天 |
| ns 0 手写页 | ~110 个（活动页文案分叉、关卡页、音乐页、`采购中心/凭证交易所` 的 42 对表格） | D / E | 2 天，机器人先按页出 diff |

`Cbox2/core` 单独提一句：7230 次引用、Common.css 为它开过特例、且首页盘点里新皮肤的 `.ak-*` 组件已有对应的提示框——建议直接映射到皮肤组件而不是在模板里再写一遍响应式。（2026-10-02 照此落地：`模板:Cbox2/core` 输出 `.ak-cbox`，见 `migration/cbox2/README.md`。）

### 阶段 3 · 站点级清理（切换窗口内，半天）

- `Common.css` 删 190–203 行兼容块和阶段 0 加的临时定义；`Vector.css` / `Mobile.css` / `Minerva.css` / 3 个 Vector 2022 gadget 随皮肤退役（首页盘点 §3 已列）。
- `Gadget-enemyFilter.js` / `Gadget-copyUrl.js` 的 `wgMFMode` 改 `matchMedia`。
- `MediaWiki:Sitenotice` 改成单一内容（现在 top / mobile 两个子页面都是空的）。

### 阶段 4 · 退 MobileFrontend（切换窗口内）

- `LocalSettings.php`：去掉 `wfLoadExtension('MobileFrontend')`、`wfLoadSkin('MinervaNeue')`、`$wgDefaultMobileSkin`、`$wgMobileUrlCallback`、`$wgMFMobileHeader` 等；`etc/config.php` 去掉 `$wgMobileUrlTemplate`。
- Varnish：删 49–60 行的 UA 跳转；**`m.prts.wiki` 改成 301 到 `prts.wiki` 同路径**（站外链接、搜索引擎收录都指向它，不能直接 404）；`vcl_deliver` 里 `Vary: User-Agent` 去掉，缓存命中率会上升；**保留 `SKLand` UA 的直通逻辑**（141 行），那是给森空岛 App 内嵌用的，与本项无关。
- 切换后全站 purge。

### 阶段 5 · 删过渡 CSS

条件：`wikibot scan` 在 ns 0 / 10 / 274 / 828 / 3000 里 `nomobile` / `nodesktop` 命中为 0。删 §4.1 文件。ns 2 用户页的 47 个不等它——过渡 CSS 8 行留着也没成本，或者删了让用户页自然退化（两套都显示），二选一都行。

## 6. 风险与验收

| 风险 | 应对 |
| --- | --- |
| 过渡期移动端页面变重（MobileFrontend 不再删节点） | 阶段 0 后抽 `剧情导航` 所在页面、`采购中心/凭证交易所` 量 HTML 体积；一档模板优先合并 |
| `Gadget-fixCss.js` 若仍被引用，新皮肤下会把所有页面重定向到 `debug=true` | 阶段 0 第 4 步先处理 |
| 640 与 719 断点差异 | 已接受；如有投诉再看 |
| 机器人换名误伤 `<script>` 里的字符串（`Mpbutton` 那种） | 现有保护区机制跳过 `<script>`；Mpbutton 本身在删除名单 |
| Varnish 缓存里还有按 UA 分叉的旧对象 | 切换后 ban 全站 |
| 移动端用户习惯的 Minerva 章节折叠 | 与本项无关，但退 Minerva 时会一起没；属皮肤 UX 范畴 |

验收：每个阶段结束跑一次 `wikibot scan -t all`，四个数字（`nomobile` 命中、`nodesktop` 命中、`ak-only-mobile` 命中、`wgMFMode` 引用）只降不升；阶段 0 之后新皮肤沙箱抽样零「双份显示」。
