# PRD-0005: 통합 데이터베이스 및 자막 데이터 시스템

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0005 |
| **제목** | 통합 데이터베이스 및 자막 데이터 시스템 |
| **버전** | 1.1 |
| **작성일** | 2025-12-25 |
| **상태** | Draft |
| **상위 문서** | [PRD-0002](./PRD-0002-primary-gfx-rfid.md) |
| **참조 문서** | [WSOP Broadcast Graphics PRD](../../../automation_sub/tasks/prds/0001-prd-wsop-broadcast-graphics.md) |
| **우선순위** | P0 |

### Changelog

| 버전 | 날짜 | 변경 사항 |
|------|------|----------|
| 1.1 | 2025-12-25 | WSOP PRD 기반 자막 유형 20종 추가, 핸드 분할/등급 분석 섹션 추가 |
| 1.0 | 2025-12-25 | 초기 버전 |

---

## 1. 개요

### 1.1 목적

PRD-0002 (Primary Layer - GFX RFID)에서 출력되는 핸드 데이터를 PostgreSQL 데이터베이스로 통합 관리하여 2개 파트로 활용:

#### Part 1: RFID JSON → DB 통합 관리 → 자막 데이터 제공
1. **플레이어 추적**: 테이블 이동 시에도 동일 플레이어 데이터 통합 관리
2. **Chip Flow**: 핸드 간 스택 변화 추적 및 시계열 이력 관리
3. **자막 데이터**: WSOP PRD 기반 20종 자막 유형 지원 (Adobe After Effects 후편집용)

#### Part 2: RFID JSON → 핸드 분할 녹화 + 등급 분석 → 편집 원소스 제공
1. **핸드 분할 녹화**: 피처 테이블 핸드별 클립 마커 생성 (시작/종료 시간)
2. **핸드 등급 분석**: PRD-0001 기준 A/B/C 등급 자동 분류
3. **편집 원소스**: EDL/FCPXML/JSON 형식으로 종합 편집팀에 제공

### 1.2 인력 자동화 목표

| 역할 | 기존 | 향후 |
|------|:----:|:----:|
| 시트 관리 | 1명 | 1명 |
| 전체 모니터링 | 1명 | AI |
| 피처 테이블 A/B/C | 3명 | AI |
| **합계** | **5명** | **1명 + AI** |

### 1.3 핵심 가치

| 가치 | 설명 |
|------|------|
| **데이터 지속성** | 세션 간 데이터 유지, 히스토리컬 분석 가능 |
| **플레이어 통합** | 멀티테이블 환경에서 동일 플레이어 추적 |
| **자막 자동화** | 핸드 데이터 → AE 템플릿 자동 연동 |
| **Chip Flow 분석** | 시간별 스택 변화 그래프 데이터 제공 |

---

## 2. 아키텍처

### 2.1 시스템 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          POKER HAND CAPTURE SYSTEM                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐
│  Primary Layer   │     │ Secondary Layer  │
│  (PokerGFX RFID) │     │  (Gemini AI)     │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         │  HandResult            │  AIVideoResult
         └────────────┬───────────┘
                      ▼
              ┌───────────────┐
              │ FusionEngine  │
              │ (cross-valid) │
              └───────┬───────┘
                      │ FusedHandResult
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER (PostgreSQL)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ sessions │  │  tables  │  │ players  │  │  hands   │  │chip_flow │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │hand_cards│  │player_   │  │  hand_   │  │  clip_   │  │subtitle_ │       │
│  │          │  │  hands   │  │ actions  │  │ markers  │  │  data    │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXPORT LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐     │
│  │ SubtitleExporter   │  │ ChipFlowExporter   │  │ ClipMarkerExporter │     │
│  │ (JSON → AE)        │  │ (시계열 데이터)     │  │ (EDL/FCPXML)       │     │
│  └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘     │
│            │                       │                       │                 │
└────────────┼───────────────────────┼───────────────────────┼─────────────────┘
             │                       │                       │
             ▼                       ▼                       ▼
     ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
     │ Adobe After   │      │ 편집 소프트웨어│      │ 방송 편집     │
     │ Effects       │      │ (Resolve/FCP) │      │ (Final Cut)   │
     └───────────────┘      └───────────────┘      └───────────────┘
```

### 2.2 데이터 흐름

```
1. 핸드 완료
   PokerGFX JSON → FusionEngine → FusedHandResult
                                        │
2. DB 저장                              │
   FusedHandResult ─────────────────────┼────────────────────┐
         │                              │                    │
         ▼                              ▼                    ▼
   ┌──────────┐                  ┌──────────┐          ┌──────────┐
   │  hands   │ ◄────────────────│ player_  │          │ chip_    │
   │          │                  │  hands   │          │  flow    │
   └──────────┘                  └──────────┘          └──────────┘
         │                              │
         │                              │
3. 플레이어 매칭                        ▼
   Name → players (get_or_create) ──► player_id 연결
                                        │
4. 자막 내보내기                        │
   세션 종료 시 ────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────────┐
   │ SubtitleExporter.export_for_ae()         │
   │                                          │
   │  → players.json (프로필)                  │
   │  → hands.json (핸드 데이터)               │
   │  → chip_flow.json (스택 변화)             │
   │  → timecodes.json (편집점)               │
   └──────────────────────────────────────────┘
```

---

## 3. 데이터베이스 설계

### 3.1 ERD (Entity-Relationship Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATABASE SCHEMA (ERD)                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   sessions   │       │    tables    │       │   players    │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ PK session_id│       │ PK table_id  │       │ PK player_id │
│    name      │──1:N──│ FK session_id│       │    name      │  ◄─── 이름 기반
│    venue     │       │    status    │       │    country   │       자동 매칭
│    type      │       │    blind_sb  │       │    photo_url │
│    start_time│       │    blind_bb  │       │    notes     │
│    end_time  │       │    ante      │       │    meta      │
│    meta      │       └──────────────┘       └──────────────┘
└──────────────┘              │                      │
                              │ 1                    │ M
                              │                      │
                              N                      │
                       ┌──────────────┐              │
                       │    hands     │              │
                       ├──────────────┤              │
                       │ PK hand_id   │              │
                       │ FK table_id  │              │
                       │    hand_num  │              │
                       │    start_time│              │
                       │    end_time  │              │
                       │    duration  │              │
                       │    pot_size  │              │
                       │    source    │              │  Fusion 결과
                       │    confidence│              │
                       │    validated │              │
                       │    hand_rank │              │  등급 분류
                       │    is_premium│              │
                       │    grade     │              │  A/B/C
                       └──────────────┘              │
                              │                      │
                    ┌─────────┼─────────┐            │
                    │         │         │            │
                    N         N         N            │
             ┌──────────┐ ┌──────────┐ ┌────────────┐│
             │hand_cards│ │  hand_   │ │ player_    ││
             ├──────────┤ │ actions  │ │  hands     ││
             │PK card_id│ ├──────────┤ ├────────────┤│
             │FK hand_id│ │PK act_id │ │ PK ph_id   ││
             │   rank   │ │FK hand_id│ │ FK hand_id ││
             │   suit   │ │   seat   │ │ FK player_ │◄──┘
             │   type   │ │   action │ │    id      │
             │   seat   │ │   amount │ │   seat     │
             │   order  │ │   street │ │   position │
             └──────────┘ │   seq    │ │ stack_start│  Chip Flow
                          └──────────┘ │ stack_end  │  핵심 데이터
                                       │ stack_delta│
                                       │ hole_cards │
                                       │ hand_rank  │
                                       │ is_winner  │
                                       │ won_amount │
                                       │   vpip     │  통계
                                       │   pfr      │
                                       └────────────┘
                                              │
                                              │ 1
                                              │
                                              N
                                       ┌────────────┐
                                       │ chip_flow  │   시계열
                                       ├────────────┤   이력
                                       │ PK flow_id │
                                       │ FK ph_id   │
                                       │ FK player_ │
                                       │    id      │
                                       │ FK hand_id │
                                       │   delta    │
                                       │   reason   │
                                       │   running_ │
                                       │    total   │
                                       │   timestamp│
                                       └────────────┘

┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ clip_markers │       │  ai_results  │       │subtitle_data │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ PK marker_id │       │ PK ai_id     │       │ PK sub_id    │
│ FK hand_id   │       │ FK hand_id   │       │ FK hand_id   │
│    start_time│       │    event     │       │ FK player_id │
│    end_time  │       │    confidence│       │    type      │
│    grade     │       │    context   │       │    content   │
│    notes     │       │    cards     │       │    timecode  │
│    exported  │       │    timestamp │       │    style     │
└──────────────┘       └──────────────┘       └──────────────┘
```

