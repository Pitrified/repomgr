"""Tests for the repos_config module."""

from pathlib import Path
import textwrap
import tomllib

from pydantic import ValidationError
import pytest

from repomgr.config.repos_config import OwnerNotResolvedError
from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import RepomgrTomlConfig
from repomgr.config.repos_config import Role
from repomgr.config.repos_config import Settings
from repomgr.config.repos_config import Transport
from repomgr.config.repos_config import load_config


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Write ``content`` to ``repos.toml`` in ``tmp_path`` and return the path."""
    p = tmp_path / "repos.toml"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# load_config - happy path
# ---------------------------------------------------------------------------


def test_load_minimal_config(tmp_path: Path) -> None:
    """Minimal TOML with only required fields applies all defaults."""
    toml_path = _write_toml(
        tmp_path,
        """
        [[repo]]
        name   = "myrepo"
        owner  = "user"
        roles  = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert len(cfg.repos) == 1
    repo = cfg.repos[0]
    assert repo.name == "myrepo"
    assert repo.owner == "user"
    assert repo.transport is Transport.SSH
    assert repo.remote == "git@github.com:user/myrepo.git"
    assert repo.roles == [Role.SOURCE]
    assert repo.auto_merge is False
    assert repo.test_cmd == "uv run pytest"
    assert repo.deps == []


def test_load_full_config(tmp_path: Path) -> None:
    """All fields specified - no defaults needed."""
    state_file = tmp_path / "my.state.json"
    toml_path = _write_toml(
        tmp_path,
        f"""
        [settings]
        base_path        = "/srv/repos"
        default_test_cmd = "make test"
        state_file       = "{state_file}"
        owner            = "globalowner"
        host             = "git.example.com"
        transport        = "https"

        [[repo]]
        name       = "lib-a"
        owner      = "user"
        roles      = ["source", "consumer"]
        auto_merge = true
        test_cmd   = "pytest -x"
        path       = "/custom/lib-a"
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.settings.base_path == Path("/srv/repos")
    assert cfg.settings.default_test_cmd == "make test"
    assert cfg.settings.state_file == state_file
    assert cfg.settings.owner == "globalowner"
    assert cfg.settings.host == "git.example.com"
    assert cfg.settings.transport is Transport.HTTPS

    repo = cfg.repos[0]
    assert repo.roles == [Role.SOURCE, Role.CONSUMER]
    assert repo.auto_merge is True
    assert repo.test_cmd == "pytest -x"
    assert repo.path == Path("/custom/lib-a")
    # per-repo owner overrides global; host/transport come from settings
    assert repo.remote == "https://git.example.com/user/lib-a.git"


def test_path_resolution_default(tmp_path: Path) -> None:
    """Repo path defaults to base_path / name."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        base_path = "/srv/repos"

        [[repo]]
        name   = "myrepo"
        owner  = "user"
        roles  = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].path == Path("/srv/repos/myrepo")


def test_path_resolution_explicit_override(tmp_path: Path) -> None:
    """Explicit repo path overrides base_path / name."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        base_path = "/srv/repos"

        [[repo]]
        name   = "myrepo"
        owner  = "user"
        roles  = ["source"]
        path   = "/projects/myrepo"
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].path == Path("/projects/myrepo")


def test_path_resolution_tilde_expansion(tmp_path: Path) -> None:
    """Tilde in explicit repo path is expanded."""
    toml_path = _write_toml(
        tmp_path,
        """
        [[repo]]
        name   = "myrepo"
        owner  = "user"
        roles  = ["source"]
        path   = "~/projects/myrepo"
        """,
    )

    cfg = load_config(toml_path)

    assert not str(cfg.repos[0].path).startswith("~")


def test_state_file_resolution_relative(tmp_path: Path) -> None:
    """Relative state_file is resolved relative to the TOML file's directory."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        state_file = "subdir/my.state.json"
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.settings.state_file == (tmp_path / "subdir" / "my.state.json").resolve()


