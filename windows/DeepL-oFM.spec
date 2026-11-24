# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the Windows build.

Build with:  .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DeepL-oFM.spec
Output:      dist\DeepL-oFM\DeepL-oFM.exe
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # collect_submodules must import deepl_ofm
ICON = ROOT / "tools" / "app.ico"

hiddenimports = collect_submodules("deepl_ofm")
hiddenimports += collect_submodules("pdfplumber")
hiddenimports += collect_submodules("pypdf")
hiddenimports += collect_submodules("keyring.backends")

datas = []
datas += collect_data_files("reportlab")
datas += collect_data_files("pdfplumber")
datas += collect_data_files("pypdf")
datas += collect_data_files("keyring")

a = Analysis(
    [str(ROOT / "tools" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data", "xmlrpc"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeepL-oFM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON) if ICON.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DeepL-oFM",
)