### 3.2 테이블 정의

#### 3.2.1 sessions (세션/이벤트)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `session_id` | UUID | PK, 세션 고유 ID |
| `name` | VARCHAR(255) | 세션 이름 (예: "WSOP Main Event Day 1") |
| `venue` | VARCHAR(255) | 장소 |
| `type` | VARCHAR(50) | 타입: tournament, cash_game |
| `start_time` | TIMESTAMP | 세션 시작 시간 |
| `end_time` | TIMESTAMP | 세션 종료 시간 |
| `meta` | JSONB | 추가 메타데이터 |

#### 3.2.2 tables (테이블)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `table_id` | VARCHAR(50) | PK, 테이블 ID (예: "feature_a") |
| `session_id` | UUID | FK → sessions |
| `location` | VARCHAR(100) | 위치 (예: "Main Stage") |
| `status` | VARCHAR(20) | 상태: active, paused, closed |
| `blind_sb` | INTEGER | 스몰 블라인드 |
| `blind_bb` | INTEGER | 빅 블라인드 |
| `ante` | INTEGER | 앤티 |
| `max_seats` | INTEGER | 최대 좌석 수 (기본: 10) |

#### 3.2.3 players (플레이어 마스터)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `player_id` | UUID | PK, 플레이어 고유 ID |
| `name` | VARCHAR(255) | 플레이어 이름 (UNIQUE) |
| `display_name` | VARCHAR(100) | 방송용 표시 이름 |
| `country` | CHAR(2) | 국적 코드 (ISO 3166-1 alpha-2) |
| `photo_url` | VARCHAR(500) | 프로필 사진 URL |
| `notes` | TEXT | 메모 |
| `meta` | JSONB | 추가 프로필 정보 |

**플레이어 자동 매칭 로직**:

```python
async def get_or_create_player(self, name: str) -> Player:
    """이름으로 플레이어 조회, 없으면 자동 생성"""
    player = await self.db.fetchrow(
        "SELECT * FROM players WHERE name = $1", name
    )
    if not player:
        player_id = uuid.uuid4()
        await self.db.execute(
            "INSERT INTO players (player_id, name) VALUES ($1, $2)",
            player_id, name
        )
        return await self.get_by_id(player_id)
    return Player(**player)
```

#### 3.2.4 hands (핸드)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `hand_id` | UUID | PK, 핸드 고유 ID |
| `table_id` | VARCHAR(50) | FK → tables |
| `hand_number` | INTEGER | 핸드 번호 |
| `start_time` | TIMESTAMP | 핸드 시작 시간 |
| `end_time` | TIMESTAMP | 핸드 종료 시간 |
| `duration_sec` | INTEGER | 핸드 진행 시간 (초) |
| `pot_size` | BIGINT | 최종 팟 사이즈 |
| `winner_player_id` | UUID | FK → players (승자) |
| `source` | VARCHAR(20) | 소스: pokergfx, ai_video, fused, manual |
| `confidence` | DECIMAL(3,2) | 신뢰도 (0.00 ~ 1.00) |
| `cross_validated` | BOOLEAN | 교차 검증 여부 |
| `requires_review` | BOOLEAN | 검토 필요 여부 |
| `best_hand_rank` | INTEGER | 최고 핸드 등급 (1-10) |
| `is_premium` | BOOLEAN | 프리미엄 핸드 여부 |
| `grade` | CHAR(1) | 등급: A, B, C |
| `grade_factors` | JSONB | 등급 판정 근거 |

**인덱스**:
- `idx_hands_table` (table_id, hand_number DESC)
- `idx_hands_time` (start_time DESC)
- `idx_hands_grade` (grade) WHERE grade IN ('A', 'B')
- `idx_hands_premium` (is_premium) WHERE is_premium = TRUE

#### 3.2.5 player_hands (플레이어별 핸드 참여)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `ph_id` | UUID | PK |
| `hand_id` | UUID | FK → hands |
| `player_id` | UUID | FK → players |
| `seat` | INTEGER | 시트 번호 (1-10) |
| `position` | VARCHAR(10) | 포지션: BTN, SB, BB, UTG 등 |
| `stack_start` | BIGINT | 핸드 시작 스택 |
| `stack_end` | BIGINT | 핸드 종료 스택 |
| `stack_delta` | BIGINT | 스택 변화 (자동 계산) |
| `hole_cards` | CHAR(4) | 홀 카드 (예: "AhKd") |
| `hand_rank` | INTEGER | 쇼다운 시 핸드 등급 |
| `hand_rank_value` | INTEGER | phevaluator 값 |
| `is_winner` | BOOLEAN | 승자 여부 |
| `won_amount` | BIGINT | 승리 금액 |
| `vpip` | BOOLEAN | VPIP 여부 |
| `pfr` | BOOLEAN | PFR 여부 |
| `went_showdown` | BOOLEAN | 쇼다운 참여 여부 |

#### 3.2.6 hand_actions (핸드 액션)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `action_id` | SERIAL | PK |
| `hand_id` | UUID | FK → hands |
| `seat` | INTEGER | 시트 번호 |
| `player_id` | UUID | FK → players |
| `street` | VARCHAR(10) | 스트리트: preflop, flop, turn, river |
| `action` | VARCHAR(20) | 액션: fold, check, call, raise, bet, all_in |
| `amount` | BIGINT | 베팅/레이즈 금액 |
| `pot_after` | BIGINT | 액션 후 팟 사이즈 |
| `action_seq` | INTEGER | 액션 순서 |
| `timestamp` | TIMESTAMP | 액션 시간 |

#### 3.2.7 chip_flow (칩 흐름 추적)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `flow_id` | SERIAL | PK |
| `ph_id` | UUID | FK → player_hands |
| `player_id` | UUID | FK → players |
| `hand_id` | UUID | FK → hands |
| `delta` | BIGINT | 칩 변동량 (+/-) |
| `reason` | VARCHAR(50) | 사유: pot_win, blind, ante, rake, bet |
| `running_total` | BIGINT | 누적 스택 |
| `timestamp` | TIMESTAMP | 기록 시간 |

