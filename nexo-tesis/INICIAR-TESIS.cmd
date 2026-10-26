@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if defined PYEXE goto check
py -3 -c "import sys,tkinter,sqlite3; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto check
python -c "import sys,tkinter,sqlite3; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto check
echo --------------------------------------------------------------
echo  No se encontro Python 3.11+ con Tkinter y SQLite.
echo  No se instalo ni modifico ningun Python. Instala Python desde
echo  python.org (marca "tcl/tk and IDLE" y "py launcher") y vuelve
echo  a abrir INICIAR-TESIS.cmd.
echo --------------------------------------------------------------
echo.
pause
exit /b 1
:check
echo Comprobando el paquete sin red...
%PYEXE% verificar_instalacion.py
if errorlevel 1 (
  echo.
  echo La comprobacion fallo; no se abrira la aplicacion.
  pause
  exit /b 1
)
echo.
echo Iniciando Nexo Tesis 0.4.1-dev...
%PYEXE% app.py
if errorlevel 1 (
  echo.
  echo No se pudo iniciar. Conserva el error sin compartir claves ni datos personales.
  pause
  exit /b 1
)
