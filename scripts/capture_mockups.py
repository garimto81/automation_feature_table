"""
HTML 목업 요소 단위 캡처 스크립트

Usage:
    python scripts/capture_mockups.py                    # 모든 목업 캡처
    python scripts/capture_mockups.py hand-grading      # 특정 목업만 캡처
"""

import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Error: playwright가 설치되어 있지 않습니다.")
    print("설치: pip install playwright && playwright install chromium")
    sys.exit(1)


# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent
MOCKUPS_DIR = PROJECT_ROOT / "docs" / "mockups"
IMAGES_DIR = PROJECT_ROOT / "docs" / "images"


# 목업 파일 매핑
MOCKUPS = {
    "hand-grading": {
        "html": MOCKUPS_DIR / "hand-grading.html",
        "output": IMAGES_DIR / "hand-grading.png",
        "selector": "#capture-area",
    },
    "architecture": {
        "html": MOCKUPS_DIR / "architecture.html",
        "output": IMAGES_DIR / "architecture.png",
        "selector": "#capture-area",
    },
    "fusion-engine": {
        "html": MOCKUPS_DIR / "fusion-engine.html",
        "output": IMAGES_DIR / "fusion-engine.png",
        "selector": "#capture-area",
    },
}


async def capture_element(page, html_path: Path, output_path: Path, selector: str) -> bool:
    """특정 요소만 캡처"""
    try:
        # HTML 파일 로드
        file_url = f"file:///{html_path.as_posix()}"
        await page.goto(file_url)

        # 폰트 로딩 대기
        await page.wait_for_timeout(1000)

        # 요소 찾기
        element = page.locator(selector)

        if not await element.count():
            print(f"  [ERROR] 요소를 찾을 수 없음: {selector}")
            return False

        # 출력 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 요소만 캡처 (투명 배경)
        await element.screenshot(
            path=str(output_path),
            omit_background=True,  # 투명 배경
        )

        print(f"  [OK] {output_path.name} ({output_path.stat().st_size // 1024}KB)")
        return True

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


async def main(targets: list[str] | None = None):
    """메인 실행"""
    print("=" * 50)
    print("HTML 목업 요소 단위 캡처")
    print("=" * 50)

    # 대상 결정
    if targets:
        mockups_to_capture = {k: v for k, v in MOCKUPS.items() if k in targets}
        if not mockups_to_capture:
            print(f"Error: 알 수 없는 목업: {targets}")
            print(f"사용 가능: {list(MOCKUPS.keys())}")
            return
    else:
        mockups_to_capture = MOCKUPS

    async with async_playwright() as p:
        # Chromium 실행 (헤드리스)
        browser = await p.chromium.launch()

        # 540px 너비로 뷰포트 설정
        page = await browser.new_page(viewport={"width": 600, "height": 1200})

        success_count = 0

        for name, config in mockups_to_capture.items():
            print(f"\n[{name}]")

            if not config["html"].exists():
                print(f"  [SKIP] HTML 파일 없음: {config['html']}")
                continue

            if await capture_element(
                page,
                config["html"],
                config["output"],
                config["selector"],
            ):
                success_count += 1

        await browser.close()

    print("\n" + "=" * 50)
    print(f"완료: {success_count}/{len(mockups_to_capture)} 성공")
    print("=" * 50)


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(main(targets))