**인덱스**:
- `idx_chip_flow_player` (player_id, timestamp DESC)
- `idx_chip_flow_hand` (hand_id)

#### 3.2.8 hand_cards (핸드별 카드)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `card_id` | SERIAL | PK |
| `hand_id` | UUID | FK → hands |
| `card_rank` | CHAR(2) | 랭크: A, K, Q, J, T, 9-2 |
| `card_suit` | CHAR(1) | 수트: h, d, c, s |
| `card_type` | VARCHAR(20) | 타입: hole, flop, turn, river |
| `seat` | INTEGER | 홀 카드인 경우 시트 번호 |
| `deal_order` | INTEGER | 딜링 순서 |

#### 3.2.9 clip_markers (편집 마커)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `marker_id` | UUID | PK |
| `hand_id` | UUID | FK → hands |
| `table_id` | VARCHAR(50) | 테이블 ID |
| `hand_number` | INTEGER | 핸드 번호 |
| `start_time` | TIMESTAMP | 시작 시간 |
| `end_time` | TIMESTAMP | 종료 시간 |
| `duration_sec` | INTEGER | 길이 (초) |
| `hand_rank` | VARCHAR(50) | 핸드 등급 이름 |
| `is_premium` | BOOLEAN | 프리미엄 여부 |
| `grade` | CHAR(1) | 등급: A, B, C |
| `notes` | TEXT | 노트 |
| `exported` | BOOLEAN | 내보내기 완료 여부 |
| `export_format` | VARCHAR(20) | 내보내기 형식: edl, fcpxml, json |

#### 3.2.10 ai_results (AI 분석 결과)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `ai_id` | SERIAL | PK |
| `hand_id` | UUID | FK → hands |
| `table_id` | VARCHAR(50) | 테이블 ID |
| `detected_event` | VARCHAR(50) | 감지된 이벤트 |
| `detected_cards` | JSONB | 감지된 카드 배열 |
| `hand_rank` | INTEGER | 감지된 핸드 등급 |
| `confidence` | DECIMAL(3,2) | 신뢰도 |
| `context` | TEXT | AI 생성 설명 |
| `timestamp` | TIMESTAMP | 분석 시간 |

#### 3.2.11 subtitle_data (자막용 데이터 캐시)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `sub_id` | SERIAL | PK |
| `hand_id` | UUID | FK → hands |
| `player_id` | UUID | FK → players |
| `table_id` | VARCHAR(50) | 테이블 ID |
| `type` | VARCHAR(50) | 자막 타입 |
| `content` | JSONB | 자막 데이터 |
| `timecode_start` | VARCHAR(20) | 시작 타임코드 |
| `timecode_end` | VARCHAR(20) | 종료 타임코드 |
| `style` | VARCHAR(50) | 스타일 프리셋 |

---

## 4. 자막 데이터 구조 (WSOP PRD 기반)

> 참조: [WSOP Broadcast Graphics PRD](../../../automation_sub/tasks/prds/0001-prd-wsop-broadcast-graphics.md)

### 4.1 자막 유형 분류 (20종)

#### 4.1.1 Leaderboard System (5종)

| 유형 | 설명 | 필요 데이터 |
|------|------|------------|
| `tournament_leaderboard` | 전체 순위 (스크롤) | players[], chips, bbs, rank_change |
| `feature_table_leaderboard` | 피처 테이블 순위 | table_players[], profile_image, percentage |
| `mini_chip_counts` | 미니 칩 표시 | player_name, chips, is_highlighted, is_pot_winner |
| `payouts` | 상금 구조 (1st-9th) | payouts[], bubble_line, is_itm, total_prize |
| `mini_payouts` | 미니 상금 | current_payout, next_jump, final_table_prizes |

#### 4.1.2 Statistics (5종)

| 유형 | 설명 | 필요 데이터 |
|------|------|------------|
| `chip_comparison` | 스택 비율 비교 (도넛) | player_a_pct, player_b_pct, player_stacks |
| `chip_flow` | 시계열 그래프 | chip_history[], last_n_hands, avg_stack_pct |
| `chips_in_play` | 칩 종류별 수량 | chip_denominations[], colors |
| `vpip_stats` | VPIP 프로그레스 바 | vpip_pct, player_name, sample_size |
| `pfr_stats` | PFR 프로그레스 바 | pfr_pct, player_name, sample_size |

#### 4.1.3 Player Info (6종)

| 유형 | 설명 | 필요 데이터 |
|------|------|------------|
| `player_profile` | 기본 프로필 (Lower Third) | name, country, stack, photo_url |
| `at_risk_elimination` | 탈락 위험 알림 | rank, payout_amount, player_name |
| `player_intro_card` | 플레이어 소개 | bracelets, total_earnings, final_tables |
| `heads_up_comparison` | 1:1 비교 | player_a, player_b, stats_comparison |
| `elimination` | 탈락 알림 | player, finish_position, prize, eliminator |
| `commentator_profile` | 해설자 프로필 | name, photo, role |

#### 4.1.4 Event Graphics (4종)

| 유형 | 설명 | 필요 데이터 |
|------|------|------------|
| `broadcast_schedule` | 방송 일정 | events[], current_event, date_time |
| `tournament_info` | 토너먼트 정보 | buy_in, prize_pool, entries, remaining, places_paid |
| `event_name` | 이벤트명 | event_name, venue, location |
| `blind_level` | 블라인드 업 | level, sb, bb, ante, duration, next_level |

### 4.2 After Effects 연동 JSON 구조

#### 4.2.1 메타데이터

```json
{
  "metadata": {
    "version": "1.0",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "session_name": "WSOP Main Event Day 1",
    "table_id": "feature_a",
    "exported_at": "2025-12-25T18:00:00Z",
    "frame_rate": 30,
    "timecode_format": "HH:MM:SS:FF",
    "total_hands": 127,
    "duration_minutes": 240
  }
}
```

#### 4.2.2 플레이어 데이터

```json
{
  "players": [
    {
      "player_id": "player-uuid-1",
      "name": "Player A",
      "display_name": "PLAYER A",
      "country": "KR",
      "country_flag": "flags/kr.png",
      "seat": 7,
      "initial_stack": 10000000,
      "final_stack": 12500000,
      "session_profit": 2500000,
      "statistics": {
        "hands_played": 45,
        "hands_won": 12,
        "win_rate": 26.7,
        "vpip": 25.5,
        "pfr": 18.2,
        "aggression_factor": 2.3,
        "biggest_pot_won": 3500000,
        "biggest_pot_lost": 1200000
      },
      "hand_history": [
        {
          "hand_number": 42,
          "result": "won",
          "stack_delta": 1260000,
          "hand_rank": "Full House"
        }
      ]
    }
  ]
}
```

#### 4.2.3 핸드 데이터

