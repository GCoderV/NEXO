@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>&1
  if errorlevel 1 (
    echo Instala Python 3.11 o superior desde https://www.python.org/downloads/windows/
    echo Incluye Tcl/Tk y el lanzador py. Luego vuelve a abrir este archivo.
    pause
    exit /b 1
  )
  py -3 app.py
)
if errorlevel 1 (
  echo No se pudo iniciar. Copia el error, pero NO compartas tu API key.
  pause
)
