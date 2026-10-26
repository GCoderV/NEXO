@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Pruebas academicas: datos temporales, Word simulado. No abre ni modifica Word real.
echo La interfaz de prueba puede cambiar el portapapeles. No cierres sus ventanas.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m unittest -v test_academic
  if errorlevel 1 goto fail
  ".venv\Scripts\python.exe" test_academic_gui.py
) else (
  py -3 -m unittest -v test_academic
  if errorlevel 1 goto fail
  py -3 test_academic_gui.py
)
if errorlevel 1 goto fail
echo Pruebas terminadas. Esto NO valida Word nativo.
pause
exit /b 0
:fail
echo Una prueba fallo. Copia el mensaje sin datos privados.
pause
exit /b 1
