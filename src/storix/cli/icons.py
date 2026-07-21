"""Nerd Font icon catalog and lookup for sx listings.

Ported from eza's icon catalog (eza/src/output/icons.rs).
Uses Nerd Font codepoints organized into structured icon constants (Icons)
and extension/filename lookup tables.
"""

from __future__ import annotations

from typing import Final


class Icons:
    """Nerd Font glyph constants (eza icon set)."""

    AUDIO: Final[str] = '\uf001'
    BINARY: Final[str] = '\ueae8'
    BOOK: Final[str] = '\ue28b'
    CALENDAR: Final[str] = '\ueab0'
    COMPRESSED: Final[str] = '\uf410'
    CONFIG: Final[str] = '\uf107b'
    CSS3: Final[str] = '\ue749'
    DATABASE: Final[str] = '\uf1c0'
    DIFF: Final[str] = '\uf440'
    DISK_IMAGE: Final[str] = '\ue271'
    DOCKER: Final[str] = '\ue650'
    DOCUMENT: Final[str] = '\uf1c2'
    DOWNLOAD: Final[str] = '\uf01da'
    EMACS: Final[str] = '\ue632'
    FILE: Final[str] = '\uf15b'
    FOLDER: Final[str] = '\ue5ff'
    FOLDER_CONFIG: Final[str] = '\ue5fc'
    FOLDER_GIT: Final[str] = '\ue5fb'
    FOLDER_GITHUB: Final[str] = '\ue5fd'
    FOLDER_KEY: Final[str] = '\uf08ac'
    FOLDER_NPM: Final[str] = '\ue5fa'
    FOLDER_OPEN: Final[str] = '\uf115'
    FONT: Final[str] = '\uf031'
    GIT: Final[str] = '\uf02a2'
    HTML5: Final[str] = '\uf13b'
    IMAGE: Final[str] = '\uf1c5'
    JSON: Final[str] = '\ue60b'
    KEY: Final[str] = '\ueb11'
    LANG_C: Final[str] = '\ue61e'
    LANG_CPP: Final[str] = '\ue61d'
    LANG_CSHARP: Final[str] = '\uf031b'
    LANG_ELIXIR: Final[str] = '\ue62d'
    LANG_GO: Final[str] = '\ue65e'
    LANG_HASKELL: Final[str] = '\ue777'
    LANG_JAVA: Final[str] = '\ue256'
    LANG_JAVASCRIPT: Final[str] = '\ue74e'
    LANG_KOTLIN: Final[str] = '\ue634'
    LANG_LUA: Final[str] = '\ue620'
    LANG_NIM: Final[str] = '\ue677'
    LANG_OCAML: Final[str] = '\ue67a'
    LANG_PERL: Final[str] = '\ue67e'
    LANG_PHP: Final[str] = '\ue73d'
    LANG_PYTHON: Final[str] = '\ue606'
    LANG_R: Final[str] = '\ue68a'
    LANG_RUBY: Final[str] = '\ue739'
    LANG_RUST: Final[str] = '\ue68b'
    LANG_SASS: Final[str] = '\ue603'
    LANG_TEX: Final[str] = '\ue69b'
    LANG_TYPESCRIPT: Final[str] = '\ue628'
    LIBRARY: Final[str] = '\ueb9c'
    LICENSE: Final[str] = '\uf02d'
    LOCK: Final[str] = '\uf023'
    LOG: Final[str] = '\uf18d'
    MAKE: Final[str] = '\ue673'
    MARKDOWN: Final[str] = '\uf48a'
    NOTEBOOK: Final[str] = '\ue678'
    NPM: Final[str] = '\ue71e'
    OS_APPLE: Final[str] = '\uf179'
    OS_LINUX: Final[str] = '\uf17c'
    OS_WINDOWS: Final[str] = '\uf17a'
    OS_WINDOWS_CMD: Final[str] = '\uebc4'
    PLAYLIST: Final[str] = '\uf0cb9'
    POWERSHELL: Final[str] = '\uebc7'
    REACT: Final[str] = '\ue7ba'
    README: Final[str] = '\uf00ba'
    SHEET: Final[str] = '\uf1c3'
    SHELL: Final[str] = '\uf1183'
    SHELL_CMD: Final[str] = '\uf489'
    SLIDE: Final[str] = '\uf1c4'
    SQLITE: Final[str] = '\ue7c4'
    TEXT: Final[str] = '\uf15c'
    TOML: Final[str] = '\ue6b2'
    VECTOR: Final[str] = '\uf0559'
    VIDEO: Final[str] = '\uf03d'
    VIM: Final[str] = '\ue7c5'
    WRENCH: Final[str] = '\uf0ad'
    XML: Final[str] = '\uf05c0'
    YAML: Final[str] = '\ue8eb'
    YARN: Final[str] = '\ue6a7'


