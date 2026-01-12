# NAS SMB 설정 확인 체크리스트

## 문서 정보

| 항목 | 내용 |
|------|------|
| **관련 PRD** | PRD-0010 |
| **상태** | 인프라 에스컬레이션 대기 |
| **마지막 업데이트** | 2026-01-09 |

---

## 1. Synology DSM 설정 (NAS 관리자 권한 필요)

### 1.1 SMB 서비스 확인

**경로**: 제어판 → 파일 서비스 → SMB

| 항목 | 확인 | 권장 설정 |
|------|:----:|----------|
| SMB 서비스 활성화됨 | [ ] | 활성화 |
| 최대 SMB 프로토콜 | [ ] | **SMB3** |
| 최소 SMB 프로토콜 | [ ] | **SMB2** (SMB1 비활성화 가능) |

### 1.2 고급 설정 확인

**경로**: 제어판 → 파일 서비스 → SMB → 고급 설정

| 항목 | 확인 | 권장 설정 | 비고 |
|------|:----:|----------|------|
| 서버 서명 강제 | [ ] | **"없음"** 또는 **"선택적"** | 핵심 설정 |
| Opportunistic Locking | [ ] | 활성화 | 성능 향상 |
| 대역폭 제한 | [ ] | 없음 | 제한 시 성능 저하 |
| SMB 암호화 | [ ] | 선택적 | 필수 시 클라이언트 호환성 확인 |

> **핵심**: "서버 서명 강제"가 "필수"로 설정된 경우 Windows 클라이언트와 충돌할 수 있습니다.

### 1.3 공유 폴더 권한

**경로**: 제어판 → 공유 폴더 → docker → 편집

| 항목 | 확인 | 값 |
|------|:----:|-----|
| 공유 폴더 존재 | [ ] | `docker` |
| 하위 경로 존재 | [ ] | `/volume1/docker/pokergfx/hands` |
| 해당 사용자 읽기 권한 | [ ] | 허용 |
| 해당 사용자 쓰기 권한 | [ ] | 허용 |
| **SMB 권한** 확인 (NFS 아님) | [ ] | - |

### 1.4 방화벽 규칙

**경로**: 제어판 → 보안 → 방화벽

| 항목 | 확인 | 설정 |
|------|:----:|------|
| 방화벽 활성화 여부 | [ ] | - |
| 내부 네트워크 445/TCP 허용 | [ ] | 허용 |
| Windows PC IP 대역 허용 | [ ] | 예: 10.10.100.0/24 |

### 1.5 사용자 계정

**경로**: 제어판 → 사용자 및 그룹 → 해당 사용자

| 항목 | 확인 | 비고 |
|------|:----:|------|
| 계정 활성화됨 | [ ] | 비활성화 시 접근 불가 |
| 비밀번호 만료 안됨 | [ ] | 만료 시 갱신 필요 |
| 그룹 권한에 파일 서비스 접근 포함 | [ ] | - |
| 2단계 인증 비활성화 (SMB용) | [ ] | 2FA 활성화 시 SMB 접근 제한 |

---

## 2. Windows 측 SMB 설정

### 2.1 확인 명령어 (PowerShell)

```powershell
# 1. SMB 클라이언트 설정 확인
Get-SmbClientConfiguration

# 2. 현재 SMB 연결 목록
Get-SmbConnection

# 3. SMB 서명 설정 확인 (핵심!)
Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" | Select-Object RequireSecuritySignature, EnableSecuritySignature

# 4. SMB1 비활성화 상태 확인
Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol

# 5. SMB 관련 방화벽 규칙 확인
Get-NetFirewallRule -DisplayName "*SMB*" | Select-Object DisplayName, Enabled, Direction

# 6. 저장된 자격 증명 확인
cmdkey /list | Select-String "10.10.100.122"

# 7. 네트워크 연결 테스트
Test-NetConnection -ComputerName 10.10.100.122 -Port 445
```

### 2.2 연결 테스트

