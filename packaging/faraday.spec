# PyInstaller spec for the Faraday desktop app (one-folder build, no console).
# Build with packaging\build.ps1, which runs: pyinstaller packaging\faraday.spec

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "faraday")

datas = [
    (os.path.join(PKG, "qt", "resources", "icons", "lucide"), os.path.join("faraday", "qt", "resources", "icons", "lucide")),
    (os.path.join(PKG, "generator", "eff_large_wordlist.txt"), os.path.join("faraday", "generator")),
    (os.path.join(PKG, "generator", "WORDLIST_ATTRIBUTION.md"), os.path.join("faraday", "generator")),
    (os.path.join(ROOT, "LICENSE.txt"), "."),
]

# Qt modules Faraday never uses; leaving them out keeps the build small.
excludes = [
    "tkinter", "faraday.gui", "pytest", "pytestqt",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
]

a = Analysis(
    [os.path.join(SPECPATH, "launch_faraday.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["PySide6.QtSvg", "PySide6.QtNetwork"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Faraday",
    console=False,
    icon=os.path.join(SPECPATH, "faraday.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Faraday", upx=False)
