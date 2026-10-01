"""默认皮肤切换前的站内准备：小工具改绑 / 补新皮肤分支，删掉早已不用的旧页面。

全部对旧皮肤零影响，可以在切换之前落地。见 docs/默认皮肤切换方案.md §2.1。

    uv run python scripts/default_skin_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/default_skin_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/default_skin_apply.py                             # 线上落地
    uv run python scripts/default_skin_apply.py --only gadgets_def          # 只跑某一步
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

DOC = "prts-skin-migration/docs/默认皮肤切换方案.md"
SUMMARY = "默认皮肤切换准备（{}）。见 " + DOC

# 除 Arknights 之外的全部已装皮肤：切换前对任何人都没有变化
OLD_SKINS = "vector,vector-2022,minerva,monobook,timeless"


class Ctx:
    def __init__(self, wiki: Wiki, dry_run: bool) -> None:
        self.wiki = wiki
        self.dry_run = dry_run

    async def edit(self, title: str, transform, what: str) -> None:
        page = await self.wiki.read(title)
        if page.missing:
            raise SystemExit(f"{title} 不存在")
        new = transform(page.content)
        if new is None or new == page.content:
            print(f"  = {title}: 已是目标状态，跳过")
            return
        diff = difflib.unified_diff(
            page.content.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=2
        )
        print("\n".join(diff))
        if self.dry_run:
            print(f"  [dry-run] {title}")
            return
        await self.wiki.edit(title, new, SUMMARY.format(what), baserevid=page.revid, nocreate=True)
        print(f"  ✔ {title} 已写入")

    async def delete(self, title: str, reason: str) -> None:
        page = await self.wiki.read(title)
        if page.missing:
            print(f"  = {title}: 已不存在，跳过")
            return
        if self.dry_run:
            print(f"  [dry-run] 删除 {title}（{reason}）")
            return
        token = await self.wiki._token()  # noqa: SLF001
        data = await self.wiki.post(action="delete", title=title, reason=reason, token=token)
        if "delete" not in data:
            raise SystemExit(f"删除 {title} 失败：{data}")
        print(f"  ✔ 已删除 {title}")


def replace_each(pairs: list[tuple[str, str]]):
    """每对 (old, new) 都得恰好出现一次；全部已是 new 时返回 None（幂等）。"""

    def tf(text: str):
        if all(new in text for _, new in pairs):
            return None
        for old, new in pairs:
            n = text.count(old)
            if n != 1:
                raise SystemExit(f"期望片段出现 1 次，实际 {n} 次：\n{old[:200]}")
            text = text.replace(old, new)
        return text

    return tf


# --------------------------------------------------------------------------- 各步骤


async def step_gadgets_def(c: Ctx) -> None:
    """DarkTheme / darkModeFixV14 锁到旧皮肤（新皮肤下会把正文弄成白底浅灰字）；TippyRef 放开到新皮肤（实测可用）。"""
    await c.edit(
        "MediaWiki:Gadgets-definition",
        replace_each(
            [
                (
                    "* darkModeFixV14[ResourceLoader|type=styles]|darkModeFix.css",
                    f"* darkModeFixV14[ResourceLoader|type=styles|skins={OLD_SKINS}]|darkModeFix.css",
                ),
                (
                    "* DarkTheme[ResourceLoader|type=styles]|DarkTheme.css",
                    f"* DarkTheme[ResourceLoader|type=styles|skins={OLD_SKINS}]|DarkTheme.css",
                ),
                (
                    "* TippyRef[ResourceLoader|type=general|skins=vector]|TippyRef.js|TippyRef.css",
                    "* TippyRef[ResourceLoader|type=general|skins=vector,arknights]|TippyRef.js|TippyRef.css",
                ),
            ]
        ),
        "DarkTheme / darkModeFixV14 只在旧皮肤加载，TippyRef 放开到 Arknights",
    )


async def step_purgecache(c: Ctx) -> None:
    """新皮肤的 #p-personal 是用户菜单里的 nav > ul，交给 addPortletLink 找列表；旧皮肤路径不变。"""
    await c.edit(
        "MediaWiki:Gadget-Purgecache.js",
        replace_each(
            [
                (
                    '    mw.loader.using("moment").then(function() {\n'
                    "        var li = $('<li/>').appendTo(\"#p-personal > .vector-menu-content > ul\"),\n",
                    '    mw.loader.using(["moment", "mediawiki.util"]).then(function() {\n'
                    "        // Arknights 皮肤的 #p-personal 是用户菜单里的 nav > ul，交给 addPortletLink 找列表；旧皮肤照旧\n"
                    "        var li = mw.config.get('skin') === 'arknights'\n"
                    "                ? $(mw.util.addPortletLink('p-personal', '#', '', 'pt-purgecache')).empty()\n"
                    "                : $('<li/>').appendTo(\"#p-personal > .vector-menu-content > ul\"),\n",
                ),
            ]
        ),
        "Purgecache 在 Arknights 皮肤下挂进用户菜单",
    )


