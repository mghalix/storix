# Commands

Every command is the unix command you already know, pointed at whichever
backend the session opened.

```
navigate   ls  pwd  cd  tree
read       cat  stat  du  url
search     find
write      touch  echo  mkdir
remove     rm  rmdir
move       mv  cp
transfer   push  pull
session    whereami  provision  exists
```

Every command supports `--help`. Familiar flags behave as they do in unix:
`ls -l` (long), `-a` (hidden), `-t` (newest first), `-r` (reverse); `du -h` and
`ls -l` humanize sizes in binary units like coreutils (`165M`); `tree` closes
with the usual `N directories, M files`.

## Several paths at once

`ls`, `du`, `stat`, `tree` and `find` each take as many paths as you like, and
report them the way their unix counterparts do:

```bash
sx ls a.txt b.txt /media /logs   # files first, then a block per directory
sx du -sh /media /logs           # one total per argument
sx stat a.txt b.txt              # one block per argument
sx tree /media /logs             # one tree per argument, one closing count
sx find /media /logs --type f    # each subtree in turn
```

`ls` leads with the plain files as one group, then gives each directory its own
`name:` header with a blank line between blocks - and no header at all when
there is only one argument. `du`, `stat` and `find` keep the order you wrote,
add no header, and `du` prints no combined grand total. `tree` roots each
argument separately and closes with the count over all of them.

One difference from coreutils, and it is deliberate: sx checks every argument
before it acts on any of them. `ls a.txt nope b.txt` reports the missing path
and lists nothing, where unix `ls` lists `a.txt` first and then complains. The
same contract `cat` already keeps, and the reason is that a half-finished report
is harder to notice than a refused one.

The per-argument backend work is batched across all of them, so several
arguments cost one round trip's worth of latency rather than one each.

## Ordering a listing: `ls` and `tree`

The two listing commands take the same ordering flags: `--sort name|time|size`
and `-r` to invert whichever order was chosen. `name` is the default and
collates case-insensitively, like coreutils under a UTF-8 locale and like eza.
On `ls`, `-t` is the coreutils shorthand for `--sort time`.

`--sort` orders the entries inside a listing. `ls` orders its directory
*arguments* by name whatever `--sort` says, since ordering those by a stat would
cost a round trip nothing else on the command needs; `-r` inverts both.

```bash
sx ls --sort size          # largest first
sx ls -tr                  # oldest first (-t is --sort time, -r inverts it)
sx tree --sort time -r     # oldest sibling first, at every level
```

A directory has no size of its own - `ls -l` and `tree -l` render `-` in its
size column - so a size sort puts directories last, in both commands.

Sorting by time or size reads a modification time or a size that a plain
listing does not always carry. Those are fetched in one concurrent batch per
directory, and only for the sort that asks for them: on a cloud backend a
sorted listing of N entries costs one round trip's worth of latency, not N. A
long listing (`-l`) has already batched them, so sorting it costs nothing
extra.

## Searching with `find`

`find` searches recursively, the power-user (and agent) tool:

```bash
sx find /media --name '*.mp4' --type f   # every mp4 under /media
sx find --type d                         # all directories from cwd
```

## Sizes: `du` and `tree -l`

`du` is 1:1 with unix: a cumulative size per **directory**, bottom-up, ending
with the total. Files are aggregated but not listed by default (like
coreutils); `-a` lists them, `-s` prints only the grand total, `-d N` caps the
reported depth, `-h` humanizes.

```bash
sx du /data          # per-directory sizes + total
sx du -a /data       # include every file
sx du -sh /data      # one human-readable total
sx du -sh /a /b      # one total each, in the order written
```

For an itemized view - every file and directory with its size - use `tree -l`
(eza-style), which is the "show me everything and how big it is" companion to
`du`'s aggregate:

```bash
sx tree -l                 # kind + size columns on every entry
sx tree -L 2               # cap the depth at 2 levels
sx tree --sort size        # largest first, directories last
```

## Writing files: `echo`

`echo` prints text, or writes it into a file with `-f` (`-a` appends instead of
truncating). `-n` drops the trailing newline, exactly like `/usr/bin/echo -n`,
which is what a file that must not end on a newline needs:

```bash
sx echo hello -f /notes.txt       # stores "hello\n"
sx echo -n hello -f /notes.txt    # stores "hello"
sx echo world -a -f /notes.txt    # appends another line
```

On a terminal, output that stops mid-line says so: `sx echo -n hello` prints
`hello%`, with the `%` in inverse video, and closes the line so the next prompt
starts fresh. That is zsh's mark. It means the data ended without a newline,
not that a percent sign was printed, and `sx cat` marks a file whose last byte
is not a newline the same way. Redirected or captured output is data and is
never marked.

Left without text, `echo` takes the data from a pipe, so a producer writes
straight into storage:

```bash
gzip -c dump.sql | sx echo -f /backups/dump.sql.gz
sx echo -f /photos/raw.arw < photo.arw
```

Piped data is pulled in bounded reads, so an input larger than memory streams
through, and it is stored byte for byte: it arrives with its own encoding and
its own line endings, so nothing decodes it and nothing appends a newline to it,
which is what `-n` asks for anyway.

A terminal is never read as data, because in the REPL stdin is the prompt being
typed into. With no text and no pipe, `echo` prints just the newline, as unix
`echo` does with no operands. A lone `-` stays literal text: the argument is
content, not a file name, so overloading it would leave no way to print a dash.

## Provisioning the storage root

`sx provision` creates the backend's storage root if it is missing, and is
idempotent (safe to run in CI or a setup script):

```bash
sx -p azure provision   # provisioned: abfss://raw@acct.dfs.core.windows.net/
```

What it does depends on the backend, and the honest picture is narrow:

- **ADLS Gen2** (`azure`): creates the missing filesystem (container). This is
  the one real cloud provisioner. Already there: `already present: <uri>`.
- **local** and **memory**: report `already present` - the local base directory
  is created when the session opens, and the in-memory root always exists.
- **S3 / R2 / GCS / Azure Blob** (`s3`, `gcs`, `azblob`): **not supported**.
  These run on the opendal engine, which is data-plane only and has no
  create-bucket / create-container operation. `sx provision` exits non-zero with
  a message pointing you at your provider's own tooling (`aws s3 mb`,
  `gcloud storage buckets create`, `az storage container create`), rather than
  pretending it can create the bucket.

`sx mkdir` never creates a bucket or container - it operates *inside* an
existing root and creates a directory (or a directory marker on object stores).
Creating the root itself is a control-plane operation, which is exactly what
`provision` is for.

## When something fails

Failures print one line, not a provider traceback:

```console
$ sx -p s3 ls
ls: configured s3 bucket 'media' does not exist
```

Pass `--debug` to any invocation to get the full provider traceback (request
IDs, HTTP context) behind that one line:

```bash
sx --debug -p s3 ls
```

## Scripting with `exists`

`exists` prints nothing and exits `0` only if every path is there, which is the
shape a shell test wants:

```bash
if sx exists /media/video.mp4; then
  sx pull /media/video.mp4 ./video.mp4
fi
```
