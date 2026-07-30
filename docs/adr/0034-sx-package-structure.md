# 34. `sx` becomes a package with one job per module

Status: accepted

## Context

`sx` grew as a subsystem rather than a package. Two files carry almost all of
it:

| file | lines | jobs |
| --- | ---: | --- |
| `cli/app.py` | 1739 | every command, plus the listing helpers they share |
| `cli/shell.py` | 1077 | the REPL, its parser, its completion, its key bindings, its glob expansion, its menu layout |

The seams between those jobs are function boundaries. Nothing marks where one
ends and the next begins, nothing prevents a change to one reaching into
another, and a reader looking for "where does a prompt line become argv" has to
know it is a private function two thirds of the way down a file whose module
docstring describes a REPL.

This is not a hypothetical cost. Recent work in this area repeatedly touched
one job while sitting inside a file that does five others: glob expansion had to
interleave with quote marking, which had to run before tokenizing, which happens
in a function beside the completer. Three pull requests changed `shell.py`
concurrently and had to be told which functions to stay out of, because the file
gave no structural answer.

The next feature to want is command chaining (`&&`, `||`, `;`). That is shell
grammar, and grammar is exactly what should not be added to a file that already
splits redirects in one function and marks quote state in another. Deferring
chaining behind this restructure is recorded in the roadmap.

## Decision

Split the two files by job, leave everything already single-purpose alone, and
change no behavior.

### D1. Commands become a package, one module per help panel

```text
cli/commands/
    __init__.py     imports the modules, in the order the panels appear
    navigate.py     ls pwd cd tree find exists
    read.py         cat stat du url
    write.py        mkdir touch echo edit rm rmdir cp mv
    transfer.py     push pull
    session.py      whereami provision shell
    config.py       the sx config group      (was cli/config_cmds.py)
    maintenance.py  update install uninstall doctor
```

The grouping is the one `sx --help` already shows. A user reading the help and
a contributor reading the tree navigate by the same names, and "which file is
`du` in" has an answer that does not require grep.

`config_cmds.py` moves in and loses its suffix. That name existed only to avoid
colliding with `cli/config.py`, which holds preference loading; a package
solves the collision properly, and `commands/config.py` beside `cli/config.py`
is unambiguous because the paths say which is which.

### D2. The Typer instance moves to `cli/registry.py`

Command modules must reference the app to register on it, and the app must
import the command modules to have them registered. Whichever file holds both
is a cycle.

`cli/registry.py` holds the `typer.Typer()` instance and the help-panel
constants, and imports nothing from the CLI. Command modules import it and keep
their decorators, so a command's name and panel stay next to the function that
implements it. `cli/app.py` imports the registry and the commands package, and
remains the module that `storix.cli.main` and the tests reach for.

The alternative was to strip the decorators and register every command from one
list. That puts the order in a single readable place, but moves each command's
name and panel away from its implementation, and a reader of `navigate.py`
would no longer see which panel `ls` belongs to. Import order in
`commands/__init__.py` is one readable place too, and costs nothing at the call
site.

**Panel order is registration order**, which makes `commands/__init__.py` load
bearing rather than incidental. It says so, and a test asserts the rendered
panel order so a reordered import is caught rather than noticed.

### D3. The shell becomes a package, one module per job

```text
cli/shell/
    __init__.py     start_shell
    loop.py         the REPL, dispatch, built-ins, banner, prompt, help
    parsing.py      quote marking, tokenizing, redirect splitting, escaping
    globbing.py     pattern detection, matching, argv and on-line expansion
    completion.py   the completer and its backend and host sources
    keys.py         key bindings and the exit hint
    layout.py       menu style and float alignment
```

`parsing.py` is the module that makes chaining tractable: one place that owns
turning a typed line into structure, where an operator split can be added
without touching completion or rendering.

The dependency direction is one way. `parsing` knows nothing of the session;
`globbing` uses `parsing` and the session; `completion` and `keys` use both;
`loop` uses all of them and the command tree. Nothing below `loop` imports
`loop`.

### D4. Everything already single-purpose stays put

`render.py`, `icons.py`, `config.py`, `state.py` are cohesive modules of
reasonable size. Moving them would be churn with a rename, and a diff that
touches everything hides the parts that matter.

`state.py` is the one arguable case: it holds session state, layer
construction, and two concurrency helpers. It is left alone here deliberately.
Splitting it is a separate decision on separate evidence, and bundling it into
a structural change that is otherwise mechanical would make this one harder to
review.

### D5. No behavior changes

This is a move. Command names, flags, help text, panel order, output and exit
codes are identical before and after. The test suite is the evidence: it passes
unchanged except for import paths, and any test that had to change its
expectations would mean the refactor did something it should not have.

Private helpers keep their names. Renaming while moving would make the diff
unreviewable, and the names are not what is wrong.

## Consequences

`sx --help` groups commands by panel, and now the source does too. A
contributor adding a command edits one module and one import line. A feature
that belongs to one job stops being able to reach into another by accident,
because the reach becomes an import that shows up in review.

Chaining becomes a change to `parsing.py` rather than a change to a file that
also completes paths and draws menus.

The cost is one large mechanical diff and a churn of import paths in the tests,
which is paid once. Tests that reach for private helpers by module path have to
follow them; that they can is a property of the tests, not of the design.

Nothing here is a public API change. `storix.cli.app.app`, `storix.cli.main`,
and the `sx` entry point are unmoved, and `storix.cli.shell.start_shell` keeps
working because the package exports it.
