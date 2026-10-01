"""命令行入口。

典型流程::

    wikibot check                      # 连通性自检（API + 沙箱库）
    wikibot scan -t template           # 摸底：哪些页面用了旧写法
    wikibot plan -t template           # 预演：规则会怎么改，出 diff
    wikibot apply -t template --dry-run  # 空跑一遍确认无误
    wikibot apply -t template          # 真写
"""

import asyncio
import functools
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import httpx

from wikibot import __version__
from wikibot.config import Config, get_settings, load_config, repo_root
from wikibot.log import logger, set_level
from wikibot.models import Page, PageChange, ScanHit
from wikibot.pipeline import (
    apply_rules,
    scan_page,
    summarize_hits,
    write_plan_report,
    write_scan_report,
)
from wikibot.rules import Rule, build_registry
from wikibot.source import ApiSource, DbSource, PageSource
from wikibot.state import MigrationState, Status
from wikibot.wiki import Wiki, WikiError


def coro[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    """让 click 能挂异步命令。"""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


@dataclass
class App:
    """各命令共享的上下文。"""

    config: Config
    dry_run: bool

    def path(self, value: Path) -> Path:
        """相对路径按仓库根目录解析，免得在哪跑就把产物拉到哪。"""
        return value if value.is_absolute() else repo_root() / value

    def rules(self, ids: Sequence[str]) -> list[Rule]:
        return build_registry(self.config).select(ids)

    async def open_source(self, source: str, login: bool = False) -> PageSource:
        if source == "db":
            settings = get_settings()
            return DbSource(self.config, settings.sandbox_password or None)
        wiki = Wiki(
            self.config.api_url,
            self.config.user_agent,
            self.config.client,
            dry_run=self.dry_run,
        )
        if login:
            username, password = get_settings().require_credentials()
            await wiki.login(username, password)
        return ApiSource(wiki, self.config)


pass_app = click.make_pass_decorator(App)

TARGET_OPTION = click.option(
    "-t",
    "--target",
    default="template",
    show_default=True,
    help="config.toml 里的目标集合",
)
SOURCE_OPTION = click.option(
    "--source",
    type=click.Choice(["db", "api"]),
    default="db",
    show_default=True,
    help="读哪儿：db=本地沙箱库（快），api=线上",
)
RULE_OPTION = click.option(
    "-r", "--rule", "rule_ids", multiple=True, help="只跑指定规则，可重复；默认全跑"
)
LIMIT_OPTION = click.option(
    "-n", "--limit", type=int, default=0, help="最多处理几个页面"
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version")
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="配置文件路径，默认 config.toml",
)
@click.option("-v", "--verbose", is_flag=True, help="打印 DEBUG 日志")
@click.option("--dry-run", is_flag=True, help="所有写操作只打日志不落地")
@click.pass_context
def cli(
    ctx: click.Context, config_path: Path | None, verbose: bool, dry_run: bool
) -> None:
    """prts.wiki 新版皮肤迁移机器人。"""
    set_level("DEBUG" if verbose else "INFO")
    ctx.obj = App(config=load_config(config_path), dry_run=dry_run)


# --------------------------------------------------------------------------
# 只读命令
# --------------------------------------------------------------------------


@cli.command("rules")
@pass_app
def list_rules(app: App) -> None:
    """列出全部规则。"""
    registry = build_registry(app.config)
    click.echo(f"共 {len(registry)} 条规则（detect = 只报告，rewrite = 会改写）\n")
    for rule in registry:
        kind = "detect " if rule.detect_only else "rewrite"
        click.echo(f"  {kind}  {rule.id:<24}{rule.description}")


@cli.command("targets")
@pass_app
def list_targets(app: App) -> None:
    """列出配置里的目标集合。"""
    for name, target in app.config.targets.items():
        ns = ", ".join(str(n) for n in target.namespaces)
        click.echo(f"  {name:<12}ns=[{ns}]  {target.description}")


@cli.command()
@pass_app
@coro
async def check(app: App) -> None:
    """连通性自检：线上 API 与本地沙箱库。"""
    click.echo(f"api_url  {app.config.api_url}")
    settings = get_settings()

    wiki = Wiki(
        app.config.api_url, app.config.user_agent, app.config.client, app.dry_run
    )
    async with wiki:
        try:
            general = (await wiki.siteinfo())["general"]
            click.echo(f"  站点     {general['sitename']}（{general['generator']}）")
            if settings.username and settings.password.get_secret_value():
                await wiki.login(
                    settings.username, settings.password.get_secret_value()
                )
                info = await wiki.userinfo()
                groups = ", ".join(info.get("groups", []))
                click.echo(f"  登录     {info['name']}（{groups}）")
            else:
                click.echo("  登录     跳过：未配置 WIKI_USERNAME / WIKI_PASSWORD")
        except (WikiError, OSError) as exc:
            click.secho(f"  API 不可用：{exc}", fg="red")

    sandbox = app.config.sandbox
    click.echo(f"\nsandbox  {sandbox.host}:{sandbox.port}/{sandbox.database}")
    source = DbSource(app.config, settings.sandbox_password or None)
    async with source:
        try:
            for name, target in app.config.targets.items():
                count = sum([1 async for _ in source.iter_refs(target)])
                click.echo(f"  {name:<12}{count} 个页面")
        except Exception as exc:
            click.secho(f"  沙箱库不可用：{exc}", fg="red")


@cli.command()
@TARGET_OPTION
@SOURCE_OPTION
@LIMIT_OPTION
@pass_app
@coro
async def pages(app: App, target: str, source: str, limit: int) -> None:
    """列出目标集合里的页面标题。"""
    target_config = app.config.target(target)
    async with await app.open_source(source) as src:
        count = 0
        async for ref in src.iter_refs(target_config):
            click.echo(ref.title)
            count += 1
            if limit and count >= limit:
                break
    click.echo(f"\n共 {count} 个页面", err=True)


@cli.command()
@TARGET_OPTION
@SOURCE_OPTION
@LIMIT_OPTION
@pass_app
@coro
async def fetch(app: App, target: str, source: str, limit: int) -> None:
    """把页面正文抓到本地 cache/，之后可完全离线跑 scan / plan。"""
    from wikibot.cache import PageCache

    cache = PageCache(app.path(app.config.paths.cache_dir))
    target_config = app.config.target(target)
    count = 0
    async with await app.open_source(source) as src:
        async for page in src.iter_pages(target_config):
            if page.missing:
                continue
            await asyncio.to_thread(cache.store, page)
            count += 1
            if count % 200 == 0:
                logger.info("已抓取 {} 个页面", count)
            if limit and count >= limit:
                break
    await asyncio.to_thread(cache.save_index)
    click.echo(f"已缓存 {count} 个页面到 {cache.root}")


@cli.command()
@TARGET_OPTION
@SOURCE_OPTION
@RULE_OPTION
@LIMIT_OPTION
@click.option("--report/--no-report", default=True, help="是否写报告文件")
@click.option("--show", type=int, default=0, help="额外打印前 N 条命中明细")
@pass_app
@coro
async def scan(
    app: App,
    target: str,
    source: str,
    rule_ids: tuple[str, ...],
    limit: int,
    report: bool,
    show: int,
) -> None:
    """摸底：统计目标集合里有多少旧写法，出报告。"""
    rules = app.rules(rule_ids)
    target_config = app.config.target(target)
    hits: list[ScanHit] = []
    scanned = 0

    async with await app.open_source(source) as src:
        async for page in src.iter_pages(target_config):
            if page.missing:
                continue
            hits.extend(scan_page(page, rules))
            scanned += 1
            if limit and scanned >= limit:
                break

    stats = summarize_hits(hits)
    click.echo(f"扫描 {scanned} 个页面，命中 {len(hits)} 处\n")
    click.echo(f"  {'规则':<26}{'次数':>8}{'页面':>8}")
    for rule_id, count in stats["hits"].most_common():
        click.echo(f"  {rule_id:<26}{count:>8}{stats['pages'][rule_id]:>8}")

    for hit in hits[:show]:
        click.echo(f"\n  {hit.title}:{hit.line_no}  [{hit.rule_id}]\n    {hit.line}")

    if report and hits:
        md, jsonl = await asyncio.to_thread(
            write_scan_report, hits, app.path(app.config.paths.report_dir), target
        )
        click.echo(f"\n报告：{md}\n明细：{jsonl}")


@cli.command()
@TARGET_OPTION
@SOURCE_OPTION
@RULE_OPTION
@LIMIT_OPTION
@click.option("--report/--no-report", default=True, help="是否写报告文件")
@click.option("--show", type=int, default=0, help="打印前 N 个页面的 diff")
@pass_app
@coro
async def plan(
    app: App,
    target: str,
    source: str,
    rule_ids: tuple[str, ...],
    limit: int,
    report: bool,
    show: int,
) -> None:
    """预演：规则会把页面改成什么样，只算不写。"""
    rules = app.rules(rule_ids)
    _warn_if_all_detect(rules)
    target_config = app.config.target(target)
    changes: list[PageChange] = []

    async with await app.open_source(source) as src:
        async for page in src.iter_pages(target_config):
            if page.missing:
                continue
            changes.append(apply_rules(page, rules))
            if limit and len(changes) >= limit:
                break

    changed = [c for c in changes if c.changed]
    click.echo(f"检查 {len(changes)} 个页面，{len(changed)} 个会被改动")
    for change in changed[:show]:
        click.echo(f"\n=== {change.title}  [{change.summary_line()}]")
        click.echo(change.diff())

    if report:
        md, diff = await asyncio.to_thread(
            write_plan_report, changes, app.path(app.config.paths.report_dir), target
        )
        click.echo(f"\n报告：{md}\ndiff：{diff}")


# --------------------------------------------------------------------------
# 写命令
# --------------------------------------------------------------------------


@cli.command()
@TARGET_OPTION
@RULE_OPTION
@LIMIT_OPTION
@click.option("--summary", default="", help="编辑摘要，默认按命中的规则自动生成")
@click.option("--yes", is_flag=True, help="跳过确认")
@click.option("--force", is_flag=True, help="重新处理 state.json 里已标记完成的页面")
@pass_app
@coro
async def apply(
    app: App,
    target: str,
    rule_ids: tuple[str, ...],
    limit: int,
    summary: str,
    yes: bool,
    force: bool,
) -> None:
    """把改动写回 Wiki（永远走 API，永远带 baserevid 防冲突）。"""
    rules = app.rules(rule_ids)
    _warn_if_all_detect(rules)
    target_config = app.config.target(target)
    state_path = app.path(app.config.paths.state_path)
    state = await asyncio.to_thread(MigrationState.load, state_path)

    source = await app.open_source("api", login=not app.dry_run)
    assert isinstance(source, ApiSource)
    wiki = source.wiki

    async with source:
        titles = [
            ref.title
            async for ref in source.iter_refs(target_config)
            if force or not state.is_done(ref.title)
        ]
        click.echo(f"目标 {target}：{len(titles)} 个待检查页面")

        pending: list[tuple[Page, PageChange]] = []
        async for page in source.fetch_pages(titles):
            if page.missing:
                continue
            change = apply_rules(page, rules)
            if change.changed:
                pending.append((page, change))
            if limit and len(pending) >= limit:
                break

        if not pending:
            click.echo("没有页面需要改动。")
            return

        click.echo(f"{len(pending)} 个页面会被改动：")
        for _, change in pending[:20]:
            click.echo(f"  {change.title}  [{change.summary_line()}]")
        if len(pending) > 20:
            click.echo(f"  …… 其余 {len(pending) - 20} 个见 plan 报告")

        if not yes and not app.dry_run:
            click.confirm(f"确认提交到 {app.config.api_url}？", abort=True)

        done = failed = 0
        for page, change in pending:
            text = summary or _default_summary(change)
            try:
                result = await wiki.edit(
                    title=page.title,
                    text=change.after,
                    summary=text,
                    baserevid=page.revid,
                    basetimestamp=(
                        page.timestamp.isoformat().replace("+00:00", "Z")
                        if page.timestamp
                        else None
                    ),
                )
            # httpx 的超时 / 连接错误不是 OSError：不接住会让整批中途退出。
            # 超时的那次保存可能其实已经落盘，记 FAILED 即可，重跑时规则幂等、不会重复改
            except (WikiError, OSError, httpx.HTTPError) as exc:
                failed += 1
                logger.error("{} 提交失败：{!r}", page.title, exc)
                state.record(
                    page.title, Status.FAILED, page.revid, change.rule_ids, str(exc)
                )
                continue
            done += 1
            new_revid = result.get("edit", {}).get("newrevid", page.revid)
            state.record(page.title, Status.DONE, int(new_revid), change.rule_ids)
            logger.info("[{}/{}] {}", done + failed, len(pending), page.title)
            await asyncio.to_thread(state.save, state_path)

    await asyncio.to_thread(state.save, state_path)
    click.echo(f"\n完成 {done}，失败 {failed}，进度记在 {state_path}")


@cli.command()
@pass_app
def status(app: App) -> None:
    """看迁移进度。"""
    state_path = app.path(app.config.paths.state_path)
    state = MigrationState.load(state_path)
    if not state.pages:
        click.echo(f"还没有进度记录（{state_path}）")
        return
    counts = state.counts()
    click.echo(f"{state_path}：共 {len(state.pages)} 个页面")
    for name, count in counts.items():
        click.echo(f"  {name:<10}{count}")
    failures = [(t, s) for t, s in state.pages.items() if s.status is Status.FAILED]
    if failures:
        click.echo("\n失败的页面：")
        for title, entry in failures[:20]:
            click.echo(f"  {title}  {entry.error}")


def _default_summary(change: PageChange) -> str:
    return f"机器人：新皮肤迁移（{change.summary_line()}）"


def _warn_if_all_detect(rules: Sequence[Rule]) -> None:
    if rules and all(rule.detect_only for rule in rules):
        click.secho(
            "选中的规则全是 detect_only（只报告不改写），不会产生任何改动。"
            "用 wikibot scan 看结果，或用 -r 指定可改写的规则。",
            fg="yellow",
        )


def main(args: Any = None) -> None:
    cli(args)
