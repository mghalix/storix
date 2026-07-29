# The sx CLI

`sx` is the storix core behind a command line: the same session, the same cwd,
the same layers, the same typed errors, driven from your terminal.

It is standalone. Install it once and it works from any directory, with no
project checkout and no virtual environment to activate:

```bash
curl -LsSf https://storix.mghalix.com/install.sh | sh
```

Every other way to install it (`uv tool`, `uv add`, `pip`, Windows PowerShell,
picking provider extras) is on the
[Installation](../get-started/installation.md#the-cli) page.

## Your first commands

```bash
sx --version       # print the installed version and exit
sx                 # interactive shell, anchored where you ran it
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

That is the whole shape of it: `sx` with no command opens a shell, `sx` with a
command runs it once and exits.

Connection settings come from the same sources the library reads: the
`STORIX_*` environment variables and the provider sections of a config file
(`[s3]`, `[azure]`, ...). So `sx -p azure` talks to the account your code
already talks to.

!!! info "`sx` with no configuration lists where you stand"

    With nothing configured - no flag, no profile, no environment variable, no
    config file - a `local` session anchors at the directory you ran `sx` from,
    the way `ls` does. Any configured base still wins.

    The **library** default is unchanged: `get_storage()` with zero config is
    still `~/.storix`. Library code writing to an application's working
    directory is a hazard; a human at a prompt is the one case where the cwd is
    the honest default.

## Ask sx about itself

You should not have to come back to these pages to use it. `sx --help` groups
its commands by what they do (navigate, read, write, transfer, and the ones
about sx itself) and its options by what they configure (connection, profile,
session).

Three commands answer the questions this section otherwise would:

```bash
sx config show --effective   # what this session will do, and where each value came from
sx config sources            # which files are read, in which order they win
sx doctor                    # installation, config, and what it can reach
```

None of them opens a connection or resolves a credential, so all three still
answer when the connection is the thing that is broken.

## Where to go next

| Page | What it covers |
| --- | --- |
| [Commands](commands.md) | The command set, the unix flags, `find`/`du`/`tree`, `provision` |
| [The interactive shell](shell.md) | One live session, tab completion, aliases at the prompt |
| [Transfers](transfers.md) | `push` and `pull`, progress bars, tuning, stopping cleanly |
| [Configuration](configuration.md) | The precedence chain, the three files, `sx config` |
| [Preferences and layers](preferences.md) | Icons, aliases, the always-on layer stack |
| [doctor, install and update](maintenance.md) | Keeping a standalone install healthy |

Profiles and stages are shared with the library and have their own page:
[Profiles and stages](../guide/profiles.md).
