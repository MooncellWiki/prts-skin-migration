"""规则注册表：内置 Python 规则 + config.toml 里的声明式正则规则。"""

from typing import TYPE_CHECKING

from wikibot.rules.base import RegexRule, Rule
from wikibot.rules.skin import BUILTIN_RULES

if TYPE_CHECKING:
    from collections.abc import Iterable

    from wikibot.config import Config

__all__ = ["BUILTIN_RULES", "RegexRule", "Rule", "RuleRegistry", "build_registry"]


class RuleRegistry:
    """按 id 索引的规则集合。"""

    def __init__(self, rules: "Iterable[Rule]") -> None:
        self._rules: dict[str, Rule] = {}
        for rule in rules:
            if rule.id in self._rules:
                raise ValueError(f"规则 id 重复：{rule.id}")
            self._rules[rule.id] = rule

    def __len__(self) -> int:
        return len(self._rules)

    def __iter__(self):
        return iter(self._rules.values())

    @property
    def ids(self) -> list[str]:
        return list(self._rules)

    def select(self, ids: "Iterable[str]" = ()) -> list[Rule]:
        """按 id 取规则；不传 id 时返回全部。"""
        wanted = list(ids)
        if not wanted:
            return list(self._rules.values())
        missing = [i for i in wanted if i not in self._rules]
        if missing:
            raise KeyError(
                f"未知的规则：{', '.join(missing)}；可用：{', '.join(self._rules)}"
            )
        return [self._rules[i] for i in wanted]


def build_registry(config: "Config") -> RuleRegistry:
    """合并内置规则与 config.toml 的声明式规则，并剔除 disabled_rules。"""
    declared = [
        RegexRule(
            id=item.id,
            description=item.description,
            pattern=item.pattern,
            replacement=item.replacement,
            flags=item.flags,
        )
        for item in config.regex_rules
    ]
    disabled = set(config.disabled_rules)
    rules = [r for r in [*BUILTIN_RULES, *declared] if r.id not in disabled]
    return RuleRegistry(rules)
