# Verify host can authenticate to Docker DSH Runtime Host on :8101.
param(
    [string]$RuntimeEnvFile = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")) ".movo-dev\runtime.env")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $RuntimeEnvFile)) {
    throw "Missing $RuntimeEnvFile — run scripts/dev/sync_runtime_secrets.ps1 first."
}
$token = ""
foreach ($rawLine in [System.IO.File]::ReadAllLines($RuntimeEnvFile)) {
    $line = $rawLine.TrimStart([char]0xFEFF)
    if ($line.StartsWith("DSH_RUNTIME_HOST_TOKEN=")) {
        $token = $line.Substring("DSH_RUNTIME_HOST_TOKEN=".Length).Trim()
        break
    }
}
if (-not $token) { throw "DSH_RUNTIME_HOST_TOKEN not found in $RuntimeEnvFile" }
$response = curl.exe -s -w "`nHTTP_CODE:%{http_code}" -H "Authorization: Bearer $token" http://127.0.0.1:8101/health
Write-Host $response
if (-not ($response -match "HTTP_CODE:200")) {
    exit 1
}
