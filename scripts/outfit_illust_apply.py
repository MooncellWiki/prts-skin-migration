"""时装回廊桌面版表格里的立绘在 Skin:Arknights 下只有半格宽：改成按整格宽收缩、竖向按实际图高居中。

`模板:干员时装` 把立绘放在 `position:absolute; left:50%; transform:translateX(-50%)` 的 span 里。
绝对定位元素按内容收缩，可用宽度是「包含块宽 − left」＝半格；新皮肤的
`.mw-file-element { max-width:100% }` 又把图限在这个半宽容器里，400px 的立绘于是缩成 209px
（640–900 宽视口下表格跟着正文栏变窄，再缩到 141–190px）。Vector 没有这条限宽，图保持 400px 溢出容器，
靠 translateX 居中，所以旧皮肤看着正常。内联的 `top:-200px` 按 400px 图高写死，图一缩就偏上。

改两页：

- `模板:干员时装/styles.css`：容器 `width:max-content; max-width:100%`（最宽占满整格），
  `top:0` + `translate(-50%,-50%)` 按实际图高居中；图自己带 `max-width:100%`，Vector 窄屏下不再溢出压到右边文字。
- `模板:干员时装`：去掉立绘 span 的内联 `top:-200px`（`皮肤预览override` 分支不动）。

先写样式再写模板，写完清掉嵌入页的解析缓存——两次写入之间被重新解析的页面会短暂错位。

    uv run python scripts/outfit_illust_apply.py --dry-run                 # 只打印 diff
    uv run python scripts/outfit_illust_apply.py -c config.sandbox.toml    # 先在沙箱演练
    uv run python scripts/outfit_illust_apply.py                           # 线上落地
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

TEMPLATE = "模板:干员时装"
SUMMARY = (
    "桌面版立绘在 Skin:Arknights 下只有半格宽：容器改按整格宽收缩，竖向按实际图高居中。"
    "见 prts-skin-migration/scripts/outfit_illust_apply.py"
)

# (页面, 旧写法, 新写法)，按写入顺序
EDITS = [
    (
        f"{TEMPLATE}/styles.css",
        ".operator-outfit-label-center { left: 50%; transform: translateX(-50%); }",
        ".operator-outfit-label-center {\n"
        "\tleft: 50%;\n"
        "\ttop: 0;\n"
        "\twidth: max-content;\n"
        "\tmax-width: 100%;\n"
        "\ttransform: translate(-50%, -50%);\n"
        "}\n"
        ".operator-outfit-label-center img { max-width: 100%; height: auto; }",
    ),
    (
        TEMPLATE,
        '<span class="operator-outfit-label operator-outfit-label-center" style="top:-200px;">',
        '<span class="operator-outfit-label operator-outfit-label-center">',
    ),
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

        # 两页都核对过再动手，免得只写进去一半
        todo = []
        for title, old, new in EDITS:
            page = await wiki.read(title)
            if page.missing:
                raise SystemExit(f"{title} 不存在")
            if new in page.content:
                print(f"  = {title}: 已是目标状态，跳过")
                continue
            n = page.content.count(old)
            if n != 1:
                raise SystemExit(f"{title} 的写法和脚本里记的不一样了（命中 {n} 次），人工看一下")
            todo.append((page, page.content.replace(old, new)))

        for page, content in todo:
            diff = difflib.unified_diff(
                page.content.split("\n"),
                content.split("\n"),
                f"{page.title} (old)",
                f"{page.title} (new)",
                lineterm="",
                n=0,
            )
            print("\n".join(diff))
            if ns.dry_run:
                print(f"  [dry-run] {page.title}（原 rev {page.revid}）")
                continue
            await wiki.edit(page.title, content, SUMMARY, baserevid=page.revid, nocreate=True)
            print(f"  ✔ {page.title} 已写入（原 rev {page.revid}）")

        if ns.dry_run or not todo:
            return
        titles = [ref.title async for ref in wiki.iter_embeddedin(TEMPLATE)]
        purged = await wiki.purge(titles, forcelinkupdate=False)
        print(f"  ✔ 已清 {purged} / {len(titles)} 个嵌入页的解析缓存")


if __name__ == "__main__":
    asyncio.run(main())
