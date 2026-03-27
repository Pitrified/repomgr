"""Rich terminal output formatting for repomgr.

This is the only module in repomgr that imports ``rich``.  It receives
pre-computed data structures and prints formatted output.  It never calls git,
reads files, or writes state.

Pattern rules:
    All public functions print to the terminal and return ``None``.  Callers
    assemble data before calling; this module contains no business logic.
    Tests capture output via a ``rich.console.Console(file=StringIO())``
    instance injected through the ``console`` keyword argument.
"""

from dataclasses import dataclass
from dataclasses import field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from repomgr.git import FetchResult
from repomgr.health import HealthReport
from repomgr.health import HealthStatus
from repomgr.state import RepoState

# ---------------------------------------------------------------------------
# Module-level default console
# ---------------------------------------------------------------------------

_console = Console()

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class StatusRow:
    """Flat data assembled for one dashboard row.

    Attributes:
        name: Short repo name.
        health: Computed health report for the repo.
        live: Current git status captured at check time.
        state: Persisted runtime state from ``StateStore``.
        deps_behind: Names of tracked deps with newer tags available.
    """

    name: str
    health: HealthReport
    branch: str
    is_clean: bool
    is_behind: bool
    is_ahead: bool
    state: RepoState
    deps_behind: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    """Summary of a single repo's dep-update outcome.

    Attributes:
        name: Short repo name.
        outcome: One of ``"updated"``, ``"failed_tests"``,
            ``"no_updates"``, or ``"skipped"``.
        updated_deps: Names of deps whose version was bumped.
        error: Optional message when outcome is ``"failed_tests"`` or
            ``"skipped"`` due to an error.
    """

    name: str
    outcome: str
    updated_deps: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_HEALTH_COLOR: dict[HealthStatus, str] = {
    HealthStatus.GREEN: "green",
    HealthStatus.YELLOW: "yellow",
    HealthStatus.RED: "red",
}

_OUTCOME_COLOR: dict[str, str] = {
    "updated": "green",
    "no_updates": "dim",
    "failed_tests": "red",
    "skipped": "yellow",
}


def _health_text(report: HealthReport) -> Text:
    color = _HEALTH_COLOR.get(report.status, "white")
    return Text(report.status.upper(), style=color)


def _bool_cell(*, value: bool, true_str: str = "yes", false_str: str = "no") -> str:
    return true_str if value else false_str


def _fetch_label(state: RepoState) -> str:
    if state.last_fetch_at is None:
        return "never"
    return state.last_fetch_at.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_status(rows: list[StatusRow], *, console: Console | None = None) -> None:
    """Print the status dashboard table.

    Args:
        rows: Pre-assembled rows, one per tracked repo.
        console: Optional Rich console (defaults to stdout). Pass a
            ``Console(file=StringIO())`` in tests.
    """
    con = console or _console

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Repo", style="bold")
    table.add_column("Health")
    table.add_column("Branch")
    table.add_column("Clean")
    table.add_column("Behind")
    table.add_column("Ahead")
    table.add_column("Last Fetch")
    table.add_column("Deps Behind")

    footnotes: list[tuple[str, list[str]]] = []

    for row in rows:
        deps_cell = ", ".join(row.deps_behind) if row.deps_behind else "-"
        table.add_row(
            row.name,
            _health_text(row.health),
            row.branch or "-",
            _bool_cell(value=row.is_clean),
            _bool_cell(value=row.is_behind),
            _bool_cell(value=row.is_ahead),
            _fetch_label(row.state),
            deps_cell,
        )
        if row.health.reasons:
            footnotes.append((row.name, row.health.reasons))

    con.print(table)

    if footnotes:
        con.print()
        for name, reasons in footnotes:
            for reason in reasons:
                con.print(f"  [bold]{name}[/bold]: {reason}", highlight=False)


