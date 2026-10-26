# Nexo PC 0.6.0 — Tesis piloto
## Ratón y voz · interfaz compacta · aprobación por plan · autonomía · Ollama

Nexo es nuestro agente local independiente para Windows. No es Cline con otro nombre ni una conexión remota a Arena. Esta actualización retoma el módulo académico sin retirar las funciones anteriores.

## Nuevo en 0.6.0: módulo Tesis

Pulsa **Tesis**: expediente UCE de investigación-acción, evidencias separadas de interpretaciones, plan de acción, registro de fuentes y comprobaciones locales sin consumir API. El caso incluye los 24 participantes y el diagnóstico aportado; no inventa datos, citas ni resultados.

**Lee `GUIA-TESIS.md` para actualizar y hacer la prueba de Word.** Esta entrega es un ZIP de **actualización sobre 0.5.0**; conserva `models`, `.venv` y `.venv-voz`. No repite el archivo de voz de 40 MB. Cierra Nexo y copia todo el contenido de `NexoPC` sobre tu carpeta actual; debe indicar 0.6.0 al iniciar.

Word: puente experimental nativo para leer una selección autorizada y añadir un comentario aprobado, sin sustituir párrafos ni guardar el documento. Probado con dobles de transporte en Linux, **no validado todavía con Word real en Windows**. Primera prueba sobre una copia local. No hay motor APA completo, búsqueda académica automática ni modelo Ollama especializado todavía.

Los apartados siguientes describen las funciones previas; sus instrucciones de **paquete completo 0.5.0** no convierten este ZIP de actualización en un paquete con modelo de voz.

## Nuevo en 0.5.0: mismo chat, menos contexto repetido y voz sin elegir carpetas

- **Cambia modelo o proveedor y continúa en la misma conversación.** No pulses Nueva. Se mantienen el identificador del chat, el historial visible, los archivos y los checkpoints. Al cambiar de proveedor se pide consentimiento para enviarle el contexto anterior. Las claves siguen siendo independientes por perfil.
- **Ahorro de tokens activado por defecto.** Se conserva todo el historial local; para cada solicitud se envían extractos antiguos y pasos recientes, sin gastar otra llamada en resumir. Objetivo de 12 000 caracteres de historial, además de instrucciones y esquemas de herramientas. El último bloque de herramientas y la petición actual se conservan completos; pueden superar el objetivo si son grandes. El límite duro sigue configurable en Ajustes → Límites.
- **El modelo español ya viene dentro del ZIP** (`models/vosk-model-small-es-0.42.zip`, unos 40 MB). Al pulsar Mic, Nexo encuentra la copia instalada aunque la ruta guardada esté obsoleta. Si no encuentra una copia completa, prepara la incluida automáticamente, sin red ni selector de carpetas. El micrófono continúa requiriendo consentimiento.
- Muestra tokens acumulados **reportados por las APIs**, cuando están disponibles. No es el saldo de tu cuenta ni una estimación de coste; las solicitudes fallidas pueden no informar consumo. Cambiar de modelo no garantiza renovar una cuota compartida del proveedor.

### Actualizar conservando lo que ya instalaste

1. Cierra Nexo y conserva una copia del programa y de `%USERPROFILE%\.nexo-pc`.
2. Extrae el ZIP completo. Copia **TODO el contenido de `NexoPC` sobre tu carpeta actual**, incluida la carpeta **models**, y acepta reemplazar archivos. No borres **`.venv` ni `.venv-voz`**. No ejecutes las dos copias simultáneamente.
3. Abre **INICIAR.cmd**; el título debe indicar **0.5.0**. Si los componentes de voz ya estaban instalados, no tienes que reinstalarlos. Pulsa Mic: resolverá la ruta y preparará los datos locales si hace falta.
4. Solo si faltan las bibliotecas de audio, cierra Nexo y ejecuta **instalar-VOZ.cmd**. Reutiliza tu Python compatible (incluido Astral/uv 3.11) en `.venv-voz`; no sustituye Python 3.15 ni cambia el Python de la interfaz. Esta instalación de dependencias sí requiere Internet y confirmación, pero no elegir una carpeta.

