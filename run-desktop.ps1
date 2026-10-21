# Starts Mash Loop as a standalone Desktop application using Microsoft Edge WebView2.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONWARNINGS = "ignore"

$python = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found at .venv. Please set up the environment first." -ForegroundColor Red
    exit 1
}

Write-Host "Launching Meikova Loop Desktop Application..." -ForegroundColor Cyan
& $python -m loopbox.desktop @args
