# PRD-0007: 자체 RFID 클라이언트 개발

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0007 |
| **제목** | 자체 RFID 클라이언트 개발 |
| **버전** | 1.0 |
| **작성일** | 2025-12-25 |
| **상태** | Draft |
| **Phase** | 2-3 (향후 계획) |
| **우선순위** | P2 |

---

## 1. 개요 (Overview)

PokerGFX 라이선스 의존성을 제거하고, 자체 RFID 리더 연동 클라이언트를 개발하여 연간 $39,000 비용 절감.

---

## 2. 배경 (Background)

### 현재 상황
```
PokerGFX 라이선스: $13,000/년 × 3개 테이블 = $39,000/년
```

### 아키텍처 전환
```
Phase 1 (현재)                    Phase 2-3 (향후)
┌─────────────────┐              ┌─────────────────┐
│ PokerGFX RFID   │      →       │ 자체 RFID 모델   │
│ (라이선스 의존)  │              │ (자체 개발)      │
└────────┬────────┘              └────────┬────────┘
         │                                │
         ▼                                ▼
┌─────────────────┐              ┌─────────────────┐
│  FusionEngine   │              │  FusionEngine   │
│ (변경 없음)      │              │ (변경 없음)      │
└─────────────────┘              └─────────────────┘
```

---

## 3. 목표 (Goals)

### 비즈니스 목표
- [ ] 연간 라이선스 비용 $39,000 절감
- [ ] 테이블 확장 시 추가 비용 제거
- [ ] 벤더 종속성 탈피

### 기술 목표
- [ ] 기존 `PokerGFXClient` 인터페이스 100% 호환
- [ ] `FusionEngine` 무수정 전환
- [ ] RFID 리더 직접 제어
- [ ] 실시간 WebSocket 스트리밍

---

## 4. 사용자 스토리 (User Stories)

### Story 1: 운영자
**As a** 방송 운영자
**I want to** PokerGFX 없이도 RFID 카드 데이터를 수신
**So that** 라이선스 비용 없이 시스템 운영 가능

**수락 기준**:
- [ ] RFID 리더에서 카드 인식 시 0.5초 이내 데이터 수신
- [ ] 기존 FusionEngine과 동일하게 연동
- [ ] 3개 테이블 동시 처리

### Story 2: 개발자
**As a** 시스템 개발자
**I want to** 기존 코드 최소 수정으로 RFID 클라이언트 교체
**So that** 안정적인 무중단 전환 가능

**수락 기준**:
- [ ] `PokerGFXClient` 인터페이스 동일
- [ ] 설정 변경만으로 클라이언트 교체
- [ ] 기존 테스트 코드 통과

---

## 5. 기능 요구사항 (Functional Requirements)

### 5.1 필수 기능

| ID | 기능 | 설명 | 우선순위 |
|----|------|------|:--------:|
| F-001 | RFID 리더 연결 | 하드웨어 리더와 통신 (Serial/USB) | High |
| F-002 | 카드 인식 | 52장 카드 RFID 태그 인식 | High |
| F-003 | 핸드 이벤트 생성 | `hand_start`, `hand_deal`, `hand_complete` | High |
| F-004 | WebSocket 서버 | 내부 데이터 브로드캐스트 | High |
| F-005 | 멀티테이블 지원 | 3개 이상 동시 처리 | High |
| F-006 | 자동 재연결 | 리더 연결 끊김 시 복구 | High |

### 5.2 인터페이스 호환성 (기존 코드 분석)

```python
# 기존 PokerGFXClient 인터페이스 - 100% 호환 필수
class RFIDClient:
    """자체 RFID 클라이언트 - PokerGFXClient 대체"""

    async def connect(self) -> None:
        """RFID 리더 연결"""

    async def disconnect(self) -> None:
        """연결 해제"""

    def add_handler(self, handler: Callable[[HandResult], None]) -> None:
        """핸드 결과 핸들러 등록"""

    async def listen(self) -> AsyncIterator[HandResult]:
        """핸드 이벤트 스트림"""

    async def get_hand_history(
        self, table_id: str, limit: int = 100
    ) -> list[HandResult]:
        """핸드 히스토리 조회"""
```

