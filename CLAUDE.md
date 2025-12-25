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

# 시스템 실행
python -m src.main
```

## 아키텍처

```
Primary (PokerGFX)  +  Secondary (Gemini AI)
         ↓                    ↓
         └──────┬─────────────┘
                ↓
         FusionEngine (cross-validation)
                ↓
         Output (Overlay + ClipMarker)
```

### 핵심 컴포넌트

| 모듈 | 역할 |
|------|------|
| `src/primary/pokergfx_client.py` | PokerGFX WebSocket 연결, RFID 카드 데이터 수신 |
| `src/primary/hand_classifier.py` | phevaluator 기반 핸드 등급 분류 (Royal Flush ~ High Card) |
| `src/secondary/gemini_live.py` | Gemini Live API로 비디오 스트림 분석 |
| `src/secondary/video_capture.py` | RTSP 스트림 캡처 (OpenCV) |
| `src/fusion/engine.py` | Primary/Secondary 결과 융합 및 cross-validation |
| `src/output/overlay.py` | WebSocket 서버로 방송용 오버레이 전송 |
| `src/output/clip_marker.py` | EDL/FCPXML/JSON 편집점 마커 생성 |

### Fusion 결정 로직

1. Primary + Secondary 일치 → Primary 사용 (validated)
2. Primary + Secondary 불일치 → Primary 사용 (review 플래그)
3. Primary 없음 + Secondary 있음 (confidence >= 0.80) → Secondary fallback
4. 둘 다 없음 → Manual 필요

### 데이터 모델 (`src/models/hand.py`)

- `Card`: 카드 표현 (rank + suit)
- `HandRank`: 핸드 등급 enum (1=Royal Flush ~ 10=High Card)
- `HandResult`: Primary 결과
- `AIVideoResult`: Secondary 결과
- `FusedHandResult`: 융합 결과

## 환경 설정

`.env` 파일 필요 (`.env.example` 참조):

| 변수 | 용도 |
|------|------|
| `POKERGFX_API_URL` | PokerGFX WebSocket URL |
| `GEMINI_API_KEY` | Gemini API 키 |
| `VIDEO_STREAMS` | RTSP 스트림 URL (쉼표 구분) |
| `OVERLAY_WS_PORT` | 오버레이 WebSocket 포트 |

## 핸드 등급 기준 (A~C)

### 조건 (2개 이상 충족 시 등급 확보)

1. **프리미엄 핸드**: 플레이어 소유 핸드가 프리미엄 핸드인 경우
   - Royal Flush, Straight Flush, Four of a Kind, Full House
2. **플레이 시간**: 핸드 플레이 시간이 긴 경우
3. **보드 조합**: 보드 + 플레이 핸드 조합이 Three of a Kind 이상 (7번부터 프리미엄 체크)

### 등급 기준

| 등급 | 조건 충족 | 방송 사용 |
|:----:|:--------:|:--------:|
| A | 3개 모두 | O |
| B | 2개 | O |
| C | 1개 | X |

> **B등급 이상부터 방송 사용 가능**

### 편집점 추론

기존 방송 분석을 통한 패턴 학습으로 편집 시작점 자동 추론

## Python 버전

Python 3.11+ 필수 (phevaluator, pydantic-settings 호환성)
