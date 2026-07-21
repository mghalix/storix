# ruff: noqa: S105
"""Nerd Font icon catalog and lookup for sx listings.

Ported 100% complete from eza's icon catalog (eza/src/output/icons.rs).
Uses Nerd Font codepoints organized into structured icon constants (Icons)
and complete extension/filename/directory lookup tables.
"""

from __future__ import annotations

from typing import Final


# fmt: off
class Icons:
    """Nerd Font glyph constants (complete eza icon set)."""

    AUDIO: Final[str]           = '\uF001'  # 
    BINARY: Final[str]          = '\uEAE8'  # 
    BOOK: Final[str]            = '\uE28B'  # 
    CALENDAR: Final[str]        = '\uEAB0'  # 
    CACHE: Final[str]           = '\uF49B'  # 
    CAD: Final[str]             = '\U000F0EEB'  # 󰻫
    CLOCK: Final[str]           = '\uF43A'  # 
    COMPRESSED: Final[str]      = '\uF410'  # 
    CONFIG: Final[str]          = '\U000F107B'  # 󱁻
    CSS3: Final[str]            = '\uE749'  # 
    DATABASE: Final[str]        = '\uF1C0'  # 
    DIFF: Final[str]            = '\uF440'  # 
    DISK_IMAGE: Final[str]      = '\uE271'  # 
    DOCKER: Final[str]          = '\uE650'  # 
    DOCUMENT: Final[str]        = '\uF1C2'  # 
    DOWNLOAD: Final[str]        = '\U000F01DA'  # 󰇚
    EDA_SCH: Final[str]         = '\U000F0B45'  # 󰭅
    EDA_PCB: Final[str]         = '\uEABE'  # 
    EMACS: Final[str]           = '\uE632'  # 
    ESLINT: Final[str]          = '\uE655'  # 
    FILE: Final[str]            = '\uF15B'  # 
    FILE_3D: Final[str]         = '\U000F01A7'  # 󰆧
    FOLDER: Final[str]          = '\uE5FF'  # 
    FOLDER_BUILD: Final[str]    = '\U000F19FC'  # 󱧼
    FOLDER_CONFIG: Final[str]   = '\uE5FC'  # 
    FOLDER_EXERCISM: Final[str] = '\uEBE5'  # 
    FOLDER_GIT: Final[str]      = '\uE5FB'  # 
    FOLDER_GITHUB: Final[str]   = '\uE5FD'  # 
    FOLDER_HIDDEN: Final[str]   = '\U000F179E'  # 󱞞
    FOLDER_KEY: Final[str]      = '\U000F08AC'  # 󰢬
    FOLDER_NPM: Final[str]      = '\uE5FA'  # 
    FOLDER_OCAML: Final[str]    = '\uE67A'  # 
    FOLDER_OPEN: Final[str]     = '\uF115'  # 
    FILE_UNKNOW: Final[str]     = '\U000F086F'  # 󰡯
    FONT: Final[str]            = '\uF031'  # 
    FREECAD: Final[str]         = '\uF336'  # 
    GIMP: Final[str]            = '\uF338'  # 
    GIST_SECRET: Final[str]     = '\uEAFA'  # 
    GIT: Final[str]             = '\U000F02A2'  # 󰊢
    GODOT: Final[str]           = '\uE65F'  # 
    GRADLE: Final[str]          = '\uE660'  # 
    GRAPH: Final[str]           = '\U000F1049'  # 󱁉
    GRAPHQL: Final[str]         = '\uE662'  # 
    GRUNT: Final[str]           = '\uE611'  # 
    GTK: Final[str]             = '\uF362'  # 
    GULP: Final[str]            = '\uE610'  # 
    HTML5: Final[str]           = '\uF13B'  # 
    IMAGE: Final[str]           = '\uF1C5'  # 
    INFO: Final[str]            = '\uF129'  # 
    INTELLIJ: Final[str]        = '\uE7B5'  # 
    JSON: Final[str]            = '\uE60B'  # 
    KEY: Final[str]             = '\uEB11'  # 
    KDENLIVE: Final[str]        = '\uF33C'  # 
    KEYPASS: Final[str]         = '\uF23E'  # 
    KICAD: Final[str]           = '\uF34C'  # 
    KRITA: Final[str]           = '\uF33D'  # 
    LANG_ARDUINO: Final[str]    = '\uF34B'  # 
    LANG_ASSEMBLY: Final[str]   = '\uE637'  # 
    LANG_C: Final[str]          = '\uE61E'  # 
    LANG_CPP: Final[str]        = '\uE61D'  # 
    LANG_CSHARP: Final[str]     = '\U000F031B'  # 󰌛
    LANG_D: Final[str]          = '\uE7AF'  # 
    LANG_ELIXIR: Final[str]     = '\uE62D'  # 
    LANG_FENNEL: Final[str]     = '\uE6AF'  # 
    LANG_FORTRAN: Final[str]    = '\U000F121A'  # 󱈚
    LANG_FSHARP: Final[str]     = '\uE7A7'  # 
    LANG_GLEAM: Final[str]      = '\U000F09A5'  # 󰦥
    LANG_GO: Final[str]         = '\uE65E'  # 
    LANG_GROOVY: Final[str]     = '\uE775'  # 
    LANG_HASKELL: Final[str]    = '\uE777'  # 
    LANG_HDL: Final[str]        = '\U000F035B'  # 󰍛
    LANG_HOLYC: Final[str]      = '\U000F00A2'  # 󰂢
    LANG_JAVA: Final[str]       = '\uE256'  # 
    LANG_JAVASCRIPT: Final[str] = '\uE74E'  # 
    LANG_KOTLIN: Final[str]     = '\uE634'  # 
    LANG_LUA: Final[str]        = '\uE620'  # 
    LANG_NIM: Final[str]        = '\uE677'  # 
    LANG_OCAML: Final[str]      = '\uE67A'  # 
    LANG_PERL: Final[str]       = '\uE67E'  # 
    LANG_PHP: Final[str]        = '\uE73D'  # 
    LANG_PYTHON: Final[str]     = '\uE606'  # 
    LANG_R: Final[str]          = '\uE68A'  # 
    LANG_RUBY: Final[str]       = '\uE739'  # 
    LANG_RUBYRAILS: Final[str]  = '\uE73B'  # 
    LANG_RUST: Final[str]       = '\uE68B'  # 
    LANG_SASS: Final[str]       = '\uE603'  # 
    LANG_SCHEME: Final[str]     = '\uE6B1'  # 
    LANG_STYLUS: Final[str]     = '\uE600'  # 
    LANG_TEX: Final[str]        = '\uE69B'  # 
    LANG_TYPESCRIPT: Final[str] = '\uE628'  # 
    LANG_V: Final[str]          = '\uE6AC'  # 
    LIBRARY: Final[str]         = '\uEB9C'  # 
    LICENSE: Final[str]         = '\uF02D'  # 
    LOCK: Final[str]            = '\uF023'  # 
    LOG: Final[str]             = '\uF18D'  # 
    MAKE: Final[str]            = '\uE673'  # 
    MARKDOWN: Final[str]        = '\uF48A'  # 
    MUSTACHE: Final[str]        = '\uE60F'  # 
    NEWS: Final[str]            = '\uF1EA'  # 
    NODEJS: Final[str]          = '\uE718'  # 
    NOTEBOOK: Final[str]        = '\uE678'  # 
    NPM: Final[str]             = '\uE71E'  # 
    OS_ANDROID: Final[str]      = '\uE70E'  # 
    OS_APPLE: Final[str]        = '\uF179'  # 
    OS_LINUX: Final[str]        = '\uF17C'  # 
    OS_WINDOWS: Final[str]      = '\uF17A'  # 
    OS_WINDOWS_CMD: Final[str]  = '\uEBC4'  # 
    PLAYLIST: Final[str]        = '\U000F0CB9'  # 󰲹
    POWERSHELL: Final[str]      = '\uEBC7'  # 
    PRIVATE_KEY: Final[str]     = '\U000F0306'  # 󰌆
    PUBLIC_KEY: Final[str]      = '\U000F0DD6'  # 󰷖
    QT: Final[str]              = '\uF375'  # 
    RAZOR: Final[str]           = '\uF1FA'  # 
    REACT: Final[str]           = '\uE7BA'  # 
    README: Final[str]          = '\U000F00BA'  # 󰂺
    SHEET: Final[str]           = '\uF1C3'  # 
    SHELL: Final[str]           = '\U000F1183'  # 󱆃
    SHELL_CMD: Final[str]       = '\uF489'  # 
    SHIELD_CHECK: Final[str]    = '\U000F0565'  # 󰕥
    SHIELD_KEY: Final[str]      = '\U000F0BC4'  # 󰯄
    SHIELD_LOCK: Final[str]     = '\U000F099D'  # 󰦝
    SIGNED_FILE: Final[str]     = '\U000F19C3'  # 󱧃
    SLIDE: Final[str]           = '\uF1C4'  # 
    SQLITE: Final[str]          = '\uE7C4'  # 
    SUBLIME: Final[str]         = '\uE7AA'  # 
    SUBTITLE: Final[str]        = '\U000F0A16'  # 󰨖
    TCL: Final[str]             = '\U000F06D3'  # 󰛓
    TERRAFORM: Final[str]       = '\U000F1062'  # 󱁢
    TEXT: Final[str]            = '\uF15C'  # 
    TODO: Final[str]            = '\uF0AE'  # 
    TYPST: Final[str]           = '\uF37F'  # 
    TMUX: Final[str]            = '\uEBC8'  # 
    TOML: Final[str]            = '\uE6B2'  # 
    TRANSLATION: Final[str]     = '\U000F05CA'  # 󰗊
    UNITY: Final[str]           = '\uE721'  # 
    VECTOR: Final[str]          = '\U000F0559'  # 󰕙
    VIDEO: Final[str]           = '\uF03D'  # 
    VIM: Final[str]             = '\uE7C5'  # 
    WRENCH: Final[str]          = '\uF0AD'  # 
    XML: Final[str]             = '\U000F05C0'  # 󰗀
    XORG: Final[str]            = '\uF369'  # 
    YAML: Final[str]            = '\uE8EB'  # 
    YARN: Final[str]            = '\uE6A7'  # 
