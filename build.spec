# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        ('fbclient_3.dll', '.'),
        ('fbclient_4.dll', '.'),
        ('fbclient_5.dll', '.')
    ],
    datas=[
        ('icon.ico', '.'),
        ('sistec.jpg', '.'),
        ('Icone_plano.jpg', '.'),
        ('nfe_cli.jpg', '.')
    ],
    hiddenimports=[
        'fdb',
        'xml.etree',
        'xml.etree.ElementTree',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Importador_Sistec',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Importador_Sistec',
)
