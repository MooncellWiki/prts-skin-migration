# 道具图标在窄表格里被挤小（`item-icon-shrink`）

2026-10-04 · `模板:道具图标`、`模板:物品数量角标/styles.css` · 脚本 `scripts/item_icon_shrink_apply.py`（写入）+
`scripts/item_icon_shrink_measure.mjs`（浏览器里量）

状态：**已上线**（2026-10-04 14:18，BotCathPalug；`模板:物品数量角标/styles.css` r434261、`模板:道具图标` r434262）。
沙箱先落地（r420855、r420856）。上线后用 `scripts/purge_embeddedin.py` 清了全部 5609 个嵌入页的解析缓存（失败 0）。
主域匿名页面另受 CDN 缓存（最多 5 h）。

## 问题

[采购中心](https://prts.wiki/w/采购中心) 在新皮肤手机宽度下，「源石交易所」充值表、「凭证交易所」的物资价格表里的道具图标被压成十几像素，
数量角标比图标还大，盖在上面。390 宽下页面里 617 个可见的道具图标有 83 个被挤小，最小 17px（WebKit 14px），应为 42 / 50px。

原因是三件事叠在一起：

- 皮肤 `base/media.css`：`.mw-file-element { max-width: 100%; height: auto }`，本意是正文大图不撑破栏宽；
- `模板:道具图标`（`材料消耗` 等都走它）的外壳是 `<div style="display:inline-block;position:relative">`，宽度由内容决定；
- 百分比 `max-width` 的参照宽度（外壳）又取决于图自己，是循环依赖：规范规定这种替换元素算最小内容宽度时百分比按 0 处理。
  外壳、单元格的最小宽度于是都是 0，表格一放不下，装图标的列就被压到只剩数量角标撑着的那点宽度。

旧 Vector 没有那条 `max-width`，图标不缩、表格直接撑宽。Minerva 有同样的规则，同一页 617 个里 54 个被挤小，但那边表格没被压得那么狠，最小 38px，看不大出来。

不只这一页：`模板:道具图标` 在主名字空间有 5465 个嵌入页，390 宽下抽 240 页，24 页（10%）有图标被挤小，共 649 个，
集中在活动页的商店 / 奖励表（`火山旅梦` 95 个、`纷争演绎` 64 个）和关卡页的掉落表（`IS-3`、`BB-2` 等，最小 14px）。

## 改法

- `模板:道具图标`：外壳加 `prts-item-icon` 类；
- `模板:物品数量角标/styles.css`（模板本来就引着）末尾加一条：

  ```css
  .prts-item-icon .mw-file-element {
  	max-width: none;
  }
  ```

图标按 `width` 属性的尺寸占位，表格放不下时横滑（`.wikitable` 在 <640 自己是滚动容器，或在第四步的 `ak-table-scroll` 外壳里）。

样式页是站内编辑在维护的，脚本只在末尾追加这一条，不整页覆盖。

### 试过、没用的

- **皮肤里改成 `max-width: max(100%, 4rem)`**（想让小图标一律不缩，全站一次解决）：Blink 里图标是回到原尺寸了，但算列宽时仍按 0，
  图标伸出单元格盖到隔壁（采购中心 83 个）。纯 CSS 分不出「小图标」和「大图」，皮肤层没有干净的写法。
- **外壳行内写 `min-width: max-content`**（不用样式页）：新皮肤下效果相同，但 Minerva 的 `max-width` 也跟着失效，
  `m.prts.wiki/w/采购中心` 的一张表撑到 456px、整页 390 → 472。用类 + `max-width: none` 则压不过 Minerva 自己的规则，那边原样不动。

## 验证

### 线上真实页面预演（不写入，页内给外壳加类 + 注入同一条规则）

`采购中心`：

| 环境 | 被挤小的图标 前 → 后 | 最小图标 前 → 后 | 整页宽 前 → 后 |
| --- | --- | --- | --- |
| 新皮肤 390 · Chromium | 83 → 0 | 17 → 40 | 390 → 390 |
| 新皮肤 360 · Chromium | 85 → 0 | 14 → 40 | 360 → 360 |
| 新皮肤 390 · WebKit | 83 → 0 | 14 → 40 | 390 → 390 |
| 新皮肤 1280、旧 Vector 1280 | 0 → 0 | 40 → 40 | 各表尺寸不变 |
| Minerva 390 · Chromium / WebKit | 54 → 54 / 50 → 50 | 38 / 37 不变 | 各表尺寸不变 |

（最小 40px 是页面里本来就写 40px 的图标。）图标没有伸出单元格的。充值表 364 → 内容宽 413，在表格自己里横滑；
物资价格表 366 → 628，在 `ak-table-scroll` 里横滑。

### 沙箱（模板、样式页真实写入）

`localhost:8080/w/采购中心`，同一次加载里先摘掉类量「前」、再放回去量「后」（`UNDO=1`）：新皮肤 390 / 360 Chromium、390 WebKit
被挤小的 83 / 85 / 83 → 0，整页宽前后相同；新皮肤 1280、旧 Vector 1280 各表尺寸不变。
（沙箱这页本来就比视口宽：沙箱的商店模板是旧版，与本次改动无关。）

截图：`build/shots/item-icon-shrink-sandbox-390-yuanshi.png`（充值表）、`item-icon-shrink-sandbox-390-pingzheng.png`（物资价格表）。

### 上线后复测（真实页面）

`采购中心`，同一次加载里先摘掉类量「前」、再放回去量「后」（`UNDO=1`），与预演逐项相同：新皮肤 390 / 360 Chromium、390 WebKit
被挤小的 83 / 85 / 83 → 0，整页宽 390 / 360 / 390 不变，没有图标伸出单元格；新皮肤 1280、旧 Vector 1280、
Minerva 390（Chromium / WebKit）各表尺寸不变。

### 副作用：图标不缩了，有的表会比正文栏宽

图标原来能缩，等于替一些表格「吸收」了超宽；不缩之后，行内写了 `display:table`、又没包横滑外壳的表会伸出正文栏，把整页撑宽一点。
390 宽下抽样（预演）：240 页里 1 页（`潮起潮又起` 390 → 441，`模块:CollectGoalTable` 生成的表）；另抽 100 页里 2 页
（`此地之外` 390 → 398、`危机合约/利刃行动` 表宽 377，都只多出十来像素）。

全量预演（5465 页，360 宽）见下面「全量」一节，量出来的页面按 `../mobile-table/README.md` 第四步的办法包 `ak-table-scroll`。

## 落地命令

```bash
uv run python scripts/item_icon_shrink_apply.py --dry-run               # 先看 diff
uv run python scripts/item_icon_shrink_apply.py -c config.sandbox.toml  # 沙箱
uv run python scripts/item_icon_shrink_apply.py                         # 线上
uv run python scripts/purge_embeddedin.py 模板:道具图标                  # 脚本只 purge 三个代表页

node scripts/item_icon_shrink_measure.mjs page 采购中心                  # 各皮肤 / 引擎 / 宽度量一遍
PATCH=1 node scripts/item_icon_shrink_measure.mjs page 采购中心          # 模板没改时：页内注入修法预演
UNDO=1 node scripts/item_icon_shrink_measure.mjs page 采购中心           # 模板改完后：同一次加载里摘掉类对比
PATCH=1 node scripts/item_icon_shrink_measure.mjs sample 240            # 抽样；数字给大（99999）就是全量
```

中间文件在 `build/icon-shrink/`。

## 没做的 / 要注意的

- **同款写法的别的模板**：收缩包裹的 `inline-block` 外壳直接装 `[[文件:]]` 的还有 `模板:数量`、`模板:UP干员`、`模板:测试指标`、
  `模板:异常状态作用范围/干员`、`模板:家具`（外壳里是 `{{家具图标}}`），都有同样的隐患，这次没动；`模板:危机合约词条` 在 `contract-rune` 里单独处理。
  遇到了照这里的办法加类。
- **皮肤那条规则没动**。根子在 `.mw-file-element { max-width:100% }`，但皮肤层分不出图标和大图（见上面「试过、没用的」）。
- Minerva 上的轻微缩小（38px）保持原样。
- 沙箱里 purge 带 `forcelinkupdate` 会超过 30s 的请求超时（脚本报 `ReadTimeout`），写入本身已经成功，重跑一次显示「已是目标状态」即可。
