@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating CreditScope environment...
  python -m venv .venv
  if errorlevel 1 goto error
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto error
)
if not exist "data\schema.json" (
  echo Importing original project data...
  .venv\Scripts\python.exe scripts\import_project.py
  if errorlevel 1 goto error
)
for /f "delims=" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess)"') do set "CREDITSCOPE_PID=%%P"
if defined CREDITSCOPE_PID (
  echo.
  echo CreditScope is already running: http://127.0.0.1:8000
  echo To load an update, close the existing CreditScope window with Ctrl+C, then run this file again.
  echo.
  pause
  exit /b 0
)
echo.
echo CreditScope: http://127.0.0.1:8000
echo Keep this window open. Press Ctrl+C to stop.
echo.
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo CreditScope could not start. Review the error above.
pause
exit /b 1