async def step_nobacktotop(c: Ctx) -> None:
    await c.edit(
        "MediaWiki:Gadget-NoBackToTop.css",
        replace_each(
            [
                (
                    ".backToTop{\n\tdisplay: none !important;\n}",
                    ".backToTop,\n#ak-back-to-top {\n\tdisplay: none !important;\n}",
                ),
            ]
        ),
        "NoBackToTop 同时隐藏 Arknights 皮肤的回到顶部按钮",
    )


DEAD = {
    "微件:敌人筛选": "旧版敌人一览，已由 微件:EnemiesListV2 取代，0 引用",
    "模板:敌人筛选": "旧版敌人一览，0 引用",
    "模板:敌人筛选数据": "旧版敌人一览的数据行模板，只被本族自己引用",
    "MediaWiki:Gadget-enemyFilter.js": "旧版敌人一览的脚本，未在 Gadgets-definition 注册，加载不到",
    "MediaWiki:Gadget-fixCss.js": "未在 Gadgets-definition 注册、0 引用；若被挂回会在新皮肤下把每页跳到 debug=true",
}


async def step_dead_pages(c: Ctx) -> None:
    for title, why in DEAD.items():
        await c.delete(title, f"{why}。见 {DOC}")


SIDEBAR_EXPLORE = """{{#tsl:zh|探索}}{{#tsl:ja|関連サイトリンク集}}{{#tsl:nozhja|Explore}}
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
**[https://penguin-stats.cn 企鹅物流数据统计]
"""


async def step_sidebar_explore(c: Ctx) -> None:
    """侧栏「探索」组与 Arknights 页脚的「探索」「官方网站」两栏逐条重复（10 条链接全在页脚里），删掉。"""

    def tf(text: str):
        if SIDEBAR_EXPLORE not in text:
            if "Mooncell主站" in text:
                raise SystemExit("「探索」组和脚本里记的不一样了，人工看一下")
            return None
        n = text.count(SIDEBAR_EXPLORE)
        if n != 1:
            raise SystemExit(f"「探索」组期望出现 1 次，实际 {n} 次")
        return text.replace(SIDEBAR_EXPLORE, "")

    await c.edit("MediaWiki:MenuSidebar", tf, "侧栏去掉与新皮肤页脚重复的「探索」组")


async def step_footer_guide(c: Ctx) -> None:
    """页脚「参与」栏的编辑指南指向不存在的 帮助:编辑指南，改成侧栏一直用的 PRTS:编辑指南（重定向到如何帮助我们完善网站）。"""
    await c.edit(
        "MediaWiki:Arknights-footer-links",
        replace_each([("** Help:编辑指南|编辑指南\n", "** PRTS:编辑指南|编辑指南\n")]),
        "页脚编辑指南改指 PRTS:编辑指南（帮助:编辑指南 不存在）",
    )


SIDEBAR_MANAGE_DUP = [
    "*[[PRTS:编辑指南|{{#tsl:zh|编辑指南}}{{#tsl:ja|編集のガイドライン}}{{#tsl:nozhja|Edit Guideline}}]]\n",
    "*[[:分类:PRTS模板|{{#tsl:zh|模板一览}}{{#tsl:ja|テンプレート一覧}}{{#tsl:nozhja|Templates Overview}}]]\n",
    "*[[特殊:贡献得分|{{#tsl:zh|贡献分数}}{{#tsl:ja|貢献得点}}{{#tsl:nozhja|Contribution Scores}}]]\n",
    "*[[PRTS:收支一览|{{#tsl:zh|收支一览}}{{#tsl:ja|収支報告}}{{#tsl:nozhja|Balance Overview}}]]\n",
    "*[[PRTS:特殊贡献|{{#tsl:zh|特殊贡献}}{{#tsl:ja|特別な貢献}}{{#tsl:nozhja|Special Contribution}}]]",
]


async def step_sidebar_manage(c: Ctx) -> None:
    """「管理与编辑」组里与页脚「参与」栏重复的 5 条删掉，留最近更改、常用代码。"""

    def tf(text: str):
        present = [line for line in SIDEBAR_MANAGE_DUP if line in text]
        if not present:
            return None
        for line in present:
            if text.count(line) != 1:
                raise SystemExit(f"期望出现 1 次：{line!r}")
            text = text.replace(line, "")
        return text.rstrip("\n")

    await c.edit("MediaWiki:MenuSidebar", tf, "侧栏「管理与编辑」去掉与新皮肤页脚「参与」栏重复的 5 条")


STEPS = {
    "gadgets_def": step_gadgets_def,
    "purgecache": step_purgecache,
    "nobacktotop": step_nobacktotop,
    "dead_pages": step_dead_pages,
    "sidebar_explore": step_sidebar_explore,
    "footer_guide": step_footer_guide,
    "sidebar_manage": step_sidebar_manage,
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ap.add_argument("--only", action="append", choices=list(STEPS), help="只跑指定步骤，可重复")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    settings = get_settings()
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        username, password = settings.require_credentials()
        await wiki.login(username, password)
        c = Ctx(wiki, ns.dry_run)
        for name in ns.only or list(STEPS):
            print(f"\n=== {name}")
            await STEPS[name](c)


if __name__ == "__main__":
    asyncio.run(main())
