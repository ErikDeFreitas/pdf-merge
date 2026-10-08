@echo off
REM Gera o executavel MesclarPDFs.exe a partir do mesclar_pastas.py
REM Requisito: Python instalado (marcar "Add Python to PATH" na instalacao)

python -m pip install --upgrade pip
python -m pip install pypdf pyinstaller

python -m PyInstaller --onefile --noconsole --name MesclarPDFs mesclar_pastas.py

echo.
echo Pronto! O executavel esta em: dist\MesclarPDFs.exe
pause
