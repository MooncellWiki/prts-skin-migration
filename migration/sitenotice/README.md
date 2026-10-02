# 站点公告横幅适配新皮肤（`sitenotice`）

2026-10-02 · `MediaWiki:Sitenotice top` r432635 → r433017、`MediaWiki:Sitenotice mobile` r432644 → r433018（改前都是 Rafom 2026-10-01 的版本）·
源文件 `MediaWiki_Sitenotice_top.wiki` / `MediaWiki_Sitenotice_mobile.wiki` · 脚本 `scripts/sitenotice_apply.py`

状态：**已上线**（2026-10-02 15:20，BotCathPalug）。

生效时间：公告的解析结果按外层 `MediaWiki:Sitenotice` 原文的 md5 缓存 600 秒（`Skin::getCachedNotice`），
改子页面不会让它失效，登录用户最多 10 分钟后看到新版；匿名访客隔着 Varnish / CDN 的整页缓存（`s-maxage=18000`），
各页面在 5 小时内陆续换上，没有逐页 purge。
15:32 用不进缓存的 URL（`index.php?title=银灰&useskin=arknights&snv=…`）复测：700 暗色不溢出、链接 `#005a82`；360 浅色是 `mobile` 段，12px 单行。

## 问题

「我们正在测试新版皮肤」横幅。`MediaWiki:Sitenotice` 外层是 `.nomobile` 包着 `top`、`.mobileonly.nodesktop` 包着 `mobile`，
新皮肤按 640px 断点二选一（`legacy-device-classes.less`）。外层不动，只改两个子页面。

| 问题 | 场景 | 根因 |
| --- | --- | --- |
| 整页能横向拖 | 新皮肤 640–约 820 宽：640 宽溢出约 90px，700 宽 60px，800 宽 10px（`主题适配盘点.md` §11、`charinfo-fit` 都记过） | `top` 写死 `width:800px`，靠 `left:50%; translateX(-50%)` 居中，比正文栏宽时左右两边一起探出去 |
| 暗色下链接看不清 | 新皮肤暗色 / 自动 + 系统暗色 | 黄底是写死的，链接却跟着主题变成浅青 `#5ddcff`，对黄底 1.22:1；已访问的 `#3f8ea4` 2.86:1 |
| 浅色下链接偏淡 | 新皮肤浅色 | `#0072a8` 对黄底 4.05:1，不到 4.5 |
| 偏右 10px | 所有皮肤的桌面版 | `margin:10px` 的左边距叠在 `left:50%` 上 |
| 手机字小 | 新皮肤 < 640、Minerva | `mobile` 是 10px 字、写死 24px 高、文字绝对定位，放不下时只会被裁掉 |

## 改法

两段都改成一个 `div`，公告文字原样：

- **宽度**（`top`）：`max-width:800px; margin:5px auto 10px; box-sizing:border-box`，比正文栏窄时跟着缩。
  去掉内层绝对定位的 800px 文字层，改成 `min-height` + `line-height` 垂直居中，放不下时折行而不是被裁
- **渐变**（`top`）：两端淡出的色标从 `20%` 改成 `clamp(0px, calc(50% - 220px), 20%)`——800 宽时仍是 20%（外观不变），
  变窄时纯色段至少留 440px，文字（约 356px）始终落在纯色段里，暗色下两端不会淡进深色底
- **链接色**：行内设变量，新皮肤（`--ak-link` / `-hover` / `-visited`）和 Vector 2022 / Minerva（`--color-progressive` / `--hover` / `--color-visited`）
  在横幅里都取 `#005a82`（对黄底 5.77:1），悬停 `#003d59`（8.87:1）。已访问不另设颜色，暗色下也不会变浅。
  旧 Vector 的链接色是写死的 `#0645ad`（6.53:1），不吃变量，保持原样
- **黄色**：`var(--yellow, #f9e179)`。`--yellow` 只在 `Common.css` 的 `body` 上定义，补一个回退值
- **手机**（`mobile`）：字号 10px → 12px，`min-height:24px; padding:3px 8px; line-height:18px`，单行时仍是 24px 高

横幅保持黄底深字、明暗一致（和 Cbox2 自定义配色框「钉成亮色」同一个处理）。

## 验证（线上页面注入）

`银灰` 页，`action=parse` 解析源文件后替换 `#siteNotice` 里的两段（Sanitizer 原样保留了 `clamp()` / `calc()` / 自定义属性）。

| 皮肤 | 视口 / 主题 | 改前 | 改后 |
| --- | --- | --- | --- |
| Arknights | 1280 浅色 | 800 宽，偏右 10px | 800 宽，居中，外观同改前 |
| Arknights | 800 浅色 | 页面宽 810 | 752（铺满正文栏），页面宽 800 |
| Arknights | 700 暗色 | -40 → 760，页面宽 760，链接 `#5ddcff` | 不溢出，链接 `#005a82` |
| Arknights | 640 暗色 | 溢出 | 592 宽，文字单行、两侧各留 118px |
| Arknights | 360 / 320（`mobile`） | 10px 字 | 12px 字单行，不溢出 |
| 旧 Vector | 1280 | 偏右 10px | 居中，链接仍是 `#0645ad`，高度、上下边距不变 |
| Minerva（m.prts.wiki） | 360 | 10px 字 | 12px 单行；「了解详情」`#36c` → `#005a82` |

截图：`build/shots/sitenotice-before-*.png` / `sitenotice-after-*.png`。

## 没解决的

- Minerva 下「切换至新版」是正文黑色：微件的 `<a>` 没有 `href`，Minerva 把无 `href` 的链接画成正文色。改前就是这样，要改得动微件
- 外层 `MediaWiki:Sitenotice` 的 `.nomobile` / `.nodesktop` 双份，按 `nomobile-nodesktop响应式迁移方案.md` 阶段 3 再合成一份
