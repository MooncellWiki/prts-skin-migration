"""新皮肤首页：`/sandbox` 页是预发环境，``--mainpage`` 把同一套内容以正式页名发布到真首页。

推三类页面：

1. **生成物**——`build_mainpage_sandbox.py` 从设计稿转出来的页面、微件、`模板:行动日历/sandbox`。
2. **手写模板**——`migration/mainpage/templates/` 下的文件，文件名与页面标题的对应见 `PAGES`。
3. **数据页**——近期新增的 `首页/新增关卡`、`首页/新增主题`、`首页/新增单件` 由 BotPtilopsis
   直接按新格式写（MooncellWiki/Ptilopsis_Bot#26），sandbox 与真首页读同一份。还是旧格式的
   （自由排版的列表与 `{{家具}}`）在这里一次性转过去，已经是新格式的不动。

默认只写 `/sandbox` 页与 `微件:Mpstyle/newskin`。`首页/网页活动` 是人工维护的数据页，
只在它不存在时建一个空壳，已有的不覆盖。

加 ``--mainpage`` 才动真首页：每个 `/sandbox` 页以正式页名再发一份（页内引用同步改名，
见 `prod_title`），依赖页的保护补到与旧首页对应页面同级，最后把正文写进 `首页`
（沿用现网 `首页` 里的 ``{{#seo:}}``）。覆盖已有页面时打印原 revid，回滚按它恢复。

    uv run python scripts/build_mainpage_sandbox.py                           # 先生成
    uv run python scripts/mainpage_sandbox_apply.py --dry-run                 # 只打印 diff
    uv run python scripts/mainpage_sandbox_apply.py -c config.sandbox.toml    # 先在沙箱演练
    uv run python scripts/mainpage_sandbox_apply.py                           # 线上 sandbox
    uv run python scripts/mainpage_sandbox_apply.py --mainpage                # 发布到真首页
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki

SCRIPT = "prts-skin-migration/scripts/mainpage_sandbox_apply.py"
SUMMARY = "新皮肤首页（首页/sandbox）：按设计稿落地，见 " + SCRIPT
MAINPAGE = "首页"
MAINPAGE_SUMMARY = "首页换成新版（按新皮肤设计稿重排，各皮肤通用），见 " + SCRIPT
PROMOTE_SUMMARY = "新首页：由 /sandbox 版发布为正式版，见 " + SCRIPT
DATA_SUMMARY = (
    "转成新首页的模板调用（BotPtilopsis 之后直接按这个格式写，"
    "见 MooncellWiki/Ptilopsis_Bot#26）"
)
PROTECT_SUMMARY = "新首页的依赖页：保护级别同旧首页对应的页面，见 " + SCRIPT
# 正式页名默认是去掉 /sandbox；例外：模板:行动日历 还被 新人入门 用着（旧版表格），新版另起名。
PROD_RENAME = {"模板:行动日历/sandbox": "模板:首页/行动日历"}
# 旧首页的依赖页都有保护：结构性的 模板:首页轮播 / 行动日历 / Mpbutton 是 sysop，其余 autoconfirmed。
# 新首页的依赖页按旧首页对应页面的级别补上，不然谁都能借它们改首页。
SYSOP_PAGES = {
    "模板:首页轮播/sandbox",
    "模板:首页轮播/项/sandbox",
    "模板:首页轮播/状态标/sandbox",
    "模板:行动日历/sandbox",
    "模板:Mpbutton/sandbox",
}
LEVELS = {"": 0, "autoconfirmed": 1, "sysop": 2}
SEO = re.compile(r"\{\{#seo:.*?\n\}\}", re.DOTALL)

TEMPLATES = ROOT / "migration/mainpage/templates"

# 页面标题 → 源文件。前三个是生成物（build/），其余是手写模板。
GENERATED = {
    "微件:Mpstyle/newskin": "widget-mpstyle-newskin.txt",
    "模板:行动日历/sandbox": "templates/模板_行动日历_sandbox.wiki",
    "首页/sandbox": "page-mainpage-sandbox.wiki",
}
PAGES = {
    "模板:首页轮播/sandbox": "模板_首页轮播_sandbox.wiki",
    "模板:首页轮播/项/sandbox": "模板_首页轮播_项_sandbox.wiki",
    "模板:首页轮播/状态标/sandbox": "模板_首页轮播_状态标_sandbox.wiki",
    "模板:首页/网页活动行/sandbox": "模板_首页_网页活动行_sandbox.wiki",
    "模板:Mpbutton/sandbox": "模板_Mpbutton_sandbox.wiki",
    "模板:当前信息/sandbox": "模板_当前信息_sandbox.wiki",
    "模板:当前信息/条/sandbox": "模板_当前信息_条_sandbox.wiki",
    "模板:当前信息/临时提醒/sandbox": "模板_当前信息_临时提醒_sandbox.wiki",
    "模板:首页/亮点干员卡/sandbox": "模板_首页_亮点干员卡_sandbox.wiki",
    "模板:首页/亮点干员卡/模组/sandbox": "模板_首页_亮点干员卡_模组_sandbox.wiki",
    "模板:首页/亮点干员图标/sandbox": "模板_首页_亮点干员图标_sandbox.wiki",
    "模板:首页/亮点干员组/sandbox": "模板_首页_亮点干员组_sandbox.wiki",
    "首页/亮点干员/sandbox": "页面_首页_亮点干员_sandbox.wiki",
    "模板:首页/新增关卡/sandbox": "模板_首页_新增关卡_sandbox.wiki",
    "模板:首页/新增关卡/章节/sandbox": "模板_首页_新增关卡_章节_sandbox.wiki",
    "模板:首页/新增关卡/关卡/sandbox": "模板_首页_新增关卡_关卡_sandbox.wiki",
    "模板:首页/家具卡/sandbox": "模板_首页_家具卡_sandbox.wiki",
    "模板:首页/家具卡/渲染/sandbox": "模板_首页_家具卡_渲染_sandbox.wiki",
}
# 只在不存在时创建的页面：人工维护的数据，已有的不能覆盖。
CREATE_ONLY = {
    "首页/网页活动": (
        "<noinclude>\n"
        "首页 Hero 下方的「进行中的网页活动」列表，'''人工维护'''。\n"
        "一行一个活动，时间写北京时间，过了 <code>end</code> 自动消失；一条都没有时整块不显示。\n"
        "行的写法见 {{tl|首页/网页活动行}}。\n"
        "----\n"
        "</noinclude><includeonly></includeonly>"
    ),
}

HEADING = re.compile(r"^'''(.+?)'''$")
STAGE = re.compile(r"^\*\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\]\s*$")
MAX_GROUPS = 6  # 模板:首页/新增关卡 接的「分组名 + 关卡」对数


def _prefix(stage: str) -> str:
    """关卡码的前缀：`TO-EX-1 电影防沉迷` → `TO`。"""
    return stage.split(" ", 1)[0].split("-", 1)[0]


def convert_stages(text: str) -> str:
    """旧版 首页/新增关卡 的自由排版 → {{首页/新增关卡}} 调用，写法同 BotPtilopsis。

    旧版是「加粗行 + 无序列表」，活动名和分组名都是加粗行，写法上分不出来。
    按关卡码判：加粗行底下的关卡换了一批前缀（`TO-*` → `EE-*`），就是新的活动；
    前缀没变就是同一个活动里的下一个分组。后面紧跟着另一个加粗行的也是活动名。
    """
    blocks: list[tuple[str, list[str]]] = []  # (加粗行, 它底下的关卡)
    for raw in text.splitlines():
        line = raw.strip()
        if m := HEADING.match(line):
            blocks.append((m.group(1).strip(), []))
        elif m := STAGE.match(line):
            if not blocks:  # 机器人刚写、编辑还没补标题：整段算一个不分组的块
                blocks.append(("", []))
            blocks[-1][1].append(m.group(1).strip())
        elif line:
            raise SystemExit(f"首页/新增关卡 里有认不出的行，请人工看一下：{line}")

    events: list[tuple[str, list[tuple[str, list[str]]]]] = []
    seen: set[str] = set()
    for title, stages in blocks:
        prefixes = {_prefix(s) for s in stages}
        if not stages:  # 后面紧跟另一个加粗行：活动名
            events.append((title, []))
            seen = set()
        elif events and (not seen or prefixes & seen):  # 当前活动的一个分组
            events[-1][1].append((title, stages))
            seen |= prefixes
        else:  # 换了一批关卡码：不分组的新活动
            events.append((title, [("", stages)]))
            seen = prefixes

    out = []
    for title, groups in events:
        if len(groups) > MAX_GROUPS:
            raise SystemExit(
                f"「{title}」有 {len(groups)} 个分组，模板只接 {MAX_GROUPS} 个"
            )
        names = [s for _, stages in groups for s in stages]
        lines = ["{{首页/新增关卡", f"|1={title}"]
        if en := " · ".join(dict.fromkeys(_prefix(s) for s in names)):
            lines.append(f"|en={en}")
        for i, (name, stages) in enumerate(groups):
            calls = "".join(f"{{{{首页/新增关卡/关卡|{s}}}}}" for s in stages)
            lines += [f"|{2 * i + 2}={name}", f"|{2 * i + 3}={calls}"]
        out.append("\n".join([*lines, "}}"]))
    return "\n".join(out)


def convert_furniture(text: str) -> str:
    """旧版 首页/新增主题、首页/新增单件 的 {{家具主题}} / {{家具}} → {{首页/家具卡}}。"""
    calls = re.findall(
        r"\{\{\s*(家具主题|家具)\s*\|\s*([^|{}]+?)\s*(?:\|[^{}]*)?\}\}", text
    )
    rest = re.sub(r"\{\{\s*(?:家具主题|家具)\s*\|[^{}]*\}\}", "", text).strip()
    if rest:
        raise SystemExit(f"家具数据页里有认不出的内容，请人工看一下：{rest}")
    return "".join(
        f"{{{{首页/家具卡|1={name}" + ("|theme=1" if kind == "家具主题" else "") + "}}"
        for kind, name in calls
    )


# 数据页 → (转换函数, 已是新格式的标志)
DATA = {
    "首页/新增关卡": (convert_stages, "{{首页/新增关卡"),
    "首页/新增主题": (convert_furniture, "{{首页/家具卡"),
    "首页/新增单件": (convert_furniture, "{{首页/家具卡"),
}


def prod_title(title: str) -> str:
    """/sandbox 页对应的正式页名。"""
    return PROD_RENAME.get(title, title.removesuffix("/sandbox"))


def to_prod(text: str, staged: list[str]) -> str:
    """页内对 /sandbox 页的引用（模板调用、#ask 的 template=、{{tl}}、:页面）换成正式页名。"""
    pairs = [(t.split(":", 1)[-1], prod_title(t).split(":", 1)[-1]) for t in staged]
    for old, new in sorted(pairs, key=lambda p: -len(p[0])):
        text = text.replace(old, new)
    if "/sandbox" in text:
        line = next(x for x in text.splitlines() if "/sandbox" in x)
        raise SystemExit(f"发布正式版时还剩对 /sandbox 页的引用：{line.strip()[:120]}")
    return text


