# Google Docs PRD 작성 가이드

**Version**: 1.0.0 | **Updated**: 2025-12-25

Markdown PRD를 Google Docs로 변환하고 관리하는 전체 워크플로우 가이드입니다.

---

## 개요

### 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Markdown PRD   │────▶│  Converter      │────▶│  Google Docs    │
│  (로컬 원본)     │     │  (Python)       │     │  (게시용)        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │                       ▼                       │
        │               ┌─────────────────┐             │
        │               │  HTML Mockups   │             │
        │               │  (다이어그램)    │─────────────┘
        │               └─────────────────┘   이미지 삽입
        │
        ▼
┌─────────────────┐
│  docs/images/   │
│  (캡처된 PNG)   │
└─────────────────┘
```

### 핵심 컴포넌트

| 컴포넌트 | 경로 | 역할 |
|----------|------|------|
| **Converter** | `lib/google_docs/converter.py` | Markdown → Docs 변환 |
| **Notion Style** | `lib/google_docs/notion_style.py` | 스타일 시스템 |
| **Image Inserter** | `lib/google_docs/image_inserter.py` | 이미지 삽입 |
| **Table Renderer** | `lib/google_docs/table_renderer.py` | 테이블 렌더링 |
| **PRD 스크립트** | `scripts/prd_to_google_docs.py` | CLI 변환 도구 |

---

## 워크플로우

### 1단계: Markdown PRD 작성

```
tasks/prds/PRD-NNNN-feature-name.md
```

**PRD 구조**:

```markdown
# PRD-0001: 기능명

## 문서 정보
| 항목 | 내용 |
|------|------|
| **PRD ID** | PRD-0001 |
| **버전** | 1.0 |
| **상태** | Draft |

---

## 1. 개요
### 1.1 배경
...

## 2. 기술 아키텍처
![아키텍처](../../docs/images/architecture.png)
...
```

### 2단계: 다이어그램 생성

#### HTML 목업 작성

**위치**: `docs/mockups/[feature].html`

**규격**:
- 가로 너비: 540px
- 최소 폰트: 16px
- 캡처 대상: `#capture-area` 또는 `#capture-target`

**템플릿**: `lib/google_docs/templates/` 참조

#### 캡처 명령

```powershell
# 요소만 캡처 (권장)
npx playwright screenshot docs/mockups/architecture.html docs/images/architecture.png --selector="#capture-area"
```

### 3단계: Google Docs 변환

```powershell
# 기본 변환
python scripts/prd_to_google_docs.py tasks/prds/PRD-0001-feature.md

# 옵션 사용
python scripts/prd_to_google_docs.py --toc tasks/prds/PRD-0001.md
python scripts/prd_to_google_docs.py --folder FOLDER_ID file.md
```

**출력**:
```
============================================================
PRD to Google Docs Converter (Optimized)
============================================================
파일 수: 1
폴더 ID: 1JwdlUe_v4Ug-yQ0veXTldFl6C24GH8hW
============================================================

[FILE] PRD-0001-feature.md
  문서 생성됨: PRD-0001: 기능명
  ID: 1abc...xyz
  페이지 크기: A4 (210mm x 297mm)
  폴더로 이동됨
  Content added: 395 requests
  Tables filled: 25 tables
  Images inserted: 3 images
  [OK] https://docs.google.com/document/d/1abc.../edit
```

---

## 스타일 시스템

### Notion 스타일

`lib/google_docs/notion_style.py`에서 정의된 스타일 시스템:

#### 색상 팔레트

| 용도 | 색상 | HEX |
|------|------|-----|
| 텍스트 Primary | 거의 검정 | `#1a1a1a` |
| 텍스트 Secondary | 중간 회색 | `#555555` |
| 제목 Primary | GitHub Blue | `#0969DA` |
| 제목 Secondary | 진한 검정 | `#1F2328` |
| 코드 배경 | 연한 회색 | `#F6F8FA` |
| 코드 텍스트 | 빨강 | `#CF222E` |
| 링크 | 파랑 | `#0969DA` |

#### 타이포그래피

