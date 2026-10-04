"""封面图被旁边的百分比列挤没：与情报处理室同结构的几页（全站扫描「只放一张文件图的格子」里 1000 宽 160 → 0 的那几组）。

皮肤 `.mw-file-element { max-width:100% }` 让封面图的最小宽度计 0，旁边的格子写了百分比宽，封面列被挤到 20px 上下、图 0×0：

- `亘古长明`（`主题曲第十三章预热` 用 `#lsth` 嵌的就是它）、`主题曲第十二章预热`：「支援备忘录 / 限时支援任务」表，
  封面 `th.nomobile` 旁边是 `width=70%` / `30%`（或 `10%`）。封面加任务、奖励两列最少约 280px，正文栏最窄 550 也放得下，
  所以只在页面里给封面图套 160px 宽的 inline-block，不用样式页。
- `好久不见`：同情报处理室「特别行动记述」——封面旁边三列 `width="33%"` 的按钮格，三个 `{{剧情跳转}}` 写死 174px。
  表没有类名，先加 `long-time-no-see-story`，再在页面已经引着的 `模板:好久不见/styles.css` 里加与 `模板:情报处理室/styles.css`
  相同的三条：封面保持 160px；视口 640–899 隐藏封面列；640–719 改用手机版那格竖排的按钮。

见 migration/story-play-button/README.md。

    uv run python scripts/story_cover_apply.py --dry-run
    uv run python scripts/story_cover_apply.py
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

README = "见 prts-skin-migration/migration/story-play-button/README.md"
CHAPTER = "章节封面图被旁边 70% / 30% 的格子挤成 0 宽：封面图套 160px 宽的 inline-block。"
COVER = "封面被三列 33% 的按钮格挤成 20px、图不见：表加类，样式页里封面保持 160px，正文栏放不下时隐藏封面列、改用竖排按钮。"

# 章节封面那一行：!rowspan=N class="nomobile" style="vertical-align:top;"|[[文件:章节名称 …|无框|160px|link=]]
CHAPTER_RE = re.compile(
    r'(!rowspan=\d+ class="nomobile" style="vertical-align:top;"\|)(\[\[文件:章节名称 [^\]|]+\|无框\|160px\|link=\]\])'
)
WRAP = r'\1<span style="display:inline-block;width:160px">\2</span>'

STORY_CSS = """/* 事相记录表：封面格旁边是三列 width="33%" 的按钮格，封面图的最小宽度又因皮肤 max-width:100% 计 0，整列被挤没。
 * 图保持 160px；正文栏放不下封面 + 三个 174px 按钮（< 约 790px，视口 640–899）时隐藏封面列；
 * 连三个按钮都放不下（< 609px，视口 640–719）时改用手机版那格竖排的按钮。同 模板:情报处理室/styles.css。
 * 皮肤在 ≥640 用 !important 隐藏 .nodesktop，这里也得 !important（选择器带 .mw-parser-output，优先级更高） */
.long-time-no-see-story > tbody > tr > th.nomobile[rowspan] .mw-file-element {
\tmax-width: none;
}

@media (min-width: 640px) and (max-width: 899px) {
\t.long-time-no-see-story > tbody > tr > th.nomobile[rowspan] {
\t\tdisplay: none;
\t}
}

@media (min-width: 640px) and (max-width: 719px) {
\t.long-time-no-see-story > tbody > tr > td.nomobile {
\t\tdisplay: none;
\t}

\t.long-time-no-see-story > tbody > tr > td.nodesktop {
\t\tdisplay: table-cell !important;
\t}
}

"""
MARK = "/* theme-os:begin"

# 页面 → [(摘要, 旧, 新, 命中次数)]；旧是 re.Pattern 时按正则替换
EDITS: dict[str, list[tuple[str, str | re.Pattern[str], str, int]]] = {
    "亘古长明": [(CHAPTER, CHAPTER_RE, WRAP, 5)],
    "主题曲第十二章预热": [(CHAPTER, CHAPTER_RE, WRAP, 2)],
    "模板:好久不见/styles.css": [(COVER, MARK, STORY_CSS + MARK, 1)],
    "好久不见": [
        (
            COVER,
            '{| class="wikitable" style="text-align:center;width:100%;max-width:1000px;display:table;font-size:14px"\n'
            '!colspan=6 class="long-time-no-see-title"',
            '{| class="wikitable long-time-no-see-story" style="text-align:center;width:100%;max-width:1000px;display:table;font-size:14px"\n'
            '!colspan=6 class="long-time-no-see-title"',
            1,
        )
    ],
}


def done(content: str, old: str | re.Pattern[str], new: str) -> bool:
    if isinstance(old, re.Pattern):
        return not old.search(content)
    # 插在锚点前面的块：块本身在就算改过（锚点前面可能后来又插了别的）
    if new.endswith(old):
        return new[: -len(old)] in content
    return new in content


async def apply(wiki: Wiki, title: str, edits, *, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"{title} 不存在")
    content = page.content
    applied: list[str] = []
    for summary, old, new, count in edits:
        if done(content, old, new):
            continue
        if isinstance(old, re.Pattern):
            content, n = old.subn(new, content)
        else:
            n = content.count(old)
            content = content.replace(old, new)
        if n != count:
            raise SystemExit(f"{title} 的写法和脚本里记的不一样了（应命中 {count} 次，实际 {n} 次），人工看一下")
        if summary not in applied:
            applied.append(summary)
    if not applied:
        print(f"  = {title}: 已是目标状态，跳过")
        return
    diff = difflib.unified_diff(
        page.content.split("\n"), content.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=0
    )
    print("\n".join(line[:240] for line in diff))
    if dry_run:
        print(f"  [dry-run] {title}（原 rev {page.revid}）")
        return
    await wiki.edit(title, content, "".join(applied) + README, baserevid=page.revid, nocreate=True)
    print(f"  ✔ {title} 已写入（原 rev {page.revid}）")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        await wiki.login(*get_settings().require_credentials())
        # 样式页先于页面：页面先加了类、样式还没到时没有影响；反过来也没有，顺序只为日志好读
        for title, edits in EDITS.items():
            await apply(wiki, title, edits, dry_run=ns.dry_run)
        if not ns.dry_run:
            # 主题曲第十三章预热 用 #lsth 嵌 亘古长明，要清一下
            purged = await wiki.purge(["主题曲第十三章预热", "好久不见", "亘古长明", "主题曲第十二章预热"], forcelinkupdate=False)
            print(f"  ✔ 已清 {purged} 页的解析缓存")


if __name__ == "__main__":
    asyncio.run(main())
