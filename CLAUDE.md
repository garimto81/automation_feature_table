# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

PokerGFX 기반 멀티테이블 포커 핸드 자동 캡처 및 분류 시스템. Primary(PokerGFX RFID)와 Secondary(Gemini AI Video) 이중화 아키텍처로 안정성 확보.

### 목적: 인력 자동화 (5명 → 1명 + AI)

| 역할 | 기존 | 향후 |
|------|------|------|
| 시트 관리 | 1명 | 1명 |
| 전체 모니터링 | 1명 | AI |
| 피처 테이블 A/B/C | 3명 | AI |

### 3단계 핸드 분류 프로세스

1. **1차**: GFX RFID JSON 파일로 핸드 분류
2. **2차**: Gemini Live API로 핸드 분류
3. **3차**: 1차+2차 결과를 AI가 분석 → 핸드 등급 + 편집 시작점 도출

### 활용 목적

피처 테이블 → 핸드 단위 분리/캡처 → 등급 표기 → 종합 편집팀에 핸드 소스 제공

## 빌드/테스트 명령

```powershell
# 의존성 설치
pip install -e ".[dev]"

# 린트
ruff check src/ --fix

# 단일 테스트 (권장)
pytest tests/test_hand_classifier.py -v

# 전체 테스트
pytest tests/ -v

# 커버리지 포함
pytest tests/ -v --cov=src

# 타입 검사
mypy src/

# 시스템 실행
python -m src.main

# Simulator GUI 실행 (Streamlit)
streamlit run src/simulator/gui/app.py
```

**참고**:
- `asyncio_mode = "auto"` 설정으로 async 테스트에서 `@pytest.mark.asyncio` 데코레이터 불필요
- `mypy --strict` 모드 활성화됨 (pyproject.toml)

## 아키텍처

```
Primary (PokerGFX)  +  Secondary (Gemini AI)
         ↓                    ↓
         └──────┬─────────────┘
                ↓
         FusionEngine (cross-validation)
                ↓
    ┌───────────┼───────────┐
    ↓           ↓           ↓
Database    Grading    Recording
(PostgreSQL) (A/B/C)   (vMix)
```

### 핵심 컴포넌트

| 모듈 | 역할 |
|------|------|
| `src/primary/pokergfx_client.py` | PokerGFX WebSocket 연결, RFID 카드 데이터 수신 |
| `src/primary/json_file_watcher.py` | NAS JSON 파일 감시 (watchdog 기반) |
| `src/primary/hand_classifier.py` | phevaluator 기반 핸드 등급 분류 |
| `src/secondary/gemini_live.py` | Gemini Live API로 비디오 스트림 분석 |
| `src/secondary/video_capture.py` | RTSP 스트림 캡처 (OpenCV) |
| `src/fusion/engine.py` | Primary/Secondary 결과 융합 및 cross-validation |
| `src/grading/grader.py` | 핸드 A/B/C 등급 분류 |
| `src/database/supabase_*.py` | Supabase 클라이언트 및 저장소 (Primary DB) |
| `src/database/` | PostgreSQL ORM 모델 (Legacy, deprecated) |
| `src/dashboard/` | 실시간 모니터링 WebSocket 서버 및 알림 |
| `src/simulator/` | GFX JSON 시뮬레이터 및 Streamlit GUI |
| `src/recording/` | vMix 녹화 세션 관리 |
| `src/vmix/client.py` | vMix HTTP API 클라이언트 |
| `src/fallback/` | 장애 감지 및 수동 마킹 폴백 |

### Fusion 결정 로직

| 케이스 | 조건 | 결과 |
|--------|------|------|
| 1 | Primary + Secondary 일치 | Primary 사용 (validated) |
| 2 | Primary + Secondary 불일치 | Primary 사용 (review 플래그) |
| 3 | Primary 없음 + Secondary (confidence >= 0.80) | Secondary fallback |
| 4 | 둘 다 없음 | Manual 필요 |

### 데이터 모델 (`src/models/hand.py`)

- `HandRank`: 핸드 등급 enum (value 1~10, 낮을수록 강함)
- `HandResult`: Primary 결과 (RFID 기반, confidence=1.0)
- `AIVideoResult`: Secondary 결과 (AI 추론, confidence=0.0~1.0)
- `FusedHandResult`: 융합 결과 (cross_validated, requires_review 플래그)

### HandRank 값 기준

| Value | Rank | Premium |
|:-----:|------|:-------:|
| 1 | Royal Flush | O |
| 2 | Straight Flush | O |
| 3 | Four of a Kind | O |
| 4 | Full House | O |
| 5 | Flush | X |
| 6 | Straight | X |
| 7 | Three of a Kind | X |
| 8 | Two Pair | X |
| 9 | One Pair | X |
| 10 | High Card | X |

## 환경 설정

