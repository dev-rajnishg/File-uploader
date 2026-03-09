# Quick run script - automatically uses virtual environment
# Usage: .\run.ps1 script_name.py

param(
    [Parameter(Mandatory=$true)]
    [string]$ScriptName
)

$venvPython = ".\.venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    Write-Host "Running with virtual environment Python..." -ForegroundColor Green
    & $venvPython $ScriptName
} else {
    Write-Host "ERROR: Virtual environment not found at $venvPython" -ForegroundColor Red
    exit 1
}
