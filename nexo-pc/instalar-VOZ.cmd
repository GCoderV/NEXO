@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Cierra Nexo antes de instalar los componentes opcionales de voz.
echo Este instalador busca un Python compatible YA instalado.
echo No reemplaza Python 3.15 ni cambia el Python usado por la interfaz.
py -3 voice_setup.py
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo No se completo la preparacion de voz. Revisa el mensaje concreto anterior.
  echo Puedes ejecutar DIAGNOSTICO-VOZ.cmd sin instalar ni descargar nada.
)
pause
exit /b %RESULT%
