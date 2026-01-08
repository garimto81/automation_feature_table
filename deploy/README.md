# Synology NAS 배포 가이드

포커 핸드 자동 캡처 시스템을 Synology NAS에 Docker로 배포하는 가이드입니다.

## 시스템 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| DSM 버전 | 7.2 이상 | 7.2.1 이상 |
| RAM | 4GB | 8GB |
| CPU | x86_64 또는 ARM64 | Intel Celeron J4125+ |
| 패키지 | Container Manager | Container Manager |
| 저장공간 | 2GB | 10GB |

### 지원 모델

| 아키텍처 | 모델 예시 |
|----------|----------|
| x86_64 (Intel/AMD) | DS920+, DS720+, DS220+ |
| ARM64 | DS220j, DS223, DS124 |

---

## 빠른 시작 (원클릭 배포)

### Windows에서 배포

```powershell
# PowerShell에서 실행
cd deploy
.\deploy-to-nas.ps1 -NasHost 10.10.100.122 -DbPassword "your_password"

# pgAdmin 포함
.\deploy-to-nas.ps1 -NasHost 10.10.100.122 -DbPassword "your_password" -WithPgAdmin
```

### NAS에서 직접 설치

```bash
# 1. 배포 패키지를 NAS로 복사 (USB, File Station, SCP 등)
# 2. SSH로 NAS 접속
ssh admin@NAS_IP

# 3. 설치 스크립트 실행
cd /volume1/docker/poker-capture
chmod +x install.sh
./install.sh
```

---

## 수동 배포

### Step 1: Container Manager 설치

1. Synology DSM 로그인
2. **패키지 센터** 열기
3. "Container Manager" 검색 후 설치

### Step 2: 폴더 구조 생성

SSH 또는 File Station에서 다음 폴더를 생성합니다:

```bash
mkdir -p /volume1/docker/poker-capture/app
mkdir -p /volume1/docker/poker-capture/data
mkdir -p /volume1/docker/postgresql/data
mkdir -p /volume1/docker/pokergfx/hands
```

### Step 3: 파일 복사

로컬에서 NAS로 파일을 복사합니다:

```bash
# 애플리케이션 코드
scp -r src/ admin@NAS_IP:/volume1/docker/poker-capture/app/

# 배포 파일
scp deploy/Dockerfile admin@NAS_IP:/volume1/docker/poker-capture/app/
scp deploy/requirements.txt admin@NAS_IP:/volume1/docker/poker-capture/app/
scp deploy/docker-compose.yml admin@NAS_IP:/volume1/docker/poker-capture/
```

### Step 4: 환경 변수 설정

```bash
ssh admin@NAS_IP
cd /volume1/docker/poker-capture

# .env 파일 생성
cat > .env << 'EOF'
DB_PASSWORD=your_secure_password
PGADMIN_PASSWORD=your_admin_password
LOG_LEVEL=INFO
VMIX_AUTO_RECORD=false
EOF

chmod 600 .env
```

### Step 5: Docker 빌드 및 실행

```bash
cd /volume1/docker/poker-capture
docker-compose up -d --build
```

### Step 6: 상태 확인

```bash
# 컨테이너 상태
docker-compose ps

# 로그 확인
docker-compose logs -f poker-capture

# 데이터베이스 연결 확인
docker exec poker-db psql -U poker -d poker_hands -c "SELECT 1"
```

## PokerGFX 연결

PokerGFX 소프트웨어에서 JSON 출력 경로를 설정합니다:

- **네트워크 경로**: `\\NAS_IP\docker\pokergfx\hands\`
- **매핑 드라이브**: `Z:\pokergfx\hands\` (Windows에서 매핑 시)

## 운영 명령어

### 서비스 관리

```bash
# 시작
docker-compose up -d

# 중지
docker-compose down

# 재시작
docker-compose restart poker-capture

# 로그 확인
docker-compose logs -f poker-capture
```

### 데이터베이스 관리

```bash
# 백업
docker exec poker-db pg_dump -U poker poker_hands > backup_$(date +%Y%m%d).sql

# 복원
docker exec -i poker-db psql -U poker poker_hands < backup_20250106.sql

# 직접 쿼리
docker exec -it poker-db psql -U poker poker_hands
```

### pgAdmin 접속 (선택)

pgAdmin을 사용하려면:

```bash
docker-compose --profile admin up -d
```

웹 브라우저에서 `http://NAS_IP:5050` 접속

### 처리 파일 초기화

재처리가 필요한 경우:

```bash
rm /volume1/docker/poker-capture/data/processed_files.json
docker-compose restart poker-capture
```

## 트러블슈팅

### 컨테이너가 시작되지 않음

```bash
# 상세 로그 확인
docker-compose logs poker-capture

# 이미지 재빌드
docker-compose build --no-cache poker-capture
```

### 데이터베이스 연결 실패

```bash
# DB 컨테이너 상태 확인
docker exec poker-db pg_isready -U poker

# 네트워크 확인
docker network ls
docker network inspect poker-capture_poker-network
```

### JSON 파일이 처리되지 않음

1. 파일 권한 확인:
   ```bash
   ls -la /volume1/docker/pokergfx/hands/
   ```

2. 처리된 파일 목록 확인:
   ```bash
   cat /volume1/docker/poker-capture/data/processed_files.json
   ```

3. 컨테이너 내부에서 확인:
   ```bash
   docker exec poker-capture ls -la /watch/
   ```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Synology NAS (DSM 7.2)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PokerGFX PC ──SMB──▶ /volume1/docker/pokergfx/hands/       │
│                              │                              │
│                              ▼                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Docker: poker-capture                                 │ │
│  │  - JSON 파일 감시 (PollingObserver)                    │ │
│  │  - 핸드 분류 (phevaluator)                            │ │
│  │  - A/B/C 등급 부여                                    │ │
│  └───────────────────────────────────────────────────────┘ │
│                              │                              │
│                              ▼                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Docker: poker-db (PostgreSQL 16)                      │ │
│  │  - 핸드 데이터 저장                                   │ │
│  │  - 등급별 조회                                        │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
