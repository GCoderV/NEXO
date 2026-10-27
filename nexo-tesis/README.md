# Nexo Tesis 0.4.1-dev (desarrollo sobre 0.4.0)

Agente académico independiente de Nexo PC. Empieza con un **tema**, conserva cada proyecto por separado y desarrolla propuestas revisables. No instala un complemento en Word ni incluye un tema de investigación obligatorio.

## Cambios de esta versión

- **Archivos por proyecto:** copia local de originales, versiones, huella SHA-256, rol, ubicaciones de texto y estado de extracción. Importar no envía nada al modelo.
- **Guías revisables:** propuestas de requisitos con fragmento y ubicación; clasificación orientativa como obligación, recomendación, ejemplo o por confirmar. El usuario selecciona y aprueba. El perfil elegido gobierna la vista previa y el formato nativo, sin convertir silenciosamente los títulos a mayúsculas/minúsculas.
- **Contexto selectivo:** instrucciones diferentes para conversar y redactar; datos conocidos sin el historial completo, fuentes pertinentes, borradores necesarios y extractos autorizados. Se conserva el texto completo del apartado objeto de revisión. Un saludo ya no crea un proyecto llamado «hola».
- **Copilot:** se conservan las funciones de lanzamiento, entrada y captura pasiva que funcionaban. Cambia el tratamiento de respuestas y se conservan referencias devueltas, sin declararlas verificadas. La continuidad remota opcional sigue siendo **experimental y desactivada por defecto**.
- **Autonomía acotada:** conserva las protecciones, cancelación y verificación de avance de 0.3.1. Un anteproyecto no programa resultados finales por tener un diagnóstico. Cronograma, presupuesto y anexos pueden incorporarse al plan cuando se aprueba ese requisito de la guía. Los cambios puramente tipográficos no obligan a reescribir todos los borradores.
- Se mantiene la corrección del índice de Word de 0.3.1 y su modo **Solo actualizar índice**, siempre con vista previa y aprobación.

## Iniciar o actualizar

