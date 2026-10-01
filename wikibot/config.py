"""配置加载与校验。

分两层：

* ``config.toml`` —— 非敏感配置（API 地址、目标名字空间、声明式规则），随仓库提交，
  由本模块的 pydantic 模型校验，字段写错 / 多写会直接报错。
* 环境变量（``WIKI_`` 前缀，本地开发可写进 ``.env``）—— Wiki 登录凭据，
  经 pydantic-settings 读取，永不入库。
"""

import re
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
"""仓库根目录。.env 要按它定位，否则换个工作目录跑就读不到凭据。"""

CONFIG_ENV_VAR = "WIKI_CONFIG_PATH"
"""与 Settings.config_path 对应（env_prefix + 字段名），仅用于报错提示。"""
CONFIG_FILENAME = "config.toml"

_FLAG_MAP = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
}


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """编译正则，把 re.error 翻译成 pydantic 认得的 ValueError。"""
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"正则有误 {pattern!r}：{exc}") from exc


def parse_flags(flags: str) -> int:
    """把 ``"im"`` 这样的字符串翻译成 ``re`` 的标志位。"""
    value = 0
    for ch in flags:
        if ch not in _FLAG_MAP:
            raise ValueError(f"未知的正则标志 {ch!r}，可用：{''.join(_FLAG_MAP)}")
        value |= _FLAG_MAP[ch]
    return value


class StrictModel(BaseModel):
    """配置模型基类：禁止多余字段，写错 key 立刻暴露。"""

    model_config = ConfigDict(extra="forbid")


class ClientConfig(StrictModel):
    """MediaWiki 客户端的网络行为。"""

    timeout: Annotated[float, Field(gt=0)] = 30.0
    """单次 HTTP 请求超时（秒）。"""
    max_retries: Annotated[int, Field(ge=1)] = 3
    """网络错误 / maxlag 的重试次数。"""
    maxlag: Annotated[int, Field(ge=0)] = 5
    """MediaWiki maxlag 参数，0 表示不发送。"""
    read_batch_size: Annotated[int, Field(ge=1, le=500)] = 50
    """一次 query 请求拉取的页面数上限。"""
    concurrency: Annotated[int, Field(ge=1, le=32)] = 4
    """并发读请求数上限，写操作始终串行。"""
    edit_delay: Annotated[float, Field(ge=0)] = 5.0
    """两次写入之间的间隔（秒）。"""


class PathsConfig(StrictModel):
    """各类产物的落盘位置，相对路径按仓库根目录解析。"""

    cache_dir: Path = Path("cache")
    report_dir: Path = Path("reports")
    state_path: Path = Path("state.json")


class SandboxConfig(StrictModel):
    """本地沙箱（prts-sandbox）的 MySQL 直连信息。

    只读，用于把上千个页面一次性拉下来做离线扫描——比走 API 快一到两个数量级。
    这里的口令是本地容器的开发口令，不是线上凭据；真要覆盖走 WIKI_SANDBOX_PASSWORD。
    """

    host: str = "127.0.0.1"
    port: Annotated[int, Field(gt=0, le=65535)] = 3307
    user: str = "akdev"
    password: str = "akdev"
    database: str = "ak"
    table_prefix: str = "ak"
    """MediaWiki 建表前缀，沙箱库里是 akpage / akrevision 这样。"""


class TargetConfig(StrictModel):
    """一组待迁移页面的选取条件。"""

    description: str = ""
    namespaces: Annotated[list[int], Field(min_length=1)]
    """名字空间编号，如模板 10、微件 274。"""
    include: list[str] = []
    """标题白名单正则；非空时只保留命中的页面。"""
    exclude: list[str] = []
    """标题黑名单正则；命中即剔除，优先级高于 include。"""

    @field_validator("include", "exclude")
    @classmethod
    def _check_patterns(cls, value: list[str]) -> list[str]:
        for pattern in value:
            compile_pattern(pattern)
        return value

    def matches(self, title: str) -> bool:
        """判断完整标题（含名字空间前缀）是否属于本目标集合。"""
        if any(re.search(p, title) for p in self.exclude):
            return False
        if self.include:
            return any(re.search(p, title) for p in self.include)
        return True


