@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalara en .venv: Playwright/Chromium, PyAutoGUI, Pillow, pyperclip y pywinauto.
echo Descarga dependencias externas. No necesita administrador.
echo No instala ni configura un servicio de control remoto.
choice /C SN /M "Continuar"
if errorlevel 2 exit /b 0
py -3 -c "import sys; assert sys.version_info >= (3,11)"
if errorlevel 1 goto error
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements-extras.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto error
echo Listo. Abre INICIAR.cmd. Habilita solo las herramientas que quieras probar.
pause
exit /b 0
:error
echo Instalacion incompleta. Revisa el error anterior y tu version de Python.
pause
exit /b 1