### 5.3 데이터 모델 (기존 호환)

```python
# 기존 HandResult 그대로 사용
@dataclass
class HandResult:
    table_id: str
    hand_number: int
    hand_rank: HandRank
    rank_value: int
    is_premium: bool
    confidence: float  # RFID = 1.0
    players_showdown: list[dict]
    pot_size: int
    timestamp: datetime
    community_cards: list[Card]
    winner: Optional[str]
```

### 5.4 선택 기능

| ID | 기능 | 설명 | 우선순위 |
|----|------|------|:--------:|
| F-101 | 웹 대시보드 | 리더 상태 모니터링 UI | Medium |
| F-102 | 로그 저장 | 모든 이벤트 파일 저장 | Medium |
| F-103 | 칩 추적 | RFID 칩 인식 (향후) | Low |

---

## 6. 시스템 아키텍처

### 6.1 컴포넌트 구조

```
┌─────────────────────────────────────────────────────────┐
│                    RFID Hardware Layer                   │
├─────────────┬─────────────┬─────────────┬───────────────┤
│  Reader A   │  Reader B   │  Reader C   │  ...N         │
│  (Table 1)  │  (Table 2)  │  (Table 3)  │               │
└──────┬──────┴──────┬──────┴──────┬──────┴───────────────┘
       │             │             │
       ▼             ▼             ▼
┌─────────────────────────────────────────────────────────┐
│                  RFIDReaderManager                       │
│  - Serial/USB 통신                                       │
│  - 카드 태그 → Card 객체 변환                             │
│  - 멀티 리더 관리                                         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   HandEventProcessor                     │
│  - 카드 위치 추적 (시트별 홀카드, 커뮤니티)                 │
│  - 핸드 시작/종료 감지                                    │
│  - HandResult 생성                                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                     RFIDClient                           │
│  - PokerGFXClient 인터페이스 구현                         │
│  - WebSocket 브로드캐스트                                 │
│  - FusionEngine 연동                                     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    FusionEngine                          │
│  (기존 코드 - 수정 없음)                                   │
└─────────────────────────────────────────────────────────┘
```

### 6.2 파일 구조

```
src/primary/
├── pokergfx_client.py      # 기존 (Phase 1에서 유지)
├── rfid_client.py          # 신규: 자체 RFID 클라이언트
├── rfid_reader.py          # 신규: 하드웨어 리더 통신
├── hand_event_processor.py # 신규: 핸드 이벤트 처리
├── hand_classifier.py      # 기존 (재사용)
└── __init__.py             # 클라이언트 선택 팩토리
```

### 6.3 클라이언트 팩토리

```python
# src/primary/__init__.py
from src.config.settings import Settings

def create_primary_client(settings: Settings):
    """설정에 따라 Primary 클라이언트 생성"""
    if settings.primary_source == "pokergfx":
        from src.primary.pokergfx_client import PokerGFXClient
        return PokerGFXClient(settings.pokergfx)
    elif settings.primary_source == "rfid":
        from src.primary.rfid_client import RFIDClient
        return RFIDClient(settings.rfid)
    else:
        raise ValueError(f"Unknown primary source: {settings.primary_source}")
```

---

## 7. RFID 하드웨어 사양

### 7.1 지원 리더

| 리더 | 인터페이스 | 프로토콜 | 비고 |
|------|-----------|----------|------|
| ACR122U | USB | PC/SC | 테스트용 |
| 포커 전용 리더 | Serial | Custom | 제조사 문의 |

### 7.2 카드 태그 매핑

```python
# 52장 카드 RFID UID → Card 매핑 테이블
CARD_MAPPING = {
    "04:A1:B2:C3:D4:E5:F6": Card("A", "h"),  # Ace of Hearts
    "04:A1:B2:C3:D4:E5:F7": Card("K", "h"),  # King of Hearts
    # ... 52장 전체 매핑
}
```

