"""规则的行为。"""

import pytest

from wikibot.config import Config, RegexRuleConfig
from wikibot.rules import RegexRule, RuleRegistry, build_registry
from wikibot.rules.skin import DUAL_RENDER, FontTagRule


def test_font_tag_rewrite() -> None:
    rule = FontTagRule()
    text = '<font color="red" size="5">警告</font>'
    new_text, count = rule.rewrite(text)
    assert new_text == '<span style="color:red;font-size:x-large">警告</span>'
    assert count == 1


def test_font_tag_keeps_other_attributes() -> None:
    new_text, _ = FontTagRule().rewrite('<font class="x" color=#fff>a</font>')
    assert new_text == '<span class="x" style="color:#fff">a</span>'


def test_font_tag_skips_parser_function_attributes() -> None:
    """属性值由 {{#switch:}} 拼出来时正则改不对，必须原样留下。"""
    text = (
        '<font color={{#switch:{{{x|}}}|0="9D9D9D"|#default="black"}}>精英化：</font>'
    )
    assert FontTagRule().rewrite(text) == (text, 0)


def test_font_tag_skips_nested_and_unbalanced_tags() -> None:
    rule = FontTagRule()
    assert rule.rewrite("<font color=red>没有闭合") == ("<font color=red>没有闭合", 0)
    nested = "<font color=red>a<font color=blue>b</font>c</font>"
    # 内层可以安全转换，外层因为跨过了 font 标签而保持不动
    assert rule.rewrite(nested)[0].count("<font") == 1


def test_font_tag_scan_still_reports_skipped_tags() -> None:
    """不自动改，不代表不报告。"""
    text = "<font color={{{c}}}>x</font>"
    assert len(FontTagRule().scan("模板:X", text)) == 2


def test_font_tag_without_font_is_untouched() -> None:
    text = "<span>没有 font 标签</span>"
    assert FontTagRule().rewrite(text) == (text, 0)


def test_detect_only_rule_never_rewrites() -> None:
    text = '<div class="nomobile">桌面版</div><div class="nodesktop">移动版</div>'
    assert DUAL_RENDER.detect_only
    assert DUAL_RENDER.apply(text) == (text, 0)
    hits = DUAL_RENDER.scan("模板:X", text)
    assert [h.match for h in hits] == ["nomobile", "nodesktop"]


def test_scan_reports_line_numbers() -> None:
    rule = RegexRule(id="t", pattern=r"foo")
    text = "第一行\n第二行 foo\n第三行\nfoo 又一次"
    hits = rule.scan("模板:X", text)
    assert [(h.line_no, h.line) for h in hits] == [
        (2, "第二行 foo"),
        (4, "foo 又一次"),
    ]


def test_regex_rule_rewrites_with_groups() -> None:
    rule = RegexRule(
        id="t", pattern=r"background:\s*(#[0-9a-f]{6})", replacement=r"background: \1"
    )
    assert rule.rewrite("background:#ff0000")[0] == "background: #ff0000"


def test_invalid_pattern_is_rejected_at_load_time() -> None:
    with pytest.raises(ValueError, match="unterminated"):
        RegexRule(id="bad", pattern="(")


def test_registry_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="重复"):
        RuleRegistry([RegexRule(id="a", pattern="x"), RegexRule(id="a", pattern="y")])


def test_registry_select_and_unknown_id() -> None:
    registry = RuleRegistry(
        [RegexRule(id="a", pattern="x"), RegexRule(id="b", pattern="y")]
    )
    assert [r.id for r in registry.select(["b"])] == ["b"]
    assert len(registry.select()) == 2
    with pytest.raises(KeyError, match="未知的规则"):
        registry.select(["nope"])


def _config(**kwargs) -> Config:
    base = {
        "api_url": "https://example.invalid/api.php",
        "user_agent": "test",
        "targets": {"t": {"namespaces": [10]}},
    }
    return Config.model_validate(base | kwargs)


def test_build_registry_merges_declarative_rules() -> None:
    registry = build_registry(
        _config(
            regex_rules=[
                RegexRuleConfig(
                    id="from-toml", pattern="a", replacement="b"
                ).model_dump()
            ]
        )
    )
    assert "from-toml" in registry.ids
    assert registry.select(["from-toml"])[0].rewrite("aaa") == ("bbb", 3)


def test_build_registry_honours_disabled_rules() -> None:
    registry = build_registry(_config(disabled_rules=["dual-render"]))
    assert "dual-render" not in registry.ids


