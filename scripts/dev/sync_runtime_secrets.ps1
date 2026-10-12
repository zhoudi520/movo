# Copy Docker bootstrap secrets to .movo-dev/runtime.env for host-side backends.
param(
    [string]$VolumePrefix = $(if ($env:MOVO_VOLUME_PREFIX) { $env:MOVO_VOLUME_PREFIX } else { "movo" })
)

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$OutDir = Join-Path $RootDir ".movo-dev"
$OutFile = Join-Path $OutDir "runtime.env"
$VolumeName = "${VolumePrefix}_deployment-secrets"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$raw = docker run --rm -v "${VolumeName}:/run/askai-secrets:ro" alpine:3.21 cat /run/askai-secrets/runtime.env
if (-not $raw) {
    throw "Could not read runtime.env from Docker volume ${VolumeName}"
}
[System.IO.File]::WriteAllText($OutFile, $raw.TrimEnd() + "`n")

Write-Host "Wrote $OutFile from Docker volume $VolumeName"
Write-Host "Restart chat-api / run_backends.py so Settings reloads the DSH token."
