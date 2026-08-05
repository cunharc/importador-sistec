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
        ('nfe_cli.jpg', '.'),
        ('Logo oficial grupos - Sistec.png', '.'),
        ('Logo azul ícone - Sistec.png', '.')
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

# ONEFILE: o que se distribui é um Importador_Sistec.exe único — é o que o
# utils/updater.py baixa do ZIP da release e copia para a pasta de instalação
# (`copy /y "...\Importador_Sistec.exe"`). Com exclude_binaries=True + COLLECT o
# PyInstaller geraria uma pasta dist\Importador_Sistec\ com _internal ao lado, que
# o updater não sabe instalar.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Importador_Sistec',
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
    icon=['icon.ico'],
)
