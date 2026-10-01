"""对嵌入了某个模板的页面分批提交 purge，让模板改动立刻反映到页面上。

模板改完后页面靠 htmlCacheUpdate 任务陆续刷新，引用量大时要等很久；这里直接清缓存。
默认只清解析缓存（页面下次被访问时重新解析），不重建链接表。

    uv run python scripts/purge_embeddedin.py --dry-run 模板:Color
    uv run python scripts/purge_embeddedin.py 模板:Color
    uv run python scripts/purge_embeddedin.py --namespace 0 模板:Color
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki


async def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(f"目标站点 {cfg.api_url}")
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client) as wiki:
        titles = [
            ref.title
            async for ref in wiki.iter_embeddedin(args.title, args.namespace)
        ]
        print(f"{args.title} 被 {len(titles)} 个页面嵌入")
        if args.dry_run:
            return 0
        await wiki.login(*get_settings().require_credentials())
        purged = 0
        failed: list[str] = []
        for start in range(0, len(titles), args.batch):
            batch = titles[start : start + args.batch]
            try:
                purged += await wiki.purge(batch, forcelinkupdate=args.links)
            except Exception as exc:  # 一批失败不影响后面的批次，最后汇总
                print(f"  ✘ 第 {start + 1} 页起的一批失败：{exc}")
                failed.extend(batch)
            done = min(start + args.batch, len(titles))
            if done % (args.batch * 10) == 0 or done == len(titles):
                print(f"  {done} / {len(titles)}")
            await asyncio.sleep(args.delay)
    print(f"\n已清缓存 {purged} 页，失败 {len(failed)} 页")
    for title in failed:
        print(f"  失败 {title}")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("title", help="模板名，带名字空间前缀")
    parser.add_argument("-c", "--config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="只统计页面数")
    parser.add_argument("--namespace", type=int, default=None)
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.5, help="批次间隔（秒）")
    parser.add_argument("--links", action="store_true", help="同时重建链接表")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
