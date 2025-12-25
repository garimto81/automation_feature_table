# PRD-0002: Primary Layer - GFX RFID

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0002 |
| **제목** | Primary Layer - PokerGFX RFID 기술 상세 |
| **버전** | 1.0 |
| **작성일** | 2025-12-24 |
| **상태** | Draft |
| **상위 문서** | [PRD-0001](./PRD-0001-poker-hand-auto-capture.md) |
| **일정** | Phase 1 (01/06 ~ 01/19) |

---

## 1. 개요

### 1.1 역할

Primary Layer는 PokerGFX RFID 시스템에서 JSON 데이터를 수신하여 핸드를 분류하는 핵심 계층입니다.

| 항목 | 값 |
|------|-----|
| **신뢰도** | 99.9% (RFID 기반 정확한 데이터) |
| **지연시간** | < 100ms |
| **용도** | 핸드 데이터의 정확한 소스 |

### 1.2 데이터 흐름

```
PokerGFX RFID → JSON Export → Primary Processor → HandResult
```

---

## 2. PokerGFX JSON API

### 2.1 연결 방식

| 방식 | 설명 |
|------|------|
| **파일 감시** | JSON 파일 출력 후 파일 시스템 감시 |
| **WebSocket** | 실시간 이벤트 스트림 (확인 필요) |

### 2.2 소프트웨어 버전

- **PokerGFX 3.2** 이상
- 엔터프라이즈/프로 라이선스 필요

---

## 3. 데이터 스키마

### 3.1 최상위 구조