```json
{
  "hands": [
    {
      "hand_id": "hand-uuid-1",
      "hand_number": 42,
      "start_timecode": "01:23:45:00",
      "end_timecode": "01:25:30:15",
      "duration_frames": 3165,
      "pot_size": 1260000,
      "pot_size_bb": 7.0,
      "blinds": {
        "small_blind": 50000,
        "big_blind": 100000,
        "ante": 10000
      },
      "board": {
        "flop": ["Ah", "Kd", "Qs"],
        "flop_timecode": "01:24:00:00",
        "turn": "Jc",
        "turn_timecode": "01:24:30:00",
        "river": "Th",
        "river_timecode": "01:25:00:00"
      },
      "result": {
        "winner": "Player A",
        "winner_seat": 7,
        "hand_rank": "Full House",
        "hand_rank_number": 4,
        "is_premium": true,
        "grade": "A",
        "winning_cards": ["Ah", "Kd", "Qs", "Jc", "Th"]
      },
      "showdown_players": [
        {
          "player_name": "Player A",
          "seat": 7,
          "hole_cards": ["Ac", "Ad"],
          "hand_rank": "Full House",
          "won_amount": 1260000
        },
        {
          "player_name": "Player B",
          "seat": 3,
          "hole_cards": ["Kc", "Kh"],
          "hand_rank": "Two Pair",
          "won_amount": 0
        }
      ],
      "key_actions": [
        {
          "timecode": "01:24:45:00",
          "player": "Player A",
          "action": "ALL_IN",
          "amount": 800000,
          "highlight": true
        }
      ]
    }
  ]
}
```

#### 4.2.4 Chip Flow 데이터

```json
{
  "chip_flow": {
    "chart_config": {
      "y_axis_min": 0,
      "y_axis_max": 20000000,
      "x_axis_format": "hand_number",
      "smoothing": true
    },
    "players": {
      "Player A": {
        "color": "#FF6B6B",
        "data_points": [
          {
            "hand_number": 1,
            "timecode": "00:10:00:00",
            "stack": 10000000,
            "event": null
          },
          {
            "hand_number": 15,
            "timecode": "00:35:00:00",
            "stack": 8500000,
            "event": "lose"
          },
          {
            "hand_number": 42,
            "timecode": "01:25:30:15",
            "stack": 12500000,
            "event": "big_win"
          }
        ]
      },
      "Player B": {
        "color": "#4ECDC4",
        "data_points": [
          {
            "hand_number": 1,
            "timecode": "00:10:00:00",
            "stack": 8000000,
            "event": null
          }
        ]
      }
    },
    "highlights": [
      {
        "timecode": "01:25:30:15",
        "event_type": "double_up",
        "player": "Player A",
        "description": "Double up with Full House"
      }
    ]
  }
}
```

#### 4.2.5 하이라이트 이벤트

```json
{
  "highlights": [
    {
      "type": "premium_hand",
      "hand_number": 42,
      "timecode": "01:25:00:00",
      "duration_frames": 150,
      "alert_level": "epic",
      "data": {
        "hand_rank": "Full House",
        "player": "Player A",
        "pot_size": 1260000
      },
      "animation": {
        "style": "glow",
        "color": "#FFD700",
        "sound_cue": "premium_hand.mp3"
      }
    },
    {
      "type": "big_pot",
      "hand_number": 87,
      "timecode": "02:45:30:00",
      "duration_frames": 90,
      "alert_level": "mega",
      "data": {
        "pot_size": 5000000,
        "pot_size_bb": 50.0,
        "players_involved": ["Player A", "Player C", "Player E"]
      }
    },
    {
      "type": "elimination",
      "hand_number": 102,
      "timecode": "03:15:00:00",
      "duration_frames": 180,
      "data": {
        "eliminated": "Player F",
        "eliminator": "Player A",
        "finish_position": 7,
        "prize": 25000
      }
    }
  ]
}
```

### 4.3 After Effects 템플릿 연동

#### 4.3.1 AE 템플릿 구조

```
AE_Templates/
├── lower_third/
│   ├── player_profile.aep        # 플레이어 Lower Third
│   ├── chip_display.aep          # 스택 표시
│   └── action_callout.aep        # 액션 알림
├── graphics/
│   ├── hand_rank_display.aep     # 핸드 등급 표시
│   ├── premium_alert.aep         # 프리미엄 핸드 알림
│   └── big_pot_alert.aep         # Big Pot 경고
├── charts/
│   └── chip_flow_graph.aep       # Chip Flow 그래프
└── overlays/
    ├── tournament_status.aep     # 토너먼트 현황
    └── hand_info_box.aep         # 핸드 정보 박스
```

#### 4.3.2 AE Expression 연동

```javascript
// AE에서 JSON 데이터 읽기 (ExtendScript)
var jsonFile = new File("/path/to/export/hands.json");
jsonFile.open("r");
var jsonData = JSON.parse(jsonFile.read());
jsonFile.close();

// 텍스트 레이어에 데이터 적용
var playerName = jsonData.players[0].name;
var playerStack = jsonData.players[0].final_stack.toLocaleString();

// 소스 텍스트 설정
text.sourceText = playerName + "\n" + playerStack + " chips";
```

#### 4.3.3 Timecode 매핑

```python
def calculate_timecode(timestamp: datetime, session_start: datetime, fps: int = 30) -> str:
    """타임스탬프를 AE 타임코드로 변환"""
    delta = timestamp - session_start
    total_frames = int(delta.total_seconds() * fps)

    hours = total_frames // (3600 * fps)
    minutes = (total_frames % (3600 * fps)) // (60 * fps)
    seconds = (total_frames % (60 * fps)) // fps
    frames = total_frames % fps

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
```

---

## 5. 기술 스택

### 5.1 데이터베이스

| 컴포넌트 | 기술 | 버전 |
|----------|------|------|
| **DB 엔진** | PostgreSQL | 16+ |
| **비동기 드라이버** | asyncpg | 0.29.0+ |
| **마이그레이션** | Alembic | 1.13+ |
| **ORM (Optional)** | SQLAlchemy | 2.0+ |

### 5.2 Python 의존성 추가

```toml
[project.optional-dependencies]
db = [
    "asyncpg>=0.29.0",
    "alembic>=1.13",
]
```

### 5.3 설정 구조

```python
# src/config/settings.py

class DatabaseSettings(BaseSettings):
    """PostgreSQL 데이터베이스 설정"""

    host: str = "localhost"
    port: int = 5432
    database: str = "poker_hand_capture"
    user: str = "postgres"
    password: str = ""

    min_connections: int = 5
    max_connections: int = 20

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    model_config = SettingsConfigDict(env_prefix="DATABASE_")


class ExportSettings(BaseSettings):
    """내보내기 설정"""

    output_path: Path = Path("./output")
    frame_rate: int = 30
    timecode_format: str = "HH:MM:SS:FF"

    model_config = SettingsConfigDict(env_prefix="EXPORT_")
```

---

## 6. 구현 로드맵

### Phase 1: DB 기반 구축 (Week 1)

| 작업 | 우선순위 | 설명 |
|------|:--------:|------|
| PostgreSQL 스키마 생성 | P0 | 11개 테이블 DDL 작성 |
| asyncpg 연결 풀 구현 | P0 | connection.py |
| 기본 Repository 패턴 | P0 | 베이스 클래스 구현 |
| 설정 클래스 추가 | P0 | DatabaseSettings |

### Phase 2: 핸드 저장 (Week 2)

| 작업 | 우선순위 | 설명 |
|------|:--------:|------|
| HandRepository 구현 | P0 | CRUD 구현 |
| FusionEngine 훅 추가 | P0 | DB 저장 콜백 |
| ClipMarkerManager 연동 | P1 | DB 저장 추가 |
| hand_cards, hand_actions 저장 | P1 | 상세 데이터 저장 |

### Phase 3: 플레이어 추적 (Week 3)

| 작업 | 우선순위 | 설명 |
|------|:--------:|------|
| PlayerRepository 구현 | P0 | 이름 기반 자동 매칭 |
| player_hands 연결 | P0 | 플레이어-핸드 연결 |
| 테이블 이동 추적 | P1 | 동일 플레이어 통합 |
| 통계 계산 로직 | P1 | VPIP, PFR 등 |

