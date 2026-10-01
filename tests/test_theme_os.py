"""自动偏好（os）分支生成。"""

from wikibot.theme_os import (
    BEGIN,
    END,
    add_os_branch,
    add_os_branch_embedded,
    add_os_branch_to_page,
    build_os_rules,
    parse_rules,
    split_selectors,
)


def test_plain_night_rule_gets_os_copy() -> None:
    css = "html.skin-theme-clientpref-night body .a {\n  color: #fff !important;\n}\n"
    new_css, count = add_os_branch(css)
    assert count == 1
    assert new_css.startswith(css)
    assert BEGIN in new_css and new_css.rstrip().endswith(END)
    assert (
        "@media (prefers-color-scheme: dark) {\n"
        "  html.skin-theme-clientpref-os body .a {\n"
        "    color: #fff !important;\n"
        "  }\n"
        "}"
    ) in new_css


def test_is_idempotent() -> None:
    css = "html.skin-theme-clientpref-night .a { color: red }\n"
    once, _ = add_os_branch(css)
    twice, count = add_os_branch(once)
    assert twice == once
    assert count == 1


def test_regenerates_after_night_rule_changes() -> None:
    once, _ = add_os_branch("html.skin-theme-clientpref-night .a { color: red }\n")
    edited = once.replace("color: red", "color: blue", 1)
    again, _ = add_os_branch(edited)
    assert "color: red" not in again
    assert again.count("color: blue") == 2


def test_media_screen_is_merged_into_one_query() -> None:
    css = "@media screen {\n  html.skin-theme-clientpref-night .a { color: red }\n}\n"
    new_css, _ = add_os_branch(css)
    assert "@media screen and (prefers-color-scheme: dark) {" in new_css


def test_media_list_is_nested_instead_of_merged() -> None:
    css = "@media screen, print { html.skin-theme-clientpref-night .a { color: red } }"
    (rule,) = build_os_rules(css)
    assert rule.context == (
        "@media (prefers-color-scheme: dark)",
        "@media screen, print",
    )


def test_only_night_selectors_are_copied() -> None:
    css = ".plain, html.skin-theme-clientpref-night .a { color: red }"
    (rule,) = build_os_rules(css)
    assert rule.selectors == ("html.skin-theme-clientpref-os .a",)


def test_duplicate_selectors_collapse() -> None:
    """Pathnav2 里每个选择器都写了两遍。"""
    css = (
        "html.skin-theme-clientpref-night .a,\n"
        "html.skin-theme-clientpref-night .a { color: red }"
    )
    (rule,) = build_os_rules(css)
    assert rule.selectors == ("html.skin-theme-clientpref-os .a",)


def test_existing_os_rule_is_not_duplicated() -> None:
    css = (
        "html.skin-theme-clientpref-night .a { color: red }\n"
        "html.skin-theme-clientpref-night .b { color: red }\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  html.skin-theme-clientpref-os .a { color: red }\n"
        "}\n"
    )
    (rule,) = build_os_rules(css)
    assert rule.selectors == ("html.skin-theme-clientpref-os .b",)


def test_sheet_without_night_rules_is_untouched() -> None:
    css = ".a { color: red }\n"
    assert add_os_branch(css) == (css, 0)


def test_comments_and_attribute_commas_do_not_break_parsing() -> None:
    css = (
        "/* html.skin-theme-clientpref-night .ghost { color: red } */\n"
        'html.skin-theme-clientpref-night .a[style*="a,b{"]:not(.x, .y) { color: red }'
    )
    rules = parse_rules(css)
    assert len(rules) == 1
    assert rules[0].selectors == (
        'html.skin-theme-clientpref-night .a[style*="a,b{"]:not(.x, .y)',
    )


def test_split_selectors_keeps_nested_commas() -> None:
    assert split_selectors("a:is(.x, .y), b") == ["a:is(.x, .y)", "b"]


def test_url_with_semicolon_stays_in_one_declaration() -> None:
    css = (
        "html.skin-theme-clientpref-night .a {"
        " background: url(data:image/png;base64,AAAA) }"
    )
    new_css, _ = add_os_branch(css)
    assert "    background: url(data:image/png;base64,AAAA);" in new_css


def test_existing_os_rule_under_media_screen_counts() -> None:
    """手写的 os 规则常套在 ``@media screen and (…dark)`` 里，night 规则在顶层。"""
    css = (
        "html.skin-theme-clientpref-night .a { color: red }\n"
        "@media screen and (prefers-color-scheme: dark) {\n"
        "  html.skin-theme-clientpref-os .a { color: red }\n"
        "}\n"
    )
    assert add_os_branch(css) == (css, 0)


def test_widget_style_block_gets_os_inside_braces() -> None:
    text = (
        "{{#widget:style|style=\n"
        "html.skin-theme-clientpref-night body .a { color: #fff; }\n"
        "}}\n"
        "{{Navbox|title=x}}"
    )
    new_text, count = add_os_branch_embedded(text)
    assert count == 1
    assert new_text.endswith(END + "\n}}\n{{Navbox|title=x}}")
    assert add_os_branch_embedded(new_text) == (new_text, 1)


def test_single_line_widget_style() -> None:
    text = (
        "<includeonly>{{#Widget:style|style=.x {a:b} "
        "html.skin-theme-clientpref-night body .y {filter: invert(1);} }}</includeonly>"
    )
    new_text, count = add_os_branch_embedded(text)
    assert count == 1
    assert "html.skin-theme-clientpref-os body .y" in new_text
    assert new_text.endswith(END + "\n}}</includeonly>")


def test_style_tag_in_widget() -> None:
    text = (
        "<style>\n.a{color:#000}\n"
        "html.skin-theme-clientpref-night body .a{color:#fff}\n"
        "</style>\n<div>{$x}</div>"
    )
    new_text, count = add_os_branch_to_page("微件:X", text)
    assert count == 1
    assert new_text.endswith(END + "\n</style>\n<div>{$x}</div>")


def test_stylesheet_page_is_handled_whole() -> None:
    css = "html.skin-theme-clientpref-night .a { color: red }\n"
    assert add_os_branch_to_page("模板:X/styles.css", css) == add_os_branch(css)
