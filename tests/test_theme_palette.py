"""浅色 → 暗色推导。"""

import pytest

from wikibot.theme_palette import (
    DARK_TEXT,
    contrast,
    dark_variant,
    from_oklch,
    parse_hex,
    to_oklch,
)


def test_short_hex_expands() -> None:
    assert parse_hex("#fdd") == parse_hex("#ffdddd")


@pytest.mark.parametrize("value", ["#4487df", "#85c1f7", "#ebf7fe", "#663333"])
def test_oklch_round_trip(value: str) -> None:
    assert from_oklch(*to_oklch(value)) == value


def test_contrast_matches_wcag() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21)
    assert contrast("#fff", "#fff") == pytest.approx(1)


def test_navbox_levels_keep_order_and_hue() -> None:
    """三级蓝：暗色下仍是一级比一级离底色远，色相不变。"""
    level3, level2, level1 = (
        dark_variant(c) for c in ("#ebf7fe", "#85c1f7", "#4487df")
    )
    lightness = [to_oklch(c)[0] for c in ("#1a1b1c", level3, level2, level1)]
    assert lightness == sorted(lightness)
    assert abs(to_oklch(level1)[2] - to_oklch("#4487df")[2]) < 3


@pytest.mark.parametrize(
    "light", ["#ebf7fe", "#ddeeff", "#85c1f7", "#ffdddd", "#ffeeee", "#f2bdb5"]
)
def test_tints_keep_body_text_readable(light: str) -> None:
    assert contrast(DARK_TEXT, dark_variant(light)) >= 4.5


@pytest.mark.parametrize("light", ["#4487df", "#663333", "#0098dc"])
def test_strong_colors_keep_white_text_readable(light: str) -> None:
    assert contrast("#ffffff", dark_variant(light, strong=True)) >= 4.5


def test_neutrals_snap_to_skin_surfaces() -> None:
    assert dark_variant("#fdfdfd") == "#1a1b1c"
    assert dark_variant("#f7f7f7") == "#232425"
