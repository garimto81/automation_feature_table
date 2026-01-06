<#
.SYNOPSIS
    Synology NAS 배포용 패키지 빌드

.DESCRIPTION
    poker-capture-package.tar.gz 파일 생성
    USB 또는 File Station으로 NAS에 복사 후 install.sh 실행

.EXAMPLE
    .\build-package.ps1
    # 생성된 poker-capture-package.tar.gz를 NAS로 복사
#>

$ErrorActionPreference = "Stop"

# 프로젝트 경로
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DeployDir = $PSScriptRoot
$OutputDir = Join-Path $DeployDir "dist"
$PackageName = "poker-capture-package"

Write-Host "=== Building Synology NAS Package ===" -ForegroundColor Cyan
Write-Host ""

# 출력 디렉토리 정리
if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\$PackageName" | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\$PackageName\app" | Out-Null

Write-Host "[1/4] Copying application files..." -ForegroundColor Yellow

# 앱 코드 복사
Copy-Item -Recurse "$ProjectRoot\src" "$OutputDir\$PackageName\app\"
Copy-Item "$DeployDir\Dockerfile" "$OutputDir\$PackageName\app\"
Copy-Item "$DeployDir\requirements.txt" "$OutputDir\$PackageName\app\"

# 배포 파일 복사
Copy-Item "$DeployDir\docker-compose.yml" "$OutputDir\$PackageName\"
Copy-Item "$DeployDir\install.sh" "$OutputDir\$PackageName\"
Copy-Item "$DeployDir\.env.example" "$OutputDir\$PackageName\"
Copy-Item "$DeployDir\README.md" "$OutputDir\$PackageName\"

Write-Host "[2/4] Setting file permissions..." -ForegroundColor Yellow

# .gitkeep 파일 제거
Get-ChildItem -Path "$OutputDir\$PackageName" -Recurse -Name ".gitkeep" | ForEach-Object {
    Remove-Item -Path (Join-Path "$OutputDir\$PackageName" $_) -Force
}

Write-Host "[3/4] Creating package..." -ForegroundColor Yellow

# tar.gz 생성
$TarPath = "$OutputDir\$PackageName.tar.gz"
Push-Location "$OutputDir"
tar -czvf "$PackageName.tar.gz" "$PackageName"
Pop-Location

# 압축 전 폴더 삭제
Remove-Item -Recurse -Force "$OutputDir\$PackageName"

Write-Host "[4/4] Package created!" -ForegroundColor Green
Write-Host ""

$FileSize = [math]::Round((Get-Item $TarPath).Length / 1MB, 2)
Write-Host "Output: $TarPath" -ForegroundColor Cyan
Write-Host "Size: ${FileSize} MB" -ForegroundColor Cyan
Write-Host ""

Write-Host "=== Next Steps ===" -ForegroundColor Yellow
Write-Host "1. Copy the package to NAS (USB, File Station, or SCP)"
Write-Host "2. Extract on NAS:"
Write-Host "   tar -xzvf $PackageName.tar.gz -C /volume1/docker/poker-capture/"
Write-Host "3. Run installer:"
Write-Host "   cd /volume1/docker/poker-capture/$PackageName && chmod +x install.sh && ./install.sh"
