# 0.6.0 — Tesis piloto

- Nuevo panel académico de seis pestañas; expediente editable del caso UCE, grado, Educación, investigación-acción.
- Evidencias diferenciadas; frecuencias opcionales validadas, sin inferir números desde texto narrativo.
- Cuatro actividades propuestas editables, con campos del PDF y vínculos al diagnóstico; duración pendiente.
- Registro manual de fuentes y revisión local. No certifica evidencia, APA ni cumplimiento UCE.
- Contexto por apartado al borrador del chat (máximo 5500 caracteres), sin envío automático ni selección de Word; Planificar, todas las herramientas desactivadas.
- Puente nativo Word experimental: confirmar documento, leer selección y aprobar comentario. Hash, rango y ventana; sin reemplazos, guardado ni reintentos automáticos.
- Guardado atómico del expediente, copia anterior, bloqueo y detección de modificaciones externas.
- Entrega incremental: conserva el modelo de voz y los entornos existentes. No instala dependencias nuevas.

# Nexo PC 0.5.0 — continuidad, ahorro y modelo de voz incluido

- Cambiar modelo, proveedor o endpoint local ya no bloquea el chat ni exige Nueva. Mismo ID, historial visible y checkpoints. Conversión a texto portable y archivo incremental de protocolos originales, sin repetir herramientas ni reutilizar permisos. Consentimiento al enviar contexto a otro proveedor.
- Ahorro predeterminado: extractos locales, objetivo de 12 000 caracteres de historial, sin llamada extra de resumen. Última petición y bloque de herramientas completos; firmas Gemini intactas dentro del mismo modelo. Historial guardado sin compactar; se avisa al utilizar extractos. Límite duro configurable. No garantiza recordar cada detalle ni eludir cuotas.
- Contadores acumulados con los tokens reportados por Groq, Gemini y Ollama, no estimaciones presentadas como saldo.
- Modelo español oficial incluido (39 817 833 bytes, Apache 2.0, SHA-256 fijado). Detección de rutas obsoletas, padres y anidamientos. Preparación automática offline sin elegir carpetas, con respaldo si hay copia incompleta. Reparación local desde Ajustes → Voz.
- Conserva `.venv-voz`, Python principal y dependencias fijadas de 0.4.1; no requiere reinstalar componentes ya disponibles. Permisos de Windows y voces instaladas siguen dependiendo del sistema.
- 204 pruebas unitarias definidas: 201 correctas y 3 omitidas en Linux. 27 comprobaciones Tk base, 36 de ratón/voz, 16 nuevas de continuidad/preparación y 9 Chromium correctas.
- Prueba adicional real: extracción offline del modelo incluido, corrección de ruta y arranque de Vosk en entorno separado, pausado sin abrir el micrófono.
- Pendiente: APIs autenticadas, instalación/audio nativos de Windows y precisión del dictado del usuario. Los ensayos de continuidad usan respuestas simuladas, no avalan calidad ni coste con un modelo real.

# Nexo PC 0.4.1 — corrección del instalador de voz

- Corrige la selección de Python cuando `py -3` inicia 3.15 pero ya existe CPython compatible, incluido Astral/uv 3.11.16. Lee rutas del lanzador, no interpreta sus etiquetas como órdenes de instalación.
- Entorno `.venv-voz` exclusivo para audio. Se conservan el Python predeterminado y `.venv` principal; no se instala otro intérprete ni se exige Tk en el Python de voz.
- Los tres procesos de voz (reconocimiento, lectura y listado de voces) usan el nuevo entorno en modo aislado. Compatibilidad con instalaciones anteriores si no hay entorno separado; aviso claro si está incompleto.
- Comprobación de versión, arquitectura del proceso y ABI; consentimiento antes de instalar dependencias/modelo. Un entorno incompatible se respalda únicamente después de otra confirmación.
- Diagnóstico de componentes en el Python de audio y nuevo `DIAGNOSTICO-VOZ.cmd`, de solo lectura. Se mantiene el bloqueo de instalación con Nexo abierto.
- 176 pruebas unitarias definidas: 173 correctas y 3 omitidas en Linux, incluidas 29 regresiones nuevas. 27 comprobaciones Tk base, 36 de ratón/voz y 9 Chromium correctas.
- Arranque adicional del reconocedor con Vosk real y modelo real en entorno virtual separado de Linux: inicializado y pausado sin abrir el micrófono; el Python principal no tenía Vosk. Metadatos de PyPI confirman wheels de los paquetes fijados para CPython 3.11–3.14 Windows x64.
- Pendiente: ejecución del instalador en Windows, micrófono y TTS nativos en el equipo del usuario. Las pruebas simuladas de su selección de versiones no sustituyen esa comprobación.

# Nexo PC 0.4.0 — ratón y conversación por voz

- Clic derecho para copiar selección/mensaje, pegar, cortar y seleccionar todo; botones Copiar y Leer en las respuestas y Pegar junto al editor.
- Botón Mic para activar/apagar dictado continuo local en español. Envío después de una pausa configurable, varios turnos, cuenta atrás y comandos hablados explícitos.
- Lectura mediante voces nativas instaladas de Windows, es-MX preferido, sin cambio de idioma silencioso. Botón para detener reproducción.
- Pausa de escucha durante trabajo, lectura, revisiones y pérdida de foco; descarte de eventos antiguos y cancelación de envíos pendientes. Micrófono apagado al arrancar.
- Revisión manual de transcripciones con confianza baja. No hay aprobación de planes o permisos por voz.
- Acceso separado a Win+H; no se afirma controlar su micrófono ni usar ese motor en la conversación continua.
- Instalador opcional de voz y modelo español (unos 40 MB), comprobación SHA-256 y extracción acotada. Sin descargas al abrir el chat.
- Configuración de voz en una cuarta pestaña; mantiene tamaño compacto de 480 × 400 y no recorta los botones.
- 147 pruebas definidas: 144 correctas y 3 omitidas en Linux. 27 comprobaciones base de interfaz, 36 de ratón/voz y 9 de Chromium correctas. Modelo Vosk real cargado y probado solo con silencio sintético.
- Pendiente: voz y audio reales en Windows, precisión con el acento del usuario, Win+H, DPAPI y otras pruebas nativas. No se ha grabado al usuario ni utilizado un servicio remoto de voz.

