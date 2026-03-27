# Phase 7 - GitHub App Authentication (Deferred)

## Goal

Provide GitHub App token generation for HTTPS-based git operations, following the
existing config/params pattern. This enables repomgr to work without SSH keys.

## Status

**Deferred** - not needed for v1. SSH-based git operations work fine for a single-box setup.
This phase becomes relevant when:
- Moving to HTTPS-only git remotes
- Adding GitHub API features (PR creation, status checks)
- Running in environments without SSH key access

## Files

- `src/repomgr/config/github_app_config.py` - Pydantic shape model
- `src/repomgr/params/github_app_params.py` - Value loader from env vars

## Config shape

```python
from pydantic import SecretStr
from repomgr.data_models.basemodel_kwargs import BaseModelKwargs

class GitHubAppConfig(BaseModelKwargs):
    """Shape of GitHub App credentials."""

    app_id: int
    installation_id: int
    private_key_pem: SecretStr   # contents of the PEM file, not the path
```

## Params loader

```python
class GitHubAppParams:
    """Load GitHub App credentials from environment variables.

    Env vars (set in ~/cred/repomgr/.env):
        GITHUB_APP_ID: App ID from GitHub settings page
        GITHUB_INSTALLATION_ID: Installation ID
        GITHUB_APP_PEM_PATH: Path to the .pem private key file
    """

    def __init__(self, env_type: EnvType | None = None) -> None: ...
    def to_config(self) -> GitHubAppConfig: ...
```

The params loader reads `GITHUB_APP_PEM_PATH`, expands it, reads the file contents,
and stores them as `SecretStr`. The PEM file path is an env var; the PEM contents
are the actual secret.

## Token generation

Separate module or method on the config:

```python
def get_installation_token(config: GitHubAppConfig) -> str:
    """Generate a short-lived installation access token.

    Signs a JWT with the private key, exchanges it for an installation token.
    Token is valid for 1 hour.

    Requires: PyJWT, cryptography, httpx
    """
```

## Token caching

Wrap in a class that caches the token and refreshes 5 minutes before expiry:

```python
class GitHubTokenProvider:
    def __init__(self, config: GitHubAppConfig) -> None: ...
    def token(self) -> str: ...  # returns cached or refreshes
```

## Integration with git.py

When using HTTPS remotes, git operations need the token:
- Clone: `https://x-access-token:{token}@github.com/owner/repo.git`
- Push: set credential helper or rewrite remote URL temporarily

This integration is deferred - `git.py` currently works with whatever remote URL
is configured (SSH or HTTPS). Token injection would be added as an optional parameter.

## New dependencies (only when this phase is implemented)

```toml
# Add to pyproject.toml when needed
"PyJWT>=2",
"cryptography>=41",
"httpx>=0.27",
```

## Integration into RepomgrParams

When implemented, `RepomgrParams` gains a `github_app` attribute:

```python
class RepomgrParams(metaclass=Singleton):
    def load_config(self) -> None:
        self.paths = RepomgrPaths(self.env_type)
        self.github_app = GitHubAppParams(self.env_type)
        # ...
```

## Reference

See `linux-box-cloudflare/scratch_space/vibes/09.1-github-app-auth-guide.md` for the
full setup walkthrough (App creation, key generation, installation, maintenance).

## nokeys.env (already exists)

```
GITHUB_APP_ID=12345678
GITHUB_INSTALLATION_ID=99999999
GITHUB_APP_PEM_PATH=~/.config/github-apps/repomgr-bot.pem
```
