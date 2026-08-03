param(
    [string]$AnnotatorId = ""
)

$ErrorActionPreference = "Stop"
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Join-Path $toolDir "data\pilot_manifest.json"

if (-not (Test-Path -LiteralPath $manifest)) {
    throw "Pilot data가 없습니다. 먼저 prepare_pilot.py를 실행하세요."
}

$arguments = @(
    (Join-Path $toolDir "app.py"),
    "--open-browser",
    "--port", "8765"
)
if ($AnnotatorId) {
    $arguments += @("--annotator", $AnnotatorId)
}

Write-Host "REL annotation server: http://127.0.0.1:8765"
Write-Host "종료할 때 이 창에서 Ctrl+C를 누르세요."
& python @arguments
