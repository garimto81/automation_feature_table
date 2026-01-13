# GFX JSON Simulator

PokerGFX JSON 파일을 입력받아 실제 게임 진행처럼 핸드를 순차적으로 누적 생성하는 시뮬레이터입니다.

## 개요

### 목적
- 실제 게임 없이 NAS 연동 테스트 가능
- 파일 감시(File Watcher) 로직 검증
- SMB 장애 시나리오 테스트

### 동작 방식
1. 소스 폴더에서 GFX JSON 파일 스캔
2. 각 파일의 `Hands` 배열을 추출
3. 지정된 간격으로 핸드를 하나씩 누적하여 타겟 폴더에 저장
4. 실시간 진행률 및 로그 모니터링

```
Source JSON:         Output (누적):
{                    Step 1: {"Hands": [H1]}
  "Hands": [         Step 2: {"Hands": [H1, H2]}
    H1, H2, H3       Step 3: {"Hands": [H1, H2, H3]}
  ]
}
```

## 빠른 시작

### GUI 모드 (권장)

```powershell
streamlit run src/simulator/gui/app.py
```

브라우저에서 `http://localhost:8501` 접속

### CLI 모드

```powershell
python -m src.simulator.gfx_json_simulator --help

# 예시
python -m src.simulator.gfx_json_simulator \
  --source C:\gfx_json\tournament \
  --target \\NAS\pokergfx\hands \
  --interval 60 \
  --no-gui
```

## GUI 사용법

### 1. 소스 경로 설정
- 사이드바에서 GFX JSON 파일이 있는 폴더 경로 입력
- `📁` 버튼으로 폴더 선택 다이얼로그 사용 가능

### 2. 파일 스캔
- `🔍 파일 스캔` 버튼 클릭
- 테이블별로 그룹화된 파일 목록 표시
- 체크박스로 시뮬레이션할 파일 선택

### 3. 타겟 경로 설정
- NAS 또는 로컬 출력 폴더 경로 입력
- UNC 경로 지원 (`\\NAS\share\folder`)

### 4. 생성 간격 설정
- 핸드 생성 간격(초) 설정
- 기본값: 60초

### 5. 시뮬레이션 실행
- `▶️ 시작`: 시뮬레이션 시작
- `⏹️ 정지`: 현재 핸드 완료 후 중지
- `🔄 초기화`: 모든 상태 리셋

### 6. 모니터링
- **진행률 바**: 전체 진행 상황
- **메트릭**: 현재 핸드, 진행률, 경과/남은 시간
- **실시간 로그**: 최근 50개 로그 메시지

## 설정

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SIMULATOR_SOURCE_PATH` | `./gfx_json` | 소스 폴더 경로 |
| `SIMULATOR_NAS_PATH` | `./output` | 타겟 폴더 경로 |
| `SIMULATOR_INTERVAL_SEC` | `60` | 핸드 생성 간격 (초) |
| `STREAMLIT_PORT` | `8501` | Streamlit 서버 포트 |

### 설정 파일 (.simulator_settings.json)

사용자 설정은 자동으로 저장되며 재시작 시 복원됩니다:

```json
{
  "last_source_path": "C:\\gfx_json\\tournament",
  "last_target_path": "\\\\NAS\\pokergfx\\hands",
  "last_interval": 60
}
```

## 파일 구조

```
src/simulator/
├── __init__.py              # 모듈 초기화
├── config.py                # 설정 관리 (SimulatorSettings)
├── hand_splitter.py         # 핸드 분리 유틸리티
├── gfx_json_simulator.py    # 메인 시뮬레이터 + CLI
└── gui/
    ├── __init__.py          # GUI 모듈 초기화
    ├── app.py               # Streamlit 메인 앱
    └── file_browser.py      # 파일 브라우저 유틸리티
```

## 클래스 참조

### GFXJsonSimulator

메인 시뮬레이터 클래스

```python
from src.simulator.gfx_json_simulator import GFXJsonSimulator, Status

sim = GFXJsonSimulator(
    source_path=Path("./gfx_json"),
    target_path=Path("./output"),
    interval=60,  # 핸드 생성 간격 (초)
)

# 비동기 실행
await sim.run()

# 동기 실행 (CLI용)
sim.run_sync()

# 상태 확인
print(sim.status)     # Status.RUNNING, COMPLETED, ERROR 등
print(sim.progress)   # SimulationProgress 객체
```

### HandSplitter

핸드 분리 유틸리티

```python
from src.simulator.hand_splitter import HandSplitter

# 핸드 목록 추출 (HandNum으로 정렬)
hands = HandSplitter.split_hands(json_data)

# 누적 JSON 생성 (처음 N개 핸드)
cumulative = HandSplitter.build_cumulative(hands, count=5, metadata=meta)

# 핸드 수 확인
count = HandSplitter.get_hand_count(json_data)
```

## 상태 (Status)

| 상태 | 설명 |
|------|------|
| `IDLE` | 초기 상태, 시작 대기 중 |
| `RUNNING` | 시뮬레이션 실행 중 |
| `PAUSED` | 일시 정지 (향후 지원) |
| `STOPPED` | 사용자가 중지함 |
| `COMPLETED` | 모든 파일 처리 완료 |
| `ERROR` | 오류 발생 (재시도 실패 등) |

## 에러 처리

### 파일 쓰기 재시도
- 쓰기 실패 시 3회 재시도 (5초 간격)
- 모든 재시도 실패 시 ERROR 상태

### JSON 파싱 오류
- 잘못된 JSON 파일은 건너뜀
- 로그에 오류 기록

### 경로 오류
- 존재하지 않는 소스 경로: 에러 메시지 표시
- 타겟 폴더 없음: 자동 생성

## 테스트

```powershell
# 단위 테스트
python -m pytest tests/test_gfx_json_simulator.py -v

# 통합 테스트
python -m pytest tests/test_simulator_integration.py -v

# E2E 테스트 (Playwright 필요)
python -m pytest tests/e2e/test_simulator_gui.py -v -m e2e

# 전체 테스트 + 커버리지
python -m pytest tests/ -v --cov=src/simulator
```

## 수동 Import 탭

SMB 연결 실패 시 수동으로 GFX JSON 파일을 업로드하는 기능:

1. **수동 Import** 탭 선택
2. 파일 드래그앤드롭 또는 업로드
3. Fallback 폴더에 자동 저장
4. 시스템이 자동으로 처리

## 관련 문서

- [PRD-0009](../../docs/PRD-0009-gfx-json-simulator.md): 기능 명세
- [PRD-0009 Checklist](../../docs/checklists/PRD-0009.md): 진행 체크리스트
