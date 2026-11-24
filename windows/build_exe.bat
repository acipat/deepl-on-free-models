@echo off
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Run run.bat once first: it creates the virtual environment.
    pause
    exit /b 1
)

"%PY%" -m pip install --upgrade pyinstaller pillow
"%PY%" tools\make_icon.py
"%PY%" -m PyInstaller --noconfirm --clean DeepL-oFM.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Done: dist\DeepL-oFM\DeepL-oFM.exe
pause
