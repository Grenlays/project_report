@echo off
chcp 65001 >nul
title Сервис отчётов по проектам
cd /d "%~dp0"
set PORT=8600
set REPORT_PORT=%PORT%
set PYTHONIOENCODING=utf-8

rem --- Python ---
set PY=
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if not defined PY (
  echo [ОШИБКА] Python не найден. Установите Python 3.12 или новее.
  pause
  exit /b 1
)

rem --- уже запущен? ---
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Сервис уже запущен. Открываю его в браузере...
  start "" "http://localhost:%PORT%/"
  timeout /t 3 >nul
  exit /b 0
)

echo ============================================================
echo  Сервис отчётов по проектам разработки
echo  Адрес на этом ПК:   http://localhost:%PORT%/
echo  Адрес для коллег:   http://%COMPUTERNAME%.neurosoft.ru:%PORT%/
echo.
echo  Не закрывайте это окно, пока сервис нужен.
echo  Остановить: закрыть окно или нажать Ctrl+C.
echo ============================================================
echo.

start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:%PORT%/"
%PY% run.py

echo.
echo Сервис остановлен.
pause
