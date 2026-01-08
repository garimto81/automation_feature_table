# PRD-0009: GFX JSON Simulator (NAS Test)

| 항목 | 값 |
|------|---|
| **PRD ID** | PRD-0009 |
| **제목** | GFX JSON 시뮬레이터 (NAS 테스트용) |
| **우선순위** | P1 |
| **상태** | Draft |
| **생성일** | 2026-01-08 |
| **작성자** | Claude |

---

## 1. 목적

PokerGFX에서 생성된 JSON 파일을 핸드 단위로 분리하여 NAS에 1분 간격으로 저장하는 시뮬레이터.
**Streamlit GUI**로 실시간 진행 상황 모니터링 가능.

---

## 2. 배경

### 현재 상황
- `gfx_json/` 폴더에 **완성된** JSON 파일 존재 (모든 핸드 포함)
- 실제 방송에서는 핸드가 끝날 때마다 **누적**되어 JSON 업데이트

### 문제점
- 현재 테스트 데이터는 최종 상태만 있음
- Primary 소스(PokerGFX)의 **실시간 처리** 테스트 불가

### 해결책
- JSON 파일을 핸드 단위로 분리
- 1분 간격으로 NAS에 순차 저장
- **Streamlit GUI**로 진행 상황 실시간 확인

---

## 3. JSON 데이터 구조

### 원본 파일 위치
```
gfx_json/
├── table-GG/
│   ├── 1015/
│   │   └── PGFX_live_data_export GameID=638961224831992165.json
│   └── 1020/
│       └── PGFX_live_data_export GameID=638965539561171011.json
└── table-pokercaster/
    └── 1019/
        └── PGFX_live_data_export GameID=638964779563363778.json
```

### JSON 구조
```json
{
  "CreatedDateTimeUTC": "2025-10-20T10:45:56.1171011Z",
  "EventTitle": "",
  "Hands": [
    {
      "HandNum": 1,
      "Duration": "PT1M10.9099008S",
      "StartDateTimeUTC": "2025-10-20T10:56:40.1947940Z",
      "GameVariant": "HOLDEM",
      "Players": [...],
      "Events": [...]
    }
  ]
}
```

---

## 4. 기능 요구사항

### 4.1 핵심 기능

| 기능 | 설명 |
|------|------|
| **JSON 파싱** | 원본 JSON에서 핸드 배열 추출 |
| **핸드 분리** | 시간순 정렬 후 개별 핸드로 분리 |
| **누적 생성** | 핸드 1 -> 1+2 -> 1+2+3 형태로 누적 |
| **타이머 생성** | 1분(60초) 간격으로 파일 생성 |
| **NAS 저장** | 설정된 NAS 경로에 파일 저장 |
| **GUI 모니터링** | Streamlit으로 실시간 상태 확인 |

### 4.2 출력 구조

```
{NAS_PATH}/
├── table-GG/
│   └── PGFX_live_data_export GameID={GameID}.json
└── table-pokercaster/
    └── PGFX_live_data_export GameID={GameID}.json
```

### 4.3 시뮬레이션 흐름

```
[0분] Hand 1만 포함된 JSON 생성
  |
[1분] Hand 1+2 포함된 JSON 생성 (덮어쓰기)
  |
[2분] Hand 1+2+3 포함된 JSON 생성 (덮어쓰기)
  |
...
[N분] 전체 핸드 포함 (완료)
```

---

## 5. Streamlit GUI 설계

### 5.1 화면 레이아웃

```
+-------------------------------------------------------------+
|  GFX JSON Simulator                                   [설정] |
+-------------------------------------------------------------+
|                                                             |
|  +---------------+  +-----------------------------+         |
|  | 설정          |  | 진행 상황                   |         |
|  |               |  |                             |         |
|  | Source: [선택]|  | ============-------- 65%   |         |
|  | Target: [선택]|  |                             |         |
|  | Interval:[60s]|  | 현재: Hand 13 / 20         |         |
|  |               |  | 경과: 12분 30초            |         |
|  | [시작] [정지] |  | 남은: 7분 30초             |         |
|  +---------------+  +-----------------------------+         |
|                                                             |
|  +-------------------------------------------------------+  |
|  | 실시간 로그                                            |  |
|  |                                                        |  |
|  | [12:30:45] OK Hand 13 생성 완료 (table-GG)            |  |
|  | [12:29:45] OK Hand 12 생성 완료 (table-GG)            |  |
|  | [12:28:45] OK Hand 11 생성 완료 (table-GG)            |  |
|  | [12:27:45] WARN NAS 연결 재시도 (1/3)                 |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

### 5.2 GUI 기능

| 영역 | 기능 |
|------|------|
| **설정 패널** | Source/Target 경로 선택, Interval 설정 |
| **제어 버튼** | 시작/정지 버튼 |
| **진행 바** | 전체 진행률 (%) |
| **상태 표시** | 현재 핸드, 경과/남은 시간 |
| **로그 뷰어** | 실시간 로그 스크롤 (최근 100개) |

### 5.3 상태 표시

| 상태 | 아이콘 | 설명 |
|------|--------|------|
| 대기 | IDLE | 시작 전 |
| 실행 중 | RUNNING | 시뮬레이션 진행 중 |
| 일시 정지 | PAUSED | 사용자가 일시 정지 |
| 완료 | COMPLETED | 모든 핸드 처리 완료 |
| 오류 | ERROR | NAS 연결 실패 등 |

---

## 6. 설정 파일

### 6.1 .env 환경 변수

```env
# NAS 경로 설정
SIMULATOR_NAS_PATH=\\\\NAS\\poker\\gfx_output
# 또는 마운트된 드라이브
# SIMULATOR_NAS_PATH=Z:\\poker\\gfx_output

