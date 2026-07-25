# storix installer for Windows: a thin, inspectable wrapper over `uv tool install`.
#
#   powershell -c "irm https://storix.mghalix.com/install.ps1 | iex"
#   & ([scriptblock]::Create((irm https://storix.mghalix.com/install.ps1))) -With azure,s3
#
# It installs one tool for the current user. It does not need administrator
# rights, does not ask for credentials, does not write configuration, and does
# not edit your profile. To remove it later: uv tool uninstall storix
[CmdletBinding()]
param(
    [string] $With = '',
    [switch] $All,
    [string] $Version = '',
    [switch] $Help
)

$ErrorActionPreference = 'Stop'

function Show-Usage {
    @'
storix installer

Usage: install.ps1 [options]

  -With EXTRAS    comma-separated provider extras (azure, s3, gcs, r2, minio)
  -All            every extra, equivalent to -With azure,s3,gcs
  -Version VER    install an exact version instead of the latest
  -Help           show this message

Examples:
  install.ps1
  install.ps1 -With azure,s3
  install.ps1 -All
  install.ps1 -Version 0.5.0

Uninstall with: uv tool uninstall storix
'@ | Write-Output
}

if ($Help) {
    Show-Usage
    exit 0
}

$extras = 'cli'
if ($All) {
    $extras = 'all'
} elseif ($With) {
    $extras = "cli,$With"
}

$spec = 'storix'
if ($Version) {
    $spec = "storix==$Version"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Output 'uv is not installed; storix installs through it.'
    Write-Output 'Running the official uv installer from https://astral.sh/uv/install.ps1'
    # in a child shell, not this scope: uv's installer assigns variables of its
    # own, and a name this script declares as a param (-Help) cannot be
    # overwritten once PowerShell has optimized the scope holding it.
    $shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
    & $shell -NoProfile -ExecutionPolicy Bypass -Command 'Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression'
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'the uv installer failed'
        exit 1
    }
    $uvBin = Join-Path $env:USERPROFILE '.local\bin'
    $env:Path = "$uvBin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error 'uv installation did not put uv on PATH'
        exit 1
    }
}

Write-Output "Installing $spec[$extras] with uv tool install"
uv tool install --force "$spec[$extras]"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$sx = Get-Command sx -ErrorAction SilentlyContinue
Write-Output ''
if ($sx) {
    Write-Output "Installed: $($sx.Source)"
    Write-Output 'Try: sx --version'
} else {
    Write-Output 'Installed, but sx is not on your PATH yet.'
    Write-Output 'Add it with: uv tool update-shell'
    Write-Output 'Then open a new terminal.'
}