```powershell
# 기본 연결 테스트
net use \\10.10.100.122\docker

# 자격 증명 포함 연결 (테스트용)
net use \\10.10.100.122\docker /user:사용자명 비밀번호 /persistent:no

# 상세 오류 확인
net use \\10.10.100.122\docker 2>&1
```

### 2.3 수정 명령어 (관리자 권한 필요)

```powershell
# === 주의: 보안 설정 변경 ===

# SMB 서명 요구사항 비활성화 (임시 해결책)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" -Name "RequireSecuritySignature" -Value 0 -Type DWord

# SMB 서명 활성화 (선택적)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" -Name "EnableSecuritySignature" -Value 1 -Type DWord

# 변경 후 서비스 재시작
Restart-Service LanmanWorkstation -Force

# 자격 증명 삭제 및 재등록
cmdkey /delete:10.10.100.122
cmdkey /add:10.10.100.122 /user:NAS사용자명 /pass:비밀번호
```

---

## 3. 일반적인 에러 코드

| 에러 코드 | 메시지 | 원인 | 해결 방법 |
|:--------:|--------|------|----------|
| **67** | 네트워크 이름을 찾을 수 없음 | SMB 프로토콜 협상 실패 | SMB 서명/버전 설정 확인 |
| **5** | 접근 거부됨 | 권한 없음 | 자격 증명/폴더 권한 확인 |
| **53** | 네트워크 경로 없음 | 경로 또는 네트워크 문제 | 네트워크 연결/경로 확인 |
| **86** | 네트워크 암호 틀림 | 비밀번호 오류 | 자격 증명 재설정 |
| **1326** | 로그온 실패 | 사용자/비밀번호 오류 | 자격 증명 확인 |
| **64** | 네트워크 이름 삭제됨 | 연결 끊김 | 재연결 시도 |

---

## 4. System Error 67 특별 가이드

**Error 67**은 가장 흔한 SMB 연결 실패 원인입니다.

### 4.1 주요 원인

1. **SMB 서명 불일치**
   - Windows: `RequireSecuritySignature=True`
   - NAS: "서버 서명 강제" = 없음

2. **SMB 프로토콜 버전 제한**
   - NAS가 SMB2/3만 지원
   - Windows가 SMB1만 시도

3. **방화벽 차단**
   - NAS 방화벽이 특정 IP만 허용

### 4.2 해결 순서

1. NAS DSM → SMB 고급 설정 → "서버 서명 강제" = **없음** 또는 **선택적**
2. Windows → `RequireSecuritySignature` = **0**
3. Windows 자격 증명 재설정
4. `net use \\NAS_IP\공유폴더` 테스트

---

## 5. 체크 결과 기록

### 시도 이력

| 날짜 | 시도 | 결과 | 담당자 |
|------|------|------|--------|
| 2026-01-09 | NAS ping | OK | - |
| 2026-01-09 | SMB 포트 445 | OK | - |
| 2026-01-09 | NAS SMB 서비스 | OK | - |
| 2026-01-09 | 공유 폴더 SSH 확인 | OK | - |
| 2026-01-09 | `net use` 연결 | **Error 67** | - |
| - | NAS SMB 고급 설정 | 대기 | 인프라 |
| - | Windows 탐색기 직접 접근 | 대기 | 인프라 |

### 인프라 담당자 확인 필요 항목

- [ ] NAS DSM 관리자 권한으로 SMB 고급 설정 확인
- [ ] "서버 서명 강제" 설정값 확인/수정
- [ ] Windows 탐색기에서 `\\10.10.100.122` 직접 접근 테스트
- [ ] 결과 이 문서에 기록

---

## 6. 관련 문서

| 문서 | 위치 |
|------|------|
| PRD-0010 | `tasks/prds/PRD-0010-nas-smb-integration.md` |
| NAS 설정 가이드 | `docs/NAS_SETUP.md` |
| Checklist | `docs/checklists/PRD-0010.md` |
| GitHub Issue | [#5](https://github.com/garimto81/automation_feature_table/issues/5) |
