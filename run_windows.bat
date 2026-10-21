@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo KaraokeSesh is not installed yet. Running installer...
  call scripts\install_windows.bat
)

.venv\Scripts\python.exe app.py
pause
