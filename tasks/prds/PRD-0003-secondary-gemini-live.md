# PRD-0003: Secondary Layer - Gemini Live API

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0003 |
| **제목** | Secondary Layer - Gemini Live API 기술 상세 |
| **버전** | 1.1 |
| **작성일** | 2025-12-24 |
| **수정일** | 2026-01-05 |
| **상태** | Draft |
| **상위 문서** | [PRD-0001](./PRD-0001-poker-hand-auto-capture.md) |
| **일정** | Phase 2 (01/20 ~ 02/02) |
| **협의 담당** | **ATI 팀** |

---

## 1. 개요

### 1.1 역할

Secondary Layer는 AI 비디오 분석을 통해 핸드를 감지하고 분류합니다. Primary Layer의 백업 및 추가 맥락 정보를 제공합니다.

| 항목 | 값 |
|------|-----|
| **신뢰도** | 85-95% (조명, 각도에 따라 변동) |
| **지연시간** | 1-3초 (1 FPS 샘플링) |
| **용도** | Primary 백업 + 맥락적 이벤트 감지 |

### 1.2 데이터 흐름

```
RTSP 스트림 → OpenCV 캡처 → 프레임 추출 (1 FPS) → Gemini Live API → AIVideoResult
```

![Secondary Layer - Gemini Live API](../../docs/images/live-api-architecture.png)

### 1.3 ATI 팀 협의 사항

> **담당**: ATI 팀과 협의하여 Live API 관련 사항 처리

#### 협의 필요 항목

| 항목 | 설명 | 우선순위 | 상태 |
|------|------|:--------:|:----:|
| **API 키 발급** | Google AI Studio 또는 Vertex AI 계정 생성 | P0 | [ ] |
| **Live API 접근 권한** | Gemini 2.5 Flash Native Audio 사용 권한 확인 | P0 | [ ] |
| **월 예산 승인** | 예상 비용 $500~1,000/월 승인 | P0 | [ ] |
| **비디오 인프라 확인** | RTSP/NDI 스트림 출력 가능 여부 | P1 | [ ] |
| **네트워크 대역폭** | 테이블당 5-10 Mbps 확보 | P1 | [ ] |
| **프롬프트 튜닝** | 포커 컨텍스트 프롬프트 최적화 협의 | P2 | [ ] |

#### 협의 일정

| 단계 | 일정 | 내용 |
|------|------|------|
| **1차 미팅** | Phase 2 시작 (01/20) | API 키 발급, 예산 승인 |
| **2차 미팅** | Week 3 중반 (01/23) | 인프라 확인, 테스트 환경 구축 |
| **3차 미팅** | Week 4 종료 (02/02) | 성능 검증, 프롬프트 튜닝 결과 |

#### 의사결정 필요 사항

1. **Google AI Studio vs Vertex AI**
   - AI Studio: 간편한 설정, 개인/팀 프로젝트
   - Vertex AI: 엔터프라이즈 기능, 더 많은 제어

2. **비용 최적화 전략**
   - FPS 조정 (1.0 → 0.5): 비용 50% 절감
   - 배치 처리: 비활성 시간대 비용 절감

3. **Fallback 전략**
   - Live API 장애 시 Gemini 3 Flash REST API 사용 여부

---

## 2. AI 모델 선택

### 2.1 모델 비교

| 용도 | 모델 | 특징 |
|------|------|------|
| **실시간 비디오 분석** | Gemini 2.5 Flash Native Audio | WebSocket 실시간 스트리밍 지원 |
| **녹화 비디오 분석** | Gemini 3 Flash | 더 높은 정확도, 최대 45분 비디오 |

### 2.2 Gemini 2.5 Flash Native Audio (Live API)

| 항목 | 값 |
|------|-----|
| **모델 ID** | `gemini-2.5-flash-preview-native-audio-dialog` |
| **프로토콜** | WebSocket |
| **입력** | 텍스트, 오디오, 비디오 (이미지 시퀀스) |
| **출력** | 텍스트, 오디오 |
| **세션 제한** | 10분 (자동 재연결 필요) |
| **컨텍스트** | 100만 토큰 |

### 2.3 Gemini 3 Flash (녹화 분석용)

| 항목 | 값 |
|------|-----|
| **모델 ID** | `gemini-3.0-flash` |
| **프로토콜** | REST API |
| **입력** | 텍스트, 이미지, 비디오 (최대 45분) |
| **출력** | 텍스트 |
| **용도** | 녹화된 핸드 재분석, 품질 검증 |