### 7.3 시트 위치 매핑

```
┌─────────────────────────────────────┐
│            커뮤니티 카드              │
│         [F] [T] [R] [4] [5]          │
├─────────────────────────────────────┤
│  S1   S2   S3   S4   S5   S6   S7   │
│  [□□] [□□] [□□] [□□] [□□] [□□] [□□]  │
└─────────────────────────────────────┘

시트 1~10: 플레이어 홀카드 (각 2장)
F, T, R, 4, 5: 커뮤니티 카드 (Flop 3장, Turn 1장, River 1장)
```

---

## 8. 비기능 요구사항 (Non-Functional Requirements)

| 항목 | 요구사항 |
|------|----------|
| **지연시간** | 카드 인식 → 이벤트 전송 < 500ms |
| **동시성** | 3개 테이블 동시 처리 |
| **안정성** | 24시간 무중단 운영 |
| **복구** | 리더 재연결 < 5초 |
| **정확도** | RFID 인식 정확도 100% (confidence = 1.0) |

---

## 9. 구현 계획

### Phase 2-1: 프로토타입 (단일 테이블)
- [ ] RFID 리더 통신 모듈 개발
- [ ] 카드 태그 매핑 테이블 구성
- [ ] 단일 테이블 핸드 이벤트 처리
- [ ] RFIDClient 인터페이스 구현
- [ ] 단위 테스트

### Phase 2-2: 통합 (멀티테이블)
- [ ] RFIDReaderManager 멀티 리더 지원
- [ ] 클라이언트 팩토리 구현
- [ ] FusionEngine 통합 테스트
- [ ] A/B 테스트 (PokerGFX vs 자체)

### Phase 3: 전환
- [ ] 운영 환경 배포
- [ ] PokerGFX 라이선스 종료
- [ ] 모니터링 대시보드 구축

---

## 10. 테스트 계획

### 10.1 단위 테스트

```python
# tests/test_rfid_client.py
class TestRFIDClient:
    async def test_connect(self):
        """리더 연결 테스트"""

    async def test_card_recognition(self):
        """카드 인식 테스트"""

    async def test_hand_event_generation(self):
        """핸드 이벤트 생성 테스트"""

    async def test_interface_compatibility(self):
        """PokerGFXClient 인터페이스 호환성 테스트"""
```

### 10.2 통합 테스트

| 테스트 | 설명 | 기준 |
|--------|------|------|
| FusionEngine 연동 | RFIDClient → FusionEngine | 기존 테스트 통과 |
| 멀티테이블 | 3개 테이블 동시 | 모든 이벤트 처리 |
| 장시간 운영 | 24시간 연속 | 오류 없음 |

---

## 11. 범위 제외 (Out of Scope)

- 칩 RFID 추적 (Phase 3 이후 검토)
- 3D 그래픽 오버레이 (기존 output 모듈 사용)
- 모바일 앱 연동

---

## 12. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| RFID 리더 호환성 | High | 테스트용 리더로 사전 검증 |
| 카드 태그 오인식 | High | 듀얼 리더로 교차 검증 |
| 개발 지연 | Medium | PokerGFX 병행 운영 유지 |

---

## 13. 성공 지표 (Success Metrics)

| 지표 | 목표 | 측정 |
|------|------|------|
| 비용 절감 | $39,000/년 | 라이선스 해지 |
| 인식 정확도 | 100% | 오인식 0건/월 |
| 시스템 가동률 | 99.9% | 다운타임 < 9시간/년 |
| 전환 영향 | 0% | FusionEngine 수정 없음 |

---

## 14. 미해결 질문 (Open Questions)

- [ ] RFID 리더 제조사/모델 확정
- [ ] 기존 RFID 카드 태그 UID 목록 확보
- [ ] 테이블당 리더 설치 위치
- [ ] 네트워크 구성 (리더 ↔ 서버)

---

## 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| 1.0.0 | 2025-12-25 | 초안 작성 |
| 1.0.1 | 2025-12-26 | PRD 번호 변경 (0001 → PRD-0007) |
