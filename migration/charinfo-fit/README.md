# 干员立绘舞台宽度适配（`charinfo-fit`）

2026-10-01 · `微件:CharinfoV2` r410622（源文件 `微件_CharinfoV2.wiki`）· 脚本 `scripts/charinfo_fit_apply.py`

状态：**沙箱已写入，线上未写**。

## 问题

[结城理](https://prts.wiki/w/结城理) 等干员页「干员信息」下的立绘舞台在 Skin:Arknights 下比正文栏宽，压到右侧目录上。

调用链：`模板:CharinfoV2` → `微件:CharinfoV2`。样式和脚本都在 static.prts.wiki，不在 wiki 里：

- `charinfo_*.min.css`（`<link media="(min-width:600px)">`）：`.charinfo-wrapper` 写死 `1024px × 576px`；
- `charinfom_*.min.css`（`(max-width:600px)`）：手机版 `600px × 800px`；
- `charinfo_*.min.js`：只在加载时看一次「容器父级的父级」宽度，< 600 就走手机版（`P = 1`），
  写内联的容器宽高并把舞台 `scale(宽/600)`；桌面版从不处理宽度。

新皮肤正文栏最宽 982px（1920 宽），所以桌面宽度下**全部**溢出：

| 视口 | 正文栏 | 舞台溢出 |
| ---: | ---: | ---: |
| 1920 | 982 | 42 |
| 1600 | 950 | 74 |
| 1440 | 790 | 234 |
| 1280 | 894 | 130 |
| 1120 | 734 | 290（整页能横向拖） |
| 1024 | 934 | 90 |
| 768 | 678 | 346 |

另外 601–约 690（Vector 是 601–约 825）是个错位区：视口 > 600 加载桌面样式，正文栏 < 600 脚本又按手机版处理，
1024×576 的舞台被按 600×800 的比例绕中心缩小，偏到右边溢出 400 多 px，下面留一大块空白。
Vector 下 1024–1250 宽同样溢出（正文栏 < 1024），只是旧皮肤正文栏宽，平时不显眼。

## 改法

纯 CSS，加在微件已有的 `<style>` 里（外部 JS / CSS 不动），只在 `min-width: 601px` 下生效：

- `.charinfo-wrapper { max-width: 100% }`：舞台收窄到正文栏宽，高度仍是 576，**不缩放、裁掉右侧**。
  舞台里的控件按 `left` / `right` 定位：左侧信息、顶部按钮不动；右下角按钮、时装面板（`right:-400px → 0`）贴右边跟着进来。
- `.top-btns { width: auto }`：原来是舞台的 60%，收窄后精英 / 时装 / 背景按钮会挤成两行。
- `.back img { object-fit: cover }`：背景是 `width/height="100%"` 的 `<img>`（1820×1024，与 1024×576 同比例），
  收窄后不压扁，改为裁两边。
- 错位区：`.charinfo-container` 宽高 `auto !important`、`.charinfo-wrapper` `transform: none !important`，
  压掉 `charinfo.js` 手机版写的内联尺寸 / 缩放，按桌面版收窄显示。这是唯一用到 `!important` 的地方，对付的是内联样式。

`601` 而不是 `600`：恰好 600 宽时两份样式表都生效、`charinfo.js` 走手机版（正文栏 576），不能插手。
≤ 600 的手机版一行没碰。不分皮肤：正文栏 ≥ 1024 时（Vector ≥ 约 1250 宽）这些规则都不起作用。

先试过按容器宽等比缩小（JS 算 `scale`，或 CSS `tan(atan2(100cqw, 1024px))`），能完整保留画面，
但要么得写 JS，要么依赖较新的 CSS 且 `container-type` 会影响全屏；裁切方案在新皮肤的宽度范围内效果足够，选了更简单的。

## 验证

线上页面同源 iframe 里注入这段 CSS，与注入前对比（沙箱站点拿不到 static.prts.wiki 的 CSS——`ERR_BLOCKED_BY_ORB`，
只用来确认微件能保存）。页面 `结城理`：

| 皮肤 | 视口 | 改前 | 改后 |
| --- | --- | --- | --- |
| Arknights | 360 / 600 | 手机版 | 不变（含内联缩放） |
| Arknights | 601 / 640 | 错位，溢出 427 / 431，下方空 204 / 181 | 577×576 / 550×576，贴合 |
| Arknights | 700–1920（8 档） | 溢出 42–414 | 全部贴合，如 1440：790×576 |
| Vector | 640 | 错位，溢出 451 | 415×576，贴合（见下方「已知问题」） |
| Vector | 1024 | 溢出 225 | 799×576，贴合 |
| Vector | 1440 | 1024×576 | **不变** |

- 所有桌面宽度下顶部按钮位置（0 / 245 / 355）与右下按钮距右边 10px 和改前一致。
- 交互（Arknights 700 宽，舞台 610）：时装面板 400px 从右侧滑入、不越界；切到「视野」场景背景不变形。
- 全屏（Arknights 1440）：铺满 1440×900，退出后回到 790×576。
- 截图：`build/shots/charinfo-fit-before-arknights-{1440,640}.png`、`charinfo-crop-arknights-{1440,700,640}.png`、
  `charinfo-crop-arknights-700-{scene,skins}.png`、`charinfo-crop-arknights-640-skins.png`、`charinfo-fit-after-vector-640.png`。

## 已知问题

- 裁切不重新居中立绘：立绘位置是 `charinfo.js` 按 1024 宽舞台写的内联 `translate`，舞台越窄越偏右。
  新皮肤最窄的桌面正文栏是 550（640 宽），还能看到大半个人；Vector 601–约 825 宽（正文栏 376–600）人物基本被裁掉，
  但这一段改前本来就是错位溢出的。
- 错位区里 `charinfo.js` 仍以为是手机版，点「时装」后画师 / CV 栏不收起、右下按钮下沉一截，能用但不整齐。
- 640–768 宽下页面仍能横向拖 26–90px：是站点公告（`#siteNotice` 里 800px 宽的 `.nomobile` 横幅），与本微件无关。2026-10-02 已修，见 `../sitenotice/`。

## 落地

```bash
uv run python scripts/charinfo_fit_apply.py --dry-run   # diff 只有 <style> 里新增的一段
uv run python scripts/charinfo_fit_apply.py
```

脚本会核对线上仍是 r410622，否则拒绝整页覆盖。微件改完不会触发页面刷新，470 个嵌入页要等解析缓存过期或手动 purge：

```bash
uv run python scripts/purge_embeddedin.py 模板:CharinfoV2
```
