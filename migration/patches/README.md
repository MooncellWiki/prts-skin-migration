# 仓库级改动记录

迁移涉及的、**本仓库之外**的改动记在这里：改哪个仓库、为什么、怎么验证的、落没落地。

兼容期原则：迁移未完成之前不改现网行为。能证明对旧皮肤零影响的可以直接落；
会改变现网渲染的，先留 `*.patch` + 文档，等切换窗口统一 apply。

---

## 0001 · mw：TemplateStyles 放行 Mooncell 自家域名

**状态**：已落地（`MooncellWiki/mw` 工作区，未提交）· 2026-08-23

**仓库 / 文件**：`MooncellWiki/mw` → `LocalSettings.php`（`wfLoadExtension('TemplateStyles')` 之后）

**为什么**：`$wgTemplateStylesAllowedUrls` 站点从未覆盖，一直是扩展默认值——只放行
`upload.wikimedia.org/wikipedia/commons/`。Mooncell 各站的图片全在自己的域名上，
不放行的话**任何带图的模板都迁不进 TemplateStyles**。

**为什么可以直接落**：它只放宽 `sanitized-css` 的保存校验，不改变任何现有页面的渲染。
现网 73 个 TemplateStyles 页面里 `url()` 出现 0 次（本来也写不进去），所以零回归面。

**做法**：按域名通配，而不是逐个列子域——`media` / `static` / `torappu` 之外以后再冒出新的图床不用再改配置。

```php
$hosts = '(?:[a-z0-9-]+\.)*(?:prts|fgo|mooncell)\.wiki';
```

- `(?:[a-z0-9-]+\.)*` 任意层子域，也允许裸域（`//prts.wiki/`）
- 结尾的 `/` 锚死域名——这是关键，少了它 `prts.wiki.evil.com` 就能过
- `(?:https:)?` 现网 wikitext 大量是协议相对写法 `//media.prts.wiki/…`
- `i` 修饰符兜住大写主机名
- 扩展默认的 Commons 一并留着：本次只做加法，不顺手收窄

**有意不放行的两项**：

- `data:` URI —— 现网只有一处在用（首页列表项的项目符号），而设计稿的首页压根不要项目符号，
  不值得为它开口子。别处真要用，上传成 File: 再引。
- `@font-face`（`font` 白名单留空）—— 字体归皮肤管（`skins.arknights.fonts`），不该让模板自己引。

**验证**（沙箱 `prts-sandbox`，PHP 层直接调 `sanitized-css` 内容处理器的 `sanitize()`，
不写页面、不过 API、不触发滥用过滤器）：19 个用例全部符合预期。

| 应放行 | 应拒绝 |
| --- | --- |
| `//media.prts.wiki/…` `https://media.prts.wiki/…` | `https://media.prts.wiki.evil.com/…` |
| `//static.prts.wiki/…` `//torappu.prts.wiki/…` | `//prts.wiki.evil.com/…` |
| `//media.fgo.wiki/…` `//static.fgo.wiki/…` | `//evilprts.wiki/…` |
| `//ak.mooncell.wiki/…` | `//prts.wiki.co/…` |
| 裸域 `//prts.wiki/…` `//fgo.wiki/…` | `//mooncell.wiki.evil.com/…` |
| 大写 `//MEDIA.PRTS.WIKI/…` | `data:image/png;base64,…` |
| 多层 `//a.b.c.prts.wiki/…` | `https://evil.example.com/…` |
