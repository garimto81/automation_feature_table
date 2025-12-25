# PRD-0004: Fusion Engine

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0004 |
| **제목** | Fusion Engine 기술 상세 |
| **버전** | 1.0 |
| **작성일** | 2025-12-24 |
| **상태** | Draft |
| **상위 문서** | [PRD-0001](./PRD-0001-poker-hand-auto-capture.md) |
| **일정** | Phase 3 (02/03 ~ 02/09) |

---

## 1. 개요

### 1.1 역할

Fusion Engine은 Primary Layer(GFX RFID)와 Secondary Layer(Gemini AI)의 결과를 **조합**하여 최종 핸드 데이터를 생성합니다.

> **핵심 차별점**: Primary/Secondary 중 택일 ❌ → 두 검증 로직을 조합하여 완성된 데이터로 추론 ✅

### 1.2 목표

| 목표 | 설명 |
|------|------|
| **교차 검증** | 두 소스의 결과 일치 여부 확인 |
| **상호 보완** | 누락된 데이터를 상대 소스로 채움 |
| **신뢰도 산출** | 최종 확률 계산 |
| **편집점 생성** | 클립 시작/종료 타임스탬프 도출 |

---

## 2. 입력 데이터

### 2.1 Primary 입력 (HandResult)

```python
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
    is_premium: bool
    timestamp: datetime
    duration_seconds: float
```

### 2.2 Secondary 입력 (AIVideoResult)

```python
@dataclass
class AIVideoResult:
    """Secondary Layer AI 분석 결과"""
    event: EventType
    cards_detected: list[str]
    card_type: Optional[CardType]
    hand_rank: Optional[str]
    confidence: float
    timestamp_offset_ms: int
    details: Optional[str]
```

---

## 3. Fusion 프로세스

### 3.1 프로세스 개요

```
┌─────────────────┐     ┌─────────────────┐
│  Primary Layer  │     │ Secondary Layer │
│   (HandResult)  │     │ (AIVideoResult) │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │    Fusion Engine      │
         │  ┌─────────────────┐  │
         │  │ 교차 검증       │  │
         │  ├─────────────────┤  │
         │  │ 상호 보완       │  │
         │  ├─────────────────┤  │
         │  │ 신뢰도 산출     │  │
         │  ├─────────────────┤  │
         │  │ 등급 결정       │  │
         │  └─────────────────┘  │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │   FusedHandResult     │
         └───────────────────────┘
```

### 3.2 교차 검증

| 검증 항목 | 방법 |
|----------|------|
| **카드 일치** | Primary 홀 카드 vs Secondary 감지 카드 비교 |
| **핸드 등급 일치** | Primary 등급 vs Secondary 등급 비교 |
| **이벤트 타이밍** | 핸드 시작/종료 시점 비교 |

```python
def cross_validate(
    primary: HandResult,
    secondary: AIVideoResult
) -> CrossValidationResult:
    """교차 검증"""
    # 카드 일치 확인
    cards_match = set(primary.hole_cards) == set(secondary.cards_detected)

    # 등급 일치 확인
    rank_match = primary.rank_name == secondary.hand_rank

    # 검증 결과
    return CrossValidationResult(
        cards_match=cards_match,
        rank_match=rank_match,
        validation_score=calculate_score(cards_match, rank_match)
    )
```

### 3.3 상호 보완

| 상황 | 보완 방법 |
|------|----------|
| **Primary 카드 누락** | Secondary 감지 카드로 보완 |
| **Secondary 등급 불확실** | Primary 등급 사용 |
| **타이밍 불일치** | Primary 타이밍 우선 |

### 3.4 신뢰도 산출

```python
def calculate_confidence(
    primary: Optional[HandResult],
    secondary: Optional[AIVideoResult],
    validation: CrossValidationResult
) -> float:
    """최종 신뢰도 계산"""
    base_confidence = 0.0

    if primary:
        # Primary는 기본 90% 신뢰도
        base_confidence = 0.90

    if secondary and secondary.confidence >= 0.8:
        if primary:
            # 둘 다 있으면 검증 결과에 따라 가중
            if validation.cards_match and validation.rank_match:
                return 0.99  # 완전 일치
            elif validation.cards_match or validation.rank_match:
                return 0.95  # 부분 일치
            else:
                return 0.85  # 불일치 (Primary 우선)
        else:
            # Secondary만 있으면 AI 신뢰도 사용
            return secondary.confidence

    return base_confidence
```

