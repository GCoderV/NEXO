@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Pruebas con proyectos temporales, respuestas simuladas y Word simulado.
echo No utiliza tus claves ni toca Word real. Incluye un servidor HTTP temporal SOLO local para probar transporte.
echo En Windows prueba DPAPI con un secreto inventado y analiza la sintaxis PowerShell sin ejecutar Word.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m unittest discover -s tests -v
  if errorlevel 1 goto fail
  ".venv\Scripts\python.exe" test_ui.py
) else (
  py -3 -m unittest discover -s tests -v
  if errorlevel 1 goto fail
  py -3 test_ui.py
)
if errorlevel 1 goto fail
echo Pruebas terminadas. No equivalen a validar Word real o calidad de un modelo.
pause
exit /b 0
:fail
echo Una prueba fallo. Conserva el mensaje y no compartas datos privados.
pause
exit /b 1
