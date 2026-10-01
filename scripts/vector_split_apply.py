"""把 MediaWiki:Vector.css 里的正文样式分流到 Common.css / TemplateStyles / Arknights.css。

依据 docs/Vector.css分流清单.md。每一步都是幂等的：已经包含目标片段就跳过。

    uv run python scripts/vector_split_apply.py --dry-run          # 只打印 diff
    uv run python scripts/vector_split_apply.py --only pathnav2    # 只跑某一步
    uv run python scripts/vector_split_apply.py -c config.sandbox.toml  # 先在沙箱演练
    uv run python scripts/vector_split_apply.py                    # 全部落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config  # noqa: E402
from wikibot.wiki import Wiki  # noqa: E402

DOC = "prts-skin-migration/docs/Vector.css分流清单.md"
SUMMARY = "Vector.css 正文样式分流（{}）。见 " + DOC

# --------------------------------------------------------------------------- 工具


class Ctx:
    def __init__(self, wiki: Wiki, dry_run: bool) -> None:
        self.wiki = wiki
        self.dry_run = dry_run
        self.vector_css: list[str] | None = None

    async def vector_lines(self) -> list[str]:
        """线上 Vector.css 按行（1-based 用 lines[n-1]）。"""
        if self.vector_css is None:
            page = await self.wiki.read("MediaWiki:Vector.css")
            self.vector_css = page.content.split("\n")
        return self.vector_css

    async def vslice(self, start: int, end: int) -> str:
        """Vector.css 第 start..end 行（含两端，1-based）。"""
        lines = await self.vector_lines()
        return "\n".join(lines[start - 1 : end])

    async def edit(
        self,
        title: str,
        transform,
        what: str,
        *,
        create: bool = False,
    ) -> None:
        page = await self.wiki.read(title)
        if page.missing and not create:
            raise SystemExit(f"{title} 不存在")
        old = "" if page.missing else page.content
        new = transform(old)
        if new is None:
            print(f"  = {title}: 已是目标状态，跳过")
            return
        if new == old:
            print(f"  = {title}: 无变化，跳过")
            return
        diff = difflib.unified_diff(
            old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=2
        )
        print("\n".join(diff))
        if self.dry_run:
            print(f"  [dry-run] {title}")
            return
        await self.wiki.edit(
            title,
            new,
            SUMMARY.format(what),
            baserevid=None if page.missing else page.revid,
            nocreate=not create,
        )
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


def replace_once(text: str, old: str, new: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"期望片段出现 1 次，实际 {n} 次：\n{old[:200]}")
    return text.replace(old, new)


def prepend_if_missing(marker: str, block: str):
    def tf(text: str):
        if marker in text:
            return None
        return block.rstrip("\n") + "\n\n" + text

    return tf


def append_if_missing(marker: str, block: str):
    def tf(text: str):
        if marker in text:
            return None
        return text.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"

    return tf


def create_with(block: str):
    def tf(text: str):
        if text.strip():
            return None if block.strip() in text else text
        return block.rstrip("\n") + "\n"

    return tf


# --------------------------------------------------------------------------- 各步骤


async def step_pathnav2(c: Ctx) -> None:
    block = """/* 基础态：蓝底上的链接用白字（自 MediaWiki:Vector.css 1256–1264 行分流） */
.pathnav2-center a,
.pathnav2-center a:visited {
  color: #fff;
}

.pathnav2-center a:hover {
  color: #ddd;
}"""
    await c.edit("模板:Pathnav2/styles.css", prepend_if_missing("基础态：蓝底上的链接用白字", block), "Pathnav2 白字")


NAVBOX_LAYOUT = """/* 布局（自 MediaWiki:Vector.css 1772–1907 行分流；配色交给皮肤 / 模板行内样式） */
.navbox {
  width: 100%;
  margin: auto;
  clear: both;
  text-align: center;
  padding: 1px;
}
.navbox-inner,
.navbox-subgroup {
  width: 100%;
}
.navbox th,
.navbox-title,
.navbox-abovebelow {
  text-align: center;
  padding: 1px 1em;
}
th.navbox-group {
  white-space: nowrap;
  text-align: right;
  padding: 1px 1em;
}
/* 模块给每个 navbox-list 画了 2px 左边框（行内 style），Vector 用 #fdfdfd 背景色藏起来；这里直接透明 */
.navbox-list {
  border-color: transparent;
}
table.navbox + table.navbox {
  margin-top: -1px;
}
ol + table.navbox,
ul + table.navbox {
  margin-top: 0.5em;
}
.navbox .hlist td dl,
.navbox .hlist td ol,
.navbox .hlist td ul,
.navbox td.hlist dl,
.navbox td.hlist ol,
.navbox td.hlist ul {
  padding: 0.125em 0;
}
.navbox .hlist dd,
.navbox .hlist dt,
.navbox .hlist li {
  white-space: nowrap;
}
.navbox .hlist dd dl,
.navbox .hlist dt dl,
.navbox .hlist li ol,
.navbox .hlist li ul {
  white-space: normal;
}

