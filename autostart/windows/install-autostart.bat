@echo off
setlocal
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%~dp0start-hidden.vbs"
set "WScriptExe=%SystemRoot%\System32\wscript.exe"

if not exist "%TARGET%" (
  echo Could not find start-hidden.vbs
  exit /b 1
)

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path $env:STARTUP 'insta-post-to-pdf.lnk')); $s.TargetPath = $env:WScriptExe; $s.Arguments = ('\"' + $env:TARGET + '\"'); $s.WorkingDirectory = (Resolve-Path (Join-Path (Split-Path $env:TARGET) '..\..')).Path; $s.WindowStyle = 7; $s.Save()"

echo Shortcut created in the Startup folder.
echo Uvicorn will start hidden in the background when you sign in.
echo App URL: http://127.0.0.1:8585
