@echo off
setlocal
title Folio Local OCR Studio
cd /d "%~dp0"
echo Folio Local OCR Studio - ThinkHomeo.in
echo Website: https://thinkhomeo.in/
echo Dependencies are checked before startup. Setup opens if something is missing.
echo Keep this window open while using Folio. Close it to stop the foreground server.
call "%~dp0folio_bootstrap.bat" --launch %*
if errorlevel 1 pause