### Phase 4: Chip Flow (Week 4)

| 작업 | 우선순위 | 설명 |
|------|:--------:|------|
| ChipFlowRepository 구현 | P0 | 칩 흐름 저장 |
| stack_start/end 추적 | P0 | 핸드별 스택 변화 |
| 시계열 쿼리 구현 | P1 | 그래프용 데이터 조회 |
| running_total 계산 | P1 | 누적 스택 계산 |

### Phase 5: 자막 내보내기 (Week 5)

| 작업 | 우선순위 | 설명 |
|------|:--------:|------|
| SubtitleExporter 구현 | P0 | JSON 내보내기 |
| Timecode 매핑 | P0 | 타임스탬프 → 타임코드 |
| 자막 유형별 템플릿 | P1 | 7가지 유형 구현 |
| AE 템플릿 예제 | P2 | 샘플 .aep 파일 |

---

## 7. 테스트 계획

### 7.1 단위 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| Repository CRUD | 각 Repository의 기본 CRUD | P0 |
| 플레이어 자동 매칭 | get_or_create 로직 | P0 |
| Chip Flow 계산 | stack_delta 계산 정확성 | P0 |
| Timecode 변환 | 타임코드 형식 정확성 | P1 |

### 7.2 통합 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| 핸드 저장 파이프라인 | FusionEngine → DB | P0 |
| 세션 전체 내보내기 | 127핸드 세션 내보내기 | P0 |
| 멀티테이블 플레이어 추적 | 테이블 이동 시 동일 ID | P1 |

### 7.3 성능 목표

| 지표 | 목표 |
|------|------|
| 핸드 저장 시간 | < 50ms |
| 플레이어 조회/생성 | < 10ms |
| 세션 내보내기 (100핸드) | < 5s |
| Chip Flow 쿼리 | < 100ms |

---

## 8. 핸드 분할 녹화 (Part 2)

### 8.1 워크플로우

```
RFID JSON (hand_complete 이벤트)
        │
        ▼
┌───────────────────────────────────────┐
│ HandDivider (핸드 분할기)              │
├───────────────────────────────────────┤
│ 1. 핸드 시작/종료 시간 추출            │
│    - StartDateTimeUTC                 │
│    - Duration (ISO 8601)              │
│ 2. 영상 타임코드 매핑                  │
│    - 세션 시작 기준 오프셋 계산        │
│    - FPS 기반 프레임 변환 (30fps)      │
│ 3. 클립 마커 생성                      │
│    - start_tc, end_tc                 │
│    - hand_number, table_id            │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ HandGrader (등급 분석기)               │
│ → 섹션 9 참조                          │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ EditSourceExporter (편집 원소스)       │
│ → 섹션 10 참조                         │
└───────────────────────────────────────┘
```

### 8.2 타임코드 변환 로직

```python
from datetime import datetime, timedelta

class HandDivider:
    """핸드 분할 및 타임코드 생성"""

    def __init__(self, session_start: datetime, fps: int = 30):
        self.session_start = session_start
        self.fps = fps

    def calculate_timecode(self, timestamp: datetime) -> str:
        """타임스탬프를 SMPTE 타임코드로 변환"""
        delta = timestamp - self.session_start
        total_frames = int(delta.total_seconds() * self.fps)

        hours = total_frames // (3600 * self.fps)
        minutes = (total_frames % (3600 * self.fps)) // (60 * self.fps)
        seconds = (total_frames % (60 * self.fps)) // self.fps
        frames = total_frames % self.fps

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

    def create_clip_marker(self, hand_data: dict) -> ClipMarker:
        """핸드 데이터에서 클립 마커 생성"""
        start_time = datetime.fromisoformat(hand_data['StartDateTimeUTC'])
        duration = self._parse_duration(hand_data['Duration'])
        end_time = start_time + duration

        return ClipMarker(
            hand_number=hand_data['HandNum'],
            table_id=hand_data['table_id'],
            start_tc=self.calculate_timecode(start_time),
            end_tc=self.calculate_timecode(end_time),
            duration_sec=int(duration.total_seconds())
        )

    def _parse_duration(self, iso_duration: str) -> timedelta:
        """ISO 8601 Duration 파싱 (PT2M56.2628165S)"""
        # PT2M56.2628165S -> 2분 56.26초
        import re
        match = re.match(r'PT(?:(\d+)M)?(?:([\d.]+)S)?', iso_duration)
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return timedelta(minutes=minutes, seconds=seconds)
```

---

## 9. 핸드 등급 분석 (Part 2)

### 9.1 등급 분류 기준 (PRD-0001)

> 참조: [PRD-0001: 포커 핸드 자동 캡처](./PRD-0001-poker-hand-auto-capture.md)

핸드 등급은 **3가지 조건** 중 충족 개수에 따라 결정:

| 조건 | 설명 | 체크 방식 |
|------|------|----------|
| **프리미엄 핸드** | Royal Flush, Straight Flush, Quads, Full House | `best_hand_rank <= 4` |
| **플레이 시간** | 핸드 Duration이 평균 이상 | `duration > avg_duration` |
| **보드 조합** | Three of Kind 이상 (핸드 7번부터 프리미엄 체크) | 커뮤니티 + 홀 카드 → 등급 |

### 9.2 등급 정의

| 등급 | 조건 충족 | 방송 사용 | 편집 우선순위 |
|:----:|:--------:|:--------:|:------------:|
| **A** | 3개 모두 | O | 최우선 |
| **B** | 2개 | O | 일반 |
| **C** | 1개 | X | 아카이브 |

> **B등급 이상부터 방송 사용 가능**

### 9.3 구현 코드

```python
from enum import Enum
from dataclasses import dataclass

class HandGrade(str, Enum):
    A = "A"  # 3개 조건 충족 - 최우선 편집
    B = "B"  # 2개 조건 충족 - 방송 사용 가능
    C = "C"  # 1개 조건 충족 - 아카이브

@dataclass
class GradeResult:
    grade: HandGrade
    factors: list[str]
    is_broadcast_ready: bool

class HandGrader:
    """핸드 등급 분석기"""

    PREMIUM_RANK_THRESHOLD = 4  # Full House 이하

    def __init__(self, avg_duration_sec: float = 120.0):
        self.avg_duration = avg_duration_sec

    def grade_hand(self, hand_data: dict) -> GradeResult:
        """핸드 등급 분석"""
        factors = []

        # 조건 1: 프리미엄 핸드
        if hand_data.get('best_hand_rank', 10) <= self.PREMIUM_RANK_THRESHOLD:
            factors.append("premium_hand")

        # 조건 2: 플레이 시간
        if hand_data.get('duration_sec', 0) > self.avg_duration:
            factors.append("long_duration")

        # 조건 3: 보드 조합 (핸드 7번부터)
        if hand_data.get('hand_number', 0) >= 7:
            if self._check_board_combo(hand_data):
                factors.append("board_combo")

        # 등급 결정
        factor_count = len(factors)
        if factor_count >= 3:
            grade = HandGrade.A
        elif factor_count >= 2:
            grade = HandGrade.B
        else:
            grade = HandGrade.C

        return GradeResult(
            grade=grade,
            factors=factors,
            is_broadcast_ready=(grade in [HandGrade.A, HandGrade.B])
        )

    def _check_board_combo(self, hand_data: dict) -> bool:
        """보드 + 홀 카드 조합이 Three of Kind 이상인지 체크"""
        # phevaluator로 7장 평가
        # rank 1610 이하 = Three of Kind 이상
        rank_value = hand_data.get('hand_rank_value', 7462)
        return rank_value <= 2467  # Three of Kind 이상
```

