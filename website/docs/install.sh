#!/bin/sh
# storix installer: a thin, inspectable wrapper over `uv tool install`.
#
#   curl -LsSf https://storix.mghalix.com/install.sh | sh
#   curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --with azure,s3
#   curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --all
#   curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --version 0.5.0
#
# It installs one tool for the current user. It does not need root, does not
# ask for credentials, does not write configuration, and does not edit shell
# startup files. To remove it later: uv tool uninstall storix
set -eu

EXTRAS="cli"
VERSION=""
SPEC="storix"

usage() {
    cat <<'USAGE'
storix installer

Usage: install.sh [options]

  --with EXTRAS   comma-separated provider extras (azure, s3, gcs, r2, minio)
  --all           every extra, equivalent to --with azure,s3,gcs
  --version VER   install an exact version instead of the latest
  --help          show this message

Examples:
  install.sh
  install.sh --with azure,s3
  install.sh --all
  install.sh --version 0.5.0

Uninstall with: uv tool uninstall storix
USAGE
}

say() {
    printf '%s\n' "$*"
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --with)
            [ $# -ge 2 ] || die "--with needs a value, e.g. --with azure,s3"
            EXTRAS="cli,$2"
            shift 2
            ;;
        --with=*)
            EXTRAS="cli,${1#--with=}"
            shift
            ;;
        --all)
            EXTRAS="all"
            shift
            ;;
        --version)
            [ $# -ge 2 ] || die "--version needs a value, e.g. --version 0.5.0"
            VERSION="$2"
            shift 2
            ;;
        --version=*)
            VERSION="${1#--version=}"
            shift
            ;;
        --help | -h)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1 (try --help)"
            ;;
    esac
done

if [ -n "$VERSION" ]; then
    SPEC="storix==$VERSION"
fi

if ! command -v uv >/dev/null 2>&1; then
    say "uv is not installed; storix installs through it."
    say "Running the official uv installer from https://astral.sh/uv/install.sh"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # the uv installer places it here before any shell restart
    PATH="$HOME/.local/bin:$PATH"
    export PATH
    command -v uv >/dev/null 2>&1 || die "uv installation did not put uv on PATH"
fi

say "Installing ${SPEC}[${EXTRAS}] with uv tool install"
uv tool install --force "${SPEC}[${EXTRAS}]"

if command -v sx >/dev/null 2>&1; then
    say ""
    say "Installed: $(command -v sx)"
    say "Try: sx --version"
else
    say ""
    say "Installed, but sx is not on your PATH yet."
    say "Add it with: uv tool update-shell"
    say "Then restart your shell, or add ~/.local/bin to PATH yourself."
fi