---

## 4. 4가지 케이스 분기

### 4.1 케이스 요약

| 케이스 | Primary | Secondary | 처리 |
|:------:|:-------:|:---------:|------|
| **1** | ✅ | ✅ 일치 | Primary 사용 (validated) |
| **2** | ✅ | ✅ 불일치 | Primary 사용 (review 플래그) |
| **3** | ❌ | ✅ (≥0.8) | Secondary fallback |
| **4** | ❌ | ❌ | Manual 필요 |

### 4.2 Case 1: Primary + Secondary 일치

**조건**:
- Primary 데이터 존재
- Secondary 데이터 존재
- 카드 또는 등급 일치

**처리**:
```python
def handle_case_1(
    primary: HandResult,
    secondary: AIVideoResult
) -> FusedHandResult:
    """Case 1: 일치 - Primary 사용 (validated)"""
    return FusedHandResult(
        source="primary",
        hand_result=primary,
        ai_result=secondary,
        confidence=0.99,
        validated=True,
        needs_review=False,
        fusion_case=1
    )
```

### 4.3 Case 2: Primary + Secondary 불일치

**조건**:
- Primary 데이터 존재
- Secondary 데이터 존재
- 카드 및 등급 모두 불일치

**처리**:
```python
def handle_case_2(
    primary: HandResult,
    secondary: AIVideoResult
) -> FusedHandResult:
    """Case 2: 불일치 - Primary 사용 (review 플래그)"""
    return FusedHandResult(
        source="primary",
        hand_result=primary,
        ai_result=secondary,
        confidence=0.85,
        validated=False,
        needs_review=True,  # 수동 검토 필요
        fusion_case=2,
        review_reason="Primary/Secondary 결과 불일치"
    )
```

### 4.4 Case 3: Primary 없음 + Secondary 있음

**조건**:
- Primary 데이터 없음 (RFID 실패)
- Secondary 데이터 존재
- Secondary 신뢰도 ≥ 0.80

**처리**:
```python
def handle_case_3(
    secondary: AIVideoResult
) -> FusedHandResult:
    """Case 3: Secondary fallback"""
    # AI 결과로 HandResult 생성
    inferred_result = infer_hand_from_ai(secondary)

    return FusedHandResult(
        source="secondary",
        hand_result=inferred_result,
        ai_result=secondary,
        confidence=secondary.confidence,
        validated=False,
        needs_review=True,
        fusion_case=3,
        review_reason="Primary 데이터 없음, AI fallback"
    )
```

### 4.5 Case 4: 둘 다 없음

**조건**:
- Primary 데이터 없음
- Secondary 데이터 없음 또는 신뢰도 < 0.80

**처리**:
```python
def handle_case_4() -> FusedHandResult:
    """Case 4: Manual 필요"""
    return FusedHandResult(
        source="none",
        hand_result=None,
        ai_result=None,
        confidence=0.0,
        validated=False,
        needs_review=True,
        fusion_case=4,
        review_reason="Primary/Secondary 모두 실패, 수동 처리 필요"
    )
```

---

## 5. 출력 데이터