# fmt: on


DIRECTORY_ICONS: Final[dict[str, tuple[str, str]]] = {
    '.config': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    '.exercism': (Icons.FOLDER_EXERCISM, 'bold blue'),  # 
    '.git': (Icons.FOLDER_GIT, 'bold blue'),  # 
    '.github': (Icons.FOLDER_GITHUB, 'bold blue'),  # 
    '.npm': (Icons.FOLDER_NPM, 'bold blue'),  # 
    '.opam': (Icons.FOLDER_OCAML, 'bold blue'),  # 
    '.ssh': (Icons.FOLDER_KEY, 'bold blue'),  # 󰢬
    '.Trash': ('\uf1f8', 'bold blue'),  # 
    'build': (Icons.FOLDER_BUILD, 'bold blue'),  # 󱧼
    'config': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'Contacts': ('\U000f024c', 'bold blue'),  # 󰉌
    'cron.d': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'cron.daily': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'cron.hourly': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'cron.minutely': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'cron.monthly': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'cron.weekly': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'Desktop': ('\uf108', 'bold blue'),  # 
    'Documents': ('\U000f0c82', 'bold blue'),  # 󰲂
    'Downloads': ('\U000f024d', 'bold blue'),  # 󰉍
    'etc': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'Favorites': ('\U000f069d', 'bold blue'),  # 󰚝
    'hidden': (Icons.FOLDER_HIDDEN, 'bold blue'),  # 󱞞
    'home': ('\U000f10b5', 'bold blue'),  # 󱂵
    'include': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'Mail': ('\U000f01f0', 'bold blue'),  # 󰇰
    'Movies': ('\U000f0fce', 'bold blue'),  # 󰿎
    'Music': ('\U000f1359', 'bold blue'),  # 󱍙
    'node_modules': (Icons.FOLDER_NPM, 'bold blue'),  # 
    'npm_cache': (Icons.FOLDER_NPM, 'bold blue'),  # 
    'pacman.d': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'pam.d': (Icons.FOLDER_KEY, 'bold blue'),  # 󰢬
    'Pictures': ('\U000f024f', 'bold blue'),  # 󰉏
    'src': ('\U000f08de', 'bold blue'),  # 󰣞
    'ssh': (Icons.FOLDER_KEY, 'bold blue'),  # 󰢬
    'sudoers.d': (Icons.FOLDER_KEY, 'bold blue'),  # 󰢬
    'Videos': ('\uf03d', 'bold blue'),  # 
    'xbps.d': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'xorg.conf.d': (Icons.FOLDER_CONFIG, 'bold blue'),  # 
    'cabal': (Icons.LANG_HASKELL, 'bold blue'),  # 
}

