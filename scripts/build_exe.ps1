<#
.SYNOPSIS
    Poker Hand Auto-Capture System Build Script

.DESCRIPTION
    PyInstaller를 사용하여 exe 패키징 수행.
    다른 장비에서 Python 설치 없이 실행 가능한 실행 파일 생성.

.EXAMPLE
    .\scripts\build_exe.ps1
    .\scripts\build_exe.ps1 -Clean
    .\scripts\build_exe.ps1 -Verbose

.OUTPUTS
    dist/PokerHandCapture/PokerHandCapture.exe
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Poker Hand Capture System Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Clean 옵션 처리
if ($Clean) {
    Write-Host "[1/5] Cleaning previous builds..." -ForegroundColor Yellow

    $foldersToClean = @("build", "dist", "__pycache__")
    foreach ($folder in $foldersToClean) {
        $path = Join-Path $ProjectRoot $folder
        if (Test-Path $path) {
            Remove-Item -Path $path -Recurse -Force
            Write-Host "  Removed: $folder" -ForegroundColor Gray
        }
    }

    # .spec 캐시 정리
    Get-ChildItem -Path $ProjectRoot -Filter "*.spec.bak" -ErrorAction SilentlyContinue | Remove-Item -Force

    Write-Host "  Clean completed." -ForegroundColor Green
} else {
    Write-Host "[1/5] Skipping clean (use -Clean flag to enable)" -ForegroundColor Gray
}

Write-Host ""

# 의존성 설치
if (-not $SkipInstall) {
    Write-Host "[2/5] Installing build dependencies..." -ForegroundColor Yellow

    pip install -e ".[build]" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install dependencies"
        exit 1
    }
    Write-Host "  Dependencies installed." -ForegroundColor Green
} else {
    Write-Host "[2/5] Skipping dependency install (use -SkipInstall flag)" -ForegroundColor Gray
}

Write-Host ""

# PyInstaller 버전 확인
Write-Host "[3/5] Checking PyInstaller..." -ForegroundColor Yellow
$pyinstallerVersion = pyinstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller not found. Run: pip install pyinstaller"
    exit 1
}
Write-Host "  PyInstaller version: $pyinstallerVersion" -ForegroundColor Green

Write-Host ""

# 빌드 실행
Write-Host "[4/5] Building executable..." -ForegroundColor Yellow
Write-Host "  This may take several minutes..." -ForegroundColor Gray

$specFile = Join-Path $ProjectRoot "poker_capture.spec"
if (-not (Test-Path $specFile)) {
    Write-Error "Spec file not found: $specFile"
    exit 1
}

pyinstaller $specFile --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
    exit 1
}

Write-Host "  Build completed." -ForegroundColor Green

Write-Host ""

# 결과 확인
Write-Host "[5/5] Verifying build output..." -ForegroundColor Yellow

$exePath = Join-Path $ProjectRoot "dist\PokerHandCapture\PokerHandCapture.exe"
if (Test-Path $exePath) {
    $fileInfo = Get-Item $exePath
    $sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " BUILD SUCCESSFUL" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Output: $exePath" -ForegroundColor White
    Write-Host "Size: $sizeMB MB" -ForegroundColor White
    Write-Host ""
    Write-Host "To run on another machine:" -ForegroundColor Yellow
    Write-Host "  1. Copy the entire 'dist/PokerHandCapture' folder" -ForegroundColor Gray
    Write-Host "  2. Create .env file from .env.example" -ForegroundColor Gray
    Write-Host "  3. Run PokerHandCapture.exe" -ForegroundColor Gray
    Write-Host ""

    # dist 폴더 내용 표시
    $distFolder = Join-Path $ProjectRoot "dist\PokerHandCapture"
    $totalSize = (Get-ChildItem -Path $distFolder -Recurse | Measure-Object -Property Length -Sum).Sum
    $totalSizeMB = [math]::Round($totalSize / 1MB, 2)

    Write-Host "Distribution folder contents:" -ForegroundColor Yellow
    Write-Host "  Total size: $totalSizeMB MB" -ForegroundColor Gray

} else {
    Write-Error "Build output not found: $exePath"
    exit 1
}
