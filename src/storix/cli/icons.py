"""Nerd Font icon catalog and lookup for sx listings.

Ported directly from eza's icon catalog (eza/src/output/icons.rs).
Uses Nerd Font codepoints organized into structured icon constants (Icons)
and extension/filename lookup tables.
"""

from __future__ import annotations

from typing import Final


class Icons:
    """Nerd Font glyph constants (eza icon set)."""

    AUDIO: Final[str] = '\uf001'  # 
    BINARY: Final[str] = '\ueae8'  # 
    BOOK: Final[str] = '\ue28b'  # 
    CALENDAR: Final[str] = '\ueab0'  # 
    CACHE: Final[str] = '\uf49b'  # 
    CAD: Final[str] = '\U000f0eeb'  # 󰻫
    CLOCK: Final[str] = '\uf43a'  # 
    COMPRESSED: Final[str] = '\uf410'  # 
    CONFIG: Final[str] = '\U000f107b'  # 󱁻
    CSS3: Final[str] = '\ue749'  # 
    DATABASE: Final[str] = '\uf1c0'  # 
    DIFF: Final[str] = '\uf440'  # 
    DISK_IMAGE: Final[str] = '\ue271'  # 
    DOCKER: Final[str] = '\ue650'  # 
    DOCUMENT: Final[str] = '\uf1c2'  # 
    DOWNLOAD: Final[str] = '\U000f01da'  # 󰇚
    EDA_SCH: Final[str] = '\U000f0b45'  # 󰭅
    EDA_PCB: Final[str] = '\ueabe'  # 
    EMACS: Final[str] = '\ue632'  # 
    ESLINT: Final[str] = '\ue655'  # 
    FILE: Final[str] = '\uf15b'  # 
    FILE_3D: Final[str] = '\U000f01a7'  # 󰆧
    FOLDER: Final[str] = '\ue5ff'  # 
    FOLDER_BUILD: Final[str] = '\U000f19fc'  # 󱧼
    FOLDER_CONFIG: Final[str] = '\ue5fc'  # 
    FOLDER_EXERCISM: Final[str] = '\uebe5'  # 
    FOLDER_GIT: Final[str] = '\ue5fb'  # 
    FOLDER_GITHUB: Final[str] = '\ue5fd'  # 
    FOLDER_HIDDEN: Final[str] = '\U000f179e'  # 󱞞
    FOLDER_KEY: Final[str] = '\U000f08ac'  # 󰢬
    FOLDER_NPM: Final[str] = '\ue5fa'  # 
    FOLDER_OCAML: Final[str] = '\ue67a'  # 
    FOLDER_OPEN: Final[str] = '\uf115'  # 
    FILE_UNKNOWN: Final[str] = '\U000f086f'  # 󰡯
    FONT: Final[str] = '\uf031'  # 
    FREECAD: Final[str] = '\uf336'  # 
    GIMP: Final[str] = '\uf338'  # 
    GIST_SECRET: Final[str] = '\ueafa'  # noqa: S105  # 
    GIT: Final[str] = '\U000f02a2'  # 󰊢
    GODOT: Final[str] = '\ue65f'  # 
    GRADLE: Final[str] = '\ue660'  # 
    GRAPH: Final[str] = '\U000f1049'  # 󱁉
    GRAPHQL: Final[str] = '\ue662'  # 
    GRUNT: Final[str] = '\ue611'  # 
    GTK: Final[str] = '\uf362'  # 
    GULP: Final[str] = '\ue610'  # 
    HTML5: Final[str] = '\uf13b'  # 
    IMAGE: Final[str] = '\uf1c5'  # 
    INFO: Final[str] = '\uf129'  # 
    INTELLIJ: Final[str] = '\ue7b5'  # 
    JSON: Final[str] = '\ue60b'  # 
    KEY: Final[str] = '\ueb11'  # 
    KDENLIVE: Final[str] = '\uf33c'  # 
    KEYPASS: Final[str] = '\uf23e'  # 
    KICAD: Final[str] = '\uf34c'  # 
    KRITA: Final[str] = '\uf33d'  # 
    LANG_ARDUINO: Final[str] = '\uf34b'  # 
    LANG_ASSEMBLY: Final[str] = '\ue637'  # 
    LANG_C: Final[str] = '\ue61e'  # 
    LANG_CPP: Final[str] = '\ue61d'  # 
    LANG_CSHARP: Final[str] = '\U000f031b'  # 󰌛
    LANG_D: Final[str] = '\ue7af'  # 
    LANG_ELIXIR: Final[str] = '\ue62d'  # 
    LANG_FENNEL: Final[str] = '\ue6af'  # 
    LANG_FORTRAN: Final[str] = '\U000f121a'  # 󱈚
    LANG_FSHARP: Final[str] = '\ue7a7'  # 
    LANG_GLEAM: Final[str] = '\U000f09a5'  # 󰦥
    LANG_GO: Final[str] = '\ue65e'  # 
    LANG_GROOVY: Final[str] = '\ue775'  # 
    LANG_HASKELL: Final[str] = '\ue777'  # 
    LANG_HDL: Final[str] = '\U000f035b'  # 󰍛
    LANG_HOLYC: Final[str] = '\U000f00a2'  # 󰂢
    LANG_JAVA: Final[str] = '\ue256'  # 
    LANG_JAVASCRIPT: Final[str] = '\ue74e'  # 
    LANG_KOTLIN: Final[str] = '\ue634'  # 
    LANG_LUA: Final[str] = '\ue620'  # 
    LANG_NIM: Final[str] = '\ue677'  # 
    LANG_OCAML: Final[str] = '\ue67a'  # 
    LANG_PERL: Final[str] = '\ue67e'  # 
    LANG_PHP: Final[str] = '\ue73d'  # 
    LANG_PYTHON: Final[str] = '\ue606'  # 
    LANG_R: Final[str] = '\ue68a'  # 
    LANG_RUBY: Final[str] = '\ue739'  # 
    LANG_RUBYRAILS: Final[str] = '\ue73b'  # 
    LANG_RUST: Final[str] = '\ue68b'  # 
    LANG_SASS: Final[str] = '\ue603'  # 
    LANG_SCHEME: Final[str] = '\ue6b1'  # 
    LANG_STYLUS: Final[str] = '\ue600'  # 
    LANG_TEX: Final[str] = '\ue69b'  # 
    LANG_TYPESCRIPT: Final[str] = '\ue628'  # 
    LANG_V: Final[str] = '\ue6ac'  # 
    LIBRARY: Final[str] = '\ueb9c'  # 
    LICENSE: Final[str] = '\uf02d'  # 
    LOCK: Final[str] = '\uf023'  # 
    LOG: Final[str] = '\uf18d'  # 
    MAKE: Final[str] = '\ue673'  # 
    MARKDOWN: Final[str] = '\uf48a'  # 
    MUSTACHE: Final[str] = '\ue60f'  # 
    NEWS: Final[str] = '\uf1ea'  # 
    NODEJS: Final[str] = '\ue718'  # 
    NOTEBOOK: Final[str] = '\ue678'  # 
    NPM: Final[str] = '\ue71e'  # 
    OS_ANDROID: Final[str] = '\ue70e'  # 
    OS_APPLE: Final[str] = '\uf179'  # 
    OS_LINUX: Final[str] = '\uf17c'  # 
    OS_WINDOWS: Final[str] = '\uf17a'  # 
    OS_WINDOWS_CMD: Final[str] = '\uebc4'  # 
    PLAYLIST: Final[str] = '\U000f0cb9'  # 󰲹
    POWERSHELL: Final[str] = '\uebc7'  # 
    PRIVATE_KEY: Final[str] = '\U000f0306'  # 󰌆
    PUBLIC_KEY: Final[str] = '\U000f0dd6'  # 󰷖
    QT: Final[str] = '\uf375'  # 
    RAZOR: Final[str] = '\uf1fa'  # 
    REACT: Final[str] = '\ue7ba'  # 
    README: Final[str] = '\U000f00ba'  # 󰂺
    SHEET: Final[str] = '\uf1c3'  # 
    SHELL: Final[str] = '\U000f1183'  # 󱆃
    SHELL_CMD: Final[str] = '\uf489'  # 
    SHIELD_CHECK: Final[str] = '\U000f0565'  # 󰕥
    SHIELD_KEY: Final[str] = '\U000f0bc4'  # 󰯄
    SHIELD_LOCK: Final[str] = '\U000f099d'  # 󰦝
    SIGNED_FILE: Final[str] = '\U000f19c3'  # 󱧃
    SLIDE: Final[str] = '\uf1c4'  # 
    SQLITE: Final[str] = '\ue7c4'  # 
    SUBLIME: Final[str] = '\ue7aa'  # 
    SUBTITLE: Final[str] = '\U000f0a16'  # 󰨖
    TCL: Final[str] = '\U000f06d3'  # 󰛓
    TERRAFORM: Final[str] = '\U000f1062'  # 󱁢
    TEXT: Final[str] = '\uf15c'  # 
    TODO: Final[str] = '\uf0ae'  # 
    TYPST: Final[str] = '\uf37f'  # 
    TMUX: Final[str] = '\uebc8'  # 
    TOML: Final[str] = '\ue6b2'  # 
    TRANSLATION: Final[str] = '\U000f05ca'  # 󰗊
    UNITY: Final[str] = '\ue721'  # 
    VECTOR: Final[str] = '\U000f0559'  # 󰕙
    VIDEO: Final[str] = '\uf03d'  # 
    VIM: Final[str] = '\ue7c5'  # 
    WRENCH: Final[str] = '\uf0ad'  # 
    XML: Final[str] = '\U000f05c0'  # 󰗀
    XORG: Final[str] = '\uf369'  # 
    YAML: Final[str] = '\ue8eb'  # 
    YARN: Final[str] = '\ue6a7'  # 


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
