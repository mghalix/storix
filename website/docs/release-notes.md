# Release Notes

## [0.5.4] - 2026-07-30

### What's Changed
#### Fixes
* fix(core): bound the glob walk to the depth the pattern can reach by @mghalix in https://github.com/mghalix/storix/pull/87

## [0.5.3] - 2026-07-30

The shell learns to expand patterns and the listing commands learn to take more
than one path, which are the two halves of the same thing: `ls *.md` now works,
at the prompt and on Tab. Alongside them, `echo` gains `-n` and a pipe, and two
quoting defects are fixed - one of which silently split a filename into two
arguments.

Every change here is in `sx`. The library is untouched.

### Added

- **Glob expansion at the prompt** (#79): `ls *.md`, `rm *.tmp` and
  `cat sub/*.md` now expand against the session's backend, which the outer
  shell cannot do because the paths live in remote storage. Expansion happens
  both on Enter and on Tab, where the pattern is replaced on the line with the
  names it matched, the way zsh's `expand-or-complete` does:

  ```console
  / > cat *.md<TAB>
  / > cat a.md b.md with\ space.md
  ```

  A quoted pattern is left alone - '*.md', "*.md" and \*.md all reach the
  command as the literal text. That distinction survives tokenizing, which
  shlex would otherwise erase along with the quotes.

  No match reports the pattern and runs nothing, which is zsh's behavior rather
  than bash's. bash hands the unexpanded pattern to the command, and an object
  store accepts * in a key, so rm *.tmp with no matches could address or
  create a literal *.tmp object.

  Expanded names are relative unless the pattern was absolute, so
  ls *.md in a deep directory does not become a column of full paths. Only
  path positions expand: not the command name, not an option token, and not a
  redirect target, which names a file being written rather than one to be
  found.

- Several paths in the listing commands (#80): ls, du, stat, tree
  and find each take one or more paths, matching what their unix counterparts
  have always done, and what makes an expanded pattern useful for more than one
  match. ls a.txt d1 d2 lists the plain files first as one group, then each
  directory under a name: header, with no header at all for a single
  argument. du, stat and find report per argument in argument order;
  tree prints one rooted tree per argument and a single combined total.

- storix still validates every argument before acting on any of them, so one
  bad path refuses the whole command. That is a deliberate divergence from
  coreutils, which processes operands one at a time and reports failures as it
  goes, and it now holds for several arguments the same way it held for one.

- Batching is preserved: several arguments do not become several serial round
  trips. ls issues one concurrent listing batch, one flattened stat batch
  covering both the -l columns and the sort keys across every block, and one
  batch for the directory glyphs.
- echo -n and writing a file from a pipe (#81): -n suppresses the
  trailing newline, and a pipe writes into storage with no positional argument
  at all:

  some-command | sx echo -f /dest.txt

- The pipe streams rather than buffering, so a large file does not have to fit
  in memory, and its bytes are written verbatim - nothing decodes them and
  nothing renders them. A terminal is never read as data, which is what keeps
  typing echo at the interactive prompt from swallowing the next line. A lone
- stays literal text: unlike cat -, where the operand is a path, echo's
  operand is content, so overloading it would leave no way to print a dash.

### Fixed

- Output that does not end in a newline is marked (#84): echo -n hi and
  cat of a file whose last byte is not a newline both left the next prompt
  welded to the output. Adding a newline unconditionally would have fixed that
  and lost the distinction, so a terminal now gets zsh's % in inverse video,
  then the newline:

  ```console
  / > echo hi
  hi
  / > echo -n hi
  hi%
  ```

- Captured output stays byte-exact: no mark, no added newline, which is the
  entire point of -n. TERM=dumb degrades to a plain %.
- Completed names are escaped by rule, wildcards included (#83): tab
  completion inserted a filename with only an ad hoc set of characters escaped.
  A name containing \* or ? was inserted bare and then re-expanded as a
  pattern, so the command acted on whatever matched rather than the file that
  was picked.

- The wildcards were the reported symptom. A literal backslash was the worse
  defect: back\slash.txt had its backslash silently eaten, and
  weird\ name.txt split into two arguments. Escaping now follows a rule
  rather than a list - every ASCII character that is not alphanumeric or in
  shlex's safe set - which is also what makes escaping the backslash possible
  at all, since a chain of replacements cannot tell an inserted backslash from
  one in the name. Non-ASCII is deliberately left alone: it is syntax to no
  tokenizer, and a backslash before every accent makes the line unreadable.

### Changed

- prompt-toolkit now requires 3.0.24 or newer (#79), raised from 3.0.0.
  Before 3.0.24 a Buffer could not be constructed without a current event
  loop, because loading a history eagerly called asyncio.get_event_loop(),
  which Python 3.12 raises on rather than creating a loop. The shell had needed
  that behavior since it gained a persistent history; only the lower-bounds CI
  job installs the floor, so nothing caught it until now. 3.0.24 is verified
  against every prompt_toolkit API the shell uses.

### Documentation

- Deferred decisions are recorded with the condition that would revisit
  them (#82): a new roadmap section, separate from "Under consideration"
  because these need neither a use case nor a design pass - only sequencing.
  It holds command chaining (&&, ||, ;) and the sx package restructure
  that precedes it. cli/app.py holds every command and cli/shell.py holds
  the REPL, its completion, its key bindings, its redirect parsing and its glob
  expansion, so the seams are function boundaries where they want to be module
  boundaries - and shell grammar is the wrong thing to add to that. Pipes
  between sx commands are named as out of scope.

## [0.5.2] - 2026-07-30

Two things this release is about. Writes can now refuse to clobber a change
they did not see, and the interactive shell behaves like a shell: interrupts
that warn before they leave, completion that finds `LICENSE` from `li`, and
redirection that writes text instead of a terminal rendering. Alongside them,
the first pass of a unix parity audit - `cat` is byte-exact when piped, `ls -l`
works on a file, and a trailing separator means what it means in every shell.

See ADR 0033 for the conditional-write design.

### Added

- **Conditional writes** (#71, #73, ADR 0033): every write was last-write-wins,
  so two writers holding the same path destroyed one another's work with no
  error on either side. `stat` now reports an opaque `version`, and `write`
  takes `if_match`: a version writes only while the stored object still carries
  it, and `IF_MATCH_ABSENT` writes only while nothing exists at the path. The
  store compares and writes as one operation, so there is no window between the
  check and the write, and `PreconditionFailedError` tells a losing writer that
  someone else changed the object rather than that the write failed.

  ```python
  props = fs.stat("/config.toml")
  fs.echo(edited, "/config.toml", if_match=props.version)  # or PreconditionFailedError
  ```

  Two capabilities, not one, because comparing a version and refusing an
  occupied path are separate guarantees that stores offer independently:
  conditional_writes and exclusive_create. Local disk creates exclusively
  through O_EXCL and has no compare-and-write; the opendal-backed stores read
  both flags from the endpoint actually configured rather than assuming them of
  the provider, so an S3-compatible store that takes one and not the other is
  reported accurately. Native ADLS Gen2 carries the precondition on the create
  that completes a file (#73) - not the flush, which happens after the old
  content is already gone.

  Nothing is emulated. The only available emulation is stat, compare, then
  write, which reopens the exact race a precondition exists to close, so a
  backend that cannot be atomic advertises nothing and raises instead.

- sx is an interactive shell again (#70): two consecutive Ctrl+C or Ctrl+D
  presses leave and a single one never does, with the hint rendered under the
  line being typed rather than printed above a fresh prompt, and lapsing after
  a second so a press now and another one later stay two intentions. Ctrl+D
  does nothing while there is text on the line, which is the terminal's own
  rule: it delivers the pending line and reports end of input only on an empty
  one. Tab completion gains [cli] completion_case (default smart: ignore
  case until an uppercase letter is typed), Enter on a highlighted completion
  puts it on the line instead of running it, and the menu is a grid rather than
  a tall column. sx edit opens a remote file in $VISUAL/$EDITOR and writes
  it back, with [cli] editor taking precedence over both. Redirection
  (ls -l > out.txt) writes into the backend.

- One sort vocabulary for ls and tree (#76): --sort name|time|size
  with -r/--reverse on both, where ls had time and reverse but no size
  and tree had all three keys but no reverse. ls keeps -t as the
  coreutils shorthand. A size sort reuses the stats a listing already carries,
  so ls -l --sort size costs no extra request; directories sort below every
  file, since neither command renders a size for one.

- cd - (#69): returns to the previous directory and echoes where it
  landed, marked with the jump glyph, because you did not name the destination.

- StorixPath.named_as_directory (#75): reports whether a path was written
  with a trailing separator, which a normalized path otherwise forgets. This is
  what lets a StorixPath destination be held to the same assertion a string
  is, and what makes maybe_file() agree with is_file_approx().

### Fixed

- cat is byte-exact when piped, and no longer buffers the whole object
  (#66): file bytes went through rich.console.print, which hard-wrapped at 80
  columns and turned tabs into spaces, so a piped file was not the file. A 10 MB
  read took 35s and 230 MB of resident memory, and a 400 MB file had not
  finished in two minutes, because fs.cat() materialized the object while the
  core's streaming path went unused. Bytes now go straight to
  sys.stdout.buffer.

- sx ls -l FILE (#66) exited with path '/f/f' does not exist: the long
  and time-sorted paths rebuilt each entry's path from the listing base, which
  holds only when the base is the directory being listed. Listing a file yields
  one entry whose path is the base itself, so the join appended the file's own
  name to it.

- echo prints its argument literally (#66): markup was eaten
  ([bold]hi[/bold] printed as hi) and a[/]b raised a traceback, because
  the text went through rich's markup parser.

- Listings collate like ls and eza (#66): a byte-order key filed every
  capitalized name above every lowercase one, so Zebra.txt sorted above
  a.txt. Completions follow the order a shell's own completion list shows,
  where leading punctuation does not file a package's dunder modules ahead of
  every letter.

- tree FILE counts a file as a file (#66), rather than reporting
  1 directory, 0 files.

- Errors never leak host paths (#66): cp a.txt a.txt reported
  PosixPath('/tmp/sxx/a.txt') and ... are the same file, exposing the
  filesystem behind the session.

- A trailing separator asserts a directory (#74, #75): cp a.txt nodir/
  exited 0 and created a file called nodir, putting content at a path
  nobody asked for and reporting success. The separator is how every shell says
  "this name is a directory", so the destination is now a directory or an
  error, quoted as it was typed. The assertion survives for a StorixPath
  destination too, and a path derived from one - the parent of nodir/x -
  correctly asserts nothing.

- sx update could not cross a pin it created itself (#70): sx install
  pins to the running version every time it adds an extra, uv records that pin
  in its receipt, and uv tool upgrade refuses to cross it. Adding a provider
  backend silently and permanently disabled self-update. It now reinstalls at
  @latest carrying the receipt's extras, with --refresh-package so a
  release published inside PyPI's ten-minute index cache is visible rather than
  reported as "nothing to upgrade".

- Redirection writes text, not a rendering (#70): ls -l > out.txt wrote
  ANSI escapes and trailing column padding into the file. The console is built
  at import time and rich resolves its color system once there, so under a
  terminal it kept emitting escapes into a file that was never one; replacing
  stdout does not undo that decision, and no_color removes color while
  leaving dim and bold.

- The interactive shell keeps its history and shows its real command set
  (#66): history died with the session, and help advertised a deprecated
  alias while omitting find, whereami, doctor and config.

- StorixPath('a.txt/').maybe_file() (#75) returned True. The
  trailing-separator check ran after the argument had been converted to a pure
  path, which is the conversion that removes one, so the branch was unreachable
  for exactly the shape it existed to judge.

### Changed

- sx update <VERSION> moves in either direction (#70). A backward move
  names itself as a downgrade and notes that an older storix can reject
  configuration keys this one accepts; a version that cannot be ordered against
  the installed one is left unremarked rather than guessed at. There is no
  sx pin: a pin records standing intent, a self-contained tool has no project
  file to record it in, and a pin that made bare sx update refuse to move
  would silently stop delivering fixes while the tool continued to look healthy.

- Nothing in the prompt paints a background (#70). The defaults were opaque
  throughout - the completion menu a grey slab, its meta rows two more greys,
  the scrollbar two, the exit hint a full-width reversed bar - which covers a
  terminal configured to be transparent. A selected entry reverses rather than
  choosing a pair, so the highlight follows both the terminal theme and the type
  color a directory already carries.

## [0.5.1] - 2026-07-29

A release about `sx` telling the truth about itself. `sx doctor` reported every
provider extra as installed whether or not it was, naming a provider whose
extra was missing asked for credentials instead on Azure, and the only way to
add a backend after installing was to rerun the installer with different
flags. Now `sx install s3` adds one, `sx uninstall s3` removes it, and
`doctor` answers from what this environment can actually import. See ADR 0031
D15.

### Added

- **`sx install` and `sx uninstall`** (#62, ADR 0031 D15): provider extras are
no longer only an install-time choice. `sx install s3`, `sx install
azure,gcs`, `sx uninstall gcs`. Extras are cumulative: `uv tool install`
replaces a tool's requirement rather than amending it, so the extras already
present are read back from uv's receipt and restated, and adding `s3` never
drops `azure`. The rewrite pins the running version, because adding a
backend is not a moment to also move versions - that is `sx update`, done
deliberately. Legal names come from the distribution's own `Provides-Extra`
metadata, so a typo is refused before uv spends a resolve on it. `cli`
cannot be uninstalled - an `sx` without it cannot run, and so cannot put it
back - and the refusal names `uv tool uninstall storix` for the reader who
wanted that instead. Like `sx update`, it refuses any installation it did
not create, printing the manual command for that context. The missing-extra
remedy becomes `sx install s3` on a uv tool install.

### Fixed

- **`sx doctor` reported every provider extra as installed** (#61): it asked
`available_providers()`, which is the builder registry - the names
`get_storage` accepts, not what this environment can import. A
`storix[cli]`-only install listed `azure`, `gcs`, `local` and `s3` all as
present with none of their engines there, which is the opposite of what the
command exists for. It now probes the modules each extra installs.
- **A missing Azure extra asked for credentials instead** (#61): `s3` and
`gcs` import their engine before validating configuration, so an absent
extra surfaced as one; `azure` validated first, so the same install answered
`sx -p azure` with `missing configuration: container, account_name,
credential` - not advice a reader with no SDK can act on. The check now runs
once in `get_storage`, at the point every builder routes through, so the
order no longer depends on the statement order inside each builder.
**Library callers see this too**: `get_storage("azure")` without the extra
now raises `ModuleNotFoundError`, which is what `get_storage("s3")` already
did. Providers registered through `register_backend` bring their own
dependencies and are never gated.
- **`sx ls -l` on a single file** (#63): it died with `path '/a.txt/a.txt'
does not exist`. The long and `-t` paths rebuilt each entry's path as
`base / name`, which holds only when `base` is the directory being listed;
listing a file yields one entry whose path is `base` itself, so the join
appended the file's own name to it. Every other batched-stat caller already
passed the path the port had returned.
- **`install.sh --version` and `install.ps1 -Version`** (#61): both assembled
`storix==0.5.0[cli]`, which is not a PEP 508 requirement - extras precede
the version specifier - so pinning a version failed at the resolver with no
local symptom. An automation test now runs the installer against a stub `uv`
and asserts the argv it builds.

### Documentation

- **Installation leads with `sx install`** (#64): the page opened with a bare
`curl | sh` and then four more curl lines carrying `--with`, `--all`,
`--version` and `--help`, which predated any way to add a backend
afterwards. Install once, then pick backends with `sx install`. The
install-time selections moved into a collapsible note, kept rather than
dropped because a scripted or unattended install has no second command to
run.
- **The sx CLI has its own section** (#59): `guide/cli.md` had grown to 627
lines and 17 headings covering eight separate jobs, filed inside Guide
between the library pages, so someone who came for the CLI had to find it
inside the library documentation. It is now a top-level section, one page
per job.
- **The documentation uses the full viewport** (#58): Material caps every
`.md-grid` element at 61rem, so header, navigation, prose and table of
contents all sat in one narrow column marooned in the middle of a large
screen. Above the desktop breakpoint the grid spans the viewport, with the
prose column capped at a readable 42rem and centred between them.
- **One stream, three backends** (#57): a runnable showcase streaming FFmpeg
stdout to local storage, Azure Blob Storage and Cloudflare R2 through one
session and one stream, with its own page and poster.

## [0.5.0] - 2026-07-25

`sx` becomes a standalone tool: one command to install it on any operating
system, configuration it can find without a checkout, named profiles with
stage overlays shared with the library, and `sx config` / `sx doctor` to see
what any of it resolves to. Alongside it, a single large file no longer
transfers at one connection's speed - `download` fetches several byte ranges
of the same file concurrently, measured at 2.1x on a 200 MiB pull from Azure.

Two breaking changes, both in the zero-configuration path. See ADR 0031 for
the configuration and installation design, ADR 0032 for ranged reads.

### Changed (breaking)

- **`sx` with no configuration anchors at the directory you ran it from**
  (#53), instead of `~/.storix`. A unix user running an exploration CLI
  expects `sx ls` to list where they stand. Only the nothing-configured case
  changes: a base from a flag, `--set`, a profile or its stage,
  `STORIX_LOCAL_BASE`, `.env`, or a config file still decides, and the CLI
  asks the loader's own provenance rather than guessing. **The library
  default is unchanged**: `get_storage()` with zero configuration is still
  `~/.storix`, because library code writing into an application's working
  directory is a hazard, while a human at a prompt is the one case where the
  cwd is the honest default (ADR 0009 stands).

  ```bash
  # to keep the old behavior
  export STORIX_LOCAL_BASE=~/.storix
  ```

  ```toml
  # or, per project
  [local]
  base = "~/.storix"
  ```

- **A profile pinned in a config file no longer steers `get_storage()`**
  (#54). A `profile = "media"` key, and `STORIX_PROFILE`, are `sx`
  conveniences; honoring them in the library meant a personal file could
  point an application's session at another account, and that
  `get_storage("s3")` beside `get_storage("azure")` - the shape every
  migration and every composite filesystem takes - failed on whichever
  machine happened to carry a pin. The library selects a profile only when
  the call asks. Migration is mechanical:

  ```python
  # was, with `profile = "media"` in a config file
  fs = get_storage()
  # now
  fs = get_storage(profile="media")
  ```

  This lands in the same release as the pin itself, so no published version
  ever behaved the other way.

### Added

- **Parallel range reads** (#40, ADR 0032): `Storix.download()` fetches
  several byte ranges of one file concurrently and writes each at its offset,
  so a single large file is no longer bounded by one connection's round
  trips. Measured on a 200 MiB file to Azure over one home connection, sha256
  verified: 61.53s at one range, 25.51s at eight - **2.1x**, peak RSS 173 MB.
  New port method `read_range(path, *, offset, length, chunk_size=None)`, with
  `BackendBase` emulating it over `read_stream` so every backend (including a
  third-party one) returns correct bytes; local, memory, Azure ADLS, and the
  opendal-backed stores override it natively and advertise the new
  `ranged_reads` capability. Like `bulk_listing`, it gates a fast path and
  never raises. `ranges=1` forces a single stream, per call or globally with
  `STORIX_MAX_TRANSFER_RANGES=1`; every range is a separate request, so the
  speed is bought with transaction count.
- **Provider settings in configuration files** (#47, ADR 0031 D3): one loader,
  shared by the library and `sx`, reads `~/.config/storix/config.toml`
  (`%APPDATA%\storix\config.toml` on Windows), a project `storix.toml`, or
  `[tool.storix]` in `pyproject.toml`, and records which source supplied each
  effective field. Non-secret coordinates (bucket, container, account name,
  region, endpoint, base, root) are project facts and now belong in project
  files; secrets stay out, with `credential = "env:VAR"` naming a variable
  instead of holding one. `sx` gains coordinate flags (`--base`, `--bucket`,
  `--container`, ...), a repeatable `--set provider.field=value`, and
  `--version`.
- **Named profiles and stage overlays** (#48, #49, ADR 0031 D8/D9): a profile
  is a named connection - one provider plus its settings - and a stage
  overlays what differs between deployments, typically a separate account and
  its own credential per stage. `get_storage(profile="ingest",
  environment="prod")` and `sx --profile ingest --env prod`. A profile layers
  over that provider's own table, so settings shared by every profile on a
  backend are written once. A profile names its own provider; a stage can
  change settings but never the provider.
- **`sx config`** (#50, ADR 0031 D10): `path`, `sources`, `show`, `get`,
  `set`, `unset`, `init`, `validate`, `edit`, `profiles`. Writes round-trip
  through `tomlkit` (comments and layout survive), validate against the same
  models a loaded file gets, and land atomically. Secrets are redacted in
  every read command and refused on write in project scope. `--effective` on
  `show` and `get` reports the session that would actually run, each field
  with its value and the layer that supplied it.
- **`sx doctor` and `sx update`** (#52, ADR 0031 D11/D12): `doctor` reports
  version, installation method, importable extras, discovered config files,
  the selected profile and stage, and where each effective field comes from,
  touching the network only under `--updates`. `update` drives the package
  manager that installed storix - `uv tool upgrade storix`, extras preserved
  from uv's receipt - and refuses with exit 2 anywhere else rather than
  rewriting an environment it did not create.
- **`sx whereami`** (#54): what this session is connected to - backend,
  profile and stage, root URI, cwd, home, layers - without opening a
  connection. The shell banner names the profile too. `sx provider` remains as
  a hidden alias.
- **A one-command install, on every operating system** (#51, ADR 0031 D13):

  ```bash
  curl -LsSf https://storix.mghalix.com/install.sh | sh
  ```

  ```powershell
  powershell -c "irm https://storix.mghalix.com/install.ps1 | iex"
  ```

  Thin wrappers over `uv tool install` (`--with azure,s3`, `--all`,
  `--version`, `--help`): no root, no credentials, no configuration written,
  no shell startup files edited. CI runs each script for real on its own
  operating system.
- **The same transfer knobs on every provider** (#43): `read_chunk_size` and
  `write_chunk_size` for all backends, plus `read_prefetch_size` for those
  that fetch over the network, as `STORIX_<PROVIDER>_*` or config-file keys.
  Local disk deliberately has no prefetch: a knob that silently does nothing
  is worse than one that is absent. The opendal-backed stores now pass their
  sizes to the engine on every streaming read.
- **Readable transfer sizes** (#46): `STORIX_AZURE_READ_PREFETCH_SIZE=32MiB`,
  `get_storage("s3", read_chunk_size="8MiB")`. Parsed by `pydantic.ByteSize`,
  so `8MiB` is 8,388,608 and `8MB` is 8,000,000 - not synonyms. Plain byte
  counts still work.
- **`storix.toml.example`** (#49): a complete annotated reference for every
  key, tracked in the repository and held to the models by a test.

### Fixed

- **Ctrl+C during a transfer stops the transfer** (#42): cancelling returned
  the prompt but left the workers running, because a thread blocked in a
  socket read cannot be interrupted and `KeyboardInterrupt` only reaches the
  main thread. SIGINT now sets an event that the per-chunk progress sink
  raises on, so every stream unwinds at its next chunk boundary, queued files
  never start, and a half-written local file is removed rather than left
  looking complete. The command reports it and exits `130`; a second Ctrl+C
  restores the default handler.
- **`zensical` is no longer a runtime dependency** (#44): the documentation
  site generator sat in `[project].dependencies`, so every `pip install
  storix` pulled it and its eight transitive packages - 10 of 22 packages in a
  bare install. Published metadata is immutable, so every release up to 0.4.9
  keeps it; this fixes it going forward. An automation test now pins
  `[project].dependencies`.
- **A download sink is fast-pathed only when its bytes reach its descriptor
  unchanged** (#45): the `os.pwrite` path was gated on `seekable()` and
  `fileno()`, and `gzip.GzipFile` answers True and hands back the *underlying*
  descriptor - so a parallel download would have written raw bytes at range
  offsets into a compressed file. Now an explicit allowlist. `dest` also
  widens to a `BinarySink` protocol, so `GzipFile` and `SpooledTemporaryFile`
  type-check; a text stream still cannot qualify, because a range boundary can
  fall inside a multi-byte character.
- **`sx --help` at the declared dependency floor** (#52): typer 0.13 through
  0.15 call click's `Parameter.make_metavar()` without the `ctx` click 8.2
  made required, and the `cli` extra already required click 8.2, so at the
  minimum versions any `--help` raised `TypeError`. The floor is now
  `typer>=0.16.0`.
- **The interactive shell keeps the flags it was started with** (#54): every
  line typed in the shell re-enters the root callback carrying none of them,
  and the session was re-derived from what it saw - so `sx --profile prod`
  listed whatever a config file pinned, from the first command onward, and a
  startup `--base`, `--cache` or `--sandbox` was dropped the same way.
- **Configuration views report the selection they were given** (#54):
  `sx config show`, `show --effective` and `doctor` re-resolved the selection
  instead of reading it, so `--profile` and `--env` were dropped; `doctor`
  computed provenance without the profile, printing `<- default` for every
  field a profile supplies. A stage overlay is now reported apart from the
  profile under it (`<- environment` against `<- profile`).
- **Reading configuration no longer resolves a credential** (#54): naming a
  profile's provider went through the full resolution, so an `env:` reference
  to an unexported variable took down `sx config profiles`, `sx doctor`, and
  anything else that needed only the backend's name - exactly when those
  commands are reached for.
- **`-p` on a merely pinned profile** (#54) no longer errors. A pin is a
  default, and one line in a personal file should not lock the CLI to one
  backend. `--profile` and a conflicting `-p` together still refuse: there the
  user said two things.
- **Error messages naming a TOML table** (#54): every message went through
  rich markup, so a `[table]` name in one was parsed as a style tag and
  printed as nothing - worst in the messages that name the table to go and
  fix. A `[environment]` table inside a profile now also names the spelling
  stages take.

### Documentation

- **Profiles and stages** (#54, #55): a guide page of its own, because
  profiles were written up inside the CLI guide where a reader using storix as
  a library never looks, and `get_storage(profile=, environment=)` is the same
  feature. Covers stages carrying a separate account and credential each,
  selection order, sharing settings between profiles, and how to see what is
  in force.
- **Installation** (#51): the `uv tool` matrix, both one-liners, the
  download-inspect-execute alternative, and `uv tool uninstall storix`.
- **Configure from settings** and **Tune transfers** gain the config-file
  sources, the precedence order, the secret policy, the per-provider knob
  table, and a "turning it off" section for ranged downloads with the request
  cost stated.
- `sx --help` groups its commands (navigate, read, write, transfer, session
  and setup) and its options (connection, profile, session, inspect), and its
  epilog names the commands that explain a session.

### Internal

- The test suite no longer reads the developer's real `~/.config/storix`: an
  autouse fixture points `XDG_CONFIG_HOME` at an empty directory and clears
  `STORIX_*`. This was latent from #47 onward and passed in CI while failing
  locally.
- `reset_session()` clears the whole process-wide CLI session between tests,
  not just its filesystem.
- CI gains an `Installers` matrix job that runs each installer for real on
  ubuntu and windows runners, and `zizmor` moves to 1.28.0 (1.27.0 was yanked,
  GHSA-f42p-wjw5-97qh).

## [0.4.9] - 2026-07-24

A transfer correctness and cost release. Cancelling a bulk `push`/`pull` now
takes effect immediately instead of hanging the shell on exit, uploads no
longer walk a binary file newline by newline, and a bulk transfer's resident
memory is bounded by what it actually needs rather than by what the allocator
felt like keeping. Measured end to end on a real Azure (ADLS) container: a 480
MiB pull peaked at 273 MB instead of 814 MB, and a 192 MiB push spent 2.49s of
CPU instead of 5.85s, both at equal or better wall time.

### Fixed

- **Ctrl+C during a transfer aborts now** (#38): `concurrent` no longer joins
  in-flight thunks while tearing down, so the first interrupt returns to the
  prompt and the queued files never start. `sx` then exits without waiting on
  the abandoned transfer threads, which is what left `bye` hanging for minutes
  and printed an `Exception ignored on threading shutdown` traceback on a second
  Ctrl+C.
- **Binary uploads are read by size, not by line** (#39): `ensure_chunks`
  checked for an iterable before a readable, and a binary file object is
  iterable by newline-delimited lines. In the sync flavor - the one `sx` runs -
  every upload was pulled in newline-sized pieces (about 250 bytes on random
  data), with one progress event per piece, and a file containing no newline was
  materialized whole. Readables now go through `read()` at 1 MiB. Uploads of
  incompressible data (video, archives) are substantially faster and use a
  fraction of the CPU.

### Changed

- **Azure's initial download request is 8 MiB, was 32 MiB** (#39): it is the one
  buffer a download holds whole before yielding a chunk, so a concurrent pull
  multiplies it by the number of streams. The SDK re-chunks it to 4 MiB
  immediately, so the extra was resident memory and nothing else. A lone stream
  now pays one range request per 8 MiB, about 14 percent slower on a single
  large file over a high-latency link; restore the old behavior per session with
  `STORIX_AZURE_READ_PREFETCH_SIZE=33554432` or
  `AzureBackend(read_prefetch_size=...)`.
- **`sx` returns freed transfer buffers to the operating system** (#39): the CLI
  pins glibc's mmap threshold at startup, so multi-megabyte chunk buffers are
  released on free instead of being retained in per-thread allocator arenas. A
  finished bulk push previously sat at 931 MB resident with about 30 MB of live
  Python objects behind it. No-op on any other libc, and deliberately not done
  on library import: a library has no business setting a process-wide allocator
  policy for your application.

### Documentation

- **Tune transfers** (#39): a new recipe covering the memory model (streams in
  flight times per-stream buffers), the measured prefetch curve, which
  `STORIX_*` variable moves what, the request-count and rate-limit cost of
  smaller chunks, and the transfer limits that still stand.

### Internal

- `benchmarks/` is now `bench/`, linted and formatted with the rest of the
  repository, and gains `bench/transfer.py`: bulk push/pull wall time,
  throughput, peak and retained RSS at a given fan-out, reproducible against a
  latency-injecting local backend or real against Azure.

## [0.4.8] - 2026-07-22

A performance release: cloud listing and traversal drop from N serial round
trips to one bulk request or bounded concurrent batches, with unix ordering and
streaming output preserved. Measured on a real Azure (ADLS) container, cold
cache: `sx ls` went from ~2-3s on v0.4.7 to 0.35s (0.42s with icons). It also
sharpens `sx` transfer setup - `push` scaffolds its remote destination, a
missing bucket or container now fails with one actionable line instead of a raw
provider dump - and adds explicit storage-root provisioning where a backend can
create its own root.

### Added

- **Bulk emptiness** (#28): backends that can list a subtree in one request
  advertise the new `bulk_listing` capability; `Storix.empty_children` derives a
  whole listing's folder emptiness from a single recursive listing (bounded by a
  10,000-key limit with a silent portable fallback). `sx ls` folder icons ride
  it. New port method `list_tree`.
- **`sx --debug`** (#32): a global flag that prints the full provider traceback
  (original exception, request IDs, HTTP context, nested causes) behind the
  concise error.
- **Storage-root provisioning** (#34, ADR 0030): a new optional `provisioning`
  capability with `sx provision` and `fs.provision()` creates a missing storage
  root idempotently. Honest scope - real only where the backend engine can do
  it: ADLS creates a missing filesystem; local and memory report
  already-present; the opendal backends (S3/R2/GCS/Azure Blob) are data-plane
  only and report it unsupported, pointing at your provider's own tooling
  (`aws s3 mb`, `gcloud storage buckets create`, `az storage container
  create`). `sx mkdir` never creates a root.

### Changed

- **Concurrent recursive traversal** (#29, ADR 0028): `walk` (and with it
  `find`, `glob`, `du`, `sx tree`) now fetches directory listings level-wise
  through bounded concurrent batches, so wide remote trees are bounded by
  per-level latency instead of the sum of every directory latency. `walk` gains
  an additive `max_depth` keyword; excluded levels cost zero backend calls
  (`sx tree -L` rides it).
- **Fewer listing round trips** (#30): the opendal-engine backends
  (S3/GCS/Azure Blob) list first and stat only to disambiguate an empty result,
  so a non-empty `list_dir` is 1 request instead of 3. The native Azure (ADLS)
  backend drops to exactly 1 request for every `list_dir`, from 2.
- **Concurrent push/pull** (#31): `sx push`/`sx pull` transfer directory files
  through bounded concurrent batches instead of a serial loop, create each
  unique parent directory once instead of once per file, and the progress bar
  tallies interleaved events correctly (a per-path cumulative sum) so it
  advances monotonically.
- **`sx push` scaffolds its destination** (#32): single-file `sx push` now
  creates missing destination parents inside the storage root before
  transferring, matching directory push, so `sx push ./video.mp4
  /demos/video.mp4` works with no prior `mkdir`. (`push` never creates the
  bucket or container itself.)
- **Concise missing-storage-root errors** (#32): a missing S3/R2 bucket, Azure
  Blob container, or ADLS Gen2 filesystem now fails with one actionable line
  (`configured s3 bucket 'media' does not exist`) via the new typed
  `StorageRootNotFoundError`, instead of a raw provider/OpenDAL diagnostic dump.

### Fixed

- **Unix ordering and streaming restored** (#33): `walk` emits exact depth-first
  order (byte-identical to v0.4.7) over the new concurrent fetching, so
  `find`/`glob`/`du` mirror the old order, and `sx tree`/`sx find` stream output
  progressively instead of waiting for the full traversal. `order='level'`
  remains an opt-in for sibling-contiguous consumption.
- **Missing container/filesystem no longer misreported** (#32): a missing Azure
  Blob container or ADLS Gen2 filesystem surfaced as `PathNotFoundError: path
  '/' does not exist`; it now reports the missing storage root correctly.
- **Directory `push` surfaces real errors** (#32): a failed remote `mkdir`
  during directory push (permission denied, an intermediate file, a missing
  bucket) now fails loudly instead of being silently swallowed.
- **Shell completion side**: in the interactive `sx` shell, tab-completing the
  second argument of `push` and `pull` completed from the wrong side (local vs
  remote); it now completes the correct namespace.

### Notes

- **Compatibility**: Fully backward-compatible with v0.4.7. `walk` ordering is unchanged; `max_depth`
  and `order` are additive keyword-only arguments; the `bulk_listing` and
  provisioning capabilities plus the `list_tree` and `provision` port methods
  default off (with raising `BackendBase` defaults), so custom backends
  subclassing `BackendBase` keep working and all additions are invisible to
  existing callers. No API removals. One failure-path nuance: a missing Azure Blob
  container or ADLS Gen2 filesystem now raises `StorageRootNotFoundError` (a
  `ConfigurationError`) where it previously raised `PathNotFoundError` - a
  corrected misdiagnosis, not a change to any success path. PATCH under ADR 0021;
  pin `storix>=0.4,<0.5`.



## [0.4.7] - 2026-07-21

Storix 0.4.7 brings major CLI usability and performance upgrades to `sx`, featuring
complete eza-grade icon coverage, rich `ls -l` long listings, custom subcommand aliases in
`storix.toml`, recursive `push` and `pull` transfer commands and context-aware shell completions.

### Added

- **Full eza Icon Catalog**: Integrated 100% of eza's icon catalog (623 file extensions,
270 exact filename mappings, and modeline definitions) into `sx` with Nerd Font icon
rendering and aligned file classification.
- **Rich `ls -l` Long Listing**: Formats Unix/eza style file permissions/kind, human-
readable byte sizes, modification date/time, and icon-prefixed labels across single and
multi-column terminal views.
- **Subcommand Aliases (`[cli.alias]` / `[cli.aliases]`)**: Configure custom CLI shortcuts
in `storix.toml`, `.storix.toml`, or `pyproject.toml` (e.g. `l = "ls -l"`, `ll = "ls -la"`,
`lt = "tree --level=2"`), automatically expanded in both `sx` commands and the interactive
REPL shell.
- **`push` and `pull` Commands**: Transfer single files or entire directory trees
recursively between host disk and remote storage backends (`sx push <local> [remote]` and
`sx pull <remote> [local]`).

### Changed

- **Context-Aware Shell Completions**: `sx` shell tab completion dynamically detects
argument context—completing local host disk paths for `push <1>` and `pull <2>`, and remote
backend paths for `push <2>`, `pull <1>`, `cd`, `ls`, and all other backend operations.
- **Path & Space Handling**: Tilde (`~`) home shortcuts and spaces/special characters in
local and remote paths are automatically expanded and backslash-escaped during shell tab
completion.

### Fixed

- **Monotonic Transfer Progress Bar**: Accumulated byte deltas across multi-file directory
transfers so the Rich progress bar advances steadily from 0% to 100% without resetting per
file stream.

### Removed

- **Legacy `upload` and `download` commands**: Replaced completely by `push` and `pull`.

## [0.4.6] - 2026-07-20

Storix now has a clearer public entry point for developers exploring typed,
streaming storage workflows. This release focuses on documentation, examples,
package discovery, and community participation. SDK runtime behavior is
unchanged.

### Added

* A contribution guide and structured GitHub forms for bug reports and
  workflow discussions.
* Runnable streaming recipes demonstrating subprocess output written
  incrementally through Storix, including an optional yt-dlp integration.
* Clear maintainer priorities and community-driven workflow guidance in the
  public roadmap.

### Changed

* The README and documentation homepage now present Storix as an async-first,
  streaming-first storage SDK across local storage, Azure, S3, and GCS.
* Package metadata, keywords, homepage links, and project URLs now match the
  current documentation and provider support.
* Community guidance now directs open-ended workflows and API ideas to GitHub
  Discussions, while confirmed bugs remain in GitHub Issues.
* FastAPI examples now distinguish chunked `UploadFile` reads from raw request
  body streaming and avoid implying that multipart uploads bypass framework
  spooling.

### Fixed

* The Workflows discussion category now loads its structured workflow form
  correctly.

## [0.4.5] - 2026-07-18

Recursive search is now a first-class core capability, with a faster and more
capable Unix-style CLI built on the same primitives.

### Added

- `Storix.walk` lazily traverses directory trees in top-down or bottom-up
  order, while `Storix.find` filters by glob and entry kind and `Storix.glob`
  provides pathlib-style recursive matching.
- `find(kind=...)` accepts the typed `PathKindStr` literals `file` and
  `directory` as well as `PathKind` values.
- `sx find` exposes recursive search from the command line.
- `sx du` gains summary, per-file, and maximum-depth modes, and `sx tree` gains
  depth limits, long output, and sorting by name, time, or size.
- A listing-and-searching recipe and reproducible listing benchmarks document
  the new APIs and their performance model.

### Changed

- `sx ls` and `sx tree` batch per-entry metadata lookups through Storix's
  concurrency helper, avoiding one serial network round trip per entry on
  remote backends.

### Fixed

- `find` and `glob` can include hidden entries when `all=True`.
- `sx tree -l` no longer leaks dim styling from metadata columns into names.

### Removed

- The unreferenced and unexported legacy `src/storix/core` prototype is gone;
  the supported `Storix` methods now own recursive traversal. This does not
  remove a public API.

## [0.4.4] - 2026-07-18

Rich recursive-listing groundwork, Azure Blob URL parity, and real concurrency
in the sync flavor. Three backward-compatible features. See ADRs 0023-0025.

### Added

- `Storix.scandir` yields a directory's entries lazily as rich `DirEntry`
  objects (name, absolute path, `kind`, and any size the listing carried for
  free), after `os.scandir`; `iterdir` is its lazy-names sibling (after
  `pathlib`); `is_empty` answers whether a directory holds anything in one
  round trip (hidden entries counted, so a dotfile-only directory is not
  empty). `ls` is reimplemented over `scandir` with unchanged behavior, so the
  kind/size the port already produces reaches consumers without a stat per
  entry. `DirEntry` is exported from `storix` and `storix.aio`. ADR 0023.
- `AzureBlobBackend.url()` mints a read SAS from an account key locally
  (`generate_blob_sas`, pure HMAC, no request), 1:1 with `AzureBackend` (ADLS):
  the same code and credential now produce a URL on any Azure account kind.
  `presigned_urls` is advertised when the credential can sign, and
  `azure-storage-blob` joins the lean `azblob` extra so it works there too.
  ADR 0024.

### Changed

- The sync flavor's multi-target operations (`cat`, `touch`, `mkdir`, `rm`,
  `mv`, `cp`, and `du`'s subtree walk) now run concurrently. A thunk-based
  `concurrent` helper dispatches the fan-out to a bounded `ThreadPoolExecutor`
  in sync and to `asyncio.gather` in async; because the backends do
  GIL-releasing blocking I/O, the sync threads give genuine I/O concurrency. So
  `sx du`/`cp`/`rm` on a wide cloud tree parallelize like the async API. The
  async path is unchanged, error semantics stay unwrapped (the storix taxonomy
  survives), and codegen is untouched. ADR 0025.
- The `sx` CLI consumes the new core listing: its `list_entries` and
  `has_children` re-implementations are gone in favor of `scandir` and
  `is_empty`, so listing semantics live in one place.

## [0.4.3] - 2026-07-17

The `sx` revamp: completion, progress, icons, unix-consistent output, and a
persistent config file. Library code is untouched; every change lives in the
CLI. See ADR 0022.

### Added

- `Storix.layers` reports the active layers, outermost first, and
  `Storix.base_backend` walks past them to the real provider. Reading the
  stack is a legitimate need - naming what wraps a session, recording it in an
  audit trail - and the alternative was duck-typing on a layer's private
  `_inner`, which is what the CLI had been doing. Composition stays with
  `with_layer` / `without_layer`; layers are identified structurally, so
  custom ones appear beside the built-ins.
- The interactive shell runs on `prompt_toolkit`: Tab completes command names
  (with their descriptions) and remote paths, directories complete with a
  trailing slash, and arrow-key history works. Completion sources a live
  listing, so an active cache layer makes repeats instant.
- `upload` and `download` render a live progress bar driven by the
  `ObservabilityLayer`. `sx` owns the total (the local file's size for an
  upload, `stat` for a download) and the layer supplies transferred bytes, per
  ADR 0019.
- Listings decorate entries with Nerd Font icons, the glyph set eza and
  nvim-web-devicons draw from, with per-category colors. The table ships as
  package data (`storix/cli/data/icons.toml`), so retheming is a data edit.
  Icons disable automatically when output is not a terminal.
- A persistent config file for CLI preferences and an always-on layer stack
  (ADR 0022). Precedence, strongest first: flags, the nearest project config
  (`storix.toml` > `.storix.toml` > `pyproject.toml [tool.storix.cli]`, found
  by walking upward), `STORIX_CLI_*` environment variables,
  `~/.config/storix/config.toml`, defaults. The ordered `[[cli.layers]]` array
  resolves the curated CLI layer set (`cache`, `sandbox`) by name, completing
  the DSL ADR 0015 deferred. Unknown keys, and connection settings put in the
  CLI table by mistake, exit with the correct home named rather than being
  silently ignored.
- `ls -t` (sort by modification time) and `-r` (reverse); `tree -a`; `du -h`;
  `--icons/--no-icons`.
- CLI preferences `provider` (which backend `sx` opens by default, overriding
  `STORIX_PROVIDER` for the CLI only, with `-p` still winning) and
  `dir_contents` (whether flat listings check emptiness).
- `r2` and `minio` install extras, aliases for `s3`, whose API both stores
  speak. Installing for the store you use no longer requires knowing that.
- The configured `[[cli.layers]]` stack covers every built-in layer a config
  file can express: `cache`, `sandbox`, `url`, and `metadata`. The two
  capability-backfilling layers go through `with_layer_missing`, so one config
  yields a native SAS URL where the backend has one and a `data:` URL where it
  does not.

### Changed

- `du -h` and `ls -l` humanize sizes in binary units with coreutils'
  single-letter suffixes (`165M`), matching `du -h` / `numfmt --to=iec
  --round=up` exactly, including the boundary where rounding promotes the unit.
- `tree` closes with unix tree's `N directories, M files` summary, counts the
  root directory as tree does, and reads entry kinds from the listing instead
  of a stat per child (one request per level).
- `upload` detects a content type (extension first, else sniffing the head)
  and sets it on backends advertising the `content_type` capability. Uploads
  previously left Azure to default every blob to `application/octet-stream`.
- `upload` and `download` stream instead of materializing the whole file, so a
  transfer larger than memory succeeds.
- `du` echoes the path as given rather than the resolved one, like unix `du`.
- The CLI package is split by concern: `app` (commands), `state` (session and
  layer-stack access), `render` (consoles, icons, sizes), `config`
  (preferences), `shell` (REPL), `data/` (assets).
- The `cli` extra gained `prompt-toolkit`; the launcher's missing-extra guard
  covers it.

### Fixed

- Directory icons tell the truth about emptiness. Flat listings now check
  (`dir_contents`, on by default), so an empty folder reads as empty and a
  populated one as populated, rather than every directory sharing one glyph.
  `tree` already knew, for free.
- `sx` verifies a sandbox root before jailing the session. A missing root
  used to surface later, correctly rescoped and unreadable, as
  `PathNotFoundError: path '/' does not exist` - inside the jail the missing
  root *is* `/`. The check names the real root and the provider while it
  still can.
- Well-known filenames (`Makefile`, `Dockerfile`, `pyproject.toml`,
  `.gitignore`, ...) get their own icon instead of the generic file glyph.
- The shell prompt is just the working directory again. The backend name and
  layer stack, which grow with every layer, print once in the start banner
  and on demand via `provider` instead of prefixing every command.
- `SandboxLayer` no longer reports `path '/' does not exist` when its root is
  missing: true inside the jail, where the absent root *is* `/`, and nonsense
  to anyone reading it. It now says `sandbox root does not exist`, still
  without naming the real root it exists to hide. Library users get this too,
  not just `sx`.

## [0.4.2] - 2026-07-16

Object stores: S3, GCS, and Azure Blob through the first external backend
adapter. See ADR 0020.

### Added

- `S3Backend` and `GcsBackend` over an internal opendal engine, reaching
  Amazon S3, S3-compatible stores (MinIO, R2), and Google Cloud Storage, with
  the `s3` and `gcs` extras.
- `AzureBlobBackend` and a self-detecting `azure` provider that builds either
  Azure backend from one schema, so a flat (non-HNS) account works without
  code changes.
- Lean install profiles: `azadls` (ADLS Gen2 only) and `azblob` (blob only);
  `azure` composes the two.
- Documentation for the object-store backends: guide, reference, install
  profiles, a recipe, and an S3 sample against a throwaway local MinIO.

### Fixed

- `storix[azure]` bundles the blob engine, and optional-dependency errors name
  the exact extra to install.

## [0.4.1] - 2026-07-16

Transfer progress as composable observability events, with documentation,
typing, and project presentation improvements.

### Added

- `ObservabilityLayer` wraps streaming reads and writes and emits a cumulative
  `TransferEvent` for each transferred chunk. Its sink may be synchronous or
  asynchronous, and omitting the sink leaves the layer as a pure passthrough.
- `ObservabilityLayer` and `TransferEvent` are exported from the sync, async,
  and top-level public APIs.
- The documentation includes an observability guide, API reference, and a
  runnable Rich progress-bar recipe.

### Changed

- Storix dataclass DTOs now share the `@dto` house-style decorator, keeping
  them consistently frozen, slotted, and keyword-only without changing their
  public behavior.
- The README and documentation site use the refreshed Storix brand kit,
  including dark/light banners, favicon, and header logo variants.

### Fixed

- Layer re-composition and Click command annotations now pass the configured
  static type checks without changing runtime behavior.

## [0.4.0] - 2026-07-15

`when_missing` infers its capability from the layer. Breaking combinator
signature. See ADR 0018.

### Changed (breaking)

- The free `when_missing` combinator infers the gated capability from the
  layer's `provides` ClassVar and drops the explicit first argument, matching
  `with_layer_missing`. It now forwards constructor args to the layer, so the
  conditional case no longer needs `functools.partial`. Migration is
  mechanical: delete the leading capability argument.

  ```python
  # was
  when_missing(Capability.PRESIGNED_URLS, DataUrlLayer)
  # now
  when_missing(DataUrlLayer)

  # constructor kwargs forward directly (no functools.partial):
  when_missing(MetadataLayer, serialize=dumps, deserialize=loads)
  ```

  It raises `ValueError` if the layer declares no `provides` (nothing to
  infer, use it unconditionally instead). `functools.partial` stays the shape
  for unconditional layers in a `layers=` list.

### Added

- `LayerFactory` (the ParamSpec layer-factory protocol behind `with_layer` and
  now `when_missing`) is a public export from `storix` and `storix.aio`, beside
  `BoundLayer`, so integrators writing their own layer helpers can name the
  type.

## [0.3.0] - 2026-07-14

Bounded, provider-aware streaming in both directions. This is a breaking
backend-port release. See ADR 0017.

### Added

- `get_storage("memory")` and `STORIX_PROVIDER=memory` now expose the built-in
  zero-configuration memory backend through the same typed factory as local and
  Azure storage.
- `Storix.stream(..., chunk_size=)` now exposes a consumer-facing maximum
  chunk size. It splits oversized provider chunks without coalescing smaller
  ones; `None` selects the backend default.
- `Storix.echo(..., chunk_size=)` controls target write batches for every
  accepted source shape. Tiny iterator yields are combined and oversized
  values are split with a linear, bounded-memory stdlib implementation.
- The backend port now has explicit whole-object and streaming pairs:
  `read`/`read_stream` and `write`/`write_stream`. `BackendBase` derives either
  form from the other, so a custom backend may implement native streaming or
  the simpler whole-object form independently per direction.
- Azure transfer settings: `read_chunk_size` (4 MiB default),
  `write_chunk_size` (4 MiB), and `read_prefetch_size` (32 MiB), also available
  as `STORIX_AZURE_*` configuration.

### Changed (breaking)

- `StorageBackend.write(path, data, ...)` now takes one complete `bytes`
  payload. Streaming backends implement `write_stream(path, iterator, ...)`.
- `StorageBackend.read_stream` and `write_stream` accept the keyword-only
  `chunk_size` control. Custom backends and layers overriding either method
  must add it and honor the port contract.
- Explicit zero or negative chunk sizes raise stdlib `ValueError`. There is no
  `-1` whole-file sentinel; use `cat()` for a complete read.

### Fixed

- Local and memory reads no longer reuse the former 100 MiB write batch, which
  made ordinary files appear as one chunk. Generic/local defaults are now 1
  MiB, while Azure keeps provider-appropriate 4 MiB transfer batches.
- Azure reads no longer coalesce SDK chunks just to fill the requested output
  size, and Azure writes no longer issue one append request per tiny producer
  yield.
- The `cli` extra now declares its direct `click` dependency. The `sx` launcher
  reports an actionable install command without a traceback when the extra is
  absent, and Azure uses the same optional-extra error style.
- Azure client authentication failures now raise `ConfigurationError` with a
  credential hint. `PermissionDeniedError` is reserved for authorization
  failures after authentication succeeds.

## [0.2.2] - 2026-07-12

Per-op cache bypass, and public-API fixes.

### Added

- `Storix.without_layer(*types)` - a *new* session with the given layer
  types bypassed, the rest re-composed (absent types are a no-op; cwd is
  preserved). `Storix.uncached` is sugar for `without_layer(CacheLayer)`,
  for a guaranteed-fresh read: `fs.uncached.ls()`. Layers gate this with
  `removable: ClassVar[bool]` (default `True`); `SandboxLayer` sets it
  `False` - a jail is a security boundary and raises
  `NonRemovableLayerError` if you try to strip it. (ADR 0016)
- `BoundLayer` (`Callable[[StorageBackend], StorageBackend]`, the
  `layers=` / `with_layer` shape) is now a public export from `storix`
  and `storix.aio`, so consumers stop redefining it.

### Fixed

- `CacheOp`, `CacheStore`, and `InMemoryCacheStore` are now in the
  `__all__` of both `storix` and `storix.aio` - they were importable at
  runtime but rejected by type checkers. `storix.aio` also regains the
  `PathKind`/`RawStat` exports the sync namespace already had, so the two
  flavors are symmetric (now guarded by a test).

## [0.2.1] - 2026-07-12

Configurable read-through caching, in the library and the `sx` CLI.

### Added

- `CacheLayer`: a configurable per-op read-through cache. metadata
  (stat/list/exists, on by default), `du`, `read` (content) and `url`
  (presigned) each toggle as `bool | CacheOp` - `cache(ttl=, store=,
  max_bytes=)` per op, or the layer defaults. Eviction is per op on every
  mutation through the layer (metadata: path+parent; du: ancestor chain;
  read: the file); `url` is TTL-only, capped to the URL's lifetime. Keys
  follow `<namespace>[:<environment>]:<op>:<locator>` and are keyed on the
  physical `locate()`, so sessions sharing a store never collide.
  (ADR 0014)
- Pluggable `CacheStore` - a cashews-shaped async protocol
  (`get`/`set`/`delete`/`delete_match`) with loose returns, so a
  `cashews.Cache` (Redis, disk, ...) satisfies the async flavor with no
  adapter. The sync flavor uses synchronous implementations of the same four
  methods. Ships
  `InMemoryCacheStore` (optional `maxsize` LRU) as the default. New
  exports: `CacheLayer`, `CacheOp`, `cache`, `CacheStore`,
  `InMemoryCacheStore`.
- CLI layer flags: `sx --cache [--cache-ttl N]` (metadata+du+read, content
  capped at 8 MiB) and `sx --sandbox PATH`, applied sandbox-innermost /
  cache-outermost. The REPL prints the active stack and gains a `refresh`
  built-in (namespace-scoped cache clear); `provider` lists the layers and
  the backing store. (ADR 0015)
- `sx url <file> --expire <seconds>` to set presigned-URL lifetime.

### Changed

- The `sx` shell prompt and `provider` now show the real backend annotated
  with the active stack (e.g. `LocalBackend(cache, sandbox)`) instead of
  the outermost layer's class name.

### Notes

- `CacheLayer` correctness assumes a single writer of its store(s); pass
  `ttl` to bound staleness (the default never expires). A declarative
  `[tool.storix.cli]` layer stack and CLI cache-store selection
  (disk/redis) are designed and deferred - see `docs/adr/0015` and
  `docs/roadmap.md`.

## [0.2.0] - 2026-07-12

Ground-up hexagonal rework: one core engine (`Storix`) owns every unix
semantic over a small backend port; the sync flavor is generated from
the async source of truth. Breaking release.

### Added

- One `Storix` engine over a ~14-method backend port; the sync flavor is
  generated from the async source of truth (`scripts/unasync.py`), so the
  two never drift and one conformance suite proves both.
- `MemoryBackend` (dict-backed reference backend) alongside `LocalBackend`
  and the HNS-only `AzureBackend`; bring your own via the port +
  `register_backend()`.
- Layers - backends that wrap backends: `SandboxLayer` (chroot as
  middleware, with `to_real`/`to_virtual` for audit), `DataUrlLayer` and
  `MetadataLayer` (portable capabilities - `url()` and custom metadata on
  backends that lack them natively), and `LayerBase` for writing your
  own. Compose with `Storix(be, layers=[...])`, `fs.with_layer()`
  (ParamSpec-typed, Starlette-style kwarg forwarding), or
  `fs.with_layer_missing()` (skips the layer when the backend is already
  native - capability inferred from the layer's `provides`).
- `temporary()` and `scratch(backend, root=...)` disposable/pinned
  workspaces; `fs.scratch()` and `fs.chroot()` on any session.
- Capabilities with typed gates (`UnsupportedOperationError` names the
  missing one): `content_type`, `custom_metadata` (write-through +
  `fs.set_metadata(..., merge=)`), `presigned_urls` (`fs.url()`, SAS on
  Azure) and the backend-agnostic `fs.data_url()`.
- `fs.stream()` (streaming `cat`), `fs.resolve()` (navigable/bookmarkable
  port path) and `fs.locate()` (physical URI - file://, abfss:// - for
  audit/cross-system reference, resolved through any sandbox).
- Typed factory: `get_storage('azure', container=...)` with full IDE
  completion, `register_backend()` + `available_providers()` for third
  parties; namespaced `STORIX_*` configuration.
- `MetadataLayer` takes pluggable `serialize`/`deserialize` callables
  (default stdlib json; pass `orjson.dumps`/`orjson.loads` or any
  object<->bytes pair).
- Typed, fact-carrying error taxonomy (`storix.errors`) with errno and
  dual stdlib inheritance; every failure raises - no boolean returns.
- Rewritten `sx` CLI + REPL on the new core (session cwd persists; the
  shell reuses the Typer parser, so every flag matches the one-shot CLI).
- `py.typed`: the package is now typed for downstream checkers.

### Changed (breaking)

| 0.1.x | 0.2.0 |
|---|---|
| `LocalFilesystem(...)` | `Storix(LocalBackend(base))` |
| `AzureDataLake(...)` | `Storix(AzureBackend(container, account_name=..., credential=...))` |
| `STORAGE_*` / `ADLSG2_*` env vars | `STORIX_PROVIDER`, `STORIX_LOCAL_*`, `STORIX_AZURE_*` (see env.example) |
| `touch(path, data)` | `touch(*paths)` creates/refreshes only; data goes through `echo` |
| `rm(path)` file-only + `rmdir(recursive=True)` | `rm(*paths, recursive=True)` is rm -r; `rmdir(*paths)` strictly empty dirs |
| `mv(src, dst)` / `cp(src, dst)` | variadic, last argument is the destination (unix) |
| `ls()` shows dotfiles | hidden by default; `ls(all=True)` shows them |
| failed ops return `False` | typed exceptions, always |
| `sandboxed=True` constructor flag | explicit `SandboxLayer(backend, root=...)` composition |
| `FileProperties.file_kind` | `FileProperties.kind` |
| `PathNotFoundError` subclasses `ValueError` | subclasses `FileNotFoundError` only |

### Notes

- Azure behavior is wire-verified: the full conformance suite (80
  integration params, both flavors) passes against a real HNS account.
  Run yours with `pytest -m integration` (needs `ADLSG2_*` credentials).
- `tree`/`find`/`wc` are not yet core methods (the CLI provides `tree`);
  along with `MountLayer`, `CacheLayer`, range reads, `glob`, and a
  pathlib-style adapter they are on the 0.2.x/0.3.x roadmap
  (`docs/roadmap.md`).
- Design rationale for the rework lives in `docs/adr/` (13 records).


## [0.1.3] - 2026-07-05

### Fixed

- Loosened dependency lower bounds to their tested minimums so `storix` no longer
  conflicts with packages that pin older versions (e.g. `pyrit`'s `aiofiles>=24,<25`):
  `aiofiles>=24.1.0`, `rich>=13.0.0`, `typer>=0.13.0`, `loguru>=0.7.2`,
  `azure-storage-file-datalake>=12.14.0`, `aiohttp>=3.9.0`. No code changes;
  functionality is identical to 0.1.2.
- Removed the unused `rich-toolkit` dependency from the `cli` extra.

## [0.1.2] - 2026-06-02

### Improvements

- `StorixPath` is now always in POSIX path form, making it platform-agnostic across
  Windows and Unix systems.
- `StorixPath` is now recognized by Pydantic as a valid type for model fields and
  validation.

### Internal

- `storix.errors` is now eagerly imported (no longer lazy-loaded), since the module
  is lightweight and needed at import time for isinstance checks.

## [0.1.0] - 2025-12-14

### Highlights

- Add test coverage for `du()` / `stat()` and `StorixPath` helpers across providers.

### BREAKING CHANGES

- `ls()` now always returns `StorixPath` items (never `str`).

    Migration:
    - If you previously relied on strings, convert explicitly:

        ```python
        files = fs.ls("/")
        names = [p.name for p in files]
        paths_as_str = [str(p) for p in files]
        ```

### Internal

- Added test coverage for `du`/`stat` and `StorixPath` helpers across providers.

## [0.0.3] - 2025-12-14

### Features

- Smart MIME type inference when writing files (path-first → buffer sniff →
  default), with explicit `content_type` override for sync/async Azure `touch`
  and `echo`.
- New helpers: `storix.utils.detect_mimetype` and
  `storix.utils.guess_mimetype_from_path`.
- Unified missing-path exception: `PathNotFoundError` (subclasses
  `FileNotFoundError` & `ValueError`) replacing previous raw `ValueError` while
  keeping backward compatibility.
- Introduce StorixPath as the standardized return for logical path operations + bonus
  defined operations such as mimetype detection and file type guess
- Introduce new function `echo` for efficient streaming writes
- Introduce simple implementation of `tree` and extras such as `wc` and `find`

### Fixes

- Storage protocols are now runtime checkable to easily check isinstance() and support
  for tools that enforce type hints through instance checks like pydantic
- settings are loaded by `get_settings`; to avoid cached settings, allowing
  manipulation of environment dynamically during runtime affecting filesystems
  initialization defaults and `get_storage()`.

## [0.0.2] – 2025‑10‑16

### Highlights

- **Python 3.12+ support** – raised the minimum Python version to 3.12 (tested
  on 3.13) and dropped support for older versions.
- **`src` layout & build upgrade** – moved all code under the `src/` directory
  and switched from `hatchling` to **uv_build** for packaging. This aligns with
  best practices and simplifies installation via `uv`.
- **Lazy imports & module reorganisation** – refactored modules into `storix`
  and `storix.aio` packages under `src`, introducing `__getattr__` to lazily load
  providers (avoids importing optional dependencies until needed).
- **Sandbox refactor** – replaced `PathSandboxable` with **PathSandboxer** and
  `SandboxedPathHandler`, strengthening sandbox enforcement and path‑resolution
  logic to block traversal & symlink escapes.
- **New utility & model modules** – added `storix/utils` (e.g. `to_data_url`,
  `PathLogicMixin`) and data models such as `AzureFileProperties` to standardize
  metadata returned by `stat()`.
- **Scripts & CLI updates** – updated scripts (`coverage`, `format`, `lint`) to
  operate on the new `src` layout; `pyproject.toml` now defines pytest discovery
  paths and richer `ruff` formatting/linting rules.
- **Miscellaneous improvements** – improved `get_storage()` typing
  (`StrPathLike`), added lazy provider lookup maps, fixed configuration for
  docstring formatting, and defined version statically rather than dynamically.

### Migration notes

- **Sandbox handlers** – if you rely on custom sandbox handlers, update them to
  implement `PathSandboxer` rather than the old `PathSandboxable` interface.
- **Async API** – the asynchronous API remains identical; just import from
  `storix.aio` and use `await` on file operations.

## [0.0.1] - 2024-07-06

### 🎉 Initial Release

Storix is a blazing-fast, secure, and developer-friendly storage abstraction
for Python that provides Unix-style file operations across local and cloud
storage backends.

### ✨ Key Features

- **Unified API**: Seamless sync and async support with identical interfaces
- **Local Filesystem & Azure Data Lake Storage Gen2**: Production-ready backends
- **CLI Tool (`sx`)**: Interactive shell and command-line interface
- **Sandboxing**: Secure file operations with path traversal protection
- **Smart Configuration**: Automatic `.env` discovery and environment variable support

### 📦 Installation

```bash
# Basic (local filesystem only)
uv add storix

# With CLI tools
uv add "storix[cli]"

# With Azure support
uv add "storix[azure]"

# Everything included
uv add "storix[all]"
```

### 🚀 Quick Start

```python
from storix import get_storage

fs = get_storage()
fs.touch("hello.txt", "Hello, Storix!")
content = fs.cat("hello.txt").decode()
print(content)  # Hello, Storix!
```

### 🔧 Configuration

Create a `.env` file:

```env
STORAGE_PROVIDER=local
STORAGE_INITIAL_PATH=.
STORAGE_INITIAL_PATH_LOCAL=/path/to/your/data
STORAGE_INITIAL_PATH_AZURE=/your/azure/path
ADLSG2_CONTAINER_NAME=my-container
ADLSG2_ACCOUNT_NAME=my-storage-account
ADLSG2_TOKEN=your-sas-token-or-account-key
```

### 📚 Documentation

- [GitHub Repository](https://github.com/mghalix/storix)
- [Sandbox Implementation](https://github.com/mghalix/storix/blob/v0.1.0/docs/SANDBOX_IMPLEMENTATION.md)
- [Async Migration Guide](https://github.com/mghalix/storix/blob/v0.1.0/docs/ASYNC_MIGRATION.md)

---

## Version History

### <0.1.2> – 2026-06-02

- `StorixPath` is now always in posix path form - platform agnostic.
- `StorixPath` is now recognized by pydantic.
- `storix.errors` is now eagerly imported for reliable isinstance checks.

### <0.1.1> – 2026-06-02 *(yanked — republished as 0.1.2)*

### <0.1.0> – 2025-12-14

- Breaking: `ls()` now always returns `StorixPath` items (never `str`).
- Added test coverage for `du()` / `stat()` and `StorixPath` helpers across providers.

### <0.0.3> – 2025-12-14

- Smart MIME type inference for sync/async Azure `touch()` and `echo()` (with explicit
  `content_type` override).
- Added `storix.utils.detect_mimetype()` and `storix.utils.guess_mimetype_from_path()`.
- Unified missing-path exception as `PathNotFoundError` (subclasses `FileNotFoundError`
  & `ValueError`).

### <0.0.2> – 2025‑10‑16

- Introduced Python 3.12+ requirement and removed support for Python < 3.12.
- Adopted a `src` layout and switched packaging to `uv_build`.
- Implemented lazy imports via `__getattr__` and reorganized modules under
  `storix` and `storix.aio`.
- Refactored sandbox to use `PathSandboxer`/`SandboxedPathHandler`.
- Added new utility and model modules (`utils`, `AzureFileProperties`).
- Updated scripts and tooling (`coverage`, `format`, `lint`, `pyproject.toml`).

### <0.0.1> - 2024-07-06

- Initial release with local filesystem and Azure Data Lake Storage Gen2 support
- Sync and async APIs with unified interface
- CLI tool with interactive shell
- Sandboxing and security features
- Comprehensive test suite and documentation
