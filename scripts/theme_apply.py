"""按 docs/主题适配盘点.md 落地颜色适配（浅色 / 暗色 / 自动偏好）。

每一步都幂等：CSS 写在带标记的区块里，重跑只替换区块；
os 分支由 wikibot/theme_os.py 从 night 规则机械生成。
CSS 片段放在 scripts/theme_css/，每个文件对应一个目标页。

各步骤先登记改动，再按页面合并执行：一页只写一次，
``--only`` 选中的页面总是套上它在所有步骤里的改动。

    # 沙箱预演 / 落地
    uv run python scripts/theme_apply.py -c config.sandbox.toml --from-live --dry-run
    uv run python scripts/theme_apply.py -c config.sandbox.toml --from-live
    # 线上预演 / 落地
    uv run python scripts/theme_apply.py --only common_css --dry-run
    uv run python scripts/theme_apply.py --only common_css

``--from-live`` 以线上当前正文为底生成，再写进目标站点：沙箱库比线上旧，
这样沙箱验证的就是线上将要得到的结果。对线上站点使用会直接报错退出。
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.theme_os import (
    add_os_branch_to_page,
    strip_generated,
    style_spans,
)
from wikibot.theme_page import derive, mark_dark_tables
from wikibot.wiki import Wiki

DOC = "prts-skin-migration/docs/主题适配盘点.md"
SUMMARY = "主题适配（{}）。见 " + DOC
LIVE_API = "https://prts.wiki/api.php"
CSS_DIR = Path(__file__).with_name("theme_css")

Transform = Callable[[str], str | None]

# --------------------------------------------------------------------------- 工具


@dataclass
class PlannedEdit:
    step: str
    transform: Transform
    what: str
    create: bool


class Ctx:
    """各步骤只登记改动（``edit``），``flush`` 时按页面合并执行。

    同一页可能被几步改到（如 集成战略导航 在 common_css 和 navbox 里各有一处）。
    合并后每页只读一次、按步骤顺序套上它的全部改动、只写一次；``--only`` 只决定
    处理哪些页面，处理到的页面总是套上全部改动，所以结果不取决于单独跑了哪一步
    （``--from-live`` 每次都以线上正文为底，不合并会互相覆盖）。
    """

    def __init__(
        self,
        wiki: Wiki,
        live: Wiki | None,
        dry_run: bool,
        show_diff: bool,
        dump: Path | None = None,
    ) -> None:
        self.wiki = wiki
        self.live = live
        self.dry_run = dry_run
        self.show_diff = show_diff
        self.dump = dump
        self.step = ""
        self.plan: dict[str, list[PlannedEdit]] = {}
        self.written: list[str] = []
        self.skipped: list[str] = []

    async def edit(
        self, title: str, transform: Transform, what: str, *, create: bool = False
    ) -> None:
        """登记一处改动。transform 返回 None 表示不用改（仍会补 os 分支）。"""
        self.plan.setdefault(title, []).append(
            PlannedEdit(self.step, transform, what, create)
        )

    async def flush(self, steps: set[str]) -> None:
        for title, edits in self.plan.items():
            if any(e.step in steps for e in edits):
                await self._apply(title, edits)

    async def _apply(self, title: str, edits: list[PlannedEdit]) -> None:
        """读目标页 → 各 transform → 补 os 分支 → 写回。

        ``--from-live`` 时以线上正文为底。
        """
        create = any(e.create for e in edits)
        page = await self.wiki.read(title)
        base_page = page
        if self.live is not None:
            base_page = await self.live.read(title)
            if base_page.missing and not page.missing:
                base_page = page
        if page.missing and not create:
            print(f"  ! {title}: 目标站点没有这一页，跳过")
            self.skipped.append(title)
            return
        base = "" if base_page.missing else base_page.content
        new = base
        for planned in edits:
            result = planned.transform(new)
            if result is not None:
                new = result
        new, _ = add_os_branch_to_page(title, new, base_page.content_model)
        what = "；".join(dict.fromkeys(e.what for e in edits))
        old = "" if page.missing else page.content
        if new.rstrip() == old.rstrip():  # MediaWiki 保存时会去掉结尾空白
            print(f"  = {title}: 已是目标状态")
            return
        if self.dump is not None:
            self.dump.mkdir(parents=True, exist_ok=True)
            (self.dump / (title.replace("/", "__") + ".wiki")).write_text(
                new, encoding="utf-8"
            )
        if self.show_diff:
            # 只看本次改动：底稿（--from-live 时是线上正文）→ 新正文
            diff = difflib.unified_diff(
                base.split("\n"),
                new.split("\n"),
                f"{title} ({'live' if self.live else 'old'})",
                f"{title} (new)",
                lineterm="",
                n=2,
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
        self.written.append(title)
        print(f"  ✔ {title}")


def snippet(name: str) -> str:
    return (CSS_DIR / name).read_text(encoding="utf-8").strip("\n")


def _block_re(name: str) -> re.Pattern[str]:
    return re.compile(
        r"/\* theme:begin "
        + re.escape(name)
        + r"\b.*?/\* theme:end "
        + re.escape(name)
        + r" \*/",
        re.DOTALL,
    )


def upsert_block(text: str, name: str, body: str, note: str) -> str:
    """把 ``body`` 放进 ``theme:begin/end name`` 区块。

    已有则只替换两个标记之间的内容（两侧空白不动，重跑不会产生空白差异）；
    没有就追加到末尾（先剥掉 theme-os 区块，它总是由生成器重新放到最后）。
    """
    block = f"/* theme:begin {name} {note} */\n{body.strip()}\n/* theme:end {name} */"
    pattern = _block_re(name)
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    text = strip_generated(text)
    if not text.strip():
        return block + "\n"
    return text.rstrip("\n") + "\n\n" + block + "\n"


def with_block(name: str, css_file: str, note: str) -> Transform:
    body = snippet(css_file)
    return lambda text: upsert_block(text, name, body, note)


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"期望片段出现 1 次，实际 {count} 次：\n{old[:200]}")
    return text.replace(old, new)


def replace_n(text: str, old: str, new: str, expected: int) -> str:
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"期望片段出现 {expected} 次，实际 {count} 次：\n{old[:200]}")
    return text.replace(old, new)


def sub(old: str, new: str, expected: int = 1) -> Transform:
    """幂等替换：已经是 new 就不动，否则要求 old 恰好出现 expected 次。"""

    def run(text: str) -> str | None:
        if old not in text and new in text:
            return None
        return replace_n(text, old, new, expected)

    return run


def chain(*transforms: Transform) -> Transform:
    def run(text: str) -> str:
        for transform in transforms:
            result = transform(text)
            if result is not None:
                text = result
        return text

    return run


# --------------------------------------------------------------------------- 各步骤

STEPS: dict[str, Callable[[Ctx], Awaitable[None]]] = {}


def step(name: str):
    def register(func: Callable[[Ctx], Awaitable[None]]):
        STEPS[name] = func
        return func

    return register


NOTE = "主题适配，见 " + DOC


PAGE_TEXT_AS_BACKGROUND = [
    "模板:集成战略导航",
    "模板:争锋频道导航",
    "模板:卫戍协议导航",
    "模板:多维合作导航",
    "模板:生息演算导航",
    "模板:分支特性信息表格",
]


@step("common_css")
async def step_common_css(c: Ctx) -> None:
    """§5 / §6：语义变量的暗色值、深色折叠表表头、深色底表格 / 单元格工具类。"""
    # 这几个模板把正文色变量当成深色表头的底色用。变量有了暗色值后它会跟着变浅，
    # 所以先把底色改成固定的 #202122（浅色下值不变），再上 Common.css
    for title in PAGE_TEXT_AS_BACKGROUND:
        await c.edit(
            title,
            sub(
                "background-color:var(--prts-page-text);",
                "background-color:#202122;",
            ),
            "深色表头底色改为固定值（原借用正文色变量，暗色下会变浅）",
        )
    await c.edit(
        "MediaWiki:Common.css",
        with_block("common", "common.css", NOTE),
        "语义变量暗色值、深色折叠表表头、深色底表格工具类",
    )


# 深色卡片表格：整张表深灰底、表头全是深色底，挂 .prts-table-dark 让表头跟随表格的白字
DARK_CARD_TABLES = [
    "模板:收藏品",
    "模板:收藏品/pro",
    "模板:集成战略道具",
    "模板:生息演算道具",
    "模板:生息演算道具/资源",
    "模板:生息演算道具/信物",
]


@step("c_class")
async def step_c_class(c: Ctx) -> None:
    """§5：浅色下深底深字。只写了 --color-base、或深色底表头没写文字色。"""
    for title in DARK_CARD_TABLES:
        await c.edit(
            title,
            sub('class="wikitable logo"', 'class="wikitable logo prts-table-dark"'),
            "深色卡片表格挂 prts-table-dark",
        )
    await c.edit(
        "模板:干员获得方式",
        sub(
            '{|class="wikitable" style="width:40%;',
            '{|class="wikitable prts-table-dark" style="width:40%;',
        ),
        "深色表格挂 prts-table-dark",
    )
    await c.edit(
        "模板:剿灭关卡信息",
        sub(
            '!style="width:10%;background:#2f2f2f;font-size:smaller;"',
            '!style="width:10%;background:#2f2f2f;color:white;font-size:smaller;"',
            expected=2,
        ),
        "深色表头补文字色",
    )
    await c.edit(
        "模板:敌方情报/标题行",
        sub(
            '! id="EnemyCE" colspan=', '! id="EnemyCE" class="prts-cell-dark" colspan='
        ),
        "深色表头挂 prts-cell-dark（折叠按钮跟随白字）",
    )
    await c.edit(
        "模板:剿灭作战进度奖励",
        chain(
            sub(
                '!style="width:200px;color:white;',
                '!class="prts-cell-dark" style="width:200px;color:white;',
            ),
            sub(
                '!style="width:400px;color:white;',
                '!class="prts-cell-dark" style="width:400px;color:white;',
            ),
        ),
        "深色表头挂 prts-cell-dark（折叠按钮跟随白字）",
    )
    await c.edit(
        "模板:测试指标/全息/style",
        chain(
            sub(
                ".group_title {text-align:left !important;"
                "background:#84000f !important;--color-base:#fff;}",
                ".group_title {text-align:left !important;"
                "background:#84000f !important;--color-base:#fff;"
                "color:#fff !important;}",
            ),
            sub(
                ".runetable_title {background:#505050 !important;--color-base:#fff;}",
                ".runetable_title {background:#505050 !important;"
                "--color-base:#fff;color:#fff !important;}",
            ),
        ),
        "深色表头补文字色",
    )
    await c.edit(
        "模板:IngameStory/styles.css",
        with_block("ingame-story-toggle", "ingame_story.css", NOTE),
        "标题栏折叠按钮跟随文字色",
    )


# §3：只写了 night、没有 os 分支（静态扫描，2026-09-29 现网）。按主名字空间引用量排序。
# 不含 Gadget-darkModeFix.css（§8 拆分，不补）
# 和首页的 微件:Mpstyle、微件:Mpstyle/newskin（首页不在本批）。
OS_BRANCH_PAGES = [
    "模板:Cbox2/styles.css",
    "模板:Pathnav2/styles.css",
    "模板:掉落标签/styles.css",
    "模板:敌人信息/common2/styles.css",
    "模板:敌人信息/levelcontent/styles.css",
    "模板:后勤技能/styles.css",
    "模板:模组/styles.css",
    "模板:活动信息/styles.css",
    "模板:修正/styles.css",
    "模板:登场敌人/styles.css",
    "模板:异格干员/styles.css",
    "模板:干员时装/styles.css",
    "模板:简易折叠/styles.css",
    "模板:集成战略选项/styles.css",
    "模板:活动里程碑/styles.css",
    "模板:EnemyDataMini",
    "模板:EnemyDataMini/intex",
    "模板:集成战略档案折叠标题/styles.css",
    "模板:集成战略/诡意行商/styles.css",
    "模板:关卡一览/styles.css",
    "模板:关卡一览/曲谱/styles.css",
    "模板:关卡一览/本章回想/styles.css",
    "模板:关卡一览/主题曲/隐秘战线/styles.css",
    "模板:危机合约作战赛季/styles.css",
    "模板:危机合约/作战赛季/styles.css",
    "模板:卫戍协议/道具/styles.css",
    "模板:通用凭证区/styles.css",
    "模板:公招计算/styles.css",
    "模板:情报处理室/styles.css",
    "模板:音乐鉴赏/styles.css",
    "模板:Node/rebuilding/styles.css",
    "模板:ORACLE DATABASE/index/styles.css",
    "模板:引航者试炼/styles.css",
    "模板:EventShopList/styles.css",
    "模板:PRTS常用代码/styles.css",
    "模板:维护状态标签/styles.css",
    # 活动页专用
    "模板:叙拉古人/待办事项记录/styles.css",
    "模板:叙拉古人/艺术评论/styles.css",
    "模板:喧闹法则/styles.css",
    "模板:沃伦姆德的薄暮/styles.css",
    "模板:理想城长夏狂欢季/styles.css",
    "模板:太阳甩在身后/styles.css",
    "模板:孤星2024/styles.css",
    "模板:尖灭测试作战/styles.css",
    "模板:多索雷斯假日/标志物一览/styles.css",
    "模板:多索雷斯假日/标志物模板/styles.css",
    "模板:好久不见/styles.css",
    "模板:崔林特尔梅之金/PRTS金律记录/styles.css",
    "模板:愚人节活动/2024/styles.css",
    "模板:明日方舟：黎明前奏/styles.css",
    "模板:沙洲遗闻/styles.css",
    "模板:特派信使！使命必达？/styles.css",
    "模板:游城拓荒：铸基者/styles.css",
    "模板:萨卡兹的无终奇语/巫仪档案库/styles.css",
    "模板:长夜临光/信息端口/styles.css",
    # §3.2 微件（样式在 <style> 里）
    "微件:Mailstyle",
    "微件:ShopList",
    "微件:ShopItemListCss",
]


def widget_style(text: str) -> tuple[int, int, int, int]:
    """唯一一段 ``{{#widget:style|style=…}}`` 的 (调用起点, 样式起, 样式止, 调用止)。"""
    spans = [s for s in style_spans(text) if not text[: s[0]].rstrip().endswith(">")]
    if len(spans) != 1:
        raise SystemExit(f"期望 1 段 #widget:style，实际 {len(spans)} 段")
    start, end = spans[0]
    call = text.rfind("{{", 0, start)
    return call, start, end, end + 2


def drop_widget_style(allowed: re.Pattern[str]) -> Transform:
    """整段删掉 #widget:style（连同其后的换行）。

    样式里出现 allowed 之外的类名就报错，防止误删。
    """

    def run(text: str) -> str | None:
        if not _WIDGET_STYLE_RE.search(text):
            return None
        call, start, end, stop = widget_style(text)
        classes = set(re.findall(r"\.([\w-]+)", _css_only(text[start:end])))
        extra = {c for c in classes if not allowed.fullmatch(c)}
        if extra:
            raise SystemExit(
                f"#widget:style 里有通用规则之外的类名，不能整段删：{extra}"
            )
        if text[stop : stop + 1] == "\n":
            stop += 1
        return text[:call] + text[stop:]

    return run


def edit_widget_style(transform: Callable[[str], str]) -> Transform:
    def run(text: str) -> str:
        _, start, end, _ = widget_style(text)
        css = strip_generated(text[start:end])
        new_css = transform(css)
        if css.startswith("\n") and not new_css.startswith("\n"):
            new_css = "\n" + new_css
        if not new_css.endswith("\n"):
            new_css += "\n"
        return text[:start] + new_css + text[end:]

    return run


def edit_style_tag(transform: Callable[[str], str]) -> Transform:
    """微件里唯一一段 ``<style>`` 的正文。"""

    def run(text: str) -> str:
        spans = [s for s in style_spans(text) if text[: s[0]].rstrip().endswith(">")]
        if len(spans) != 1:
            raise SystemExit(f"期望 1 段 <style>，实际 {len(spans)} 段")
        start, end = spans[0]
        new_css = transform(strip_generated(text[start:end]))
        return text[:start] + new_css.rstrip("\n") + "\n" + text[end:]

    return run


_WIDGET_STYLE_RE = re.compile(r"\{\{\s*#widget\s*:\s*style\s*\|", re.IGNORECASE)


def _css_only(css: str) -> str:
    """去掉注释和属性选择器里的字符串，只留选择器 / 声明，用来数类名。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return re.sub(r"\"[^\"]*\"|'[^']*'", "", css)


@step("navbox")
async def step_navbox(c: Ctx) -> None:
    """§7：navbox 保留 Vector 三级蓝，暗色由浅色值推导。

    五个导航模板去掉 Vector 作用域、去重。
    """

    def drop_vector_rules(text: str) -> str | None:
        marker = "\nhtml.skin-theme-clientpref-night body.skin-vector-2022 .navbox"
        if marker not in text:
            return None
        return text[: text.index(marker)].rstrip("\n") + "\n"

    await c.edit(
        "模板:Navbox/styles.css",
        chain(
            drop_vector_rules,
            with_block("navbox-palette", "navbox.css", NOTE),
        ),
        "保留 Vector 三级蓝并覆盖皮肤配色；暗色由浅色值推导，去掉 Vector 作用域",
    )
    # 这三个模板的 #widget:style 只有 navbox 通用规则（分组黑字、--lightblue 上下栏），
    # 已由 Navbox/styles.css 接管
    generic = re.compile(
        r"skin-theme-clientpref-(night|os)|skin-vector-2022|mw-parser-output"
        r"|stage-navbox|enemy-navbox|navbox-group|navbox-abovebelow"
    )
    for title in ("模板:关卡导航", "模板:敌人导航", "模板:地形导航"):
        await c.edit(
            title,
            drop_widget_style(generic),
            "删除限定 Vector 的暗色规则副本（已由 Navbox/styles.css 接管）",
        )
    cc_css = snippet("navbox_cc.css")
    await c.edit(
        "模板:Navbox 危机合约",
        edit_widget_style(lambda _: cc_css),
        "暗色改由浅色值推导，去掉 Vector 作用域；通用部分交给 Navbox/styles.css",
    )
    await c.edit(
        "模板:集成战略导航",
        edit_widget_style(lambda css: css.replace(" body.skin-vector-2022 ", " body ")),
        "暗色规则去掉 Vector 作用域",
    )


EVENT_SHOP_TONES = """
-- 模块自带的档位色才加暗色类（暗色值在 模板:EventShopList/styles.css）。
-- 调用方自定义的颜色、渐变不加：它们的配色由调用方决定，暗色下原样保留。
local toneClassTable = {
	["金"] = "eventshoplist-tone-gold",
	["紫"] = "eventshoplist-tone-purple",
	["蓝"] = "eventshoplist-tone-blue",
	["灰"] = "eventshoplist-tone-gray",
	["复刻"] = "eventshoplist-tone-reprint",
	["彩"] = "eventshoplist-tone-rainbow",
}
"""


def event_shop_tone_classes(text: str) -> str | None:
    """模块:EventShopList：档位行加 eventshoplist-tone-* 类，并输出它的 styles.css。

    2026-06 有过一版同类改动，因为把行内样式改成字符串拼接，调用方数据里给 gsub 写的
    ``10%%`` 不再还原成 ``10%``，渐变失效（沙洲遗闻），于 08-23 被回退。这里行内样式的
    拼法一个字符不动，只把类名并进折叠用的同一个 class 属性。
    """
    if "toneClassTable" in text:
        return None
    text = replace_once(text, "local p = {}\n", "local p = {}\n" + EVENT_SHOP_TONES)
    text = replace_once(
        text,
        '\t\ttable.insert(res_table, checkbox_css .. "\\n")\n\tend\n',
        '\t\ttable.insert(res_table, checkbox_css .. "\\n")\n\tend\n'
        "\ttable.insert(res_table, frame:extensionTag{ name = 'templatestyles', "
        "args = { src = 'EventShopList/styles.css' } } .. \"\\n\")\n",
    )
    text = replace_once(
        text,
        '\t\t\tlocal textColor = mw.text.trim(datum_table[6] or "")\n',
        '\t\t\tlocal textColor = mw.text.trim(datum_table[6] or "")\n'
        "\t\t\tlocal toneClass = toneClassTable[color] "
        'and ("eventshoplist-item " .. toneClassTable[color]) or nil\n',
    )
    # 折叠组那段在「注释」分支里也有一份，连同后面的 table.insert 一起匹配才唯一
    return replace_once(text, _SHOP_ROW_CLASS_OLD, _SHOP_ROW_CLASS_NEW)


_SHOP_ROW_CLASS_OLD = r"""			if cur_collapseGroup then
				local cgstr = ("class=\"mw-collapsible __isC__\" id=\"mw-customcollapsible-eventShopList%s\""):format(cur_collapseGroup)
				cgstr = cgstr:gsub("__isC__", cur_collapseGroupCollapse and "mw-collapsed" or "")
				str = str:gsub("__curColl__", cgstr)
			else
				str = str:gsub("__curColl__", "")
			end
			table.insert(res_table, str)
			--table.insert"""  # noqa: E501
_SHOP_ROW_CLASS_NEW = r"""			if cur_collapseGroup then
				local cgstr = ("class=\"mw-collapsible __isC__%s\" id=\"mw-customcollapsible-eventShopList%s\""):format(toneClass and (" " .. toneClass) or "", cur_collapseGroup)
				cgstr = cgstr:gsub("__isC__", cur_collapseGroupCollapse and "mw-collapsed" or "")
				str = str:gsub("__curColl__", cgstr)
			else
				str = str:gsub("__curColl__", toneClass and ("class=\"" .. toneClass .. "\"") or "")
			end
			table.insert(res_table, str)
			--table.insert"""  # noqa: E501


EVENT_SHOP_FIXED_TEXT = """
-- 调用方给了底色、没给文字色的行：文字固定为深色（浅色主题下原本就是这个颜色）。
-- 底色是固定的，文字跟着明暗主题变浅会看不清（如沙洲遗闻各 STAGE 分组行的浅色渐变）。
-- 只认看起来是 CSS 颜色的值（# 或英文字母开头）；「白」这类颜色表里没有的档位名
-- 输出的是无效的 background，等于没有底色，文字仍跟随主题。
local FIXED_TEXT_COLOR = "#202122"
local function isColor(v)
\treturn v ~= nil and mw.text.trim(v):match("^[#%a]") ~= nil
end
"""

# 21:58 上线过一版用 hasValue 判断（不管值是否有效），把「白」当成了有底色
_EVENT_SHOP_FIXED_TEXT_V1 = """
-- 调用方给了底色、没给文字色的行：文字固定为深色（浅色主题下原本就是这个颜色）。
-- 底色是固定的，文字跟着明暗主题变浅会看不清（如沙洲遗闻各 STAGE 分组行的浅色渐变）。
local FIXED_TEXT_COLOR = "#202122"
local function hasValue(v)
\treturn v ~= nil and mw.text.trim(v) ~= ""
end
"""

_SHOP_TEXT_COLOR = re.compile(
    r'if datum_table\[4\] then (\w+) = \1\.\."color:"\.\.datum_table\[4\]\.\.";" end'
)
_SHOP_ROW_FIXED = (
    '\t\t\tif textColor == "" and isColor(color) and not toneClassTable[color] '
    "then textColor = FIXED_TEXT_COLOR end\n"
)


def event_shop_fixed_text(text: str) -> str | None:
    """模块:EventShopList：有底色没文字色的行，文字固定深色。

    包括分组 / 标题 / 注释 / 商品行。

    商品行的行内样式仍走原来的 gsub 拼法（调用方数据里的 ``%%`` 依赖它），
    只在拼之前给空的 textColor 赋值；档位色行不动，由暗色类负责。
    """
    if "local function isColor" in text:
        return None
    if "local function hasValue" in text:  # 升级 21:58 那一版
        text = replace_once(text, _EVENT_SHOP_FIXED_TEXT_V1, EVENT_SHOP_FIXED_TEXT)
        text = replace_n(
            text,
            "elseif hasValue(datum_table[3]) then",
            "elseif isColor(datum_table[3]) then",
            3,
        )
        return replace_once(
            text,
            '\t\t\tif textColor == "" and color ~= "" and not toneClassTable[color] '
            "then textColor = FIXED_TEXT_COLOR end\n",
            _SHOP_ROW_FIXED,
        )
    text = replace_once(
        text,
        "local toneClassTable = {",
        EVENT_SHOP_FIXED_TEXT + "\nlocal toneClassTable = {",
    )
    if len(_SHOP_TEXT_COLOR.findall(text)) != 3:
        raise SystemExit("模块:EventShopList 的行文字色写法不是预期的 3 处")
    text = _SHOP_TEXT_COLOR.sub(
        lambda m: (
            f'if datum_table[4] then {m[1]} = {m[1]}.."color:"..datum_table[4]..";" '
            f'elseif isColor(datum_table[3]) then {m[1]} = {m[1]}.."color:"'
            '..FIXED_TEXT_COLOR..";" end'
        ),
        text,
    )
    anchor = (
        "\t\t\tlocal toneClass = toneClassTable[color] "
        'and ("eventshoplist-item " .. toneClassTable[color]) or nil\n'
    )
    return replace_once(text, anchor, anchor + _SHOP_ROW_FIXED)


@step("d_class")
async def step_d_class(c: Ctx) -> None:
    """§6：暗色下浅底浅字。

    能换成已有暗色值的语义变量 / 共享类的就换，其余在模板样式里加暗色规则。
    """

    # 数量角标：和 模板:道具图标 用同一个共享类（物品数量角标/styles.css 已有暗色描边）
    def quantity_label(text: str) -> str | None:
        if "prts-item-quantity-label" in text:
            return None
        text = replace_once(
            text,
            '<includeonly><div style="display:inline-block;position:relative">',
            '<includeonly><templatestyles src="物品数量角标/styles.css" />'
            '<div style="display:inline-block;position:relative">',
        )
        pattern = re.compile(
            r'<span style="position:absolute;bottom:-3px;right:2px;white-space:nowrap;'
            r"color:black!important;font-weight:bold;font-size:\{\{\{size2\|10pt\}\}\};"
            r'text-shadow:[^"]*">'
        )
        if len(pattern.findall(text)) != 1:
            raise SystemExit("模板:数量 的角标 span 不是预期的写法")
        return pattern.sub(
            '<span class="prts-item-quantity-label" '
            'style="font-size:{{{size2|10pt}}};">',
            text,
        )

    await c.edit(
        "模板:数量",
        quantity_label,
        "数量角标改用共享类 prts-item-quantity-label（带暗色描边）",
    )
    await c.edit(
        "模板:活动信赖获取提升干员",
        sub(
            'style="background-color:#eaebee;"',
            'style="background-color:var(--prts-muted-section-bg, #eaebee);"',
        ),
        "说明栏底色改用语义变量（带暗色值）",
    )
    await c.edit(
        "模板:危机合约轮换测试地任务",
        sub(
            "background:#eaebee;",
            "background:var(--prts-muted-section-bg, #eaebee);",
            expected=2,
        ),
        "标题栏底色改用语义变量（带暗色值）",
    )
    # 黑字写死在跟随主题的底色上（头像格、半透明属性徽章）
    for title in ("模板:EnemyDataMini/intex",):
        await c.edit(
            title,
            chain(
                sub(
                    "top: 0%;color: #000;",
                    "top: 0%;color: var(--prts-page-text, #000);",
                ),
                sub(
                    "=#10F6ED55}};color:#000;",
                    "=#10F6ED55}};color:var(--prts-page-text, #000);",
                ),
            ),
            "编号与属性徽章的黑字改用语义变量（带暗色值）",
        )
    # 固定底色上的文字要固定颜色，不能跟随主题
    await c.edit(
        "模板:保全派驻/line2",
        sub(
            'style{{=}}"background:#ffe037;"',
            'style{{=}}"background:#ffe037;color:#202122;"',
        ),
        "黄底表头补深色文字",
    )
    await c.edit(
        "模板:保全派驻信息/Ver2",
        sub(
            "background: #ffe037;top: 50%;",
            "background: #ffe037;color:#202122;top: 50%;",
        ),
        "黄底角标补深色文字",
    )
    await c.edit(
        "模板:记录修复奖励/styles.css",
        with_block("record-restore", "record_restore.css", NOTE),
        "表头文字色固定为深字，不跟随明暗主题",
        create=True,
    )
    await c.edit(
        "模板:记录修复奖励",
        sub(
            '!colspan=6 {{#if:{{{反色|}}}|class="revertrec"}} '
            'style="background:#{{{主题色|8fc5b7}}};"| [[文件:图标 记录修复.png',
            '!colspan=6 class="record-restore-title {{#if:{{{反色|}}}|revertrec}}" '
            'style="background:#{{{主题色|8fc5b7}}};"| '
            '<templatestyles src="记录修复奖励/styles.css" />[[文件:图标 记录修复.png',
        ),
        "表头文字色不再跟随主题（底色由主题色参数决定）",
    )
    await c.edit(
        "模板:修正/styles.css",
        with_block("fix-mark", "fix_mark.css", NOTE),
        "高亮固定深色文字",
    )
    await c.edit(
        "模板:争锋频道基础样式",
        edit_widget_style(
            lambda css: upsert_block(
                css, "ggg-channel", snippet("ggg_channel.css"), NOTE
            )
        ),
        "频道表头黄底补暗色",
    )
    await c.edit(
        "微件:DeviceOverview",
        edit_style_tag(
            lambda css: upsert_block(
                css, "device-overview", snippet("device_overview.css"), NOTE
            )
        ),
        "补暗色",
    )
    await c.edit(
        "模板:保全派驻",
        sub(
            "!colspan=5 "
            'style="text-align:center;background-color:#bdbdbd;color:#424242;"|',
            '!colspan=5 class="prts-cell-dark" '
            'style="text-align:center;background-color:#bdbdbd;color:#424242;"|',
        ),
        "固定底色表头挂 prts-cell-dark（折叠按钮跟随表头文字色）",
    )
    await c.edit(
        "模板:模组/卫戍协议",
        sub(
            "max-width:800px;background-color:#f8f9fa;",
            "max-width:800px;background-color:var(--prts-page-subtle-bg, #f8f9fa);",
        ),
        "卡片底色改用语义变量（带暗色值）",
    )
    await c.edit(
        "模板:模组/一览/style",
        chain(
            sub(
                "max-width:800px;background-color:#f8f9fa;",
                "max-width:800px;background-color:var(--prts-page-subtle-bg, #f8f9fa);",
            ),
            sub(
                ".majorsep {height:1px;background-color:black;}",
                ".majorsep {height:1px;background-color:var(--prts-page-text, black);}",
            ),
        ),
        "卡片底色、分隔线改用语义变量（带暗色值）",
    )
    await c.edit(
        "模块:EventShopList",
        chain(event_shop_tone_classes, event_shop_fixed_text),
        "模块自带的档位色加暗色类并输出 EventShopList/styles.css（行内样式的拼法不变，"
        "自定义颜色 / 渐变不加类）；有底色没文字色的行文字固定深色",
    )
    await c.edit(
        "模板:EventShopList/styles.css",
        with_block("eventshoplist-align", "eventshoplist.css", NOTE),
        "图标与文字垂直居中",
    )
    await c.edit(
        "模块:EnemyStageAppearance",
        sub(
            'style="color:#36c;cursor:pointer;"',
            'style="color:var(--color-progressive, #36c);cursor:pointer;"',
            expected=2,
        ),
        "展开 / 折叠按钮改用链接色变量（随主题变化，与核心折叠按钮一致）",
    )
    await c.edit(
        "微件:ListOrderToggle",
        sub(
            "background:transparent;color:#202122;padding:0;",
            "background:transparent;color:var(--prts-page-text,#202122);padding:0;",
        ),
        "文字色改用语义变量（带暗色值）",
    )
    await c.edit(
        "微件:SectionTabs.css",
        chain(
            # 解析器会把前几个按钮包进 <p>、最后一个留在外面，浮动因此错位；
            # 改成 flex 并让 <p> 不生成盒子，按钮就都是同一行的弹性项
            sub(
                ".section_tab {\n  overflow: hidden;\n}",
                ".section_tab {\n"
                "  display: flex;\n"
                "  flex-wrap: wrap;\n"
                "  overflow: hidden;\n"
                "}\n\n"
                ".section_tab > p {\n"
                "  display: contents;\n"
                "}",
            ),
            sub(
                "  font-weight: bold;\n  color: #000;",
                "  font-weight: bold;\n  color: var(--prts-page-text, #000);",
            ),
            sub(
                "  background-color: #fff;\n"
                "  border:4px solid #00AEF6;\n"
                "  color: #000;",
                "  background-color: var(--prts-page-card-bg, #fff);\n"
                "  border:4px solid #00AEF6;\n"
                "  color: var(--prts-page-text, #000);",
            ),
        ),
        "标签文字色、选中标签底色改用语义变量（带暗色值）；"
        "标签栏改 flex，修按钮上下错位",
    )


PARSER_OUTPUT_OPEN = (
    "<!-- TemplateStyles 只作用于 .mw-parser-output 之内，系统消息默认不带这层，"
    "所以包一层（主题适配，2026-09-29） -->"
    '<div class="mw-parser-output">'
)


def wrap_parser_output(text: str) -> str | None:
    if PARSER_OUTPUT_OPEN in text:
        return None
    return PARSER_OUTPUT_OPEN + text.rstrip("\n") + "</div>"


@step("dark_mode_fix")
async def step_dark_mode_fix(c: Ctx) -> None:
    """§8：Gadget-darkModeFix.css 拆分。

    模板专属的部分进模板自己的样式；行内颜色匹配改在模板源头。
    本章回想 / 简易折叠 / 集成战略档案折叠标题 三个类各自的 styles.css 里
    已有等价 night 规则，os 分支在 os_branch 一步补齐，不用搬。
    """
    await c.edit(
        "模板:Documentation/styles.css",
        with_block("documentation", "documentation.css", NOTE),
        "文档框样式从行内移到 TemplateStyles，补暗色",
        create=True,
    )
    await c.edit(
        "模板:Documentation",
        chain(
            sub(
                '<div class="template-documentation" '
                'style="background: aliceblue; padding: 1em; border: 1px solid #eee;">',
                '<templatestyles src="Documentation/styles.css" />'
                '<div class="template-documentation">',
            ),
            sub(
                'style="padding-bottom:3px; border-bottom: 1px solid #eee; '
                'margin-bottom:1ex"',
                'style="padding-bottom:3px; margin-bottom:1ex"',
            ),
        ),
        "文档框样式移到 Documentation/styles.css（带暗色）",
    )
    # 编辑页顶部的系统消息里用了 {{cbox2}}。系统消息解析出来不包 .mw-parser-output，
    # 而 TemplateStyles 给每条规则都加了这个前缀，
    # Cbox2 的暗色规则（以及 cbox-autonarrow）在编辑页上匹配不到
    for title in (
        "MediaWiki:Editpage-head-copy-warn",
        "MediaWiki:Editpage-head-copy-warn/zh",
    ):
        await c.edit(
            title,
            wrap_parser_output,
            "内容包进 .mw-parser-output，"
            "让 Cbox2 的 TemplateStyles（含暗色）在编辑页生效",
        )
    # 行内红字：{{color|red}} 等是模板里最常见的写法（23 个模板），
    # 在 模板:Color 源头换成语义变量；
    # 变量缺省时回退到原色，Common.css 不加载的场合（如 Minerva）外观不变。
    # `color:` 必须写在 #switch 的每个分支里面：解析器函数的输出以 # 开头时，
    # 解析器会在前面补一个换行（防止被当成列表项），<poem> 又把换行换成 <br />，
    # 09-29 那版（color: 在 #switch 外面）在 {{#tag:poem|…}} 里输出
    # style="color:<br /> #FF4F0B;"，颜色失效。
    # 黑字（10-01 加）：暗色下深底黑字，改跟正文色 --prts-page-text（浅色 #202122）。
    # 悖论模拟描述里的关卡效果行（165 页）、navbox 分组名、集成战略条目都是这种写法。
    # 分析与考据/角色导航 手机版表头写的 background: var(--,#EBF7FE) 是无效声明
    # （-- 不是合法变量名，浏览器整条丢掉），表头本来就是皮肤底色，黑字跟随正文色正好
    color_fixed = (
        '<span style="{{#switch:{{lc:{{{1}}}}}'
        "|red|#f00|#ff0000=color:var(--prts-alert-text, {{{1}}})"
        "|#c0392b=color:var(--prts-red-text, {{{1}}})"
        "|black|#000|#000000=color:var(--prts-page-text, {{{1}}})"
        '|#default=color:{{{1}}}}};">'
    )
    color_0929 = (
        '<span style="color:{{#switch:{{lc:{{{1}}}}}'
        "|red|#f00|#ff0000=var(--prts-alert-text, {{{1}}})"
        "|#c0392b=var(--prts-red-text, {{{1}}})"
        '|#default={{{1}}}}};">'
    )
    color_0930 = (
        '<span style="{{#switch:{{lc:{{{1}}}}}'
        "|red|#f00|#ff0000=color:var(--prts-alert-text, {{{1}}})"
        "|#c0392b=color:var(--prts-red-text, {{{1}}})"
        '|#default=color:{{{1}}}}};">'
    )

    def color_semantic(text: str) -> str | None:
        for older in (color_0929, color_0930):
            if older in text:
                return replace_once(text, older, color_fixed)
        return sub('<span style="color:{{{1}}};">', color_fixed)(text)

    await c.edit(
        "模板:Color",
        color_semantic,
        "红字改用语义变量 --prts-alert-text / --prts-red-text（暗色下提亮），"
        "黑字改用 --prts-page-text（暗色下跟随正文色）；"
        "color: 移进 #switch 分支，修复 <poem> 里 # 开头的色值失效",
    )


@step("arknights_css")
async def step_arknights_css(c: Ctx) -> None:
    """皮肤作用域的站内兜底：行内图片垂直居中，对齐 Vector；反馈与建议版头公告框的底色。"""
    await c.edit(
        "MediaWiki:Arknights.css",
        with_block("img-align", "arknights.css", NOTE),
        "行内图片垂直居中，对齐 Vector（核心 mediawiki.skinning 的 img 规则）",
    )
    await c.edit(
        "MediaWiki:Arknights.css",
        with_block("forum-notice", "arknights_forum_notice.css", NOTE),
        "反馈与建议版头公告框（forum-notice-*）底色跟随主题，暗色下不再浅底浅字",
    )


def drop_legacy_night_blocks(text: str) -> str | None:
    """删掉 Vector 时期手写的 ``@media screen { html.skin-theme-clientpref-night … }``。

    只删顶层、且里面每条规则都是 night 规则的 ``@media screen`` 块；
    ``theme:begin/end`` 区块里的内容不动。没有可删的返回 None。
    """
    kept = [
        m.span()
        for m in re.finditer(
            r"/\* theme:begin\b.*?/\* theme:end [\w-]+ \*/", text, re.DOTALL
        )
    ]
    out: list[str] = []
    pos = 0
    dropped = 0
    for match in re.finditer(r"@media\s+screen\s*\{", text):
        start = match.start()
        if start < pos or any(a <= start < b for a, b in kept):
            continue
        depth = 1
        end = match.end()
        while end < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[end], 0)
            end += 1
        if depth:
            raise SystemExit(f"@media 块没有闭合（偏移 {start}）")
        inner = _css_only(text[match.end() : end - 1])
        selectors = re.findall(r"([^{}]+)\{[^{}]*\}", inner)
        if not selectors or not all(
            "skin-theme-clientpref-night" in part
            for selector in selectors
            for part in selector.split(",")
        ):
            continue
        out.append(text[pos:start].rstrip("\n") + "\n\n" if out or start else "")
        pos = end
        dropped += 1
    if not dropped:
        return None
    out.append(text[pos:].lstrip("\n"))
    return "".join(out).lstrip("\n")


@step("cbox2")
async def step_cbox2(c: Ctx) -> None:
    """Cbox2 暗色重做：以浅色方案为基准推导，替换 Vector 时期手写的 night 规则。"""
    await c.edit(
        "模板:Cbox2/styles.css",
        chain(
            drop_legacy_night_blocks,
            with_block("cbox2-night", "cbox2.css", NOTE),
        ),
        "Cbox2 暗色按浅色方案重新推导：去边框、图标按等级着色、lv2 / lv3 分开、"
        "链接跟随皮肤；自定义配色的框压暗底色（原先浅底浅字看不清）",
    )


@step("enemy_level")
async def step_enemy_level(c: Ctx) -> None:
    """敌人信息等级表：皮肤的行悬停底色盖掉了深底只剩白字；评级弹窗写死白底。"""
    await c.edit(
        "微件:EnemyDataController",
        edit_style_tag(
            lambda css: upsert_block(css, "enemy-rank", snippet("enemy_rank.css"), NOTE)
        ),
        "评级单元格悬停蓝底不再被皮肤行悬停盖掉；评级弹窗底色 / 文字跟随主题",
    )
    await c.edit(
        "模板:敌人信息/levelcontent/styles.css",
        with_block("enemy-level-diff", "enemy_level_diff.css", NOTE),
        "变更高亮格悬停时保持深底",
    )
    # 旧模板不加载上面那张样式表，.diff_block 写在自己的 #widget:style 里
    await c.edit(
        "模板:敌人信息/level",
        edit_widget_style(
            lambda css: upsert_block(
                css, "enemy-level-diff", snippet("enemy_level_diff.css"), NOTE
            )
        ),
        "变更高亮格悬停时保持深底",
    )


@step("relic")
async def step_relic(c: Ctx) -> None:
    """收藏品/common：主题行写死浅灰底，暗色下浅底浅字；定宽 825px 在窄屏撑破页面。"""
    await c.edit(
        "模板:收藏品/common/styles.css",
        chain(
            # 同 table-fixed-width 迁移：桌面不变，窄于 825px 的正文栏里不再溢出，
            # WebKit 也不再把定长 width 当成表格最小宽度
            sub("    width: 825px;\n", "    width: min(825px, 100%);\n"),
            with_block("relic-common", "relic_common.css", NOTE),
        ),
        "主题行暗色底、折叠按钮暗色字；描述 / 备注去掉皮肤的引用块竖线；"
        "表格宽度不超过正文栏",
    )


# --------------------------------------------------------------------------- 条目页


@dataclass(frozen=True)
class PageDark:
    """条目页暗色区块（§13.12）的参数。"""

    # 子页面会被主条目嵌入：区块放页尾的 <noinclude> 里，嵌入时不重复。
    # 主条目放进页内第一段 {{#widget:style}}，不多出空段落
    sub: bool = True
    skip: frozenset[str] = frozenset()  # 页内已经手写过暗色规则的色值
    extra: str | None = None  # 追加的手写片段（scripts/theme_css/）


IS_ROOTS = ("岁的界园志异", "沉沦者的黑流树海", "萨卡兹的无终奇语")
IS_PAGE_OPTS = {
    "岁的界园志异": PageDark(
        sub=False,
        # 页内手写过这几种底色的暗色规则（#18352f 一系），沿用；序列化写法见 is6_sui.css
        skip=frozenset({"#d9fff3", "#bdfee9", "#fdf7ee", "#ffffff", "#f9e179"}),
        extra="is6_sui.css",
    ),
    "沉沦者的黑流树海": PageDark(sub=False),
    "萨卡兹的无终奇语": PageDark(sub=False, extra="is5_sarkaz.css"),
}
# 只被嵌入、不单独阅读的片段（图标、带参数的预览）：样式由嵌入它们的页面推导
IS_EMBED_ONLY = {
    "岁的界园志异/通宝图标",
    "岁的界园志异/钱盒预览",
    "沉沦者的黑流树海/零件图标",
    "萨卡兹的无终奇语/思绪图标",
}
PAGE_DARK_NOTE = "主题适配：页内写死的浅色底 / 深色字的暗色值，由源码推导，见 " + DOC

# 界园页手写的这条把所有 color:#132229 / black 的元素改成白字，
# 浅色渐变格子（没被手写的底色规则换掉）和徽章上因此成了浅底白字
_SUI_TEXT_RULE = re.compile(
    r"\n(?:  html\.skin-theme-clientpref-(?:night|os) body\.page-岁的界园志异 "
    r'\.mw-parser-output \[style\*="color: ?(?:#132229|black)"\][,]? ?\{?\n?)+'
    r"    color: #f8f9fa !important;\n  \}"
)


def drop_sui_text_rule(text: str) -> str | None:
    new, count = _SUI_TEXT_RULE.subn("", text)
    if count not in (0, 2):
        raise SystemExit(f"界园页的黑字规则应有 night / os 各 1 条，实际 {count} 条")
    return new if count else None


_PAGE_NOINCLUDE = re.compile(
    r"\s*(<noinclude>\{\{#widget:style\|style=\n/\* theme:begin page-dark\b)"
)
_HEADING_END = re.compile(r"(?:^|\n)=[^\n]*=[ \t]*$")


def _page_noinclude_sep(before: str) -> str:
    """页尾 <noinclude> 前的空白会跟着嵌入、在主条目里多出空行，所以紧贴前文；
    前文以标题结尾时留一个换行，否则单看这页时那一行不再是标题。"""
    return "\n" if _HEADING_END.search(before) else ""


def place_page_block(text: str, css: str, sub: bool) -> str:
    """把 ``page-dark`` 区块放进条目：已有就替换，否则按 ``sub`` 选位置。"""
    name = "page-dark"
    block = f"/* theme:begin {name} {PAGE_DARK_NOTE} */\n{css}\n/* theme:end {name} */"
    pattern = _block_re(name)
    if pattern.search(text):
        text = pattern.sub(lambda _: block, text, count=1)
        # 旧版在 <noinclude> 前固定留一个换行，重跑时一并收紧
        return _PAGE_NOINCLUDE.sub(
            lambda m: _page_noinclude_sep(text[: m.start()]) + m[1], text, count=1
        )
    spans = [s for s in style_spans(text) if not text[: s[0]].rstrip().endswith(">")]
    if sub or not spans:
        text = text.rstrip()
        return text + _page_noinclude_sep(text) + (
            f"<noinclude>{{{{#widget:style|style=\n{block}\n}}}}</noinclude>\n"
        )
    start, end = spans[0]
    css_now = strip_generated(text[start:end])
    return text[:start] + css_now.rstrip() + "\n\n" + block + "\n" + text[end:]


def page_dark(opts: PageDark, embedded: list[str]) -> Transform:
    def run(text: str) -> str | None:
        current = _block_re("page-dark").sub("", text)
        css = derive([current, *embedded], skip=opts.skip).css()
        if opts.extra:
            css = snippet(opts.extra) + "\n" + css
        if not css.strip():
            return None
        return place_page_block(text, css, opts.sub)

    return run


async def _embedded_articles(wiki: Wiki, title: str) -> list[str]:
    """页面嵌入的主名字空间页面（子页面、其他条目）的源码。"""
    data = await wiki.get(
        action="query", prop="templates", titles=title, tlnamespace=0, tllimit="max"
    )
    pages = data["query"]["pages"]  # formatversion=2：列表
    titles = [t["title"] for p in pages for t in p.get("templates", [])]
    return [(await wiki.read(t)).content for t in titles]


@step("is_pages")
async def step_is_pages(c: Ctx) -> None:
    """§13.12：集成战略三个主题的条目与子页面。"""
    source = c.live or c.wiki
    for root in IS_ROOTS:
        titles = [root]
        async for ref in source.iter_allpages(namespace=0, prefix=root + "/"):
            if ref.title not in IS_EMBED_ONLY:
                titles.append(ref.title)
        for title in titles:
            opts = IS_PAGE_OPTS.get(title, PageDark())
            transforms: list[Transform] = [mark_dark_tables]
            if title == "岁的界园志异":
                transforms.append(drop_sui_text_rule)
            transforms.append(page_dark(opts, await _embedded_articles(source, title)))
            await c.edit(
                title,
                chain(*transforms),
                "深色底表格挂 prts-table-dark；页内浅色底 / 深色字补暗色值",
            )
    # 岁的界园志异/炎国干员速查 → 集成战略/炎国干员速查：表格由微件脚本生成，写死白底
    await c.edit(
        "微件:SuiYanOperatorQuickRef",
        chain(
            sub(
                "text-align:center;background:#fff;')",
                "text-align:center;background:var(--prts-page-card-bg, #fff);')",
                expected=2,
            ),
            sub(
                "'background:#eaecf0;color:#202122;",
                "'background:var(--prts-muted-section-bg, #eaecf0);"
                "color:var(--prts-page-text, #202122);",
            ),
            sub(
                "'background:#f8f9fa;color:#202122;",
                "'background:var(--prts-page-subtle-bg, #f8f9fa);"
                "color:var(--prts-page-text, #202122);",
            ),
        ),
        "表格底色 / 表头改用语义变量（浅色值不变），暗色下不再是白底",
    )


@step("os_branch")
async def step_os_branch(c: Ctx) -> None:
    """§3：由 night 规则机械生成 os 分支。"""
    for title in OS_BRANCH_PAGES:
        await c.edit(title, lambda _: None, "补自动偏好（os）暗色分支")


async def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("-c", "--config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-live", action="store_true")
    parser.add_argument("--show-diff", action="store_true")
    parser.add_argument(
        "--dump", type=Path, help="改后的正文写到这个目录（给 theme_audit --preview）"
    )
    parser.add_argument(
        "--only", action="append", choices=list(STEPS), help="只跑指定步骤，可重复"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    live: Wiki | None = None
    if args.from_live:
        if cfg.api_url == LIVE_API:
            raise SystemExit("--from-live 只用于沙箱：目标站点已经是线上")
        live = Wiki(LIVE_API, cfg.user_agent, cfg.client, dry_run=True)
    print(f"目标站点 {cfg.api_url}" + ("（以线上正文为底）" if live else ""))
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=args.dry_run
    ) as wiki:
        if not args.dry_run:
            await wiki.login(*get_settings().require_credentials())
        ctx = Ctx(wiki, live, args.dry_run, args.show_diff or args.dry_run, args.dump)
        for name, register in STEPS.items():  # 全部登记，按 --only 挑页面执行
            ctx.step = name
            await register(ctx)
        selected = set(args.only or STEPS)
        print("步骤：" + "、".join(n for n in STEPS if n in selected))
        await ctx.flush(selected)
    if live is not None:
        await live.aclose()
    print(f"\n写入 {len(ctx.written)} 页，跳过 {len(ctx.skipped)} 页")
    for title in ctx.skipped:
        print(f"  跳过 {title}")


if __name__ == "__main__":
    asyncio.run(main())
