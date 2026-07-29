# doctor and update

A standalone `sx` lives outside any project, so the two questions it has to
answer for itself are "is this installed and configured the way I think" and
"how do I move to a newer version".

```bash
sx doctor              # how storix is installed, configured, and what it reaches
sx doctor --updates    # the same, plus one question to PyPI
sx update              # upgrade through the package manager that installed it
sx update --check      # report installed and latest, change nothing
```

## `sx doctor`

`sx doctor` reports the version and how it was installed, the Python it runs on,
which provider extras are importable, the config files it found, the profile and
stage in force, the effective provider with **where each value came from**, and
whether `$VISUAL`/`$EDITOR` is set for `sx config edit`.

It asks the network nothing unless you pass `--updates`. That matters when the
thing you are debugging is the network.

This is the first command to run when a session is not talking to what you
expected, because it answers the config question without needing the connection
to work.

## `sx update`

`sx update` drives the package manager that installed storix and never rewrites
its own files.

On a `uv tool` install it runs `uv tool upgrade storix`, printing the command
first. uv's receipt already remembers the extras you asked for, so they survive
the upgrade.

Anywhere else (a virtualenv, an editable checkout, a system install) it refuses
and prints the exact command for that context:

```console
$ sx update
sx: storix runs from a virtualenv install, which sx will not modify.
Upgrade it the way you installed it:
  /path/to/python -m pip install --upgrade storix
```

That refusal is deliberate. A tool that reaches into the environment that owns
it is a tool that can leave you with neither the old version nor the new one.
