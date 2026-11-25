@echo off
chcp 65001 >nul
title Восстановление базы отчётов из резервной копии
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=python
where python >nul 2>&1 || set PY=py -3

echo ВНИМАНИЕ: база отчётов будет заменена содержимым выбранной копии.
echo Текущая база перед этим сохранится в папке копий как before_restore_....sqlite3
echo Сервис должен быть остановлен (файл "Остановить сервис.bat").
echo.
%PY% backup.py list
echo.
set /p NAME="Введите имя файла копии (например reports_20261116_155339.sqlite3) или Enter для отмены: "
if "%NAME%"=="" (
  echo Отменено.
  pause
  exit /b 0
)
choice /C YN /M "Восстановить базу из %NAME%? Y - да, N - нет"
if errorlevel 2 (
  echo Отменено.
  pause
  exit /b 0
)
%PY% backup.py restore "%NAME%"
echo.
pause
