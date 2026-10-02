"""条目页暗色区块落位（scripts/theme_apply.py）的单测。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from theme_apply import place_page_block


def test_sub_page_block_glued_to_noinclude() -> None:
    out = place_page_block("正文\n<noinclude>\n{{导航}}\n</noinclude>\n", "a{}", sub=True)
    assert "</noinclude><noinclude>{{#widget:style|style=\n" in out


def test_sub_page_block_glued_to_content() -> None:
    out = place_page_block("{|\n|x\n|}\n\n", "a{}", sub=True)
    assert "|}<noinclude>{{#widget:style|style=\n" in out


def test_heading_at_page_end_keeps_its_line() -> None:
    out = place_page_block("|}\n====匿名信息====\n", "a{}", sub=True)
    assert "====匿名信息====\n<noinclude>{{#widget:style|style=\n" in out
    rerun = place_page_block(out, "b{}", sub=True)
    assert "====匿名信息====\n<noinclude>{{#widget:style|style=\n" in rerun


def test_rerun_removes_gap_from_old_placement() -> None:
    old = place_page_block("正文</noinclude>", "a{}", sub=True)
    gapped = old.replace("</noinclude><noinclude>", "</noinclude>\n<noinclude>", 1)
    out = place_page_block(gapped, "b{}", sub=True)
    assert "</noinclude><noinclude>{{#widget:style|style=\n" in out
    assert "\nb{}\n" in out and "a{}" not in out
