# PRD-0008: 모니터링 대시보드 구현

| 항목 | 값 |
|------|---|
| **Version** | 1.0 |
| **Status** | Draft |
| **Priority** | P1 |
| **Created** | 2026-01-07 |
| **Author** | Claude Code |

---

## 1. 개요

### 1.1 배경

PokerGFX 기반 멀티테이블 포커 핸드 자동 캡처 시스템의 **실시간 모니터링**이 필요합니다. 현재 시스템은 Primary(PokerGFX RFID), Secondary(Gemini AI), FusionEngine, 녹화(vMix) 등 여러 컴포넌트로 구성되어 있으며, 운영팀과 편집팀이 통합된 뷰에서 시스템 상태를 확인할 수 있어야 합니다.

### 1.2 목표

- **운영팀**: 실시간 방송 중 테이블 상태, 핸드 진행 현황 모니터링
- **편집팀**: 핸드 등급(A/B/C) 분포, 녹화 세션 상태 확인
- **통합 뷰**: 양 팀이 동일한 대시보드에서 필요 정보 확인

### 1.3 성공 지표

| 지표 | 목표 |
|------|------|
| 데이터 갱신 지연 | < 1초 (WebSocket) |
| 대시보드 가동률 | 99.5% |
| 사용자 만족도 | 4.0/5.0 이상 |

---

## 2. 대상 사용자

### 2.1 Primary Users

| 사용자 | 역할 | 핵심 니즈 |
|--------|------|----------|
| 방송 운영팀 | 실시간 모니터링 | 테이블 상태, 장애 알림 |
| 편집팀 | 핸드 소스 확인 | 등급 분포, 녹화 현황 |

### 2.2 Secondary Users

| 사용자 | 역할 | 핵심 니즈 |
|--------|------|----------|
| 시스템 관리자 | 인프라 관리 | 시스템 헬스, 에러 로그 |

---

## 3. 핵심 기능

### 3.1 테이블 상태 모니터링

```
┌─────────────────────────────────────────────────────────────┐
│ 테이블 상태                                    [실시간 ●]   │
├─────────────────────────────────────────────────────────────┤
│  Table A          Table B          Table C                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Primary  │    │ Primary  │    │ Primary  │              │
│  │   ● ON   │    │   ● ON   │    │   ○ OFF  │              │
│  ├──────────┤    ├──────────┤    ├──────────┤              │
│  │Secondary │    │Secondary │    │Secondary │              │
│  │   ● ON   │    │   ○ OFF  │    │   ● ON   │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│                                                             │
│  현재 핸드: #142   현재 핸드: #98    현재 핸드: #56        │
│  진행 시간: 2:34   진행 시간: 1:12   진행 시간: 0:45       │
└─────────────────────────────────────────────────────────────┘
```

**표시 항목**:
- Primary (PokerGFX RFID) 연결 상태
- Secondary (Gemini AI) 연결 상태
- 현재 핸드 번호
- 핸드 진행 시간
- Fusion 결과 (validated / requires_review)

### 3.2 핸드 등급 현황

```
┌─────────────────────────────────────────────────────────────┐
│ 핸드 등급 분포                              [오늘 / 전체]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   A등급    ████████████░░░░░░░░░░░░░░░░  23개 (15%)         │
│   B등급    ████████████████████░░░░░░░░  45개 (30%)         │
│   C등급    ████████████████████████████  82개 (55%)         │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 최근 A등급 핸드                                     │  │
│   │ #142 Table A - Royal Flush - 3:24                   │  │
│   │ #138 Table B - Straight Flush - 2:45                │  │
│   │ #125 Table A - Four of a Kind - 4:12                │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                             │
│   방송 적합: A+B = 68개 (45%)                              │
└─────────────────────────────────────────────────────────────┘
```

**표시 항목**:
- 등급별 핸드 수 및 비율
- 최근 A등급 핸드 목록
- 방송 적합 핸드 수 (B등급 이상)
- 시간대별 등급 트렌드 차트

### 3.3 녹화 세션 관리

```
┌─────────────────────────────────────────────────────────────┐
│ 녹화 세션                                      [vMix 연결]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   진행 중 세션: 3                                           │
│   ┌────────────────────────────────────────────────────┐   │
│   │ Session #12 │ Table A │ ● REC │ 00:12:34 │ 2.3GB  │   │
│   │ Session #13 │ Table B │ ● REC │ 00:08:21 │ 1.8GB  │   │
│   │ Session #14 │ Table C │ ● REC │ 00:03:45 │ 0.8GB  │   │
│   └────────────────────────────────────────────────────┘   │
│                                                             │
│   오늘 완료: 24 세션 │ 총 용량: 45.2GB                      │
│                                                             │
│   [세션 시작] [세션 종료] [전체 목록]                       │
└─────────────────────────────────────────────────────────────┘
```

**표시 항목**:
- 진행 중 녹화 세션 목록
- 세션별 녹화 시간, 파일 크기
- 오늘 완료된 세션 수
- 총 저장 용량

### 3.4 시스템 헬스

