"""情报处理室「记录修复奖励」表头在夜间模式下字是糊的。

条目页首 `{{#Widget:style}}` 里有 `.revertrec{filter:invert(1);}`：`{{记录修复奖励|反色=1}}` 的表头整格反色，
调用方传的主题色是反着写的（`#5bfef6` 显示成红），固定的深字和黑图标反成白的。同一块里的夜间规则又给故事表的所有
`th` 加了黑色 `text-shadow` 和压暗用的 `inset box-shadow`。两样都在滤镜之前画，跟着被反成白的：
白字外面一圈白晕（糊），底色蒙一层白（发灰）。不反色的表头是模板固定的深字，套上黑阴影也发脏。

补两条（night / os 各一份）：`th.record-restore-title` 不要文字阴影；`th.revertrec` 的遮罩改成白的，反色后正好是压暗。
Vector 没有 `skin-theme-clientpref-*`，这些规则不生效，不受影响。见 docs/主题适配盘点.md §13.18。

    uv run python scripts/intelligence_room_revertrec_apply.py --dry-run               # 只打印 diff
    uv run python scripts/intelligence_room_revertrec_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/intelligence_room_revertrec_apply.py                         # 线上落地
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

TITLE = "情报处理室"
SUMMARY = (
    "夜间模式下「记录修复奖励」表头的字是糊的：表头的黑色文字阴影和压暗遮罩被 .revertrec 的反色滤镜反成白的。"
    "这一格去掉文字阴影，反色表头的遮罩改成白的（反色后是压暗）。"
    "见 prts-skin-migration/docs/主题适配盘点.md §13.18"
)

NIGHT = "html.skin-theme-clientpref-night .intelligence-room-story-table"
OS = "html.skin-theme-clientpref-os .intelligence-room-story-table"


def fix(prefix: str, indent: str) -> str:
    return (
        f"{indent}{prefix} th.record-restore-title{{\n"
        f"{indent}  text-shadow:none;\n"
        f"{indent}}}\n"
        f'{indent}{prefix} th.revertrec[style*="background"]{{\n'
        f"{indent}  box-shadow:inset 0 0 0 9999px rgba(255,255,255,.18);\n"
        f"{indent}}}\n"
    )


# (锚点, 接在锚点后面的新规则)，锚点是条目里现有的压暗规则，得恰好命中一次
EDITS = [
    (
        f'{NIGHT} th[style*="background"],\n'
        f'{NIGHT} th[style*="background"]{{\n'
        "  box-shadow:inset 0 0 0 9999px rgba(0,0,0,.18);\n"
        "}\n",
        fix(NIGHT, ""),
    ),
    (
        f'  {OS} th[style*="background"]{{\n    box-shadow:inset 0 0 0 9999px rgba(0,0,0,.18);\n  }}\n',
        fix(OS, "  "),
    ),
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        await wiki.login(*get_settings().require_credentials())
        page = await wiki.read(TITLE)
        if page.missing:
            raise SystemExit(f"{TITLE} 不存在")
        content = page.content
        for anchor, added in EDITS:
            if anchor + added in content:
                continue
            n = content.count(anchor)
            if n != 1:
                raise SystemExit(f"{TITLE} 的写法和脚本里记的不一样了（{anchor[:60]}… 命中 {n} 次），人工看一下")
            content = content.replace(anchor, anchor + added)
        if content == page.content:
            print(f"  = {TITLE}: 已是目标状态，跳过")
            return
        diff = difflib.unified_diff(
            page.content.split("\n"),
            content.split("\n"),
            f"{TITLE} (old)",
            f"{TITLE} (new)",
            lineterm="",
            n=0,
        )
        print("\n".join(diff))
        if ns.dry_run:
            print(f"  [dry-run] {TITLE}（原 rev {page.revid}）")
            return
        await wiki.edit(TITLE, content, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TITLE} 已写入（原 rev {page.revid}）")


if __name__ == "__main__":
    asyncio.run(main())
