# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Meikova Loop Desktop Application."""
import sys
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
    "loopbox.tray",
    "loopbox.sessions",
    "loopbox.auth",
    "loopbox.config",
    "loopbox.analysis.models",
    "loopbox.analysis.onnx_tracker",
    "loopbox.analysis.transitions",
    "loopbox.analysis.splices",
    "loopbox.analysis.voice",
    "onnxruntime",
    "soundfile",
]

if sys.platform == "win32":
    hiddenimports.extend(["clr", "webview.platforms.winforms"])
elif sys.platform == "darwin":
    hiddenimports.extend(["webview.platforms.cocoa", "objc"])
elif sys.platform.startswith("linux"):
    hiddenimports.extend(["webview.platforms.gtk", "gi"])

a = Analysis(
    ["meikova_loop_app.py"],
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
    name="MeikovaLoop",
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
    name="MeikovaLoop",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MeikovaLoop.app",
        icon=str(ROOT / "web" / "img" / "icon.ico") if (ROOT / "web" / "img" / "icon.ico").exists() else None,
        bundle_identifier="com.meikova.loop",
        info_plist={
            "NSPrincipalClass": "NSApplication",
            "NSAppleScriptEnabled": False,
            "NSHighResolutionCapable": "True",
        },
    )
