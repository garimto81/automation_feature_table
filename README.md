# Poker Hand Auto-Capture System

PokerGFX 기반 멀티테이블 포커 핸드 자동 캡처 및 분류 시스템

## 개요

포커 프로덕션 환경에서 여러 대의 피처 테이블에서 발생하는 핸드를 자동으로 감지, 분류, 기록하는 시스템입니다.

### 주요 기능

- **핸드 시작/종료 자동 감지**: PokerGFX RFID 데이터 기반
- **핸드 등급 자동 분류**: Royal Flush ~ High Card (10단계)
- **2중 안정성 아키텍처**: Primary(PokerGFX) + Secondary(AI Video) 이중화
- **핸드 등급 분류**: A/B/C 등급 자동 분류
- **클립 마킹**: EDL/FCPXML/JSON 편집점 자동 생성
- **데이터베이스 저장**: PostgreSQL 기반 핸드/플레이어 통합 관리

## 설치

### 요구사항

- Python 3.11+
- PokerGFX 엔터프라이즈 라이선스
- PostgreSQL 16+

### 설치 방법

```bash
# 저장소 클론
git clone <repository-url>
cd automation_feature_table

# 의존성 설치
pip install -e ".[dev]"

# 환경 변수 설정
cp .env.example .env
# .env 파일 수정하여 API 키 설정
```

## 설정

### 환경 변수 (.env)

```env
# PokerGFX
POKERGFX_API_URL=ws://localhost:8080
POKERGFX_API_KEY=your_api_key

# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Video Streams
VIDEO_STREAMS=rtsp://table1:554/stream,rtsp://table2:554/stream

# Database
DB_HOST=localhost
DB_NAME=poker_hand_capture

# vMix
VMIX_HOST=localhost
VMIX_PORT=8088
```

## 사용법

### 시스템 실행

```bash
python -m src.main
```

### 출력 형식

- **JSON**: 모든 핸드 정보 포함
- **EDL**: DaVinci Resolve, Premiere Pro 호환
- **FCPXML**: Final Cut Pro 호환

## 프로젝트 구조

```
automation_feature_table/
├── src/
│   ├── config/         # 설정 관리
│   ├── models/         # 데이터 모델
│   ├── primary/        # PokerGFX RFID 연동
│   ├── secondary/      # Gemini AI Video 연동
│   ├── fusion/         # Primary/Secondary 융합 엔진
│   ├── database/       # PostgreSQL 연결/저장소
│   ├── grading/        # 핸드 A/B/C 등급 분류
│   ├── recording/      # vMix 녹화 세션 관리
│   ├── vmix/           # vMix HTTP API 클라이언트
│   ├── fallback/       # 장애 감지/수동 마킹
│   └── main.py         # 메인 진입점
├── tests/              # 테스트
├── docs/               # 문서
│   └── checklists/     # 체크리스트
├── tasks/
│   └── prds/           # PRD 문서
├── pyproject.toml      # 프로젝트 설정
└── README.md
```

## 테스트

```bash
# 전체 테스트
pytest tests/ -v

# 커버리지 포함
pytest tests/ -v --cov=src
```

## 관련 문서

- [PRD-0001](tasks/prds/PRD-0001-poker-hand-auto-capture.md) - 프로젝트 요구사항
- [PRD-0005](tasks/prds/PRD-0005-integrated-db-subtitle-system.md) - DB/자막 시스템
- [CLAUDE.md](CLAUDE.md) - 개발자 지침 (아키텍처, 핸드 등급 상세)

## 라이선스

MIT License
