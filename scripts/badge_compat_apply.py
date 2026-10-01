"""给 Vector / Vector 2022 / Minerva 的站点 JS 追加页脚徽章的过渡期兼容脚本。

背景：`$wgFooterIcons` 全站只有一份。切到 Skin:Arknights 后，Powered by MediaWiki / SMW /
CC BY-NC-SA 三枚指向皮肤自带的白描版（白字透明底，给黑页脚用），放到旧皮肤的浅色底板上就看不见了。
这段脚本在旧皮肤下把它们换回官方彩色原图（核心 / SMW / 核心许可图，都还在原位）。脚本写进各皮肤
自己的 JS 页（`MediaWiki:<皮肤>.js`，随 `site` 模块只在该皮肤下加载），旧皮肤退役时随页面一起没，
不用回头清理。幂等：已含标记就跳过。

    uv run python scripts/badge_compat_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/badge_compat_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/badge_compat_apply.py                             # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/badge_compat_apply.py"
SUMMARY = "页脚徽章过渡期兼容：Skin:Arknights 的白描版在本皮肤下换回官方原图。见 " + SCRIPT

MARKER = "/* ak-badge-compat */"

# 三个皮肤的页脚徽章都是核心的 ul#footer-icons > li > a > img。只认皮肤自带的那几枚
# （路径含 /resources/badge/，按文件名对回原图），Mooncell / HoRain 原图不动。
BLOCK = f"""{MARKER}
/* 页脚徽章过渡期兼容：$wgFooterIcons 全站一份，通用三枚指向 Skin:Arknights 的白描版（白字透明底，
   给黑页脚用），在本皮肤的浅色底板上看不见，这里换回官方彩色原图。随本皮肤退役，不必单独清理。
   由 {SCRIPT} 写入。 */
$( function () {{
	var base = mw.config.get( 'wgScriptPath' );
	var originals = {{
		'mediawiki.svg': base + '/resources/assets/poweredby_mediawiki.svg',
		'smw.svg': mw.config.get( 'wgExtensionAssetsPath' ) + '/SemanticMediaWiki/res/smw/assets/logo_footer.svg',
		'cc-by-nc-sa.svg': base + '/resources/assets/licenses/cc-by-nc-sa.png'
	}};
	$( '#footer-icons img[src*="/resources/badge/"]' ).each( function () {{
		var original = originals[ this.src.split( '/' ).pop() ];
		if ( original ) {{
			this.removeAttribute( 'srcset' );
			this.src = original;
		}}
	}} );
}} );"""

# MediaWiki:<皮肤名>.js 随 site 模块只在对应皮肤下加载；Vector-2022.js / Minerva.js 现网没有，直接建。
PAGES = [
    "MediaWiki:Vector.js",
    "MediaWiki:Vector-2022.js",
    "MediaWiki:Minerva.js",
]


def append_if_missing(text: str) -> str | None:
    if MARKER in text:
        return None
    return (text.rstrip("\n") + "\n\n" if text.strip() else "") + BLOCK + "\n"


async def apply_page(wiki: Wiki, title: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    old = "" if page.missing else page.content
    new = append_if_missing(old)
    if new is None:
        print(f"  = {title}: 已含兼容块，跳过")
        return
    diff = difflib.unified_diff(
        old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=2
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}")
        return
    await wiki.edit(
        title,
        new,
        SUMMARY,
        baserevid=None if page.missing else page.revid,
        nocreate=False,
    )
    print(f"  ✔ {title} 已写入")


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
        for title in PAGES:
            print(f"\n=== {title}")
            await apply_page(wiki, title, ns.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
