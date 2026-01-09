# NAS SMB 설정 가이드

PokerGFX → NAS → Docker 컨테이너 연동을 위한 설정 가이드.

## 아키텍처 개요

```
[Windows PC]                         [Synology NAS]
PokerGFX  ─── SMB/CIFS ───>  \\NAS_IP\docker\pokergfx\hands\
                              ↓ (NAS 로컬 경로)
                         /volume1/docker/pokergfx/hands
                              ↓ (Docker 볼륨 마운트)
[Docker Container]  ←────  /watch:ro (읽기 전용)
poker-capture
```

---

## 1. Synology NAS 설정

### 1.1 SMB 서비스 활성화

1. **DSM 접속** → 제어판 → 파일 서비스 → SMB
2. **SMB 서비스 활성화** 체크
3. **최대 SMB 프로토콜**: SMB3 권장
4. **최소 SMB 프로토콜**: SMB2 (Windows 7 이상 호환)
5. **적용** 클릭

### 1.2 공유 폴더 생성/확인

#### 기존 폴더 사용 시

1. 제어판 → 공유 폴더
2. `docker` 폴더 선택 → 편집
3. **권한** 탭 → 사용자에게 읽기/쓰기 권한 부여

#### 새 폴더 생성 시

1. 제어판 → 공유 폴더 → 생성
2. 이름: `docker`
3. 위치: Volume 1 (또는 원하는 볼륨)
4. 휴지통 활성화: 선택 사항
5. **다음** → 권한 설정

### 1.3 하위 폴더 생성

SSH 또는 File Station에서:

```bash
# SSH 접속
ssh admin@10.10.100.122

# 폴더 생성
sudo mkdir -p /volume1/docker/pokergfx/hands

# 권한 설정 (Docker 컨테이너에서 읽기 가능)
sudo chmod 755 /volume1/docker/pokergfx/hands

# 소유자 설정 (선택)
sudo chown -R admin:users /volume1/docker/pokergfx
```

### 1.4 방화벽 확인

1. 제어판 → 보안 → 방화벽
2. SMB 포트 허용 확인: **445/TCP**
3. 내부 네트워크 대역 허용 (예: 10.10.100.0/24)

---

## 2. Windows 설정

### 2.1 자격 증명 저장

**방법 1: 명령 프롬프트 (권장)**

```powershell
# 관리자 권한으로 실행

# 1. 기존 자격 증명 삭제 (있으면)
cmdkey /delete:10.10.100.122

# 2. 새 자격 증명 저장
cmdkey /add:10.10.100.122 /user:NAS사용자명 /pass:비밀번호

# 3. 저장된 자격 증명 확인
cmdkey /list
```

**방법 2: 자격 증명 관리자 GUI**

1. 제어판 → 사용자 계정 → 자격 증명 관리자
2. Windows 자격 증명 → 자격 증명 추가
3. 네트워크 주소: `10.10.100.122`
4. 사용자 이름: NAS 사용자
5. 비밀번호: NAS 비밀번호

### 2.2 연결 테스트

```powershell
# 네트워크 연결 테스트
net use \\10.10.100.122\docker

# 폴더 내용 확인
dir \\10.10.100.122\docker\pokergfx\hands

# 파일 쓰기 테스트
echo test > \\10.10.100.122\docker\pokergfx\hands\test.txt
del \\10.10.100.122\docker\pokergfx\hands\test.txt
```

### 2.3 드라이브 매핑 (선택)

```powershell
# 영구 드라이브 매핑
net use Z: \\10.10.100.122\docker\pokergfx\hands /persistent:yes

# 매핑 해제
net use Z: /delete
```

---

## 3. PokerGFX 설정

### JSON 출력 경로 설정

PokerGFX 설정에서 JSON 출력 경로를 다음 중 하나로 설정:

```
\\10.10.100.122\docker\pokergfx\hands\
또는
Z:\  (드라이브 매핑 사용 시)
```

---

## 4. Docker Compose 설정

`deploy/docker-compose.yml`의 볼륨 마운트 설정:

```yaml
services:
  poker-capture:
    volumes:
      # NAS 로컬 경로 → 컨테이너 /watch (읽기 전용)
      - /volume1/docker/pokergfx/hands:/watch:ro
    environment:
      - POKERGFX_JSON_PATH=/watch
      - POKERGFX_POLLING_INTERVAL=2.0
```

---

## 5. 트러블슈팅

### 문제: "네트워크 경로를 찾을 수 없습니다"

```
System error 53 has occurred.
The network path was not found.
```

**해결**:
1. NAS IP 확인: `ping 10.10.100.122`
2. SMB 서비스 활성화 확인
3. 방화벽 445 포트 확인

### 문제: "액세스가 거부되었습니다"

```
System error 5 has occurred.
Access is denied.
```

**해결**:
1. 자격 증명 삭제 후 재등록
2. NAS 공유 폴더 권한 확인
3. 사용자 계정 잠금 상태 확인

### 문제: "지정한 네트워크 암호가 맞지 않습니다"

```
System error 86 has occurred.
The specified network password is not correct.
```

**해결**:
1. NAS 사용자 비밀번호 확인
2. 특수문자가 있으면 따옴표로 감싸기:
   ```powershell
   cmdkey /add:10.10.100.122 /user:admin /pass:"P@ss!word"
   ```

### 문제: "SMB 프로토콜 버전 불일치"

**해결**:
1. NAS DSM에서 최소 SMB 버전을 SMB1로 낮춤 (보안 주의)
2. 또는 Windows에서 SMB1 클라이언트 활성화:
   ```powershell
   Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol-Client
   ```

### 문제: Docker 컨테이너에서 파일이 안 보임

**해결**:
1. NAS SSH 접속 후 확인:
   ```bash
   ls -la /volume1/docker/pokergfx/hands
   ```
2. Docker 볼륨 마운트 확인:
   ```bash
   docker exec poker-capture ls -la /watch
   ```
3. 컨테이너 재시작:
   ```bash
   docker-compose restart poker-capture
   ```

---

## 6. 검증 체크리스트

### NAS 측
- [ ] SMB 서비스 활성화
- [ ] 공유 폴더 존재 (`docker`)
- [ ] 하위 폴더 존재 (`pokergfx/hands`)
- [ ] 사용자 권한 부여 (읽기/쓰기)
- [ ] 방화벽 445 포트 허용

### Windows 측
- [ ] 자격 증명 저장됨
- [ ] `net use` 연결 성공
- [ ] 파일 쓰기 테스트 성공

### Docker 측
- [ ] 볼륨 마운트 설정 확인
- [ ] 컨테이너에서 `/watch` 접근 가능
- [ ] 파일 변경 감지 확인

### PokerGFX 측
- [ ] JSON 출력 경로 설정
- [ ] 테스트 핸드 → JSON 파일 생성 확인

---

## 참고 링크

- [Synology SMB 설정 가이드](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_winmacnfs_win)
- [Windows SMB 트러블슈팅](https://docs.microsoft.com/en-us/windows-server/storage/file-server/troubleshoot/troubleshoot-smb)
- [Docker 볼륨 마운트](https://docs.docker.com/storage/volumes/)