> **참고**: Gemini 3 Flash (2025년 12월 출시)는 Live API를 지원하지 않음. 실시간 분석에는 Gemini 2.5 Flash Native Audio 사용 필요.

---

## 3. Gemini Live API

### 3.1 WebSocket 연결

**엔드포인트**:
```
wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent
```

### 3.2 연결 파라미터

```python
ws_url = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
    f"?key={GEMINI_API_KEY}"
)
```

### 3.3 세션 관리

| 항목 | 값 | 대응 방안 |
|------|-----|----------|
| **세션 제한** | 10분 | 9분 30초에 자동 재연결 |
| **동시 연결** | 제한 있음 | 테이블당 1개 연결 |
| **재시도** | 지수 백오프 | 1초 → 2초 → 4초 |

### 3.4 요청 형식

**Setup 메시지**:
```json
{
  "setup": {
    "model": "models/gemini-2.5-flash-preview-native-audio-dialog",
    "generation_config": {
      "response_modalities": ["TEXT"],
      "temperature": 0.1
    },
    "system_instruction": {
      "parts": [{"text": "...시스템 프롬프트..."}]
    }
  }
}
```

**이미지 전송 메시지**:
```json
{
  "realtime_input": {
    "media_chunks": [
      {
        "mime_type": "image/jpeg",
        "data": "<base64 encoded image>"
      }
    ]
  }
}
```

### 3.5 응답 형식

```json
{
  "serverContent": {
    "modelTurn": {
      "parts": [
        {
          "text": "{\"event\": \"hand_start\", ...}"
        }
      ]
    }
  }
}
```

---

## 4. 비디오 캡처 파이프라인

### 4.1 RTSP 스트림 캡처

```python
import cv2
import asyncio
from typing import AsyncGenerator

class VideoCapture:
    """RTSP 스트림 캡처"""

    def __init__(self, rtsp_url: str, fps: float = 1.0):
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.frame_interval = 1.0 / fps
        self.cap = None

    async def connect(self) -> bool:
        """RTSP 연결"""
        self.cap = cv2.VideoCapture(self.rtsp_url)

        if not self.cap.isOpened():
            return False

        # 버퍼 크기 최소화 (최신 프레임만 사용)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        return True

    async def capture_frames(self) -> AsyncGenerator[bytes, None]:
        """프레임 캡처 (1 FPS)"""
        last_capture = 0

        while True:
            current_time = asyncio.get_event_loop().time()

            if current_time - last_capture < self.frame_interval:
                await asyncio.sleep(0.01)
                continue

            ret, frame = self.cap.read()

            if not ret:
                await asyncio.sleep(1)
                await self.connect()
                continue

            # JPEG 인코딩
            _, jpeg_data = cv2.imencode(
                '.jpg',
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 80]
            )

            last_capture = current_time
            yield jpeg_data.tobytes()

    def release(self):
        """리소스 해제"""
        if self.cap:
            self.cap.release()
```

### 4.2 프레임 처리 파이프라인

```
RTSP (30 FPS)
     ↓
캡처 (1 FPS 샘플링)
     ↓
리사이즈 (1280x720 → 640x360)
     ↓
JPEG 인코딩 (품질 80%)
     ↓
Base64 인코딩
     ↓
Gemini Live API 전송
```

### 4.3 최적화 파라미터

| 파라미터 | 값 | 이유 |
|----------|-----|------|
| **FPS** | 1.0 | API 비용 절감 + 충분한 정보 |
| **해상도** | 640x360 | 카드 인식 가능 최소 해상도 |
| **JPEG 품질** | 80% | 파일 크기 vs 품질 균형 |
| **버퍼 크기** | 1 | 최신 프레임만 처리 |

---

## 5. 시스템 프롬프트

### 5.1 포커 분석 프롬프트

