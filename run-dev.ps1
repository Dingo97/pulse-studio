$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$Root\.venv")) {
    py -3.12 -m venv "$Root\.venv"
}
& "$Root\.venv\Scripts\python.exe" -m pip install -r "$Root\backend\requirements.txt"

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$Root\backend'; & '$Root\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --port 8000"
)

Push-Location "$Root\frontend"
try {
    if (-not (Test-Path "node_modules")) { npm install }
    npm run dev
} finally {
    Pop-Location
}