| 레벨 | 크기 | 여백 (전/후) |
|------|------|-------------|
| H1 | 32pt | 48pt / 16pt |
| H2 | 24pt | 36pt / 12pt |
| H3 | 18pt | 28pt / 8pt |
| H4 | 16pt | 20pt / 6pt |
| Body | 14pt | - / 8pt |
| Code | 13pt | 16pt / 16pt |

#### 섹션 아이콘

H2, H3 제목에 자동으로 아이콘이 추가됩니다:

| 키워드 | 아이콘 |
|--------|--------|
| overview, introduction | 📋, 📝 |
| architecture, technical | 🏗️, ⚙️ |
| features, requirements | ✨, 📋 |
| workflow, process | 🔄, ⚡ |
| testing, security | 🧪, 🔒 |
| deployment | 🚢 |
| appendix, references | 📎, 📖 |

### 폰트 설정

| 용도 | 폰트 |
|------|------|
| 제목 | Georgia |
| 본문 | Arial |
| 코드 | Consolas |
| UI | Segoe UI |

---

## 마크다운 변환 지원

### 지원 문법

| 문법 | 예시 | 변환 결과 |
|------|------|----------|
| 제목 | `# H1` ~ `###### H6` | 스타일링된 제목 |
| 볼드 | `**bold**` | **굵은 글씨** |
| 이탤릭 | `*italic*` | *기울임* |
| 코드 | `` `code` `` | 인라인 코드 (빨간 텍스트 + 배경) |
| 취소선 | `~~strike~~` | ~~취소선~~ |
| 링크 | `[text](url)` | 파란 밑줄 링크 |
| 불릿 | `- item` | • 불릿 리스트 |
| 번호 | `1. item` | 번호 리스트 |
| 체크박스 | `- [ ]` / `- [x]` | ☐ / ☑ |
| 인용문 | `> quote` | 왼쪽 테두리 + 배경 |
| 코드블록 | ` ``` ` | 언어 표시 + 코드 스타일 |
| 테이블 | `\| a \| b \|` | 네이티브 테이블 |
| 이미지 | `![alt](path)` | Drive 업로드 후 삽입 |
| 수평선 | `---` | ─ × 50 |

### 테이블 스타일

- 헤더 행: 볼드 + 배경색 (`#F6F8FA`)
- 셀 내 볼드: `**text**` → 파란색 볼드
- 열 너비: A4 페이지에 맞게 균등 분배

### 이미지 처리

1. 상대 경로 → 절대 경로 변환
2. Google Drive에 업로드
3. 공개 URL 생성
4. 플레이스홀더를 실제 이미지로 교체
5. 너비: 405 PT (540px 기준)

---

## 이미지 삽입

### ImageInserter 클래스

```python
from lib.google_docs.image_inserter import ImageInserter
from lib.google_docs.auth import get_credentials

creds = get_credentials()
inserter = ImageInserter(creds)

# Drive에 업로드
file_id, image_url = inserter.upload_to_drive(Path('diagram.png'))

# 특정 위치에 삽입
inserter.insert_image_at_position(doc_id, image_url, position=100, width=400)

# 텍스트 다음에 삽입
inserter.insert_image_after_text(doc_id, image_url, "## 아키텍처")

# 제목 다음에 삽입
inserter.insert_image_after_heading(doc_id, image_url, "기술 아키텍처")
```

### 지원 이미지 형식

| 확장자 | MIME Type |
|--------|-----------|
| `.png` | image/png |
| `.jpg`, `.jpeg` | image/jpeg |
| `.gif` | image/gif |
| `.webp` | image/webp |
| `.svg` | image/svg+xml |

---

## HTML 목업 템플릿

### 사용 가능한 템플릿

| 템플릿 | 경로 | 용도 |
|--------|------|------|
| **base** | `templates/base.html` | 기본 레이아웃 |
| **architecture** | `templates/architecture.html` | 시스템 아키텍처 |
| **flowchart** | `templates/flowchart.html` | 프로세스 흐름도 |
| **erd** | `templates/erd.html` | 데이터베이스 ERD |
| **ui-mockup** | `templates/ui-mockup.html` | UI 목업 |

### 다이어그램 생성기

```python
from lib.google_docs.diagram_generator import DiagramGenerator

generator = DiagramGenerator()

# 아키텍처 다이어그램 생성
html = generator.create_architecture_diagram(
    title="시스템 아키텍처",
    components=[
        {"name": "Frontend", "type": "client"},
        {"name": "API Gateway", "type": "gateway"},
        {"name": "Backend", "type": "server"},
    ]
)
```