FILENAME_ICONS: Final[dict[str, tuple[str, str]]] = {
    '.aliases': (Icons.SHELL, ''),  # 󱆃
    '.atom': ('\ue764', ''),  # 
    '.bashrc': (Icons.SHELL, ''),  # 󱆃
    '.bash_aliases': (Icons.SHELL, ''),  # 󱆃
    '.bash_history': (Icons.SHELL, ''),  # 󱆃
    '.bash_logout': (Icons.SHELL, ''),  # 󱆃
    '.bash_profile': (Icons.SHELL, ''),  # 󱆃
    '.CFUserTextEncoding': (Icons.OS_APPLE, ''),  # 
    '.clang-format': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.clang-tidy': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.codespellrc': ('\U000f04c6', ''),  # 󰓆
    '.condarc': ('\ue715', ''),  # 
    '.cshrc': (Icons.SHELL, ''),  # 󱆃
    '.DS_Store': (Icons.OS_APPLE, ''),  # 
    '.editorconfig': ('\ue652', ''),  # 
    '.emacs': (Icons.EMACS, 'green'),  # 
    '.envrc': ('\uf462', ''),  # 
    '.eslintignore': (Icons.ESLINT, 'green'),  # 
    '.eslintrc.cjs': (Icons.ESLINT, 'green'),  # 
    '.eslintrc.js': (Icons.ESLINT, 'green'),  # 
    '.eslintrc.json': (Icons.ESLINT, 'green'),  # 
    '.eslintrc.yaml': (Icons.ESLINT, 'green'),  # 
    '.eslintrc.yml': (Icons.ESLINT, 'green'),  # 
    '.gcloudignore': ('\U000f11f6', ''),  # 󱇶
    '.fennelrc': (Icons.LANG_FENNEL, 'green'),  # 
    '.gitattributes': (Icons.GIT, 'cyan'),  # 󰊢
    '.git-blame-ignore-revs': (Icons.GIT, 'cyan'),  # 󰊢
    '.gitconfig': (Icons.GIT, 'cyan'),  # 󰊢
    '.gitignore': (Icons.GIT, 'cyan'),  # 󰊢
    '.gitignore_global': (Icons.GIT, 'cyan'),  # 󰊢
    '.gitlab-ci.yml': ('\uf296', ''),  # 
    '.gitmodules': (Icons.GIT, 'cyan'),  # 󰊢
    '.gtkrc-2.0': (Icons.GTK, ''),  # 
    '.gvimrc': (Icons.VIM, 'green'),  # 
    '.htaccess': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.htpasswd': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.idea': (Icons.INTELLIJ, ''),  # 
    '.ideavimrc': (Icons.VIM, 'green'),  # 
    '.inputrc': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.kshrc': (Icons.SHELL, ''),  # 󱆃
    '.login': (Icons.SHELL, ''),  # 󱆃
    '.logout': (Icons.SHELL, ''),  # 󱆃
    '.luacheckrc': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.luaurc': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.nanorc': ('\ue838', ''),  # 
    '.nuxtrc': ('\U000f1106', ''),  # 󱄆
    '.ocamlinit': (Icons.LANG_OCAML, 'green'),  # 
    '.mailmap': (Icons.GIT, 'cyan'),  # 󰊢
    '.node_repl_history': (Icons.NODEJS, ''),  # 
    '.npmignore': (Icons.NPM, 'cyan'),  # 
    '.npmrc': (Icons.NPM, 'cyan'),  # 
    '.pre-commit-config.yaml': ('\U000f06e2', ''),  # 󰛢
    '.prettierignore': ('\ue6b4', ''),  # 
    '.prettierrc': ('\ue6b4', ''),  # 
    '.prettierrc.json': ('\ue6b4', ''),  # 
    '.prettierrc.json5': ('\ue6b4', ''),  # 
    '.prettierrc.toml': ('\ue6b4', ''),  # 
    '.prettierrc.yaml': ('\ue6b4', ''),  # 
    '.prettierrc.yml': ('\ue6b4', ''),  # 
    '.parentlock': (Icons.LOCK, 'cyan'),  # 
    '.profile': (Icons.SHELL, ''),  # 󱆃
    '.pylintrc': (Icons.CONFIG, 'cyan'),  # 󱁻
    '.python_history': (Icons.LANG_PYTHON, 'green'),  # 
    '.rustfmt.toml': (Icons.LANG_RUST, 'green'),  # 
    '.rvm': (Icons.LANG_RUBY, 'green'),  # 
    '.rvmrc': (Icons.LANG_RUBY, 'green'),  # 
    '.SRCINFO': ('\uf303', ''),  # 
    '.stowrc': ('\ueef1', ''),  # 
    '.tcshrc': (Icons.SHELL, ''),  # 󱆃
    '.viminfo': (Icons.VIM, 'green'),  # 
    '.vimrc': (Icons.VIM, 'green'),  # 
    '.Xauthority': (Icons.XORG, ''),  # 
    '.xinitrc': (Icons.XORG, ''),  # 
    '.Xresources': (Icons.XORG, ''),  # 
    '.xsession': (Icons.XORG, ''),  # 
    '.yarnrc': (Icons.YARN, 'cyan'),  # 
    '.zlogin': (Icons.SHELL, ''),  # 󱆃
    '.zlogout': (Icons.SHELL, ''),  # 󱆃
    '.zprofile': (Icons.SHELL, ''),  # 󱆃
    '.zshenv': (Icons.SHELL, ''),  # 󱆃
    '.zshrc': (Icons.SHELL, ''),  # 󱆃
    '.zsh_history': (Icons.SHELL, ''),  # 󱆃
    '.zsh_sessions': (Icons.SHELL, ''),  # 󱆃
    '._DS_Store': (Icons.OS_APPLE, ''),  # 
    '_gvimrc': (Icons.VIM, 'green'),  # 
    '_vimrc': (Icons.VIM, 'green'),  # 
    'a.out': (Icons.SHELL_CMD, 'green'),  # 
    'authorized_keys': ('\U000f08c0', ''),  # 󰣀
    'AUTHORS': ('\uedca', ''),  # 
    'AUTHORS.txt': ('\uedca', ''),  # 
    'bashrc': (Icons.SHELL, ''),  # 󱆃
    'Brewfile': ('\U000f1116', ''),  # 󱄖
    'Brewfile.lock.json': ('\U000f1116', ''),  # 󱄖
    'bspwmrc': ('\uf355', ''),  # 
    'build.gradle.kts': (Icons.GRADLE, ''),  # 
    'build.zig.zon': ('\ue6a9', ''),  # 
    'bun.lockb': ('\ue76f', ''),  # 
    'cantorrc': ('\uf373', ''),  # 
    'Cargo.lock': (Icons.LANG_RUST, 'green'),  # 
    'Cargo.toml': (Icons.LANG_RUST, 'green'),  # 
    'CMakeLists.txt': ('\ue794', ''),  # 
    'CHANGELOG': (Icons.NEWS, ''),  # 
    'CHANGELOG.md': (Icons.NEWS, ''),  # 
    'CHANGES': (Icons.NEWS, ''),  # 
    'CHANGES.md': (Icons.NEWS, ''),  # 
    'CODE_OF_CONDUCT': ('\uf4ae', ''),  # 
    'CODE_OF_CONDUCT.md': ('\uf4ae', ''),  # 
    'composer.json': (Icons.LANG_PHP, 'green'),  # 
    'composer.lock': (Icons.LANG_PHP, 'green'),  # 
    'config': (Icons.CONFIG, 'cyan'),  # 󱁻
    'config.ru': (Icons.LANG_RUBY, 'green'),  # 
    'config.status': (Icons.CONFIG, 'cyan'),  # 󱁻
    'configure': (Icons.WRENCH, ''),  # 
    'configure.ac': (Icons.CONFIG, 'cyan'),  # 󱁻
    'configure.in': (Icons.CONFIG, 'cyan'),  # 󱁻
    'constraints.txt': (Icons.LANG_PYTHON, 'green'),  # 
    'COPYING': (Icons.LICENSE, 'yellow'),  # 
    'COPYRIGHT': (Icons.LICENSE, 'yellow'),  # 
    'crontab': (Icons.CONFIG, 'cyan'),  # 󱁻
    'crypttab': (Icons.CONFIG, 'cyan'),  # 󱁻
    'csh.cshrc': (Icons.SHELL, ''),  # 󱆃
    'csh.login': (Icons.SHELL, ''),  # 󱆃
    'csh.logout': (Icons.SHELL, ''),  # 󱆃
    'docker-compose.yml': (Icons.DOCKER, 'cyan'),  # 
    'Dockerfile': (Icons.DOCKER, 'cyan'),  # 
    'compose.yaml': (Icons.DOCKER, 'cyan'),  # 
    'compose.yml': (Icons.DOCKER, 'cyan'),  # 
    'docker-compose.yaml': (Icons.DOCKER, 'cyan'),  # 
    'dropbox': ('\ue707', ''),  # 
    'dune': (Icons.LANG_OCAML, 'green'),  # 
    'dune-project': (Icons.WRENCH, ''),  # 
    'Earthfile': ('\uf0ac', ''),  # 
    'COMMIT_EDITMSG': (Icons.GIT, 'cyan'),  # 
    'environment': (Icons.CONFIG, 'cyan'),  # 󱁻
    'favicon.ico': ('\ue623', ''),  # 
    'flake.lock': ('\uf313', ''),  # 
    'fennelrc': (Icons.LANG_FENNEL, 'green'),  # 
    'fonts.conf': (Icons.FONT, ''),  # 
    'fp-info-cache': (Icons.KICAD, ''),  # 
    'fp-lib-table': (Icons.KICAD, ''),  # 
    'FreeCAD.conf': (Icons.FREECAD, ''),  # 
    'Gemfile': (Icons.LANG_RUBY, 'green'),  # 
    'Gemfile.lock': (Icons.LANG_RUBY, 'green'),  # 
    'GNUmakefile': (Icons.MAKE, ''),  # 
    'go.mod': (Icons.LANG_GO, 'green'),  # 
    'go.sum': (Icons.LANG_GO, 'green'),  # 
    'go.work': (Icons.LANG_GO, 'green'),  # 
    'gradle': (Icons.GRADLE, ''),  # 
    'gradle.properties': (Icons.GRADLE, ''),  # 
    'gradlew': (Icons.GRADLE, ''),  # 
    'gradlew.bat': (Icons.GRADLE, ''),  # 
    'group': (Icons.LOCK, 'cyan'),  # 
    'gruntfile.coffee': (Icons.GRUNT, ''),  # 
    'gruntfile.js': (Icons.GRUNT, ''),  # 
    'gruntfile.ls': (Icons.GRUNT, ''),  # 
    'gshadow': (Icons.LOCK, 'cyan'),  # 
    'gtkrc': (Icons.GTK, ''),  # 
    'gulpfile.coffee': (Icons.GULP, ''),  # 
    'gulpfile.js': (Icons.GULP, ''),  # 
    'gulpfile.ls': (Icons.GULP, ''),  # 
    'heroku.yml': ('\ue77b', ''),  # 
    'hostname': (Icons.CONFIG, 'cyan'),  # 󱁻
    'hypridle.conf': ('\uf359', ''),  # 
    'hyprland.conf': ('\uf359', ''),  # 
    'hyprlock.conf': ('\uf359', ''),  # 
    'hyprpaper.conf': ('\uf359', ''),  # 
    'i3blocks.conf': ('\uf35a', ''),  # 
    'i3status.conf': ('\uf35a', ''),  # 
    'id_dsa': (Icons.PRIVATE_KEY, ''),  # 󰌆
    'id_ecdsa': (Icons.PRIVATE_KEY, ''),  # 󰌆
    'id_ecdsa_sk': (Icons.PRIVATE_KEY, ''),  # 󰌆
    'id_ed25519': (Icons.PRIVATE_KEY, ''),  # 󰌆
    'id_ed25519_sk': (Icons.PRIVATE_KEY, ''),  # 󰌆
    'id_rsa': (Icons.PRIVATE_KEY, ''),  # 󰌆
    'index.theme': ('\uee72', ''),  # 
    'inputrc': (Icons.CONFIG, 'cyan'),  # 󱁻
    'Jenkinsfile': ('\ue66e', ''),  # 
    'jsconfig.json': (Icons.LANG_JAVASCRIPT, 'green'),  # 
    'Justfile': (Icons.WRENCH, ''),  # 
    'justfile': (Icons.WRENCH, ''),  # 
    'kalgebrarc': ('\uf373', ''),  # 
    'kdeglobals': ('\uf373', ''),  # 
    'kdenlive-layoutsrc': (Icons.KDENLIVE, ''),  # 
    'kdenliverc': (Icons.KDENLIVE, ''),  # 
    'known_hosts': ('\U000f08c0', ''),  # 󰣀
    'kritadisplayrc': (Icons.KRITA, 'bright_magenta'),  # 
    'kritarc': (Icons.KRITA, 'bright_magenta'),  # 
    'LICENCE': (Icons.LICENSE, 'yellow'),  # 
    'LICENCE.md': (Icons.LICENSE, 'yellow'),  # 
    'LICENCE.txt': (Icons.LICENSE, 'yellow'),  # 
    'LICENSE': (Icons.LICENSE, 'yellow'),  # 
    'LICENSE-APACHE': (Icons.LICENSE, 'yellow'),  # 
    'LICENSE-MIT': (Icons.LICENSE, 'yellow'),  # 
    'LICENSE.md': (Icons.LICENSE, 'yellow'),  # 
    'LICENSE.txt': (Icons.LICENSE, 'yellow'),  # 
    'localized': (Icons.OS_APPLE, ''),  # 
    'localtime': (Icons.CLOCK, ''),  # 
    'lock': (Icons.LOCK, 'cyan'),  # 
    'LOCK': (Icons.LOCK, 'cyan'),  # 
    'log': (Icons.LOG, 'dim'),  # 
    'LOG': (Icons.LOG, 'dim'),  # 
    'lxde-rc.xml': ('\uf363', ''),  # 
    'lxqt.conf': ('\uf364', ''),  # 
    'Makefile': (Icons.MAKE, ''),  # 
    'makefile': (Icons.MAKE, ''),  # 
    'Makefile.ac': (Icons.MAKE, ''),  # 
    'Makefile.am': (Icons.MAKE, ''),  # 
    'Makefile.in': (Icons.MAKE, ''),  # 
    'MANIFEST': (Icons.LANG_PYTHON, 'green'),  # 
    'MANIFEST.in': (Icons.LANG_PYTHON, 'green'),  # 
    'mix.lock': (Icons.LANG_ELIXIR, 'green'),  # 
    'mpv.conf': ('\uf36e', ''),  # 
    'NEWS': (Icons.NEWS, ''),  # 
    'NEWS.md': (Icons.NEWS, ''),  # 
    'npm-shrinkwrap.json': (Icons.NPM, 'cyan'),  # 
    'npmrc': (Icons.NPM, 'cyan'),  # 
    'package-lock.json': (Icons.NPM, 'cyan'),  # 
    'package.json': (Icons.NPM, 'cyan'),  # 
    'passwd': (Icons.LOCK, 'cyan'),  # 
    'php.ini': (Icons.LANG_PHP, 'green'),  # 
    'PKGBUILD': ('\uf303', ''),  # 
    'platformio.ini': ('\ue682', ''),  # 
    'pom.xml': ('\ue674', ''),  # 
    'Procfile': ('\ue77b', ''),  # 
    'profile': (Icons.SHELL, ''),  # 󱆃
    'PrusaSlicer.ini': ('\uf351', ''),  # 
    'PrusaSlicerGcodeViewer.ini': ('\uf351', ''),  # 
    'pyvenv.cfg': (Icons.LANG_PYTHON, 'green'),  # 
    'pyproject.toml': (Icons.LANG_PYTHON, 'green'),  # 
    'qt5ct.conf': (Icons.QT, ''),  # 
    'qt6ct.conf': (Icons.QT, ''),  # 
    'QtProject.conf': (Icons.QT, ''),  # 
    'Rakefile': (Icons.LANG_RUBY, 'green'),  # 
    'README': (Icons.README, ''),  # 󰂺
    'README.md': (Icons.README, ''),  # 󰂺
    'release.toml': (Icons.LANG_RUST, 'green'),  # 
    'renovate.json': ('\U000f027c', ''),  # 󰉼
    'requirements.txt': (Icons.LANG_PYTHON, 'green'),  # 
    'robots.txt': ('\U000f06a9', ''),  # 󰚩
    'rubydoc': (Icons.LANG_RUBYRAILS, 'green'),  # 
    'rvmrc': (Icons.LANG_RUBY, 'green'),  # 
    'SECURITY': ('\U000f0483', ''),  # 󰒃
    'SECURITY.md': ('\U000f0483', ''),  # 󰒃
    'settings.gradle.kts': (Icons.GRADLE, ''),  # 
    'shadow': (Icons.LOCK, 'cyan'),  # 
    'shells': (Icons.CONFIG, 'cyan'),  # 󱁻
    'sudoers': (Icons.LOCK, 'cyan'),  # 
    'sxhkdrc': (Icons.CONFIG, 'cyan'),  # 
    'sym-lib-table': (Icons.KICAD, ''),  # 
    'timezone': (Icons.CLOCK, ''),  # 
    'tmux.conf': (Icons.TMUX, ''),  # 
    'tmux.conf.local': (Icons.TMUX, ''),  # 
    'TODO': (Icons.TODO, ''),  # 
    'TODO.md': (Icons.TODO, ''),  # 
    'tsconfig.json': (Icons.LANG_TYPESCRIPT, 'green'),  # 
    'Vagrantfile': ('\u2371', ''),  # ⍱
    'vlcrc': ('\U000f057c', ''),  # 󰕼
    'webpack.config.js': ('\U000f072b', ''),  # 󰜫
    'xorg.conf': (Icons.XORG, ''),  # 
    'xsettingsd.conf': (Icons.XORG, ''),  # 
    'weston.ini': ('\uf367', ''),  # 
    'xmobarrc': (Icons.XORG, ''),  # 
    'xmobarrc.hs': (Icons.XORG, ''),  # 
    'xmonad.hs': (Icons.XORG, ''),  # 
    'yarn.lock': (Icons.YARN, 'cyan'),  # 
    'zlogin': (Icons.SHELL, ''),  # 󱆃
    'zlogout': (Icons.SHELL, ''),  # 󱆃
    'zprofile': (Icons.SHELL, ''),  # 󱆃
    'zshenv': (Icons.SHELL, ''),  # 󱆃
    'zshrc': (Icons.SHELL, ''),  # 󱆃
}

