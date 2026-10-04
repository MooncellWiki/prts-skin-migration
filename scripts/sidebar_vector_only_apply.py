"""侧栏按皮肤分流：新皮肤另有去处的项只给 Vector 看，之前为新皮肤删掉的项在 Vector 下加回来。

`MediaWiki:MenuSidebar` 是 Vector（VectorMenuSidebar）与新皮肤共用的一页。10-01 起为了新皮肤陆续从这页删掉了
与页脚重复的项（「探索」组、「管理与编辑」里 5 条、「赞助者一览」），Vector 下这些链接就没了，旧皮肤的页脚里也没有。

做法：VectorMenuSidebar 0.1.0 起按皮肤读取——有 `MediaWiki:MenuSidebar-vector` 就用它，没有才读 `MediaWiki:MenuSidebar`。
菜单仍只有一份：

- `MediaWiki:MenuSidebar-vector` 只有一行 `{{MediaWiki:MenuSidebar|vector=1}}`，带着参数嵌入共用的那一页；
- `MediaWiki:MenuSidebar` 里只给 Vector 看的部分包在 `{{#if:{{{vector|}}}|…}}` 里。新皮肤直接解析这一页，
  `{{{vector|}}}` 为空，这些项根本不输出（不靠 CSS 隐藏）；BotPtilopsis 照旧只改这一页。

`{{#if:}}` 的写法有两条讲究（都是 wikitext 的行为）：
- 列表里的条件行接在上一行行尾：`*上一项{{#if:{{{vector|}}}|*只给 Vector 的项}}`。结果以 `*` 开头时解析器会自动另起一行；
  单独占一行的话，条件不成立时会留下一个空行，把列表断成两个 `<ul>`。
- 整组（标题 + 列表）单独占一行：标题是普通段落，接在上一行行尾会并进上一个列表项；它前后本来就是组与组的分界，空行无妨。

这次动的项：

| 项 | Vector | 新皮肤 |
| --- | --- | --- |
| 复制短链接 | 侧栏（原样；首页上第一行是它） | 标题末尾的链条图标（`$wgArknightsShortUrl`）；侧栏第一行恒为「首页」 |
| 赞助者一览（10-04 删） | 侧栏，加回 | 页脚「参与」栏（已有） |
| 「探索」组（10-01 删） | 侧栏，加回 | 页脚「探索」「官方网站」两栏（已有） |
| 编辑指南 / 模板一览 / 贡献分数 / 收支一览 / 特殊贡献（10-01 删） | 侧栏，加回 | 页脚「参与」栏（已有） |
| 常用代码 | 侧栏（原样） | 页脚「参与」栏（本脚本加） |

Vector 下的结果与删减之前逐行相同（顺序也是）。

**上线顺序**：先让 VectorMenuSidebar ≥ 0.1.0 上线（脚本会查，没到就不写——旧版只读 `MediaWiki:MenuSidebar`，
改完之后 Vector 下会连复制短链接、常用代码也没了），新皮肤带标题末尾短链接图标的版本也要先上线
（post-config 里设 `$wgArknightsShortUrl = '/id/$1'`），否则新皮肤下暂时没有复制短链接的入口。
写入顺序：页脚、`MenuSidebar-vector` 在前，侧栏在后。

    uv run python scripts/sidebar_vector_only_apply.py --dry-run                 # 只打印 diff
    uv run python scripts/sidebar_vector_only_apply.py -c config.sandbox.toml    # 先在沙箱演练
    uv run python scripts/sidebar_vector_only_apply.py                           # 线上落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config  # noqa: E402
from wikibot.wiki import Wiki  # noqa: E402

SUMMARY = "侧栏按皮肤分流（{}）。见 prts-skin-migration/scripts/sidebar_vector_only_apply.py"

VMS = "VectorMenuSidebar"
VMS_MIN = (0, 1, 0)  # 按皮肤读取 MediaWiki:MenuSidebar-<skin> 的第一个版本

PARAM = "{{{vector|}}}"


def vector_only(inner: str) -> str:
    return "{{#if:" + PARAM + "|" + inner + "}}"


SIDEBAR = "MediaWiki:MenuSidebar"
SIDEBAR_VECTOR = "MediaWiki:MenuSidebar-vector"
SIDEBAR_VECTOR_TEXT = "{{MediaWiki:MenuSidebar|vector=1}}"

HOME = "{{#tsl:zh|[[首页]]}}{{#tsl:ja|[[首页|メインページ]]}}{{#tsl:nozhja|[[首页|Main page]]}}"
COPY_URL = (
    "{{#tsl:zh|{{#Widget:CopyURL|title=复制短链接|id=sidebar|url=https://prts.wiki/id/{{PAGEID}}}}}}"
    "{{#tsl:ja|{{#Widget:CopyURL|title=短縮URL|id=sidebar|url=https://prts.wiki/id/{{PAGEID}}}}}}"
    "{{#tsl:nozhja|{{#Widget:CopyURL|title=Short URL|id=sidebar|url=https://prts.wiki/id/{{PAGEID}}}}}}"
)
# 首组的头两行：首页上只有复制短链接，特殊页面只有首页，其它页面两行都有
FIRST = (
    "{{#ifeq:{{FULLPAGENAME}}|首页|" + COPY_URL + "|{{#ifeq:{{NAMESPACENUMBER}}|-1|" + HOME + "|" + HOME + "\n"
    "*" + COPY_URL + "}}}}"
)

SUPPORT = (
    "*{{#tsl:zh|[[PRTS:如何帮助我们完善网站#资助我们改善访问质量|支持我们]]}}"
    "{{#tsl:ja|[[PRTS:如何帮助我们完善网站#资助我们改善访问质量|Support us]]}}"
    "{{#tsl:nozhja|[[PRTS:如何帮助我们完善网站#资助我们改善访问质量|Support us]]}}"
)
SPONSORS = (
    "*{{#tsl:zh|[[PRTS:如何帮助我们完善网站#赞助者公示|赞助者一览]]}}"
    "{{#tsl:ja|[[PRTS:如何帮助我们完善网站#赞助者公示|スポンサー一覧]]}}"
    "{{#tsl:nozhja|[[PRTS:如何帮助我们完善网站#赞助者公示|Sponsors list]]}}"
)

# 「探索」组：10-01 删掉的原文（default_skin_apply.py 的 SIDEBAR_EXPLORE）
EXPLORE = """\
{{#tsl:zh|探索}}{{#tsl:ja|関連サイトリンク集}}{{#tsl:nozhja|Explore}}
*[https://fgo.wiki {{#tsl:zh|Mooncell主站}}{{#tsl:ja|Mooncell (FGO攻略Wiki)}}{{#tsl:nozhja|Mooncell(FGOWiki)}}]
*'''{{#tsl:zh|官方网站}}{{#tsl:ja|公式サイト}}{{#tsl:nozhja|Offical Website}}'''
**[https://ak.hypergryph.com 明日方舟简中服官网]
**[https://monster-siren.hypergryph.com/ 塞壬唱片]
**[https://terra-historicus.hypergryph.com/ 泰拉记事社]
**[https://www.arknights.jp 明日方舟日服官网]
**[https://www.arknights.global 明日方舟美服官网]
**[https://ak.gryphline.com 明日方舟台服官网]
**[https://www.arknights.kr 明日方舟韩服官网]
*'''{{#tsl:zh|友情链接}}{{#tsl:ja|相互リンク}}{{#tsl:nozhja|Link Exchange}}'''
**[http://www.gfwiki.org 少前百科GFwiki]
**[https://penguin-stats.cn 企鹅物流数据统计]"""

MANAGE_HEADING = "{{#tsl:zh|管理与编辑}}{{#tsl:ja|管理と編集}}{{#tsl:nozhja|Management and Editing}}\n"
RECENT = "*[[特殊:最近更改|{{#tsl:zh|最近更改}}{{#tsl:ja|最近の更新}}{{#tsl:nozhja|Recent Changes}}]]"
USEFUL_CODES = "*[[PRTS:常用代码|{{#tsl:zh|常用代码}}{{#tsl:ja|マークアップ早見表}}{{#tsl:nozhja|Useful Codes}}]]"
# 「管理与编辑」里除最近更改之外的 6 条，删减之前的顺序（常用代码一直在，其余 5 条 10-01 删）
MANAGE_ROWS = [
    "*[[PRTS:编辑指南|{{#tsl:zh|编辑指南}}{{#tsl:ja|編集のガイドライン}}{{#tsl:nozhja|Edit Guideline}}]]",
    USEFUL_CODES,
    "*[[:分类:PRTS模板|{{#tsl:zh|模板一览}}{{#tsl:ja|テンプレート一覧}}{{#tsl:nozhja|Templates Overview}}]]",
    "*[[特殊:贡献得分|{{#tsl:zh|贡献分数}}{{#tsl:ja|貢献得点}}{{#tsl:nozhja|Contribution Scores}}]]",
    "*[[PRTS:收支一览|{{#tsl:zh|收支一览}}{{#tsl:ja|収支報告}}{{#tsl:nozhja|Balance Overview}}]]",
    "*[[PRTS:特殊贡献|{{#tsl:zh|特殊贡献}}{{#tsl:ja|特別な貢献}}{{#tsl:nozhja|Special Contribution}}]]",
]


def once(text: str, old: str, new: str, what: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{what}：期望出现 1 次，实际 {n} 次，页面和脚本里记的不一样了，人工看一下")
    return text.replace(old, new)


def sidebar(text: str) -> str:
    if PARAM in text:
        return text
    for gone in ("赞助者一览", "Mooncell主站", "PRTS:编辑指南", "PRTS:特殊贡献"):
        if gone in text:
            raise SystemExit(f"侧栏里还有「{gone}」，不是脚本预期的删减后状态，人工看一下")
    if not text.startswith("*" + FIRST + "\n"):
        raise SystemExit("侧栏头两行（首页 / 复制短链接）和脚本里记的不一样了，人工看一下")
    # Vector：头两行原样；新皮肤：恒为「首页」（首页上是当前页高亮）
    text = "*" + vector_only(FIRST + "|" + HOME) + text[len("*" + FIRST) :]
    text = once(text, SUPPORT + "\n", SUPPORT + vector_only(SPONSORS) + "\n", "支持我们")
    text = once(text, MANAGE_HEADING, vector_only(EXPLORE) + "\n" + MANAGE_HEADING, "「管理与编辑」标题")
    tail = RECENT + "\n" + USEFUL_CODES
    if not text.rstrip("\n").endswith(tail):
        raise SystemExit("「管理与编辑」组不是「最近更改、常用代码」两条收尾，人工看一下")
    return once(text, tail, RECENT + vector_only("\n".join(MANAGE_ROWS)), "「管理与编辑」组")


def sidebar_vector(text: str) -> str:
    if text.strip() not in ("", SIDEBAR_VECTOR_TEXT):
        raise SystemExit(f"{SIDEBAR_VECTOR} 已经有别的内容了，人工看一下")
    return SIDEBAR_VECTOR_TEXT


FOOTER = "MediaWiki:Arknights-footer-links"
FOOTER_GUIDE = "** PRTS:编辑指南|编辑指南\n"
FOOTER_CODES = "** PRTS:常用代码|常用代码\n"


def footer(text: str) -> str:
    if FOOTER_CODES in text:
        return text
    return once(text, FOOTER_GUIDE, FOOTER_GUIDE + FOOTER_CODES, "页脚「参与」栏的编辑指南")


# 顺序有讲究：页脚、MenuSidebar-vector 在前（后者在侧栏改之前嵌入的还是旧内容，Vector 没有变化），侧栏在后
EDITS = [
    (FOOTER, footer, "常用代码进页脚「参与」栏", False),
    (SIDEBAR_VECTOR, sidebar_vector, "Vector 读这一页：带 vector=1 嵌入共用的 MenuSidebar", True),
    (
        SIDEBAR,
        sidebar,
        "只给 Vector 看的项包进 {{#if:{{{vector|}}}|…}}：复制短链接、常用代码，以及加回的赞助者一览、「探索」组、「管理与编辑」5 条",
        False,
    ),
]


async def require_vms(wiki: Wiki) -> None:
    data = await wiki.post(action="query", meta="siteinfo", siprop="extensions")
    for ext in data["query"]["extensions"]:
        if ext.get("name") == VMS:
            version = ext.get("version", "0")
            if tuple(int(p) for p in version.split(".")) < VMS_MIN:
                need = ".".join(map(str, VMS_MIN))
                raise SystemExit(f"站点上的 {VMS} 是 {version}，要 ≥ {need}（按皮肤读取）才能改侧栏，先让扩展上线")
            print(f"{VMS} {version}")
            return
    raise SystemExit(f"站点上没有装 {VMS}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    settings = get_settings()
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        username, password = settings.require_credentials()
        await wiki.login(username, password)
        await require_vms(wiki)
        for title, transform, what, create in EDITS:
            page = await wiki.read(title)
            if page.missing and not create:
                raise SystemExit(f"{title} 不存在")
            old = "" if page.missing else page.content
            new = transform(old)
            if new == old:
                print(f"  = {title}: 已是目标状态，跳过")
                continue
            diff = difflib.unified_diff(old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=0)
            print("\n".join(diff))
            if ns.dry_run:
                print(f"  [dry-run] {title}" + ("（新建）" if page.missing else f"（原 rev {page.revid}）"))
                continue
            if page.missing:
                await wiki.edit(title, new, SUMMARY.format(what), nocreate=False)
                print(f"  ✔ {title} 已新建")
            else:
                await wiki.edit(title, new, SUMMARY.format(what), baserevid=page.revid, nocreate=True)
                print(f"  ✔ {title} 已写入（原 rev {page.revid}）")


if __name__ == "__main__":
    asyncio.run(main())
