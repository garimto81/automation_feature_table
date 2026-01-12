# SMB Signing Fix Script for NAS Connection
# Run this script as Administrator

Write-Host "=== SMB Signing Fix Script ===" -ForegroundColor Cyan
Write-Host ""

# Check current setting
Write-Host "[1] Current SMB Signing Settings:" -ForegroundColor Yellow
$current = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" -ErrorAction SilentlyContinue
Write-Host "  RequireSecuritySignature: $($current.RequireSecuritySignature)"
Write-Host "  EnableSecuritySignature: $($current.EnableSecuritySignature)"
Write-Host ""

# Disable RequireSecuritySignature
Write-Host "[2] Disabling RequireSecuritySignature..." -ForegroundColor Yellow
try {
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" -Name "RequireSecuritySignature" -Value 0 -Type DWord
    Write-Host "  SUCCESS: RequireSecuritySignature set to 0" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Verify change
Write-Host ""
Write-Host "[3] Verifying change:" -ForegroundColor Yellow
$updated = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters"
Write-Host "  RequireSecuritySignature: $($updated.RequireSecuritySignature)"
Write-Host ""

# Restart LanmanWorkstation service
Write-Host "[4] Restarting LanmanWorkstation service..." -ForegroundColor Yellow
try {
    Restart-Service LanmanWorkstation -Force
    Write-Host "  SUCCESS: Service restarted" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: Could not restart service. Please restart manually or reboot." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[5] Testing SMB connection to NAS (10.10.100.122)..." -ForegroundColor Yellow
$result = Test-NetConnection -ComputerName 10.10.100.122 -Port 445
if ($result.TcpTestSucceeded) {
    Write-Host "  Port 445: OPEN" -ForegroundColor Green
} else {
    Write-Host "  Port 445: CLOSED" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Script Complete ===" -ForegroundColor Cyan
Write-Host "Please test: net use \\10.10.100.122\docker" -ForegroundColor White