async def put(
    wiki: Wiki,
    title: str,
    new: str,
    dry_run: bool,
    summary: str = SUMMARY,
    create_only: bool = False,
) -> None:
    """写一页；覆盖已有页面时打印原 revid，回滚按它恢复。"""
    page = await wiki.read(title)
    old = "" if page.missing else page.content
    if create_only and not page.missing:
        print(f"  = {title}: 已存在（人工维护），不覆盖")
        return
    if old.rstrip("\n") == new.rstrip("\n"):
        print(f"  = {title}: 无变化")
        return
    diff = list(
        difflib.unified_diff(
            old.split("\n"),
            new.split("\n"),
            f"{title} (old)",
            f"{title} (new)",
            lineterm="",
            n=1,
        )
    )
    added = sum(1 for x in diff if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in diff if x.startswith("-") and not x.startswith("---"))
    state = "新建" if page.missing else f"+{added} -{removed} 行，原 rev {page.revid}"
    if dry_run:
        print("\n".join(x[:200] for x in diff[:40]))
        print(f"  [dry-run] {title}（{state}）")
        return
    await wiki.edit(
        title,
        new,
        summary,
        baserevid=None if page.missing else page.revid,
        nocreate=False,
    )
    print(f"  ✔ {title}（{state}）")


async def migrate_data(wiki: Wiki, dry_run: bool) -> None:
    """近期新增三页：还是旧格式的转成新格式；空页与已是新格式的不动。"""
    for title, (convert, marker) in DATA.items():
        page = await wiki.read(title)
        if page.missing or not page.content.strip() or marker in page.content:
            print(f"  = {title}: 已是新格式")
            continue
        await put(wiki, title, convert(page.content), dry_run, DATA_SUMMARY)