```json
{
  "CreatedDateTimeUTC": "2025-10-16T08:25:17.0907267Z",
  "EventTitle": "",
  "Hands": [...],
  "ID": 638961999170907267,
  "Payouts": [0,0,0,0,0,0,0,0,0,0],
  "SoftwareVersion": "PokerGFX 3.2",
  "Type": "FEATURE_TABLE"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `CreatedDateTimeUTC` | string | 세션 생성 시간 (ISO 8601) |
| `EventTitle` | string | 이벤트 제목 |
| `Hands` | array | 핸드 객체 배열 |
| `ID` | number | 세션 고유 ID |
| `Payouts` | array | 페이아웃 배열 |
| `SoftwareVersion` | string | PokerGFX 버전 |
| `Type` | string | 테이블 타입 |

### 3.2 Hand 객체

```json
{
  "HandNum": 2,
  "GameVariant": "HOLDEM",
  "GameClass": "FLOP",
  "BetStructure": "NOLIMIT",
  "Duration": "PT2M56.2628165S",
  "StartDateTimeUTC": "2025-10-16T08:28:43.2539856Z",
  "NumBoards": 1,
  "RunItNumTimes": 1,
  "Players": [...],
  "Events": [...],
  "FlopDrawBlinds": {...}
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `HandNum` | number | 핸드 번호 |
| `GameVariant` | string | 게임 종류 (HOLDEM, OMAHA) |
| `GameClass` | string | 게임 클래스 (FLOP, DRAW) |
| `BetStructure` | string | 베팅 구조 (NOLIMIT, POTLIMIT, LIMIT) |
| `Duration` | string | 핸드 진행 시간 (ISO 8601 Duration) |
| `StartDateTimeUTC` | string | 핸드 시작 시간 |
| `NumBoards` | number | 보드 수 |
| `RunItNumTimes` | number | Run It 횟수 |
| `Players` | array | 플레이어 배열 |
| `Events` | array | 이벤트 배열 |
| `FlopDrawBlinds` | object | 블라인드 정보 |

### 3.3 Player 객체

```json
{
  "PlayerNum": 7,
  "Name": "J",
  "LongName": "",
  "StartStackAmt": 9000,
  "EndStackAmt": 9000,
  "CumulativeWinningsAmt": 0,
  "HoleCards": ["7s", "7h"],
  "SittingOut": false,
  "EliminationRank": -1,
  "VPIPPercent": 0,
  "PreFlopRaisePercent": 0,
  "AggressionFrequencyPercent": 0,
  "WentToShowDownPercent": 0
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `PlayerNum` | number | 시트 번호 |
| `Name` | string | 플레이어 이름 |
| `LongName` | string | 플레이어 전체 이름 |
| `StartStackAmt` | number | 시작 스택 |
| `EndStackAmt` | number | 종료 스택 |
| `CumulativeWinningsAmt` | number | 누적 수익 |
| `HoleCards` | array | 홀 카드 (2장) |
| `SittingOut` | boolean | 자리 비움 여부 |
| `EliminationRank` | number | 탈락 순위 (-1: 미탈락) |
| `VPIPPercent` | number | VPIP 통계 |
| `PreFlopRaisePercent` | number | PFR 통계 |
| `AggressionFrequencyPercent` | number | AF 통계 |
| `WentToShowDownPercent` | number | WTSD 통계 |

### 3.4 Event 객체

```json
{
  "EventType": "CALL",
  "PlayerNum": 5,
  "BetAmt": 180000,
  "Pot": 370000,
  "BoardCards": null,
  "BoardNum": 0,
  "DateTimeUTC": null,
  "NumCardsDrawn": 0
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `EventType` | string | 이벤트 타입 |
| `PlayerNum` | number | 플레이어 번호 |
| `BetAmt` | number | 베팅 금액 |
| `Pot` | number | 현재 팟 |
| `BoardCards` | array/null | 보드 카드 (BOARD CARD 이벤트 시) |
| `BoardNum` | number | 보드 번호 |
| `DateTimeUTC` | string/null | 이벤트 시간 |
| `NumCardsDrawn` | number | 드로우한 카드 수 |

### 3.5 FlopDrawBlinds 객체

```json
{
  "ButtonPlayerNum": 2,
  "SmallBlindPlayerNum": 3,
  "SmallBlindAmt": 5000,
  "BigBlindPlayerNum": 4,
  "BigBlindAmt": 180000,
  "AnteType": "BB_ANTE_BB1ST",
  "BlindLevel": 0
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ButtonPlayerNum` | number | 버튼 위치 |
| `SmallBlindPlayerNum` | number | SB 위치 |
| `SmallBlindAmt` | number | SB 금액 |
| `BigBlindPlayerNum` | number | BB 위치 |
| `BigBlindAmt` | number | BB 금액 |
| `AnteType` | string | 앤티 타입 |
| `BlindLevel` | number | 블라인드 레벨 |

---

## 4. 카드 형식

### 4.1 표기법

| 구분 | 형식 | 예시 |
|------|------|------|
| **Rank** | 2-9, 10, j, q, k, a | j, q, k, a (소문자) |
| **Suit** | d, h, s, c | d=다이아, h=하트, s=스페이드, c=클럽 |
| **카드** | `<rank><suit>` | 7s, jd, as, kc |
| **홀 카드** | `["<card1>", "<card2>"]` | ["7s", "7h"] |

### 4.2 phevaluator 변환

PokerGFX 형식 → phevaluator 형식:

| PokerGFX | phevaluator | 설명 |
|----------|-------------|------|
| `as` | `As` | Ace of Spades |
| `kh` | `Kh` | King of Hearts |
| `10d` | `Td` | Ten of Diamonds |
| `jc` | `Jc` | Jack of Clubs |

```python
def convert_card(pokergfx_card: str) -> str:
    """PokerGFX 카드 형식을 phevaluator 형식으로 변환"""
    rank = pokergfx_card[:-1].upper()
    suit = pokergfx_card[-1].lower()

    # 10 → T 변환
    if rank == '10':
        rank = 'T'

    return f"{rank}{suit}"
```

---

## 5. 이벤트 타입

| EventType | 설명 | 필수 필드 |
|-----------|------|----------|
| `FOLD` | 폴드 | PlayerNum |
| `CALL` | 콜 | PlayerNum, BetAmt, Pot |
| `CHECK` | 체크 | PlayerNum, Pot |
| `RAISE` | 레이즈 | PlayerNum, BetAmt, Pot |
| `BET` | 베팅 | PlayerNum, BetAmt, Pot |
| `BOARD CARD` | 보드 카드 공개 | BoardCards, BoardNum |
| `ALL_IN` | 올인 | PlayerNum, BetAmt, Pot |
| `SHOWDOWN` | 쇼다운 | - |

### 5.1 이벤트 순서

```
PREFLOP: FOLD/CALL/RAISE/ALL_IN
    ↓
BOARD CARD (Flop - 3장)
    ↓
FLOP: CHECK/BET/CALL/RAISE/FOLD/ALL_IN
    ↓
BOARD CARD (Turn - 1장)
    ↓
TURN: CHECK/BET/CALL/RAISE/FOLD/ALL_IN
    ↓
BOARD CARD (River - 1장)
    ↓
RIVER: CHECK/BET/CALL/RAISE/FOLD/ALL_IN
    ↓
SHOWDOWN (선택적)
```

---

## 6. 핸드 분류 엔진

### 6.1 phevaluator 라이브러리

- **저장소**: https://github.com/HenryRLee/PokerHandEvaluator
- **Python 패키지**: `phevaluator`
- **성능**: 7장 평가 ~0.1μs

### 6.2 핸드 등급

| 등급 | 핸드 | phevaluator 범위 |
|:----:|------|------------------|
| 1 | Royal Flush | 1 |
| 2 | Straight Flush | 2-10 |
| 3 | Four of a Kind | 11-166 |
| 4 | Full House | 167-322 |
| 5 | Flush | 323-1599 |
| 6 | Straight | 1600-1609 |
| 7 | Three of a Kind | 1610-2467 |
| 8 | Two Pair | 2468-3325 |
| 9 | One Pair | 3326-6185 |
| 10 | High Card | 6186-7462 |

### 6.3 코드 구현

```python
from phevaluator import evaluate_cards
from dataclasses import dataclass
from typing import Optional
from enum import IntEnum


class HandRank(IntEnum):
    """핸드 등급 열거형"""
    ROYAL_FLUSH = 1
    STRAIGHT_FLUSH = 2
    FOUR_OF_A_KIND = 3
    FULL_HOUSE = 4
    FLUSH = 5
    STRAIGHT = 6
    THREE_OF_A_KIND = 7
    TWO_PAIR = 8
    ONE_PAIR = 9
    HIGH_CARD = 10


@dataclass
class HandResult:
    """Primary Layer 핸드 결과"""
    hand_num: int
    player_name: str
    hole_cards: list[str]
    community_cards: list[str]
    rank_value: int
    rank_name: str
    rank_category: HandRank
    is_premium: bool  # 등급 1-4


class PokerGFXProcessor:
    """PokerGFX JSON 데이터 기반 핸드 분류 엔진"""

    RANK_THRESHOLDS = [
        (1, 1, HandRank.ROYAL_FLUSH),
        (2, 10, HandRank.STRAIGHT_FLUSH),
        (11, 166, HandRank.FOUR_OF_A_KIND),
        (167, 322, HandRank.FULL_HOUSE),
        (323, 1599, HandRank.FLUSH),
        (1600, 1609, HandRank.STRAIGHT),
        (1610, 2467, HandRank.THREE_OF_A_KIND),
        (2468, 3325, HandRank.TWO_PAIR),
        (3326, 6185, HandRank.ONE_PAIR),
        (6186, 7462, HandRank.HIGH_CARD),
    ]

    RANK_NAMES = {
        HandRank.ROYAL_FLUSH: "Royal Flush",
        HandRank.STRAIGHT_FLUSH: "Straight Flush",
        HandRank.FOUR_OF_A_KIND: "Four of a Kind",
        HandRank.FULL_HOUSE: "Full House",
        HandRank.FLUSH: "Flush",
        HandRank.STRAIGHT: "Straight",
        HandRank.THREE_OF_A_KIND: "Three of a Kind",
        HandRank.TWO_PAIR: "Two Pair",
        HandRank.ONE_PAIR: "One Pair",
        HandRank.HIGH_CARD: "High Card",
    }

    def convert_card(self, pokergfx_card: str) -> str:
        """PokerGFX 카드 형식을 phevaluator 형식으로 변환"""
        rank = pokergfx_card[:-1].upper()
        suit = pokergfx_card[-1].lower()

        if rank == '10':
            rank = 'T'

        return f"{rank}{suit}"

    def get_rank_category(self, rank_value: int) -> HandRank:
        """phevaluator 값을 HandRank로 변환"""
        for min_val, max_val, category in self.RANK_THRESHOLDS:
            if min_val <= rank_value <= max_val:
                return category
        return HandRank.HIGH_CARD

    def extract_community_cards(self, events: list[dict]) -> list[str]:
        """이벤트에서 커뮤니티 카드 추출"""
        community_cards = []
        for event in events:
            if event.get('EventType') == 'BOARD CARD':
                board_cards = event.get('BoardCards', [])
                if board_cards:
                    community_cards.extend(board_cards)
        return community_cards

    def process_hand(self, hand_data: dict) -> list[HandResult]:
        """단일 핸드 처리"""
        results = []
        hand_num = hand_data.get('HandNum', 0)

        # 커뮤니티 카드 추출
        community_cards = self.extract_community_cards(
            hand_data.get('Events', [])
        )

        # 각 플레이어 처리
        for player in hand_data.get('Players', []):
            hole_cards = player.get('HoleCards', [])

            if not hole_cards or len(hole_cards) < 2:
                continue

            if not community_cards or len(community_cards) < 3:
                continue

            # 카드 변환
            converted_hole = [self.convert_card(c) for c in hole_cards]
            converted_community = [self.convert_card(c) for c in community_cards]

            # 7장 평가 (홀 카드 2장 + 커뮤니티 5장)
            all_cards = converted_hole + converted_community[:5]

            if len(all_cards) >= 5:
                rank_value = evaluate_cards(*all_cards[:7])
                rank_category = self.get_rank_category(rank_value)

                result = HandResult(
                    hand_num=hand_num,
                    player_name=player.get('Name', ''),
                    hole_cards=hole_cards,
                    community_cards=community_cards,
                    rank_value=rank_value,
                    rank_name=self.RANK_NAMES[rank_category],
                    rank_category=rank_category,
                    is_premium=(rank_category.value <= 4)
                )
                results.append(result)

        return results

    def process_session(self, session_data: dict) -> list[HandResult]:
        """전체 세션 처리"""
        all_results = []

        for hand in session_data.get('Hands', []):
            results = self.process_hand(hand)
            all_results.extend(results)

        return all_results
```

---

## 7. 기술 스택

| 컴포넌트 | 기술 | 버전 |
|----------|------|------|
| **언어** | Python | 3.11+ |
| **핸드 평가** | phevaluator | 0.5.0+ |
| **JSON 파싱** | 내장 json | - |
| **데이터 모델** | Pydantic | 2.0+ |
| **비동기** | asyncio | 내장 |
| **파일 감시** | watchdog | 3.0+ |

### 7.1 의존성

```toml
[project]
dependencies = [
    "phevaluator>=0.5.0",
    "pydantic>=2.0",
    "watchdog>=3.0",
]
```

---

## 8. 테스트 계획

### 8.1 단위 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| 카드 변환 | PokerGFX → phevaluator | P0 |
| 핸드 평가 | 10가지 핸드 등급 검증 | P0 |
| JSON 파싱 | 스키마 검증 | P0 |
| 이벤트 추출 | 커뮤니티 카드 추출 | P1 |

### 8.2 통합 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| 세션 처리 | 전체 세션 JSON 처리 | P0 |
| 실시간 처리 | 파일 감시 + 처리 | P1 |
| 멀티테이블 | 동시 처리 테스트 | P1 |

### 8.3 성능 목표

| 지표 | 목표 |
|------|------|
| 핸드 처리 시간 | < 10ms |
| 메모리 사용량 | < 100MB (세션당) |
| JSON 파싱 시간 | < 1ms |

---

## 부록

### A. 샘플 JSON 파일

테스트용 샘플 파일: `tests/fixtures/pokergfx_sample.json`

### B. 참조 자료

- [PokerGFX 공식](https://www.pokergfx.io/)
- [phevaluator GitHub](https://github.com/HenryRLee/PokerHandEvaluator)
