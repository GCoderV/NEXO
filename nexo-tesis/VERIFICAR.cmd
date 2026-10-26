@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if defined PYEXE goto check
py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto check
python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto check
echo No se encontro Python 3.11+. No se instalo nada.
pause
exit /b 1
:check
%PYEXE% verificar_instalacion.py
echo.
pause