`.env` 파일 필요 (`.env.example` 참조):

| 변수 | 용도 |
|------|------|
| `POKERGFX_API_URL` | PokerGFX WebSocket URL |
| `GEMINI_API_KEY` | Gemini API 키 |
| `VIDEO_STREAMS` | RTSP 스트림 URL (쉼표 구분) |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase 연결 (Primary DB) |
| `DB_HOST`, `DB_NAME` | PostgreSQL 데이터베이스 (Legacy) |
| `VMIX_HOST`, `VMIX_PORT` | vMix HTTP API 연결 |
| `VMIX_AUTO_RECORD` | 자동 녹화 활성화 |

## 핸드 등급 기준 (A~C)

### 조건 (2개 이상 충족 시 등급 확보)

1. **프리미엄 핸드**: HandRank.value <= 4 (Full House 이상)
2. **플레이 시간**: duration >= 120초 (설정 가능)
3. **보드 조합**: board_rank_value <= 7 (Three of a Kind 이상)

### 등급 기준

| 등급 | 조건 충족 | 방송 사용 |
|:----:|:--------:|:--------:|
| A | 3개 모두 | O |
| B | 2개 | O |
| C | 0~1개 | X |

> **B등급 이상부터 방송 사용 가능** (`broadcast_eligible = True`)

## Python 버전

Python 3.11+ 필수 (phevaluator, pydantic-settings 호환성)

## 문서 관리

### Google Drive (마스터 문서)

| 리소스 | URL |
|--------|-----|
| **공유 폴더** | [Google AI Studio](https://drive.google.com/drive/folders/1JwdlUe_v4Ug-yQ0veXTldFl6C24GH8hW) |
| PRD-0001 (Docs) | 포커 핸드 자동 캡처 및 분류 시스템 |

**폴더 내용**:
- `PRD-0001: 포커 핸드 자동 캡처 및 분류 시스템` (Google Docs)
- `architecture.png` - 시스템 아키텍처 다이어그램
- `fusion-engine.png` - Fusion Engine 설계
- `hand-grading.png` - 핸드 등급 분류

### 문서 (통합 관리)

> 이 프로젝트의 모든 문서는 **루트 프로젝트**에서 통합 관리됩니다.
>
> **절대 경로**: `C:\claude\docs\unified\`

| 유형 | 위치 | 네임스페이스 |
|------|------|-------------|
| PRD | `docs/unified/prds/FT/` | FT-0001 ~ FT-0011 |

**전체 문서 인덱스**: [C:\claude\docs\unified\index.md](../docs/unified/index.md)

## 데이터 흐름

```
PokerGFX WebSocket → HandResult → ┐
                                   ├→ FusionEngine.fuse() → FusedHandResult → HandGrader.grade() → GradeResult → Database
Gemini Live API → AIVideoResult → ┘
```

### 주요 클래스 관계

| 클래스 | 파일 | 역할 |
|--------|------|------|
| `PokerHandCaptureSystem` | `src/main.py` | 메인 오케스트레이터 |
| `MultiTableFusionEngine` | `src/fusion/engine.py` | 테이블별 FusionEngine 관리 |
| `FusionEngine` | `src/fusion/engine.py` | Primary/Secondary 결과 융합 |
| `HandGrader` | `src/grading/grader.py` | A/B/C 등급 분류 |
| `FailureDetector` | `src/fallback/detector.py` | 장애 감지 및 fallback 트리거 |
| `GFXJsonSimulator` | `src/simulator/gfx_json_simulator.py` | NAS JSON 시뮬레이션 |
| `MonitoringService` | `src/dashboard/monitoring_service.py` | 실시간 상태 동기화 |
| `SupabaseManager` | `src/database/supabase_client.py` | Supabase 연결 관리 |

## 설정 구조

`src/config/settings.py`의 중첩 설정 클래스:

```python
Settings
├── pokergfx: PokerGFXSettings
├── gemini: GeminiSettings
├── video: VideoSettings
├── database: DatabaseSettings
├── supabase: SupabaseSettings
├── vmix: VMixSettings
├── recording: RecordingSettings
├── grading: GradingSettings
├── fallback: FallbackSettings
└── simulator: SimulatorSettings  # src/simulator/config.py
```

설정 로드: `get_settings()` (LRU 캐시 적용)

## 데이터베이스 전환

**Supabase를 Primary DB로 사용** (PostgreSQL은 Legacy로 유지)

| 구분 | 용도 | 상태 |
|------|------|------|
| Supabase | 실시간 대시보드, GFX 세션 저장 | **Active** |
| PostgreSQL | 기존 핸드/플레이어 데이터 | Legacy |

Supabase 테이블:
- `gfx_sessions`: PokerGFX JSON 세션 원본 저장
- `table_status`: 테이블 연결 상태 모니터링
- `hand_grades`: 핸드 등급 이력