En una carpeta nueva tendrás que preparar allí los entornos opcionales. No copies entornos virtuales entre ubicaciones. Los permisos de micrófono y la instalación de voces de Windows no se fuerzan ni se modifican automáticamente.

## Funciones incorporadas en 0.4.0: copiar/pegar y conversación por voz

- **Copiar** en cada respuesta y menú de clic derecho para copiar, cortar, pegar y seleccionar todo.
- **Pegar** junto al editor; no envía el texto automáticamente.
- **Mic** activa o apaga una conversación continua por turnos, con transcripción local de español, envío opcional tras una pausa y lectura de respuestas con voces de Windows.
- **Leer** reproduce una respuesta o selección; el mismo botón detiene la voz.
- **Dictado Windows** abre Win+H sin abrir el teclado táctil. Es una opción separada, sin autoenvío y cuyo micrófono controla Windows.

Copiar y pegar funciona sin instalar nada más. Si ya instalaste la voz, pulsa Mic directamente. Solo si faltan componentes, cierra Nexo y ejecuta `instalar-VOZ.cmd`. Puedes revisar las voces disponibles en **Ajustes → Voz → Detectar voces instaladas**. La preferencia de lectura es **español de México (es-MX)**; no se sustituye por inglés si falta esa voz.

**Importante:** el reconocimiento continuo usa Vosk local en español general, no el motor Win+H ni un modelo certificado de acento mexicano. El audio no se guarda ni se envía a una API de voz; el texto enviado sí se transmite al proveedor de chat elegido. La escucha se pausa durante tareas, lectura, revisiones y pérdida de foco. El micrófono siempre arranca apagado. Las aprobaciones de seguridad no se aceptan por voz.

Consulta **[GUIA-VOZ.md](GUIA-VOZ.md)** para instalación, funcionamiento, privacidad, comandos hablados y límites de la opción nativa de Windows.

## 1. Actualizar desde versiones anteriores

1. **Cierra completamente la versión anterior.** Las dos versiones comparten una protección para evitar dos escritores simultáneos en Windows.
2. Conserva una copia de `%USERPROFILE%\.nexo-pc` si quieres poder volver al estado anterior de tus datos.
3. Extrae **todo** el ZIP en una carpeta nueva, por ejemplo `C:\NexoPC-0.5.0`. No ejecutes los archivos dentro del ZIP ni mezcles archivos de versiones diferentes.
4. Abre `INICIAR.cmd`. Necesita Python 3.11 o superior con Tcl/Tk y el lanzador `py`, igual que antes. No lo ejecutes como administrador.
5. Abre **Ajustes → Modelos** y configura tus perfiles. Si vienes de 0.2, tendrás que introducir las claves una primera vez; si vienes de 0.3.x o 0.4.x, se conservan sus perfiles y claves guardadas.

Las conversaciones y checkpoints continúan en `%USERPROFILE%\.nexo-pc`; el formato de sesiones sigue siendo compatible. El nuevo archivo `preferences.json` guarda preferencias, perfiles y claves protegidas. No se modifican tus documentos por instalar o abrir el programa.

Si utilizabas navegador/escritorio, la carpeta nueva no contiene el entorno `.venv` de la anterior. Ejecuta `instalar-EXTRAS.cmd` en la nueva carpeta si necesitas esas funciones. Pide confirmación antes de descargar dependencias; el uso básico de archivos y APIs sigue usando la biblioteca estándar de Python.

## Corrección 0.3.2: navegador y HTTP 400

La versión anterior exigía `value` y `text` incluso al abrir una URL. Un modelo podía generar `{"action":"open","url":"https://..."}` y el proveedor rechazarlo antes de que Nexo lo recibiera. El contrato ahora admite:

- Abrir: `{"action":"open","url":"https://example.com"}`.
- Inspeccionar: `{"action":"inspect"}`.
- Pulsar: `{"action":"click","selector":"#boton"}`.
- Rellenar: `{"action":"fill","selector":"#campo","text":"contenido"}`.
- Cerrar: `{"action":"close"}`.

Las llamadas anteriores con `value` siguen funcionando. Nexo valida los requisitos específicos de cada acción; no inventa una URL, selector o texto omitido, ni acepta alias contradictorios. Los permisos y modos se aplican antes de ejecutar.

