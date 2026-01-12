<#
.SYNOPSIS
    Synology NAS에 Poker Hand Capture System 자동 배포

.DESCRIPTION
    1. 배포 패키지 생성 (.tar.gz)
    2. NAS로 SCP 전송
    3. SSH로 Docker Compose 실행

.PARAMETER NasHost
    NAS IP 주소 또는 호스트명

.PARAMETER NasUser
    NAS SSH 사용자 (기본: admin)

.PARAMETER DbPassword
    PostgreSQL 비밀번호

.EXAMPLE
    .\deploy-to-nas.ps1 -NasHost 10.10.100.122 -DbPassword "mypassword"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$NasHost,

    [string]$NasUser = "admin",

    [Parameter(Mandatory=$true)]
    [string]$DbPassword,

    [string]$PgAdminPassword = "",

    [switch]$SkipBuild,

    [switch]$WithPgAdmin
)

$ErrorActionPreference = "Stop"

# 프로젝트 루트
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DeployDir = $PSScriptRoot
$TempDir = Join-Path $env:TEMP "poker-capture-deploy"
$PackageName = "poker-capture-package.tar.gz"

Write-Host "=== Poker Hand Capture System - Synology NAS Deployment ===" -ForegroundColor Cyan
Write-Host ""

# 1. 임시 디렉토리 준비
Write-Host "[1/5] Preparing package..." -ForegroundColor Yellow
if (Test-Path $TempDir) {
    Remove-Item -Recurse -Force $TempDir
}
New-Item -ItemType Directory -Path $TempDir | Out-Null
New-Item -ItemType Directory -Path "$TempDir\app" | Out-Null

# 2. 파일 복사
Write-Host "[2/5] Copying files..." -ForegroundColor Yellow

# 앱 코드 (전체 src 폴더 복사)
Copy-Item -Recurse -Force "$ProjectRoot\src" "$TempDir\app\"
Copy-Item "$DeployDir\Dockerfile" "$TempDir\app\"
Copy-Item "$DeployDir\requirements.txt" "$TempDir\app\"

# 필수 파일 검증
$RequiredFiles = @(
    "$TempDir\app\src\__init__.py",
    "$TempDir\app\src\main.py",
    "$TempDir\app\src\dashboard\__init__.py",
    "$TempDir\app\src\dashboard\monitoring_service.py",
    "$TempDir\app\src\dashboard\alerts.py",
    "$TempDir\app\src\database\__init__.py",
    "$TempDir\app\src\primary\__init__.py",
    "$TempDir\app\src\fusion\__init__.py"
)

$MissingFiles = @()
foreach ($file in $RequiredFiles) {
    if (-not (Test-Path $file)) {
        $MissingFiles += $file
    }
}

if ($MissingFiles.Count -gt 0) {
    Write-Host "ERROR: Missing required files:" -ForegroundColor Red
    $MissingFiles | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    throw "Deployment aborted due to missing files. Please check the source directory."
}

# Docker Compose
Copy-Item "$DeployDir\docker-compose.yml" "$TempDir\"

# .env 파일 생성
$EnvContent = @"
# Auto-generated for deployment
DB_PASSWORD=$DbPassword
PGADMIN_PASSWORD=$PgAdminPassword
LOG_LEVEL=INFO
VMIX_AUTO_RECORD=false
"@
$EnvContent | Out-File -FilePath "$TempDir\.env" -Encoding utf8

# 3. tar.gz 패키지 생성
Write-Host "[3/5] Creating package..." -ForegroundColor Yellow
$PackagePath = Join-Path $DeployDir $PackageName

# Windows에서 tar 사용 (Windows 10 1803+)
Push-Location $TempDir
tar -czvf $PackagePath *
Pop-Location

Write-Host "  Package created: $PackagePath" -ForegroundColor Green

# 4. NAS로 전송
Write-Host "[4/5] Uploading to NAS ($NasHost)..." -ForegroundColor Yellow

$NasPath = "/volume1/docker/poker-capture"
$SshTarget = "$NasUser@$NasHost"

# 디렉토리 생성
ssh $SshTarget "mkdir -p $NasPath/app $NasPath/data /volume1/docker/postgresql/data /volume1/docker/pokergfx/hands"

# 패키지 전송
scp $PackagePath "${SshTarget}:$NasPath/"

# 5. NAS에서 압축 해제 및 실행
Write-Host "[5/5] Deploying on NAS..." -ForegroundColor Yellow

# --no-cache를 사용하여 Docker 빌드 캐시 문제 방지 (이슈 #4)
$DeployCommand = @"
cd $NasPath && \
tar -xzvf $PackageName && \
rm $PackageName && \
docker-compose down 2>/dev/null || true && \
docker-compose build --no-cache poker-capture && \
docker-compose up -d --force-recreate
"@

if ($WithPgAdmin) {
    $DeployCommand = @"
cd $NasPath && \
tar -xzvf $PackageName && \
rm $PackageName && \
docker-compose down 2>/dev/null || true && \
docker-compose build --no-cache && \
docker-compose --profile admin up -d --force-recreate
"@
}

ssh $SshTarget $DeployCommand

# 상태 확인
Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Container Status:" -ForegroundColor Cyan
ssh $SshTarget "cd $NasPath && docker-compose ps"

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. PokerGFX JSON 출력 경로 설정: \\$NasHost\docker\pokergfx\hands\"
Write-Host "  2. 로그 확인: ssh $SshTarget 'docker-compose -f $NasPath/docker-compose.yml logs -f poker-capture'"
if ($WithPgAdmin) {
    Write-Host "  3. pgAdmin 접속: http://${NasHost}:5050"
}

# 정리
Remove-Item -Recurse -Force $TempDir