def mainpage_text(page: str, current: str) -> str:
    """真首页的正文：与 首页/sandbox 同一份，末尾接上现网 首页 里的 {{#seo:}}（标题 / 关键词 / 描述）。"""
    seo = SEO.findall(current)
    if len(seo) != 1:
        raise SystemExit(
            f"现网 {MAINPAGE} 里的 {{{{#seo:}}}} 应当正好一处，实际 {len(seo)} 处，请人工看一下"
        )
    return page.rstrip("\n") + "\n" + seo[0] + "\n"


async def protect_deps(wiki: Wiki, deps: list[str], dry_run: bool) -> None:
    """依赖页的保护补到与旧首页对应页面同级；只升不降。"""
    sysop = {prod_title(t) for t in SYSOP_PAGES}
    current = await wiki.protection(deps)
    for title in deps:
        want = "sysop" if title in sysop else "autoconfirmed"
        have = current.get(title, {})
        # 已经更严（或是不认识的级别）的保持原样
        levels = {
            kind: max(have.get(kind, ""), want, key=lambda x: LEVELS.get(x, 99))
            for kind in ("edit", "move")
        }
        if levels == {k: have.get(k, "") for k in levels}:
            print(f"  = {title}: 已保护（{have}）")
            continue
        await wiki.protect(title, levels, PROTECT_SUMMARY)
        print(
            f"  {'[dry-run] ' if dry_run else '✔ '}保护 {title}：{have or '无'} → {levels}"
        )