---

## OAuth 인증

### 설정 파일

| 파일 | 경로 | 용도 |
|------|------|------|
| Credentials | `D:\AI\claude01\json\desktop_credentials.json` | OAuth 클라이언트 |
| Token | `D:\AI\claude01\json\token.json` | 액세스 토큰 (자동 생성) |

### 필요 권한 (Scopes)

```python
SCOPES = [
    'https://www.googleapis.com/auth/documents',  # Docs 읽기/쓰기
    'https://www.googleapis.com/auth/drive'       # Drive 읽기/쓰기
]
```

### 인증 흐름

1. `get_credentials()` 호출
2. `token.json` 존재 시 → 토큰 로드
3. 토큰 만료 시 → 자동 갱신
4. 토큰 없음 → 브라우저에서 OAuth 인증
5. 새 토큰 저장

---

## 공유 폴더

### 기본 폴더

| 항목 | 값 |
|------|-----|
| 폴더 ID | `1JwdlUe_v4Ug-yQ0veXTldFl6C24GH8hW` |
| URL | [Google AI Studio 폴더](https://drive.google.com/drive/folders/1JwdlUe_v4Ug-yQ0veXTldFl6C24GH8hW) |

### 폴더 변경

```powershell
# 다른 폴더에 생성
python scripts/prd_to_google_docs.py --folder NEW_FOLDER_ID file.md

# 내 드라이브 루트에 생성
python scripts/prd_to_google_docs.py --no-folder file.md
```

---

## CLI 옵션

```powershell
python scripts/prd_to_google_docs.py [OPTIONS] [FILE...]

Options:
  --folder, -f ID    대상 폴더 ID (기본: 공유 폴더)
  --toc              목차 자동 생성
  --no-folder        폴더 이동 없이 내 드라이브에 생성

Examples:
  # 기본 PRD 변환
  python scripts/prd_to_google_docs.py

  # 특정 파일 변환
  python scripts/prd_to_google_docs.py tasks/prds/PRD-0001.md

  # 배치 변환
  python scripts/prd_to_google_docs.py tasks/prds/*.md

  # 목차 포함
  python scripts/prd_to_google_docs.py --toc file.md
```

---

## 문제 해결

### 일반적인 오류

| 오류 | 원인 | 해결 |
|------|------|------|
| `token.json not found` | 인증 미완료 | 스크립트 실행 시 브라우저 인증 |
| `Folder move failed` | 폴더 권한 없음 | 폴더 공유 권한 확인 |
| `Image insert failed` | 이미지 경로 오류 | 절대 경로 또는 상대 경로 확인 |
| `Table fill failed` | 테이블 구조 오류 | 마크다운 테이블 문법 확인 |

### 디버깅

```powershell
# 상세 출력 확인
python scripts/prd_to_google_docs.py file.md 2>&1 | tee log.txt
```

---

## 코드 구조

```
lib/google_docs/
├── __init__.py          # 패키지 초기화
├── __main__.py          # CLI 진입점
├── auth.py              # OAuth 인증
├── cli.py               # CLI 인터페이스
├── converter.py         # Markdown → Docs 변환
├── diagram_generator.py # 다이어그램 생성
├── image_inserter.py    # 이미지 삽입
├── models.py            # 데이터 모델
├── notion_style.py      # 스타일 시스템
├── table_renderer.py    # 테이블 렌더링
└── templates/           # HTML 템플릿
    ├── architecture.html
    ├── base.html
    ├── erd.html
    ├── flowchart.html
    └── ui-mockup.html
```

---

## 관련 문서

| 문서 | 설명 |
|------|------|
| `docs/HTML_MOCKUP_GUIDE.md` | HTML 목업 설계 가이드 |
| `CLAUDE.md` | 프로젝트 전역 지침 |
| `docs/COMMAND_REFERENCE.md` | 커맨드 참조 |

---

## 버전 이력

| 버전 | 날짜 | 변경 |
|------|------|------|
| 1.0.0 | 2025-12-25 | 초기 작성 - 전체 워크플로우 문서화 |