### 5.1 FusedHandResult 스키마

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class FusionSource(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    NONE = "none"


class HandGrade(str, Enum):
    A = "A"  # 3개 조건 충족 → 방송 우선
    B = "B"  # 2개 조건 충족 → 방송 가능
    C = "C"  # 1개 조건 충족 → 아카이브만


@dataclass
class EditPoint:
    """편집점 데이터"""
    hand_num: int
    clip_start: datetime
    clip_end: datetime
    pre_roll_seconds: float = 5.0  # 핸드 시작 전 버퍼
    post_roll_seconds: float = 3.0  # 핸드 종료 후 버퍼

    @property
    def duration_seconds(self) -> float:
        return (self.clip_end - self.clip_start).total_seconds()


@dataclass
class FusedHandResult:
    """Fusion Engine 최종 출력"""
    # 소스 정보
    source: FusionSource
    fusion_case: int  # 1-4

    # 핸드 데이터
    hand_result: Optional[HandResult]
    ai_result: Optional[AIVideoResult]

    # 검증 정보
    confidence: float
    validated: bool
    needs_review: bool
    review_reason: Optional[str] = None

    # 등급 정보
    grade: Optional[HandGrade] = None
    grade_conditions: list[str] = field(default_factory=list)

    # 편집점
    edit_point: Optional[EditPoint] = None

    # 메타데이터
    table_id: str = ""
    processed_at: datetime = field(default_factory=datetime.now)

    def is_broadcast_ready(self) -> bool:
        """방송 가능 여부"""
        return (
            self.grade in [HandGrade.A, HandGrade.B]
            and self.confidence >= 0.80
            and not self.needs_review
        )
```

### 5.2 등급 결정 로직

```python
def determine_grade(result: FusedHandResult) -> HandGrade:
    """핸드 등급 결정"""
    conditions_met = []

    hand = result.hand_result
    if not hand:
        return HandGrade.C

    # 조건 1: 프리미엄 핸드 (등급 1-4)
    if hand.is_premium:
        conditions_met.append("premium_hand")

    # 조건 2: 플레이 시간이 긴 경우 (세션 평균 × 1.5배)
    avg_duration = get_session_average_duration()
    if hand.duration_seconds > avg_duration * 1.5:
        conditions_met.append("long_duration")

    # 조건 3: 보드 조합이 Three of a Kind 이상
    if hand.rank_category.value <= 7:  # Three of a Kind 이상
        conditions_met.append("strong_board")

    # 등급 결정
    count = len(conditions_met)
    if count >= 3:
        return HandGrade.A
    elif count >= 2:
        return HandGrade.B
    else:
        return HandGrade.C
```

### 5.3 편집점 생성

```python
def generate_edit_point(result: FusedHandResult) -> EditPoint:
    """편집점 생성"""
    hand = result.hand_result

    if not hand:
        return None

    # 핸드 시작 시간 (pre-roll 적용)
    clip_start = hand.timestamp - timedelta(seconds=5.0)

    # 핸드 종료 시간 (post-roll 적용)
    clip_end = hand.timestamp + timedelta(seconds=hand.duration_seconds + 3.0)

    return EditPoint(
        hand_num=hand.hand_num,
        clip_start=clip_start,
        clip_end=clip_end,
        pre_roll_seconds=5.0,
        post_roll_seconds=3.0
    )
```

---

## 6. 코드 구현

### 6.1 FusionEngine 클래스

```python
from dataclasses import dataclass
from typing import Optional, Callable
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


@dataclass
class FusionConfig:
    """Fusion Engine 설정"""
    secondary_min_confidence: float = 0.80
    pre_roll_seconds: float = 5.0
    post_roll_seconds: float = 3.0
    session_avg_duration: float = 120.0  # 2분 기본값


class FusionEngine:
    """Primary/Secondary 결과 융합 엔진"""

    def __init__(
        self,
        config: FusionConfig,
        on_result: Optional[Callable[[FusedHandResult], None]] = None
    ):
        self.config = config
        self.on_result = on_result
        self.session_durations: list[float] = []

    def update_session_average(self, duration: float):
        """세션 평균 업데이트"""
        self.session_durations.append(duration)
        # 최근 50개 핸드만 유지
        if len(self.session_durations) > 50:
            self.session_durations = self.session_durations[-50:]

    @property
    def average_duration(self) -> float:
        """세션 평균 핸드 시간"""
        if not self.session_durations:
            return self.config.session_avg_duration
        return sum(self.session_durations) / len(self.session_durations)

    def cross_validate(
        self,
        primary: Optional[HandResult],
        secondary: Optional[AIVideoResult]
    ) -> dict:
        """교차 검증"""
        if not primary or not secondary:
            return {"match": False, "cards_match": False, "rank_match": False}

        # 카드 일치 확인
        primary_cards = set(primary.hole_cards)
        secondary_cards = set(secondary.cards_detected)
        cards_match = len(primary_cards & secondary_cards) > 0

        # 등급 일치 확인
        rank_match = (
            secondary.hand_rank is not None
            and primary.rank_name.lower() == secondary.hand_rank.lower()
        )

        return {
            "match": cards_match or rank_match,
            "cards_match": cards_match,
            "rank_match": rank_match
        }

    def determine_grade(self, hand: Optional[HandResult]) -> HandGrade:
        """핸드 등급 결정"""
        if not hand:
            return HandGrade.C

        conditions = []

        # 조건 1: 프리미엄 핸드
        if hand.is_premium:
            conditions.append("premium_hand")

        # 조건 2: 긴 플레이 시간
        if hand.duration_seconds > self.average_duration * 1.5:
            conditions.append("long_duration")

        # 조건 3: 강한 보드 조합
        if hand.rank_category.value <= 7:
            conditions.append("strong_board")

        count = len(conditions)
        if count >= 3:
            return HandGrade.A
        elif count >= 2:
            return HandGrade.B
        else:
            return HandGrade.C

    def generate_edit_point(self, hand: HandResult) -> EditPoint:
        """편집점 생성"""
        from datetime import timedelta

        clip_start = hand.timestamp - timedelta(
            seconds=self.config.pre_roll_seconds
        )
        clip_end = hand.timestamp + timedelta(
            seconds=hand.duration_seconds + self.config.post_roll_seconds
        )

        return EditPoint(
            hand_num=hand.hand_num,
            clip_start=clip_start,
            clip_end=clip_end,
            pre_roll_seconds=self.config.pre_roll_seconds,
            post_roll_seconds=self.config.post_roll_seconds
        )

    def fuse(
        self,
        primary: Optional[HandResult],
        secondary: Optional[AIVideoResult],
        table_id: str = ""
    ) -> FusedHandResult:
        """Primary/Secondary 결과 융합"""

        # 교차 검증
        validation = self.cross_validate(primary, secondary)

        # 케이스 분기
        if primary and secondary:
            if validation["match"]:
                # Case 1: 일치
                result = self._handle_case_1(primary, secondary, table_id)
            else:
                # Case 2: 불일치
                result = self._handle_case_2(primary, secondary, table_id)

        elif not primary and secondary:
            if secondary.confidence >= self.config.secondary_min_confidence:
                # Case 3: Secondary fallback
                result = self._handle_case_3(secondary, table_id)
            else:
                # Case 4: 신뢰도 부족
                result = self._handle_case_4(table_id)

        elif primary and not secondary:
            # Primary만 있음 - Case 1과 유사하게 처리
            result = self._handle_primary_only(primary, table_id)

        else:
            # Case 4: 둘 다 없음
            result = self._handle_case_4(table_id)

        # 세션 평균 업데이트
        if result.hand_result:
            self.update_session_average(result.hand_result.duration_seconds)

        # 콜백 호출
        if self.on_result:
            self.on_result(result)

        return result

    def _handle_case_1(
        self,
        primary: HandResult,
        secondary: AIVideoResult,
        table_id: str
    ) -> FusedHandResult:
        """Case 1: 일치"""
        grade = self.determine_grade(primary)
        edit_point = self.generate_edit_point(primary)

        return FusedHandResult(
            source=FusionSource.PRIMARY,
            fusion_case=1,
            hand_result=primary,
            ai_result=secondary,
            confidence=0.99,
            validated=True,
            needs_review=False,
            grade=grade,
            grade_conditions=self._get_conditions(primary),
            edit_point=edit_point,
            table_id=table_id
        )

    def _handle_case_2(
        self,
        primary: HandResult,
        secondary: AIVideoResult,
        table_id: str
    ) -> FusedHandResult:
        """Case 2: 불일치"""
        grade = self.determine_grade(primary)
        edit_point = self.generate_edit_point(primary)

        return FusedHandResult(
            source=FusionSource.PRIMARY,
            fusion_case=2,
            hand_result=primary,
            ai_result=secondary,
            confidence=0.85,
            validated=False,
            needs_review=True,
            review_reason="Primary/Secondary 결과 불일치",
            grade=grade,
            grade_conditions=self._get_conditions(primary),
            edit_point=edit_point,
            table_id=table_id
        )

    def _handle_case_3(
        self,
        secondary: AIVideoResult,
        table_id: str
    ) -> FusedHandResult:
        """Case 3: Secondary fallback"""
        # AI 결과로 HandResult 추론
        inferred = self._infer_from_ai(secondary)
        grade = self.determine_grade(inferred)
        edit_point = self.generate_edit_point(inferred) if inferred else None

        return FusedHandResult(
            source=FusionSource.SECONDARY,
            fusion_case=3,
            hand_result=inferred,
            ai_result=secondary,
            confidence=secondary.confidence,
            validated=False,
            needs_review=True,
            review_reason="Primary 데이터 없음, AI fallback",
            grade=grade,
            edit_point=edit_point,
            table_id=table_id
        )

    def _handle_case_4(self, table_id: str) -> FusedHandResult:
        """Case 4: 둘 다 없음"""
        return FusedHandResult(
            source=FusionSource.NONE,
            fusion_case=4,
            hand_result=None,
            ai_result=None,
            confidence=0.0,
            validated=False,
            needs_review=True,
            review_reason="Primary/Secondary 모두 실패",
            table_id=table_id
        )

    def _handle_primary_only(
        self,
        primary: HandResult,
        table_id: str
    ) -> FusedHandResult:
        """Primary만 있는 경우"""
        grade = self.determine_grade(primary)
        edit_point = self.generate_edit_point(primary)

        return FusedHandResult(
            source=FusionSource.PRIMARY,
            fusion_case=1,
            hand_result=primary,
            ai_result=None,
            confidence=0.90,
            validated=True,
            needs_review=False,
            grade=grade,
            grade_conditions=self._get_conditions(primary),
            edit_point=edit_point,
            table_id=table_id
        )

    def _get_conditions(self, hand: HandResult) -> list[str]:
        """충족된 조건 목록"""
        conditions = []
        if hand.is_premium:
            conditions.append("premium_hand")
        if hand.duration_seconds > self.average_duration * 1.5:
            conditions.append("long_duration")
        if hand.rank_category.value <= 7:
            conditions.append("strong_board")
        return conditions

    def _infer_from_ai(self, ai: AIVideoResult) -> Optional[HandResult]:
        """AI 결과로 HandResult 추론"""
        # 간소화된 추론 로직
        if not ai.hand_rank:
            return None

        rank_map = {
            "Royal Flush": (HandRank.ROYAL_FLUSH, 1),
            "Straight Flush": (HandRank.STRAIGHT_FLUSH, 5),
            "Four of a Kind": (HandRank.FOUR_OF_A_KIND, 50),
            "Full House": (HandRank.FULL_HOUSE, 200),
            "Flush": (HandRank.FLUSH, 500),
            "Straight": (HandRank.STRAIGHT, 1605),
            "Three of a Kind": (HandRank.THREE_OF_A_KIND, 2000),
            "Two Pair": (HandRank.TWO_PAIR, 2900),
            "One Pair": (HandRank.ONE_PAIR, 5000),
            "High Card": (HandRank.HIGH_CARD, 7000),
        }

        if ai.hand_rank not in rank_map:
            return None

        rank_cat, rank_val = rank_map[ai.hand_rank]

        return HandResult(
            hand_num=0,
            player_name="Unknown",
            hole_cards=ai.cards_detected[:2] if len(ai.cards_detected) >= 2 else [],
            community_cards=ai.cards_detected[2:] if len(ai.cards_detected) > 2 else [],
            rank_value=rank_val,
            rank_name=ai.hand_rank,
            rank_category=rank_cat,
            is_premium=(rank_cat.value <= 4),
            timestamp=datetime.now(),
            duration_seconds=120.0  # 기본값
        )
```

---

## 7. 기술 스택

| 컴포넌트 | 기술 | 버전 |
|----------|------|------|
| **언어** | Python | 3.11+ |
| **데이터 모델** | Pydantic / dataclasses | - |
| **비동기** | asyncio | 내장 |
| **로깅** | logging | 내장 |

### 7.1 의존성

```toml
[project]
dependencies = [
    "pydantic>=2.0",
]
```

---

## 8. 테스트 계획

### 8.1 단위 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| 4가지 케이스 분기 | 각 케이스별 처리 검증 | P0 |
| 교차 검증 로직 | 일치/불일치 판정 | P0 |
| 등급 결정 | A/B/C 등급 판정 | P0 |
| 편집점 생성 | 타임스탬프 계산 | P1 |

### 8.2 통합 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| Primary + Secondary | 전체 파이프라인 | P0 |
| Fallback 시나리오 | RFID 실패 시 AI fallback | P0 |
| 멀티테이블 | 동시 처리 | P1 |

### 8.3 성능 목표

| 지표 | 목표 |
|------|------|
| Fusion 처리 시간 | < 10ms |
| 메모리 사용량 | < 50MB |
| 등급 결정 시간 | < 1ms |

---

## 부록

### A. 케이스별 통계 예상

| 케이스 | 예상 비율 | 설명 |
|:------:|:--------:|------|
| Case 1 | 85% | 정상 동작 |
| Case 2 | 10% | 수동 검토 필요 |
| Case 3 | 4% | AI fallback |
| Case 4 | 1% | 완전 실패 |

### B. 참조 자료

- [PRD-0002: Primary Layer](./PRD-0002-primary-gfx-rfid.md)
- [PRD-0003: Secondary Layer](./PRD-0003-secondary-gemini-live.md)