Un nuevo `tool_use_failed` del proveedor se comunica de forma explícita. No se ejecuta el contenido de `failed_generation` ni se reenvía automáticamente la tarea: los comandos anteriores podrían haber tenido efectos.

Para retomar una tarea que debía crear un Word en Escritorio → test, elige primero esa carpeta mediante Ajustes → Permisos y pulsa Nueva si cambiaste el destino. Pide inspeccionar lo existente antes de crear o reemplazar nada. El navegador requiere Extras, y automatizar el Word instalado requiere Word y los permisos correspondientes; esta actualización no añade todavía un módulo Word especializado ni garantiza completar la investigación. La ruta del Escritorio puede estar redirigida a OneDrive.

## Corrección 0.3.1: salida PowerShell

Se solicita salida de texto y UTF-8, se desactiva el progreso ordinario y se capturan stdout y stderr por separado. Si todavía aparece CLIXML en una salida, se omiten únicamente los registros de progreso reconocidos; errores y advertencias se conservan. Los bloques incompletos o no reconocidos se mantienen con aviso, no se descartan.

`output` contiene la salida normal y `stderr` el canal de diagnóstico. Hay un límite de 16 000 bytes por canal y aviso de truncamiento. Un `exit_code: 0` no demuestra que se cumpliera la tarea: el modelo recibe una indicación explícita de verificar el efecto concreto. Esta corrección no interpreta un `True` aislado como éxito de toda la tarea.

## 2. Interfaz y teclado

- Conversación en el centro; ajustes e historial en ventanas separadas.
- Ventana inicial de 880 × 700, reducible a **480 × 400** en las pruebas realizadas. En tamaños bajos se ocultan etiquetas secundarias y se reduce el editor para conservar espacio de conversación.
- **Enter:** enviar. **Shift+Enter:** nueva línea. También funciona el Enter del teclado numérico.
- **Enviar:** se desactiva durante la tarea y vuelve a habilitarse al terminar.
- Si presionas Enter otra vez mientras trabaja, no crea otra tarea ni una línea accidental. Puedes escribir el borrador de tu siguiente mensaje mientras esperas.
- **Detener:** revoca nuevas acciones. No deshace lo ya ejecutado; una llamada API puede tardar hasta el tiempo configurado en terminar.
- Los resultados de herramientas aparecen resumidos; **Detalles** muestra el contenido registrado completo de esas vistas. Los argumentos extensos de una aprobación se pueden leer en su diálogo.

## 3. Tres niveles de control

### Planificar

Solo permite `list_files` y `read_file` dentro de la carpeta seleccionada. No habilita PowerShell, navegador, escritorio ni escritura aunque un modelo los solicite.

Con la política recomendada, la lectura no abre una ventana por cada archivo: ya autorizas la carpeta y el tratamiento del contexto. Con revisión estricta, también se revisan las lecturas.

### Actuar + aprobación por plan — recomendado

En **Ajustes → Permisos**, selecciona **Aprobar un plan por tarea** y deja Autónomo desactivado.

1. El agente presenta su plan con `submit_plan`.
2. Ves el objetivo, pasos, carpeta, herramientas y presupuesto.
3. Pulsas **Aprobar plan y ejecutar**.
4. Las acciones cubiertas se ejecutan sin volver a preguntar en cada paso.

Las escrituras que lleguen antes de aprobar el plan se bloquean. Rechazar el plan termina la tarea; no se vuelve a presentar repetidamente dentro de esa tarea.

**Qué significa la autorización:** es una autorización de capacidades para la tarea, no una aprobación de cada byte que se escribirá. Archivos comprende toda la carpeta elegida y subcarpetas. El host controla herramientas, carpeta y presupuesto; no puede demostrar automáticamente que todo cambio satisface perfectamente el texto del plan. Si necesitas revisar cada diferencia, utiliza revisión por acción.

La autorización caduca al finalizar, detener o agotar el presupuesto. No se restaura al abrir una sesión ni se reutiliza para una nueva instrucción. Una tarea puede realizar muchas rondas de herramientas sin nuevas aprobaciones; un nuevo mensaje del usuario empieza otra tarea.

