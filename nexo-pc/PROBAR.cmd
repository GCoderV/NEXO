@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Pruebas de Nexo: archivos temporales y modelo simulado. Sin clave API.
echo En Windows incluye PowerShell inocuo y DPAPI con un secreto de prueba.
echo No accede a tus claves ni usa una API real.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m unittest -v test_nexo test_upgrade test_powershell_output test_browser_contract test_voice test_voice_setup test_continuity test_academic
) else (
  py -3 -m unittest -v test_nexo test_upgrade test_powershell_output test_browser_contract test_voice test_voice_setup test_continuity test_academic
)
pause
