@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py -3 -c "import sys,tkinter,sqlite3; assert sys.version_info >= (3,11)" >nul 2>&1
  if errorlevel 1 (
    echo Nexo Tesis requiere Python 3.11 o superior con Tkinter y SQLite.
    echo No se instalo ni modifico ningun Python. Usa tu instalacion compatible existente.
    echo Si falta, instala Python desde python.org con el lanzador py y Tcl/Tk.
    pause
    exit /b 1
  )
  py -3 app.py
)
if errorlevel 1 (
  echo No se pudo iniciar. Conserva el error sin compartir claves ni datos personales.
  pause
  exit /b 1
)
