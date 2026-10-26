@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Abre una interfaz de PRUEBA con modelo simulado y archivos temporales.
echo No usa tus credenciales ni abre el microfono. No cierres las ventanas mientras se ejecuta.
echo Las pruebas de copiar y pegar sustituyen el contenido del portapapeles por texto de prueba.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" test_gui.py
  ".venv\Scripts\python.exe" test_voice_gui.py
  ".venv\Scripts\python.exe" test_continuity_gui.py
) else (
  py -3 test_gui.py
  py -3 test_voice_gui.py
  py -3 test_continuity_gui.py
)
pause