class RegexRuleConfig(StrictModel):
    """写在 config.toml 里的声明式正则规则。"""

    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    description: str = ""
    pattern: str
    replacement: str
    flags: str = ""

    @field_validator("flags")
    @classmethod
    def _check_flags(cls, value: str) -> str:
        parse_flags(value)
        return value

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: str) -> str:
        compile_pattern(value)
        return value


class Config(StrictModel):
    """config.toml 的整体结构，不含任何敏感信息。"""

    api_url: str
    """MediaWiki api.php 地址。"""
    user_agent: str
    """UA，按 MediaWiki 礼节应包含联系方式。"""
    client: ClientConfig = ClientConfig()
    paths: PathsConfig = PathsConfig()
    sandbox: SandboxConfig = SandboxConfig()
    namespace_names: dict[int, str] = {}
    """名字空间编号 → 本地化前缀，直连数据库时用来拼出完整标题。"""
    targets: Annotated[dict[str, TargetConfig], Field(min_length=1)]
    """按名字索引的页面集合，CLI 用 ``-t/--target`` 选取。"""
    regex_rules: list[RegexRuleConfig] = []
    """声明式规则，与 Python 规则合并进同一个注册表。"""
    disabled_rules: list[str] = []
    """要停用的规则 id。"""

    def full_title(self, ns: int, title: str) -> str:
        """把 (名字空间, 页面名) 拼成 API 风格的完整标题。"""
        title = title.replace("_", " ")
        prefix = self.namespace_names.get(ns, "")
        return f"{prefix}:{title}" if prefix else title

    def target(self, name: str) -> TargetConfig:
        """按名字取目标集合，不存在时给出可用值。"""
        try:
            return self.targets[name]
        except KeyError:
            raise KeyError(
                f"未知的目标 {name!r}，config.toml 中可用：{', '.join(self.targets)}"
            ) from None


class Settings(BaseSettings):
    """敏感配置，全部来自环境变量（前缀 ``WIKI_``），本地可写在 .env。"""

    model_config = SettingsConfigDict(
        env_prefix="WIKI_",
        env_file=(".env", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    config_path: str = ""
    """config.toml 路径覆盖，对应 WIKI_CONFIG_PATH。

    走 BaseSettings 而非直接读 os.environ，才能同时支持真实环境变量与 .env。
    """
    username: str = ""
    """Wiki 登录用户名，对应 WIKI_USERNAME。"""
    password: SecretStr = SecretStr("")
    """Wiki 登录密码，建议用 Special:BotPasswords 生成，对应 WIKI_PASSWORD。"""
    sandbox_password: str = ""
    """覆盖 config.toml 里的沙箱库口令，对应 WIKI_SANDBOX_PASSWORD。"""

    def require_credentials(self) -> tuple[str, str]:
        """返回 (username, password)，缺失时抛出带指引的异常。"""
        missing = [
            name
            for name, value in (
                ("WIKI_USERNAME", self.username),
                ("WIKI_PASSWORD", self.password.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"缺少 Wiki 登录凭据环境变量：{', '.join(missing)}。"
                "本地开发可在项目根目录创建 .env（参考 .env.example）；"
                "CI 请在仓库 Settings → Secrets 中配置同名 Secret。"
            )
        return self.username, self.password.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """惰性读取环境变量，避免离线命令（scan/plan）也要求提供凭据。"""
    return Settings()


def repo_root() -> Path:
    """仓库根目录（本文件的上上级）。"""
    return REPO_ROOT


def _resolve_config_path() -> Path:
    """按 环境变量 / .env → 当前工作目录 → 仓库根目录 的顺序定位 config.toml。"""
    if override := get_settings().config_path:
        return Path(override)
    cwd_candidate = Path.cwd() / CONFIG_FILENAME
    if cwd_candidate.is_file():
        return cwd_candidate
    return repo_root() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> Config:
    """读取并校验 config.toml。"""
    config_path = path or _resolve_config_path()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"找不到配置文件 {config_path}；"
            f"可通过环境变量 {CONFIG_ENV_VAR} 指定其他路径。"
        )
    with config_path.open("rb") as f:
        return Config.model_validate(tomllib.load(f))


@lru_cache(maxsize=1)
def get_config() -> Config:
    """默认配置的单例，CLI 传了 --config 时改用 load_config()。"""
    return load_config()