1. Descomprime **toda** esta carpeta en una ubicación propia. Para actualizar, usa una carpeta nueva y cierra la versión anterior.
2. Ejecuta **INICIAR-TESIS.cmd** en Windows 10/11. Necesitas tu instalación existente de Python 3.11 o superior, con Tkinter y SQLite. El iniciador no instala paquetes, sustituye Python ni modifica Nexo PC.
3. Tus proyectos se conservan en `%USERPROFILE%\.nexo-tesis\`, fuera de esta carpeta. **No borres ese directorio para actualizar.** Respáldalo con Nexo cerrado.
4. Abre **Modelos y cuentas**. La primera migración conserva una copia de la configuración anterior en `config-v01-respaldo.json`; revisa las cuentas importadas. Las rutas migradas no se incorporan automáticamente a la rotación.

El cliente WebSocket y el lector PDF necesarios ya están incluidos. No necesitas instalar el proxy de referencia, Node, REA, Playwright ni un servidor adicional. Word de escritorio es opcional para conversar; hace falta para las operaciones nativas sobre documentos.

## Recibir archivos y utilizar una guía

1. Abre el proyecto y pulsa **Archivos**. Elige el rol: `guia`, `borrador`, `fuente`, `datos` u `observaciones` del asesor. Pulsa **Adjuntar** y autoriza la lectura local. El selector de archivos está implementado; no hay arrastrar y soltar.
2. Revisa el estado, advertencias y texto extraído. **Recibido no significa leído**. `texto_extraido` tampoco certifica una interpretación completa: algunos formatos contienen objetos que no se leen. Los localizadores y avisos muestran el alcance.
3. Si el modelo necesita ese contenido, pulsa **Autorizar extractos**. Se requiere permiso para todas las rutas candidatas de la ejecución, incluida su rotación. Cambiar cuenta, modelo, endpoint o generación de credencial puede exigir un permiso nuevo. No se hace una llamada al concederlo: los extractos se seleccionan en la siguiente tarea.
4. Puedes referirte a `D1`, `D2`, etc. en el chat para priorizar un documento. Se envían hasta seis fragmentos y 6000 caracteres, **no el archivo completo**. Revisa las respuestas antes de asumir que se consultaron todas las páginas.
5. Para una guía, pulsa **Revisar requisitos**, comprueba evidencia, ámbito y ejemplos, selecciona solo las reglas aplicables y aprueba. También puedes revisar los requisitos ya escritos en **Memoria → guia**. No se deduce automáticamente que una muestra es una norma. Los conflictos de valores bloquean la aprobación conjunta.
6. En Word, prepara la vista previa antes de aplicar. **Restaurar perfil APA base** es explícito y no modifica Word por sí solo. Sustituir o retirar la guía deja su perfil pendiente de revisión, en vez de seguir aplicándolo como vigente.

**Detección normativa parcial:** fuente global Times New Roman/Arial/Calibri; tamaños de cuerpo, títulos y subtítulos; interlineado 1, 1.5 o 2; márgenes uniformes de 1–4 cm; alineación del cuerpo; papel Carta/A4; y menciones de cronograma, presupuesto y anexos para confirmar. Hasta 80 propuestas. No sustituye la lectura académica de un manual: ámbitos complejos, márgenes diferentes, estructura institucional completa, tipos de referencia y excepciones requieren revisión. Los campos no seleccionados mantienen la base APA. Mayúsculas/minúsculas quedan como comprobación manual, no se reescribe el texto.

| Formato | Lectura en esta versión |
|---|---|
| PDF | Texto por página, hasta 200 páginas. No OCR ni interpretación de gráficos; no se abren PDF cifrados. |
| DOCX | Word nativo abre una copia de biblioteca en solo lectura, sin guardar; macros y actualización de vínculos deshabilitados durante la apertura. Cuerpo principal hasta 4000 párrafos; no encabezados, notas ni imágenes. Las marcas de seguridad de Windows se conservan cuando existen. Prueba real de esta nueva lectura COM pendiente. |
| TXT / MD | UTF-8 o UTF-16 con BOM; ubicaciones por líneas. |
| CSV / TSV | Filas y valores; hasta 5000 filas. No ejecuta fórmulas. |
| XLSX | Valores guardados en celdas, incluidas hojas ocultas si existen; no recalcula ni ejecuta macros/enlaces. Hasta 5000 filas; nombres internos `sheetN`. |
| PPTX | Texto de partes `slideN`, hasta 200; el número interno no certifica el orden de presentación. Sin imágenes, notas ni animaciones. |
| PNG / JPG | Se conserva el original, marcado **sin texto leído**. No OCR ni envío visual al modelo. |

Límites locales: **20 MB por archivo, 30 archivos/versiones por proyecto y 100 000 caracteres extraídos por archivo**. Los textos grandes quedan parciales, no se presentan como completos. Hay límites de expansión XML/ZIP, lectura en subproceso con tiempo máximo de 60 s, y límite de memoria de 700 MB cuando el sistema POSIX lo permite; este último no se afirma para Windows. DOCX tiene un máximo de 90 s. Un tiempo agotado puede dejar la copia abierta en Word: revísala antes de repetir. No se desactivan las políticas de Office para abrir documentos rechazados.

**Privacidad y procedencia:** los permisos son de extractos, no una subida nativa a Copilot. Originales y extracción se guardan fuera de SQLite. Se identifica conservadoramente la procedencia de respuestas y borradores generados; los derivados marcados no se reenvían a una ruta sin permiso. Si un dato esencial o el borrador objetivo dependen de un archivo revocado, la tarea se detiene antes de enviarlo. Las ediciones manuales de un borrador conservan esa procedencia. Los datos confirmados manualmente en Memoria se tratan como información del proyecto; no hay un rastreador universal de copias/pegados hechos por el usuario.

**Revocar** impide futuros envíos controlados por Nexo y reinicia los identificadores de continuidad guardados; **no borra lo ya recibido por Microsoft, sus conversaciones, ni tus borradores locales**. Retirar una versión suspende nuevas extracciones, conserva el original y revoca su permiso; puedes autorizar de nuevo solo su contexto derivado sin reactivarla. Importar una versión nueva no hereda permisos de extractos. Anonimiza datos de estudiantes antes de compartirlos.

No hay subida nativa de archivos, análisis visual, OCR, descarga/ejecución de artefactos de Copilot ni análisis semántico integral de todas las páginas en un solo turno. Un enlace o referencia devuelto por Copilot **no prueba** que Nexo haya leído su contenido.

### Continuidad y referencias de Copilot

En Conversación → **Hilo Copilot** puedes activar la reutilización experimental de identificadores de conversación/sesión por proyecto y cuenta/generación/endpoint. Se renuevan al llegar a 40 turnos, ante un resultado incierto o al reiniciar el hilo. No se comparten entre proyectos ni se guardan tokens en esa memoria. Se siguen enviando datos esenciales locales: **no se ha verificado que el servidor recuerde todo lo anterior**. Desactivar esta opción devuelve el comportamiento no persistente.

En Fuentes → **Referencias Copilot**, se muestran los títulos, identificadores y enlaces estructurados que el servicio haya devuelto. No se convierten automáticamente en fuentes verificadas ni en citas APA. Por privacidad se eliminan parámetros y fragmentos de URL; algunos enlaces pueden dejar de ser navegables. No se procesa todavía el conjunto completo de tipos de artefactos del servicio.

## Configurar cuentas y modelos

### Cuentas

En **Modelos y cuentas → Cuentas**:

- Elige proveedor, escribe un nombre para identificar la cuenta y su API key. Guarda la cuenta. Aparecerá en Modelos y rutas con un modelo sugerido y seleccionado en el editor; pulsa **Guardar y usar** para adoptarlo como ruta inicial, o elige otro ID primero.
- **Excepción Copilot365: no es una API y no tiene API key.** Al seleccionarlo desaparece el campo «API key» y el botón pasa a **Conectar / guardar M365**. No hay que pegar claves, tokens ni URLs: pulsa **Conectar escritorio M365** (o ese botón) para vincular tu sesión de Microsoft 365. Si desde **Modelos y rutas** intentas guardar una ruta Copilot365 sin cuenta, Nexo te ofrece abrir esa conexión en lugar de pedir credenciales. Ver «Conectar desde Nexo».
- Puedes registrar varias cuentas del mismo proveedor. Una cuenta se reutiliza en cuantos modelos de **ese proveedor** selecciones: no necesitas duplicar su clave por modelo.
- **Recordar** guarda el secreto con Windows DPAPI, vinculado al usuario/equipo actuales. Desmarcado significa que Nexo conserva la credencial solo durante esta ejecución. En otros sistemas no hay sustituto en texto plano.
- Deja la clave vacía al editar una cuenta para conservarla. Deshabilitar o eliminar una cuenta la excluye de las llamadas automáticas. Eliminarla deja sus rutas sin credencial.
- «Lista; no verificada» significa que existe una credencial legible, no que Microsoft u otro proveedor la haya aceptado. No se hace inferencia al guardar.

Proveedores: **Google mediante Gemini API —incluidos IDs Gemma—, Groq, OpenRouter, Requesty, NVIDIA, Microsoft 365 Copilot experimental y Ollama local**. No se trata de GitHub Copilot.

### Modelos y rutas

1. Selecciona proveedor y cuenta en **Modelos y rutas**.
2. Pulsa **Actualizar lista** para consultar su catálogo, o escribe un ID compatible. La consulta de catálogo es explícita; no genera contenido. Los modelos publicados no garantizan acceso con tu cuenta.
3. **Guardar ruta** vincula ese modelo a la cuenta. Puedes añadir el mismo modelo con otra cuenta y otros modelos con la misma cuenta. Guarda los nuevos sin borrar los anteriores.
4. **Guardar y usar** establece la ruta inicial. Cambiarla **no crea un proyecto ni borra la conversación**.
5. Marca **Incluir esta ruta en la rotación automática** solo en las rutas que quieras autorizar para ese uso. Las flechas ordenan rutas dentro de los grupos de prioridad.

Para **Ollama**, inicia tu servicio local, selecciona el proveedor y pulsa **Actualizar lista**. La lista procede de `/api/tags`: no descarga modelos. Usa una dirección de bucle local, por ejemplo `http://127.0.0.1:11434`. Ollama se selecciona **manualmente**, no participa en rotación y nunca pasa silenciosamente a un proveedor remoto. Se rechazan etiquetas que contengan `cloud`; verifica además que tu instalación de Ollama no delegue en la nube por otra configuración.