---

## 10. 편집 원소스 출력 (Part 2)

### 10.1 출력 형식

| 형식 | 대상 소프트웨어 | 용도 |
|------|----------------|------|
| **EDL** (CMX3600) | DaVinci Resolve, Premiere Pro | 편집점 타임코드 |
| **FCPXML** | Final Cut Pro | 마커 및 노트 |
| **JSON** | 범용 | 메타데이터 |

### 10.2 EDL 출력 예시

```
TITLE: Feature Table A - Day 1
FCM: NON-DROP FRAME

001  AX       V     C        01:23:45:00 01:25:30:15 01:23:45:00 01:25:30:15
* FROM CLIP NAME: Table_A_Hand_042
* COMMENT: Full House - Grade A
* MARKER: PREMIUM HAND

002  AX       V     C        01:30:00:00 01:32:15:20 01:30:00:00 01:32:15:20
* FROM CLIP NAME: Table_A_Hand_043
* COMMENT: Straight - Grade B
```

### 10.3 FCPXML 출력 예시

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
  <resources>
    <format id="r1" name="FFVideoFormat1080p30"
            frameDuration="1001/30000s" width="1920" height="1080"/>
  </resources>
  <library>
    <event name="Feature Table A - Day 1">
      <project name="Graded Hands">
        <sequence format="r1">
          <spine>
            <clip name="Hand 042" offset="0s" duration="105s"
                  start="01:23:45:00" tcFormat="NDF">
              <note>Full House - Grade A</note>
              <keyword start="0s" duration="105s" value="premium,grade_a"/>
            </clip>
            <clip name="Hand 043" offset="105s" duration="135s"
                  start="01:30:00:00" tcFormat="NDF">
              <note>Straight - Grade B</note>
              <keyword start="0s" duration="135s" value="grade_b"/>
            </clip>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
```

### 10.4 JSON 메타데이터 출력 예시

```json
{
  "export_info": {
    "table_id": "feature_a",
    "session_id": "session-uuid",
    "exported_at": "2025-12-25T18:00:00Z",
    "total_hands": 127,
    "graded_hands": {
      "A": 15,
      "B": 42,
      "C": 70
    }
  },
  "hands": [
    {
      "hand_number": 42,
      "start_tc": "01:23:45:00",
      "end_tc": "01:25:30:15",
      "duration_sec": 105,
      "grade": "A",
      "grade_factors": ["premium_hand", "long_duration", "board_combo"],
      "hand_rank": "Full House",
      "hand_rank_number": 4,
      "pot_size": 1260000,
      "winner": "Player A",
      "showdown": true,
      "players_showdown": [
        {
          "name": "Player A",
          "seat": 7,
          "hole_cards": ["Ac", "Ad"],
          "won_amount": 1260000
        }
      ]
    },
    {
      "hand_number": 43,
      "start_tc": "01:30:00:00",
      "end_tc": "01:32:15:20",
      "duration_sec": 135,
      "grade": "B",
      "grade_factors": ["long_duration", "board_combo"],
      "hand_rank": "Straight",
      "hand_rank_number": 6,
      "pot_size": 850000,
      "winner": "Player C",
      "showdown": true
    }
  ]
}
```

### 10.5 EditSourceExporter 구현

```python
from pathlib import Path
from datetime import datetime

