@echo off
chcp 65001 >nul
title Остановка сервиса отчётов
set PORT=8600

set FOUND=
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set FOUND=%%p
)
if not defined FOUND (
  echo Сервис не запущен.
  pause
  exit /b 0
)

echo Сервис работает (процесс %FOUND%, порт %PORT%).
choice /C YN /M "Остановить сервис? Y - да, N - нет"
if errorlevel 2 exit /b 0

taskkill /PID %FOUND% /T /F >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Не удалось остановить процесс %FOUND%.
) else (
  echo Сервис остановлен.
)
pause