/* {{Navbar}} 嵌在 navbox 里 */
.navbar {
  display: inline;
  font-weight: normal;
}
.navbar ul {
  display: inline;
  white-space: nowrap;
}
.navbar li {
  word-spacing: -0.125em;
}
.navbar.mini li abbr[title] {
  font-variant: small-caps;
  border-bottom: none;
  text-decoration: none;
  cursor: inherit;
}
.navbox .navbar {
  display: block;
}
.navbox-title .navbar {
  float: left;
  text-align: left;
  margin-right: 0.5em;
  width: 8em;
}

/* Gadget-collapsibleTables.js 动态插入的 [显示▼]/[隐藏▲] */
.collapseButton {
  float: right;
  font-weight: normal;
  margin-left: 0.5em;
  text-align: right;
  width: auto;
}
.navbox .collapseButton {
  width: 8em;
}"""


async def step_navbox(c: Ctx) -> None:
    await c.edit("模板:Navbox/styles.css", prepend_if_missing(".navbox-inner,", NAVBOX_LAYOUT), "Navbox 布局")

    def tf_module(text: str):
        if "Navbox/styles.css" in text:
            return None
        pat = re.compile(r"    renderTrackingCategories\(res\)\n[ \t]*\n    return tostring\(res\)\nend")
        if len(pat.findall(text)) != 1:
            raise SystemExit("模块:Navbox 尾部锚点不唯一")
        new = """    renderTrackingCategories(res)

    -- 子表（subgroup / child）嵌在父 navbox 里，样式由父级带；顶层输出一次 TemplateStyles
    local styles = ''
    if border ~= 'subgroup' and border ~= 'child' then
        styles = mw.getCurrentFrame():extensionTag{ name = 'templatestyles', args = { src = 'Navbox/styles.css' } }
    end
    return styles .. tostring(res)
end"""
        return pat.sub(lambda _: new, text)

    await c.edit("模块:Navbox", tf_module, "Navbox 模块输出 TemplateStyles")

    def tf_v2(text: str):
        if "Navbox/styles.css" in text:
            return None
        old = """    debugLog('rootnode build done, Navbox end')
    return tostring(rootNode:allDone())
end"""
        new = """    debugLog('rootnode build done, Navbox end')
    local styles = frame:extensionTag{ name = 'templatestyles', args = { src = 'Navbox/styles.css' } }
    return styles .. tostring(rootNode:allDone())
end"""
        return replace_once(text, old, new)

    await c.edit("模块:NavboxV2", tf_v2, "NavboxV2 模块输出 TemplateStyles")


async def step_navbox_parity(c: Ctx) -> None:
    """对已写入第一版布局的 Navbox/styles.css 补齐：th 内边距对齐 Vector、藏掉 navbox-list 左边框。"""

    def tf(text: str):
        if "border-color: transparent" in text:
            return None
        return replace_once(text, """.navbox th,
