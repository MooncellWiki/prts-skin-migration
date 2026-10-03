# 「页面样式将要大改」提示只给旧皮肤看（`page-iteration`）

2026-10-02 · `模板:页面迭代` r433218 → r433220 + 新建 `模板:页面迭代/styles.css` r433219（源文件 `模板_页面迭代_styles.css`）·
`干员一览` r429884 → r433221、`公招计算` r288896 → r433222 · 脚本 `scripts/page_iteration_apply.py`

状态：**已上线**（2026-10-02 23:56，BotCathPalug）。没在沙箱演练：沙箱库里没有这个模板（Rafom 15:39 刚建）。

## 问题

`模板:页面迭代` 是 Rafom 建的 `{{cbox2|lv=3}}` 提示框：「这个页面的样式将要发生重大变化……您可以通过页面上方的链接切换至新版预览」。
要挂到干员一览、公招计算顶部，只给 Arknights 以外的皮肤（旧 Vector / Vector 2022 / Minerva）看——在新皮肤上叫人「切换至新版」没意义。

## 改法

解析缓存不分皮肤，框照常输出，由 body 上的皮肤类藏掉（同 `模板:首页/旧版`、`模板:干员筛选` 的 `.ol-notes-legacy`）：

- `模板:页面迭代`：框外包一层 `<div class="prts-page-iteration">`，前面带 `<templatestyles src="页面迭代/styles.css" />`；
  `<noinclude>` 里加一句说明（Arknights 皮肤下模板页本身是空的）。文案是 Rafom 在站内维护的，脚本不拿快照覆盖，只给现网正文套外壳
- `模板:页面迭代/styles.css`：`body.skin-arknights .prts-page-iteration { display: none; }`。样式排在框之前，不会先露一下再藏
- `干员一览` / `公招计算`：正文最前面加 `{{页面迭代}}`，和原来的第一行接在一起，不多出空行。干员一览的 `{{Ads/normal}}{{Ads/mobile}}` 现在是空模板

藏在模板里而不是调用处：以后挂到别的页面也自动只对旧皮肤生效。

## 验证（线上）

1280 宽，`useskin=` 切皮肤，量 `.prts-page-iteration`：

| 皮肤 | 干员一览 | 公招计算 |
| --- | --- | --- |
| 旧 Vector | 显示，112 高，在两条「参阅」提示之上 | 显示，112 高 |
| Vector 2022 | 显示 | 显示 |
| Minerva | — | 显示（`useskin=minerva`） |
| Arknights | `display:none`，0 高 | `display:none`，0 高 |

各皮肤整页宽度不变（1280）。截图：`build/shots/page-iteration-*.png`。

## 撤掉

新皮肤成为默认、旧皮肤退役时：两个页面删掉开头的 `{{页面迭代}}`，模板和样式页可以一起删。
