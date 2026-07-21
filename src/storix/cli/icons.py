"""Nerd Font icon catalog and lookup for sx listings.

Ported directly from eza's icon catalog (eza/src/output/icons.rs).
Uses Nerd Font codepoints organized into structured icon constants (Icons)
and extension/filename lookup tables.
"""

from __future__ import annotations

from typing import Final


# fmt: off
class Icons:
    """Nerd Font glyph constants (eza icon set)."""

    AUDIO: Final[str]           = '\uF001'      # 
    BINARY: Final[str]          = '\uEAE8'      # 
    BOOK: Final[str]            = '\uE28B'      # 
    CALENDAR: Final[str]        = '\uEAB0'      # 
    CACHE: Final[str]           = '\uF49B'      # 
    CAD: Final[str]             = '\U000F0EEB'  # 󰻫
    CLOCK: Final[str]           = '\uF43A'      # 
    COMPRESSED: Final[str]      = '\uF410'      # 
    CONFIG: Final[str]          = '\U000F107B'  # 󱁻
    CSS3: Final[str]            = '\uE749'      # 
    DATABASE: Final[str]        = '\uF1C0'      # 
    DIFF: Final[str]            = '\uF440'      # 
    DISK_IMAGE: Final[str]      = '\uE271'      # 
    DOCKER: Final[str]          = '\uE650'      # 
    DOCUMENT: Final[str]        = '\uF1C2'      # 
    DOWNLOAD: Final[str]        = '\U000F01DA'  # 󰇚
    EDA_SCH: Final[str]         = '\U000F0B45'  # 󰭅
    EDA_PCB: Final[str]         = '\uEABE'      # 
    EMACS: Final[str]           = '\uE632'      # 
    ESLINT: Final[str]          = '\uE655'      # 
    FILE: Final[str]            = '\uF15B'      # 
    FILE_3D: Final[str]         = '\U000F01A7'  # 󰆧
    FOLDER: Final[str]          = '\uE5FF'      # 
    FOLDER_BUILD: Final[str]    = '\U000F19FC'  # 󱧼
    FOLDER_CONFIG: Final[str]   = '\uE5FC'      # 
    FOLDER_EXERCISM: Final[str] = '\uEBE5'      # 
    FOLDER_GIT: Final[str]      = '\uE5FB'      # 
    FOLDER_GITHUB: Final[str]   = '\uE5FD'      # 
    FOLDER_HIDDEN: Final[str]   = '\U000F179E'  # 󱞞
    FOLDER_KEY: Final[str]      = '\U000F08AC'  # 󰢬
    FOLDER_NPM: Final[str]      = '\uE5FA'      # 
    FOLDER_OCAML: Final[str]    = '\uE67A'      # 
    FOLDER_OPEN: Final[str]     = '\uF115'      # 
    FILE_UNKNOWN: Final[str]    = '\U000F086F'  # 󰡯
    FONT: Final[str]            = '\uF031'      # 
    FREECAD: Final[str]         = '\uF336'      # 
    GIMP: Final[str]            = '\uF338'      # 
    GIST_SECRET: Final[str]     = '\uEAFA'      # noqa: S105  # 
    GIT: Final[str]             = '\U000F02A2'  # 󰊢
    GODOT: Final[str]           = '\uE65F'      # 
    GRADLE: Final[str]          = '\uE660'      # 
    GRAPH: Final[str]           = '\U000F1049'  # 󱁉
    GRAPHQL: Final[str]         = '\uE662'      # 
    GRUNT: Final[str]           = '\uE611'      # 
    GTK: Final[str]             = '\uF362'      # 
    GULP: Final[str]            = '\uE610'      # 
    HTML5: Final[str]           = '\uF13B'      # 
    IMAGE: Final[str]           = '\uF1C5'      # 
    INFO: Final[str]            = '\uF129'      # 
    INTELLIJ: Final[str]        = '\uE7B5'      # 
    JSON: Final[str]            = '\uE60B'      # 
    KEY: Final[str]             = '\uEB11'      # 
    KDENLIVE: Final[str]        = '\uF33C'      # 
    KEYPASS: Final[str]         = '\uF23E'      # 
    KICAD: Final[str]           = '\uF34C'      # 
    KRITA: Final[str]           = '\uF33D'      # 
    LANG_ARDUINO: Final[str]    = '\uF34B'      # 
    LANG_ASSEMBLY: Final[str]   = '\uE637'      # 
    LANG_C: Final[str]          = '\uE61E'      # 
    LANG_CPP: Final[str]        = '\uE61D'      # 
    LANG_CSHARP: Final[str]     = '\U000F031B'  # 󰌛
    LANG_D: Final[str]          = '\uE7AF'      # 
    LANG_ELIXIR: Final[str]     = '\uE62D'      # 
    LANG_FENNEL: Final[str]     = '\uE6AF'      # 
    LANG_FORTRAN: Final[str]    = '\U000F121A'  # 󱈚
    LANG_FSHARP: Final[str]     = '\uE7A7'      # 
    LANG_GLEAM: Final[str]      = '\U000F09A5'  # 󰦥
    LANG_GO: Final[str]         = '\uE65E'      # 
    LANG_GROOVY: Final[str]     = '\uE775'      # 
    LANG_HASKELL: Final[str]    = '\uE777'      # 
    LANG_HDL: Final[str]        = '\U000F035B'  # 󰍛
    LANG_HOLYC: Final[str]      = '\U000F00A2'  # 󰂢
    LANG_JAVA: Final[str]       = '\uE256'      # 
    LANG_JAVASCRIPT: Final[str] = '\uE74E'      # 
    LANG_KOTLIN: Final[str]     = '\uE634'      # 
    LANG_LUA: Final[str]        = '\uE620'      # 
    LANG_NIM: Final[str]        = '\uE677'      # 
    LANG_OCAML: Final[str]      = '\uE67A'      # 
    LANG_PERL: Final[str]       = '\uE67E'      # 
    LANG_PHP: Final[str]        = '\uE73D'      # 
    LANG_PYTHON: Final[str]     = '\uE606'      # 
    LANG_R: Final[str]          = '\uE68A'      # 
    LANG_RUBY: Final[str]       = '\uE739'      # 
    LANG_RUBYRAILS: Final[str]  = '\uE73B'      # 
    LANG_RUST: Final[str]       = '\uE68B'      # 
    LANG_SASS: Final[str]       = '\uE603'      # 
    LANG_SCHEME: Final[str]     = '\uE6B1'      # 
    LANG_STYLUS: Final[str]     = '\uE600'      # 
    LANG_TEX: Final[str]        = '\uE69B'      # 
    LANG_TYPESCRIPT: Final[str] = '\uE628'      # 
    LANG_V: Final[str]          = '\uE6AC'      # 
    LIBRARY: Final[str]         = '\uEB9C'      # 
    LICENSE: Final[str]         = '\uF02D'      # 
    LOCK: Final[str]            = '\uF023'      # 
    LOG: Final[str]             = '\uF18D'      # 
    MAKE: Final[str]            = '\uE673'      # 
    MARKDOWN: Final[str]        = '\uF48A'      # 
    MUSTACHE: Final[str]        = '\uE60F'      # 
    NEWS: Final[str]            = '\uF1EA'      # 
    NODEJS: Final[str]          = '\uE718'      # 
    NOTEBOOK: Final[str]        = '\uE678'      # 
    NPM: Final[str]             = '\uE71E'      # 
    OS_ANDROID: Final[str]      = '\uE70E'      # 
    OS_APPLE: Final[str]        = '\uF179'      # 
    OS_LINUX: Final[str]        = '\uF17C'      # 
    OS_WINDOWS: Final[str]      = '\uF17A'      # 
    OS_WINDOWS_CMD: Final[str]  = '\uEBC4'      # 
    PLAYLIST: Final[str]        = '\U000F0CB9'  # 󰲹
    POWERSHELL: Final[str]      = '\uEBC7'      # 
    PRIVATE_KEY: Final[str]     = '\U000F0306'  # 󰌆
    PUBLIC_KEY: Final[str]      = '\U000F0DD6'  # 󰷖
    QT: Final[str]              = '\uF375'      # 
    RAZOR: Final[str]           = '\uF1FA'      # 
    REACT: Final[str]           = '\uE7BA'      # 
    README: Final[str]          = '\U000F00BA'  # 󰂺
    SHEET: Final[str]           = '\uF1C3'      # 
    SHELL: Final[str]           = '\U000F1183'  # 󱆃
    SHELL_CMD: Final[str]       = '\uF489'      # 
    SHIELD_CHECK: Final[str]    = '\U000F0565'  # 󰕥
    SHIELD_KEY: Final[str]      = '\U000F0BC4'  # 󰯄
    SHIELD_LOCK: Final[str]     = '\U000F099D'  # 󰦝
    SIGNED_FILE: Final[str]     = '\U000F19C3'  # 󱧃
    SLIDE: Final[str]           = '\uF1C4'      # 
    SQLITE: Final[str]          = '\uE7C4'      # 
    SUBLIME: Final[str]         = '\uE7AA'      # 
    SUBTITLE: Final[str]        = '\U000F0A16'  # 󰨖
    TCL: Final[str]             = '\U000F06D3'  # 󰛓
    TERRAFORM: Final[str]       = '\U000F1062'  # 󱁢
    TEXT: Final[str]            = '\uF15C'      # 
    TODO: Final[str]            = '\uF0AE'      # 
    TYPST: Final[str]           = '\uF37F'      # 
    TMUX: Final[str]            = '\uEBC8'      # 
    TOML: Final[str]            = '\uE6B2'      # 
    TRANSLATION: Final[str]     = '\U000F05CA'  # 󰗊
    UNITY: Final[str]           = '\uE721'      # 
    VECTOR: Final[str]          = '\U000F0559'  # 󰕙
    VIDEO: Final[str]           = '\uF03D'      # 
    VIM: Final[str]             = '\uE7C5'      # 
    WRENCH: Final[str]          = '\uF0AD'      # 
    XML: Final[str]             = '\U000F05C0'  # 󰗀
    XORG: Final[str]            = '\uF369'      # 
    YAML: Final[str]            = '\uE8EB'      # 
    YARN: Final[str]            = '\uE6A7'      # 
# fmt: on


DIRECTORY_ICONS: Final[dict[str, tuple[str, str]]] = {
    '.config': (Icons.FOLDER_CONFIG, 'bold blue'),
    '.git': (Icons.FOLDER_GIT, 'bold blue'),
    '.github': (Icons.FOLDER_GITHUB, 'bold blue'),
    '.npm': (Icons.FOLDER_NPM, 'bold blue'),
    '.ssh': (Icons.FOLDER_KEY, 'bold blue'),
    'build': (Icons.FOLDER_BUILD, 'bold blue'),
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
    # Archives & Installers
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
    # Programming Languages & Web
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
    entry_name: str,
    is_dir: bool,  # noqa: FBT001
    dir_state: str = 'closed',
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