Gemma en Google usa instrucciones dentro del mensaje y validación JSON en Nexo; no se presupone que admita todos los parámetros de Gemini. Otros modelos pueden rechazar el formato solicitado: en ese caso queda una petición pendiente, no una respuesta inventada.

### Rotación, cuotas y coste

Con rotación activa, se intenta:

**cuenta/modelo inicial → otras cuentas seleccionadas del mismo modelo → otros modelos configurados del proveedor → otros proveedores configurados y autorizados.**

Solo participan rutas habilitadas, marcadas para rotación y con una credencial del proveedor correcto. Un modelo de catálogo sin ruta, o una cuenta vacía, eliminada, deshabilitada o cuyo secreto no se puede abrir, recibe **cero llamadas**. Las credenciales de solo sesión sí pueden participar. Una cuenta rechazada por autenticación se pausa hasta que la guardes/reconectes; los límites técnicos conservan un tiempo de espera.

Por defecto hay hasta **6 intentos de transporte por ciclo** y un presupuesto de **180 segundos**; se pueden ajustar en Rotación y privacidad. No son un límite al número de cuentas. Se respetan los tiempos de espera del proveedor y no se crea un bucle infinito. El tiempo de una búsqueda o de una autorización también puede consumir el presupuesto antes de la segunda fase.

La rotación puede consumir cuota o saldo de las rutas que marques. **No todos los modelos son gratuitos**, incluso cuando exista una modalidad gratuita del servicio. Nexo no crea cuentas, activa suscripciones, compra créditos ni recarga saldos. Las cuotas pueden estar compartidas entre modelos o cuentas; no se exige demostrar que sean independientes. Consulta los precios y condiciones actuales en cada proveedor. En modalidades gratuitas de Google, revisa también sus condiciones de uso de los datos.

Antes de enviar, Nexo pide autorización de los destinatarios para ese proyecto. La conserva sin preguntarla en cada paso; una cuenta o modelo nuevo necesita autorización. Se comparten decisiones, el mensaje y extractos pertinentes, no todo el documento Word. No incluyas datos identificables de estudiantes.

## Continuar y Reanudar no son lo mismo

