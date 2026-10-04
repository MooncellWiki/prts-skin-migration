"""新人入门：「干员职业」那组 AKCollapse 标题在手机上不再压住箭头、不再掉出标题条。
见 migration/mobile-table/README.md「新人入门的折叠」。

页面自己的 {{#widget:style}} 把标题写死 `height:2em`，右侧也没给箭头（`.AKCollapse-tri`，绝对定位）留位置：
390 宽下三条长标题压在箭头上，字号稍大的手机上折到第二行的字掉到标题条外面。

- 只加一条 <640 的规则，原规则不动，桌面不变；
- `height:2em` 放开成 `min-height`，折行时标题条跟着长高；右内边距留出箭头的 2.2em，`width` 相应减掉，总宽度不变；
- 标题改 flex，折行的文字排在职业图标右边而不是掉到图标下面。

只改这一个页面，不动 `微件:AKCollapse`（33 个页面在用，各自覆盖了 padding / height）。
幂等：已是目标状态就跳过。

    uv run python scripts/novice_akcollapse_apply.py --dry-run               # 只打印 diff
    uv run python scripts/novice_akcollapse_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/novice_akcollapse_apply.py                         # 线上落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki

PAGE = "新人入门"
SUMMARY = (
    "「干员职业」折叠标题：手机上长标题不再压住箭头 / 掉出标题条"
    "（<640：height → min-height，右侧给箭头留位，文字排在图标右边），桌面不变。"
    "见 prts-skin-migration/migration/mobile-table/README.md"
)

OLD = ".novice-profession .AKCollapse-title {height:2em;padding: 0.3em 0.5em;}"
# 写在 {{#widget:style}} 的参数里：不能出现 `}}`，两个右花括号之间留空格
NEW = (
    OLD + " @media (max-width:639px) {"
    " .novice-profession .AKCollapse-title {height:auto;min-height:2em;padding-right:2.2em;"
    "width:calc(100% - 2.7em);display:flex;align-items:center;gap:0.3em;}"
    " .novice-profession .AKCollapse-title span:first-child {flex:none;} }"
)


def rewrite(title: str, text: str) -> str:
    if NEW in text:
        return text
    if text.count(OLD) != 1:
        raise SystemExit(f"{title}: 期望 1 处 {OLD!r}，实际 {text.count(OLD)} 处")
    return text.replace(OLD, NEW)


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(line[:600] for line in diff))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run
    ) as wiki:
        await wiki.login(*get_settings().require_credentials())
        page = await wiki.read(PAGE)
        if page.missing:
            raise SystemExit(f"{PAGE} 不存在")

        new = rewrite(PAGE, page.content)
        if new == page.content:
            print(f"  = {PAGE}: 已是目标状态，跳过")
            return
        show_diff(PAGE, page.content, new)
        if ns.dry_run:
            print(f"  [dry-run] {PAGE}（r{page.revid}）")
            return
        await wiki.edit(PAGE, new, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {PAGE} 已写入")
        await wiki.purge([PAGE])
        print(f"  purge：{PAGE}")


if __name__ == "__main__":
    asyncio.run(main())