```
┌─────────────────────────────────────────────────────────────┐
│ 시스템 상태                                  [마지막 체크]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   PostgreSQL     ● Connected    Latency: 12ms              │
│   PokerGFX API   ● Connected    Latency: 45ms              │
│   Gemini API     ● Connected    Quota: 85% remaining       │
│   vMix           ● Connected    Status: Recording          │
│   Redis Cache    ● Connected    Memory: 128MB/512MB        │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 최근 에러 로그                                      │  │
│   │ [WARN] 10:23:45 - Gemini API rate limit warning     │  │
│   │ [INFO] 10:20:12 - Table C Primary reconnected       │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**표시 항목**:
- 주요 서비스 연결 상태
- API 응답 지연 시간
- Gemini API 쿼터 잔량
- 최근 에러/경고 로그

---

## 4. 기술 스택

### 4.1 선택: Metabase

| 항목 | 내용 |
|------|------|
| **선택 이유** | 배포 패키지에 이미 포함 (docker-compose) |
| **데이터 소스** | PostgreSQL (직접 연결) |
| **실시간** | Metabase Native + WebSocket 프록시 |
| **배포** | 기존 Synology NAS Docker 환경 활용 |

### 4.2 아키텍처

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Browser    │────▶│   Metabase   │────▶│  PostgreSQL  │
│  (Dashboard) │     │   (Docker)   │     │   (Docker)   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                                          ▲
       │ WebSocket                                │
       ▼                                          │
┌──────────────┐                         ┌──────────────┐
│   FastAPI    │─────────────────────────│   System     │
│ (WebSocket)  │                         │   (Main.py)  │
└──────────────┘                         └──────────────┘
```

### 4.3 실시간 업데이트 구현

**방안 1: Metabase Auto-refresh + FastAPI WebSocket**

```python
# src/dashboard/websocket_server.py
from fastapi import FastAPI, WebSocket
from typing import Dict, Set

app = FastAPI()
connections: Set[WebSocket] = set()

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    await websocket.accept()
    connections.add(websocket)
    try:
        while True:
            # 1초마다 상태 브로드캐스트
            status = await get_system_status()
            await websocket.send_json(status)
            await asyncio.sleep(1)
    finally:
        connections.remove(websocket)
```

**방안 2: Metabase Questions + 자동 갱신**

- Metabase Dashboard의 Auto-refresh 기능 (5초 간격)
- 실시간 알림은 별도 WebSocket 서버로 처리

---

## 5. 데이터베이스 스키마 확장

### 5.1 시스템 상태 테이블

```sql
-- 테이블 상태 (실시간)
CREATE TABLE table_status (
    id SERIAL PRIMARY KEY,
    table_id VARCHAR(50) NOT NULL,
    primary_connected BOOLEAN DEFAULT FALSE,
    secondary_connected BOOLEAN DEFAULT FALSE,
    current_hand_id INTEGER,
    hand_start_time TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 시스템 헬스 로그
CREATE TABLE system_health_log (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'connected', 'disconnected', 'error'
    latency_ms INTEGER,
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 녹화 세션
CREATE TABLE recording_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    table_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'recording', 'stopped', 'completed'
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    file_size_mb DECIMAL(10, 2),
    file_path TEXT
);
```

### 5.2 Metabase Questions 정의

| Question | SQL | 용도 |
|----------|-----|------|
| 테이블 상태 | `SELECT * FROM table_status` | 테이블별 연결 상태 |
| 등급 분포 | `SELECT grade, COUNT(*) FROM hands GROUP BY grade` | 파이 차트 |
| 시간대별 핸드 | `SELECT DATE_TRUNC('hour', ...) ...` | 트렌드 차트 |
| 최근 A등급 | `SELECT * FROM hands WHERE grade='A' ORDER BY ...` | 테이블 |

---

## 6. 구현 계획

### Phase 1: 기본 대시보드 (MVP)

| 태스크 | 예상 작업량 |
|--------|-----------|
| DB 스키마 확장 | 스키마 설계 + 마이그레이션 |
| Metabase 설정 | Docker 구성 + 초기 설정 |
| 기본 Questions 생성 | 4개 핵심 쿼리 |
| Dashboard 레이아웃 | 4개 패널 배치 |

### Phase 2: 실시간 기능

| 태스크 | 예상 작업량 |
|--------|-----------|
| WebSocket 서버 구현 | FastAPI 엔드포인트 |
| 상태 브로드캐스트 | 1초 주기 업데이트 |
| 알림 시스템 | 장애 발생 시 알림 |

### Phase 3: 고급 기능

| 태스크 | 예상 작업량 |
|--------|-----------|
| 커스텀 시각화 | React 임베드 차트 |
| 리포트 내보내기 | PDF/CSV 생성 |
| 사용자 권한 | 팀별 뷰 분리 |

---

## 7. 제약 사항

### 7.1 기술적 제약

| 제약 | 대응 |
|------|------|
| Metabase 무료 버전 제한 | 오픈소스 버전 사용 |
| WebSocket 연결 수 제한 | 최대 50 동시 연결 |
| DB 쿼리 부하 | 인덱스 최적화, 캐싱 |

### 7.2 운영 제약

| 제약 | 대응 |
|------|------|
| Synology NAS 리소스 | CPU/메모리 모니터링 |
| 네트워크 대역폭 | 압축 전송 |

---

## 8. 관련 문서

| 문서 | 링크 |
|------|------|
| PRD-0001 | 포커 핸드 자동 캡처 시스템 (메인) |
| PRD-0005 | 통합 DB/자막 시스템 |
| 배포 가이드 | `deploy/README.md` |

---

## Appendix A: Metabase Dashboard JSON

배포 시 자동 적용되는 대시보드 설정:

```json
{
  "name": "Poker Hand Monitoring",
  "cards": [
    {"name": "Table Status", "visualization": "table"},
    {"name": "Grade Distribution", "visualization": "pie"},
    {"name": "Recording Sessions", "visualization": "table"},
    {"name": "System Health", "visualization": "scalar"}
  ]
}
```
