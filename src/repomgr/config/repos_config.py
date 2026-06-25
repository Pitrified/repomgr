"""Repos TOML configuration models and loader.

This module defines the Pydantic schema for ``repos.toml`` and provides the
``load_config()`` function that reads, validates, and resolves all paths from
that file.

Everything downstream works with the typed models returned here; no other
module ever reads raw TOML.

Pattern rules:
    The resolution order for each repo is applied entirely inside
    ``load_config()``, not inside the model validators.  Validators only
    handle normalisation that is always safe regardless of context (e.g.
    expanding ``~`` in paths).

See Also:
    ``docs/library/repos_config.md`` - narrative guide.
"""

from enum import StrEnum
from pathlib import Path
import tomllib
from typing import Self

from pydantic import BaseModel
from pydantic import Field
from pydantic import computed_field
from pydantic import field_validator
from pydantic import model_validator


class Role(StrEnum):
    """Role of a repository in the dependency graph.

    Attributes:
        SOURCE: The repo produces artifacts consumed by other repos.
        CONSUMER: The repo depends on git-source artifacts from other repos.
    """

    SOURCE = "source"
    CONSUMER = "consumer"


class Transport(StrEnum):
    """Git transport used to build a repo's clone URL.

    Attributes:
        SSH: ``git@<host>:<owner>/<repo>.git``.
        HTTPS: ``https://<host>/<owner>/<repo>.git``.
    """

    SSH = "ssh"
    HTTPS = "https"


class OwnerNotResolvedError(ValueError):
    """Raised when a repo has no ``owner`` and ``[settings].owner`` is unset."""

    def __init__(self, repo_name: str) -> None:
        """Build the error message naming the offending repo."""
        super().__init__(
            f"repo {repo_name!r} has no 'owner' and [settings].owner is not set"
        )


class Settings(BaseModel):
    """Global settings block from ``repos.toml``.

    Attributes:
        base_path:
            Root directory under which repos are cloned by default.
            Tilde is expanded on construction.
        default_test_cmd:
            Command used when a repo does not specify its own ``test_cmd``.
        state_file:
            Path to the JSON state file.  When relative it is resolved
            against the TOML file's parent directory inside ``load_config()``.
        owner:
            Default repo owner/org applied to every repo that does not set its
            own ``owner``.  Optional; a repo with no owner here or per-repo is
            an error (see ``OwnerNotResolvedError``).
        host:
            Git host used when building clone URLs.  Defaults to ``github.com``.
        transport:
            Git transport (``ssh`` or ``https``) used when building clone URLs.
            Defaults to ``ssh``.
    """

    base_path: Path = Path("~/repos").expanduser()
    default_test_cmd: str = "uv run pytest"
    state_file: Path = Field(default=Path("./repos.state.json"))
    owner: str | None = None
    host: str = "github.com"
    transport: Transport = Transport.SSH

    @field_validator("base_path", mode="before")
    @classmethod
    def _expand_base_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser()

    @field_validator("state_file", mode="before")
    @classmethod
    def _expand_state_file(cls, v: str | Path) -> Path:
        return Path(v).expanduser()


class RepoConfig(BaseModel):
    """Configuration for a single tracked repository.

    Attributes:
        name:
            Unique short name for the repo.  Also the default local clone
            directory name and the default remote repo name.
        owner:
            Repo owner/org on the host.  Resolved by ``load_config()`` from a
            per-repo override or the global ``settings.owner``.
        repo_name:
            Remote repo name, when it differs from ``name``.  When ``None`` the
            clone URL falls back to ``name``.
        host:
            Git host used to build ``remote``.  Resolved by ``load_config()``
            from ``settings.host``.
        transport:
            Git transport used to build ``remote``.  Resolved by
            ``load_config()`` from ``settings.transport``.
        roles:
            One or more roles: ``source`` and/or ``consumer``.
        auto_merge:
            Whether to auto-merge dependency updates on success.
        test_cmd:
            Command to run the test suite.  Resolved by ``load_config()``
            from a per-repo override or the global ``default_test_cmd``.
        path:
            Absolute path to the local clone.  Resolved by ``load_config()``
            from an explicit override or ``base_path / name``.
        deps:
            Git-sourced dependency names.  Left empty here; populated later
            by ``deps.py`` during startup.
        remote:
            Computed git clone URL, derived from ``transport``, ``host``,
            ``owner`` and ``repo_name`` (or ``name``).
    """

    name: str
    owner: str
    repo_name: str | None = None
    host: str = "github.com"
    transport: Transport = Transport.SSH
    roles: list[Role]
    auto_merge: bool = False
    test_cmd: str
    path: Path
    deps: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v:
            msg = "repo name must not be empty"
            raise ValueError(msg)
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remote(self) -> str:
        """Build the git clone URL from the resolved identity fields."""
        repo = self.repo_name or self.name
        if self.transport is Transport.SSH:
            return f"git@{self.host}:{self.owner}/{repo}.git"
        return f"https://{self.host}/{self.owner}/{repo}.git"

    @field_validator("roles")
    @classmethod
    def _roles_not_empty(cls, v: list[Role]) -> list[Role]:
        if not v:
            msg = "roles must not be empty"
            raise ValueError(msg)
        return v

    @field_validator("path", mode="before")
    @classmethod
    def _expand_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser()


