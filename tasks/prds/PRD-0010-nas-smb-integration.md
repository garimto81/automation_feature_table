# PRD-0010: NAS SMB 연동

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0010 |
| **제목** | NAS SMB 연동 - Windows ↔ NAS ↔ Docker 파일 공유 |
| **버전** | 1.0 |
| **작성일** | 2026-01-09 |
| **상태** | 🔴 Blocked |
| **상위 문서** | [PRD-0002](./PRD-0002-primary-gfx-rfid.md) |
| **관련 이슈** | [#5](https://github.com/garimto81/automation_feature_table/issues/5) |

---

## 1. 개요

### 1.1 목적

PokerGFX (Windows PC)에서 생성된 JSON 파일을 NAS SMB 공유 폴더를 통해 Docker 컨테이너로 전달하는 파일 공유 아키텍처 구현.

### 1.2 배경

| 문제 | 설명 |
|------|------|
| **현재 상황** | PokerGFX가 로컬 파일로만 JSON 출력 |
| **제약 조건** | Docker 컨테이너는 Windows 로컬 파일에 직접 접근 불가 |
| **해결 방안** | NAS SMB 공유 폴더를 중간 저장소로 활용 |

### 1.3 아키텍처

```
┌─────────────────┐     SMB/CIFS      ┌─────────────────┐
│  Windows PC     │ ───────────────▶  │  Synology NAS   │
│  (PokerGFX)     │   Port 445/TCP    │  (DSM 7.2+)     │
└─────────────────┘                   └────────┬────────┘
                                               │
        \\NAS_IP\docker\pokergfx\hands\        │ /volume1/docker/pokergfx/hands
                                               │
                                      ┌────────▼────────┐
                                      │ Docker Container │
                                      │ (poker-capture)  │
                                      │ /watch:ro        │
                                      └─────────────────┘
```

---

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | Windows에서 NAS SMB 공유 폴더에 파일 쓰기 | HIGH |
| FR-02 | Docker 컨테이너에서 NAS 볼륨 읽기 | HIGH |
| FR-03 | 파일 쓰기 완료 감지 (락 해제 대기) | HIGH |
| FR-04 | 연결 끊김 시 자동 재연결 | MEDIUM |
| FR-05 | 중복 파일 감지 (해시 기반) | MEDIUM |

### 2.2 비기능 요구사항

| ID | 요구사항 | 목표 값 |
|----|----------|---------|
| NFR-01 | 파일 전송 지연 | < 5초 |
| NFR-02 | SMB 연결 가용성 | 99.9% |
| NFR-03 | 파일 락 대기 시간 | 최대 10초 (5회 재시도) |
| NFR-04 | 네트워크 대역폭 | 10Mbps 이상 |

---

## 3. 시스템 구성

### 3.1 네트워크 환경

| 구성 요소 | IP/호스트 | 역할 |
|----------|-----------|------|
| Windows PC | 10.10.100.x | PokerGFX 실행, JSON 생성 |
| Synology NAS | 10.10.100.122 | SMB 파일 서버, Docker 호스트 |
| Docker Container | poker-capture | JSON 파일 감시, 처리 |

### 3.2 경로 매핑

| 위치 | 경로 | 용도 |
|------|------|------|
| Windows UNC | `\\10.10.100.122\docker\pokergfx\hands\` | PokerGFX 출력 경로 |
| NAS 로컬 | `/volume1/docker/pokergfx/hands` | 실제 저장 위치 |
| Docker 볼륨 | `/watch:ro` | 컨테이너 마운트 (읽기 전용) |

### 3.3 Docker Compose 설정

```yaml
services:
  poker-capture:
    volumes:
      - /volume1/docker/pokergfx/hands:/watch:ro
    environment:
      - POKERGFX_MODE=json
      - POKERGFX_JSON_PATH=/watch
      - POKERGFX_POLLING_INTERVAL=2.0
```

---

## 4. NAS SMB 설정

### 4.1 공유 폴더 설정

| 설정 | 값 | 설명 |
|------|-----|------|
| 공유 폴더 이름 | `docker` | 최상위 공유 폴더 |
| 하위 폴더 | `pokergfx/hands` | JSON 파일 저장 위치 |
| SMB 프로토콜 | SMB3 | 최대 프로토콜 버전 |
| 권한 | 읽기/쓰기 | PokerGFX 사용자 |

### 4.2 방화벽 설정

| 포트 | 프로토콜 | 용도 |
|------|----------|------|
| 445 | TCP | SMB 파일 공유 |
| 139 | TCP | NetBIOS (선택) |

---

## 5. Windows 클라이언트 설정

### 5.1 자격 증명 저장

```powershell
# 자격 증명 저장
cmdkey /add:10.10.100.122 /user:NAS사용자명 /pass:비밀번호

# 연결 테스트
net use \\10.10.100.122\docker

# 드라이브 매핑 (선택)
net use Z: \\10.10.100.122\docker\pokergfx\hands /persistent:yes
```

### 5.2 PokerGFX 설정

| 설정 | 값 |
|------|-----|
| JSON Export Path | `\\10.10.100.122\docker\pokergfx\hands\` |
| Export Format | JSON |
| Auto Export | Enabled |

---

## 6. 파일 감시 로직

### 6.1 파일 락 처리

PokerGFX가 파일 쓰기 중일 때 읽기 시도 시 `WinError 32` 발생. 이를 해결하기 위한 재시도 로직:

```python
async def _wait_for_file_ready(self, path: Path, max_retries: int = 5) -> bool:
    """파일 쓰기 완료 대기 (크기 변화 감지)."""
    delay = self.settings.file_settle_delay  # 기본값: 0.5초

    for attempt in range(max_retries):
        try:
            size1 = path.stat().st_size
            await asyncio.sleep(delay)
            size2 = path.stat().st_size

            if size1 == size2 and size2 > 0:
                return True  # 크기 안정 = 쓰기 완료

            delay = min(delay * 1.5, 5.0)  # 지수 백오프

        except PermissionError:
            await asyncio.sleep(1.0)  # 파일 락
        except OSError:
            await asyncio.sleep(1.0)  # 네트워크 오류

    return False
```

### 6.2 설정 검증

```python
@model_validator(mode="after")
def validate_json_mode_settings(self) -> "PokerGFXSettings":
    if self.mode == "json":
        if not self.json_watch_path:
            raise ValueError(
                "POKERGFX_JSON_PATH must be set when using json mode."
            )
    return self
```

### 6.3 중복 감지

| 방식 | 구현 | 장점 |
|------|------|------|
| 파일명 기반 | `JSONFileWatcher` | 단순, 빠름 |
| 해시 기반 | `SupabaseJSONFileWatcher` | 내용 변경 감지 |

---

## 7. 에러 처리

### 7.1 에러 유형별 처리

| 에러 | 원인 | 처리 |
|------|------|------|
| `WinError 32` | 파일 락 (쓰기 중) | 재시도 (최대 5회) |
| `System error 5` | 접근 거부 | 자격 증명 확인 |
| `System error 53` | 경로 없음 | NAS 연결 확인 |
| `System error 86` | 비밀번호 오류 | 자격 증명 재설정 |
| `TimeoutError` | 네트워크 지연 | 재연결 시도 |

### 7.2 재연결 전략

```
연결 끊김 감지
    ↓
5초 대기 → 재시도 1
    ↓ (실패)
10초 대기 → 재시도 2
    ↓ (실패)
20초 대기 → 재시도 3
    ↓ (실패)
로그 경고 + 수동 개입 필요
```

---

## 8. 모니터링

### 8.1 로그 항목

| 레벨 | 이벤트 | 메시지 예시 |
|------|--------|-------------|
| INFO | 파일 처리 완료 | `Processed session.json: 15 hand results` |
| WARNING | 파일 락 대기 | `File locked, retrying... (3/5)` |
| WARNING | 연결 끊김 | `NAS connection lost, attempting to reconnect...` |
| ERROR | 파일 읽기 실패 | `Could not read file: WinError 32` |

### 8.2 메트릭

| 메트릭 | 설명 | 임계값 |
|--------|------|--------|
| `files_processed_total` | 처리된 파일 수 | - |
| `file_processing_seconds` | 파일 처리 시간 | > 10초 경고 |
| `nas_connection_failures` | 연결 실패 횟수 | > 3회/시간 경고 |
| `file_lock_retries` | 파일 락 재시도 | > 3회/파일 경고 |

---

## 9. 트러블슈팅

### 9.1 체크리스트

#### NAS 측
- [ ] SMB 서비스 활성화
- [ ] 공유 폴더 `docker` 존재
- [ ] 하위 폴더 `pokergfx/hands` 존재
- [ ] 사용자 권한 (읽기/쓰기)
- [ ] 방화벽 445 포트 허용

#### Windows 측
- [ ] 자격 증명 저장됨 (`cmdkey /list`)
- [ ] `net use` 연결 성공
- [ ] 파일 쓰기 테스트 성공

#### Docker 측
- [ ] 볼륨 마운트 설정 확인
- [ ] 컨테이너에서 `/watch` 접근 가능
- [ ] 환경 변수 `POKERGFX_JSON_PATH=/watch`

### 9.2 진단 명령어

```powershell
# Windows - 연결 테스트
net use \\10.10.100.122\docker
dir \\10.10.100.122\docker\pokergfx\hands

# NAS SSH - 폴더 확인
ls -la /volume1/docker/pokergfx/hands

# Docker - 볼륨 확인
docker exec poker-capture ls -la /watch
```

---

## 10. 구현 현황

### 10.1 완료 항목

| 항목 | 파일 | 상태 |
|------|------|------|
| 파일 락 재시도 로직 | `json_file_watcher.py` | ✅ 완료 |
| 설정 검증 | `settings.py` | ✅ 완료 |
| NAS 설정 가이드 | `docs/NAS_SETUP.md` | ✅ 완료 |
| 이슈 추적 가이드 | `docs/ISSUE_UPDATE_GUIDE.md` | ✅ 완료 |

### 10.2 🔴 Blocked 항목

| 항목 | 담당 | 상태 | 비고 |
|------|------|------|------|
| Windows → NAS SMB 연결 | 인프라 | 🔴 Blocked | System error 67 반복 |
| 통합 테스트 | 개발 | ⏳ 대기 | SMB 연결 해결 후 진행 |

### 10.3 시도 이력 (반복 실패 중)

| 날짜 | 시도 | 결과 |
|------|------|------|
| 2026-01-09 | NAS ping | ✅ 성공 |
| 2026-01-09 | SMB 포트 445 | ✅ 열림 |
| 2026-01-09 | NAS SMB 서비스 | ✅ 실행 중 |
| 2026-01-09 | 공유 폴더 설정 | ✅ 존재함 (`docker`) |
| 2026-01-09 | 폴더 구조 | ✅ `/volume1/docker/pokergfx/hands` |
| 2026-01-09 | Windows 자격 증명 | ✅ 저장됨 (GGP) |
| 2026-01-09 | `net use` 연결 | ❌ **error 67** |
| 2026-01-09 | 다른 공유 폴더 | ❌ **error 67** |

### 10.4 에스컬레이션 필요

**추정 원인**:
1. Windows SMB 서명 요구사항 (`RequireSecuritySignature=True`)
2. NAS SMB 프로토콜 버전 제한
3. NAS 방화벽 규칙

**필요 조치**:
- NAS DSM 관리자 권한으로 SMB 고급 설정 확인
- Windows 탐색기에서 `\\10.10.100.122` 직접 접근 테스트
- 네트워크/인프라 담당자 확인

---

## 11. 관련 문서

| 문서 | 설명 |
|------|------|
| [PRD-0002](./PRD-0002-primary-gfx-rfid.md) | Primary Layer - GFX RFID |
| [docs/NAS_SETUP.md](../../docs/NAS_SETUP.md) | NAS SMB 설정 가이드 |
| [docs/ISSUE_UPDATE_GUIDE.md](../../docs/ISSUE_UPDATE_GUIDE.md) | 이슈 업데이트 프로세스 |
| [GitHub Issue #5](https://github.com/garimto81/automation_feature_table/issues/5) | NAS SMB 연동 실패 이슈 |

---

## 12. 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 1.0 | 2026-01-09 | 초안 작성 | Claude |