### Actuar + Autónomo

Activa el interruptor **Autónomo** y acepta su alcance. El agente puede ejecutar acciones ordinarias de las herramientas autorizadas sin pedir un plan previo ni permiso por cada archivo.

Mantiene límites, registro, checkpoints y protección contra rutas fuera de la carpeta en las herramientas de archivos. Desactivar el interruptor durante una tarea solicita detenerla; no espera a la siguiente tarea para revocar el permiso.

Autónomo **no** activa herramientas deshabilitadas, no cambia a una API de pago, no eleva permisos y no significa ejecución indefinida. Se desactiva al reiniciar Nexo.

### Revisión de cada acción

Disponible en Ajustes → Permisos. Muestra argumentos completos y diferencias antes de cada escritura. Conserva el flujo estricto de la versión anterior para tareas delicadas.

### Herramientas de acceso amplio

Por defecto, PowerShell, escritorio y clics/rellenos del navegador requieren revisión individual, también en autónomo. Para no interrumpir una tarea avanzada:

1. Habilita solo las herramientas necesarias.
2. Marca **Autorizar herramientas amplias por tarea**.
3. Acepta expresamente el aviso de alcance.

Con esa opción, el plan aprobado o el modo autónomo cubren también esas herramientas sin revisar cada paso. **PowerShell y escritorio no están confinados a la carpeta:** pueden actuar con los derechos de tu cuenta, borrar archivos o enviar datos. El navegador puede transmitir información. No existe un filtro semántico perfecto ni un deshacer general de esos efectos. Esta autorización no se guarda para el siguiente arranque.

El modelo recibe instrucciones de pedir confirmación concreta para compras, publicación, envíos sensibles, eliminación masiva y cambios de seguridad. Esas instrucciones son una defensa adicional, **no una barrera técnica infalible**. No habilites acceso amplio sin supervisión sobre un equipo con datos importantes.

## 4. Claves y perfiles por modelo

En **Ajustes → Modelos**:

1. Elige proveedor y escribe o selecciona el identificador de modelo.
2. Introduce la clave de ese perfil.
3. Deja **Recordar clave para este modelo** activado.
4. Pulsa **Guardar perfil y ajustes**. También se guarda el perfil antes de enviar una tarea.

Cada combinación proveedor/modelo tiene su propia clave. El selector de modelos incluye los perfiles guardados. Cambiar de perfil carga su clave; abrir una conversación recupera el perfil correspondiente. Puedes reutilizar la misma clave en varios modelos si el proveedor lo permite, pero debes guardarla en cada perfil.

**Protección:** Windows DPAPI con la identidad del usuario actual; no hay alternativa silenciosa de texto plano. Un archivo de preferencias copiado a otra cuenta o equipo puede no poder descifrarse. El cifrado no protege frente a otro programa que ya opere con tu misma cuenta de Windows. Las claves existen en memoria mientras se usan.

**Olvidar clave** elimina la copia guardada de ese perfil, sin afectar a los otros y sin revocarla en el proveedor. Si desmarcas Recordar y guardas, se elimina la copia persistida; queda utilizable durante la sesión.

Fuera de Windows, la persistencia segura de claves no está implementada. Puedes desmarcar Recordar y usarlas en memoria. No se sustituye DPAPI por un cifrado casero.

Historial y checkpoints **no están cifrados**. El programa omite capturas y redacta claves conocidas al guardar el contenido de conversación, pero no puede reconocer todos los secretos o datos personales presentes en tus archivos. No compartas el directorio de datos como si estuviera anonimizado.

## 5. Ollama local

La aplicación incluye un adaptador propio a la API local de Ollama. No depende de un conector de Arena.

1. Instala/abre Ollama en Windows mediante su distribución oficial, si aún no lo tienes.
2. Descarga un modelo que admita llamadas a herramientas y que quepa en la memoria de tu PC. Nexo no descarga modelos de chat automáticamente.
3. En Ajustes → Modelos elige **Ollama**.
4. Usa la dirección `http://127.0.0.1:11434`, salvo que hayas configurado otro puerto local.
5. Pulsa **Detectar Ollama** y selecciona un modelo instalado. El identificador de ejemplo editable es `qwen3:8b`; no implica que esté instalado o que sea apropiado para tu hardware.
6. Guarda y continúa escribiendo en el mismo chat. No pulses Nueva por cambiar de modelo o proveedor.