DIRECTORY_ICONS: Final[dict[str, tuple[str, str]]] = {
    '.config': (Icons.FOLDER_CONFIG, 'bold blue'),
    '.git': (Icons.FOLDER_GIT, 'bold blue'),
    '.github': (Icons.FOLDER_GITHUB, 'bold blue'),
    '.npm': (Icons.FOLDER_NPM, 'bold blue'),
    '.ssh': (Icons.FOLDER_KEY, 'bold blue'),
    'build': (Icons.CONFIG, 'bold blue'),
    'config': (Icons.FOLDER_CONFIG, 'bold blue'),
    'node_modules': (Icons.FOLDER_NPM, 'bold blue'),
    'src': (Icons.WRENCH, 'bold blue'),
    'Downloads': (Icons.DOWNLOAD, 'bold blue'),
    'Music': (Icons.AUDIO, 'bold blue'),
    'Pictures': (Icons.IMAGE, 'bold blue'),
    'Videos': (Icons.VIDEO, 'bold blue'),
}

EXTENSION_ICONS: Final[dict[str, tuple[str, str]]] = {
    # Audio
    'aac': (Icons.AUDIO, 'magenta'),
    'flac': (Icons.AUDIO, 'magenta'),
    'm4a': (Icons.AUDIO, 'magenta'),
    'mid': (Icons.AUDIO, 'magenta'),
    'midi': (Icons.AUDIO, 'magenta'),
    'mp3': (Icons.AUDIO, 'magenta'),
    'ogg': (Icons.AUDIO, 'magenta'),
    'opus': (Icons.AUDIO, 'magenta'),
    'wav': (Icons.AUDIO, 'magenta'),
    'wma': (Icons.AUDIO, 'magenta'),
    # Video
    'avi': (Icons.VIDEO, 'magenta'),
    'flv': (Icons.VIDEO, 'magenta'),
    'm4v': (Icons.VIDEO, 'magenta'),
    'mkv': (Icons.VIDEO, 'magenta'),
    'mov': (Icons.VIDEO, 'magenta'),
    'mp4': (Icons.VIDEO, 'magenta'),
    'mpeg': (Icons.VIDEO, 'magenta'),
    'mpg': (Icons.VIDEO, 'magenta'),
    'webm': (Icons.VIDEO, 'magenta'),
    'wmv': (Icons.VIDEO, 'magenta'),
    # Images
    'avif': (Icons.IMAGE, 'bright_magenta'),
    'bmp': (Icons.IMAGE, 'bright_magenta'),
    'gif': (Icons.IMAGE, 'bright_magenta'),
    'heic': (Icons.IMAGE, 'bright_magenta'),
    'ico': (Icons.IMAGE, 'bright_magenta'),
    'jpeg': (Icons.IMAGE, 'bright_magenta'),
    'jpg': (Icons.IMAGE, 'bright_magenta'),
    'png': (Icons.IMAGE, 'bright_magenta'),
    'psd': (Icons.IMAGE, 'bright_magenta'),
    'svg': (Icons.VECTOR, 'bright_magenta'),
    'tiff': (Icons.IMAGE, 'bright_magenta'),
    'webp': (Icons.IMAGE, 'bright_magenta'),
    # Archives
    '7z': (Icons.COMPRESSED, 'red'),
    'bz2': (Icons.COMPRESSED, 'red'),
    'deb': (Icons.COMPRESSED, 'red'),
    'gz': (Icons.COMPRESSED, 'red'),
    'iso': (Icons.DISK_IMAGE, 'red'),
    'jar': (Icons.LANG_JAVA, 'red'),
    'rar': (Icons.COMPRESSED, 'red'),
    'rpm': (Icons.COMPRESSED, 'red'),
    'tar': (Icons.COMPRESSED, 'red'),
    'tgz': (Icons.COMPRESSED, 'red'),
    'xz': (Icons.COMPRESSED, 'red'),
    'zip': (Icons.COMPRESSED, 'red'),
    'zst': (Icons.COMPRESSED, 'red'),
    # Code & Languages
    'c': (Icons.LANG_C, 'green'),
    'cc': (Icons.LANG_CPP, 'green'),
    'clj': (Icons.FILE, 'green'),
    'cpp': (Icons.LANG_CPP, 'green'),
    'cs': (Icons.LANG_CSHARP, 'green'),
    'css': (Icons.CSS3, 'green'),
    'dart': (Icons.FILE, 'green'),
    'elixir': (Icons.LANG_ELIXIR, 'green'),
    'ex': (Icons.LANG_ELIXIR, 'green'),
    'exs': (Icons.LANG_ELIXIR, 'green'),
    'go': (Icons.LANG_GO, 'green'),
    'h': (Icons.LANG_C, 'green'),
    'hpp': (Icons.LANG_CPP, 'green'),
    'hs': (Icons.LANG_HASKELL, 'green'),
    'htm': (Icons.HTML5, 'green'),
    'html': (Icons.HTML5, 'green'),
    'java': (Icons.LANG_JAVA, 'green'),
    'jl': (Icons.FILE, 'green'),
    'js': (Icons.LANG_JAVASCRIPT, 'green'),
    'jsx': (Icons.REACT, 'green'),
    'kt': (Icons.LANG_KOTLIN, 'green'),
    'kts': (Icons.LANG_KOTLIN, 'green'),
    'lua': (Icons.LANG_LUA, 'green'),
    'mjs': (Icons.LANG_JAVASCRIPT, 'green'),
    'nim': (Icons.LANG_NIM, 'green'),
    'php': (Icons.LANG_PHP, 'green'),
    'pl': (Icons.LANG_PERL, 'green'),
    'py': (Icons.LANG_PYTHON, 'green'),
    'pyi': (Icons.LANG_PYTHON, 'green'),
    'r': (Icons.LANG_R, 'green'),
    'rb': (Icons.LANG_RUBY, 'green'),
    'rs': (Icons.LANG_RUST, 'green'),
    'sass': (Icons.LANG_SASS, 'green'),
    'scala': (Icons.LANG_JAVA, 'green'),
    'scss': (Icons.LANG_SASS, 'green'),
    'sh': (Icons.SHELL_CMD, 'green'),
    'bash': (Icons.SHELL_CMD, 'green'),
    'zsh': (Icons.SHELL_CMD, 'green'),
    'fish': (Icons.SHELL_CMD, 'green'),
    'ps1': (Icons.POWERSHELL, 'green'),
    'sql': (Icons.DATABASE, 'green'),
    'svelte': (Icons.FILE, 'green'),
    'swift': (Icons.FILE, 'green'),
    'ts': (Icons.LANG_TYPESCRIPT, 'green'),
    'tsx': (Icons.REACT, 'green'),
    'vim': (Icons.VIM, 'green'),
    'vue': (Icons.FILE, 'green'),
    'zig': (Icons.FILE, 'green'),
    # Config & Data
    'cfg': (Icons.CONFIG, 'cyan'),
    'conf': (Icons.CONFIG, 'cyan'),
    'csv': (Icons.SHEET, 'cyan'),
    'env': (Icons.CONFIG, 'cyan'),
    'ini': (Icons.CONFIG, 'cyan'),
    'json': (Icons.JSON, 'cyan'),
    'jsonc': (Icons.JSON, 'cyan'),
    'lock': (Icons.LOCK, 'cyan'),
    'toml': (Icons.TOML, 'cyan'),
    'tsv': (Icons.SHEET, 'cyan'),
    'xml': (Icons.XML, 'cyan'),
    'yaml': (Icons.YAML, 'cyan'),
    'yml': (Icons.YAML, 'cyan'),
    # Documents
    'doc': (Icons.DOCUMENT, ''),
    'docx': (Icons.DOCUMENT, ''),
    'epub': (Icons.BOOK, ''),
    'ipynb': (Icons.NOTEBOOK, 'green'),
    'log': (Icons.LOG, 'dim'),
    'md': (Icons.MARKDOWN, ''),
    'mdx': (Icons.MARKDOWN, ''),
    'pdf': (Icons.DOCUMENT, 'red'),
    'ppt': (Icons.SLIDE, ''),
    'pptx': (Icons.SLIDE, ''),
    'rst': (Icons.TEXT, ''),
    'txt': (Icons.TEXT, ''),
    'xls': (Icons.SHEET, 'cyan'),
    'xlsx': (Icons.SHEET, 'cyan'),
    # Binaries & System
    'a': (Icons.LIBRARY, 'dim'),
    'bin': (Icons.BINARY, 'dim'),
    'class': (Icons.LANG_JAVA, 'dim'),
    'db': (Icons.DATABASE, 'dim'),
    'dll': (Icons.LIBRARY, 'dim'),
    'dylib': (Icons.LIBRARY, 'dim'),
    'exe': (Icons.OS_WINDOWS_CMD, 'dim'),
    'o': (Icons.BINARY, 'dim'),
    'pyc': (Icons.LANG_PYTHON, 'dim'),
    'so': (Icons.LIBRARY, 'dim'),
    'sqlite': (Icons.SQLITE, 'dim'),
    'wasm': (Icons.BINARY, 'dim'),
    # Fonts
    'eot': (Icons.FONT, ''),
    'otf': (Icons.FONT, ''),
    'ttf': (Icons.FONT, ''),
    'woff': (Icons.FONT, ''),
    'woff2': (Icons.FONT, ''),
}

