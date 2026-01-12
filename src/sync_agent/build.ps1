<#
.SYNOPSIS
    GFX Sync Agent 빌드 스크립트

.DESCRIPTION
    PyInstaller를 사용하여 독립 실행 파일(.exe)을 생성합니다.
    모든 의존성이 포함된 단일 배포 패키지를 만듭니다.

.PARAMETER Clean
    빌드 전 기존 빌드 폴더 삭제

.PARAMETER OneFile
    단일 .exe 파일로 빌드 (기본: 폴더 배포)

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Clean
    .\build.ps1 -OneFile
#>

param(
    [switch]$Clean,
    [switch]$OneFile,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

Write-Host "=== GFX Sync Agent Build ===" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"
Write-Host ""

# 1. 빌드 환경 확인
Write-Host "[1/5] Checking build environment..." -ForegroundColor Yellow

# Python 확인
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found" -ForegroundColor Red
    exit 1
}
Write-Host "  Python: $pythonVersion" -ForegroundColor Green

# PyInstaller 확인/설치
$pyinstaller = pip show pyinstaller 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}
Write-Host "  PyInstaller: installed" -ForegroundColor Green

# 2. 기존 빌드 정리
if ($Clean) {
    Write-Host "[2/5] Cleaning previous builds..." -ForegroundColor Yellow
    $foldersToClean = @("build", "dist", "__pycache__")
    foreach ($folder in $foldersToClean) {
        $path = Join-Path $ScriptDir $folder
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
            Write-Host "  Removed: $folder" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "[2/5] Skipping clean (use -Clean to force)" -ForegroundColor Gray
}

# 3. 테스트 실행
if (-not $SkipTests) {
    Write-Host "[3/5] Running tests..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    python -m pytest tests/sync_agent/ -v --tb=short -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Tests failed. Fix tests before building." -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
    Write-Host "  All tests passed" -ForegroundColor Green
} else {
    Write-Host "[3/5] Skipping tests (use without -SkipTests to run)" -ForegroundColor Gray
}

# 4. PyInstaller 빌드
Write-Host "[4/5] Building executable..." -ForegroundColor Yellow
Push-Location $ScriptDir

if ($OneFile) {
    Write-Host "  Mode: Single executable file" -ForegroundColor Gray
    # 단일 파일 빌드
    pyinstaller --onefile --name GFXSyncAgent `
        --hidden-import=supabase `
        --hidden-import=postgrest `
        --hidden-import=gotrue `
        --hidden-import=realtime `
        --hidden-import=storage3 `
        --hidden-import=httpx `
        --hidden-import=pydantic `
        --hidden-import=pydantic_settings `
        --hidden-import=watchdog `
        --hidden-import=watchdog.observers.polling `
        --hidden-import=dotenv `
        --exclude-module=tkinter `
        --exclude-module=matplotlib `
        --exclude-module=numpy `
        --exclude-module=pytest `
        --add-data "config.env.example;." `
        --console `
        main.py
} else {
    Write-Host "  Mode: Folder distribution" -ForegroundColor Gray
    # spec 파일 사용
    pyinstaller sync_agent.spec
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}

Pop-Location
Write-Host "  Build completed" -ForegroundColor Green

# 5. 배포 패키지 생성
Write-Host "[5/5] Creating distribution package..." -ForegroundColor Yellow

$DistDir = Join-Path $ScriptDir "dist"
$PackageDir = Join-Path $DistDir "GFXSyncAgent-Package"

if (Test-Path $PackageDir) {
    Remove-Item -Recurse -Force $PackageDir
}
New-Item -ItemType Directory -Path $PackageDir | Out-Null

# 파일 복사
if ($OneFile) {
    Copy-Item (Join-Path $DistDir "GFXSyncAgent.exe") $PackageDir
} else {
    Copy-Item -Recurse (Join-Path $DistDir "GFXSyncAgent") (Join-Path $PackageDir "bin")
}

# 설정 파일 및 스크립트 복사
Copy-Item (Join-Path $ScriptDir "config.env.example") (Join-Path $PackageDir "config.env.example")
Copy-Item (Join-Path $ScriptDir "install.ps1") $PackageDir
Copy-Item (Join-Path $ScriptDir "register-service.ps1") $PackageDir

# README 생성
$ReadmeContent = @"
# GFX Sync Agent

PokerGFX JSON 파일을 Supabase로 직접 동기화하는 에이전트입니다.

## 설치

1. config.env.example을 config.env로 복사
2. config.env에 Supabase 정보 입력
3. GFXSyncAgent.exe 실행

## 설정

config.env 파일을 편집하세요:

``````
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
GFX_WATCH_PATH=C:\GFX\output
``````

## 실행

### 수동 실행
``````
GFXSyncAgent.exe --config config.env
``````

### Windows 서비스로 등록
``````powershell
.\register-service.ps1
``````

## 문제 해결

로그 파일 위치: C:\GFX\logs\sync_agent.log

문의: https://github.com/garimto81/automation_feature_table/issues
"@

$ReadmeContent | Out-File -FilePath (Join-Path $PackageDir "README.md") -Encoding utf8

# ZIP 압축
$ZipPath = Join-Path $DistDir "GFXSyncAgent-v1.0.0.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath
}
Compress-Archive -Path "$PackageDir\*" -DestinationPath $ZipPath

Write-Host "  Package created: $ZipPath" -ForegroundColor Green

# 완료
Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Output files:" -ForegroundColor Cyan
if ($OneFile) {
    Write-Host "  Executable: $DistDir\GFXSyncAgent.exe"
} else {
    Write-Host "  Executable: $DistDir\GFXSyncAgent\GFXSyncAgent.exe"
}
Write-Host "  Package:    $ZipPath"
Write-Host ""
Write-Host "To deploy to GFX PC:" -ForegroundColor Cyan
Write-Host "  1. Copy $ZipPath to GFX PC"
Write-Host "  2. Extract to desired location"
Write-Host "  3. Edit config.env with Supabase credentials"
Write-Host "  4. Run GFXSyncAgent.exe or register as service"
