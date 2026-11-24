@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "STAMP=%~dp0.venv\requirements.stamp"

if not exist "%PY%" (
    echo === DeepL-oFM: first run, preparing Python ===
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10 or newer was not found. Install Python 3.12 from
        echo https://www.python.org/downloads/windows/
        echo and tick "Add python.exe to PATH", then run this file again.
        pause
        exit /b 1
    )
    rem Prefer a version that has wheels for every dependency.
    set "LAUNCHER="
    if not defined LAUNCHER (
        py -3.12 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "LAUNCHER=py -3.12"
    )
    if not defined LAUNCHER (
        py -3.13 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "LAUNCHER=py -3.13"
    )
    if not defined LAUNCHER (
        py -3.11 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "LAUNCHER=py -3.11"
    )
    if not defined LAUNCHER set "LAUNCHER=py -3"
    !LAUNCHER! -m venv .venv
    if errorlevel 1 goto :fail
    "%PY%" -m pip install --upgrade pip
)

rem The virtual environment must be Python 3.10 or newer.
"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo This virtual environment uses a Python older than 3.10.
    echo Delete the .venv folder and run this file again with Python 3.12 installed.
    pause
    exit /b 1
)
"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info < (3, 14) else 1)" >nul 2>nul
if not errorlevel 1 (
    echo   Note: Python 3.14 is very new. If installing the dependencies fails,
    echo   install Python 3.12 instead: https://www.python.org/downloads/windows/
)

rem Reinstall only when requirements.txt changed.
set "HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%~dp0requirements.txt" MD5') do (
    if not defined HASH set "HASH=%%H"
)
set "HASH=%HASH: =%"
if not exist "%STAMP%" goto :install
set /p CURRENT=<"%STAMP%"
if not "%CURRENT%"=="%HASH%" goto :install
goto :run

:install
echo === Installing dependencies ===
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
> "%STAMP%" echo %HASH%

:run
set "RUN=%PYW%"
if /i "%~1"=="--debug" set "RUN=%PY%"
if defined DEEPLOFM_DEBUG set "RUN=%PY%"
if not exist "%RUN%" set "RUN=%PY%"

if "%RUN%"=="%PY%" (
    "%RUN%" -m deepl_ofm %*
) else (
    start "" "%RUN%" -m deepl_ofm %*
)
exit /b 0

:fail
echo.
echo Could not prepare the Python environment. See the messages above.
pause
exit /b 1
