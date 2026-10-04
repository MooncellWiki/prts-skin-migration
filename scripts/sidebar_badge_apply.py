"""侧栏「新增干员」后的 NEW 角标：字改由 CSS 画，悬停飞出的标题不再带「NEW」。

新皮肤悬停收起着的「新增干员」会飞出子项预览，标题取的是标签的 textContent。角标原先是
`MediaWiki:MenuSidebar` 里一段内联样式的 `<span …>NEW</span>`，字在 DOM 里，标题就成了纯文字的「新增干员NEW」。
不改设计系统的 sidebar-tree.js：把角标换成一个空的 `<span class="menusidebar-new"></span>`，
「NEW」和红底都由 `::after` 画，textContent 里没有它。

`MediaWiki:MenuSidebar` 是 Vector 与新皮肤共用的一页，所以规则要两边各放一份，样子都和原来的内联样式一致：

- 新皮肤：`MediaWiki:Arknights.css`（site.styles，只在 Arknights 下加载）
- Vector：`MediaWiki:MenuSidebar.css`（VectorMenuSidebar 跟着旧侧栏一起内联输出，只在 Vector 下有）

选择器带 `:empty`：CSS 先于侧栏改动生效时不会画出第二个 NEW，所以先写两页 CSS、最后写 MenuSidebar。
新皮肤的 site.styles 有几分钟缓存，这段时间里新皮肤下角标暂时不显示（空 span 没有样式），不会错位。

`vertical-align: .1em` 是之前量出来的：10px 的角标默认 baseline 对齐，跟在 14px 的标签后面，
红块的中线比中文字形的中线低 ~1.7px。`vertical-align: middle` 不管用——它对的是 x-height 的一半，中文字的中线比那高。
按字形墨迹量（canvas measureText），提 .1em 时新皮肤（思源黑体 14px）差 0.05px，Vector（sans-serif 14.4px）
从 1.72px 降到 0.72px。用 em 不用 px：读者放大字号时跟着角标自己的字号走。

    uv run python scripts/sidebar_badge_apply.py --dry-run                 # 只打印 diff
    uv run python scripts/sidebar_badge_apply.py -c config.sandbox.toml    # 先在沙箱演练
    uv run python scripts/sidebar_badge_apply.py                           # 线上落地
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

SUMMARY = "侧栏 NEW 角标改由 CSS 画，新皮肤悬停飞出的标题不再带 NEW。见 prts-skin-migration/scripts/sidebar_badge_apply.py"

SIDEBAR = "MediaWiki:MenuSidebar"
# 原来的内联角标（带不带 vertical-align 都认）
BADGE_RE = re.compile(r'<span style="padding-left:10px;"><span style="[^"]*">NEW</span></span>')
BADGE = '<span class="menusidebar-new"></span>'

ARKNIGHTS_CSS = "MediaWiki:Arknights.css"
ARKNIGHTS_RULE = """\
/* 侧栏「新增干员」后的 NEW 角标：MediaWiki:MenuSidebar 里只留一个空 span，字由这里画。
   字写在 wikitext 里会被侧栏悬停飞出的标题（取标签的 textContent）带成「新增干员NEW」。
   Vector 下的同一条规则在 MediaWiki:MenuSidebar.css。见 prts-skin-migration/scripts/sidebar_badge_apply.py */
.menusidebar-new:empty::after {
  content: "NEW";
  margin-left: 10px;
  padding: 0 4px;
  border-radius: 3px;
  background-color: red;
  color: #fff;
  font-size: 10px;
  font-weight: bold;
  text-shadow: 0 0 2px rgb(0 0 0 / 40%);
  vertical-align: .1em;
}"""

VECTOR_CSS = "MediaWiki:MenuSidebar.css"
VECTOR_RULE = (
    '#MenuSidebar .menusidebar-new:empty::after{content:"NEW";margin-left:10px;padding:0 4px;border-radius:3px;'
    "background-color:red;color:#fff;font-size:10px;font-weight:bold;text-shadow:0 0 2px rgb(0 0 0 / 40%);"
    "vertical-align:.1em}"
)


def append_rule(rule: str, sep: str = "\n\n"):
    def run(text: str) -> str:
        if rule in text:
            return text
        if ".menusidebar-new" in text:
            raise SystemExit("页面里已有 .menusidebar-new 的规则，但和脚本里记的不一样，人工看一下")
        return text.rstrip("\n") + sep + rule + "\n"

    return run


def swap_badge(text: str) -> str:
    if BADGE in text:
        return text
    new, n = BADGE_RE.subn(BADGE, text)
    if n != 1:
        raise SystemExit(f"NEW 角标的写法和脚本里记的不一样了（命中 {n} 次），人工看一下")
    return new


# 顺序有讲究：两页 CSS 在前，侧栏在后
EDITS = [
    (ARKNIGHTS_CSS, append_rule(ARKNIGHTS_RULE)),
    (VECTOR_CSS, append_rule(VECTOR_RULE, sep="\n")),  # 这页是一行一条的压缩写法
    (SIDEBAR, swap_badge),
]


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
        for title, transform in EDITS:
            page = await wiki.read(title)
            if page.missing:
                raise SystemExit(f"{title} 不存在")
            new = transform(page.content)
            if new == page.content:
                print(f"  = {title}: 已是目标状态，跳过")
                continue
            diff = difflib.unified_diff(
                page.content.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=0
            )
            print("\n".join(diff))
            if ns.dry_run:
                print(f"  [dry-run] {title}（原 rev {page.revid}）")
                continue
            await wiki.edit(title, new, SUMMARY, baserevid=page.revid, nocreate=True)
            print(f"  ✔ {title} 已写入（原 rev {page.revid}）")


if __name__ == "__main__":
    asyncio.run(main())
