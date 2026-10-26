@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Abre Chromium contra una pagina local temporal. No llama a una API IA.
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta instalar-EXTRAS.cmd primero.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" test_browser.py
pause