```python
POKER_ANALYSIS_PROMPT = """
You are a poker broadcast analyzer specializing in Texas Hold'em.
Analyze the video stream and detect poker events.

## Your Tasks

1. **Hand Boundaries Detection**
   - hand_start: New cards being dealt
   - hand_end: Pot being pushed, cards mucked

2. **Card Detection**
   - Community cards (flop, turn, river)
   - Hole cards when visible

3. **Action Detection**
   - all_in: Player pushes all chips
   - showdown: Cards being revealed
   - significant_pot: Large pot relative to blinds

4. **Hand Ranking**
   - Identify the best possible hand
   - Rate confidence level

## Response Format

Respond ONLY with valid JSON:

{
  "event": "hand_start|hand_end|showdown|all_in|card_detected|no_event",
  "cards_detected": ["Ah", "Kd", "Qs", "Jc", "Td"],
  "card_type": "community|hole",
  "hand_rank": "Royal Flush|Straight Flush|Four of a Kind|...",
  "confidence": 0.95,
  "timestamp_offset_ms": 0,
  "details": "Optional additional context"
}

## Important Notes

- Only respond when you detect a significant event
- Use standard card notation: Rank (A,K,Q,J,T,9-2) + Suit (h,d,c,s)
- Confidence must be between 0.0 and 1.0
- If uncertain, use lower confidence score
"""
```

### 5.2 응답 JSON 스키마

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class EventType(str, Enum):
    HAND_START = "hand_start"
    HAND_END = "hand_end"
    SHOWDOWN = "showdown"
    ALL_IN = "all_in"
    CARD_DETECTED = "card_detected"
    NO_EVENT = "no_event"


class CardType(str, Enum):
    COMMUNITY = "community"
    HOLE = "hole"


class AIVideoResult(BaseModel):
    """Secondary Layer AI 분석 결과"""
    event: EventType
    cards_detected: list[str] = Field(default_factory=list)
    card_type: Optional[CardType] = None
    hand_rank: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp_offset_ms: int = 0
    details: Optional[str] = None

    def is_significant(self) -> bool:
        """중요한 이벤트인지 확인"""
        return (
            self.event != EventType.NO_EVENT
            and self.confidence >= 0.8
        )
```

---

## 6. 코드 구현

### 6.1 GeminiLiveProcessor 클래스

```python
import asyncio
import base64
import json
import websockets
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class GeminiConfig:
    """Gemini API 설정"""
    api_key: str
    model: str = "models/gemini-2.5-flash-preview-native-audio-dialog"
    temperature: float = 0.1
    session_timeout: float = 570  # 9.5분 (10분 제한 전 재연결)


class GeminiLiveProcessor:
    """Gemini Live API 기반 실시간 비디오 분석"""

    WS_URL = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
    )

    def __init__(
        self,
        config: GeminiConfig,
        on_result: Optional[Callable[[AIVideoResult], None]] = None
    ):
        self.config = config
        self.on_result = on_result
        self.ws = None
        self.session_start = None

    @property
    def ws_url(self) -> str:
        return f"{self.WS_URL}?key={self.config.api_key}"

    async def connect(self):
        """WebSocket 연결"""
        self.ws = await websockets.connect(
            self.ws_url,
            additional_headers={"Content-Type": "application/json"}
        )
        self.session_start = asyncio.get_event_loop().time()

        # Setup 메시지 전송
        setup_msg = {
            "setup": {
                "model": self.config.model,
                "generation_config": {
                    "response_modalities": ["TEXT"],
                    "temperature": self.config.temperature
                },
                "system_instruction": {
                    "parts": [{"text": POKER_ANALYSIS_PROMPT}]
                }
            }
        }
        await self.ws.send(json.dumps(setup_msg))

        # Setup 응답 대기
        response = await self.ws.recv()
        return json.loads(response)

    async def send_frame(self, jpeg_data: bytes):
        """프레임 전송"""
        if not self.ws:
            await self.connect()

        # 세션 타임아웃 체크
        elapsed = asyncio.get_event_loop().time() - self.session_start
        if elapsed > self.config.session_timeout:
            await self.reconnect()

        # Base64 인코딩
        b64_data = base64.b64encode(jpeg_data).decode('utf-8')

        # 이미지 전송
        msg = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "mime_type": "image/jpeg",
                        "data": b64_data
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(msg))

    async def receive_results(self):
        """결과 수신 루프"""
        while True:
            try:
                response = await asyncio.wait_for(
                    self.ws.recv(),
                    timeout=5.0
                )
                data = json.loads(response)

                # 모델 응답 파싱
                if "serverContent" in data:
                    model_turn = data["serverContent"].get("modelTurn", {})
                    parts = model_turn.get("parts", [])

                    for part in parts:
                        if "text" in part:
                            try:
                                result_data = json.loads(part["text"])
                                result = AIVideoResult(**result_data)

                                if result.is_significant() and self.on_result:
                                    self.on_result(result)

                            except (json.JSONDecodeError, ValueError):
                                pass  # 파싱 실패 무시

            except asyncio.TimeoutError:
                continue
            except websockets.ConnectionClosed:
                await self.reconnect()

    async def reconnect(self):
        """재연결"""
        if self.ws:
            await self.ws.close()
        await asyncio.sleep(1)
        await self.connect()

    async def process_video_stream(self, video_capture: VideoCapture):
        """비디오 스트림 처리"""
        await self.connect()

        # 수신 태스크 시작
        receive_task = asyncio.create_task(self.receive_results())

        try:
            async for frame in video_capture.capture_frames():
                await self.send_frame(frame)

        finally:
            receive_task.cancel()
            if self.ws:
                await self.ws.close()

    async def close(self):
        """연결 종료"""
        if self.ws:
            await self.ws.close()
            self.ws = None