- **Continuar** propone el siguiente paso académico: es una solicitud nueva.
- **Reanudar** retoma una solicitud pendiente tras un error, agotamiento, detención o reinicio. No vuelvas a escribir su texto. Conserva su mensaje original, procedencia y fase guardada.
- Las propuestas y búsquedas ya guardadas no se ejecutan de nuevo. Reanudar nunca vuelve a insertar texto ni comentarios en Word.
- Si cambiaste el contenido del proyecto, se pide confirmar el contexto actualizado. No se duplica tu mensaje ni se repiten búsquedas completadas.
- Una respuesta que no cumple el formato académico no se aplica ni dispara otra llamada de reparación. Puedes elegir otra ruta y pulsar Reanudar. El aviso indica el **motivo concreto** sin mostrar la respuesta del modelo. Se acepta un único objeto JSON válido aunque venga envuelto en texto o en un bloque ```json —caso habitual en Copilot365—, y se toleran las comas finales. **Los borradores admiten hasta 20 000 caracteres**, el mismo límite del editor de Apartados; si el modelo lo supera, el texto se recorta en un límite de párrafo y se avisa dentro del propio borrador en vez de rechazar la respuesta. También se normalizan etiquetas de apartado, alias en español y fuentes con formato irregular. Detalle en `INCIDENCIA-FORMATO-BORRADOR.md` (incluido en este paquete). `VERIFICAR.cmd` muestra `(longdraft-1)` y la línea «Borradores largos: OK» para confirmar que estás abriendo esta copia y no una carpeta antigua.
- Si se perdió la respuesta después de enviar, el servidor pudo haber trabajado y consumido cuota. Se detiene el cambio automático y se pide confirmación antes de reanudar. **No puede garantizarse facturación exactamente una vez.**
- Detener impide nuevos pasos. Una petición HTTP ya enviada puede tardar hasta su límite de espera en terminar. No devuelve cuotas, retira peticiones del servidor ni deshace Word.

## Microsoft 365 Copilot — experimental, no oficial

**El usuario confirmó que Copilot funciona desde Nexo con 0.3.0. Su conexión se conserva en esta versión.** El asistente no tiene acceso autenticado a esa cuenta ni ha comprobado todas las condiciones de expiración/renovación o políticas institucionales. Las pruebas locales de transporte no sustituyen esa verificación real.

El transporte de las solicitudes de Nexo es **WebSocket/SignalR directo**. No se escribe ni se lee el chat por automatización DOM. Tampoco se extraen contraseñas, cookies de otros perfiles, almacenes generales de credenciales ni refresh tokens de MSAL. No se solicita que pegues tokens, solicitudes PowerShell o archivos HAR.

### Conectar desde Nexo

1. En Cuentas, pulsa **Nueva cuenta**, elige **Copilot365** y asigna un nombre. **No busques un campo de API key: al elegir Copilot365 desaparece.** Si el programa parece pedirte una clave, es que elegiste otro proveedor o aún no has iniciado la conexión; no pegues contraseñas ni tokens.
2. Mantén **Escritorio M365** como método inicial. Cierra primero Microsoft 365 Copilot.
3. Pulsa **Conectar escritorio M365** (equivalente al botón **Conectar / guardar M365**) y lee la autorización. Nexo intentará abrir la aplicación instalada con diagnóstico de bucle local. Comprueba que el puerto observado esté enlazado solo a `127.0.0.1`/`::1`. No instala la aplicación ni fuerza el cierre de procesos.
4. Inicia sesión **tú mismo** en la ventana de Microsoft. Espera a que Nexo indique que la observación está preparada. La ventana no se recarga desde Nexo.
5. Copia la frase **NEXO CONEXION…** con el botón correspondiente y envíala **manualmente** en un chat nuevo de Microsoft, **sin adjuntos**. Es una prueba de conexión, no la conversación académica. La espera está limitada a tres minutos.
6. Nexo conserva únicamente la conexión que transporta esa frase y una plantilla depurada de su invocación. La frase, el texto anterior y sus adjuntos no se guardan en la plantilla. El token queda en memoria o DPAPI según tu elección.
7. Guarda la ruta **auto** y pulsa **Guardar y usar**. Envía una solicitud desde la conversación de Nexo. Solo una respuesta recibida y validada confirmará la inferencia independiente; observar la conexión por sí solo no la confirma.
8. Si el escritorio no abre un puerto compatible, cambia el método a **Acceso con Edge** y vuelve a conectar. Es una ventana de autenticación de Microsoft en un perfil separado, no un bot que maneja el chat. No se instala Edge automáticamente. El botón conserva su nombre aunque selecciones este método.

Las solicitudes académicas y sus respuestas se muestran en Nexo. Se crean identificadores remotos separados por operación/cuenta; la continuidad de tus investigaciones la conserva el proyecto local, no una supuesta memoria ilimitada del servidor de Microsoft.

**Renovación:** al caducar, Nexo puede observar una conexión que Microsoft renueve de forma natural en la misma ventana autorizada y con la misma identidad. No se fuerza una recarga. Si no aparece una conexión nueva, debes reconectar y enviar la frase en un chat NUEVO. No se garantiza renovación sin ventana, sin volver a iniciar sesión o bajo todas las políticas institucionales. Si falla, reconecta desde Cuentas. No se desactiva MFA, acceso condicional, certificados TLS ni políticas de Office.

**Cierra las ventanas de Copilot/Edge abiertas para esta conexión al terminar**, de modo que cierre su puerto de diagnóstico. Aunque sea local, otros programas de tu usuario podrían acceder a ese puerto mientras esté abierto. El perfil separado de Edge guarda su propio estado de inicio de sesión en `.nexo-tesis/copilot-login`; elegir «solo sesión» para la credencial de Nexo no borra las cookies que administra el navegador. Cierra sesión allí si no deseas conservarlas.

El usuario informó que su aplicación ofrece modos automático, rápido y profundo y muestra GPT-5.6. Esta versión sigue usando **el modo observado al conectar** bajo el ID local `auto`; no incorpora todavía un selector independiente de los tres modos ni traduce esos nombres a alias privados supuestos.

No se fija una licencia Premium, no se transforma una cuenta Starter en otra modalidad y no se anuncian nombres internos de modelos. **auto** conserva la selección observada en el cliente; no certifica el modelo físico que responde. Los parámetros `licenseType`, `isEdu`, `source` o las variantes observadas no demuestran licencias ni capacidades. Microsoft sigue comprobando sus permisos y puede cambiar o rechazar el protocolo.

Copilot podría utilizar información institucional conforme a sus capacidades y permisos. Si autorizas otras rutas para el proyecto, los extractos que queden incorporados en él podrían enviarse a esos otros proveedores. Revisa ese permiso antes de usarlo con material interno. Nexo no expone terminal, herramientas generales de PC ni operaciones de Word al servicio Copilot.

## Trabajo autónomo sin pulsar Continuar en cada paso

1. Aporta tu tema y los datos disponibles como siempre. Guarda cualquier edición manual antes de empezar.
2. En **Conversación**, elige el máximo de apartados (2, 4, **6 por defecto**, 8 o 12) y pulsa **Trabajar solo**.
3. Revisa el plan que propone crear o revisar apartados y aprueba el conjunto. Se utilizan únicamente las rutas ya configuradas y autorizadas. Puede consumir cuota/saldo; no crea cuentas ni activa pagos.
4. Cada tarea solicita un borrador concreto. Verás el estado de ejecución y el avance guardado, sin tener que escribir «continúa». Se trabajan primero apartados faltantes/desactualizados y luego, cuando corresponde, borradores del modelo pendientes de revisión. No hay un pulido infinito: el mismo apartado no se vuelve a procesar con los mismos datos y texto tras completar su tarea.
5. **Detener** impide nuevos pasos y conserva los ya guardados. Una llamada en curso puede tardar en terminar. No se reinicia una sesión al abrir Nexo. **Reanudar** retoma únicamente la solicitud pendiente con sus controles habituales; no reinicia automáticamente el resto del conjunto.

Límites: hasta dos respuestas lógicas del modelo por apartado, incluida una corrección por falta de avance o una segunda fase después de búsqueda; los intentos de transporte siguen sujetos a los límites de rutas configurados. Tras diez minutos no se inicia otro apartado; una tarea ya iniciada puede finalizar después. Errores, cambios de destinatario, respuestas inciertas y falta de progreso detienen la sesión con un aviso, no con un bucle oculto. No se garantiza que un modelo entregue un texto académico correcto por haber producido un cambio.

Se protegen los apartados **aprobados, editados por ti o ya insertados en Word**, también si una modificación de datos los marcó como desactualizados. Los borradores antiguos sin procedencia identificable se conservan por precaución. Una revisión automática recibe el texto previo completo y no puede sustituir silenciosamente un borrador largo por un resumen de menos del 65 % de su extensión. Las versiones anteriores siguen conservadas según los límites del proyecto.

Las tareas automáticas se registran como actividades del sistema, **no como declaraciones tuyas**. No pueden aportar nuevos hechos, confirmar datos ni inventar resultados; resultados/discusión/conclusiones necesitan datos o corpus aportados y confirmados en Memoria. Se pueden desarrollar propuestas provisionales sin detenerse ante cada pregunta no bloqueante. Para trabajos documentales no se imponen instrumentos de participantes ni planes de acción.

**Alcance:** el modo autónomo escribe en **Apartados de Nexo**, no directamente en Word. Las operaciones Word siguen requiriendo su vista previa y aprobación. Con Permitir búsqueda activado, cada consulta externa conserva su aprobación explícita; sin activarlo, la sesión puede avanzar sobre el material disponible y señalar fuentes pendientes.

### Si falló el índice en 0.3.0

El error pudo aparecer después de aplicar formato e incluso crear el campo del índice. **No repitas a ciegas toda la operación.** Conserva la copia afectada, revísala en Word y usa una copia anterior si necesitas deshacer cambios. Si el formato está como deseas y existe un único índice, abre **Organizar / APA 7 → Solo actualizar índice**, revisa que no haya inserciones ni formato completo seleccionados y aprueba esa vista previa. No hay deshacer automático ni borrado de revisiones para ocultar el fallo.

## Flujo académico y fuentes

Empieza con el tema o pega directamente un texto de varias líneas con tus datos en la conversación inicial. Un tema breve crea el proyecto sin consultar al modelo; un texto inicial de varias líneas crea un proyecto por delimitar y, previa autorización del proveedor, lo envía una sola vez para extraer los datos. Si contiene un tema explícito, puede adoptarse como título con evidencia literal; no se sustituye silenciosamente el tema de un proyecto ya establecido.

En un proyecto existente también puedes pegar todos los datos juntos. No necesitas ordenarlos por campos. El modelo debe extraer primero lo aportado y reunir en un solo bloque las preguntas iniciales pertinentes que falten. Una respuesta tuya puede contestar varias preguntas a la vez. Lo declarado como «no definido» o «no disponible» no autoriza inventar resultados. Indica nivel, institución, metodología y contexto cuando proceda; ninguno está impuesto. Puedes corregir los datos en **Memoria**, aplazar preguntas, cambiar de proyecto y conservar el historial tras reiniciar.

Cada respuesta propone hasta dos apartados. Hay hasta dos **fases de generación** por turno; la segunda se usa después de una búsqueda autorizada. Esas fases no equivalen al número de intentos de transporte de la rotación. El contexto se acota a 24 000 caracteres más las instrucciones y salida, no a un número exacto de tokens. La conversación completa permanece local; la pantalla muestra los últimos cien mensajes.

Los hechos extraídos requieren evidencia literal del mensaje o tema, pero eso no certifica que su interpretación sea correcta. Las correcciones marcan borradores dependientes para revisión. Resultados, discusión y conclusiones requieren datos/corpus registrados y tu confirmación de disponibilidad; no se inventan resultados para completar apartados. Aun con controles, revisa cifras, citas y afirmaciones del modelo.

**Permitir búsqueda** habilita que se proponga una consulta de Crossref. Antes de enviarla se muestra el texto exacto. Máximo una consulta de cinco resultados por turno. Crossref aporta metadatos y a veces resúmenes: **no demuestra lectura de artículos completos**. Puedes registrar fragmentos realmente consultados con localizador y estado. Se bloquean IDs de fuentes inexistentes; un DOI existente tampoco prueba que respalde una afirmación.

El perfil UCE incluido es opcional y procede de una guía aportada de tres páginas; no es un manual institucional completo ni vigente verificado. Puedes aportar reglas de otras instituciones. APA/CSL completo, validadores institucionales adicionales, análisis estadístico especializado, voz continua y ajuste de un modelo para Ollama siguen pendientes. No se garantiza superar detectores ni sustituir la revisión académica.

## Word de escritorio — operaciones nativas y acotadas

**La automatización COM real sigue sin verificarse en Windows. Haz la primera prueba sobre una COPIA local, guardada en Word como `.docx`, sin datos sensibles.** No se utiliza Python-DOCX ni se instala un complemento.

Puedes usar **Crear en Word** para abrir un documento nuevo vacío: confirma la acción y guárdalo tú desde Word como `.docx`, con el nombre y ubicación que decidas. No se crea un archivo silenciosamente ni se asigna una autoría desde Nexo. **Abrir DOCX** permite elegir y confirmar una copia existente; se deshabilitan temporalmente macros y actualización automática de vínculos durante la apertura, se restauran las opciones y no se omiten las protecciones de Office. Estos botones están implementados; la prueba COM real sigue pendiente.

1. Abre y guarda esa copia en Word. En Nexo → Word, pulsa **Buscar abiertos** y selecciona el documento exacto.
2. En Word, selecciona un párrafo del cuerpo principal o coloca el cursor. Vuelve a Nexo y pulsa **Confirmar y leer**. Leer no envía automáticamente el fragmento a un modelo.
3. **Revisar en chat** prepara, previa autorización, un mensaje sin enviar con hasta 4500 caracteres. El documento no se interpreta como instrucciones ni decisiones del usuario.
4. Desde Apartados, **Preparar en Word** solo prepara texto. Revisa y aprueba **Insertar con revisiones** o **Añadir comentario** para modificar Word.
5. Comprueba el efecto en la copia. La inserción añade texto, no reemplaza lo anterior. Acepta/rechaza revisiones desde Word o elimina el comentario. Guarda tú el documento cuando corresponda.

Se comprueban documento, ventana, posición y huella del texto. No edites Word durante la operación. Cada autorización de selección se consume una vez; moverla exige volver a leer. Nexo no llama a Guardar/Guardar como, no cambia propiedades de autor ni acepta revisiones anteriores. **AutoSave de Word puede actuar por su cuenta.** Las operaciones usan marcadores o etiquetas `[Nexo:…]` para identificación.

Límites: DOCX guardado, editable y sin protección; cuerpo principal, no tablas, encabezados, notas ni selecciones múltiples. Lectura de hasta 12 000 caracteres, inserción de 10 000 y comentario de 6000. Puede detectar solo una instancia de Word. Se requiere el mismo usuario/nivel de permisos. El análisis de documento completo admite hasta 4000 párrafos y 2 millones de caracteres; cada apartado hasta 10 000 unidades UTF-16 y el lote hasta 60 000. No es un corrector bibliográfico integral ni certifica cumplimiento institucional. No eleves privilegios ni desactives políticas para sortear errores.

Un tiempo de espera puede dejar un efecto parcial: **inspecciona Word antes de repetir**. No hay reintentos automáticos de escritura ni deshacer general. Conserva copias de seguridad.

### Organización automática, índice y APA 7

1. Trabaja en una **copia local DOCX guardada**, abierta y activa en Word. Selecciónala en Nexo. No necesitas colocar el cursor para este flujo.
2. Pulsa **Organizar / APA 7** y autoriza el análisis local. Se lee el cuerpo para calcular huellas y reconocer párrafos, títulos y campos. Este análisis **no llama a un modelo ni le envía el documento**.
3. Deja activadas las opciones de formato del documento completo e índice, o desmarca lo que no quieras. Selecciona opcionalmente varios borradores guardados de Apartados. El texto editado solo en el cuadro de propuesta manual no se usa aquí.
4. Pulsa **Preparar vista previa**. Verás los títulos detectados, el texto nuevo, sus ubicaciones y las reglas de formato. Se inserta al final del apartado correspondiente; si falta, se propone crearlo en orden académico. **No reemplaza párrafos existentes ni decide correcciones semánticas dentro de ellos.** Los títulos duplicados/ambiguos, estructura no reconocible y varios índices bloquean las operaciones afectadas: corrígelos en Word o usa el flujo manual.
5. **Aprobar y aplicar conjunto** requiere confirmar esa vista previa. Si cambian el texto/estructura de Word o los borradores del proyecto, debe prepararse de nuevo. Las operaciones se ejecutan una vez, sin reintentos. Las inserciones se verifican y marcan para evitar repetir el mismo borrador.
6. Revisa la copia en Word. Las inserciones y el formato utilizan control de cambios, pero la paginación, campos y estilos no son una transacción reversible garantizada. No se aceptan revisiones automáticamente ni se llama a Guardar. AutoSave de Word puede guardar por su cuenta. Tras aceptar/rechazar revisiones, vuelve a actualizar **toda la tabla** desde Word si cambian las páginas.

**Base APA cuando no hay otro perfil aprobado:** Times New Roman 12, doble espacio, párrafos del cuerpo alineados a la izquierda, 0 puntos antes/después, primera línea a 1,27 cm, márgenes de 2,54 cm, papel Carta. Encabezados de niveles 1–3, resumen sin sangría inicial, referencias con sangría francesa y citas en bloque explícitas con sangría. Conserva el texto y las negritas/cursivas existentes; no reescribe títulos ni elimina párrafos vacíos. La portada mantiene alineación/sangrías y requiere revisión de datos/disposición. El papel y los márgenes pueden redistribuir páginas.

**Índice real de Word:** creación antes del cuerpo reconocido o actualización del único índice existente, con niveles 1–3, enlaces y páginas calculadas por Word, no inventadas por un modelo. Se conservan entradas personalizadas de un índice previo; revísalas. Si no hay numeración ni contenido en encabezados/pies, se añade numeración superior derecha desde 1; si los hay, se preservan y se avisa para revisión. Se respetan tablas, figuras incrustadas, ecuaciones y contenido de cabeceras; notas, listas complejas, títulos 4–9, citas de varios párrafos y maquetación especial necesitan revisión humana.

**No es una certificación APA 7:** no inventa autores, años, DOI ni fuentes, ni convierte automáticamente `[F1]` en una cita válida. Tampoco corrige por sí solo todos los tipos de referencia, la correspondencia cita–referencia o requisitos propios de UASD/UCE. El índice general es una función solicitada para la tesis, no una exigencia universal de APA. Reglas de formato de referencia: [APA: párrafos](https://apastyle.apa.org/style-grammar-guidelines/paper-format/paragraph-format). Operaciones nativas: [Word TablesOfContents.Add](https://learn.microsoft.com/en-us/office/vba/api/word.tablesofcontents.add).

Si una operación falla o agota el tiempo, puede haber dejado un efecto parcial. **No la repitas a ciegas**: inspecciona la copia; revierte desde Word o vuelve a una copia previa según corresponda.

## Agente con herramientas y documento completo (0.4.1-dev, `agentloop-1`)

El modo autónomo ya no se queda sin tareas mientras haya trabajo pendiente. Se
corrigió la causa real: las consultas booleanas de 340–414 caracteres se
rechazaban por un límite de 250 y nunca llegaban a Crossref. Ahora
`bibliography.normalize_queries()` las divide en un máximo de 3 consultas
simples, se aprueban y se ejecutan. El botón **«Buscar fuentes»** permite
buscar sin esperar a que el modelo lo proponga; si no hay red, puedes dar de
alta fuentes a mano en la pestaña Fuentes. `autonomy.plan()` desbloquea
Instrumentos con un borrador de Metodología, ofrece Cronograma/Presupuesto/
Anexos como plantillas «Por definir» y explica exactamente qué falta cuando no
hay tareas elegibles. **Antecedentes** se redacta dentro del Marco teórico y
**Referencias** se reconstruye desde el registro de fuentes.

Nuevo **bucle de agente acotado** (botón «Agente con herramientas» en
Conversación o «Completar lo que falta» en Documento). El usuario aprueba el
objetivo, el número de pasos (2–12) y la carpeta de exportación. El modelo
responde con `{"reply","tool_calls","done"}` y el anfitrión valida y ejecuta 15
herramientas: inspeccionar el documento, ver pendientes, leer un apartado,
listar fuentes, buscar fuentes, escribir un apartado, **editar solo el fragmento
que falta** (`insertar_despues`/`reemplazar`/`eliminar`), **añadir, quitar o
restaurar apartados**, registrar datos con evidencia literal, preguntar al
usuario y finalizar. Máximo 4 herramientas por paso. Se detiene por
`finalizar`, pregunta al usuario, ausencia de herramientas, límite de pasos o
falta de progreso medible dos pasadas seguidas, y deja un **recibo auditable**
en «Ver recibo del agente». Los fallos de herramientas se contienen como datos.

La pestaña **Documento** muestra la estructura, permite alto/ocultado (ocultar
NO borra el borrador) y **«Generar documento completo»** exporta sin modelo,
sin red y sin Word: `.md`, `.html` y un `.docx` OOXML estándar escrito con la
biblioteca estándar. Los apartados pendientes se imprimen como
`**[Por redactar]**`. No se inventan fuentes, autorías, años, DOI ni resultados;
los apartados aprobados o editados por ti son inmutables para el agente y Word
nunca se modifica. Ideas funcionales de proyectos abiertos (DoThesis, Loopy,
agentic-thesis-writing, Academic Writing Toolkit, OpenDraft) en
`AGENTE-LOOP-Y-DOCUMENTO.md`, incluido en este paquete.

`VERIFICAR.cmd` muestra `(fase6-1)` y ejecuta tres comprobaciones
funcionales sin red: borradores largos, consultas largas + planificador y un
bucle completo del agente con exportación válida. **467 pruebas** superadas /
2 omitidas con fixtures sintéticas. Sin verificación real de Tk, Word COM,
DPAPI, Microsoft 365 Copilot ni de que Word abra el DOCX generado en este
entorno.

## Reconstrucción por fases (build `fase6-1`)

Tras el error real `cannot use 'dict' as a dict key (unhashable type: 'dict')`
(mensaje nuevo de Python 3.14) y una ventana blanca huérfana de Copilot/Edge, se
reconstruyó el núcleo con ideas de DoThesis, Loopy, agentic-thesis-writing y
Academic Writing Toolkit, analizadas con metodología REA. Detalle completo en
`RECONSTRUCCION-FASES-0-6.md`, incluido en el ZIP.

- **Fase 0 — Diagnóstico.** `diagnostics.py` guarda un traceback **redactado**
  en `~/.nexo-tesis/logs/` y la UI muestra un mensaje útil con «Copiar
  diagnóstico» en lugar del mensaje crudo del intérprete. `as_key()` normaliza
  todas las fronteras de claves de diccionario. `process_guard.py` cierra los
  procesos de Copilot/Edge que Nexo inició cuando la conexión falla.
- **Fase 1 — Estado único.** `project_state.commit_slice()` es la única vía de
  escritura: cinco módulos M1–M5, DAG de invalidación, snapshots, deshacer y
  verificación determinista. Proyectos 0.4.x migran sin perder borradores.
- **Fase 2 — Agente continuo SIN CUOTA DE PASOS.** `run_loop.RunProfile` con
  `max_passes=None`: repite inspeccionar → investigar → escribir/editar →
  verificar hasta que `project_state.verify()` dice `done=true`. El modelo no
  puede declarar «listo». Topes que **no son cuota**: reloj (60 min por defecto),
  estancamiento tras cambiar de estrategia, fusible de 300 llamadas, pregunta al
  usuario y botón Detener. Cada parada deja un recibo auditable.
- **Fase 3 — Investigación en sitio.** `research.py` consulta Crossref,
  OpenAlex, Semantic Scholar y arXiv con presupuesto, deduplica con
  proveniencia y marca verificación en 2+ bases. Sólo metadatos/resúmenes;
  nunca afirma que un paper respalda una afirmación. `gates.py` bloquea citas y
  DOI inventados, cifras sin corpus confirmado y porcentajes imposibles.
- **Fase 4 — Documento.** Markdown/HTML/DOCX OOXML offline con las puertas de
  calidad adjuntas. Ocultar un apartado conserva su borrador.
- **Fase 5 — UI.** Pestaña Documento con estado M1–M5, «Agente continuo · hasta
  terminar», confirmar módulo, deshacer, recibo y diagnóstico.
- **Fase 6 — Validación.** 467 pruebas / 2 omitidas. `VERIFICAR.cmd` muestra
  `(fase6-1)` y ejecuta cinco comprobaciones funcionales sin red, incluido un
  bucle continuo que termina por verificación.

**Uso del modo continuo:** Documento → «Agente continuo · hasta terminar» →
aprobar el conjunto. Verás y autorizarás cada consulta antes de que salga a la
red. El botón Detener funciona en cualquier momento.

**No verificado aquí:** Windows real, Tk con display, Word COM, DPAPI, sesión
real de M365 Copilot, respuesta real de las APIs académicas y apertura del DOCX
en Word. Python 3.14 no está en el sandbox (hay 3.11.2); la corrección valida
tipos, no mensajes de error.

## Datos, recuperación y comprobaciones de esta versión

En `%USERPROFILE%\.nexo-tesis\`:

- `projects.sqlite3`: proyectos, historial y fases pendientes; seis checkpoints recientes y cinco versiones anteriores por apartado. Hasta 3 MB por proyecto.
- `config.json`: cuentas, rutas, catálogo y secretos DPAPI cuando se pidió recordarlos.
- `materials\<proyecto>\<material>\`: originales y `extracted.json`. Incluye esta carpeta en las copias de seguridad; los permisos y metadatos están en el proyecto.
- `word-audit\`: intención/resultado y huellas de operaciones, sin texto del documento ni credenciales.
- `copilot-login\`: perfil de Edge separado, solo si utilizaste ese método.

Los proyectos y las exportaciones son **texto legible, no cifrado**. Respáldalos con Nexo cerrado. DPAPI no hace portable una clave a cualquier equipo o usuario. Si `config.json` está dañado, Nexo guarda **una sola** copia `config-invalido-<fecha>.json` y arranca con una configuración vacía que puedes volver a rellenar desde **Modelos y cuentas**; ya no bloquea todos los guardados. No borres el directorio de datos de Nexo PC.

**Robustez (auditoría 0.4.1-dev):** la configuración se escribe con bloqueo y una instantánea, de modo que el hilo de red y la interfaz no se pisen. Los identificadores `F#` y `D#` son monótonos: borrar una fuente o un archivo no reasigna su número a otro contenido y las citas existentes no cambian de destino. Un `extracted.json` dañado se omite en lugar de abortar el turno. El lanzador comprueba además, sin leer claves, que la carpeta de datos sea escribible. El detalle completo está en `contexto/AUDITORIA-ROBUSTEZ.md` (en el repositorio de desarrollo).

