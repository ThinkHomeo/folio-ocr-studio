@echo off
setlocal
title Folio Setup
cd /d "%~dp0"
echo Folio Setup - ThinkHomeo.in
echo Website: https://thinkhomeo.in/
call "%~dp0folio_bootstrap.bat" %*
if errorlevel 1 pause
