@echo off
setlocal
cd /d "%~dp0..\.."

where uv >nul 2>&1
if not errorlevel 1 (
  uv run uvicorn app:app --host 127.0.0.1 --port 8585
  exit /b
)

if exist "%USERPROFILE%\.local\bin\uv.exe" (
  "%USERPROFILE%\.local\bin\uv.exe" run uvicorn app:app --host 127.0.0.1 --port 8585
  exit /b
)

echo uv was not found. Install uv and add it to PATH, then try again.
pause
exit /b 1
