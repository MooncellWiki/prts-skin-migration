# prts-skin-migration

把 [prts.wiki](https://prts.wiki) 现有的**模板**与**微件**迁移到新版皮肤
（[mediawiki-skins-Arknights](https://github.com/MooncellWiki/mediawiki-skins-Arknights)）的机器人。

结构上参考 [Ptilopsis_Bot](https://github.com/MooncellWiki/Ptilopsis_Bot)：
非敏感配置进 `config.toml` 由 pydantic 校验，凭据走环境变量 / `.env`（pydantic-settings），日志用 loguru，
HTTP 走 httpx + asyncio。

## 它解决什么问题

换皮肤会打断一大批写死的东西。先摸清楚有多少，再决定改哪些、怎么改：

```
scan  ── 摸底：哪些页面用了旧写法，出报告
plan  ── 预演：规则会把页面改成什么样，出 diff，不写
apply ── 落地：带 baserevid 防冲突地写回，进度记在 state.json
```

`scan` / `plan` 默认读**本地沙箱库**（`../prts-sandbox` 的 MySQL），一次 SQL 拉完 1900 个模板 / 微件，
不受 API 限流也不打扰线上；`apply` 永远走 API。

首页的迁移盘点见 [docs/首页迁移盘点.md](docs/首页迁移盘点.md)。

## 快速开始

```bash
uv sync
cp .env.example .env        # 填 WIKI_USERNAME / WIKI_PASSWORD
uv run wikibot check        # 自检：线上 API 登录 + 沙箱库连通
uv run wikibot rules        # 看有哪些规则
uv run wikibot scan -t all  # 全量摸底
```

`wikibot check` 的输出大致是：

```
api_url  https://prts.wiki/api.php
  站点     PRTS（MediaWiki 1.43.5）
  登录     BotCathPalug（Editor, bot, sysop, *, user, autoconfirmed）

sandbox  127.0.0.1:3307/ak
  template    771 个页面
  widget      469 个页面
  module      92 个页面
  sitecss     73 个页面
  all         1929 个页面
```

## 命令

| 命令 | 作用 |
| --- | --- |
| `wikibot check` | 连通性自检（API 登录 + 沙箱库） |
| `wikibot targets` / `rules` | 列出目标集合 / 规则 |
| `wikibot pages -t template` | 列出目标集合里的页面 |
| `wikibot fetch -t template` | 把正文抓到 `cache/`，之后可完全离线 |
| `wikibot scan -t all` | 扫描旧写法，出 `reports/scan-*.md` + `.jsonl` |
| `wikibot plan -t template -r font-tag` | 预演改写，出 `reports/plan-*.md` + `.diff` |
| `wikibot apply -t template --dry-run` | 空跑；去掉 `--dry-run` 才真写 |
| `wikibot status` | 看迁移进度 |

公共选项：`-c/--config` 换配置文件、`-v` 打 DEBUG 日志、`--dry-run` 全局只读、
`--source db|api` 选数据来源、`-n/--limit` 限量、`-r/--rule` 选规则。

先在沙箱站点上验证写入，再对线上跑：

```bash
uv run wikibot -c config.sandbox.toml apply -t template -r font-tag
```

## 规则

规则同时负责**检测**（scan 报告哪里有旧写法）和**改写**（plan / apply 重写），两者共用同一套匹配，
所以「扫描到的」和「会被改的」永远是同一批位置。

内置 13 条，其中 12 条是 `detect_only`（只报告不改写）—— 新皮肤的类名与 CSS 变量还在定，
先摸清现状比贸然批量替换安全。`wikibot rules` 看全部。规则不是拍脑袋定的，是拿沙箱库跑出来的：

| 规则 | 命中页面 | 说明 |
| --- | ---: | --- |
| `raw-style-attr` | 544 | 较长的行内 style，应抽到 TemplateStyles |
| `hardcoded-color` | 458 | 写死颜色，暗色模式下会瞎 |
| `fixed-px-width` | 392 | 写死像素宽度，窄屏溢出 |
| `css-important` | 249 | 在跟旧皮肤样式打架 |
| `px-font-size` | 124 | px 字号不跟随用户设置 |
| `dual-render` | 88 | `.nomobile` / `.nodesktop` 双份渲染 |
| `hardcoded-skin-name` | 64 | `skin-vector-2022` 之类，换皮肤后整段失效 |
| `float-layout` | 48 | float 布局 |
| `legacy-skin-selector` | 32 | `#content` / `.mw-body` 等旧皮肤 DOM 选择器 |
| `deprecated-html-attr` | 68 | HTML4 表现属性 |
| `center-tag` / `font-tag` | 8 / 4 | HTML5 已废弃的标签（`font-tag` 会自动改写） |

加规则有两条路：

- **声明式**——简单的查找替换写进 `config.toml` 的 `[[regex_rules]]`，改规则不用动代码。
- **Python**——复杂逻辑写成 `wikibot/rules/skin.py` 里的 `Rule` 子类，配单测。

### 改写的两条安全线

这两条都是被真实数据打出来的，别拆：

1. **保护区**：`<nowiki>` `<pre>` `<syntaxhighlight>` 与 HTML 注释里的内容既不改也不报（那是给人看的示例）；
   `<script>` `<style>` 里的内容不改但仍报告——微件里大量原始 JS，wikitext 规则改进去必然改坏。
2. **拿不准就不动**：`font-tag` 只改成对出现、不嵌套、且属性里没有 wiki 标记的标签。
   现网大量 `<font color={{#switch:…}}>` 这种属性值由解析器函数拼出来的写法，正则改它必然改坏。

## 配置

| 内容 | 位置 |
| --- | --- |
| API 地址、目标名字空间、沙箱库连接、声明式规则 | `config.toml`，随仓库提交，由 `wikibot/config.py` 的 pydantic 模型校验（多写 / 写错字段直接报错） |
| Wiki 登录凭据 | 环境变量，本地用 `.env`（已 gitignore），CI 用 Actions Secrets |

| 环境变量 | 必填 | 说明 |
| --- | --- | --- |
| `WIKI_USERNAME` | 是 | 不带 `@BotName` 后缀 |
| `WIKI_PASSWORD` | 是 | 请用 [Special:BotPasswords](https://prts.wiki/w/Special:BotPasswords) 生成，**不要用主账号密码**（用主账号密码登录会收到 API 弃用警告） |
| `WIKI_SANDBOX_PASSWORD` | 否 | 覆盖 `config.toml` 里的沙箱库口令 |
| `WIKI_CONFIG_PATH` | 否 | 指定 `config.toml` 路径 |

目标集合（`-t`）在 `config.toml` 的 `[targets.*]` 里定义，按名字空间 + 标题正则选页面：
`template` / `widget` / `module` / `sitecss` / `styles` / `all`。

## 本地沙箱

`../prts-sandbox` 是一份生产形态的本地 MediaWiki（Caddy + php-fpm + MySQL，见它的 README）。
本项目只读它的库：

```bash
docker compose -f ../prts-sandbox/docker-compose.yml up -d
uv run wikibot check
```

`DbSource` 直接按 MediaWiki 1.43 的 MCR 存储（`page → slots → content → text`）取最新修订的正文，
用非缓冲游标流式读，不会把整个名字空间读进内存。沙箱库目前正文全是 utf-8 明文；
真碰上压缩 / 外部存储会报错让你改用 `--source api`。

## 开发

```bash
uv run ruff check . && uv run ruff format .
uv run pytest
uv run pre-commit install
```
