# -*- mode: python ; coding: utf-8 -*-
"""
GFX Sync Agent PyInstaller Spec File

빌드 명령:
    pyinstaller sync_agent.spec

출력:
    dist/GFXSyncAgent/GFXSyncAgent.exe
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로
SPEC_DIR = Path(SPECPATH)
PROJECT_ROOT = SPEC_DIR.parent.parent  # src/sync_agent -> project root

block_cipher = None

# 데이터 파일 (설정 템플릿 포함)
datas = [
    (str(SPEC_DIR / 'config.env.example'), '.'),
]

# 히든 임포트 (동적으로 로드되는 모듈)
hiddenimports = [
    # Supabase 관련
    'supabase',
    'supabase._sync_client',
    'postgrest',
    'gotrue',
    'realtime',
    'storage3',
    'httpx',
    'httpcore',

    # Pydantic 관련
    'pydantic',
    'pydantic_settings',
    'pydantic.deprecated.decorator',

    # Watchdog 관련
    'watchdog',
    'watchdog.observers',
    'watchdog.observers.polling',
    'watchdog.events',

    # 표준 라이브러리
    'sqlite3',
    'asyncio',
    'json',
    'hashlib',
    'logging',
    'pathlib',
    'threading',
    'signal',

    # dotenv
    'dotenv',
    'python_dotenv',
]

# 제외할 모듈 (불필요한 것들)
excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    'PIL',
    'cv2',
    'tensorflow',
    'torch',
    'pytest',
    'IPython',
    'notebook',
    'sphinx',
]

a = Analysis(
    [str(SPEC_DIR / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name='GFXSyncAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 콘솔 앱 (로그 출력용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 추가 시: 'icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GFXSyncAgent',
)