.navbox-title,
.navbox-abovebelow {
  text-align: center;
  padding-left: 1em;
  padding-right: 1em;
}
th.navbox-group {
  white-space: nowrap;
  text-align: right;
}""", """.navbox th,
.navbox-title,
.navbox-abovebelow {
  text-align: center;
  padding: 1px 1em;
}
th.navbox-group {
  white-space: nowrap;
  text-align: right;
  padding: 1px 1em;
}
/* 模块给每个 navbox-list 画了 2px 左边框（行内 style），Vector 用 #fdfdfd 背景色藏起来；这里直接透明 */
.navbox-list {
  border-color: transparent;
}""")

    await c.edit("模板:Navbox/styles.css", tf, "Navbox 对齐 Vector：th 内边距、藏 navbox-list 左边框")


async def step_common_css(c: Ctx) -> None:
    parts = [
        "/***** 以下自 MediaWiki:Vector.css 分流：皮肤无关的正文样式。见 " + DOC + " *****/",
        "/* ULS 语言列表裁剪（原 244–289 行） */",
        await c.vslice(244, 289),
        "/* 水印表格（原 348–358 行） */",
        await c.vslice(348, 358),
        "/* 结构式讨论话题页面隐藏评论（原 568–574 行） */",
        await c.vslice(568, 574),
        "/* plainlist（原 585–597 行） */",
        await c.vslice(585, 597),
        "/* 黑幕反白 .spoiler：蚀刻章展示 / 防剧透 / MedalShowcase 共用（原 1231–1240 行） */",
        await c.vslice(1231, 1240),
        "/* tl-idnav：Pathnav2/core、Navigator/* 共用（原 1266–1274 行） */",
        await c.vslice(1266, 1274),
        "/* LST section 标签兜底（原 1573–1576 行） */",
        await c.vslice(1573, 1576),
        "/* nowrap / nowraplinks：模块:Navbox 输出（原 1643–1673 行） */",
        await c.vslice(1643, 1673),
        "/* hlist / hnum 横排列表：模块:Navbox 与各导航模板（原 1675–1755 行） */",
        (await c.vslice(1675, 1755)).replace(
            ".skin-monobook .hlist dl,\n.skin-modern .hlist dl,\n.skin-vector .hlist dl {", ".hlist dl {"
        ),
        "/* .noedit：模块:Navbar 输出（原 1908–1912 行） */",
        await c.vslice(1908, 1912),
        "/* 懒加载渐入：Crisis v2、Collapsible-block/lazyload 等微件（原 1914–1922 行） */",
        await c.vslice(1914, 1922),
        "/* 深色折叠表补充（原 1945–1953 行），与上方 .mw-collapsible-dark 变量块配套 */",
        await c.vslice(1945, 1953),
        "/* 反馈板 Flow 下拉刷新图标（原 1955–1959 行） */",
        await c.vslice(1955, 1959),
    ]
    block = "\n\n".join(parts)
    await c.edit("MediaWiki:Common.css", append_if_missing("以下自 MediaWiki:Vector.css 分流", block), "Common.css 接收正文样式")


async def step_heimu_fuzzy(c: Ctx) -> None:
    heimu = "/* 黑幕基础态（自 MediaWiki:Vector.css 599–641 行分流）。切换态 body.heimu_toggle_on 在 Gadget-heimu-toggle.css */\n" + await c.vslice(599, 641)
    await c.edit("模板:黑幕/styles.css", create_with(heimu), "黑幕 TemplateStyles", create=True)
    await c.edit(
        "模板:黑幕",
        lambda t: None if "templatestyles" in t else replace_once(t, '<includeonly><span title=', '<includeonly><templatestyles src="黑幕/styles.css" /><span title='),
        "黑幕挂 TemplateStyles",
    )
    fuzzy = "/* 模糊（自 MediaWiki:Vector.css 336–346 行分流） */\n" + await c.vslice(337, 346)
    await c.edit("模板:模糊/styles.css", create_with(fuzzy), "模糊 TemplateStyles", create=True)
    await c.edit(
        "模板:模糊",
        lambda t: None if "templatestyles" in t else replace_once(t, '<includeonly><span title=', '<includeonly><templatestyles src="模糊/styles.css" /><span title='),
        "模糊挂 TemplateStyles",
    )


async def step_gadgets(c: Ctx) -> None:
    edittools = "/* Edittools / CharInsert 编辑框按钮（自 MediaWiki:Vector.css 295–335 行分流） */\n" + await c.vslice(295, 335)
    await c.edit("MediaWiki:Gadget-Edittools.css", create_with(edittools), "Edittools 样式", create=True)
    filterable = "/* Filterable 筛选工具（自 MediaWiki:Vector.css 368–496 行分流） */\n" + await c.vslice(368, 496)
    await c.edit("MediaWiki:Gadget-Filterable.css", create_with(filterable), "Filterable 样式", create=True)

    def tf(text: str):
        if "Filterable.css" in text and "Edittools.css" in text:
            return None
        text = replace_once(
            text,
            "* Filterable[ResourceLoader|type=general|default|hidden]|Filterable.js\n",
            "* Filterable[ResourceLoader|type=general|default|hidden]|Filterable.js|Filterable.css\n",
        )
        text = replace_once(
            text,
            "* Edittools[ResourceLoader|default]|Edittools.js\n",
            "* Edittools[ResourceLoader|default]|Edittools.js|Edittools.css\n",
        )
        return text

    await c.edit("MediaWiki:Gadgets-definition", tf, "Edittools / Filterable 挂 CSS")


async def step_misc_templatestyles(c: Ctx) -> None:
    # TemplateStyles 不认 -webkit- 前缀属性，只留标准 mask-image
    semi = "/* 半折叠（自 MediaWiki:Vector.css 521–551 行分流） */\n" + "\n".join(
        ln for ln in (await c.vslice(522, 551)).split("\n") if not ln.strip().startswith("-webkit-mask-image")
    )
    await c.edit("模板:半折叠/styles.css", create_with(semi), "半折叠 TemplateStyles", create=True)
    await c.edit(
        "模板:半折叠/before",
        lambda t: None if "templatestyles" in t else '<templatestyles src="半折叠/styles.css" />' + t,
        "半折叠挂 TemplateStyles",
    )

    autonarrow = "/* cbox2 自动宽度（自 MediaWiki:Vector.css 1566–1571 行分流） */\n" + await c.vslice(1567, 1571)
    await c.edit("模板:Cbox2/styles.css", append_if_missing("cbox-autonarrow", autonarrow), "Cbox2 autonarrow")

    reflist = """/* Reflist（自 MediaWiki:Vector.css 1586–1604 行分流）。ol.references 本身的字号与 :target 高亮由皮肤负责 */
