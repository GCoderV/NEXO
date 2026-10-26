# De la investigación a Nexo PC 0.5.0

## Qué se estudió

Referente: **Cline, extensión oficial 4.1.25**, publicada el 16 de octubre de 2026.

- VSIX: https://github.com/cline/cline/releases/download/v4.1.25/cline-4.1.25.vsix
- SHA-256 verificado contra el digest publicado: `aac83af0513f5168372905c02a72eee3835d32a53b9d635d3b055ed4a7bd71fc`.
- Motor acotado recuperado del bundle: intervalo de bytes `[11230969, 11262552)`.
- Hash del fragmento original: `b3beb979ed7536618784f7fbcfe54de832065dcd0dc54c6f0017c46d87968762`.
- Evidencia REA sobre ese fragmento: `ev_b0d81e90b780b44d094109e4d03b11782f31aeda66ba582b84cd6f018287f128`.

El análisis completo del bundle agotó el heap asignado. El análisis acotado parseó un archivo, visitó 7 665 nodos AST y no encontró errores de parseo, **con cobertura parcial**. No se convierte ese resultado parcial en una afirmación de comprensión total del producto.

Se ejecutaron 15 pruebas de componentes sobre métodos recuperados del bundle, con objetos de estado, callbacks y herramientas inocuas controlados. Los resultados y las posiciones están en `referencia/contract-tests.json` y `referencia/extraction.json`. El estudio completo se entregó por separado como `estudio-cline-rea.zip`.

**El usuario decidió omitir la prueba del Cline original en su Windows.** Por eso no hay un benchmark end-to-end original-versión propia, ni una afirmación de equivalencia global.

## Cómo se tradujo a nuestro código

| Observación / requisito | Implementación independiente de Nexo | Verificación |
|---|---|---|
| Separar preparación y ejecución de herramientas | `runtime.py` prepara y revisa el lote antes de ejecutar en orden | Test de orden de fases con acciones reales sobre archivos temporales |
| Denegar si falta o falla la aprobación | Revisión explícita en modo estricto y al conceder planes: solo se acepta el booleano `True`; autonomía y permisos de tarea son políticas independientes del host | Ausencia de revisor, excepción, rechazo y respuesta no booleana |
| No invocar una acción bloqueada | La política de modo y módulos se evalúa antes del callback y de la ejecución | PLAN, módulos deshabilitados, rechazo y cancelación |
| Vincular resultados con llamadas concretas | Adaptadores Gemini/Groq conservan identificadores y mensajes de herramientas | Formato de llamadas, firmas Gemini y recuperación de protocolos pendientes |
| Plan/Act como funciones del producto de referencia | Política propia más acotada: PLAN permite únicamente `list_files` y `read_file` | Bloqueo incluso cuando el modelo simulado pide escribir |
| Checkpoints documentados en Cline | Diseño propio simplificado por archivo, con hash anterior/posterior y comprobación de conflictos | Restauración de creación, sobrescritura, cadena, conflicto y copia corrupta |
| Historial/sesiones documentados | JSON local con escritura atómica y estado de llamadas pendientes | Reapertura y continuación, recuperación sin repetición, capturas omitidas al persistir |
| Terminal y navegador como herramientas del agente | Adaptadores propios y separados de la política | Navegador real en Linux; PowerShell pendiente de prueba Windows |

Las decisiones de implementación sobre Plan/Act, checkpoints, almacenamiento y escritorio **no fueron probadas como equivalentes a Cline**. Son requisitos inspirados en sus funciones y respaldados por nuestras propias pruebas. No heredamos la madurez ni las garantías de Cline por estudiar un fragmento suyo.

## Diferencias deliberadas

- Sin SDK, runtime ni módulos Cline en la aplicación.
- En 0.2 era obligatoria la aprobación por acción. En 0.3, por petición del usuario, se añadieron aprobación por plan y autonomía acotada. Las autorizaciones explícitas conservan el requisito de booleano `True`; no se presentan estas políticas nuevas como equivalentes a las de Cline.
- Ejecución secuencial en esta versión; no grupos paralelos aunque el motor estudiado los admita.
- Checkpoints **por archivo editado**, no un repositorio sombra ni snapshot de todo el workspace.
- Navegador separado que se cierra al terminar el turno, no navegador persistente entre sesiones.
- Sin herramientas MCP, subagentes, tareas programadas ni ejecución distribuida todavía.
- El control visual es un módulo opcional propio y experimental; no una capacidad universal validada por Cline.
- No hay sandbox de sistema operativo: los permisos de archivos no limitan lo que puede hacer un comando PowerShell aprobado.

## Qué se reutilizó

Se reutilizaron helpers propios del prototipo anterior para conectarse a las APIs y operar herramientas. Se sustituyó el bucle anterior por `runtime.py`, se añadieron `storage.py`, modos, diferencias, checkpoints, recuperación y una interfaz nueva.

Esto no es un proceso de clean-room formal: quien implementó leyó los métodos de referencia. Sí es una implementación independiente: no se copió su runtime ni se incluyeron sus clases en la aplicación. Los archivos de `referencia/` contienen resultados y metadatos del estudio, no código del producto Cline.