# 생성 간격 (초)
SIMULATOR_INTERVAL_SEC=60

# 소스 JSON 경로
SIMULATOR_SOURCE_PATH=C:\\claude\\automation_feature_table\\gfx_json

# Streamlit 포트
STREAMLIT_PORT=8501
```

### 6.2 CLI 옵션 (GUI 없이 실행)

```powershell
python -m src.simulator.gfx_json_simulator `
  --source gfx_json/ `
  --target \\NAS\poker\output `
  --interval 60 `
  --no-gui
```

---

## 7. 기술 설계

### 7.1 모듈 구조

```
src/
└── simulator/
    ├── __init__.py
    ├── gfx_json_simulator.py   # 시뮬레이터 핵심 로직
    ├── hand_splitter.py        # 핸드 분리
    ├── config.py               # 설정 관리
    └── gui/
        ├── __init__.py
        ├── app.py              # Streamlit 메인 앱
        └── components.py       # UI 컴포넌트
```

### 7.2 클래스 설계

#### GFXJsonSimulator

```python
class GFXJsonSimulator:
    def __init__(self, source: Path, target: Path, interval: int = 60):
        self.source_path = source
        self.target_path = target
        self.interval = interval
        self.status = Status.IDLE
        self.logs: list[LogEntry] = []
        self.current_hand = 0
        self.total_hands = 0

    async def run(self) -> None:
        """시뮬레이션 실행"""
        ...

    def stop(self) -> None:
        """시뮬레이션 정지"""
        ...

    def get_progress(self) -> float:
        """진행률 반환 (0.0 ~ 1.0)"""
        ...

    def get_logs(self) -> list[LogEntry]:
        """로그 목록 반환"""
        ...
```

#### HandSplitter

```python
class HandSplitter:
    @staticmethod
    def split_hands(json_data: dict) -> list[dict]:
        """JSON에서 핸드 목록 추출 및 정렬"""
        ...

    @staticmethod
    def build_cumulative(hands: list[dict], count: int, metadata: dict) -> dict:
        """누적 JSON 생성"""
        ...
```

---

## 8. 비기능 요구사항

| 항목 | 요구사항 |
|------|----------|
| **네트워크 오류** | NAS 연결 실패 시 재시도 (3회) |
| **로깅** | 핸드별 생성 로그 + GUI 표시 |
| **중단/재개** | GUI 버튼 또는 Ctrl+C로 안전 종료 |
| **실시간 업데이트** | GUI 1초 간격 새로고침 |

---

## 9. 구현 계획

### Phase 1: 핵심 시뮬레이터
- [ ] HandSplitter 클래스
- [ ] GFXJsonSimulator 기본 로직
- [ ] CLI 인터페이스

### Phase 2: Streamlit GUI
- [ ] Streamlit 앱 기본 레이아웃
- [ ] 진행 바 및 상태 표시
- [ ] 실시간 로그 뷰어

### Phase 3: 설정 및 에러 처리
- [ ] .env 설정 통합
- [ ] NAS 연결 재시도 로직
- [ ] 에러 핸들링

---

## 10. 테스트 계획

| 테스트 | 검증 항목 |
|--------|----------|
| Unit | HandSplitter 핸드 분리 로직 |
| Unit | 누적 JSON 생성 정확성 |
| Integration | NAS 파일 쓰기 |
| E2E | Streamlit GUI + 시뮬레이션 |

---

## 11. 실행 방법

### GUI 모드 (기본)
```powershell
streamlit run src/simulator/gui/app.py
```

### CLI 모드
```powershell
python -m src.simulator.gfx_json_simulator --no-gui
```

---

## 12. 관련 문서

- PRD-0001: 포커 핸드 자동 캡처 및 분류 시스템
- PRD-0002: Primary 소스 (PokerGFX RFID)