```

### 6.2 사용 예시

```python
async def main():
    config = GeminiConfig(
        api_key="YOUR_API_KEY"
    )

    def on_result(result: AIVideoResult):
        print(f"Event: {result.event}, Confidence: {result.confidence}")
        if result.cards_detected:
            print(f"Cards: {result.cards_detected}")

    processor = GeminiLiveProcessor(config, on_result=on_result)
    video = VideoCapture("rtsp://192.168.1.100:554/stream1")

    await video.connect()
    await processor.process_video_stream(video)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. 기술 스택

| 컴포넌트 | 기술 | 버전 |
|----------|------|------|
| **언어** | Python | 3.11+ |
| **비디오 캡처** | OpenCV | 4.8+ |
| **WebSocket** | websockets | 12.0+ |
| **비동기** | asyncio | 내장 |
| **데이터 모델** | Pydantic | 2.0+ |
| **HTTP 클라이언트** | httpx | 0.25+ |

### 7.1 의존성

```toml
[project]
dependencies = [
    "opencv-python>=4.8.0",
    "websockets>=12.0",
    "pydantic>=2.0",
    "httpx>=0.25",
]
```

---

## 8. 테스트 계획

### 8.1 단위 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| 프레임 캡처 | RTSP 연결 및 캡처 | P0 |
| JSON 파싱 | API 응답 파싱 | P0 |
| 재연결 로직 | 세션 타임아웃 처리 | P0 |
| 프롬프트 응답 | 예상 형식 검증 | P1 |

### 8.2 통합 테스트

| 테스트 | 설명 | 우선순위 |
|--------|------|:--------:|
| 실시간 스트림 | 30분 연속 처리 | P0 |
| 카드 인식 | 알려진 핸드 검증 | P0 |
| 이벤트 감지 | 핸드 시작/종료 감지 | P1 |

### 8.3 성능 목표

| 지표 | 목표 |
|------|------|
| 프레임 처리 시간 | < 500ms |
| 메모리 사용량 | < 500MB (스트림당) |
| API 응답 시간 | < 2초 |
| 카드 인식 정확도 | > 85% |

---

## 9. 비용 추정

### 9.1 API 사용량

| 항목 | 값 |
|------|-----|
| **프레임 크기** | ~50KB (JPEG) |
| **FPS** | 1.0 |
| **시간당 프레임** | 3,600 |
| **시간당 데이터** | ~180MB |

### 9.2 예상 비용

| 테이블 수 | 시간당 | 일일 (8시간) | 월간 (20일) |
|:--------:|:------:|:-----------:|:----------:|
| 1대 | $0.5 | $4 | $80 |
| 3대 | $1.5 | $12 | $240 |
| 5대 | $2.5 | $20 | $400 |

> 실제 비용은 API 가격 정책에 따라 변동될 수 있음

---

## 부록

### A. 참조 자료

- [Gemini Live API 문서](https://ai.google.dev/gemini-api/docs/live)
- [Gemini 3 Flash 소개](https://blog.google/products/gemini/gemini-3-flash/)
- [OpenCV 문서](https://docs.opencv.org/)

### B. 환경 변수

```bash
GEMINI_API_KEY=your_api_key_here
RTSP_URL_TABLE_1=rtsp://192.168.1.100:554/stream1
RTSP_URL_TABLE_2=rtsp://192.168.1.101:554/stream1
RTSP_URL_TABLE_3=rtsp://192.168.1.102:554/stream1
```
