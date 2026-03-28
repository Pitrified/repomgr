# TODOs

## `--config` flag for repomgr, not subcommands

we currently have `repomgr status --config path/to/repos.toml`, but it would be more intuitive to have `repomgr --config path/to/repos.toml status` - the config applies to the whole command, not just the subcommand.
which could also allow us to create a shell alias like `alias lbr='repomgr --config ~/repos/linux-box-cloudflare/configs/repomgr/repos.toml'` for convenience.