# --------------------------------------------------------------------------
# table-fixed-width
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            '{|class="wikitable logo" '
            'style="text-align:center; width:800px; display:table;"',
            '{|class="wikitable logo" '
            'style="text-align:center; width:min(800px, 100%); display:table;"',
        ),
        # 最后一条声明、没有分号
        (
            '{| class="wikitable" style="text-align:left; width: 700px"',
            '{| class="wikitable" style="text-align:left; width:min(700px, 100%)"',
        ),
        # 最后一条声明、带分号
        ("{| style='width:500px;'", "{| style='width:min(500px, 100%);'"),
        (
            '<table class="wikitable" style="width:600px !important">',
            '<table class="wikitable" style="width:min(600px, 100%) !important">',
        ),
        (
            '{| class="wikitable" style="width: 50em; max-width: 100%;"',
            '{| class="wikitable" style="width:min(50em, 100%); max-width: 100%;"',
        ),
        # width 属性：去掉属性，换成样式
        ("{|width=800px", '{| style="width:min(800px, 100%)"'),
        (
            '{| class="wikitable" width="800px" style="text-align:center"',
            '{| class="wikitable" style="text-align:center; width:min(800px, 100%)"',
        ),
        (
            '<table width="600" class="x">',
            '<table class="x" style="width:min(600px, 100%)">',
        ),
        # 第一版的输出：收成一条
        (
            '{| class="wikitable" style="text-align:center; width:567px; '
            'width:min(567px, 100%); white-space:normal;"',
            '{| class="wikitable" style="text-align:center; '
            'width:min(567px, 100%); white-space:normal;"',
        ),
        (
            '{| style="width:600px !important; width:min(600px, 100%) !important"',
            '{| style="width:min(600px, 100%) !important"',
        ),
        (
            '{|width=800px style="width:min(800px, 100%)"',
            '{| style="width:min(800px, 100%)"',
        ),
    ],
)
def test_table_fixed_width_rewrite(before: str, after: str) -> None:
    from wikibot.rules.skin import TableFixedWidthRule

    assert TableFixedWidthRule().rewrite(before) == (after, 1)


@pytest.mark.parametrize(
    "text",
    [
        # 不是表格
        '<div style="width:800px">x</div>',
        # 百分比 / max-width / min-width
        '{| class="wikitable" style="width:100%; max-width:800px"',
        '{| class="wikitable" style="min-width:800px"',
        # 模板参数拼出来的宽度
        '{| class="wikitable" style="width:{{{width|800px}}}"',
        '{| class="wikitable" style="width:800px{{#if:{{{a|}}}|;color:red}}"',
        # 窄表：任何手机都放得下
        '{| class="wikitable" style="width:265px"',
        '{|class="wikitable" width=90px',
        # 样式里另有百分比 width，属性不生效
        '{| width="800" style="width:100%"',
        # 百分比属性
        '{| width="80%"',
        # 已迁过
        '{| style="width:min(800px, 100%)"',
        # 作者自己写的 min()，数值与属性不同：不碰
        '{| width="900" style="width:min(800px, 100%)"',
    ],
)
def test_table_fixed_width_leaves_alone(text: str) -> None:
    from wikibot.rules.skin import TableFixedWidthRule

    assert TableFixedWidthRule().rewrite(text) == (text, 0)


def test_table_fixed_width_is_idempotent_and_skips_protected() -> None:
    from wikibot.rules.skin import TableFixedWidthRule

    rule = TableFixedWidthRule()
    text = (
        '{| class="wikitable" style="width:800px"\n|a\n|}\n'
        '<pre>{| style="width:800px"</pre>\n'
        '<!-- {| style="width:900px" -->\n'
        '<includeonly>{|class="wikitable" style="width:567px;"</includeonly>'
    )
    once, count = rule.apply(text)
    assert count == 2
    assert '<pre>{| style="width:800px"</pre>' in once
    assert '<!-- {| style="width:900px" -->' in once
    assert rule.apply(once) == (once, 0)
    assert len(rule.scan("模板:X", text)) == 2


def test_table_fixed_width_skip_list(tmp_path) -> None:
    import json

    from wikibot.rules.skin import TableFixedWidthRule

    skip = tmp_path / "skip.json"
    skip.write_text(
        json.dumps({"页面A": ["float:right; width:350px"]}, ensure_ascii=False),
        "utf-8",
    )
    rule = TableFixedWidthRule(skip_path=str(skip))
    text = '{| style="float:right; width:350px"\n|}\n{| style="width:800px"\n|}'
    out_a, count_a = rule.apply_to("页面A", text)
    assert count_a == 1
    assert '{| style="float:right; width:350px"\n' in out_a
    _, count_b = rule.apply_to("页面B", text)
    assert count_b == 2