## Cambios propios de 0.3

- `permissions.py`: aprobación por plan mediante `submit_plan`, política por acción y autonomía. Alcance técnico por herramientas/carpeta/presupuesto, no verificación semántica del plan.
- `settings.py`: perfiles por proveedor/modelo y cifrado DPAPI mediante API pública de Windows. No deriva del código Cline ni incluye un cifrado casero.
- `adapters.py`: API nativa de Ollama, listado de modelos, protocolo de herramientas y restricción loopback. Referencias técnicas: https://docs.ollama.com/api/chat y https://docs.ollama.com/api/tags .
- `app.py`: interfaz Tk reestructurada, ajustes separados, Enter/Shift+Enter y ventanas compactas. Sin nueva dependencia de interfaz ni servidor web.
- No se incorporó un conector remoto de Arena ni se instaló nada en el PC del usuario durante la construcción.

## Corrección propia de 0.3.1

`powershell_output.py` añade preparación de la invocación y lectura conservadora de CLIXML. Se separaron stdout y stderr; no se convierte código de salida cero en prueba de éxito. Las nuevas pruebas usan fixtures de progreso/error y un proceso simulado; la prueba nativa Windows está incluida pero no ejecutada aquí.

## Corrección propia de 0.3.2

El contrato de navegador admite url/selector y llamadas anteriores con value. Validación por acción antes de pedir permiso y antes de ejecutar; alias contradictorios rechazados. El HTTP 400 proporcionado por el usuario se reproduce con fixtures de respuesta del proveedor. No se ejecuta ni reintenta failed_generation. Se comprobó que comandos anteriores no se repiten al reanudar. Las instrucciones PLAN orientan a preparar un plan útil sin habilitar herramientas de escritura. No se añade un módulo Word especializado.

## Componentes estudiados y utilizados para 0.4.0

- Se revisó la documentación de reconocimiento continuo de Microsoft antes de decidir la integración: las APIs SpeechRecognition documentan identidad de paquete y restricciones de idioma de PC. No se prometió que Win+H ofreciera una API de conversación continua para esta aplicación Tk sin empaquetar.
- Se utiliza el motor maduro **Vosk 0.3.45** con el modelo oficial `vosk-model-small-es-0.42` descargado opcionalmente del catálogo del proyecto. No se implementó desde cero un reconocedor ni se presenta el modelo general como entrenado específicamente para México.
- Se revisaron el ejemplo oficial de **PyWinRT** y los stubs de sus paquetes 3.2.1 para los nombres reales de SpeechSynthesizer/MediaPlayer, eventos, selección de voz y cierre. Las proyecciones se instalan desde PyPI; no se copió su motor.
- `voice.py`, `voice_ui.py`, `speech_recorder.py`, `speech_native.py`, `clipboard_ui.py` y `prepare_voice.py` son adaptadores y lógica propios: consentimiento, estado, temporizador, interfaz, procesos separados, instalación y portapapeles.
- Referencias: https://learn.microsoft.com/en-us/windows/apps/develop/input/speech-recognition ; https://learn.microsoft.com/en-us/windows/apps/develop/input/enable-continuous-dictation ; https://github.com/pywinrt/pywinrt ; https://alphacephei.com/vosk/models .
- Vosk, sounddevice, PyWinRT y el modelo conservan sus licencias propias. Los paquetes ejecutables de esas dependencias se instalan opcionalmente desde sus fuentes. Desde 0.5.0, el ZIP de Nexo sí redistribuye el modelo de datos español original bajo Apache 2.0, con licencia y atribución. El modelo conserva su README al extraerlo.
- El SHA-256 del modelo se fijó al descargarlo de la URL HTTPS del proveedor: no se presenta como una firma digital emitida por éste.

## Pruebas de esta versión

- `test_nexo.py`, `test_upgrade.py`, `test_powershell_output.py`, `test_browser_contract.py`, `test_voice.py`, `test_voice_setup.py` y `test_continuity.py`: 204 casos definidos; 201 correctos en Linux y 3 omitidos (PowerShell básico, sus canales y DPAPI real requieren Windows).
- `test_gui.py`: 27 comprobaciones con Tk real, respuestas simuladas y protector inyectado de prueba, no DPAPI real.
- `test_voice_gui.py`: 36 comprobaciones de ratón y flujo de voz con Tk/portapapeles reales; ASR, TTS y Win+H simulados.
- `pruebas-modelo-voz.json`: Vosk real cargado, diez segundos de silencio sintético sin texto. Sin prueba de precisión con habla real.
- `test_browser.py`: 9 comprobaciones con Chromium real contra una página local controlada, sin un modelo de lenguaje; repetidas con esta versión.
- Transporte Ollama ejercitado sobre HTTP real hacia un servidor local de prueba del protocolo, no contra una instancia real de Ollama ni un modelo descargado.
- Sin llamada autenticada a una API real, porque no se proporcionaron claves.
- Sin ejecución de esta versión de la interfaz, control visual, captura de micrófono, reproducción nativa o Win+H en Windows en esta fase.