---

# Nexo PC 0.3.2 — contrato de navegador

- Corrige la incompatibilidad entre `browser(action=open,url=...)` y el esquema anterior que exigía value/text.
- Admite url para abrir, selector para click/fill, text obligatorio para fill y action solamente para inspect/close.
- Mantiene los argumentos anteriores; valida campos incompatibles, URL, tipos y alias contradictorios antes de ejecutar.
- Mantiene bloqueos por PLAN, permisos deshabilitados y rechazo humano.
- Comunica tool_use_failed sin ejecutar failed_generation ni repetir automáticamente comandos previos.
- Refuerza las instrucciones de planificación, rutas de Escritorio y verificación de documentos; no incorpora aún el agente académico ni un módulo especializado de Word.
- 120 pruebas definidas: 117 correctas, 3 omitidas por requerir Windows. 27 comprobaciones de interfaz y 9 de Chromium real correctas.
- No hubo llamada a una API autenticada ni creación de Word en Windows durante esta validación. Las pruebas de API usan respuestas simuladas.
- No cambia el formato de sesiones, perfiles o claves. Incluye la corrección CLIXML de 0.3.1.

---

# Nexo PC 0.3.1 — corrección de salida PowerShell

- Suprime mensajes de progreso ordinarios como «Preparando módulos para el primer uso».
- Solicita formato de texto y codificación UTF-8.
- Captura stdout y stderr por separado, preservando errores y advertencias.
- Filtra solo progreso CLIXML válido y reconocido; conserva texto ordinario, XML desconocido y bloques truncados.
- Decodifica escapes de cadenas CLIXML sin doble decodificación.
- No trata un código 0 o un `True` aislado como verificación de la tarea.
- 98 pruebas definidas: 95 correctas en Linux y 3 pendientes de Windows. Interfaz y navegador se volvieron a probar (27 y 6 comprobaciones).
- Sin cambios de formato de perfiles, claves, sesiones o checkpoints. No necesitas volver a introducir las claves guardadas por 0.3.0.

---

# Nexo PC 0.3.0 — cambios respecto de 0.2.0

## Solicitudes implementadas

- Interfaz de conversación más despejada; historial y configuración fuera de la ventana principal.
- Tres secciones de configuración: Modelos, Permisos y Avanzado.
- Tamaño mínimo reducido de 950 × 740 a 480 × 400 en el entorno de prueba, con disposición compacta para mantener accesibles Enviar y Detener.
- Enter envía; Shift+Enter inserta una línea. Tecla Enter del teclado numérico incluida.
- Ruta de envío y estados del botón comprobados con Tk real. Las validaciones fallidas antes de iniciar mantienen el texto en el editor.
- Aprobación por plan para una tarea completa, en lugar de una confirmación por archivo o paso ya autorizado.
- Interruptor Autónomo activable/desactivable; no se restaura al arrancar.
- Acceso amplio opcional y explícito para cubrir PowerShell, escritorio y clics/rellenos sin revisión individual. No es un sandbox.
- Claves persistentes por combinación proveedor/modelo, con DPAPI en Windows, botón de olvido y opción de memoria solamente.
- Recuperación del perfil al abrir una sesión; corrección de la prioridad de un valor vacío en memoria frente a una clave guardada.
- Ollama local: descubrimiento de modelos, API de chat y llamadas a herramientas, sin clave y sin fallback remoto.
- Límites por tarea, espera de API, tamaño de contexto y tamaño de texto configurables.
- Resúmenes de herramientas en la conversación y vista separada de detalles.

## Revisiones adicionales

- No duplicar tareas al pulsar Enter durante una ejecución.
- Rechazar un plan termina la tarea en lugar de volver a pedirlo.
- Las autorizaciones de plan no se recuperan tras reiniciar ni se trasladan a una nueva tarea.
- Se conservan checkpoints y comprobación de hash también en autónomo.
- Claves conocidas redactadas al persistir contenido de conversación; sin alterar las claves estructurales del JSON.
- Sin sustitución de una clave vacía de Ollama dentro de textos de error.
- Conexión loopback de Ollama sin proxies ni redirecciones a otro servidor.
- Aviso y recuperación de claves fallidos sin alternativa insegura de texto plano.
- Errores de callbacks de interfaz visibles, con omisión de claves conocidas.
- Scripts de pruebas e instrucciones de actualización incluidos; no se borran sesiones anteriores.

## Validación y límites

78 pruebas automatizadas correctas; 2 omitidas por requerir Windows. 27 comprobaciones de Tk real y 6 de Chromium real correctas en Linux.

APIs de modelos simuladas; transporte Ollama probado mediante un servidor HTTP de prueba, no un modelo real. DPAPI real, PowerShell y ejecución completa en Windows pendientes. No se realizó ninguna instalación en el PC del usuario.
