from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

import storix as sx
from storix.typing import _AvailableProviders

app = typer.Typer(
    rich_markup_mode="rich",
    help="Storix CLI - Unix-like filesystem commands",
    no_args_is_help=False,
)
console = Console()


# Global fs instance - will be overridden by --provider flag if specified
fs = sx.get_storage()


def get_fs_with_provider(
    provider: _AvailableProviders | str | None = None,
) -> sx.Storage:
    """Get filesystem instance with optional provider override."""
    if provider:
        return sx.get_storage(provider=provider)
    return fs


@app.command()
def ls(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="A path to a directory. If not provided, lists current directory"
        ),
    ] = None,
    *,
    long: Annotated[
        bool,
        typer.Option("-l", "--long", help="Use long listing format"),
    ] = False,
    all: Annotated[
        bool,
        typer.Option("-a", "--all", help="Show hidden files"),
    ] = False,
    colors: Annotated[
        bool,
        typer.Option("--color/--no-color", help="Enable/disable colors"),
    ] = True,
) -> None:
    """List directory contents."""
    try:
        files = fs.ls(path, all=all)

        if not files:
            return

        if long:
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Type")
            table.add_column("Name")
            table.add_column("Size")

            for file in files:
                full_path = fs._topath(path) / file if path else fs.pwd() / file  # type: ignore
                if fs.isdir(full_path):
                    file_type = "DIR"
                    name = Text(file, style="bold blue") if colors else file
                    size = "-"
                elif fs.isfile(full_path):
                    file_type = "FILE"
                    name = Text(file, style="white") if colors else file
                    try:
                        size = str(full_path.stat().st_size)
                    except Exception:
                        size = "?"
                else:
                    file_type = "?"
                    name = file
                    size = "?"

                table.add_row(file_type, name, size)

            console.print(table)
        else:
            colored_files = []
            for file in files:
                full_path = fs._topath(path) / file if path else fs.pwd() / file  # type: ignore
                if colors:
                    if fs.isdir(full_path):
                        colored_files.append(Text(file, style="bold blue"))
                    elif fs.isfile(full_path):
                        colored_files.append(Text(file, style="white"))
                    else:
                        colored_files.append(Text(file, style="dim"))
                else:
                    colored_files.append(Text(file))

            console.print(*colored_files)

    except Exception as e:
        console.print(f"[red]ls: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def pwd() -> None:
    """Print current working directory."""
    console.print(fs.pwd())


@app.command()
def cd(
    path: Annotated[
        Path | None,
        typer.Argument(help="Directory to change to. If not provided, goes to home"),
    ] = None,
) -> None:
    """Change the current directory."""
    try:
        fs.cd(path)
        console.print(f"Changed to: {fs.pwd()}")
    except Exception as e:
        console.print(f"[red]cd: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def mkdir(
    directories: Annotated[
        list[Path],
        typer.Argument(help="Directories to create"),
    ],
    *,
    parents: Annotated[
        bool,
        typer.Option("-p", "--parents", help="Create parent directories as needed"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v", "--verbose", help="Print a message for each created directory"
        ),
    ] = False,
) -> None:
    """Create directories."""
    for directory in directories:
        try:
            fs.mkdir(directory, parents=parents)
            if verbose:
                console.print(f"Created directory: {directory}")
        except Exception as e:
            console.print(
                f"[red]mkdir: cannot create directory '{directory}': {e}[/red]"
            )
            raise typer.Exit(1) from e


@app.command()
def rmdir(
    directories: Annotated[
        list[Path],
        typer.Argument(help="Directories to remove"),
    ],
    *,
    recursive: Annotated[
        bool,
        typer.Option(
            "-r",
            "--recursive",
            help="Remove directories and their contents recursively",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v", "--verbose", help="Print a message for each removed directory"
        ),
    ] = False,
) -> None:
    """Remove directories."""
    for directory in directories:
        try:
            if fs.rmdir(directory, recursive=recursive):
                if verbose:
                    console.print(f"Removed directory: {directory}")
            else:
                console.print(f"[red]rmdir: failed to remove '{directory}'[/red]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]rmdir: {e}[/red]")
            raise typer.Exit(1) from e


@app.command()
def touch(
    files: Annotated[
        list[Path],
        typer.Argument(help="Files to create or update"),
    ],
) -> None:
    """Create empty files or update timestamps."""
    for file in files:
        try:
            if fs.touch(file):
                console.print(f"Touched: {file}")
            else:
                console.print(f"[red]touch: failed to touch '{file}'[/red]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]touch: {e}[/red]")
            raise typer.Exit(1) from e


@app.command()
def rm(
    files: Annotated[
        list[Path],
        typer.Argument(help="Files to remove"),
    ],
    *,
    force: Annotated[
        bool,
        typer.Option("-f", "--force", help="Ignore nonexistent files"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Print a message for each removed file"),
    ] = False,
) -> None:
    """Remove files."""
    for file in files:
        try:
            if fs.rm(file):
                if verbose:
                    console.print(f"Removed: {file}")
            else:
                if not force:
                    console.print(f"[red]rm: failed to remove '{file}'[/red]")
                    raise typer.Exit(1)
        except Exception as err:
            if not force:
                console.print(f"[red]rm: {err}[/red]")
                raise typer.Exit(1) from err


@app.command()
def cp(
    source: Annotated[Path, typer.Argument(help="Source file or directory")],
    destination: Annotated[Path, typer.Argument(help="Destination file or directory")],
    *,
    recursive: Annotated[
        bool,
        typer.Option("-r", "-R", "--recursive", help="Copy directories recursively"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Print copied files"),
    ] = False,
) -> None:
    """Copy files or directories."""
    try:
        if fs.isdir(source) and not recursive:
            console.print(f"[red]cp: '{source}' is a directory (not copied)[/red]")
            raise typer.Exit(1)

        fs.cp(source, destination)
        if verbose:
            console.print(f"Copied: {source} -> {destination}")
    except Exception as e:
        console.print(f"[red]cp: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def mv(
    source: Annotated[Path, typer.Argument(help="Source file or directory")],
    destination: Annotated[Path, typer.Argument(help="Destination file or directory")],
    *,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Print moved files"),
    ] = False,
) -> None:
    """Move/rename files or directories."""
    try:
        fs.mv(source, destination)
        if verbose:
            console.print(f"Moved: {source} -> {destination}")
    except Exception as e:
        console.print(f"[red]mv: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def cat(
    files: Annotated[
        list[Path],
        typer.Argument(help="Files to display"),
    ],
    *,
    number: Annotated[
        bool,
        typer.Option("-n", "--number", help="Number output lines"),
    ] = False,
    binary: Annotated[
        bool,
        typer.Option(
            "-b", "--binary", help="Output raw binary data (use with caution)"
        ),
    ] = False,
) -> None:
    """Display file contents."""
    import sys

    for file in files:
        try:
            content = fs.cat(file)

            # Check if content appears to be binary
            def is_binary(data: bytes) -> bool:
                """Detect if data appears to be binary."""
                if not data:
                    return False
                # Check for null bytes or high percentage of non-printable characters
                null_bytes = data.count(b"\x00")
                if null_bytes > 0:
                    return True

                try:
                    data.decode("utf-8")
                    return False
                except UnicodeDecodeError:
                    return True

            if is_binary(content) and not binary:
                console.print(
                    f"[yellow]cat: {file}: Binary file (use --binary to force output or 'download' command to save)[/yellow]"
                )
                # Show some basic info about the file
                console.print(f"File size: {len(content)} bytes")

                # Try to identify file type by extension
                suffix = str(file).lower()
                if any(
                    suffix.endswith(ext)
                    for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
                ):
                    console.print(
                        "File appears to be an image. Use 'download' command to save it locally."
                    )
                elif any(
                    suffix.endswith(ext)
                    for ext in [".pdf", ".doc", ".docx", ".zip", ".tar", ".gz"]
                ):
                    console.print(
                        "File appears to be a document/archive. Use 'download' command to save it locally."
                    )

                continue

            if binary:
                # Output raw binary data to stdout
                sys.stdout.buffer.write(content)
            else:
                # Decode as text
                text = content.decode("utf-8", errors="replace")

                if number:
                    lines = text.splitlines()
                    for i, line in enumerate(lines, 1):
                        console.print(f"{i:6}\t{line}")
                else:
                    console.print(text, end="")

        except Exception as e:
            console.print(f"[red]cat: {file}: {e}[/red]")
            raise typer.Exit(1) from e


@app.command()
def echo(
    text: Annotated[str, typer.Argument(help="Text to display")],
    *,
    file: Annotated[
        Path | None,
        typer.Option("-f", "--file", help="Write to file instead of stdout"),
    ] = None,
    append: Annotated[
        bool,
        typer.Option("-a", "--append", help="Append to file instead of overwriting"),
    ] = False,
) -> None:
    """Display text or write to file."""
    if file:
        try:
            if append and fs.exists(file):
                existing_content = fs.cat(file)
                new_content = existing_content + text.encode() + b"\n"
            else:
                new_content = text.encode() + b"\n"

            fs.touch(file, new_content)
        except Exception as e:
            console.print(f"[red]echo: {e}[/red]")
            raise typer.Exit(1) from e
    else:
        console.print(text)


@app.command()
def exists(
    paths: Annotated[
        list[Path],
        typer.Argument(help="Paths to check"),
    ],
    *,
    quiet: Annotated[
        bool,
        typer.Option(
            "-q", "--quiet", help="Don't print messages, just return exit codes"
        ),
    ] = False,
) -> None:
    """Check if files or directories exist."""
    all_exist = True
    for path in paths:
        try:
            if fs.exists(path):
                if not quiet:
                    console.print(f"[green]✓[/green] {path} exists")
            else:
                if not quiet:
                    console.print(f"[red]✗[/red] {path} does not exist")
                all_exist = False
        except Exception as e:
            if not quiet:
                console.print(f"[red]exists: {e}[/red]")
            all_exist = False

    if not all_exist:
        raise typer.Exit(1)


@app.command()
def tree(
    path: Annotated[
        Path | None,
        typer.Argument(help="Directory to show tree for"),
    ] = None,
) -> None:
    """Display directory tree (not implemented)."""
    console.print("[yellow]tree: command not implemented yet[/yellow]")
    raise typer.Exit(1)


@app.command()
def find(
    path: Annotated[
        Path | None,
        typer.Argument(help="Starting directory for search"),
    ] = None,
    *,
    name: Annotated[
        str | None,
        typer.Option("-name", help="Find files with this name pattern"),
    ] = None,
    type: Annotated[
        str | None,
        typer.Option("-type", help="Find files of this type (f=file, d=directory)"),
    ] = None,
) -> None:
    """Find files and directories (basic implementation)."""
    start_path = path or fs.pwd()

    try:

        def search_recursive(
            current_path: Path,
            pattern: str | None = None,
            file_type: str | None = None,
        ) -> list[Path]:
            """Recursively search for files matching a pattern."""
            results = []
            try:
                items = fs.ls(current_path)
                for item in items:
                    item_path = current_path / item

                    # Type filtering
                    if file_type:
                        if file_type == "f" and not fs.isfile(item_path):
                            continue
                        if file_type == "d" and not fs.isdir(item_path):
                            continue

                    # Name filtering (simple pattern matching)
                    if pattern and pattern not in item:
                        if fs.isdir(item_path):
                            results.extend(
                                search_recursive(item_path, pattern, file_type)
                            )
                        continue

                    results.append(item_path)

                    # Recurse into directories
                    if fs.isdir(item_path):
                        results.extend(search_recursive(item_path, pattern, file_type))

            except Exception:
                pass  # Skip directories we can't read

            return results

        results = search_recursive(start_path, name, type)
        for result in results:
            console.print(result)

    except Exception as e:
        console.print(f"[red]find: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def wc(
    files: Annotated[
        list[Path],
        typer.Argument(help="Files to count"),
    ],
    *,
    lines: Annotated[
        bool,
        typer.Option("-l", "--lines", help="Count lines only"),
    ] = False,
    words: Annotated[
        bool,
        typer.Option("-w", "--words", help="Count words only"),
    ] = False,
    chars: Annotated[
        bool,
        typer.Option("-c", "--chars", help="Count characters only"),
    ] = False,
) -> None:
    """Count lines, words, and characters in files."""
    total_lines = total_words = total_chars = 0

    for file in files:
        try:
            content = fs.cat(file).decode("utf-8", errors="replace")

            line_count = len(content.splitlines())
            word_count = len(content.split())
            char_count = len(content)

            total_lines += line_count
            total_words += word_count
            total_chars += char_count

            output = []
            if lines or (not lines and not words and not chars):
                output.append(str(line_count))
            if words or (not lines and not words and not chars):
                output.append(str(word_count))
            if chars or (not lines and not words and not chars):
                output.append(str(char_count))

            output.append(str(file))
            console.print(" ".join(output))

        except Exception as e:
            console.print(f"[red]wc: {file}: {e}[/red]")
            raise typer.Exit(1) from e

    if len(files) > 1:
        output = []
        if lines or (not lines and not words and not chars):
            output.append(str(total_lines))
        if words or (not lines and not words and not chars):
            output.append(str(total_words))
        if chars or (not lines and not words and not chars):
            output.append(str(total_chars))
        output.append("total")
        console.print(" ".join(output))


@app.command()
def download(
    remote_path: Annotated[Path, typer.Argument(help="Remote file to download")],
    local_path: Annotated[
        Path | None,
        typer.Argument(
            help="Local destination path (defaults to filename in current directory)"
        ),
    ] = None,
    *,
    overwrite: Annotated[
        bool,
        typer.Option("-f", "--force", help="Overwrite existing local files"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Show download progress"),
    ] = False,
) -> None:
    """Download files from remote storage to local filesystem."""
    try:
        # Get the file content from remote storage
        content = fs.cat(remote_path)

        # Determine local destination
        if local_path is None:
            local_path = Path(remote_path.name)

        # Check if local file exists
        if local_path.exists() and not overwrite:
            console.print(
                f"[red]download: '{local_path}' already exists (use --force to overwrite)[/red]"
            )
            raise typer.Exit(1)

        # Create parent directories if needed
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content to local file
        with open(local_path, "wb") as f:
            f.write(content)

        if verbose:
            console.print(
                f"Downloaded {len(content)} bytes: {remote_path} -> {local_path}"
            )
        else:
            console.print(f"Downloaded: {remote_path} -> {local_path}")

    except Exception as e:
        console.print(f"[red]download: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def upload(
    local_path: Annotated[Path, typer.Argument(help="Local file to upload")],
    remote_path: Annotated[
        Path | None,
        typer.Argument(
            help="Remote destination path (defaults to filename in current remote directory)"
        ),
    ] = None,
    *,
    overwrite: Annotated[
        bool,
        typer.Option("-f", "--force", help="Overwrite existing remote files"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Show upload progress"),
    ] = False,
) -> None:
    """Upload files from local filesystem to remote storage."""
    try:
        # Check if local file exists
        if not local_path.exists():
            console.print(f"[red]upload: '{local_path}' does not exist[/red]")
            raise typer.Exit(1)

        # Determine remote destination
        if remote_path is None:
            remote_path = fs.pwd() / local_path.name

        # Check if remote file exists
        if not overwrite and fs.exists(remote_path):
            console.print(
                f"[red]upload: '{remote_path}' already exists (use --force to overwrite)[/red]"
            )
            raise typer.Exit(1)

        # Read local file content
        with open(local_path, "rb") as f:
            content = f.read()

        # Upload to remote storage
        fs.touch(remote_path, content)

        if verbose:
            console.print(
                f"Uploaded {len(content)} bytes: {local_path} -> {remote_path}"
            )
        else:
            console.print(f"Uploaded: {local_path} -> {remote_path}")

    except Exception as e:
        console.print(f"[red]upload: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def provider() -> None:
    """Show current storage provider information."""
    provider_type = type(fs).__name__

    if provider_type == "LocalFilesystem":
        console.print("[green]Current provider:[/green] Local Filesystem")
        console.print(f"[blue]Working directory:[/blue] {fs.pwd()}")
        console.print(f"[blue]Home directory:[/blue] {fs.home}")
    elif provider_type == "AzureDataLake":
        console.print("[green]Current provider:[/green] Azure Data Lake Storage Gen2")
        console.print(f"[blue]Current path:[/blue] {fs.pwd()}")
        console.print(f"[blue]Home path:[/blue] {fs.home}")
    else:
        console.print(f"[green]Current provider:[/green] {provider_type}")

    console.print(
        "\n[dim]To switch providers, set the STORAGE_PROVIDER environment variable to 'local' or 'azure'[/dim]"
    )


@app.command()
def shell() -> None:
    """Start an interactive shell session."""
    from .shell import start_shell

    start_shell()


@app.command()
def repl() -> None:
    """Start an interactive shell session (alias for shell)."""
    from .shell import start_shell

    start_shell()


def main() -> None:
    """Entry point for the storix Typer CLI app."""
    app()


# Add callback for when no command is provided
@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    interactive: Annotated[
        bool,
        typer.Option("-i", "--interactive", help="Start interactive shell session"),
    ] = False,
    provider: Annotated[
        str | None,
        typer.Option(
            "-p", "--provider", help="Select storage provider (local or azure)"
        ),
    ] = None,
) -> None:
    """Storix CLI - Unix-like filesystem commands for local and cloud storage."""
    # Store the provider in context for commands to use
    ctx.obj = {"provider": provider}

    if ctx.invoked_subcommand is None or interactive:
        # No command provided or interactive flag used, start interactive shell
        from .shell import start_shell

        # Use the selected provider for the shell
        selected_fs = get_fs_with_provider(provider)
        start_shell(selected_fs)
