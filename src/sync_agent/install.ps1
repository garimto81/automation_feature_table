<#
.SYNOPSIS
    GFX Sync Agent 설치 스크립트

.DESCRIPTION
    GFX PC에 Sync Agent를 설치합니다:
    1. Python 환경 확인
    2. 가상환경 생성
    3. 의존성 설치
    4. 설정 파일 생성

.EXAMPLE
    .\install.ps1
    .\install.ps1 -InstallDir "C:\GFX\SyncAgent"
#>

param(
    [string]$InstallDir = "C:\GFX\SyncAgent",
    [switch]$SkipVenv
)

$ErrorActionPreference = "Stop"

Write-Host "=== GFX Sync Agent Installer ===" -ForegroundColor Cyan
Write-Host ""

# 1. Python 버전 확인
Write-Host "[1/5] Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}

$versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
if ($matches[1] -lt 3 -or ($matches[1] -eq 3 -and $matches[2] -lt 11)) {
    Write-Host "ERROR: Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
    exit 1
}

Write-Host "  Found: $pythonVersion" -ForegroundColor Green

# 2. 설치 디렉토리 생성
Write-Host "[2/5] Creating install directory..." -ForegroundColor Yellow
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-Host "  Directory: $InstallDir" -ForegroundColor Green

# 3. 파일 복사
Write-Host "[3/5] Copying files..." -ForegroundColor Yellow
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$FilesToCopy = @(
    "__init__.py",
    "config.py",
    "config.env.example",
    "file_handler.py",
    "local_queue.py",
    "main.py",
    "sync_service.py",
    "requirements.txt"
)

foreach ($file in $FilesToCopy) {
    $src = Join-Path $ScriptDir $file
    $dst = Join-Path $InstallDir $file
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Force
        Write-Host "  Copied: $file" -ForegroundColor Gray
    } else {
        Write-Host "  WARNING: $file not found" -ForegroundColor Yellow
    }
}

# 4. 가상환경 및 의존성 설치
Write-Host "[4/5] Setting up Python environment..." -ForegroundColor Yellow
Push-Location $InstallDir

if (-not $SkipVenv) {
    if (-not (Test-Path "venv")) {
        python -m venv venv
        Write-Host "  Created virtual environment" -ForegroundColor Green
    }

    & ".\venv\Scripts\pip.exe" install -q -r requirements.txt
    Write-Host "  Installed dependencies" -ForegroundColor Green
}

Pop-Location

# 5. 설정 파일 생성
Write-Host "[5/5] Creating configuration..." -ForegroundColor Yellow
$ConfigPath = Join-Path $InstallDir "config.env"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item -Path (Join-Path $InstallDir "config.env.example") -Destination $ConfigPath
    Write-Host "  Created config.env (please edit with your settings)" -ForegroundColor Yellow
} else {
    Write-Host "  config.env already exists" -ForegroundColor Green
}

# 완료
Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Edit $ConfigPath with your Supabase credentials"
Write-Host "  2. Set GFX_WATCH_PATH to your PokerGFX output directory"
Write-Host "  3. Run: cd $InstallDir && .\venv\Scripts\python.exe -m main"
Write-Host ""
Write-Host "To register as Windows Service:" -ForegroundColor Cyan
Write-Host "  .\register-service.ps1"
