"""Interactive REPL shell for Storix CLI."""

import os
import shlex
from collections.abc import Callable

from rich.console import Console
from rich.prompt import Prompt

import storix as sx

console = Console()


class StorixShell:
    """Interactive shell for Storix commands."""

    def __init__(self, fs: sx.Storage | None = None) -> None:
        """Initialize the interactive shell for Storix commands."""
        if fs is None:
            fs = sx.get_storage()
        self.fs = fs
        self.running = True

        # Import command handlers from the main CLI app
        from .app import cat as _cat
        from .app import cd as _cd
        from .app import cp as _cp
        from .app import download as _download
        from .app import echo as _echo
        from .app import exists as _exists
        from .app import find as _find
        from .app import ls as _ls
        from .app import mkdir as _mkdir
        from .app import mv as _mv
        from .app import provider as _provider
        from .app import pwd as _pwd
        from .app import rm as _rm
        from .app import rmdir as _rmdir
        from .app import touch as _touch
        from .app import upload as _upload
        from .app import wc as _wc

        # Map commands to their handlers
        self.commands = {
            "ls": self._wrap_command(_ls),
            "pwd": self._wrap_command(_pwd),
            "cd": self._wrap_command(_cd),
            "mkdir": self._wrap_command(_mkdir),
            "rmdir": self._wrap_command(_rmdir),
            "touch": self._wrap_command(_touch),
            "rm": self._wrap_command(_rm),
            "cp": self._wrap_command(_cp),
            "mv": self._wrap_command(_mv),
            "cat": self._wrap_command(_cat),
            "echo": self._wrap_command(_echo),
            "exists": self._wrap_command(_exists),
            "find": self._wrap_command(_find),
            "wc": self._wrap_command(_wc),
            "download": self._wrap_command(_download),
            "upload": self._wrap_command(_upload),
            "provider": self._wrap_command(_provider),
            # Shell-specific commands
            "exit": self._exit,
            "quit": self._exit,
            "help": self._help,
            "clear": self._clear,
        }

    def _wrap_command(self, command_func: Callable) -> Callable:
        """Wrap a typer command to work in the shell context."""

        def wrapper(args: list[str]) -> None:
            try:
                # Call the command function directly with parsed arguments
                import storix.cli.app as cli_app

                # Temporarily override the global fs instance to use our shell's fs
                original_fs = cli_app.fs
                cli_app.fs = self.fs

                try:
                    # Parse arguments based on the command
                    cmd_name = command_func.__name__
                    if cmd_name.startswith("_"):
                        cmd_name = cmd_name[1:]  # Remove leading underscore

                    # Call the appropriate command method directly
                    if hasattr(self, f"_call_{cmd_name}"):
                        getattr(self, f"_call_{cmd_name}")(args)
                    else:
                        # Fallback: try to call the function directly with basic argument parsing
                        self._call_generic(command_func, args)

                finally:
                    # Restore the original filesystem instance
                    cli_app.fs = original_fs

            except SystemExit:
                # Ignore SystemExit from typer commands
                pass
            except Exception as e:
                console.print(f"[red]Error executing command: {e}[/red]")

        return wrapper

    def _call_ls(self, args: list[str]) -> None:
        """Call ls command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("path", nargs="?", default=None)
        parser.add_argument("-l", "--long", action="store_true")
        parser.add_argument("-a", "--all", action="store_true")
        parser.add_argument("--color", action="store_true", default=True)
        parser.add_argument("--no-color", dest="color", action="store_false")

        try:
            parsed = parser.parse_args(args)
            path = Path(parsed.path) if parsed.path else None

            from . import app

            app.ls(path, long=parsed.long, all=parsed.all, colors=parsed.color)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]ls: {e}[/red]")

    def _call_pwd(self, args: list[str]) -> None:
        """Call pwd command directly."""
        from . import app

        app.pwd()

    def _call_cd(self, args: list[str]) -> None:
        """Call cd command directly."""
        from pathlib import Path

        path = Path(args[0]) if args else None
        try:
            from . import app

            app.cd(path)
        except Exception as e:
            console.print(f"[red]cd: {e}[/red]")

    def _call_cat(self, args: list[str]) -> None:
        """Call cat command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("files", nargs="+")
        parser.add_argument("-n", "--number", action="store_true")
        parser.add_argument("-b", "--binary", action="store_true")

        try:
            parsed = parser.parse_args(args)
            files = [Path(f) for f in parsed.files]

            from . import app

            app.cat(files, number=parsed.number, binary=parsed.binary)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]cat: {e}[/red]")

    def _call_mkdir(self, args: list[str]) -> None:
        """Call mkdir command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("directories", nargs="+")
        parser.add_argument("-p", "--parents", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            directories = [Path(d) for d in parsed.directories]

            from . import app

            app.mkdir(directories, parents=parsed.parents, verbose=parsed.verbose)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]mkdir: {e}[/red]")

    def _call_touch(self, args: list[str]) -> None:
        """Call touch command directly."""
        from pathlib import Path

        files = [Path(f) for f in args]
        try:
            from . import app

            app.touch(files)
        except Exception as e:
            console.print(f"[red]touch: {e}[/red]")

    def _call_rm(self, args: list[str]) -> None:
        """Call rm command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("files", nargs="+")
        parser.add_argument("-f", "--force", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            files = [Path(f) for f in parsed.files]

            from . import app

            app.rm(files, force=parsed.force, verbose=parsed.verbose)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]rm: {e}[/red]")

    def _call_rmdir(self, args: list[str]) -> None:
        """Call rmdir command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("directories", nargs="+")
        parser.add_argument("-r", "--recursive", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            directories = [Path(d) for d in parsed.directories]

            from . import app

            app.rmdir(directories, recursive=parsed.recursive, verbose=parsed.verbose)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]rmdir: {e}[/red]")

    def _call_cp(self, args: list[str]) -> None:
        """Call cp command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("source")
        parser.add_argument("destination")
        parser.add_argument("-r", "-R", "--recursive", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            source = Path(parsed.source)
            destination = Path(parsed.destination)

            from . import app

            app.cp(
                source, destination, recursive=parsed.recursive, verbose=parsed.verbose
            )
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]cp: {e}[/red]")

    def _call_mv(self, args: list[str]) -> None:
        """Call mv command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("source")
        parser.add_argument("destination")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            source = Path(parsed.source)
            destination = Path(parsed.destination)

            from . import app

            app.mv(source, destination, verbose=parsed.verbose)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]mv: {e}[/red]")

    def _call_echo(self, args: list[str]) -> None:
        """Call echo command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("text")
        parser.add_argument("-f", "--file", type=str)
        parser.add_argument("-a", "--append", action="store_true")

        try:
            parsed = parser.parse_args(args)
            file = Path(parsed.file) if parsed.file else None

            from . import app

            app.echo(parsed.text, file=file, append=parsed.append)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]echo: {e}[/red]")

    def _call_exists(self, args: list[str]) -> None:
        """Call exists command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("paths", nargs="+")
        parser.add_argument("-q", "--quiet", action="store_true")

        try:
            parsed = parser.parse_args(args)
            paths = [Path(p) for p in parsed.paths]

            from . import app

            app.exists(paths, quiet=parsed.quiet)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]exists: {e}[/red]")

    def _call_find(self, args: list[str]) -> None:
        """Call find command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("path", nargs="?", default=None)
        parser.add_argument("-name", type=str)
        parser.add_argument("-type", type=str)

        try:
            parsed = parser.parse_args(args)
            path = Path(parsed.path) if parsed.path else None

            from . import app

            app.find(path, name=parsed.name, type=parsed.type)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]find: {e}[/red]")

    def _call_wc(self, args: list[str]) -> None:
        """Call wc command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("files", nargs="+")
        parser.add_argument("-l", "--lines", action="store_true")
        parser.add_argument("-w", "--words", action="store_true")
        parser.add_argument("-c", "--chars", action="store_true")

        try:
            parsed = parser.parse_args(args)
            files = [Path(f) for f in parsed.files]

            from . import app

            app.wc(files, lines=parsed.lines, words=parsed.words, chars=parsed.chars)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]wc: {e}[/red]")

    def _call_download(self, args: list[str]) -> None:
        """Call download command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("remote_path")
        parser.add_argument("local_path", nargs="?", default=None)
        parser.add_argument("-f", "--force", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            remote_path = Path(parsed.remote_path)
            local_path = Path(parsed.local_path) if parsed.local_path else None

            from . import app

            app.download(
                remote_path, local_path, overwrite=parsed.force, verbose=parsed.verbose
            )
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]download: {e}[/red]")

    def _call_upload(self, args: list[str]) -> None:
        """Call upload command directly."""
        import argparse
        from pathlib import Path

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("local_path")
        parser.add_argument("remote_path", nargs="?", default=None)
        parser.add_argument("-f", "--force", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        try:
            parsed = parser.parse_args(args)
            local_path = Path(parsed.local_path)
            remote_path = Path(parsed.remote_path) if parsed.remote_path else None

            from . import app

            app.upload(
                local_path, remote_path, overwrite=parsed.force, verbose=parsed.verbose
            )
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]upload: {e}[/red]")

    def _call_provider(self, args: list[str]) -> None:
        """Call provider command directly."""
        from . import app

        app.provider()

    def _call_generic(self, command_func: Callable, args: list[str]) -> None:
        """Fallback for commands without specific handlers."""
        try:
            # This is a simplified fallback - for complex commands,
            # we should implement specific _call_* methods
            console.print(
                f"[yellow]Command '{command_func.__name__}' not fully implemented in shell mode[/yellow]"
            )
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def _exit(self, args: list[str]) -> None:
        """Exit the shell."""
        console.print("[yellow]Goodbye![/yellow]")
        self.running = False

    def _help(self, args: list[str]) -> None:
        """Show help information."""
        console.print("[bold blue]Storix Interactive Shell[/bold blue]")
        console.print()
        console.print("[green]Available commands:[/green]")

        # File operations
        console.print("  [cyan]File Operations:[/cyan]")
        console.print(
            "    ls [path] [-l] [-a] [--color/--no-color]  - List directory contents"
        )
        console.print(
            "    cat <files> [-n] [-b]                     - Display file contents"
        )
        console.print(
            "    touch <files>                             - Create empty files"
        )
        console.print("    rm <files> [-f] [-v]                      - Remove files")
        console.print(
            "    cp <source> <dest> [-r] [-v]              - Copy files/directories"
        )
        console.print(
            "    mv <source> <dest> [-v]                   - Move/rename files"
        )
        console.print()

        # Directory operations
        console.print("  [cyan]Directory Operations:[/cyan]")
        console.print(
            "    pwd                                       - Print working directory"
        )
        console.print(
            "    cd [path]                                 - Change directory"
        )
        console.print(
            "    mkdir <dirs> [-p] [-v]                    - Create directories"
        )
        console.print(
            "    rmdir <dirs> [-r] [-v]                    - Remove directories"
        )
        console.print()

        # Utilities
        console.print("  [cyan]Utilities:[/cyan]")
        console.print(
            "    exists <paths> [-q]                       - Check if paths exist"
        )
        console.print(
            "    find [path] [-name pattern] [-type [f, d]]   - Find files/directories"
        )
        console.print(
            "    wc <files> [-l] [-w] [-c]                 - Count lines/words/chars"
        )
        console.print(
            "    echo <text> [-f file] [-a]                - Display text or write to file"
        )
        console.print()

        # Remote operations
        console.print("  [cyan]Remote Operations:[/cyan]")
        console.print(
            "    download <remote> [local] [-f] [-v]       - Download from remote storage"
        )
        console.print(
            "    upload <local> [remote] [-f] [-v]         - Upload to remote storage"
        )
        console.print(
            "    provider                                   - Show current storage provider"
        )
        console.print()

        # Shell commands
        console.print("  [cyan]Shell Commands:[/cyan]")
        console.print("    help                                      - Show this help")
        console.print("    clear                                     - Clear screen")
        console.print("    exit, quit                                - Exit shell")
        console.print()

        provider_type = type(self.fs).__name__
        if provider_type == "LocalFilesystem":
            console.print("[dim]Current provider: Local Filesystem[/dim]")
        else:
            console.print("[dim]Current provider: Azure Data Lake Storage Gen2[/dim]")
        console.print(
            "[dim]Set STORAGE_PROVIDER=azure or =local to change providers[/dim]"
        )

    def _clear(self, args: list[str]) -> None:
        """Clear the screen."""
        os.system("clear" if os.name == "posix" else "cls")

    def _get_prompt(self) -> str:
        """Get the shell prompt."""
        provider_type = type(self.fs).__name__
        provider_char = "📁" if provider_type == "LocalFilesystem" else "☁️"

        current_path = str(self.fs.pwd())
        if len(current_path) > 30:
            current_path = "..." + current_path[-27:]

        return f"{provider_char} {current_path} $ "

    def parse_command(self, line: str) -> tuple[str, list[str]]:
        """Parse a command line into command and arguments."""
        if not line.strip():
            return "", []

        try:
            parts = shlex.split(line)
        except ValueError as e:
            console.print(f"[red]Parse error: {e}[/red]")
            return "", []

        if not parts:
            return "", []

        command = parts[0]
        args = parts[1:]
        return command, args

    def execute_command(self, command: str, args: list[str]) -> None:
        """Execute a shell command."""
        if command in self.commands:
            try:
                self.commands[command](args)  # type: ignore[operator]
            except KeyboardInterrupt:
                console.print("\n[yellow]Command interrupted[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        else:
            console.print(f"[red]Unknown command: {command}[/red]")
            console.print("[dim]Type 'help' for available commands[/dim]")

    def run(self) -> None:
        """Run the interactive shell."""
        # Show welcome message
        console.print("[bold blue]Storix Interactive Shell[/bold blue]")
        provider_type = type(self.fs).__name__
        if provider_type == "LocalFilesystem":
            console.print("Connected to: [green]Local Filesystem[/green]")
        else:
            console.print("Connected to: [green]Azure Data Lake Storage Gen2[/green]")
        console.print("Type 'help' for available commands, 'exit' to quit")
        console.print()

        # Main REPL loop
        while self.running:
            try:
                prompt = self._get_prompt()
                line = Prompt.ask(prompt, default="")

                if not line.strip():
                    continue

                command, args = self.parse_command(line)
                if command:
                    self.execute_command(command, args)

            except KeyboardInterrupt:
                console.print(
                    "\n[yellow]Use 'exit' or 'quit' to leave the shell[/yellow]"
                )
            except EOFError:
                console.print("\n[yellow]Goodbye![/yellow]")
                break


def start_shell(fs: sx.Storage | None = None) -> None:
    """Start the interactive shell."""
    shell = StorixShell(fs)
    shell.run()


if __name__ == "__main__":
    start_shell()
