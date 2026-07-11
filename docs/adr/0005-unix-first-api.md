# 5. The core API is unix-first, not pathlib-first

Status: accepted

## Context
Owner direction: interfaces should read like the shell. Where unix and
Python conventions conflict, unix wins; a pathlib-flavored adapter is
planned separately (roadmap 0.3.0).

## Decision
`ls` hides dotfiles unless `all=True` and lists a file as itself;
`touch(path, /, *paths)` creates/refreshes and never truncates (data
goes through `echo`); `rm(*paths, recursive=)` is rm -r while
`rmdir(*paths)` is strictly empty-dirs; `mv`/`cp` are variadic with
last-argument destination (into-directory semantics; cp -r overlays);
`mkdir(parents=True)` keeps BOTH meanings of -p (no separate exist_ok);
multi-target methods take `path, /, *paths` so at-least-one is enforced
by the signature; `cat` concatenates; `stream()` is streaming cat;
`stat()` renders a stat(1)-style block. Errors carry the unix flavor;
`rm` validates all targets before deleting any (deliberate safety
divergence).

## Consequences
Shell users feel at home; agents get the vocabulary LLMs already know.
Divergences from unix (touch-on-dir raises; rm pre-validation) are
documented at the method.
