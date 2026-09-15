@echo off
setlocal EnableExtensions
title Insta Post to PDF - One-step install

rem One-step Windows installer:
rem   1. Installs uv if it is missing.
rem   2. Creates .venv and installs all packages (uv sync).
rem   3. Adds a hidden Startup entry so the server starts when you sign in.
rem Double-click this file to run the whole setup.

cd /d "%~dp0..\.."
if errorlevel 1 goto :dir_fail

echo ============================================
echo  Step 1 of 3 - Check/install uv
echo ============================================
where uv >nul 2>&1
if errorlevel 1 (
  if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  ) else (
    echo uv not found. Installing it now...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  )
)
where uv >nul 2>&1
if errorlevel 1 (
  echo.
  echo Could not install uv. Install it manually from https://docs.astral.sh/uv/
  echo and re-run this installer.
  pause
  exit /b 1
)

echo ============================================
echo  Step 2 of 3 - Create env and install packages
echo ============================================
uv sync
if errorlevel 1 (
  echo.
  echo uv sync failed. Review the messages above and fix the problem,
  echo then re-run this installer.
  pause
  exit /b 1
)

echo ============================================
echo  Step 3 of 3 - Add to Windows Startup
echo ============================================
call "%CD%\autostart\windows\install-autostart.bat"
if errorlevel 1 (
  echo Could not add the Startup entry.
  pause
  exit /b 1
)

echo ============================================
echo  Optional tools check
echo ============================================
where ffmpeg >nul 2>&1 || echo NOTE: ffmpeg not found on PATH - run "winget install Gyan.FFmpeg" for YouTube MP4/MP3.
where deno  >nul 2>&1 || echo NOTE: deno not found on PATH - run "winget install deno.land" for YouTube downloads.

echo.
echo Done! The server will start hidden when you log in.
echo Open the app at:  http://127.0.0.1:8585
echo To start it right now, run:  autostart\windows\start-insta-post-to-pdf.bat
pause
exit /b 0

:dir_fail
echo Could not find the project folder.
pause
exit /b 1