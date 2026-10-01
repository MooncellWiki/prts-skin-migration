"""规则跑到页面上之后的产物。"""

from wikibot.models import Page
from wikibot.pipeline import apply_rules, scan_page, summarize_hits
from wikibot.rules import RegexRule
from wikibot.rules.skin import DUAL_RENDER, FontTagRule


def _page(text: str, title: str = "模板:X") -> Page:
    return Page(title=title, revid=42, content=text)


def test_apply_rules_records_hits_and_diff() -> None:
    change = apply_rules(_page("<font color=red>a</font>"), [FontTagRule()])
    assert change.changed
    assert change.revid == 42
    assert change.summary_line() == "font-tag×1"
    assert "-<font color=red>a</font>" in change.diff()
    assert '+<span style="color:red">a</span>' in change.diff()


def test_apply_rules_leaves_untouched_pages_alone() -> None:
    change = apply_rules(_page("干净的 wikitext"), [FontTagRule()])
    assert not change.changed
    assert change.hits == []


def test_apply_rules_captures_rule_failure() -> None:
    class Boom(RegexRule):
        def rewrite(self, text: str) -> tuple[str, int]:
            raise RuntimeError("炸了")

    change = apply_rules(_page("x"), [Boom(id="boom", pattern="x")])
    assert change.error is not None
    assert "boom" in change.error
    assert not change.changed  # 出错时保持原文


def test_rules_run_in_order() -> None:
    first = RegexRule(id="a", pattern="1", replacement="2")
    second = RegexRule(id="b", pattern="2", replacement="3")
    change = apply_rules(_page("1"), [first, second])
    assert change.after == "3"
    assert change.summary_line() == "a×1, b×1"


def test_summarize_hits_counts_pages_and_occurrences() -> None:
    hits = [
        *scan_page(_page('<div class="nomobile">a</div>', "模板:A"), [DUAL_RENDER]),
        *scan_page(_page('<div class="nodesktop">b</div>', "模板:B"), [DUAL_RENDER]),
        *scan_page(_page("nomobile nodesktop", "模板:B"), [DUAL_RENDER]),
    ]
    stats = summarize_hits(hits)
    assert stats["hits"]["dual-render"] == 4
    assert stats["pages"]["dual-render"] == 2