La atribución a Cline se limita al referente de investigación. Nexo PC no está afiliado ni respaldado por el proyecto Cline. El estudio previo no sustituye las pruebas de las funciones nuevas.

## Corrección 0.4.1: separación del intérprete de audio

Se reprodujo con fixtures el inventario comunicado: Python predeterminado 3.15.1 y Astral/uv CPython 3.11.16. `voice_setup.py` encuentra rutas y verifica cada intérprete mediante un proceso aislado antes de crear `.venv-voz`. `voice.py` utiliza ese entorno para sus tres procesos, sin mover la interfaz a un Python de uv que pudiera carecer de Tk. Se mantiene el mutex real de la aplicación y la confirmación previa.

`test_voice_setup.py` añade 29 regresiones de selección, consentimiento, respaldo/conservación y despacho. `pruebas-aislamiento-voz.json` documenta un arranque con modelo y Vosk reales en un entorno separado de Linux (dependencias de prueba previamente descargadas), sin abrir el micrófono. `pruebas-paquetes-voz.json` registra los nombres de wheels publicados y sus URLs de metadatos; no verifica exhaustivamente dependencias transitivas ni acredita instalación en Windows. No se afirma haber ejecutado nada en el equipo del usuario.

## 0.5.0 — continuidad y preparación automática

`conversation.py` conserva el chat y archiva únicamente los segmentos nativos nuevos al cambiar de modelo. Traduce el historial a texto, sin portar firmas ni llamadas ejecutables entre proveedores. El recorte para cada petición es una extracción local explícita sobre una copia; no sobrescribe la conversación. Mantiene el último bloque completo de herramienta/respuestas y la petición actual; no concede permisos nuevos.

`test_continuity.py`: 28 regresiones nuevas; `test_continuity_gui.py`: 16 comprobaciones con Tk real y proveedores/preparación simulados. Total actual: 204 unitarias, 201 correctas y 3 omitidas por requerir Windows.

El archivo original `vosk-model-small-es-0.42.zip` se distribuye sin modificar bajo Apache 2.0 (catálogo oficial consultado). El ZIP de entrega contiene el modelo en `models/`; se incluyen licencia y atribución. `voice_assets.py` detecta las ubicaciones acotadas y `prepare_voice.py` valida hash, extracción y componentes antes de respaldar/reemplazar una copia incompleta. `pruebas-modelo-automatico.json` documenta el ensayo offline con el ZIP y Vosk reales. No acredita micrófono o TTS en Windows.

`pruebas-ahorro-contexto.json` compara caracteres de una conversación sintética (231 280 → 10 552). Es una reducción del texto reenviado en ese fixture, NO un porcentaje medido de facturación, de tokens exactos ni de calidad de memoria. No se ha consultado una API autenticada.


## Extensión académica 0.6.0 — estudio y límites

Se conserva el estudio acotado de Cline y la implementación independiente del runtime anterior. Para el puente Word se estudiaron antes de programar las APIs y ejemplos oficiales de Microsoft: `Selection` (selección normal, rangos y limitaciones), `Range.Information` y `Comments.Add`. No se importó ni copió una implementación de un agente de tesis; no se afirma haber aplicado REA a Word ni equivalencia con complementos comerciales.

Fuentes consultadas:
- https://learn.microsoft.com/en-us/office/vba/api/word.selection
- https://learn.microsoft.com/en-us/office/vba/api/word.range.information
- https://learn.microsoft.com/en-us/office/vba/api/word.comments.add

La documentación recomienda rangos cuando no hace falta alterar la selección. Se usa selección únicamente para obtener el ámbito consentido; se duplica su rango para añadir un comentario. No se usan `Selection.TypeText`, aceptación de revisiones, `SaveAs` ni escritores externos de DOCX. `GetActiveObject` se limita al Word ya abierto; no habilita macros ni cambia políticas de Office. Script fijo y datos JSON por stdin, sin interpolar texto del documento en código.

El plan original prefería un complemento lateral con conector local como alternativa. Para este incremento se eligió **panel de Nexo + conector local Word/COM**, porque permite una primera operación nativa acotada sin desplegar un complemento web, certificados o un servidor. Es una elección de implementación piloto, no una compatibilidad ya demostrada. Las operaciones más extensas y un panel dentro de Word siguen pendientes.

El perfil se transcribió del PDF de tres páginas aportado por el usuario (incluido en `referencia-academica`), sin sustituirlo por una plantilla genérica APA. Se conserva estado de fuente aportada y reglas ambiguas pendientes. Los ejemplos del PDF no se trataron como datos hasta que el usuario aportó su tema y diagnóstico por separado.

Los tests de `WordBridge` y de la interfaz usan un transporte simulado: prueban protocolos, consentimiento y manejo de errores, **no el comportamiento real de Word ni la ausencia de defectos en COM**. La prueba nativa se requiere sobre copia local antes de usar documentos de trabajo. Las comprobaciones académicas son validaciones de datos/campos y advertencias explícitas, no verificación semántica exhaustiva ni búsqueda bibliográfica.
