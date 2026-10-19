# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for MashLoop Desktop Application."""
from pathlib import Path

block_cipher = None
ROOT = Path.cwd()

datas = [
    (str(ROOT / "web"), "web"),
]
if (ROOT / "data" / "models").exists():
    datas.append((str(ROOT / "data" / "models"), "data/models"))
if (ROOT / "data" / "samples").exists():
    datas.append((str(ROOT / "data" / "samples"), "data/samples"))

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespans",
    "uvicorn.lifespans.on",
    "engineio.async_drivers.asgi",
    "loopbox.server",
    "loopbox.desktop",
    "loopbox.sessions",
    "loopbox.config",
    "loopbox.analysis.models",
    "loopbox.analysis.onnx_tracker",
    "loopbox.analysis.transitions",
    "loopbox.analysis.splices",
    "loopbox.analysis.voice",
    "onnxruntime",
    "soundfile",
    "clr",
    "webview.platforms.winforms",
]

a = Analysis(
    ["mashloop_app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
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
    name="MashLoop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "web" / "img" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MashLoop",
)
