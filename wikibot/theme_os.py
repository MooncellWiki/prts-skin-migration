"""给只写了夜间模式的样式表补「自动偏好」分支。

站内样式普遍只认 ``html.skin-theme-clientpref-night``。用户选「自动」时 html 上挂的是
``skin-theme-clientpref-os``，暗不暗由系统的 ``prefers-color-scheme`` 决定，
于是皮肤变暗了、模板还是浅色底，文字继承皮肤的浅色，整块看不清。

这里把每条 night 规则机械地复制一份：选择器换成 ``-os``，外面包一层
``@media (prefers-color-scheme: dark)``，集中放在样式表末尾的一个带标记的区块里。
区块整体由机器生成——改了 night 规则后重跑即可，重跑是幂等的。

已经手写过等价 os 规则的选择器不会重复生成。模板 / 微件里内嵌的样式（``<style>`` 与
``{{#widget:style|style=…}}``）逐段处理，见 ``add_os_branch_to_page``。
"""

import re
from dataclasses import dataclass

NIGHT = "skin-theme-clientpref-night"
OS = "skin-theme-clientpref-os"
DARK_QUERY = "(prefers-color-scheme: dark)"

BEGIN = (
    "/* theme-os:begin 自动偏好（跟随系统暗色）。由上方 night 规则机械生成，勿手改 */"
)
END = "/* theme-os:end */"

_BLOCK = re.compile(
    r"\n*/\* theme-os:begin\b.*?\*/.*?/\* theme-os:end \*/\n*", re.DOTALL
)
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class CssRule:
    """一条普通规则，连同它外面套着的 at-rule（由外到内）。"""

    context: tuple[str, ...]
    selectors: tuple[str, ...]
    body: str


def strip_generated(css: str) -> str:
    """去掉上一次生成的区块。"""
    stripped = _BLOCK.sub("\n", css)
    return stripped.rstrip("\n") + "\n" if stripped.strip() else ""


def _blank_comments(css: str) -> str:
    """把注释换成等长空白，偏移不变，后面按位置切原文。"""
    return _COMMENT.sub(lambda m: " " * len(m.group(0)), css)


def _skip_string(text: str, pos: int) -> int:
    quote = text[pos]
    pos += 1
    while pos < len(text):
        if text[pos] == "\\":
            pos += 2
            continue
        if text[pos] == quote:
            return pos + 1
        pos += 1
    return pos


def _matching_brace(text: str, open_pos: int) -> int:
    """返回与 ``open_pos`` 处 ``{`` 配对的 ``}`` 的位置；不配对时返回文本末尾。"""
    depth = 0
    pos = open_pos
    while pos < len(text):
        char = text[pos]
        if char in "\"'":
            pos = _skip_string(text, pos)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    return len(text)


def split_selectors(prelude: str) -> list[str]:
    """按顶层逗号拆选择器，``:not(a, b)`` / ``[x="a,b"]`` 里的逗号不算。"""
    parts: list[str] = []
    depth = 0
    start = 0
    pos = 0
    while pos < len(prelude):
        char = prelude[pos]
        if char in "\"'":
            pos = _skip_string(prelude, pos)
            continue
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(prelude[start:pos])
            start = pos + 1
        pos += 1
    parts.append(prelude[start:])
    return [_SPACE.sub(" ", part).strip() for part in parts if part.strip()]


def parse_rules(css: str) -> list[CssRule]:
    """把样式表摊平成规则列表。解析不了的片段直接跳过，不报错。"""
    rules: list[CssRule] = []
    _walk(_blank_comments(css), (), rules)
    return rules


def _walk(text: str, context: tuple[str, ...], out: list[CssRule]) -> None:
    pos = 0
    while pos < len(text):
        brace = _next_of(text, pos, "{")
        if brace == -1:
            return
        semicolon = _next_of(text, pos, ";")
        if semicolon != -1 and semicolon < brace:  # @import / @charset 之类
            pos = semicolon + 1
            continue
        prelude = _SPACE.sub(" ", text[pos:brace]).strip()
        close = _matching_brace(text, brace)
        body = text[brace + 1 : close]
        if prelude.startswith("@"):
            if re.match(r"@(media|supports|layer|container)\b", prelude):
                _walk(body, (*context, prelude), out)
            # @font-face / @keyframes 等里面没有选择器，不展开
        elif prelude:
            out.append(CssRule(context, tuple(split_selectors(prelude)), body))
        pos = close + 1


def _next_of(text: str, pos: int, target: str) -> int:
    while pos < len(text):
        char = text[pos]
        if char in "\"'":
            pos = _skip_string(text, pos)
            continue
        if char == target:
            return pos
        pos += 1
    return -1


def _is_dark_context(context: tuple[str, ...]) -> bool:
    return any("prefers-color-scheme" in item for item in context)


_DARK_CONDITION = re.compile(r"\(\s*prefers-color-scheme\s*:\s*dark\s*\)")


def _base_context(context: tuple[str, ...]) -> tuple[str, ...]:
    """去掉「系统暗色」条件和单独的 ``screen``。

    用来判断手写的 os 规则对应哪条 night 规则。

    手写的 os 规则常写成 ``@media screen and (prefers-color-scheme: dark)``，
    对应的 night 规则却在顶层；两者应视为同一条。
    """
    base: list[str] = []
    for item in context:
        if not item.startswith("@media"):
            base.append(item)
            continue
        query = _DARK_CONDITION.sub("", item[len("@media") :])
        parts = [p.strip() for p in re.split(r"\band\b", query) if p.strip()]
        parts = [p for p in parts if p != "screen"]
        if parts:
            base.append("@media " + " and ".join(parts))
    return tuple(base)