def test_state_file_resolution_absolute(tmp_path: Path) -> None:
    """Absolute state_file is kept as-is."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        state_file = "/var/data/repomgr.state.json"
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.settings.state_file == Path("/var/data/repomgr.state.json")


def test_state_file_default_relative_to_toml(tmp_path: Path) -> None:
    """Default state_file is resolved to the TOML file's directory."""
    toml_path = _write_toml(tmp_path, "")

    cfg = load_config(toml_path)

    assert cfg.settings.state_file == (tmp_path / "repos.state.json").resolve()


def test_test_cmd_per_repo_override(tmp_path: Path) -> None:
    """Per-repo test_cmd overrides the global default."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        default_test_cmd = "make test"
        owner            = "user"

        [[repo]]
        name     = "repo-a"
        roles    = ["source"]
        test_cmd = "pytest -x"

        [[repo]]
        name   = "repo-b"
        roles  = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].test_cmd == "pytest -x"
    assert cfg.repos[1].test_cmd == "make test"


def test_repos_by_name(tmp_path: Path) -> None:
    """repos_by_name index is populated correctly."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner = "user"

        [[repo]]
        name   = "repo-a"
        roles  = ["source"]

        [[repo]]
        name   = "repo-b"
        roles  = ["consumer"]
        """,
    )

    cfg = load_config(toml_path)

    assert set(cfg.repos_by_name.keys()) == {"repo-a", "repo-b"}
    assert cfg.repos_by_name["repo-a"].roles == [Role.SOURCE]
    assert cfg.repos_by_name["repo-b"].roles == [Role.CONSUMER]


def test_multiple_repos(tmp_path: Path) -> None:
    """Multiple [[repo]] entries are all loaded."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner = "u"

        [[repo]]
        name   = "a"
        roles  = ["source"]

        [[repo]]
        name   = "b"
        roles  = ["consumer"]

        [[repo]]
        name   = "c"
        roles  = ["source", "consumer"]
        """,
    )

    cfg = load_config(toml_path)

    assert len(cfg.repos) == 3


# ---------------------------------------------------------------------------
# load_config - remote URL derivation
# ---------------------------------------------------------------------------


def test_remote_derived_ssh(tmp_path: Path) -> None:
    """Default transport (ssh) builds an SSH clone URL."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner = "Pitrified"

        [[repo]]
        name  = "llm-core"
        roles = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].remote == "git@github.com:Pitrified/llm-core.git"


def test_remote_derived_https(tmp_path: Path) -> None:
    """HTTPS transport builds an HTTPS clone URL."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner     = "Pitrified"
        transport = "https"

        [[repo]]
        name  = "llm-core"
        roles = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].remote == "https://github.com/Pitrified/llm-core.git"


def test_repo_name_override(tmp_path: Path) -> None:
    """repo_name appears in the URL while path still uses name."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        base_path = "/srv/repos"
        owner     = "Pitrified"

        [[repo]]
        name      = "convo_craft"
        repo_name = "convo-craft"
        roles     = ["consumer"]
        """,
    )

    cfg = load_config(toml_path)

    repo = cfg.repos[0]
    assert repo.remote == "git@github.com:Pitrified/convo-craft.git"
    assert repo.path == Path("/srv/repos/convo_craft")


def test_owner_global_default(tmp_path: Path) -> None:
    """A repo with no owner inherits settings.owner."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner = "globalowner"

        [[repo]]
        name  = "myrepo"
        roles = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].owner == "globalowner"
    assert cfg.repos[0].remote == "git@github.com:globalowner/myrepo.git"


def test_owner_per_repo_override(tmp_path: Path) -> None:
    """A per-repo owner beats the global default."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner = "globalowner"

        [[repo]]
        name  = "myrepo"
        owner = "repoowner"
        roles = ["source"]
        """,
    )

    cfg = load_config(toml_path)

    assert cfg.repos[0].owner == "repoowner"
    assert cfg.repos[0].remote == "git@github.com:repoowner/myrepo.git"