def render_fetch_result(
    name: str,
    result: FetchResult,
    *,
    console: Console | None = None,
) -> None:
    """Print fetch results for a single repo.

    Args:
        name: Short repo name.
        result: Outcome of the fetch operation.
        console: Optional Rich console for testing.
    """
    con = console or _console

    header = Text(name, style="bold")
    header.append(" - fetched", style="default")
    con.print(header)

    if result.new_tags:
        con.print(f"  New tags: {', '.join(result.new_tags)}", highlight=False)

    if result.new_branches:
        con.print(
            f"  New branches: {', '.join(result.new_branches)}",
            highlight=False,
        )

    if result.main_advanced_by:
        con.print(
            f"  Main advanced by {result.main_advanced_by} commit(s):",
            highlight=False,
        )
        for entry in result.new_commit_log:
            con.print(f"    {entry}", highlight=False)

    if not (result.new_tags or result.new_branches or result.main_advanced_by):
        con.print("  No changes.", highlight=False)


def render_clone_result(
    name: str,
    *,
    success: bool,
    error: str | None = None,
    console: Console | None = None,
) -> None:
    """Print clone result for a single repo.

    Args:
        name: Short repo name.
        success: Whether the clone succeeded.
        error: Optional error message on failure.
        console: Optional Rich console for testing.
    """
    con = console or _console

    if success:
        con.print(f"[green]cloned[/green] {name}", highlight=False)
    else:
        msg = f"[red]failed[/red] {name}"
        if error:
            msg += f": {error}"
        con.print(msg, highlight=False)


def render_update_summary(
    results: list[UpdateResult],
    *,
    console: Console | None = None,
) -> None:
    """Print summary table of update-deps results.

    Args:
        results: One entry per repo that was evaluated.
        console: Optional Rich console for testing.
    """
    con = console or _console

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Repo", style="bold")
    table.add_column("Outcome")
    table.add_column("Updated Deps")
    table.add_column("Error")

    for r in results:
        color = _OUTCOME_COLOR.get(r.outcome, "white")
        outcome_text = Text(r.outcome, style=color)
        deps_cell = ", ".join(r.updated_deps) if r.updated_deps else "-"
        error_cell = r.error or "-"
        table.add_row(r.name, outcome_text, deps_cell, error_cell)

    con.print(table)


def render_dep_graph(
    graph: dict[str, list[str]],
    *,
    console: Console | None = None,
) -> None:
    """Print the dependency tree using a Rich Tree.

    Args:
        graph: Adjacency list mapping each consumer repo name to the list
            of source repo names it depends on.  Source-only repos have
            an entry with an empty list (or may be absent from keys while
            appearing in values).
        console: Optional Rich console for testing.
    """
    con = console or _console

    # Collect all known names
    all_names: set[str] = set(graph.keys())
    for deps in graph.values():
        all_names.update(deps)

    consumer_names = {name for name, deps in graph.items() if deps}
    source_names = all_names - consumer_names

    root = Tree("[bold]Dependency Graph[/bold]")

    for name in sorted(source_names):
        root.add(f"{name} [dim](source)[/dim]")

    for name in sorted(consumer_names):
        branch = root.add(f"{name} [dim](consumer)[/dim]")
        for dep in graph[name]:
            branch.add(f"[dim]<-[/dim] {dep}")

    con.print(root)


def render_stale_branches(
    repo_name: str,
    branches: list[str],
    *,
    console: Console | None = None,
) -> None:
    """Print stale branches for a repo.

    Args:
        repo_name: Short repo name.
        branches: Names of stale branches.
        console: Optional Rich console for testing.
    """
    con = console or _console

    if not branches:
        con.print(
            f"[dim]{repo_name}:[/dim] no stale branches",
            highlight=False,
        )
        return

    con.print(
        Panel(
            "\n".join(f"  {b}" for b in branches),
            title=f"[bold]{repo_name}[/bold] - stale branches",
            expand=False,
        )
    )
