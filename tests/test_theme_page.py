"""条目页暗色规则推导。"""

from wikibot.theme_page import derive, inline_styles, mark_dark_tables
from wikibot.theme_palette import DARK_TEXT, contrast, dark_variant, text_variant

NIGHT = "html.skin-theme-clientpref-night .mw-parser-output "


def css(*sources: str, **kwargs) -> str:
    return derive(list(sources), **kwargs).css()


def test_tags_from_wikitable_and_html_context() -> None:
    text = (
        '{| class="wikitable" style="background:#fff;"\n'
        '|- style="background:#cced81; color:#132229;"\n'
        '| style="background:#bdbdbd;" | <span style="color:#8e2309;">x</span>\n'
        '<div style="background: #FFCDD2;padding: 0 0.5em;">y</div>\n'
    )
    tags = [s.tag for s in inline_styles(text)]
    assert tags == ["table", "tr", "cell", "span", "div"]


def test_light_panel_rows_get_dark_background_and_body_text() -> None:
    out = css('{|\n|- style="background:#cced81; color:#132229;"\n| a\n|}')
    assert 'tr[style^="background:#cced81;" i]' in out
    # 折叠表格展开后行的 style 被重新序列化
    assert 'tr[style*="background: rgb(204, 237, 129)"]' in out
    assert f"background: {dark_variant('#cced81')} !important;" in out
    assert f"color: {DARK_TEXT} !important;" in out


def test_badges_with_own_text_color_stay_as_designed() -> None:
    badge = '<span style="background:#fab619; color: #2f2f2f; padding: 0 5px;">x</span>'
    assert css(badge) == ""


def test_light_box_without_text_color_converts() -> None:
    out = css('<div style="background: #FFCDD2;padding: 0 0.5em;margin-bottom:1em;">')
    assert 'div[style^="background: #FFCDD2;" i]' in out
    assert "color:" not in out  # 文字本来就跟随主题


def test_selector_does_not_catch_longer_hex_or_background_color() -> None:
    out = css('<div style="padding:0;background:#fff">', '<span style="color:#8e2309">')
    assert '[style$="background:#fff" i]' in out
    assert 'span[style^="color:#8e2309" i]' not in out  # 结尾声明：整段相等
    assert 'span[style="color:#8e2309" i]' in out


def test_dark_text_lifted_but_not_on_badges() -> None:
    out = css(
        "{{color|#8e2309|'''险路'''}} {{color|darkgreen|绿色}} {{color|#f1cd9f|淡金}}"
    )
    lifted = text_variant("#8e2309")
    assert f'span[style="color:#8e2309;" i] {{\n  color: {lifted}' in out
    assert 'span[style="color:darkgreen;" i]' in out
    assert "#f1cd9f" not in out  # 本来就够亮


def test_color_template_semantic_values_left_to_common_css() -> None:
    assert css("{{color|red|x}}{{color|#000000|y}}") == ""


def test_raw_red_uses_the_same_variable_as_color_template() -> None:
    out = css('<span style="cursor:help;color:red;">x</span>')
    assert "color: var(--prts-alert-text) !important;" in out


def test_light_gradient_maps_each_stop() -> None:
    out = css('|- style="background:linear-gradient(90deg, #d9fff3,#73e5c2 50%);"')
    dark = dark_variant("#d9fff3"), dark_variant("#73e5c2")
    assert f"linear-gradient(90deg, {dark[0]},{dark[1]} 50%) !important" in out
    assert "rgb(217, 255, 243), rgb(115, 229, 194) 50%" in out


def test_decorative_gradient_with_dark_stops_untouched() -> None:
    title = '<div style="background:linear-gradient(90deg,#f2ece2,#cf7562,#8f888c);">'
    assert css(title) == ""


def test_page_css_light_class_without_text_color() -> None:
    page = (
        "{{#widget:style|style=\n"
        ".end_text.lose{background: #ffe0e0;--bg-ca: darkred;}\n"
        ".end_caption{background:var(--bg-ca);color:#fff;}\n}}"
    )
    out = css(page)
    assert "html.skin-theme-clientpref-night .end_text.lose {" in out
    assert f"background: {dark_variant('#ffe0e0')};" in out
    assert "end_caption" not in out


def test_rules_inside_style_blocks_are_not_rescanned() -> None:
    """生成的区块里有 [style="color:#8e2309;" i]，重跑不能把它当成行内样式。"""
    first = css("{{color|#8e2309|x}}")
    page = "{{color|#8e2309|x}}{{#widget:style|style=\n" + first + "\n}}"
    assert css(page) == first


def test_skip_leaves_hand_written_colors_alone() -> None:
    assert css('<div style="background:#d9fff3;">', skip=frozenset({"#d9fff3"})) == ""


def test_lifted_text_is_readable() -> None:
    for color in ("#0c493d", "#751830", "#6e2b27"):
        assert contrast(text_variant(color), "#202122") >= 4.5


def test_mark_dark_tables() -> None:
    base = '{| class="wikitable x" style="background:#2f2f2f; --color-base:white;"'
    assert mark_dark_tables(base) == base.replace("x", "x prts-table-dark")
    white = ': {| class="wikitable" style="background-color:#464646;color:white"'
    assert "wikitable prts-table-dark" in (mark_dark_tables(white) or "")
    plain = '{|class="wikitable mw-collapsible" style="background-color:#464646;"'
    assert "prts-table-dark" in (mark_dark_tables(plain) or "")
    assert mark_dark_tables('{| class="wikitable" style="background:#fff"') is None
    done = '{| class="wikitable prts-table-dark" style="background:#000"'
    assert mark_dark_tables(done) is None


def test_font_template_color_lifted() -> None:
    out = css("[[x|{{Font|color=#72a|css=text-shadow:0 0 2px #f0f|卡兹瀑布}}]]")
    assert 'span[style^="color: #72a;" i]:not([style*="background" i])' in out
    assert 'span[style*=" color: #72a;" i]' in out
    assert css("{{Font|color=#ffd700|金}}") == ""
