# Metabase 모니터링 대시보드 설정 가이드

PRD-0008: 포커 핸드 캡처 시스템 모니터링 대시보드

## 빠른 시작

### 자동 설정 (권장)

```bash
# 1. 환경 변수 설정
export METABASE_ADMIN_PASSWORD="your_admin_password"
export DB_PASSWORD="your_db_password"

# 2. Metabase 시작 (docker-compose에서)
cd deploy
docker-compose --profile analytics up -d

# 3. 자동 설정 스크립트 실행
pip install requests
python metabase/setup_metabase.py --wait
```

### 수동 설정

#### 1. Metabase 시작

```bash
cd deploy
docker-compose --profile analytics up -d
```

#### 2. 초기 설정 (http://localhost:3000)

1. 브라우저에서 `http://localhost:3000` 접속
2. 언어 선택: **한국어**
3. 관리자 계정 생성:
   - 이메일: `admin@poker.local`
   - 비밀번호: (안전한 비밀번호 설정)
4. "나중에 데이터 추가" 클릭

#### 3. PostgreSQL 데이터 소스 연결

1. **설정** (⚙️) > **관리자** > **데이터베이스**
2. **데이터베이스 추가** 클릭
3. 다음 정보 입력:

| 항목 | 값 |
|------|-----|
| 데이터베이스 유형 | PostgreSQL |
| 표시 이름 | Poker Hands DB |
| 호스트 | db (Docker 내부) 또는 localhost (외부) |
| 포트 | 5432 (Docker 내부) 또는 6432 (외부) |
| 데이터베이스 이름 | poker_hands |
| 사용자 이름 | poker |
| 비밀번호 | (DB_PASSWORD) |

4. **저장** 클릭 > 스키마 동기화 대기

#### 4. 대시보드 생성

1. **새로 만들기** (+) > **대시보드**
2. 이름: `Poker Monitoring Dashboard`
3. 4개 패널 추가:

**패널 1: 테이블 상태 (좌상단)**
- **새로 만들기** > **SQL 쿼리**
- `dashboard-queries.sql` 의 1.1 쿼리 붙여넣기
- 시각화: 테이블

**패널 2: 핸드 등급 분포 (우상단)**
- `dashboard-queries.sql` 의 2.1 쿼리
- 시각화: 파이 차트

**패널 3: 녹화 세션 (좌하단)**
- `dashboard-queries.sql` 의 5.1 쿼리
- 시각화: 테이블

**패널 4: 시스템 헬스 (우하단)**
- `dashboard-queries.sql` 의 6.1 쿼리
- 시각화: 테이블

#### 5. Auto-refresh 설정

1. 대시보드 우측 상단 **⋯** > **자동 새로고침**
2. **5초** 선택

## 대시보드 레이아웃

```
┌────────────────────┬────────────────────┐
│                    │                    │
│   테이블 상태      │   핸드 등급 분포   │
│   (Table)          │   (Pie Chart)      │
│                    │                    │
├────────────────────┼────────────────────┤
│                    │                    │
│   녹화 세션        │   시스템 헬스      │
│   (Table)          │   (Table)          │
│                    │                    │
└────────────────────┴────────────────────┘
```

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `METABASE_HOST` | Metabase URL | http://localhost:3000 |
| `METABASE_ADMIN_EMAIL` | 관리자 이메일 | admin@poker.local |
| `METABASE_ADMIN_PASSWORD` | 관리자 비밀번호 | (필수) |
| `DB_HOST` | PostgreSQL 호스트 | db |
| `DB_PORT` | PostgreSQL 포트 | 5432 |
| `DB_NAME` | 데이터베이스 이름 | poker_hands |
| `DB_USER` | 데이터베이스 사용자 | poker |
| `DB_PASSWORD` | 데이터베이스 비밀번호 | (필수) |

## 모바일 반응형

Metabase는 기본적으로 반응형 레이아웃을 지원합니다:

- **데스크톱**: 2x2 그리드
- **태블릿**: 1x4 세로 스택
- **모바일**: 1x4 세로 스택 (스크롤)

대시보드 설정에서 **모바일 최적화** 옵션을 활성화하면 더 나은 모바일 경험을 제공합니다.

## 문제 해결

### Metabase가 시작되지 않음

```bash
# 로그 확인
docker logs poker-metabase

# 메모리 확인 (최소 1GB 필요)
docker stats poker-metabase
```

### 데이터베이스 연결 실패

1. Docker 네트워크 확인:
   ```bash
   docker network inspect deploy_poker-network
   ```

2. PostgreSQL 접속 테스트:
   ```bash
   docker exec -it poker-db psql -U poker -d poker_hands -c "SELECT 1"
   ```

### 데이터가 표시되지 않음

1. 스키마 동기화:
   - **관리자** > **데이터베이스** > **Poker Hands DB** > **스키마 동기화**

2. 테이블 존재 확인:
   ```bash
   docker exec -it poker-db psql -U poker -d poker_hands -c "\dt"
   ```

## 파일 구조

```
deploy/metabase/
├── README.md                      # 이 문서
├── setup_metabase.py              # 자동 설정 스크립트
├── dashboard-queries.sql          # SQL 쿼리 정의
└── migrations/
    └── 001_monitoring_tables.sql  # DB 마이그레이션
```

## 관련 문서

- [PRD-0008: 모니터링 대시보드](../../tasks/prds/PRD-0008-monitoring-dashboard.md)
- [체크리스트](../../docs/checklists/PRD-0008.md)
