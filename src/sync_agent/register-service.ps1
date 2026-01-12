<#
.SYNOPSIS
    GFX Sync Agent를 Windows 서비스로 등록

.DESCRIPTION
    NSSM (Non-Sucking Service Manager)을 사용하여
    Sync Agent를 Windows 서비스로 등록합니다.

.EXAMPLE
    .\register-service.ps1
    .\register-service.ps1 -ServiceName "GFXSyncAgent" -Uninstall
#>

param(
    [string]$ServiceName = "GFXSyncAgent",
    [string]$InstallDir = "C:\GFX\SyncAgent",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# NSSM 확인
$nssmPath = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssmPath) {
    Write-Host "NSSM not found. Installing via winget..." -ForegroundColor Yellow
    winget install --id nssm.nssm -e --source winget
    $nssmPath = "nssm"
}

if ($Uninstall) {
    Write-Host "Uninstalling service: $ServiceName" -ForegroundColor Yellow
    nssm stop $ServiceName 2>$null
    nssm remove $ServiceName confirm
    Write-Host "Service removed." -ForegroundColor Green
    exit 0
}

# 서비스 등록
Write-Host "=== Registering Windows Service ===" -ForegroundColor Cyan

$PythonPath = Join-Path $InstallDir "venv\Scripts\python.exe"
$MainScript = Join-Path $InstallDir "main.py"
$ConfigPath = Join-Path $InstallDir "config.env"
$LogPath = Join-Path $InstallDir "logs"

# 로그 디렉토리 생성
if (-not (Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
}

# 기존 서비스 제거
$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "Removing existing service..." -ForegroundColor Yellow
    nssm stop $ServiceName 2>$null
    nssm remove $ServiceName confirm
}

# 새 서비스 등록
Write-Host "Installing service..." -ForegroundColor Yellow
nssm install $ServiceName $PythonPath
nssm set $ServiceName AppParameters "-m main --config `"$ConfigPath`""
nssm set $ServiceName AppDirectory $InstallDir
nssm set $ServiceName DisplayName "GFX Sync Agent"
nssm set $ServiceName Description "PokerGFX JSON to Supabase synchronization agent"
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName AppStdout (Join-Path $LogPath "stdout.log")
nssm set $ServiceName AppStderr (Join-Path $LogPath "stderr.log")
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateBytes 10485760

# 서비스 시작
Write-Host "Starting service..." -ForegroundColor Yellow
nssm start $ServiceName

# 상태 확인
Start-Sleep -Seconds 2
$status = (Get-Service -Name $ServiceName).Status
if ($status -eq "Running") {
    Write-Host ""
    Write-Host "=== Service Registered Successfully ===" -ForegroundColor Green
    Write-Host "  Service Name: $ServiceName"
    Write-Host "  Status: Running"
    Write-Host "  Logs: $LogPath"
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Cyan
    Write-Host "  Stop:    nssm stop $ServiceName"
    Write-Host "  Start:   nssm start $ServiceName"
    Write-Host "  Restart: nssm restart $ServiceName"
    Write-Host "  Status:  nssm status $ServiceName"
    Write-Host "  Remove:  .\register-service.ps1 -Uninstall"
} else {
    Write-Host "WARNING: Service may not have started properly." -ForegroundColor Yellow
    Write-Host "Check logs at: $LogPath" -ForegroundColor Yellow
}