EXTENSION_ICONS: Final[dict[str, tuple[str, str]]] = {
    '123dx': (Icons.CAD, ''),  # 󰻫
    '3dm': (Icons.CAD, ''),  # 󰻫
    '3g2': (Icons.VIDEO, 'magenta'),  # 
    '3gp': (Icons.VIDEO, 'magenta'),  # 
    '3gp2': (Icons.VIDEO, 'magenta'),  # 
    '3gpp': (Icons.VIDEO, 'magenta'),  # 
    '3gpp2': (Icons.VIDEO, 'magenta'),  # 
    '3mf': (Icons.FILE_3D, ''),  # 󰆧
    '7z': (Icons.COMPRESSED, 'red'),  # 
    'a': (Icons.OS_LINUX, ''),  # 
    'aac': (Icons.AUDIO, 'magenta'),  # 
    'acf': ('\uf1b6', ''),  # 
    'age': (Icons.SHIELD_LOCK, ''),  # 󰦝
    'ai': ('\ue7b4', ''),  # 
    'aif': (Icons.AUDIO, 'magenta'),  # 
    'aifc': (Icons.AUDIO, 'magenta'),  # 
    'aiff': (Icons.AUDIO, 'magenta'),  # 
    'alac': (Icons.AUDIO, 'magenta'),  # 
    'android': (Icons.OS_ANDROID, ''),  # 
    'ape': (Icons.AUDIO, 'magenta'),  # 
    'apk': (Icons.OS_ANDROID, ''),  # 
    'app': (Icons.BINARY, 'dim'),  # 
    'applescript': (Icons.OS_APPLE, ''),  # 
    'apple': (Icons.OS_APPLE, ''),  # 
    'ar': (Icons.COMPRESSED, 'red'),  # 
    'arj': (Icons.COMPRESSED, 'red'),  # 
    'arw': (Icons.IMAGE, 'bright_magenta'),  # 
    'asc': (Icons.SHIELD_LOCK, ''),  # 󰦝
    'asm': (Icons.LANG_ASSEMBLY, 'green'),  # 
    'asp': ('\uf121', ''),  # 
    'ass': (Icons.SUBTITLE, ''),  # 󰨖
    'avi': (Icons.VIDEO, 'magenta'),  # 
    'avif': (Icons.IMAGE, 'bright_magenta'),  # 
    'avro': (Icons.JSON, 'cyan'),  # 
    'awk': (Icons.SHELL_CMD, 'green'),  # 
    'bash': (Icons.SHELL_CMD, 'green'),  # 
    'bat': (Icons.OS_WINDOWS_CMD, ''),  # 
    'bats': (Icons.SHELL_CMD, 'green'),  # 
    'bdf': (Icons.FONT, ''),  # 
    'bib': (Icons.LANG_TEX, 'green'),  # 
    'bin': (Icons.BINARY, 'dim'),  # 
    'blend': ('\U000f00ab', ''),  # 󰂫
    'bmp': (Icons.IMAGE, 'bright_magenta'),  # 
    'br': (Icons.COMPRESSED, 'red'),  # 
    'brd': (Icons.EDA_PCB, ''),  # 
    'brep': (Icons.CAD, ''),  # 󰻫
    'bst': (Icons.LANG_TEX, 'green'),  # 
    'bundle': (Icons.OS_APPLE, ''),  # 
    'bz': (Icons.COMPRESSED, 'red'),  # 
    'bz2': (Icons.COMPRESSED, 'red'),  # 
    'bz3': (Icons.COMPRESSED, 'red'),  # 
    'c': (Icons.LANG_C, 'green'),  # 
    'c++': (Icons.LANG_CPP, 'green'),  # 
    'cab': (Icons.OS_WINDOWS, ''),  # 
    'cache': (Icons.CACHE, ''),  # 
    'cast': (Icons.VIDEO, 'magenta'),  # 
    'catpart': (Icons.CAD, ''),  # 󰻫
    'catproduct': (Icons.CAD, ''),  # 󰻫
    'cbr': (Icons.IMAGE, 'bright_magenta'),  # 
    'cbz': (Icons.IMAGE, 'bright_magenta'),  # 
    'cc': (Icons.LANG_CPP, 'green'),  # 
    'cert': (Icons.GIST_SECRET, ''),  # 
    'cfg': (Icons.CONFIG, 'cyan'),  # 󱁻
    'cjs': (Icons.LANG_JAVASCRIPT, 'green'),  # 
    'class': (Icons.LANG_JAVA, 'green'),  # 
    'clj': ('\ue768', ''),  # 
    'cljc': ('\ue768', ''),  # 
    'cljs': ('\ue76a', ''),  # 
    'cls': (Icons.LANG_TEX, 'green'),  # 
    'cmake': ('\ue794', ''),  # 
    'cmd': (Icons.OS_WINDOWS, ''),  # 
    'coffee': ('\uf0f4', ''),  # 
    'com': ('\ue629', ''),  # 
    'conda': ('\ue715', ''),  # 
    'conf': (Icons.CONFIG, 'cyan'),  # 󱁻
    'config': (Icons.CONFIG, 'cyan'),  # 󱁻
    'cow': ('\U000f019a', ''),  # 󰆚
    'cp': (Icons.LANG_CPP, 'green'),  # 
    'cpio': (Icons.COMPRESSED, 'red'),  # 
    'cpp': (Icons.LANG_CPP, 'green'),  # 
    'cr': ('\ue62f', ''),  # 
    'cr2': (Icons.IMAGE, 'bright_magenta'),  # 
    'crdownload': (Icons.DOWNLOAD, ''),  # 󰇚
    'crt': (Icons.GIST_SECRET, ''),  # 
    'cs': (Icons.LANG_CSHARP, 'green'),  # 󰌛
    'csh': (Icons.SHELL_CMD, 'green'),  # 
    'cshtml': (Icons.RAZOR, ''),  # 
    'csproj': (Icons.LANG_CSHARP, 'green'),  # 󰌛
    'css': (Icons.CSS3, 'green'),  # 
    'csv': ('\ueefc', ''),  # 
    'csx': (Icons.LANG_CSHARP, 'green'),  # 󰌛
    'cts': (Icons.LANG_TYPESCRIPT, 'green'),  # 
    'cu': ('\ue64b', ''),  # 
    'cue': (Icons.PLAYLIST, ''),  # 󰲹
    'cxx': (Icons.LANG_CPP, 'green'),  # 
    'd': (Icons.LANG_D, 'green'),  # 
    'dart': ('\ue798', ''),  # 
    'db': (Icons.DATABASE, 'cyan'),  # 
    'db3': (Icons.SQLITE, 'dim'),  # 
    'dconf': (Icons.DATABASE, 'cyan'),  # 
    'deb': ('\ue77d', ''),  # 
    'desktop': ('\uebd1', ''),  # 
    'di': (Icons.LANG_D, 'green'),  # 
    'diff': (Icons.DIFF, ''),  # 
    'djv': (Icons.DOCUMENT, ''),  # 
    'djvu': (Icons.DOCUMENT, ''),  # 
    'dll': (Icons.LIBRARY, 'dim'),  # 
    'dmg': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'doc': (Icons.DOCUMENT, ''),  # 
    'docm': (Icons.DOCUMENT, ''),  # 
    'docx': (Icons.DOCUMENT, ''),  # 
    'dot': (Icons.GRAPH, ''),  # 󱁉
    'download': (Icons.DOWNLOAD, ''),  # 󰇚
    'dockerfile': (Icons.DOCKER, 'cyan'),  # 
    'dockerignore': (Icons.DOCKER, 'cyan'),  # 
    'drawio': ('\uebba', ''),  # 
    'dump': (Icons.DATABASE, 'cyan'),  # 
    'dvi': (Icons.IMAGE, 'bright_magenta'),  # 
    'dwg': (Icons.CAD, ''),  # 󰻫
    'dxf': (Icons.CAD, ''),  # 󰻫
    'dylib': (Icons.OS_APPLE, ''),  # 
    'ebook': (Icons.BOOK, ''),  # 
    'ebuild': ('\uf30d', ''),  # 
    'edn': ('\ue76a', ''),  # 
    'editorconfig': ('\ue652', ''),  # 
    'eex': (Icons.LANG_ELIXIR, 'green'),  # 
    'ejs': ('\ue618', ''),  # 
    'el': (Icons.EMACS, 'green'),  # 
    'elc': (Icons.EMACS, 'green'),  # 
    'elf': (Icons.BINARY, 'dim'),  # 
    'elm': ('\ue62c', ''),  # 
    'eml': ('\uf003', ''),  # 
    'env': ('\uf462', ''),  # 
    'eot': (Icons.FONT, ''),  # 
    'eps': (Icons.VECTOR, 'bright_magenta'),  # 󰕙
    'epub': (Icons.BOOK, ''),  # 
    'erb': (Icons.LANG_RUBYRAILS, 'green'),  # 
    'erl': ('\ue7b1', ''),  # 
    'ex': (Icons.LANG_ELIXIR, 'green'),  # 
    'exe': (Icons.OS_WINDOWS_CMD, ''),  # 
    'exs': (Icons.LANG_ELIXIR, 'green'),  # 
    'f': (Icons.LANG_FORTRAN, 'green'),  # 󱈚
    'f#': (Icons.LANG_FSHARP, 'green'),  # 
    'f3d': (Icons.CAD, ''),  # 󰻫
    'f3z': (Icons.CAD, ''),  # 󰻫
    'f90': (Icons.LANG_FORTRAN, 'green'),  # 󱈚
    'fbx': (Icons.FILE_3D, ''),  # 󰆧
    'fdmdownload': (Icons.DOWNLOAD, ''),  # 󰇚
    'fcbak': (Icons.FREECAD, ''),  # 
    'fcmacro': (Icons.FREECAD, ''),  # 
    'fcmat': (Icons.FREECAD, ''),  # 
    'fcparam': (Icons.FREECAD, ''),  # 
    'fcscript': (Icons.FREECAD, ''),  # 
    'fcstd': (Icons.FREECAD, ''),  # 
    'fcstd1': (Icons.FREECAD, ''),  # 
    'fctb': (Icons.FREECAD, ''),  # 
    'fctl': (Icons.FREECAD, ''),  # 
    'fish': (Icons.SHELL_CMD, 'green'),  # 
    'flac': (Icons.AUDIO, 'magenta'),  # 
    'flc': (Icons.FONT, ''),  # 
    'flf': (Icons.FONT, ''),  # 
    'flv': (Icons.VIDEO, 'magenta'),  # 
    'fnl': (Icons.LANG_FENNEL, 'green'),  # 
    'fnt': (Icons.FONT, ''),  # 
    'fodg': ('\uf379', ''),  # 
    'fodp': ('\uf37a', ''),  # 
    'fods': ('\uf378', ''),  # 
    'fodt': ('\uf37c', ''),  # 
    'fon': (Icons.FONT, ''),  # 
    'font': (Icons.FONT, ''),  # 
    'for': (Icons.LANG_FORTRAN, 'green'),  # 󱈚
    'fs': (Icons.LANG_FSHARP, 'green'),  # 
    'fsi': (Icons.LANG_FSHARP, 'green'),  # 
    'fsproj': (Icons.LANG_FSHARP, 'green'),  # 
    'fsscript': (Icons.LANG_FSHARP, 'green'),  # 
    'fsx': (Icons.LANG_FSHARP, 'green'),  # 
    'gba': ('\U000f1393', ''),  # 󱎓
    'gbl': (Icons.EDA_PCB, ''),  # 
    'gbo': (Icons.EDA_PCB, ''),  # 
    'gbp': (Icons.EDA_PCB, ''),  # 
    'gbr': (Icons.EDA_PCB, ''),  # 
    'gbs': (Icons.EDA_PCB, ''),  # 
    'gcode': ('\U000f0af4', ''),  # 󰫴
    'gd': (Icons.GODOT, ''),  # 
    'gdoc': (Icons.DOCUMENT, ''),  # 
    'gem': (Icons.LANG_RUBY, 'green'),  # 
    'gemfile': (Icons.LANG_RUBY, 'green'),  # 
    'gemspec': (Icons.LANG_RUBY, 'green'),  # 
    'gform': ('\uf298', ''),  # 
    'gif': (Icons.IMAGE, 'bright_magenta'),  # 
    'git': (Icons.GIT, 'cyan'),  # 󰊢
    'gleam': (Icons.LANG_GLEAM, 'green'),  # 󰦥
    'gm1': (Icons.EDA_PCB, ''),  # 
    'gml': (Icons.EDA_PCB, ''),  # 
    'go': (Icons.LANG_GO, 'green'),  # 
    'godot': (Icons.GODOT, ''),  # 
    'gpg': (Icons.SHIELD_LOCK, ''),  # 󰦝
    'gql': (Icons.GRAPHQL, ''),  # 
    'gradle': (Icons.GRADLE, ''),  # 
    'graphql': (Icons.GRAPHQL, ''),  # 
    'gresource': (Icons.GTK, ''),  # 
    'groovy': (Icons.LANG_GROOVY, 'green'),  # 
    'gsheet': (Icons.SHEET, 'cyan'),  # 
    'gslides': (Icons.SLIDE, ''),  # 
    'gtl': (Icons.EDA_PCB, ''),  # 
    'gto': (Icons.EDA_PCB, ''),  # 
    'gtp': (Icons.EDA_PCB, ''),  # 
    'gts': (Icons.EDA_PCB, ''),  # 
    'guardfile': (Icons.LANG_RUBY, 'green'),  # 
    'gv': (Icons.GRAPH, ''),  # 󱁉
    'gvy': (Icons.LANG_GROOVY, 'green'),  # 
    'gz': (Icons.COMPRESSED, 'red'),  # 
    'h': (Icons.LANG_C, 'green'),  # 
    'h++': (Icons.LANG_CPP, 'green'),  # 
    'h264': (Icons.VIDEO, 'magenta'),  # 
    'haml': ('\ue664', ''),  # 
    'hbs': (Icons.MUSTACHE, ''),  # 
    'hc': (Icons.LANG_HOLYC, 'green'),  # 󰂢
    'heic': (Icons.IMAGE, 'bright_magenta'),  # 
    'heics': (Icons.VIDEO, 'magenta'),  # 
    'heif': (Icons.IMAGE, 'bright_magenta'),  # 
    'hex': ('\U000f12a7', ''),  # 󱊧
    'hh': (Icons.LANG_CPP, 'green'),  # 
    'hi': (Icons.BINARY, 'dim'),  # 
    'hpp': (Icons.LANG_CPP, 'green'),  # 
    'hrl': ('\ue7b1', ''),  # 
    'hs': (Icons.LANG_HASKELL, 'green'),  # 
    'htm': (Icons.HTML5, 'green'),  # 
    'html': (Icons.HTML5, 'green'),  # 
    'hxx': (Icons.LANG_CPP, 'green'),  # 
    'iam': (Icons.CAD, ''),  # 󰻫
    'ical': (Icons.CALENDAR, ''),  # 
    'icalendar': (Icons.CALENDAR, ''),  # 
    'ico': (Icons.IMAGE, 'bright_magenta'),  # 
    'ics': (Icons.CALENDAR, ''),  # 
    'ifb': (Icons.CALENDAR, ''),  # 
    'ifc': (Icons.CAD, ''),  # 󰻫
    'ige': (Icons.CAD, ''),  # 󰻫
    'iges': (Icons.CAD, ''),  # 󰻫
    'igs': (Icons.CAD, ''),  # 󰻫
    'image': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'img': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'iml': (Icons.INTELLIJ, ''),  # 
    'info': (Icons.INFO, ''),  # 
    'ini': (Icons.CONFIG, 'cyan'),  # 󱁻
    'inl': (Icons.LANG_C, 'green'),  # 
    'ipynb': (Icons.NOTEBOOK, 'green'),  # 
    'ino': (Icons.LANG_ARDUINO, 'green'),  # 
    'ipt': (Icons.CAD, ''),  # 󰻫
    'iso': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'j2c': (Icons.IMAGE, 'bright_magenta'),  # 
    'j2k': (Icons.IMAGE, 'bright_magenta'),  # 
    'jad': (Icons.LANG_JAVA, 'green'),  # 
    'jar': (Icons.LANG_JAVA, 'green'),  # 
    'java': (Icons.LANG_JAVA, 'green'),  # 
    'jwmrc': ('\uf35b', ''),  # 
    'jfi': (Icons.IMAGE, 'bright_magenta'),  # 
    'jfif': (Icons.IMAGE, 'bright_magenta'),  # 
    'jif': (Icons.IMAGE, 'bright_magenta'),  # 
    'jl': ('\ue624', ''),  # 
    'jmd': (Icons.MARKDOWN, ''),  # 
    'jp2': (Icons.IMAGE, 'bright_magenta'),  # 
    'jpe': (Icons.IMAGE, 'bright_magenta'),  # 
    'jpeg': (Icons.IMAGE, 'bright_magenta'),  # 
    'jpf': (Icons.IMAGE, 'bright_magenta'),  # 
    'jpg': (Icons.IMAGE, 'bright_magenta'),  # 
    'jpx': (Icons.IMAGE, 'bright_magenta'),  # 
    'js': (Icons.LANG_JAVASCRIPT, 'green'),  # 
    'json': (Icons.JSON, 'cyan'),  # 
    'json5': (Icons.JSON, 'cyan'),  # 
    'jsonc': (Icons.JSON, 'cyan'),  # 
    'jsx': (Icons.REACT, 'green'),  # 
    'jxl': (Icons.IMAGE, 'bright_magenta'),  # 
    'kbx': (Icons.SHIELD_KEY, ''),  # 󰯄
    'kdb': (Icons.KEYPASS, ''),  # 
    'kdbx': (Icons.KEYPASS, ''),  # 
    'kdenlive': (Icons.KDENLIVE, ''),  # 
    'kdenlivetitle': (Icons.KDENLIVE, ''),  # 
    'key': (Icons.KEY, ''),  # 
    'kicad_dru': (Icons.KICAD, ''),  # 
    'kicad_mod': (Icons.KICAD, ''),  # 
    'kicad_pcb': (Icons.KICAD, ''),  # 
    'kicad_prl': (Icons.KICAD, ''),  # 
    'kicad_pro': (Icons.KICAD, ''),  # 
    'kicad_sch': (Icons.KICAD, ''),  # 
    'kicad_sym': (Icons.KICAD, ''),  # 
    'kicad_wks': (Icons.KICAD, ''),  # 
    'ko': (Icons.OS_LINUX, ''),  # 
    'kpp': (Icons.KRITA, 'bright_magenta'),  # 
    'kra': (Icons.KRITA, 'bright_magenta'),  # 
    'krz': (Icons.KRITA, 'bright_magenta'),  # 
    'ksh': (Icons.SHELL_CMD, 'green'),  # 
    'kt': (Icons.LANG_KOTLIN, 'green'),  # 
    'kts': (Icons.LANG_KOTLIN, 'green'),  # 
    'latex': (Icons.LANG_TEX, 'green'),  # 
    'lbr': (Icons.LIBRARY, 'dim'),  # 
    'lck': (Icons.LOCK, 'cyan'),  # 
    'ldb': (Icons.DATABASE, 'cyan'),  # 
    'leex': (Icons.LANG_ELIXIR, 'green'),  # 
    'less': ('\ue758', ''),  # 
    'lff': (Icons.FONT, ''),  # 
    'lhs': (Icons.LANG_HASKELL, 'green'),  # 
    'lib': (Icons.LIBRARY, 'dim'),  # 
    'license': (Icons.LICENSE, 'yellow'),  # 
    'lisp': ('\U000f0172', ''),  # 󰅲
    'localized': (Icons.OS_APPLE, ''),  # 
    'lock': (Icons.LOCK, 'cyan'),  # 
    'log': (Icons.LOG, 'dim'),  # 
    'lpp': (Icons.EDA_PCB, ''),  # 
    'lrc': (Icons.SUBTITLE, ''),  # 󰨖
    'ltx': (Icons.LANG_TEX, 'green'),  # 
    'lua': (Icons.LANG_LUA, 'green'),  # 
    'luac': (Icons.LANG_LUA, 'green'),  # 
    'luau': (Icons.LANG_LUA, 'green'),  # 
    'lz': (Icons.COMPRESSED, 'red'),  # 
    'lz4': (Icons.COMPRESSED, 'red'),  # 
    'lzh': (Icons.COMPRESSED, 'red'),  # 
    'lzma': (Icons.COMPRESSED, 'red'),  # 
    'lzo': (Icons.COMPRESSED, 'red'),  # 
    'm': (Icons.LANG_C, 'green'),  # 
    'm2ts': (Icons.VIDEO, 'magenta'),  # 
    'm2v': (Icons.VIDEO, 'magenta'),  # 
    'm3u': (Icons.PLAYLIST, ''),  # 󰲹
    'm3u8': (Icons.PLAYLIST, ''),  # 󰲹
    'm4a': (Icons.AUDIO, 'magenta'),  # 
    'm4v': (Icons.VIDEO, 'magenta'),  # 
    'magnet': ('\uf076', ''),  # 
    'markdown': (Icons.MARKDOWN, ''),  # 
    'md': (Icons.MARKDOWN, ''),  # 
    'md5': (Icons.SHIELD_CHECK, ''),  # 󰕥
    'mdb': (Icons.DATABASE, 'cyan'),  # 
    'mdx': (Icons.MARKDOWN, ''),  # 
    'mid': ('\U000f08f2', ''),  # 󰣲
    'mjs': (Icons.LANG_JAVASCRIPT, 'green'),  # 
    'mk': (Icons.MAKE, ''),  # 
    'mka': (Icons.AUDIO, 'magenta'),  # 
    'mkd': (Icons.MARKDOWN, ''),  # 
    'mkv': (Icons.VIDEO, 'magenta'),  # 
    'ml': (Icons.LANG_OCAML, 'green'),  # 
    'mli': (Icons.LANG_OCAML, 'green'),  # 
    'mll': (Icons.LANG_OCAML, 'green'),  # 
    'mly': (Icons.LANG_OCAML, 'green'),  # 
    'mm': (Icons.LANG_CPP, 'green'),  # 
    'mo': (Icons.TRANSLATION, ''),  # 󰗊
    'mobi': (Icons.BOOK, ''),  # 
    'mov': (Icons.VIDEO, 'magenta'),  # 
    'mp2': (Icons.AUDIO, 'magenta'),  # 
    'mp3': (Icons.AUDIO, 'magenta'),  # 
    'mp4': (Icons.VIDEO, 'magenta'),  # 
    'mpeg': (Icons.VIDEO, 'magenta'),  # 
    'mpg': (Icons.VIDEO, 'magenta'),  # 
    'msf': ('\uf370', ''),  # 
    'msi': (Icons.OS_WINDOWS, ''),  # 
    'mts': (Icons.LANG_TYPESCRIPT, 'green'),  # 
    'mustache': (Icons.MUSTACHE, ''),  # 
    'nef': (Icons.IMAGE, 'bright_magenta'),  # 
    'nfo': (Icons.INFO, ''),  # 
    'nim': (Icons.LANG_NIM, 'green'),  # 
    'nimble': (Icons.LANG_NIM, 'green'),  # 
    'nims': (Icons.LANG_NIM, 'green'),  # 
    'ninja': ('\U000f0774', ''),  # 󰝴
    'nix': ('\uf313', ''),  # 
    'node': (Icons.NODEJS, ''),  # 
    'norg': ('\ue847', ''),  # 
    'nsp': ('\U000f07e1', ''),  # 󰟡
    'nu': (Icons.SHELL_CMD, 'green'),  # 
    'o': (Icons.BINARY, 'dim'),  # 
    'obj': (Icons.FILE_3D, ''),  # 󰆧
    'odb': (Icons.DATABASE, 'cyan'),  # 
    'odf': ('\uf37b', ''),  # 
    'odg': ('\uf379', ''),  # 
    'odp': ('\uf37a', ''),  # 
    'ods': ('\uf378', ''),  # 
    'odt': ('\uf37c', ''),  # 
    'ogg': (Icons.AUDIO, 'magenta'),  # 
    'ogm': (Icons.VIDEO, 'magenta'),  # 
    'ogv': (Icons.VIDEO, 'magenta'),  # 
    'opam': ('\U000f0627', ''),  # 󰘧
    'opml': (Icons.XML, 'cyan'),  # 󰗀
    'opus': (Icons.AUDIO, 'magenta'),  # 
    'orf': (Icons.IMAGE, 'bright_magenta'),  # 
    'org': ('\ue633', ''),  # 
    'otf': (Icons.FONT, ''),  # 
    'out': ('\ueb2c', ''),  # 
    'p12': (Icons.KEY, ''),  # 
    'par': (Icons.COMPRESSED, 'red'),  # 
    'part': (Icons.DOWNLOAD, ''),  # 󰇚
    'patch': (Icons.DIFF, ''),  # 
    'pbm': (Icons.IMAGE, 'bright_magenta'),  # 
    'pcbdoc': (Icons.EDA_PCB, ''),  # 
    'pcm': (Icons.AUDIO, 'magenta'),  # 
    'pdf': ('\uf1c1', ''),  # 
    'pem': (Icons.KEY, ''),  # 
    'pfx': (Icons.KEY, ''),  # 
    'pgm': (Icons.IMAGE, 'bright_magenta'),  # 
    'phar': (Icons.LANG_PHP, 'green'),  # 
    'php': (Icons.LANG_PHP, 'green'),  # 
    'pkg': ('\ueb29', ''),  # 
    'pl': (Icons.LANG_PERL, 'green'),  # 
    'plist': (Icons.OS_APPLE, ''),  # 
    'pls': (Icons.PLAYLIST, ''),  # 󰲹
    'plx': (Icons.LANG_PERL, 'green'),  # 
    'ply': (Icons.FILE_3D, ''),  # 󰆧
    'pm': (Icons.LANG_PERL, 'green'),  # 
    'png': (Icons.IMAGE, 'bright_magenta'),  # 
    'pnm': (Icons.IMAGE, 'bright_magenta'),  # 
    'po': (Icons.TRANSLATION, ''),  # 󰗊
    'pod': (Icons.LANG_PERL, 'green'),  # 
    'pot': (Icons.TRANSLATION, ''),  # 󰗊
    'pp': ('\ue631', ''),  # 
    'ppm': (Icons.IMAGE, 'bright_magenta'),  # 
    'pps': (Icons.SLIDE, ''),  # 
    'ppsx': (Icons.SLIDE, ''),  # 
    'ppt': (Icons.SLIDE, ''),  # 
    'pptx': (Icons.SLIDE, ''),  # 
    'prjpcb': (Icons.EDA_PCB, ''),  # 
    'procfile': (Icons.LANG_RUBY, 'green'),  # 
    'properties': (Icons.JSON, 'cyan'),  # 
    'prql': (Icons.DATABASE, 'cyan'),  # 
    'ps': (Icons.VECTOR, 'bright_magenta'),  # 󰕙
    'ps1': (Icons.POWERSHELL, ''),  # 
    'psb': ('\ue7b8', ''),  # 
    'psd': ('\ue7b8', ''),  # 
    'psd1': (Icons.POWERSHELL, ''),  # 
    'psf': (Icons.FONT, ''),  # 
    'psm': (Icons.CAD, ''),  # 󰻫
    'psm1': (Icons.POWERSHELL, ''),  # 
    'pub': (Icons.PUBLIC_KEY, ''),  # 󰷖
    'purs': ('\ue630', ''),  # 
    'pxd': (Icons.LANG_PYTHON, 'green'),  # 
    'pxm': (Icons.IMAGE, 'bright_magenta'),  # 
    'py': (Icons.LANG_PYTHON, 'green'),  # 
    'pyc': (Icons.LANG_PYTHON, 'green'),  # 
    'pyd': (Icons.LANG_PYTHON, 'green'),  # 
    'pyi': (Icons.LANG_PYTHON, 'green'),  # 
    'pyo': (Icons.LANG_PYTHON, 'green'),  # 
    'pyw': (Icons.LANG_PYTHON, 'green'),  # 
    'pyx': (Icons.LANG_PYTHON, 'green'),  # 
    'qcow': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'qcow2': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'qm': (Icons.TRANSLATION, ''),  # 󰗊
    'qml': (Icons.QT, ''),  # 
    'qrc': (Icons.QT, ''),  # 
    'qss': (Icons.QT, ''),  # 
    'r': (Icons.LANG_R, 'green'),  # 
    'rake': (Icons.LANG_RUBY, 'green'),  # 
    'rakefile': (Icons.LANG_RUBY, 'green'),  # 
    'rar': (Icons.COMPRESSED, 'red'),  # 
    'raw': (Icons.IMAGE, 'bright_magenta'),  # 
    'razor': (Icons.RAZOR, ''),  # 
    'rb': (Icons.LANG_RUBY, 'green'),  # 
    'rdata': (Icons.LANG_R, 'green'),  # 
    'rdb': ('\ue76d', ''),  # 
    'rdoc': (Icons.MARKDOWN, ''),  # 
    'rds': (Icons.LANG_R, 'green'),  # 
    'readme': (Icons.README, ''),  # 󰂺
    'rkt': (Icons.LANG_SCHEME, 'green'),  # 
    'rlib': (Icons.LANG_RUST, 'green'),  # 
    'rmd': (Icons.MARKDOWN, ''),  # 
    'rmeta': (Icons.LANG_RUST, 'green'),  # 
    'rpm': ('\ue7bb', ''),  # 
    'rs': (Icons.LANG_RUST, 'green'),  # 
    'rspec': (Icons.LANG_RUBY, 'green'),  # 
    'rspec_parallel': (Icons.LANG_RUBY, 'green'),  # 
    'rspec_status': (Icons.LANG_RUBY, 'green'),  # 
    'rss': ('\uf09e', ''),  # 
    'rst': (Icons.TEXT, ''),  # 
    'rtf': (Icons.TEXT, ''),  # 
    'ru': (Icons.LANG_RUBY, 'green'),  # 
    'rubydoc': (Icons.LANG_RUBYRAILS, 'green'),  # 
    's': (Icons.LANG_ASSEMBLY, 'green'),  # 
    's3db': (Icons.SQLITE, 'dim'),  # 
    'sal': ('\U000f147b', ''),  # 󱑻
    'sass': (Icons.LANG_SASS, 'green'),  # 
    'sbt': (Icons.SUBTITLE, ''),  # 󰨖
    'scad': ('\uf34e', ''),  # 
    'scala': ('\ue737', ''),  # 
    'scm': (Icons.LANG_SCHEME, 'green'),  # 
    'sch': (Icons.EDA_SCH, ''),  # 󰭅
    'schdoc': (Icons.EDA_SCH, ''),  # 󰭅
    'scss': (Icons.LANG_SASS, 'green'),  # 
    'service': ('\ueba2', ''),  # 
    'sf2': ('\U000f0f70', ''),  # 󰽰
    'sfz': ('\U000f0f70', ''),  # 󰽰
    'sh': (Icons.SHELL_CMD, 'green'),  # 
    'sha1': (Icons.SHIELD_CHECK, ''),  # 󰕥
    'sha224': (Icons.SHIELD_CHECK, ''),  # 󰕥
    'sha256': (Icons.SHIELD_CHECK, ''),  # 󰕥
    'sha384': (Icons.SHIELD_CHECK, ''),  # 󰕥
    'sha512': (Icons.SHIELD_CHECK, ''),  # 󰕥
    'shell': (Icons.SHELL_CMD, 'green'),  # 
    'shtml': (Icons.HTML5, 'green'),  # 
    'sig': (Icons.SIGNED_FILE, ''),  # 󱧃
    'signature': (Icons.SIGNED_FILE, ''),  # 󱧃
    'sld': (Icons.LANG_SCHEME, 'green'),  # 
    'skp': (Icons.CAD, ''),  # 󰻫
    'sl3': (Icons.SQLITE, 'dim'),  # 
    'sldasm': (Icons.CAD, ''),  # 󰻫
    'sldprt': (Icons.CAD, ''),  # 󰻫
    'slim': (Icons.LANG_RUBYRAILS, 'green'),  # 
    'sln': ('\ue70c', ''),  # 
    'slvs': (Icons.CAD, ''),  # 󰻫
    'so': (Icons.OS_LINUX, ''),  # 
    'sql': (Icons.DATABASE, 'cyan'),  # 
    'sqlite': (Icons.SQLITE, 'dim'),  # 
    'sqlite3': (Icons.SQLITE, 'dim'),  # 
    'sr': ('\U000f147b', ''),  # 󱑻
    'srt': (Icons.SUBTITLE, ''),  # 󰨖
    'ss': (Icons.LANG_SCHEME, 'green'),  # 
    'ssa': (Icons.SUBTITLE, ''),  # 󰨖
    'stl': (Icons.FILE_3D, ''),  # 󰆧
    'ste': (Icons.CAD, ''),  # 󰻫
    'step': (Icons.CAD, ''),  # 󰻫
    'stp': (Icons.CAD, ''),  # 󰻫
    'sty': (Icons.LANG_TEX, 'green'),  # 
    'styl': (Icons.LANG_STYLUS, 'green'),  # 
    'stylus': (Icons.LANG_STYLUS, 'green'),  # 
    'sub': (Icons.SUBTITLE, ''),  # 󰨖
    'sublime-build': (Icons.SUBLIME, ''),  # 
    'sublime-keymap': (Icons.SUBLIME, ''),  # 
    'sublime-menu': (Icons.SUBLIME, ''),  # 
    'sublime-options': (Icons.SUBLIME, ''),  # 
    'sublime-package': (Icons.SUBLIME, ''),  # 
    'sublime-project': (Icons.SUBLIME, ''),  # 
    'sublime-session': (Icons.SUBLIME, ''),  # 
    'sublime-settings': (Icons.SUBLIME, ''),  # 
    'sublime-snippet': (Icons.SUBLIME, ''),  # 
    'sublime-theme': (Icons.SUBLIME, ''),  # 
    'suo': ('\ue70c', ''),  # 
    'svelte': ('\ue697', ''),  # 
    'sv': (Icons.LANG_HDL, 'green'),  # 󰍛
    'svg': (Icons.VECTOR, 'bright_magenta'),  # 󰕙
    'svh': (Icons.LANG_HDL, 'green'),  # 󰍛
    'swf': (Icons.AUDIO, 'magenta'),  # 
    'swift': ('\ue755', ''),  # 
    't': (Icons.LANG_PERL, 'green'),  # 
    'tbc': (Icons.TCL, ''),  # 󰛓
    'tar': (Icons.COMPRESSED, 'red'),  # 
    'taz': (Icons.COMPRESSED, 'red'),  # 
    'tbz': (Icons.COMPRESSED, 'red'),  # 
    'tbz2': (Icons.COMPRESSED, 'red'),  # 
    'tc': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'tcl': (Icons.TCL, ''),  # 󰛓
    'tex': (Icons.LANG_TEX, 'green'),  # 
    'tf': (Icons.TERRAFORM, ''),  # 󱁢
    'tfstate': (Icons.TERRAFORM, ''),  # 󱁢
    'tfvars': (Icons.TERRAFORM, ''),  # 󱁢
    'tgz': (Icons.COMPRESSED, 'red'),  # 
    'tif': (Icons.IMAGE, 'bright_magenta'),  # 
    'tiff': (Icons.IMAGE, 'bright_magenta'),  # 
    'tlz': (Icons.COMPRESSED, 'red'),  # 
    'tml': (Icons.CONFIG, 'cyan'),  # 
    'tmux': (Icons.TMUX, ''),  # 
    'toml': (Icons.TOML, 'cyan'),  # 
    'torrent': ('\ue275', ''),  # 
    'tres': (Icons.GODOT, ''),  # 
    'ts': (Icons.LANG_TYPESCRIPT, 'green'),  # 
    'tscn': (Icons.GODOT, ''),  # 
    'tsv': (Icons.SHEET, 'cyan'),  # 
    'tsx': (Icons.REACT, 'green'),  # 
    'ttc': (Icons.FONT, ''),  # 
    'ttf': (Icons.FONT, ''),  # 
    'twig': ('\ue61c', ''),  # 
    'txt': (Icons.TEXT, ''),  # 
    'typ': (Icons.TYPST, ''),  # 
    'txz': (Icons.COMPRESSED, 'red'),  # 
    'tz': (Icons.COMPRESSED, 'red'),  # 
    'tzo': (Icons.COMPRESSED, 'red'),  # 
    'ui': ('\uf2d0', ''),  # 
    'unity': (Icons.UNITY, ''),  # 
    'unity3d': (Icons.UNITY, ''),  # 
    'v': (Icons.LANG_V, 'green'),  # 
    'vala': ('\ue8d1', ''),  # 
    'vdi': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'vhd': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'vhs': ('\U000f0a1b', ''),  # 󰨛
    'vi': ('\ue81e', ''),  # 
    'vhdl': (Icons.LANG_HDL, 'green'),  # 󰍛
    'video': (Icons.VIDEO, 'magenta'),  # 
    'vim': (Icons.VIM, 'green'),  # 
    'vmdk': (Icons.DISK_IMAGE, 'bright_magenta'),  # 
    'vob': (Icons.VIDEO, 'magenta'),  # 
    'vsix': ('\U000f0a1e', ''),  # 󰨞
    'vue': ('\U000f0844', ''),  # 󰡄
    'war': (Icons.LANG_JAVA, 'green'),  # 
    'wav': (Icons.AUDIO, 'magenta'),  # 
    'webm': (Icons.VIDEO, 'magenta'),  # 
    'webmanifest': (Icons.JSON, 'cyan'),  # 
    'webp': (Icons.IMAGE, 'bright_magenta'),  # 
    'whl': (Icons.LANG_PYTHON, 'green'),  # 
    'windows': (Icons.OS_WINDOWS, ''),  # 
    'wma': (Icons.AUDIO, 'magenta'),  # 
    'wmv': (Icons.VIDEO, 'magenta'),  # 
    'woff': (Icons.FONT, ''),  # 
    'woff2': (Icons.FONT, ''),  # 
    'wrl': (Icons.FILE_3D, ''),  # 󰆧
    'wrz': (Icons.FILE_3D, ''),  # 󰆧
    'wv': (Icons.AUDIO, 'magenta'),  # 
    'xaml': ('\U000f0673', ''),  # 󰙳
    'xcf': (Icons.GIMP, 'bright_magenta'),  # 
    'xci': ('\U000f07e1', ''),  # 󰟡
    'xcplayground': ('\ue755', ''),  # 
    'xhtml': (Icons.HTML5, 'green'),  # 
    'xlr': (Icons.SHEET, 'cyan'),  # 
    'xls': (Icons.SHEET, 'cyan'),  # 
    'xlsm': (Icons.SHEET, 'cyan'),  # 
    'xlsx': (Icons.SHEET, 'cyan'),  # 
    'xml': (Icons.XML, 'cyan'),  # 󰗀
    'xpi': ('\ueae6', ''),  # 
    'xpm': (Icons.IMAGE, 'bright_magenta'),  # 
    'xul': (Icons.XML, 'cyan'),  # 󰗀
    'xz': (Icons.COMPRESSED, 'red'),  # 
    'x_b': (Icons.CAD, ''),  # 󰻫
    'x_t': (Icons.CAD, ''),  # 󰻫
    'yaml': (Icons.YAML, 'cyan'),  # 
    'yml': (Icons.YAML, 'cyan'),  # 
    'z': (Icons.COMPRESSED, 'red'),  # 
    'zig': ('\ue6a9', ''),  # 
    'zip': (Icons.COMPRESSED, 'red'),  # 
    'zsh': (Icons.SHELL_CMD, 'green'),  # 
    'zsh-theme': (Icons.SHELL, ''),  # 󱆃
    'zst': (Icons.COMPRESSED, 'red'),  # 
    'z64': ('\U000f1393', ''),  # 󱎓
}


def lookup_entry_decor(
    entry_name: str,
    *,
    is_dir: bool,
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
