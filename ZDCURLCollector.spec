# ZDCURLCollector.spec
# Run with: pyinstaller ZDCURLCollector.spec

block_cipher = None

a = Analysis(
    ['run.py'],                          # Entry point
    pathex=['.'],
    binaries=[],                         # Chromium binary added dynamically or at installation
    datas=[
        ('static', 'static'),            # Bundle the frontend HTML/JS/CSS
        ('app', 'app'),                  # Bundle the app package
        # DO NOT bundle sessions/, data/, output/, config/, proxy/, .env, links.txt
        # These are mutable runtime files that must live outside the .exe
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'fastapi.middleware',
        'fastapi.middleware.cors',
        'fastapi.staticfiles',
        'fastapi.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        'starlette.staticfiles',
        'starlette.responses',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'starlette',
        'playwright',
        'playwright.sync_api',
        'playwright.async_api',
        'apscheduler',
        'apscheduler.schedulers.background',
        'apscheduler.schedulers.asyncio',
        'tenacity',
        'openpyxl',
        'dotenv',
        'yt_dlp',
        'httpx',
        'telegram',
        'telegram.ext',
        'pydantic',
        'multipart',
        'aiofiles',
        'webview',
    ],
    hookspath=['.'],                      # Look in root for hook-playwright.py
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,              # Better for large apps/Playwright compatibility
    name='ZDCURLCollector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,                       # Keep True so uvicorn server logs are visible
    icon=None,                          # Omit icon since no .ico is present
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ZDCURLCollector',
)
