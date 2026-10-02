"""退役 `模板:Mbox2`：剩下的调用改成 `{{cbox2}}`，然后删掉 Mbox2 三页。

Mbox2 是 2019 年导入的大号提示框，参数和 Cbox2 完全一样（lv / icon / iconcolor / bg / bgleft /
iconclass / moreclass / title / text），只是尺寸大一号：640px 宽、64px 图标条、标题 `<big><big>`、
正文 `<big>`。它的 `/core` 全是行内样式、没有类名，Cbox2 后来补的暗色、os 自动主题、
`cbox-autonarrow` 它都没有，暗色下是浅底配皮肤的浅色字；桌面 / 移动还是 `.nomobile` / `.nodesktop` 双份渲染。

2026-10-02 线上 embeddedin：主名字空间 0 处。直接调用只剩 6 处——`模板:Navbox/doc` 顶部的本地改动说明、
`PRTS:练习条目` 的提示框、4 个用户页 / 用户沙盒（`模板:Navbox` 是经文档页间接嵌入的）。
Cbox2 已整体换成设计系统的 `.ak-cbox`（`scripts/cbox2_apply.py`），调用直接换成 `{{cbox2}}` 就是新样式，
不值得为这几处再维护一个模板。先例是 Ombox（`scripts/vector_split_apply.py` 的 `step_cleanup`）。

1. 调用方按 embeddedin 现查，不写死：`{{mbox2|` → `{{cbox2|`，参数原样。
   `text=` 开头的 `<br>` 是给 Mbox2 的 `<p><big>` 垫的，换成 Cbox2 后标题下多一个空行，顺手去掉
2. 用户页（用户 / 用户讨论名字空间）不动，删掉之后那几处显示成红链
3. `模板:Cbox2/doc` 参阅里去掉 `[[模板:mbox2]]`
4. 复查用户页以外没有页面还直接调用 Mbox2，再删 `/doc`、`/core`、`模板:Mbox2`

    uv run python scripts/mbox2_retire_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/mbox2_retire_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/mbox2_retire_apply.py                             # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/mbox2_retire_apply.py"
SUMMARY = "模板:Mbox2 退役，改用 {{cbox2}}（参数相同）。见 " + SCRIPT
DELETE_REASON = "全站已无调用（剩下的调用已改用 {{cbox2}}），Mbox2 无暗色适配。见 " + SCRIPT

TEMPLATE = "模板:Mbox2"
USER_NS = (2, 3)
# 删除顺序：先文档、再 core、最后入口
OWN_PAGES = ("模板:Mbox2/doc", "模板:Mbox2/core", TEMPLATE)

# {{mbox2| / {{Mbox2 | / {{模板:mbox2| / 换行后接 |；不碰 {{mbox2/core（只有 Mbox2 自己调）
CALL = re.compile(r"(\{\{\s*)(?:(?:模板|Template|template):\s*)?([Mm])box2(?=\s*[|}])")
# 改完之后还能匹配上的写法（子页面、拼接出来的名字等），对不上就停，不猜
LEFTOVER = re.compile(r"\{\{[^{}|]*[Mm]box2")
# Mbox2 调用里 text= 紧跟着的 <br> + 换行（给 Mbox2 的 <p><big> 垫的空行）
LEADING_BR = re.compile(
    r"(\{\{\s*(?:(?:模板|Template|template):\s*)?[Mm]box2\s*\|[^{}]*?\btext\s*=\s*)<br\s*/?>[ \t]*(?=\n)"
)
SEE_ALSO = re.compile(r"^\* *\[\[(?:模板|Template):[Mm]box2\]\]\n", re.M)


def to_cbox2(text: str) -> str:
    text = LEADING_BR.sub(r"\1", text)
    return CALL.sub(lambda m: m[1] + ("C" if m[2] == "M" else "c") + "box2", text)


async def edit(wiki: Wiki, title: str, new_text, dry_run: bool) -> bool:
    """改一页；返回改完之后它是否还直接调用 Mbox2。"""
    page = await wiki.read(title)
    if page.missing:
        print(f"  = {title}: 不存在，跳过")
        return False
    old = page.content
    new = new_text(old)
    if new == old:
        # 调用方里的 模板:Navbox 是经文档页间接嵌入的；重跑时已改过的页面也走这里
        print(f"  = {title}: 没有要改的，跳过")
        return bool(LEFTOVER.search(old))
    if LEFTOVER.search(new):
        raise SystemExit(f"  ✘ {title}: 改完还有认不出的 Mbox2 写法，没有动：{LEFTOVER.search(new)[0]!r}")
    diff = difflib.unified_diff(
        old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=1
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}")
        return False
    await wiki.edit(title, new, SUMMARY, baserevid=page.revid)
    print(f"  ✔ {title} 已写入")
    return False


async def delete(wiki: Wiki, title: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        print(f"  = {title}: 已不存在，跳过")
        return
    if dry_run:
        print(f"  [dry-run] 删除 {title}")
        return
    token = await wiki._token()  # noqa: SLF001
    data = await wiki.post(action="delete", title=title, reason=DELETE_REASON, token=token)
    if "delete" not in data:
        raise SystemExit(f"  ✘ 删除 {title} 失败：{data}")
    print(f"  ✔ 已删除 {title}")


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

        refs = [ref async for ref in wiki.iter_embeddedin(TEMPLATE) if ref.title not in OWN_PAGES]
        callers = [ref.title for ref in refs if ref.ns not in USER_NS]
        skipped = [ref.title for ref in refs if ref.ns in USER_NS]
        print(f"\n=== 调用方（{TEMPLATE} 被 {len(refs)} 个页面嵌入，用户页 {len(skipped)} 个不动）")
        for title in skipped:
            print(f"  - {title}: 用户页，不动")
        left = [t for t in callers if await edit(wiki, t, to_cbox2, ns.dry_run)]

        print("\n=== 模板:Cbox2/doc")
        await edit(wiki, "模板:Cbox2/doc", lambda t: SEE_ALSO.sub("", t, count=1), ns.dry_run)

        # 链接表靠任务队列刷新，embeddedin 会滞后；以正文为准：用户页以外没有页面还直接调用才删
        if left:
            raise SystemExit(f"\n  ✘ 这些页面还直接调用 Mbox2，没有删：{'、'.join(left)}")
        print("\n=== 删除")
        for title in OWN_PAGES:
            await delete(wiki, title, ns.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