def _dark_context(context: tuple[str, ...]) -> tuple[str, ...]:
    """给 night 规则所在的 at-rule 链加上「系统暗色」条件。

    最里层是不带逗号的 ``@media`` 时并进同一条查询（``screen and (…dark)``），
    否则在最外面再套一层。
    """
    if context and context[-1].startswith("@media") and "," not in context[-1]:
        query = context[-1][len("@media") :].strip()
        return (*context[:-1], f"@media {query} and {DARK_QUERY}")
    return (f"@media {DARK_QUERY}", *context)


def _format_body(body: str, indent: str) -> str:
    declarations = [_SPACE.sub(" ", item).strip() for item in _split_declarations(body)]
    return "\n".join(f"{indent}{item};" for item in declarations if item)


def _split_declarations(body: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    pos = 0
    while pos < len(body):
        char = body[pos]
        if char in "\"'":
            pos = _skip_string(body, pos)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == ";" and depth == 0:
            parts.append(body[start:pos])
            start = pos + 1
        pos += 1
    parts.append(body[start:])
    return parts


def build_os_rules(css: str) -> list[CssRule]:
    """算出需要补的 os 规则（已带上暗色 at-rule）。"""
    rules = parse_rules(strip_generated(css))
    existing = {
        (_base_context(rule.context), selector)
        for rule in rules
        if _is_dark_context(rule.context)
        for selector in rule.selectors
        if OS in selector
    }
    generated: list[CssRule] = []
    seen: set[tuple[tuple[str, ...], str, str]] = set()
    for rule in rules:
        if _is_dark_context(rule.context):
            continue
        context = _dark_context(rule.context)
        body = _format_body(rule.body, "")
        selectors: list[str] = []
        for selector in rule.selectors:
            if NIGHT not in selector:
                continue
            converted = selector.replace(NIGHT, OS)
            key = (context, converted, body)
            if (_base_context(rule.context), converted) in existing or key in seen:
                continue
            seen.add(key)
            selectors.append(converted)
        if selectors and body:
            generated.append(CssRule(context, tuple(selectors), rule.body))
    return generated


def render_block(rules: list[CssRule]) -> str:
    """把生成的规则排成一个区块，相邻且 at-rule 链相同的规则合并到同一层里。"""
    lines = [BEGIN]
    current: tuple[str, ...] | None = None
    for rule in rules:
        if rule.context != current:
            if current is not None:
                lines += _close(current)
            for depth, item in enumerate(rule.context):
                lines.append(f"{'  ' * depth}{item} {{")
            current = rule.context
        elif lines[-1] != "":
            lines.append("")
        pad = "  " * len(rule.context)
        lines.append(
            ",\n".join(f"{pad}{selector}" for selector in rule.selectors) + " {"
        )
        lines.append(_format_body(rule.body, pad + "  "))
        lines.append(f"{pad}}}")
    if current is not None:
        lines += _close(current)
    lines.append(END)
    return "\n".join(lines)


def _close(context: tuple[str, ...]) -> list[str]:
    return [f"{'  ' * depth}}}" for depth in reversed(range(len(context)))]


def add_os_branch(css: str) -> tuple[str, int]:
    """返回 (补完 os 分支的样式表, 生成的选择器数)。没有可补的就原样返回。"""
    base = strip_generated(css)
    rules = build_os_rules(base)
    if not rules:
        return (base if base != css and _BLOCK.search(css) else css), 0
    count = sum(len(rule.selectors) for rule in rules)
    return base.rstrip("\n") + "\n\n" + render_block(rules) + "\n", count


# ------------------------------------------------ 嵌在 wikitext / 微件里的样式

_STYLE_TAG = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE)
_WIDGET_STYLE = re.compile(
    r"\{\{\s*#widget\s*:\s*style\s*\|\s*style\s*=", re.IGNORECASE
)


def _widget_style_spans(text: str) -> list[tuple[int, int]]:
    """``{{#widget:style|style=…}}`` 里样式正文的 [起, 止)。

    按 ``{{`` / ``}}`` 配对找结尾。
    """
    spans: list[tuple[int, int]] = []
    for match in _WIDGET_STYLE.finditer(text):
        depth = 1
        pos = match.end()
        while pos < len(text):
            if text.startswith("{{", pos):
                depth += 1
                pos += 2
            elif text.startswith("}}", pos):
                depth -= 1
                if depth == 0:
                    break
                pos += 2
            else:
                pos += 1
        spans.append((match.end(), pos))
    return spans


def style_spans(text: str) -> list[tuple[int, int]]:
    """wikitext / 微件源码里所有内嵌样式正文的位置。

    包括 ``<style>`` 标签与 ``{{#widget:style}}``。
    """
    spans = [(m.start(2), m.end(2)) for m in _STYLE_TAG.finditer(text)]
    return sorted(spans + _widget_style_spans(text))


def add_os_branch_embedded(text: str) -> tuple[str, int]:
    """对 wikitext / 微件里的每一段内嵌样式分别补 os 分支。

    生成的区块放在该段样式的末尾。
    """
    out: list[str] = []
    last = 0
    total = 0
    for start, end in style_spans(text):
        css = text[start:end]
        new_css, count = add_os_branch(css)
        total += count
        out += [text[last:start], new_css]
        last = end
    out.append(text[last:])
    return "".join(out), total


def is_stylesheet(title: str, content_model: str = "") -> bool:
    return content_model in {"css", "sanitized-css"} or title.endswith(".css")


def add_os_branch_to_page(
    title: str, text: str, content_model: str = ""
) -> tuple[str, int]:
    """独立样式表整页处理，其余（模板 / 微件）只处理内嵌样式。"""
    if is_stylesheet(title, content_model):
        return add_os_branch(text)
    return add_os_branch_embedded(text)
