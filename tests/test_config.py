"""配置加载与目标匹配。"""

import pytest
from pydantic import ValidationError

from wikibot.config import Config, load_config, repo_root


def test_repo_config_is_valid() -> None:
    """仓库里的 config.toml 必须能过校验——CI 会跑到这条。"""
    config = load_config(repo_root() / "config.toml")
    assert config.api_url.endswith("api.php")
    assert "template" in config.targets
    assert config.targets["template"].namespaces == [10]


def _config(targets: dict) -> Config:
    return Config.model_validate(
        {"api_url": "https://x.invalid/api.php", "user_agent": "t", "targets": targets}
    )


def test_target_include_exclude() -> None:
    config = _config(
        {"t": {"namespaces": [10], "include": [r"^模板:"], "exclude": [r"/doc$"]}}
    )
    target = config.target("t")
    assert target.matches("模板:Cbox2")
    assert not target.matches("模板:Cbox2/doc")
    assert not target.matches("微件:X")


def test_target_without_include_accepts_everything_not_excluded() -> None:
    target = _config({"t": {"namespaces": [10], "exclude": [r"/sandbox$"]}}).target("t")
    assert target.matches("模板:A")
    assert not target.matches("模板:A/sandbox")


def test_unknown_target_lists_available_ones() -> None:
    config = _config({"t": {"namespaces": [10]}})
    with pytest.raises(KeyError, match="未知的目标"):
        config.target("nope")


def test_extra_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _config({"t": {"namespaces": [10], "typo": 1}})


def test_bad_regex_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _config({"t": {"namespaces": [10], "include": ["("]}})


def test_full_title_uses_namespace_names() -> None:
    config = Config.model_validate(
        {
            "api_url": "https://x.invalid/api.php",
            "user_agent": "t",
            "namespace_names": {10: "模板", 274: "微件"},
            "targets": {"t": {"namespaces": [10]}},
        }
    )
    assert config.full_title(10, "Cbox2/core") == "模板:Cbox2/core"
    assert config.full_title(274, "Char_box") == "微件:Char box"
    assert config.full_title(0, "银灰") == "银灰"