div.reflist {
  margin-bottom: 0.5em;
}

div.reflist ol.references {
  font-size: 100%;
}

div.reflist ol.references,
div.notelist ol.references {
  list-style-type: inherit;
}"""
    await c.edit("模板:Reflist/styles.css", create_with(reflist), "Reflist TemplateStyles", create=True)
    await c.edit(
        "模板:Reflist",
        lambda t: None if "templatestyles" in t else replace_once(t, '<div class="reflist <!--', '<templatestyles src="Reflist/styles.css" /><div class="reflist <!--'),
        "Reflist 挂 TemplateStyles",
    )


async def step_arknights_css(c: Ctx) -> None:
    block = (
        "/* 这里放置的 CSS 只影响 Arknights 皮肤。皮肤级样式优先改 mediawiki-skins-Arknights；\n"
        "   这里只放站内约定类的兜底。见 " + DOC + " */\n\n"
        "/* 折叠表格：toggle 绝对定位到表头右侧，不挤占标题文字（原 Vector.css 1357–1376 行） */\n"
        + await c.vslice(1358, 1376)
        + "\n\n/* navbox 兜底宽度：TemplateStyles 未生效的场合（微件直出）也不塌 */\n"
        ".mw-parser-output .navbox {\n  width: 100%;\n}\n\n"
        ".mw-parser-output .navbox-inner,\n.mw-parser-output .navbox-subgroup {\n  width: 100%;\n}"
    )
    await c.edit("MediaWiki:Arknights.css", create_with(block), "Arknights.css 折叠表 / navbox 兜底", create=True)


RIGHT_TOC_START = "//右侧目录\n"
BACK_TOP_START = "/* 回到顶部 */\n"


async def step_js(c: Ctx) -> None:
    common = await c.wiki.read("MediaWiki:Common.js")
    text = common.content
    if RIGHT_TOC_START not in text:
        print("  = Common.js: 已无 rightToc / backToTop，跳过")
        return
    a = text.index(RIGHT_TOC_START)
    b = text.index("//黑幕")
    right_toc = text[a:b]
    a2 = text.index(BACK_TOP_START)
    b2 = text.index("// 百度推送")
    back_top = text[a2:b2]
    moved = right_toc.rstrip("\n") + "\n\n" + back_top.rstrip("\n") + "\n"

    def tf_vector(t: str):
        if "rightToc" in t:
            return None
        return t.rstrip("\n") + "\n\n/* 以下两段自 Common.js 挪来：只在 Vector 下有对应样式（Vector.css 67–122、1189–1210 行），随 Vector 退役 */\n" + moved

    await c.edit("MediaWiki:Vector.js", tf_vector, "接收 rightToc / backToTop")

    def tf_common(t: str):
        if RIGHT_TOC_START not in t:
            return None
        t = t.replace(right_toc, "")
        t = t.replace(back_top, "")
        return t

    await c.edit("MediaWiki:Common.js", tf_common, "rightToc / backToTop 挪到 Vector.js")


async def step_cleanup(c: Ctx) -> None:
    await c.edit(
        "PRTS:版权",
        lambda t: None if "{{ombox" not in t else t.replace("{{ombox|image=none|text=", "{{cbox2|text="),
        "ombox → cbox2",
    )
    for t in ("模板:Ombox/core", "模板:Ombox"):
        await c.delete(t, "全站无调用（唯一调用方 PRTS:版权 已改用 cbox2），mbox 样式随 Vector.css 分流作废。见 " + DOC)
    for t in ("MediaWiki:PopupNotice/source", "MediaWiki:PopupNotice"):
        await c.delete(t, "全站无引用、无加载脚本，已停用。见 " + DOC)


# Vector.css 里删除的段：只删「死 CSS」（A 类，全站无 DOM）和随页面删除失效的段。
# B（Vector chrome）、C（皮肤已接管）以及已分流出去的段保留在 Vector 作用域里，随 Vector 退役。
DEAD_RANGES = [
    (508, 520, ".custom-img-comment"),
    (643, 1112, "mbox 全家 + #siteNotice/#wpSummary"),
    (1113, 1145, ".nonumtoc / .toclimit"),
    (1146, 1183, ".copyvio"),
    (1225, 1230, ".centertable"),
    (1251, 1255, ".vega"),
    (1276, 1282, ".tl-splink"),
    (1378, 1430, ".tbui-paginator"),
    (1431, 1468, ".tbui-popupdialog（PopupNotice 已删）"),
    (1469, 1509, "注释掉的热门评论 / 圣诞帽"),
    (1510, 1565, ".infobox"),
    (1605, 1635, ".references-2column / div.columns"),
    (1767, 1771, ".same-bg"),
    (1924, 1929, ".spine-background"),
]


async def step_vector_css(c: Ctx) -> None:
    lines = await c.vector_lines()

    def tf(text: str):
        if text.split("\n") != lines:
            raise SystemExit("Vector.css 在本次运行期间被改过，中止")
        keep = [True] * len(lines)
        for start, end, _ in DEAD_RANGES:
            for i in range(start - 1, end):
                keep[i] = False
        out = [ln for ln, k in zip(lines, keep, strict=True) if k]
        return "\n".join(out)

    print("  将删除的段：")
    for start, end, what in DEAD_RANGES:
        first = lines[start - 1].strip()[:60]
        last = lines[end - 1].strip()[:60]
        print(f"    {start:>4}–{end:<4} {what:40} | {first!r} … {last!r}")
    await c.edit("MediaWiki:Vector.css", tf, "删除全站无 DOM 的死 CSS")


STEPS = {
    "pathnav2": step_pathnav2,
    "navbox": step_navbox,
    "navbox_parity": step_navbox_parity,
    "common_css": step_common_css,
    "heimu_fuzzy": step_heimu_fuzzy,
    "gadgets": step_gadgets,
    "misc_templatestyles": step_misc_templatestyles,
    "arknights_css": step_arknights_css,
    "js": step_js,
    "cleanup": step_cleanup,
    "vector_css": step_vector_css,
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
        # 校验线上 Vector.css 与盘点时的版本一致（行号才有意义）
        lines = await c.vector_lines()
        anchors = {1256: "/** pathnav2 **/", 1773: "/* Default style for navigation boxes from Wikipedia*/", 1357: "/* 折叠表格的定位处理 */"}
        needs_lines = {"common_css", "heimu_fuzzy", "gadgets", "misc_templatestyles", "arknights_css", "vector_css"}
        selected = ns.only or list(STEPS)
        for n, s in anchors.items():
            if n > len(lines) or lines[n - 1].strip() != s:
                msg = f"Vector.css 第 {n} 行不是 {s!r}：行号已漂移（vector_css 步骤跑过之后属正常）"
                if set(selected) & needs_lines:
                    raise SystemExit(msg + "，依赖行号的步骤不能再跑")
                print("  ! " + msg)
                break
        for name in selected:
            print(f"\n=== {name}")
            await STEPS[name](c)


if __name__ == "__main__":
    asyncio.run(main())
