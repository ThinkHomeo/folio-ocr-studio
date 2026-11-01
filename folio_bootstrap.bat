@echo off
setlocal
cd /d "%~dp0"
set "FOLIO_PYTHON=py -3"
%FOLIO_PYTHON% -I -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto ready
set "FOLIO_PYTHON=python"
%FOLIO_PYTHON% -I -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto ready
set "FOLIO_PYTHON="%~dp0.venv\Scripts\python.exe""
if not exist "%~dp0.venv\Scripts\python.exe" goto missing_python
%FOLIO_PYTHON% -I -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
:ready
echo Checking Folio dependencies...
%FOLIO_PYTHON% -B "%~dp0setup_folio.py" %*
exit /b %errorlevel%
:missing_python
echo Python 3.10 or newer, 64-bit, is required.
echo Download: https://www.python.org/downloads/windows/
echo Select Add Python to PATH during installation.
echo Then close this window and open setup_folio.bat again.
echo.
echo Optional Windows Package Manager command:
echo winget install --id Python.Python.3.12 --exact --source winget
choice /c YN /m "Open the official Python download page now"
if errorlevel 2 exit /b 1
start "" "https://www.python.org/downloads/windows/"
exit /b 1
