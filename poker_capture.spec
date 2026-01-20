# -*- mode: python ; coding: utf-8 -*-
"""
Poker Hand Auto-Capture System PyInstaller Spec File

빌드 명령:
    pyinstaller poker_capture.spec

출력:
    dist/PokerHandCapture/PokerHandCapture.exe

의존성:
    pip install pyinstaller
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로
SPEC_DIR = Path(SPECPATH)
PROJECT_ROOT = SPEC_DIR

block_cipher = None

# phevaluator 패키지 경로 찾기
import importlib.util
phevaluator_spec = importlib.util.find_spec('phevaluator')
if phevaluator_spec and phevaluator_spec.origin:
    phevaluator_path = str(Path(phevaluator_spec.origin).parent)
else:
    phevaluator_path = None

# 데이터 파일 (설정 파일 및 phevaluator 데이터 포함)
datas = [
    ('.env.example', '.'),
    ('.env', '.'),  # 실제 환경 설정 파일 포함
]

# phevaluator 전체 패키지 포함 (테이블 데이터 포함)
if phevaluator_path:
    from PyInstaller.utils.hooks import collect_all
    phevaluator_datas, phevaluator_binaries, phevaluator_hiddenimports = collect_all('phevaluator')
    datas += phevaluator_datas
else:
    phevaluator_binaries = []
    phevaluator_hiddenimports = []

# 히든 임포트 (동적으로 로드되는 모듈)
hiddenimports = [
    # ========== Core Dependencies ==========
    # Pydantic 관련
    'pydantic',
    'pydantic_settings',
    'pydantic.deprecated.decorator',
    'pydantic_core',

    # ========== Database - Supabase (Primary) ==========
    'supabase',
    'supabase._sync_client',
    'supabase._async_client',
    'postgrest',
    'postgrest._sync_client',
    'postgrest._async_client',
    'gotrue',
    'gotrue._sync_client',
    'gotrue._async_client',
    'realtime',
    'storage3',

    # ========== Database - PostgreSQL (Legacy) ==========
    'sqlalchemy',
    'sqlalchemy.ext.asyncio',
    'sqlalchemy.orm',
    'sqlalchemy.dialects.postgresql',
    'asyncpg',
    'asyncpg.protocol',
    'alembic',

    # ========== HTTP/WebSocket ==========
    'httpx',
    'httpcore',
    'httpx._transports',
    'httpx._transports.default',
    'websockets',
    'websockets.client',
    'websockets.legacy',
    'websockets.legacy.client',
    'aiohttp',
    'aiohttp.web',

    # ========== Video/CV ==========
    'cv2',
    'numpy',
    'numpy.core',
    'numpy.core._multiarray_umath',

    # ========== Poker Evaluation ==========
    'phevaluator',
    'phevaluator.card',
    'phevaluator.evaluator',
    'phevaluator.hash',
    'phevaluator.tables',
    'phevaluator.tables.dptables',
    'phevaluator.tables.hashtable',
    'phevaluator.tables.hashtable5',
    'phevaluator.tables.hashtable6',
    'phevaluator.tables.hashtable_omaha',

    # ========== File Watching (NAS JSON mode) ==========
    'watchdog',
    'watchdog.observers',
    'watchdog.observers.polling',
    'watchdog.events',
    'aiofiles',

    # ========== Dashboard (FastAPI + Uvicorn) ==========
    'fastapi',
    'fastapi.middleware',
    'fastapi.middleware.cors',
    'uvicorn',
    'uvicorn.config',
    'uvicorn.main',
    'uvicorn.protocols',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'starlette',
    'starlette.websockets',
    'starlette.routing',

    # ========== XML Security ==========
    'defusedxml',
    'defusedxml.ElementTree',

    # ========== Standard Library ==========
    'asyncio',
    'json',
    'hashlib',
    'logging',
    'pathlib',
    'threading',
    'signal',
    'sqlite3',
    'datetime',
    'enum',

    # ========== dotenv ==========
    'dotenv',
    'python_dotenv',

    # ========== Encoding ==========
    'encodings',
    'encodings.utf_8',
    'encodings.ascii',
    'encodings.cp949',
    'encodings.euc_kr',
] + phevaluator_hiddenimports

# 제외할 모듈 (불필요한 것들 - 빌드 크기 최적화)
excludes = [
    # GUI 프레임워크 (본 앱은 콘솔)
    'tkinter',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',

    # 대용량 과학 라이브러리
    'matplotlib',
    'scipy',
    'pandas',

    # ML/DL 프레임워크
    'tensorflow',
    'torch',
    'keras',

    # 개발 도구
    'pytest',
    'IPython',
    'notebook',
    'sphinx',
    'mypy',
    'ruff',

    # Streamlit (시뮬레이터용 - 별도 빌드)
    'streamlit',
]

a = Analysis(
    ['src/main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=phevaluator_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],  # .env 로드를 위한 런타임 훅
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PokerHandCapture',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 콘솔 앱 (로그 출력 필요)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 추가 시: 'assets/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PokerHandCapture',
)
