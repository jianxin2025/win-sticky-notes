# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

hiddenimports = [
    "markdown",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
]


a = Analysis(
    ["notes.py"],
    pathex=[str(Path(SPECPATH))],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy",
        "scipy",
        "pandas",
        "matplotlib",
        "cv2",
        "sklearn",
        "skimage",
        "librosa",
        "transformers",
        "torch",
        "onnx",
        "onnxruntime",
        "numba",
        "numexpr",
        "PIL",
        "IPython",
        "jupyter",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WinStickyNotes",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=None,
)