No se necesita clave API. Solo se admiten direcciones loopback; no se siguen redirecciones ni se utilizan proxies del sistema para esa conexión. Se usa `/api/tags` para el listado y `/api/chat` para el diálogo y las herramientas. La documentación oficial describe estos endpoints y la ausencia de autorización para inferencia local. [1](https://docs.ollama.com/api/tags) [2](https://docs.ollama.com/api/introduction) [4](https://docs.ollama.com/api/chat)

**Importante:** una dirección local no prueba que el motor haga inferencia local: Ollama también puede utilizar modelos cloud a través de su servidor local. [7](https://docs.ollama.com/cloud/models) Nexo rechaza identificadores que contengan `cloud`, pero eso no detecta cualquier alias personalizado. Usa modelos descargados y desactiva las funciones cloud de Ollama si necesitas privacidad estricta.

Esta integración es de **texto y llamadas a herramientas**. No incorpora visión de escritorio para Ollama. El módulo de capturas sigue disponible solo con Gemini; Groq y Ollama no reciben capturas en esta versión.

Si un modelo no soporta herramientas, podrá devolver texto o un error, pero no se promete que pueda actuar como agente. No hay sustitución automática por un modelo remoto. La primera carga puede ser lenta; el tiempo de espera es configurable.

## 6. Configuración avanzada

Valores iniciales:

| Ajuste | Inicial | Rango |
|---|---:|---:|
| Solicitudes al modelo por tarea | 16 | 1–64 |
| Acciones por tarea | 48 | 1–256 |
| Espera de API | 120 segundos | 10–600 |
| Límite duro del contexto de texto | 120 000 caracteres | 10 000–500 000 |
| Ahorro de contexto | Activado; objetivo 12 000 caracteres | Activar / desactivar |
| Tamaño de texto | 11 | 9–16 |

Más contexto o llamadas puede aumentar consumo de cuota y costes. Con Ahorro activado se apunta a 12 000 caracteres de historial por solicitud; no es una cuota ni un número exacto de tokens. Las instrucciones, herramientas, imágenes, razonamiento y salida consumen recursos adicionales. Se muestran los tokens que reporte cada API; no hay precios ni saldo en tiempo real.

La memoria local usa extractos, no un resumen semántico validado. Puede omitir detalles antiguos: el historial completo permanece guardado y visible. Para enviar más historial antiguo, desactiva Ahorro en Ajustes → Límites; se aplicará el límite duro configurado. Amplía ese límite si necesitas bloques mayores, con mayor consumo. Al superar incluso ese límite se conserva el chat y se pide reducir la operación o ampliar el límite, no crear otro chat. El registro de sesión conserva su protección de tamaño de 8 MB al cargar; no equivale a historial infinito.

Límites adicionales heredados: lectura de 16 000 caracteres, escritura de hasta 32 000 caracteres, archivos editables hasta 1 MB, listado de hasta 100 entradas, PowerShell de hasta 60 segundos y salida acotada. El navegador usa operaciones síncronas con sus propios tiempos de espera. Stop no garantiza detener instantáneamente una llamada que ya está en curso.

## 7. Checkpoints, sesiones y seguridad

- **Ajustes → Checkpoints**: restaura escrituras de `write_file`, empezando por las más recientes. No sobrescribe un cambio manual posterior que no coincida con el hash esperado.
- Cada escritura crea checkpoint incluso en autónomo.
- No cubren efectos de PowerShell, navegador o escritorio, ni archivos cambiados manualmente.
- Las llamadas interrumpidas no se repiten automáticamente al recuperar una sesión. Sus efectos pueden ser desconocidos.
- Cambiar modelo, proveedor o dirección local de Ollama ya no requiere otra conversación. Los mensajes anteriores se convierten a texto portable; protocolos originales se archivan localmente. No se trasladan firmas de razonamiento ni capturas entre modelos, ni se vuelven a ejecutar llamadas antiguas. **Cambiar la carpeta de trabajo sí requiere Nueva**, para no mezclar destinos. Las autorizaciones se renuevan según la política de cada tarea.
- El navegador es un Chromium separado, no tu navegador personal con sesiones iniciadas; se cierra al terminar la tarea.
- El escritorio es experimental, usa pantalla principal y verifica foco; no se ha validado para todos los monitores, DPI, UAC o aplicaciones.
- Nexo no abre un servidor de control remoto. El servidor local de Ollama es un programa separado.

## 8. Qué se probó y qué falta

Resultados de esta entrega:

- **204 pruebas automatizadas definidas: 201 correctas y 3 omitidas en Linux**. Incluyen políticas, sesiones, checkpoints, perfiles, redacción de claves y transporte HTTP nativo compatible con Ollama.
- **28 regresiones nuevas de continuidad, contexto, contadores y modelo automático**, incluidas en ese total, más **16 comprobaciones nuevas con Tk real** para cambiar modelo/proveedor, recargar el mismo chat y corregir rutas de voz sin selector. Los proveedores y el micrófono se simularon.
- **29 regresiones del instalador y de selección del Python de voz**, incluidas en ese total; reproducen el caso 3.15 predeterminado + Astral/uv 3.11 instalado, con fixtures. Un arranque adicional con Vosk real en un entorno separado de Linux comprobó carga del modelo y estado pausado, sin captura de audio.
- **27 comprobaciones de interfaz con Tk real**, respuestas simuladas y archivos temporales: tamaños, Enter/Shift+Enter, botón, una aprobación para varias rondas, autonomía, detención, perfiles y reinicio.
- **36 comprobaciones adicionales de ratón y voz** con Tk/portapapeles reales y reconocimiento/síntesis simulados. No se abrió el micrófono ni se reprodujo audio real en esas pruebas.
- **9 comprobaciones de Chromium real** contra una página de prueba local: argumentos naturales y anteriores, apertura, inspección, relleno, clic, selectores inválidos, URLs inválidas y cierre.

**No se ha ejecutado esta versión en Windows ni con una clave de proveedor real.** Las tres pruebas omitidas cubren PowerShell básico, salida/progreso/errores de PowerShell y cifrado/descifrado DPAPI real. La persistencia de perfiles se probó con un protector de prueba inyectado, que no se usa en la aplicación. Ollama se verificó contra un servidor HTTP de prueba de su protocolo; no se ejecutó un modelo real de Ollama en esta entrega.

En 0.5.0 se verificó la extracción offline del ZIP oficial incluido, recuperación automática desde una ruta obsoleta y carga real del modelo Vosk en un entorno separado, inicialmente pausado sin abrir el micrófono. La prueba previa de diez segundos de silencio sintético se documenta por separado. Eso no valida precisión en español mexicano. Captura de micrófono, reproducción WinRT, voces es-MX y el atajo Win+H reales quedan pendientes de probar en Windows.

Las capturas `vista-interfaz.png` y `vista-compacta.png` muestran la interfaz real con contenido identificado como simulado. No son imágenes generadas ni evidencia de una consulta real a un modelo.

### Comprobación en tu Windows

1. Ejecuta **PROBAR.cmd**; incluye un comando PowerShell inocuo y un roundtrip DPAPI con una clave ficticia, sin utilizar tus credenciales.
2. Opcional: **PROBAR-INTERFAZ.cmd**, que utiliza un modelo simulado y archivos temporales.
3. Configura un perfil, guarda, cierra Nexo y vuelve a abrir: comprueba que la clave reaparece enmascarada.
4. Prueba Enter y Shift+Enter en una ventana reducida.
5. En Actuar por plan, solicita crear y leer dos archivos de prueba dentro de una carpeta vacía. Debe pedir una aprobación de plan, no una por archivo.
6. Prueba autónomo con solo Archivos habilitado. Después activa herramientas adicionales de una en una si las necesitas.
7. Si usas Ollama, comprueba un modelo descargado con herramientas.

No envíes tus claves ni el directorio completo de sesiones al pedir ayuda. `DIAGNOSTICO.cmd` informa sobre versión y dependencias sin imprimir claves ni rutas personales.