Validación de 0.4.0 en el entorno del asistente: **276 pruebas unitarias, 274 aprobadas y 2 omitidas por requerir Windows; 98 comprobaciones funcionales Tk y 2 capturas opcionales**. Se ejecutaron los contratos de inserción/estructura/índice de PowerShell anteriores y seis nuevas comprobaciones del perfil, sus límites y el cargador. La lógica nativa de fuente, tamaños, interlineado y papel A4/márgenes se probó con **dobles**, no con Word COM. También se comprobaron Python 3.11.17 con `-S`, importaciones sin dependencias instaladas, el paquete extraído, integridad ZIP y hashes.

Medición sintética frente a 0.3.1: las instrucciones bajaron de 6036 caracteres a 1467 en diálogo y 1323 en redacción. Con un expediente de prueba de 11 datos, 11 preguntas respondidas, 15 fuentes y ocho borradores, instrucciones + contexto bajaron **42.97 % y 40.20 %**, respectivamente. Son caracteres, no tokens facturados; **no es una medición de calidad, coste ni ahorro garantizado en tus proyectos**.

**El usuario confirmó la conexión Copilot y la integración Word anterior. El asistente no ejecutó esta versión en Word COM/PowerShell 5.1 de Windows ni hizo inferencia autenticada en Microsoft u otros proveedores.** La lectura DOCX, el perfil final aplicado y la continuidad remota necesitan comprobación real. Empieza con una copia local no sensible. Las pruebas con dobles no certifican la maquetación ni la calidad académica del modelo.