class EditSourceExporter:
    """편집 원소스 내보내기"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_edl(self, hands: list[dict], filename: str) -> Path:
        """EDL 형식 내보내기"""
        edl_path = self.output_dir / f"{filename}.edl"

        lines = [
            f"TITLE: {filename}",
            "FCM: NON-DROP FRAME",
            ""
        ]

        for i, hand in enumerate(hands, 1):
            lines.extend([
                f"{i:03d}  AX       V     C        "
                f"{hand['start_tc']} {hand['end_tc']} "
                f"{hand['start_tc']} {hand['end_tc']}",
                f"* FROM CLIP NAME: Hand_{hand['hand_number']:03d}",
                f"* COMMENT: {hand['hand_rank']} - Grade {hand['grade']}",
                f"* MARKER: {'PREMIUM HAND' if hand['grade'] == 'A' else ''}"
            ])

        edl_path.write_text("\n".join(lines))
        return edl_path

    def export_fcpxml(self, hands: list[dict], filename: str) -> Path:
        """FCPXML 형식 내보내기"""
        # XML 생성 로직
        pass

    def export_json(self, hands: list[dict], filename: str) -> Path:
        """JSON 메타데이터 내보내기"""
        import json

        json_path = self.output_dir / f"{filename}.json"

        export_data = {
            "export_info": {
                "exported_at": datetime.now().isoformat(),
                "total_hands": len(hands),
                "graded_hands": {
                    "A": sum(1 for h in hands if h['grade'] == 'A'),
                    "B": sum(1 for h in hands if h['grade'] == 'B'),
                    "C": sum(1 for h in hands if h['grade'] == 'C'),
                }
            },
            "hands": hands
        }

        json_path.write_text(json.dumps(export_data, indent=2, ensure_ascii=False))
        return json_path

    def export_all(self, hands: list[dict], filename: str) -> dict[str, Path]:
        """모든 형식으로 내보내기"""
        return {
            "edl": self.export_edl(hands, filename),
            "fcpxml": self.export_fcpxml(hands, filename),
            "json": self.export_json(hands, filename)
        }
```

---

## 11. 파일 구조

### 11.1 신규 생성 파일 (10개)

**Part 1: DB + 자막**
```
src/
├── database/
│   ├── __init__.py
│   ├── connection.py          # asyncpg 연결 풀
│   ├── models.py              # DB 모델 정의
│   └── repository.py          # Repository 패턴
│       ├── BaseRepository
│       ├── SessionRepository
│       ├── TableRepository
│       ├── PlayerRepository
│       ├── HandRepository
│       ├── PlayerHandRepository
│       ├── ChipFlowRepository
│       └── ClipMarkerRepository
│
├── export/
│   ├── __init__.py
│   ├── subtitle_exporter.py   # AE용 JSON 내보내기
│   └── chip_flow_exporter.py  # Chip Flow 데이터
```

**Part 2: 핸드 분할 + 등급**
```
src/
├── grading/
│   ├── __init__.py
│   ├── hand_divider.py        # 핸드 분할 (클립 마커 생성)
│   └── hand_grader.py         # 등급 분석 (A/B/C)
│
├── export/
│   └── edit_source_exporter.py # EDL/FCPXML/JSON 내보내기
```

**공통**
```
scripts/
└── init_db.sql                # PostgreSQL 스키마 DDL (13개 테이블)
```

### 11.2 수정 파일 (5개)

| 파일 | 수정 내용 |
|------|----------|
| `src/models/hand.py` | PlayerInfo 확장 (photo_url, bracelets 등) |
| `src/fusion/engine.py` | DB 저장 훅 + 등급 분석 연동 |
| `src/config/settings.py` | DatabaseSettings, GradingSettings 추가 |
| `src/output/clip_marker.py` | 등급 필드 (grade, grade_factors) 추가 |
| `pyproject.toml` | asyncpg, alembic 의존성 추가 |

---

## 부록

### A. PostgreSQL 스키마 DDL

```sql
-- scripts/init_db.sql

-- 확장 기능 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- sessions 테이블
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    venue VARCHAR(255),
    type VARCHAR(50),
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    meta JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- tables 테이블
CREATE TABLE tables (
    table_id VARCHAR(50) PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id),
    location VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    blind_sb INTEGER DEFAULT 0,
    blind_bb INTEGER DEFAULT 0,
    ante INTEGER DEFAULT 0,
    max_seats INTEGER DEFAULT 10,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- players 테이블 (WSOP 통계 포함)
CREATE TABLE players (
    player_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(100),
    country CHAR(2),
    photo_url VARCHAR(500),
    notes TEXT,
    -- WSOP 통계 (Player Intro Card용)
    bracelets INTEGER DEFAULT 0,
    total_earnings BIGINT DEFAULT 0,
    final_tables INTEGER DEFAULT 0,
    meta JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- hands 테이블
CREATE TABLE hands (
    hand_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    table_id VARCHAR(50) REFERENCES tables(table_id),
    hand_number INTEGER NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_sec INTEGER,
    pot_size BIGINT DEFAULT 0,
    winner_player_id UUID REFERENCES players(player_id),
    source VARCHAR(20) NOT NULL,
    confidence DECIMAL(3,2) DEFAULT 1.0,
    cross_validated BOOLEAN DEFAULT FALSE,
    requires_review BOOLEAN DEFAULT FALSE,
    best_hand_rank INTEGER,
    is_premium BOOLEAN DEFAULT FALSE,
    grade CHAR(1),
    grade_factors JSONB,
    meta JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(table_id, hand_number)
);

-- player_hands 테이블
CREATE TABLE player_hands (
    ph_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hand_id UUID REFERENCES hands(hand_id) ON DELETE CASCADE,
    player_id UUID REFERENCES players(player_id),
    seat INTEGER NOT NULL,
    position VARCHAR(10),
    stack_start BIGINT NOT NULL,
    stack_end BIGINT NOT NULL,
    stack_delta BIGINT GENERATED ALWAYS AS (stack_end - stack_start) STORED,
    hole_cards CHAR(4),
    hand_rank INTEGER,
    hand_rank_value INTEGER,
    is_winner BOOLEAN DEFAULT FALSE,
    won_amount BIGINT DEFAULT 0,
    vpip BOOLEAN DEFAULT FALSE,
    pfr BOOLEAN DEFAULT FALSE,
    went_showdown BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(hand_id, seat)
);

-- hand_cards 테이블
CREATE TABLE hand_cards (
    card_id SERIAL PRIMARY KEY,
    hand_id UUID REFERENCES hands(hand_id) ON DELETE CASCADE,
    card_rank CHAR(2) NOT NULL,
    card_suit CHAR(1) NOT NULL,
    card_type VARCHAR(20) NOT NULL,
    seat INTEGER,
    deal_order INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- hand_actions 테이블
CREATE TABLE hand_actions (
    action_id SERIAL PRIMARY KEY,
    hand_id UUID REFERENCES hands(hand_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    player_id UUID REFERENCES players(player_id),
    street VARCHAR(10) NOT NULL,
    action VARCHAR(20) NOT NULL,
    amount BIGINT DEFAULT 0,
    pot_after BIGINT,
    action_seq INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- chip_flow 테이블
CREATE TABLE chip_flow (
    flow_id SERIAL PRIMARY KEY,
    ph_id UUID REFERENCES player_hands(ph_id) ON DELETE CASCADE,
    player_id UUID REFERENCES players(player_id),
    hand_id UUID REFERENCES hands(hand_id) ON DELETE CASCADE,
    delta BIGINT NOT NULL,
    reason VARCHAR(50),
    running_total BIGINT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- clip_markers 테이블
CREATE TABLE clip_markers (
    marker_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hand_id UUID REFERENCES hands(hand_id) ON DELETE CASCADE,
    table_id VARCHAR(50),
    hand_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_sec INTEGER,
    hand_rank VARCHAR(50),
    is_premium BOOLEAN DEFAULT FALSE,
    grade CHAR(1),
    notes TEXT,
    exported BOOLEAN DEFAULT FALSE,
    export_format VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ai_results 테이블
CREATE TABLE ai_results (
    ai_id SERIAL PRIMARY KEY,
    hand_id UUID REFERENCES hands(hand_id) ON DELETE CASCADE,
    table_id VARCHAR(50),
    detected_event VARCHAR(50),
    detected_cards JSONB,
    hand_rank INTEGER,
    confidence DECIMAL(3,2),
    context TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- subtitle_data 테이블
CREATE TABLE subtitle_data (
    sub_id SERIAL PRIMARY KEY,
    hand_id UUID REFERENCES hands(hand_id) ON DELETE SET NULL,
    player_id UUID REFERENCES players(player_id),
    table_id VARCHAR(50),
    type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    timecode_start VARCHAR(20),
    timecode_end VARCHAR(20),
    style VARCHAR(50) DEFAULT 'default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- WSOP PRD 자막 지원용 추가 테이블 (3개)
-- ============================================

-- tournament_info 테이블 (Tournament Info, Payouts 자막용)
CREATE TABLE tournament_info (
    tournament_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(session_id),
    name VARCHAR(255) NOT NULL,
    buy_in INTEGER DEFAULT 0,
    prize_pool BIGINT DEFAULT 0,
    entries INTEGER DEFAULT 0,
    remaining INTEGER DEFAULT 0,
    places_paid INTEGER DEFAULT 0,
    bubble_line INTEGER DEFAULT 0,
    is_itm BOOLEAN DEFAULT FALSE,
    payouts JSONB DEFAULT '[]',              -- [{"position": 1, "amount": 1000000}, ...]
    current_level INTEGER DEFAULT 1,
    meta JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- blind_levels 테이블 (Blind Level 자막용)
CREATE TABLE blind_levels (
    level_id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id),
    level INTEGER NOT NULL,
    small_blind INTEGER NOT NULL,
    big_blind INTEGER NOT NULL,
    ante INTEGER DEFAULT 0,
    duration_minutes INTEGER DEFAULT 60,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- player_stats 테이블 (VPIP/PFR Stats 자막용 캐시)
CREATE TABLE player_stats (
    stat_id SERIAL PRIMARY KEY,
    player_id UUID REFERENCES players(player_id),
    session_id UUID REFERENCES sessions(session_id),
    table_id VARCHAR(50),
    hands_played INTEGER DEFAULT 0,
    hands_won INTEGER DEFAULT 0,
    vpip_count INTEGER DEFAULT 0,            -- VPIP 발생 횟수
    vpip_pct DECIMAL(5,2) DEFAULT 0.0,       -- VPIP 백분율
    pfr_count INTEGER DEFAULT 0,             -- PFR 발생 횟수
    pfr_pct DECIMAL(5,2) DEFAULT 0.0,        -- PFR 백분율
    aggression_factor DECIMAL(5,2) DEFAULT 0.0,
    wtsd_pct DECIMAL(5,2) DEFAULT 0.0,       -- Went To ShowDown
    current_rank INTEGER,                     -- 현재 순위
    rank_change INTEGER DEFAULT 0,            -- 순위 변동 (Leaderboard용)
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(player_id, session_id, table_id)
);

-- 인덱스 생성
CREATE INDEX idx_tables_session ON tables(session_id);
CREATE INDEX idx_hands_table ON hands(table_id, hand_number DESC);
CREATE INDEX idx_hands_time ON hands(start_time DESC);
CREATE INDEX idx_hands_grade ON hands(grade) WHERE grade IN ('A', 'B');
CREATE INDEX idx_hands_premium ON hands(is_premium) WHERE is_premium = TRUE;
CREATE INDEX idx_player_hands_player ON player_hands(player_id);
CREATE INDEX idx_player_hands_hand ON player_hands(hand_id);
CREATE INDEX idx_player_hands_winner ON player_hands(is_winner) WHERE is_winner = TRUE;
CREATE INDEX idx_hand_cards_hand ON hand_cards(hand_id);
CREATE INDEX idx_hand_actions_hand ON hand_actions(hand_id, action_seq);
CREATE INDEX idx_chip_flow_player ON chip_flow(player_id, timestamp DESC);
CREATE INDEX idx_chip_flow_hand ON chip_flow(hand_id);
CREATE INDEX idx_clip_markers_grade ON clip_markers(grade) WHERE grade IN ('A', 'B');
CREATE INDEX idx_clip_markers_premium ON clip_markers(is_premium) WHERE is_premium = TRUE;
CREATE INDEX idx_ai_results_hand ON ai_results(hand_id);
CREATE INDEX idx_subtitle_data_type ON subtitle_data(type);
CREATE INDEX idx_subtitle_data_player ON subtitle_data(player_id);
CREATE INDEX idx_players_name ON players(name);
-- 추가 테이블 인덱스
CREATE INDEX idx_tournament_info_session ON tournament_info(session_id);
CREATE INDEX idx_blind_levels_session ON blind_levels(session_id);
CREATE INDEX idx_blind_levels_current ON blind_levels(is_current) WHERE is_current = TRUE;
CREATE INDEX idx_player_stats_player ON player_stats(player_id);
CREATE INDEX idx_player_stats_session ON player_stats(session_id);
```

### B. Metabase 시각화 대시보드

> 참조: [dean.md 분석 결과](../../docs/dean.md)

#### B.1 대시보드 개요

Metabase를 활용하여 실시간 포커 데이터 시각화 대시보드를 구성합니다.

**설치 (Synology NAS Container Manager)**:
```bash
# 레지스트리에서 metabase/metabase 다운로드 후
# 로컬 포트 3000:3000 설정
http://<NAS_IP>:3000
```

#### B.2 핵심 패널 구성 (4개)

| 패널 | 차트 타입 | 데이터 소스 | 용도 |
|------|----------|------------|------|
| **Cumulative Winnings** | Line Chart | `chip_flow` | 플레이어별 누적 수익 추이 |
| **VPIP/PFR Comparison** | Grouped Bar | `player_stats` | 상위 5명 플레이어 성향 비교 |
| **Pot Size Distribution** | Histogram + KDE | `hands` | 팟 사이즈 분포 분석 |
| **Player Type Breakdown** | Pie Chart | `player_stats` | 플레이어 유형 분포 (Fish/TAG/LAG) |

#### B.3 SQL 쿼리 예시

**1. Cumulative Winnings (Hero)**

```sql
SELECT
    h.hand_number AS "Hand",
    cf.running_total AS "Stack",
    cf.timestamp
FROM chip_flow cf
JOIN hands h ON cf.hand_id = h.hand_id
JOIN players p ON cf.player_id = p.player_id
WHERE p.name = {{player_name}}
ORDER BY h.hand_number;
```

**2. Top 5 Players VPIP/PFR**

```sql
SELECT
    p.name AS "Player",
    ps.vpip_pct AS "VPIP",
    ps.pfr_pct AS "PFR",
    ps.hands_played
FROM player_stats ps
JOIN players p ON ps.player_id = p.player_id
WHERE ps.hands_played > 10
ORDER BY ps.vpip_pct DESC
LIMIT 5;
```

**3. Pot Size Distribution**

```sql
SELECT
    pot_size AS "Pot",
    COUNT(*) AS "Count"
FROM hands
WHERE pot_size > 0
GROUP BY pot_size
ORDER BY pot_size;
```

**4. Fish Detection (타겟 플레이어)**

```sql
SELECT
    p.name AS "Player",
    ps.vpip_pct AS "VPIP",
    ps.pfr_pct AS "PFR",
    CASE
        WHEN ps.vpip_pct > 35 AND ps.pfr_pct < 15 THEN 'FISH'
        WHEN ps.vpip_pct > 40 AND ps.pfr_pct > 30 THEN 'MANIAC'
        WHEN ps.vpip_pct BETWEEN 25 AND 35 THEN 'LAG'
        ELSE 'TAG/NIT'
    END AS "Type"
FROM player_stats ps
JOIN players p ON ps.player_id = p.player_id
WHERE ps.hands_played > 20
ORDER BY ps.vpip_pct DESC;
```

#### B.4 대시보드 레이아웃

```
┌─────────────────────────────────────────────────────────────┐
│                 Poker Analytics Dashboard                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Cumulative Winnings (Hero: {{player_name}})             │ │
│  │ ▄▄█▄▄▄▄▄███▄▄▄██████▄▄▄▄▄▄▄▄▄████████████▄▄▄           │ │
│  │ ────────────────────────────────────────────────────── │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │ Top 5 VPIP/PFR           │  │ Pot Size Distribution    │ │
│  │ ▓▓▓▓ VPIP                │  │ ▓▓▓▓▓                    │ │
│  │ ▒▒▒▒ PFR                 │  │ ▓▓▓▓▓▓▓▓                 │ │
│  │                          │  │ ▓▓▓▓▓▓▓▓▓▓▓              │ │
│  │ Player A ████████ ▒▒▒▒  │  │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓           │ │
│  │ Player B ██████ ▒▒▒     │  │ ▓▓▓▓▓▓▓▓▓                │ │
│  │ Player C █████ ▒▒▒      │  │ ▓▓▓▓▓                    │ │
│  └──────────────────────────┘  └──────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### B.5 NAS 배포 연동

Metabase는 `poker-capture` Docker Compose 프로젝트와 동일 네트워크에서 실행:

```yaml
# deploy/docker-compose.yml (Metabase 추가)
services:
  metabase:
    image: metabase/metabase:latest
    container_name: poker-metabase
    profiles:
      - analytics
    ports:
      - "3000:3000"
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: poker_hands
      MB_DB_PORT: 5432
      MB_DB_USER: poker
      MB_DB_PASS: ${DB_PASSWORD}
      MB_DB_HOST: poker-db
    depends_on:
      - poker-db
    networks:
      - poker-network
    restart: unless-stopped
```

**실행**:
```bash
docker-compose --profile analytics up -d
```

---

### C. 참조 자료

- [PRD-0001: 포커 핸드 자동 캡처](./PRD-0001-poker-hand-auto-capture.md)
- [PRD-0002: Primary Layer - GFX RFID](./PRD-0002-primary-gfx-rfid.md)
- [PostgreSQL 공식 문서](https://www.postgresql.org/docs/)
- [asyncpg 문서](https://magicstack.github.io/asyncpg/)
- [Metabase 문서](https://www.metabase.com/docs/latest/)
- [Adobe After Effects Scripting Guide](https://ae-scripting.docsforadobe.dev/)