class RepomgrTomlConfig(BaseModel):
    """Top-level configuration loaded from ``repos.toml``.

    Attributes:
        settings:
            Global settings block.
        repos:
            Ordered list of repo configurations.
        repos_by_name:
            Computed index from repo name to ``RepoConfig`` for O(1) lookup.
    """

    settings: Settings
    repos: list[RepoConfig]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def repos_by_name(self) -> dict[str, RepoConfig]:
        """Build a name-to-config index from the repos list."""
        return {r.name: r for r in self.repos}

    @model_validator(mode="after")
    def _check_unique_names(self) -> Self:
        names = [r.name for r in self.repos]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            msg = f"duplicate repo names: {dupes}"
            raise ValueError(msg)
        return self


def load_config(path: Path) -> RepomgrTomlConfig:
    """Read ``repos.toml`` and return a validated, path-resolved config.

    Resolution order applied inside this function:

    - ``settings.state_file``: resolved relative to the TOML file's parent
      if not already absolute.
    - ``repo.path``: explicit ``path`` override (tilde-expanded) or
      ``settings.base_path / name``.
    - ``repo.test_cmd``: per-repo override or ``settings.default_test_cmd``.
    - ``repo.owner``: per-repo override or ``settings.owner``; an unresolvable
      owner raises ``OwnerNotResolvedError``.
    - ``repo.host`` / ``repo.transport``: copied from ``settings`` so each
      repo's computed ``remote`` URL is self-contained.

    Args:
        path: Path to the ``repos.toml`` file.

    Returns:
        Validated ``RepomgrTomlConfig`` with all paths fully resolved.

    Raises:
        FileNotFoundError: If the TOML file does not exist.
        tomllib.TOMLDecodeError: If the file content is not valid TOML.
        pydantic.ValidationError: If the content does not match the schema.
        OwnerNotResolvedError: If a repo has no owner and ``settings.owner``
            is unset.
    """
    if not path.exists():
        msg = f"config file not found: {path}"
        raise FileNotFoundError(msg)

    raw = tomllib.loads(path.read_text())
    settings_raw = raw.get("settings", {})

    # Resolve state_file relative to the TOML file's parent directory.
    state_file_raw = settings_raw.get("state_file", "./repos.state.json")
    state_file = Path(state_file_raw)
    if not state_file.is_absolute():
        state_file = (path.parent / state_file).resolve()

    settings = Settings(**{**settings_raw, "state_file": state_file})

    repos: list[RepoConfig] = []
    for repo_raw in raw.get("repo", []):
        if "path" in repo_raw:
            resolved_path: Path = Path(repo_raw["path"]).expanduser()
        else:
            resolved_path = settings.base_path / repo_raw["name"]

        test_cmd: str = repo_raw.get("test_cmd", settings.default_test_cmd)

        owner = repo_raw.get("owner", settings.owner)
        if owner is None:
            raise OwnerNotResolvedError(repo_raw.get("name", ""))

        repos.append(
            RepoConfig(
                **{
                    **repo_raw,
                    "owner": owner,
                    "host": settings.host,
                    "transport": settings.transport,
                    "path": resolved_path,
                    "test_cmd": test_cmd,
                }
            )
        )

    return RepomgrTomlConfig(settings=settings, repos=repos)