FILENAME_ICONS: Final[dict[str, tuple[str, str]]] = {
    '.bashrc': (Icons.SHELL, ''),
    '.editorconfig': (Icons.CONFIG, 'cyan'),
    '.env': (Icons.CONFIG, 'cyan'),
    '.gitattributes': (Icons.GIT, ''),
    '.gitignore': (Icons.GIT, ''),
    '.gitmodules': (Icons.GIT, ''),
    '.zshrc': (Icons.SHELL, ''),
    'Cargo.lock': (Icons.LANG_RUST, 'cyan'),
    'Cargo.toml': (Icons.LANG_RUST, 'cyan'),
    'Dockerfile': (Icons.DOCKER, ''),
    'Justfile': (Icons.WRENCH, ''),
    'LICENSE': (Icons.LICENSE, ''),
    'Makefile': (Icons.MAKE, ''),
    'Procfile': (Icons.CONFIG, ''),
    'README': (Icons.README, ''),
    'README.md': (Icons.README, ''),
    'compose.yaml': (Icons.DOCKER, 'cyan'),
    'docker-compose.yml': (Icons.DOCKER, 'cyan'),
    'justfile': (Icons.WRENCH, ''),
    'makefile': (Icons.MAKE, ''),
    'package-lock.json': (Icons.NPM, 'cyan'),
    'package.json': (Icons.NPM, 'cyan'),
    'pyproject.toml': (Icons.LANG_PYTHON, 'cyan'),
    'requirements.txt': (Icons.LANG_PYTHON, ''),
    'uv.lock': (Icons.LOCK, 'cyan'),
    'yarn.lock': (Icons.YARN, 'cyan'),
}


def lookup_entry_decor(
    entry_name: str, is_dir: bool, dir_state: str = 'closed'
) -> tuple[str, str]:
    """Look up the (icon, style) pair for an entry using eza-style rules.

    Args:
        entry_name: Basename of the file or directory.
        is_dir: True if entry is a directory.
        dir_state: Directory state ('closed', 'empty', or 'full').

    Returns:
        A tuple of (glyph, rich_style).
    """
    if is_dir:
        dir_decor = DIRECTORY_ICONS.get(entry_name)
        if dir_decor is not None:
            return dir_decor
        icon = Icons.FOLDER_OPEN if dir_state == 'empty' else Icons.FOLDER
        return icon, 'bold blue'

    if entry_name in FILENAME_ICONS:
        return FILENAME_ICONS[entry_name]

    ext = entry_name.rpartition('.')[2].lower() if '.' in entry_name else ''
    if ext and ext in EXTENSION_ICONS:
        return EXTENSION_ICONS[ext]

    return Icons.FILE, ''