Esta descarga contiene únicamente el programa, su perfil opcional, este README y las licencias necesarias. Las pruebas, capturas, informes y scripts de desarrollo no forman parte del paquete.

### Licencias y referencias

Código Nexo: MIT; se conserva el aviso de autoría original en `LICENSE`. Cliente incluido `websocket-client` 1.9.2: Apache-2.0, aviso en `websocket/LICENSE` y cabeceras de sus módulos. Lector `pypdf` 6.21.2: BSD-3-Clause, aviso en `pypdf/LICENSE`; no se incluyen dependencias opcionales de imágenes o cifrado.

El adaptador Microsoft es una implementación propia limitada, estudiada mediante inventario REA, inspección de Python y pruebas de protocolo. Referencias estáticas: [Theprosonce/m365-copilot-proxy](https://github.com/Theprosonce/m365-copilot-proxy), commit `8eddc3e7bf772eb350da3d2bedc2656f79230b2c`, y [nqthiep/ms-copilot-api](https://github.com/nqthiep/ms-copilot-api), commit `334df528a58478b0f3fc4e74df8bcbb0bbd1e990`. No se ejecutaron ni distribuyen esos puentes. REA registró un inventario histórico parcial, no una prueba semántica de Python ni una verificación de Microsoft. No se ha clonado el servidor, los modelos o el producto Copilot completo.

Referencia del contrato corregido: [TableOfContents — propiedades documentadas](https://learn.microsoft.com/en-us/office/vba/api/word.tableofcontents) y [HeadingStyles.Add](https://learn.microsoft.com/en-us/office/vba/api/word.headingstyles.add).
