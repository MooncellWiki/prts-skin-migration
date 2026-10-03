"""行悬停时保住单元格底色。"""

import pytest

from wikibot.theme_hover import (
    hover_keep_css,
    hover_keep_rules,
    pin_selector,
    split_subject,
)


def test_split_subject() -> None:
    assert split_subject(".fieldeff .title") == (".fieldeff ", ".title")
    assert split_subject(".a > td.b:not(.c d)") == (".a > ", "td.b:not(.c d)")
    assert split_subject(".x") == ("", ".x")


def test_table_class_prefix_uses_is() -> None:
    assert pin_selector(".fieldeff .title", sanitized=False) == (
        ".fieldeff .title:is(.wikitable > tbody > tr:hover > td)"
    )


def test_page_prefix_is_explicit() -> None:
    assert pin_selector(".wolumonde-dark-cell", sanitized=True) == (
        ".wikitable > tbody > tr:hover > .wolumonde-dark-cell"
    )
    assert pin_selector("html.skin-theme-clientpref-night body .x", sanitized=True) == (
        "html.skin-theme-clientpref-night body .wikitable > tbody > tr:hover > .x"
    )


def test_sanitized_rejects_is() -> None:
    with pytest.raises(ValueError):
        pin_selector(".fieldeff .title", sanitized=True)


def test_only_background_of_listed_classes() -> None:
    css = (
        ".fieldeff .icon {width:80px;background:conic-gradient(#000, #fff);}\n"
        ".fieldeff .icon.good {background:#111;}\n"
        ".fieldeff .title {background:#2f2f2f;color:#fff;}\n"
        ".fieldeff .rank {background:#333;}\n"
        ".fieldeff .title::after {background:red;}\n"
        ".fieldeff .title:before {background:red;}\n"
        ".fieldeff .imp {background:#444 !important;}\n"
    )
    rules = hover_keep_rules(css, {"icon", "title", "imp"}, sanitized=False)
    assert [r.selectors for r in rules] == [
        (".fieldeff .icon:is(.wikitable > tbody > tr:hover > td)",),
        (".fieldeff .icon.good:is(.wikitable > tbody > tr:hover > td)",),
        (".fieldeff .title:is(.wikitable > tbody > tr:hover > td)",),
    ]
    assert rules[0].body == "background:conic-gradient(#000, #fff)"
    assert rules[2].body == "background:#2f2f2f"


def test_night_rule_pinned_and_media_kept() -> None:
    css = (
        ".a {background-color:#000;color:#fff}\n"
        "html.skin-theme-clientpref-night body .a {background-color:#222}\n"
        "@media screen and (max-width:600px) { .a {background:#111} }\n"
        "/* theme-os:begin x */\n@media (prefers-color-scheme: dark) {\n"
        "  html.skin-theme-clientpref-os body .a { background-color:#222 }\n}\n"
        "/* theme-os:end */\n"
    )
    out = hover_keep_css(css, {"a"}, sanitized=True)
    assert out == (
        ".wikitable > tbody > tr:hover > .a {\n"
        "  background-color:#000;\n"
        "}\n"
        "\n"
        "html.skin-theme-clientpref-night body .wikitable > tbody > tr:hover > .a {\n"
        "  background-color:#222;\n"
        "}\n"
        "@media screen and (max-width:600px) {\n"
        "  .wikitable > tbody > tr:hover > .a {\n"
        "    background:#111;\n"
        "  }\n"
        "}"
    )


def test_ignores_previous_block() -> None:
    css = ".a {background:#000}\n"
    first = hover_keep_css(css, {"a"}, sanitized=True)
    block = f"/* theme:begin hover-keep note */\n{first}\n/* theme:end hover-keep */"
    again = css + "\n" + block + "\n"
    assert hover_keep_css(again, {"a"}, sanitized=True) == first


def test_nothing_to_pin() -> None:
    assert hover_keep_css(".a {color:red}", {"a"}, sanitized=False) == ""