async def publish_mainpage(
    wiki: Wiki, sources: dict[str, Path], staged: list[str], dry_run: bool
) -> None:
    """正式版依赖先到位、补上保护，最后写真首页：不留「首页已换、依赖没到位 / 没保护」的空窗。"""
    for title in staged:
        text = to_prod(sources[title].read_text(encoding="utf-8"), staged)
        await put(wiki, prod_title(title), text, dry_run, PROMOTE_SUMMARY)
    await migrate_data(wiki, dry_run)

    # 网页活动是人工维护的页，只把行模板换成正式版，内容不动
    events = await wiki.read("首页/网页活动")
    if not events.missing:
        text = to_prod(events.content, staged)
        await put(wiki, "首页/网页活动", text, dry_run, PROMOTE_SUMMARY)

    deps = [prod_title(t) for t in staged] + [*DATA, *CREATE_ONLY]
    await protect_deps(wiki, deps, dry_run)

    page = to_prod(sources["首页/sandbox"].read_text(encoding="utf-8"), staged)
    old = await wiki.read(MAINPAGE)
    text = mainpage_text(page, old.content)
    await put(wiki, MAINPAGE, text, dry_run, MAINPAGE_SUMMARY)
    await wiki.purge([MAINPAGE])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c",
        "--config",
        type=Path,
        help="换配置文件，如 config.sandbox.toml 先在沙箱演练",
    )
    ap.add_argument("--build", type=Path, default=ROOT / "build", help="生成物所在目录")
    ap.add_argument(
        "--mainpage", action="store_true", help="同时以正式页名发布到真首页"
    )
    ns = ap.parse_args()

    sources = {t: ns.build / f for t, f in GENERATED.items()}
    sources |= {t: TEMPLATES / f for t, f in PAGES.items()}
    if missing := [str(f) for f in sources.values() if not f.is_file()]:
        raise SystemExit(
            "缺这些文件，先跑 build_mainpage_sandbox.py：\n  " + "\n  ".join(missing)
        )

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    settings = get_settings()
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run
    ) as wiki:
        username, password = settings.require_credentials()
        await wiki.login(username, password)

        # 模板先到位，页面最后写：页面保存时就能渲染出完整内容
        order = [t for t in sources if t != "首页/sandbox"]
        for title in order:
            await put(
                wiki, title, sources[title].read_text(encoding="utf-8"), ns.dry_run
            )
        for title, text in CREATE_ONLY.items():
            await put(wiki, title, text, ns.dry_run, create_only=True)
        await put(
            wiki,
            "首页/sandbox",
            sources["首页/sandbox"].read_text(encoding="utf-8"),
            ns.dry_run,
        )

        if ns.mainpage:
            # 要发正式版的 /sandbox 页：微件两边共用，首页/sandbox 本身对应的是 首页
            staged = [
                t for t in sources if t not in ("微件:Mpstyle/newskin", "首页/sandbox")
            ]
            await publish_mainpage(wiki, sources, staged, ns.dry_run)
        else:
            await migrate_data(wiki, ns.dry_run)
        await wiki.purge(["首页/sandbox"])


if __name__ == "__main__":
    asyncio.run(main())
