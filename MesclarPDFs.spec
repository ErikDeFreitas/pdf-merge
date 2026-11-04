# -*- mode: python ; coding: utf-8 -*-
# Build:  python -m PyInstaller --noconfirm MesclarPDFs.spec   (ou rode gerar_exe.bat)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/styles.qss', 'ui')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'numpy', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf', 'PySide6.QtMultimedia',
              'PySide6.QtNetwork', 'PIL._avif'],
    noarchive=False,
    optimize=0,
)

# Binários do Qt que o app não usa (renderização OpenGL por software, QML, Quick, PDF).
DESNECESSARIOS = ('opengl32sw', 'qt6quick', 'qt6qml', 'qt6pdf', 'qt6network', 'qt6opengl',
                  'qt6virtualkeyboard', 'qt6dbus')
a.binaries = [b for b in a.binaries if not b[0].lower().split('\\')[-1].startswith(DESNECESSARIOS)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MesclarPDFs',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
