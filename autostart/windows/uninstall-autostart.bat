@echo off
setlocal
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\insta-post-to-pdf.lnk"
if exist "%SHORTCUT%" (
  del "%SHORTCUT%"
  echo Removed the Startup shortcut.
) else (
  echo No Startup shortcut was found.
)
