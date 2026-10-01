"""给只有夜间模式的样式表补「自动偏好」（skin-theme-clientpref-os）分支。

生成逻辑见 wikibot/theme_os.py。幂等：重跑只会重新生成末尾的 theme-os 区块。

    uv run python scripts/theme_os_apply.py --dry-run 模板:Cbox2/styles.css
    uv run python scripts/theme_os_apply.py -c config.sandbox.toml 模板:Cbox2/styles.css
    uv run python scripts/theme_os_apply.py -c config.sandbox.toml --from-live 模板:Cbox2/styles.css

``--from-live`` 先把线上当前正文同步到目标站点再改，用于沙箱库比线上旧的情况。
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.theme_os import add_os_branch
from wikibot.wiki import Wiki

SUMMARY = (
    "补自动偏好（skin-theme-clientpref-os）暗色分支：由 night 规则机械生成 {} 个选择器"
)
LIVE_API = "https://prts.wiki/api.php"


async def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    settings = get_settings()
    live: Wiki | None = None
    if args.from_live:
        if cfg.api_url == LIVE_API:
            raise SystemExit("--from-live 只用于沙箱：目标站点已经是线上")
        live = Wiki(LIVE_API, cfg.user_agent, cfg.client, dry_run=True)

    failed = 0
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=args.dry_run
    ) as wiki:
        if not args.dry_run:
            await wiki.login(*settings.require_credentials())
        print(f"目标站点 {cfg.api_url}")
        for title in args.titles:
            page = await wiki.read(title)
            if page.missing:
                print(f"  ✘ {title}: 不存在")
                failed += 1
                continue
            old = page.content
            base = old
            if live is not None:
                base = (await live.read(title)).content
            new, count = add_os_branch(base)
            if new == old:
                print(f"  = {title}: 已是目标状态，跳过")
                continue
            diff = difflib.unified_diff(
                old.split("\n"),
                new.split("\n"),
                f"{title} (old)",
                f"{title} (new)",
                lineterm="",
                n=1,
            )
            if args.show_diff:
                print("\n".join(diff))
            if args.dry_run:
                print(f"  [dry-run] {title}: 生成 {count} 个 os 选择器")
                continue
            await wiki.edit(title, new, SUMMARY.format(count), baserevid=page.revid)
            print(f"  ✔ {title}: 生成 {count} 个 os 选择器，已写入")
    if live is not None:
        await live.aclose()
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("titles", nargs="+", help="样式表页面标题")
    parser.add_argument("-c", "--config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-live", action="store_true")
    parser.add_argument("--show-diff", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
