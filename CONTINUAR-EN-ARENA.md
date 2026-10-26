# Continuar en una sesión limpia de Arena

## Mensaje para pegar al nuevo agente

> Lee README.md, CONTINUAR-EN-ARENA.md, AGENTS.md, contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md y contexto/CONTINUIDAD-COPILOT-IMPLEMENTACION.md de este repositorio. Conserva separados Nexo PC 0.6.0 y Nexo Tesis 0.4.0 (desarrollo 0.4.1-dev). El diagnóstico de continuidad de Microsoft 365 Copilot está terminado y la corrección está implementada localmente; lo pendiente es verificarla con la sesión real del usuario, siguiendo la prueba de aceptación. No rehagas el diagnóstico ni instales todo; verifica primero el respaldo y el entorno. Usa el skill REA solo cuando corresponda. No solicites tokens, contraseñas ni exportaciones de URLs autenticadas. Trabaja en español y no presentes mocks como pruebas reales de Windows o Microsoft.

## Componentes y estado real

- **nexo-pc/**: bot de escritorio Windows, código 0.6.0. Voz local, funciones generales y módulo académico piloto anterior. No sustituir este proyecto por el bot académico separado.
- **nexo-tesis/**: aplicación académica independiente, versión entregada 0.4.0. Biblioteca local de archivos, extractos autorizados, propuestas de reglas de guía, Word nativo con revisión, contexto compacto, referencias Copilot no verificadas y continuidad optativa experimental.
- **.agents/skills/reverse-engineer-anything/**: skill original con metadatos versión 42, referencias y licencia REA. Son instrucciones, no una conexión MCP automática.
- **rea-arena/**: adaptador local Python para usar REA desde herramientas de terminal. No es un conector nativo de Arena.
- **rea-setup/**: restauración de REA 6.7.0 y Node con package-lock. `restore.sh` instala dependencias: revisar el plan y obtener aprobación antes de ejecutarlo.
- **releases/**: ZIP original Nexo PC 0.6.0 (actualización), ZIP Nexo Tesis 0.4.0, y 0.3.1 de Tesis para comparación/regresiones. No incluirlos en otro instalador por defecto.

No hay una **versión publicada** nueva: el árbol de desarrollo de `nexo-tesis/` incorpora la corrección local (0.4.1-dev) descrita en `contexto/CONTINUIDAD-COPILOT-IMPLEMENTACION.md`. Sí hay un paquete Windows **de desarrollo**, listo para usar, en `releases/nexo-tesis-v0.4.1-dev-windows.zip`: se descomprime y se abre con doble clic en `INICIAR-TESIS.cmd`, que se autoverifica antes de arrancar. Fue construido sin red y validado con las pruebas locales; no es una release ni está verificado con Microsoft. Requiere Python 3.11+ con Tkinter en el equipo; no instala nada. Los ZIP originales 0.4.0/0.3.1 siguen intactos. El análisis original, que no se repite aquí, está en `contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md`.

## Pendiente prioritario: Copilot

**Estado de la continuación (2026-10-26):** las seis causas confirmadas del diagnóstico tienen corrección en código: persistencia por defecto, sin rotación a los 40 turnos, conservación de IDs ante errores y reanudaciones, identidad de cuenta independiente de la generación de credencial, cabecera de afinidad aislada para prueba A/B y mensajes incrementales después de verificación explícita. Se añadieron decisión visible ante resultados inciertos, revocación explicada y estado del hilo en la interfaz. 305 pruebas locales pasan (2 omitidas); el guion Tk no se ejecutó en este entorno. **Falta la comprobación con la cuenta real del usuario**: un solo chat, recuerdo de datos, reinicios, renovación, cambio de proyecto/cuenta y comparación de la cabecera. No presentar esto como continuidad remota verificada.

El usuario aclaró que quiere conservar conversaciones y su historial, no tratar cada petición como una operación aislada de una API sin estado.

Hallazgos confirmados en 0.4.0:
1. `conversation_state.load` devuelve vacío si no se activó continuidad; está apagada por defecto.
2. Los hilos de 40 turnos se descartan por una regla local, no por un límite Microsoft comprobado.
3. Ciertos errores y reanudaciones descartan los IDs.
4. El cambio de generación de credencial puede desvincular el hilo.
5. La conexión usa una clave en la URL, pero no la cabecera `X-RoutingParameter-SessionKey` que una investigación externa propone para evitar bifurcaciones de backend.
6. Se envían instrucciones y contexto estructurado repetidamente.

Dirección propuesta: hilo estable por proyecto/cuenta, recuperación sin duplicación ni reinicio silencioso, prueba aislada de afinidad de backend y mensajes incrementales después de verificar continuidad. No esconder el problema con chats temporales ni borrar conversaciones. Revocar archivos requiere atención especial: lo enviado permanece en Microsoft; podría requerir un hilo limpio, explicado y autorizado.

La cabecera es evidencia de terceros, no verificación propia. No cambiar login/captura, modelos, licencias o permisos aprovechando esta corrección. No instalar ni ejecutar el proxy de referencia. El informe contiene enlaces y criterios de aceptación.

## Restricciones que deben conservarse

- Login y captura pasiva de M365 Copilot funcionan según el usuario. Preferencia por sockets propios, no automatizar el DOM de chat. No confundir Microsoft 365 Copilot con GitHub Copilot.
- No pedir tokens/URLs autenticadas, no compartir credenciales, no introducir pagos implícitos.
- Rotación únicamente sobre rutas habilitadas, configuradas y autorizadas. Ollama se selecciona manualmente; no pasar de Ollama a nube sin autorización.
- Mantener proyectos e historial, evitar preguntas repetidas y extraer juntos los datos explícitos del usuario.
- Autonomía con presupuesto, cancelación y avance real; no quedarse en promesas. No reiniciar tareas automáticamente al abrir la app.
- Word mediante Microsoft Word nativo, vista previa y aprobación. No reemplazar contenido silenciosamente, aceptar revisiones, cambiar autoría ni usar python-docx como sustituto oculto. Probar primero en una copia.
- No inventar resultados, referencias, cantidades o conclusiones. Un diagnóstico no equivale a resultados de intervención ni obliga a capítulos empíricos finales en un anteproyecto.
- No enviar archivos solo por recibirlos. Mantener permisos por destinatario, procedencia y avisos de cobertura. Sin OCR ni subida nativa de archivos implementados.
- No asumir institución/nivel/método obligatorios en Nexo Tesis. El piloto integrado en Nexo PC es un caso anterior, no una restricción universal.
- Paquetes para el usuario: runtime limpio, README y licencias necesarias. Este respaldo de desarrollo incluye pruebas y contexto porque se pidió continuar el desarrollo en otra sesión.
- Instalación de dependencias: plan/alcance y aprobación previos, verificación posterior. No reemplazar Python principal ni instalar motores nativos opcionales sin autorización.

## Validación anterior y restauración

Informe histórico: `contexto/validacion-entrega-v0.4.0.json`. Para 0.4.0 se registraron 274 unidades aprobadas/2 omitidas y 98 comprobaciones funcionales Tk + 2 capturas; pruebas nativas con dobles. No equivalen a Word COM real, DPAPI, inferencia autenticada o continuidad Microsoft. No se repitió esa campaña al preparar este respaldo.

1. Ejecutar `python tools/verificar_respaldo.py` sin red.
2. Leer los README de cada componente. No arrancar las dos aplicaciones como servidores web: son interfaces Tk de escritorio Windows.
3. Las dependencias y procesos del entorno anterior no viajan en Git. El modelo Vosk de unos 40 MB tampoco está en este respaldo; `tools/recuperar_modelo_voz.py` lo obtiene de la URL oficial únicamente con `--descargar`, verifica SHA-256 y no instala paquetes. Para modificar código no hace falta descargarlo.
4. Si se clona en otra carpeta, `python tools/restaurar_sesion.py` muestra cómo copiar los componentes a `/home/user`. Solo `--aplicar` escribe y se niega a sobrescribir un destino distinto.
5. Algunas pruebas históricas utilizan `/home/user/nexo-tesis-v0.3.1-windows.zip` y PowerShell en una caché. El restaurador coloca los ZIP de referencia en la raíz; no instala PowerShell ni Xvfb. Revisa requisitos antes de ejecutar las pruebas.
6. `python rea-arena/rea_arena.py status` consulta disponibilidad. Para analizar código fuente normal, no hace falta REA. No ejecutar `analyze` con restauración implícita antes de aprobar descargas.

## Privacidad y GitHub

El destino recomendado es un repositorio **privado**. No se han copiado sesiones de usuario, bases de datos, credenciales ni perfiles de navegador. El código/ZIP de Nexo PC conserva su piloto académico integrado, con institución, centro educativo y diagnóstico agregado; no debe confundirse con contenido listo para publicar públicamente. Los paquetes de release se conservan sin modificar. Este respaldo no contiene conversaciones completas de Arena ni datos del PC del usuario.

En la sesión que creó este respaldo, el conector GitHub devolvió `unsupported` y no había autenticación Git disponible. **No se hizo push ni se creó un repositorio remoto.** Comprobar de nuevo el acceso real en la nueva sesión antes de afirmar que hay conexión; no asumir que este estado seguirá igual.
