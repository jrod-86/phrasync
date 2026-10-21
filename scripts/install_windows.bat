@echo off
setlocal
cd /d "%~dp0\.."
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.11 or 3.12 from python.org.
  pause
  exit /b 1
)
py -3.11 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-ai.txt
if errorlevel 1 (
  echo.
  echo Core app installed, but the optional AI pack failed. Run scripts\install_ai_windows.bat later.
)
echo.
echo KaraokeSesh installation complete. Start with run_windows.bat.
pause
