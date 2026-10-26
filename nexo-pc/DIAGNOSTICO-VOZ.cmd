@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Solo diagnostico de interpretes. No instala, descarga ni abre el microfono.
echo Muestra rutas locales de Python; no lee claves ni conversaciones.
py -3 voice_setup.py --diagnose
pause