# ---------------------------------------------------------------------------
# load_config - error cases
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path: Path) -> None:
    """FileNotFoundError is raised when the TOML file does not exist."""
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.toml")


def test_invalid_toml_raises(tmp_path: Path) -> None:
    """TOMLDecodeError is raised for syntactically invalid TOML."""
    bad = tmp_path / "repos.toml"
    bad.write_text("[[repo]\nbroken toml ][")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_config(bad)


def test_owner_missing_raises(tmp_path: Path) -> None:
    """OwnerNotResolvedError when no per-repo owner and no global owner."""
    toml_path = _write_toml(
        tmp_path,
        """
        [[repo]]
        name  = "myrepo"
        roles = ["source"]
        """,
    )

    with pytest.raises(OwnerNotResolvedError, match="myrepo"):
        load_config(toml_path)


def test_transport_invalid_raises(tmp_path: Path) -> None:
    """An unknown transport value fails validation."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner     = "user"
        transport = "ftp"

        [[repo]]
        name  = "myrepo"
        roles = ["source"]
        """,
    )

    with pytest.raises(ValidationError):
        load_config(toml_path)


def test_duplicate_repo_names_raises(tmp_path: Path) -> None:
    """ValidationError is raised when two repos share the same name."""
    toml_path = _write_toml(
        tmp_path,
        """
        [settings]
        owner = "user"

        [[repo]]
        name  = "myrepo"
        roles = ["source"]

        [[repo]]
        name  = "myrepo"
        roles = ["consumer"]
        """,
    )

    with pytest.raises(ValidationError, match="duplicate repo names"):
        load_config(toml_path)


def test_empty_roles_raises(tmp_path: Path) -> None:
    """ValidationError is raised when roles list is empty."""
    toml_path = _write_toml(
        tmp_path,
        """
        [[repo]]
        name  = "myrepo"
        owner = "user"
        roles = []
        """,
    )

    with pytest.raises(ValidationError, match="roles must not be empty"):
        load_config(toml_path)


def test_empty_name_raises(tmp_path: Path) -> None:
    """ValidationError is raised when repo name is empty string."""
    toml_path = _write_toml(
        tmp_path,
        """
        [[repo]]
        name  = ""
        owner = "user"
        roles = ["source"]
        """,
    )

    with pytest.raises(ValidationError, match="repo name must not be empty"):
        load_config(toml_path)


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


def test_role_enum_values() -> None:
    """Role enum has the expected string values."""
    assert Role.SOURCE == "source"
    assert Role.CONSUMER == "consumer"


def test_transport_enum_values() -> None:
    """Transport enum has the expected string values."""
    assert Transport.SSH == "ssh"
    assert Transport.HTTPS == "https"


def test_settings_defaults() -> None:
    """Settings defaults are applied when no values are provided."""
    s = Settings()
    assert s.default_test_cmd == "uv run pytest"
    assert not str(s.base_path).startswith("~")
    assert s.owner is None
    assert s.host == "github.com"
    assert s.transport is Transport.SSH


def test_settings_base_path_tilde_expansion() -> None:
    """Tilde in base_path is expanded on construction."""
    s = Settings(base_path=Path("~/myrepos"))
    assert not str(s.base_path).startswith("~")


def test_repomgr_toml_config_repos_by_name_empty() -> None:
    """repos_by_name is empty when there are no repos."""
    cfg = RepomgrTomlConfig(settings=Settings(), repos=[])
    assert cfg.repos_by_name == {}


def test_repo_config_path_tilde_expanded(tmp_path: Path) -> None:
    """RepoConfig path field expands tilde on construction."""
    repo = RepoConfig(
        name="x",
        owner="u",
        roles=[Role.SOURCE],
        test_cmd="uv run pytest",
        path=Path("~/repos/x"),
    )
    assert not str(repo.path).startswith("~")
    assert repo.remote == "git@github.com:u/x.git"
