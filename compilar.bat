@echo off
echo ====================================
echo   COMPILAR CENTRAL DE IMPLANTACAO SISTEC
echo ====================================
echo.

cd /d "%~dp0"

echo Verificando PyInstaller...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller nao encontrado. Instalando...
    python -m pip install pyinstaller
)

echo.
echo Compilando...
python -m PyInstaller build.spec --clean

echo.
echo ====================================
echo Compilacao concluida!
echo Executavel em: dist\Central_Implantacao_Sistec\
echo ====================================
pause
