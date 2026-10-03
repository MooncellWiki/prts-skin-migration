"""行悬停时保住单元格自己的底色。

Arknights 皮肤给 wikitable 行加了悬停底色::

    .wikitable > tbody > tr:hover > td { background: var(--ak-bg-hover); }  /* 0,2,3 */

模板 / 页内样式给单元格上底色的选择器特异性比它低（``.fieldeff .title``
是 0,2,0）、又没写 !important 时，悬停那一行的单元格底色被整个换成半透明的
悬停色，文字色照旧——深底白字就成了浅底白字，渐变 / 图标底也没了。行内 style
不受影响；写在 ``|-`` 行上的底色只是被悬停色压暗一点，也不算问题。

修法：把给这些单元格上底色的规则各补一份「所在行悬停」的副本，只带 background
系声明，特异性统一抬高，彼此的先后关系不变（暗色规则的副本照样压过浅色规则的
副本），os 分支照例由 theme_os 从 night 副本生成。悬停时这些单元格保持原底色，
不再有悬停反馈。

选择器两种写法：

- 前缀只有 ``html`` / ``body``（主题类）时写成
  ``前缀 .wikitable > tbody > tr:hover > 主体``，TemplateStyles 也认
- 其余（``.fieldeff .title`` 这种表格类在前的）写成
  ``选择器:is(.wikitable > tbody > tr:hover > td)``。TemplateStyles 的
  css-sanitizer 不认 :is()，这种写法只用于 ``{{#widget:style}}`` / 微件
  ``<style>`` 这类原样输出的样式；不支持 :is() 的旧浏览器整条丢弃，等于没改
"""

import re

from wikibot.theme_os import (
    CssRule,
    _split_declarations,
    parse_rules,
    render_block,
    strip_generated,
)

ROW = ".wikitable > tbody > tr:hover > "
HOVER_ROW = ROW + "td"
_BLOCK = re.compile(
    r"\n*/\* theme:begin hover-keep\b.*?/\* theme:end hover-keep \*/\n*", re.DOTALL
)
_BACKGROUND = re.compile(r"^\s*background(?:-[a-z-]+)?\s*:", re.IGNORECASE)
_IMPORTANT = re.compile(r"!\s*important\s*$", re.IGNORECASE)
_PAGE_COMPOUND = re.compile(r"^(?:html|body)(?=$|[.#\[:])")
_PSEUDO_ELEMENT = re.compile(r"::|:(?:before|after|first-line|first-letter)\b")


def split_subject(selector: str) -> tuple[str, str]:
    """(前缀, 主体复合选择器)。前缀含结尾的组合符与空白；括号 / 方括号里的不算。"""
    depth = 0
    cut = 0
    for pos, char in enumerate(selector):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0 and char in " >+~":
            cut = pos + 1
    return selector[:cut], selector[cut:]


def _classes(compound: str) -> set[str]:
    return set(re.findall(r"\.([\w-]+)", re.sub(r"\([^)]*\)", "", compound)))


def _page_prefix(prefix: str) -> bool:
    """前缀只由 html / body 复合选择器（后代组合）组成，即都在表格之外。"""
    parts = prefix.split()
    return all(_PAGE_COMPOUND.match(part) for part in parts)


def pin_selector(selector: str, *, sanitized: bool) -> str:
    prefix, subject = split_subject(selector)
    if _page_prefix(prefix):
        return f"{prefix}{ROW}{subject}"
    if sanitized:
        raise ValueError(f"TemplateStyles 不认 :is()，这条要手写：{selector}")
    return f"{selector}:is({HOVER_ROW})"


def _background_body(body: str) -> str:
    keep = [
        item.strip()
        for item in _split_declarations(body)
        if _BACKGROUND.match(item) and not _IMPORTANT.search(item.strip())
    ]
    return ";".join(keep)


def hover_keep_rules(css: str, classes: set[str], *, sanitized: bool) -> list[CssRule]:
    """``css`` 里给 ``classes`` 单元格上底色的规则的行悬停副本。

    主体复合选择器带其中任一类名、又写了（非 !important 的）background 系声明的
    规则都算，包括暗色规则；自动生成的 os 区块与上次生成的副本不算。
    """
    base = _BLOCK.sub("\n", strip_generated(css))
    pinned: list[CssRule] = []
    for rule in parse_rules(base):
        body = _background_body(rule.body)
        if not body:
            continue
        selectors = []
        for selector in rule.selectors:
            _, subject = split_subject(selector)
            if _PSEUDO_ELEMENT.search(subject) or not _classes(subject) & classes:
                continue
            if "tr:hover" in selector:  # 本来就是行悬停规则
                continue
            selectors.append(pin_selector(selector, sanitized=sanitized))
        if selectors:
            pinned.append(CssRule(rule.context, tuple(selectors), body))
    return pinned


def hover_keep_css(css: str, classes: set[str], *, sanitized: bool) -> str:
    """副本排成的区块正文（不含 theme:begin/end 标记）；没有可补的返回空串。"""
    rules = hover_keep_rules(css, classes, sanitized=sanitized)
    if not rules:
        return ""
    lines = render_block(rules).split("\n")[1:-1]  # 去掉 theme-os 的首尾标记
    return "\n".join(lines)
