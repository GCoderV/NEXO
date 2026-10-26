# Nexo Tesis 0.1.1
## Un agente académico independiente. Empieza con un tema.

**Este es otro programa, no un módulo ni una actualización de Nexo PC.** Tiene lanzador, datos, proyectos y configuración propios. No necesita una instalación de Nexo PC, no importa sus claves y no modifica ese programa.

Se entrega una primera versión funcional de la base conversacional, multiproyecto y de investigación acotada. No es un sistema ya validado para producir una tesis completa sin supervisión.

## Corrección 0.1.1: Gemini 404

El error reportado por Google indica que `gemini-2.5-flash` ya no está disponible para usuarios nuevos. El modelo sugerido ahora es **gemini-3.8-flash**. La documentación oficial también lo muestra con `generateContent`; esta corrección no migra a Interactions ni realiza reintentos automáticos.

**Si ya tenías Gemini configurado:** abre Modelo y privacidad → Gemini → **Sugerido** → Guardar configuración. El cambio es explícito, no automático. El botón conserva la clave del mismo proveedor si el nuevo perfil no tenía otra; mantiene intacto el perfil anterior. Después continúa en el mismo proyecto. También puedes escribir el identificador manualmente; en ese caso, introduce tu clave si queda vacía. Se acepta el prefijo `models/` y se normaliza.

**Actualizar:** cierra Nexo Tesis, respalda `%USERPROFILE%\.nexo-tesis` y copia el contenido de `NexoTesis` del nuevo ZIP sobre la carpeta de este agente. No lo copies sobre Nexo PC ni borres los datos de proyectos. Abre INICIAR-TESIS.cmd y realiza el cambio de modelo anterior. No se instalan paquetes ni se cambia tu plan de API.

Referencia verificada: https://ai.google.dev/gemini-api/docs/generate-content/get-started (ejemplo REST de `gemini-3.8-flash:generateContent`). No se ha probado tu cuenta ni una llamada autenticada desde el entorno de desarrollo.

## Empezar en Windows

1. Extrae el ZIP en **una carpeta nueva**, por ejemplo `Documentos\NexoTesis`. **No lo copies encima de Nexo PC.**
2. Abre **`INICIAR-TESIS.cmd`**. Utiliza tu Python existente, 3.11 o superior, con Tkinter y SQLite. No instala paquetes ni cambia el Python del sistema. Si creas un `.venv` propio dentro de esta carpeta, el lanzador puede utilizarlo; no copies entornos de otro producto.
3. En **Modelo y privacidad**, configura tu proveedor y el identificador del modelo disponible en tu cuenta: Groq, Gemini u Ollama. Los identificadores mostrados son configurables; no se garantiza disponibilidad o cuota. Ollama requiere que el programa y el modelo ya estén instalados en tu equipo.
4. Escribe tu tema en el cuadro de conversación y pulsa Enviar, o usa **Nuevo proyecto**. No hace falta completar un formulario de universidad, muestra o metodología.
5. Responde en el chat o pulsa **Continuar**. El agente podrá proponer el siguiente apartado y formular una pregunta cuando necesite información.

**Sin un modelo configurado** puedes crear proyectos, revisar lo guardado y preparar información, pero no hay redacción generativa ni conversación inteligente. La aplicación lo indica; no simula un modelo ni obtiene una clave por su cuenta.

### ¿Qué pasó con el caso de inglés?

Es un caso de prueba en `tests/test_scenarios.py`. La aplicación **inicia sin proyectos** y no presupone UCE, Educación, 24 estudiantes o investigación-acción. El segundo caso de prueba es una revisión documental sobre eficiencia energética. El perfil de estructura UCE es opcional y no se activa automáticamente.

## Cómo trabaja el agente

### Conversación primero

El modelo recibe el tema, decisiones del proyecto, asuntos pendientes y extractos pertinentes. Puede:

- Proponer delimitación, problemática, pregunta, objetivos, justificación y otros apartados adecuados al trabajo.
- Registrar datos explícitos del mensaje o del tema, mostrando procedencia y manteniéndolos revisables.
- Formular como máximo una pregunta estructurada por respuesta; puede combinar dos datos estrechamente relacionados.
- Continuar con propuestas provisionales cuando un dato no sea bloqueante.
- Solicitar una búsqueda temática y utilizar después los metadatos obtenidos.

La aplicación evita duplicar preguntas estructuradas respondidas o aplazadas, salvo una aclaración explícita. Esto no garantiza que cualquier modelo formule siempre la mejor pregunta ni que no repita algo dentro de su texto libre. Puedes corregirlo en la conversación y revisar Memoria.

**Aplazar pregunta** registra que todavía no la responderás. No inventa una respuesta. **Continuar** solicita un nuevo paso; no inicia un proceso infinito en segundo plano.

### Memoria separada por proyecto

Los proyectos conservan conversación, hechos declarados, fuentes, borradores, preguntas y documento vinculado. Abrir otro proyecto no transmite los datos del anterior al modelo y borra la autorización de selección Word en memoria.

Los hechos extraídos por el modelo no quedan certificados: exigir una cita literal comprueba procedencia textual, **no que la interpretación sea correcta**. En **Memoria → Corregir dato** puedes rectificarla. Cambiar o incorporar datos centrales marca borradores anteriores como **necesita revisión**; no los reescribe ni aprueba silenciosamente. Cambiar el tema retira hechos extraídos exclusivamente del título anterior, conserva registro de cambios y exige revisar los apartados. Para una investigación distinta, crea otro proyecto.

La conversación completa queda guardada. La pantalla muestra los últimos 100 mensajes por rendimiento; **Exportar expediente** incluye el historial completo. Se conservan seis estados recientes del proyecto y cinco versiones anteriores por apartado, consultables mediante estados anteriores/exportaciones. No hay recuperación ilimitada ni sincronización multiusuario.

### Apartados revisables

El modelo propone hasta dos apartados por respuesta, no una tesis completa. En **Apartados** puedes editar, guardar y aprobar un borrador. Una aprobación del usuario no certifica validez científica ni cumplimiento universitario.

Resultados, discusión y conclusiones requieren un registro de **datos/corpus** y tu confirmación en **Memoria → Confirmar datos** de que realmente están disponibles. Decir «no tengo datos» no desbloquea por sí solo esos apartados. Esta confirmación tampoco valida su calidad: el agente y el autor deben revisar el análisis. Antes puede desarrollar instrumentos, planes y análisis previstos.

No se fabrican datos para llenar huecos deliberadamente. Aun con controles, un modelo puede alucinar en texto libre: revisa toda cifra, afirmación y referencia antes de utilizarla.

### Fuentes

Activa **Permitir búsqueda** cuando quieras autorizar que el agente proponga una consulta. La consulta exacta se muestra antes de enviarla a Crossref. El permiso se reinicia al abrir otro proyecto o reiniciar la aplicación.

- Máximo una búsqueda de cinco resultados por turno.
- Crossref devuelve metadatos y, a veces, resúmenes; no es lectura de texto completo ni cobertura de todas las bases.
- Cada fuente tiene un identificador local `[F1]`, estado de consulta y procedencia. Un DOI existente no demuestra que respalde una afirmación.
- **Añadir fuente** permite registrar un fragmento realmente consultado, con título, autoría, año, localizador y alcance. **Editar fuente** permite corregir los metadatos y declarar el material disponible; las correcciones manuales no se etiquetan como verificación externa.
- Las citas a IDs inexistentes bloquean el guardado del apartado. El registro de referencias se compone a partir de las fuentes existentes; **no es aún un motor APA/CSL completo**.

No hay acceso automático a artículos de pago ni extracción automática de PDF en esta versión. Puedes aportar fragmentos pertinentes y permitidos, sin datos personales de participantes. No pegues textos completos innecesarios ni claves.

### Perfiles institucionales

El perfil general es provisional. En **Memoria → Perfil / guía** puedes aportar indicaciones de tu programa o seleccionar el perfil UCE de Educación, transcrito del PDF de tres páginas aportado durante las pruebas.

Ese perfil no está cotejado con una guía institucional completa y vigente. No se inventan márgenes, portada, paginación ni reglas bibliográficas ambiguas. UASD y otras instituciones no tienen todavía perfiles completos validados. El agente puede trabajar con propuestas generales y las reglas que aportes, señalando lo pendiente.

## Word de escritorio — conexión experimental

Se trabaja mediante el modelo de objetos de Word, **no con una biblioteca Python que genere DOCX**. La ventana sigue siendo la aplicación independiente; no se instala un complemento dentro de Word.

**La integración real con Word todavía no se ha probado en Windows. Primera prueba únicamente sobre una COPIA local sin datos sensibles.** Lee `PRUEBA-WORD.md` antes de utilizarla en un documento de trabajo.

1. Abre la copia en Word y guárdala como `.docx` desde Word.
2. En Nexo Tesis → Word, pulsa **Buscar abiertos** y elige el documento exacto.
3. En Word, selecciona un párrafo del cuerpo principal o coloca el cursor donde insertarás. Vuelve a Nexo y pulsa **Confirmar y leer**.
4. Nexo lee solo esa selección o ancla, no el documento entero. La lectura por sí sola no se envía al modelo.
5. Opcionalmente, **Revisar en chat** prepara un mensaje con hasta 4500 caracteres del fragmento. Debes autorizarlo y pulsar Enviar; el fragmento se guardará en el historial de ese proyecto y lo recibirá el proveedor. El documento se trata como material no confiable para instrucciones, no como decisiones del usuario.
6. Desde Apartados, **Preparar en Word** copia una propuesta al cuadro de revisión. No la inserta automáticamente.
7. Revisa el texto y aprueba **Insertar con revisiones** o **Añadir comentario**. La inserción añade texto, no reemplaza lo existente. Nexo activa temporalmente el seguimiento y restaura su configuración previa. Acepta o rechaza después desde Word; un comentario puede eliminarse.

Nexo comprueba documento, ventana, posición y huella del texto. Un cambio de selección exige releer. No edites Word durante la operación: estas comprobaciones no son una transacción contra edición simultánea.

No llama a Guardar, Guardar como ni modifica propiedades de autor. **AutoSave de Word puede guardar independientemente.** No modifica ni acepta revisiones anteriores. Las inserciones usan marcadores internos para registrar la operación; los comentarios incluyen `[Nexo:…]`.

Límites: documentos DOCX guardados, sin protección ni solo lectura; cuerpo principal, selección continua o cursor; no tablas, encabezados, notas o selección múltiple. Lectura máxima de 12 000 caracteres; inserción de 10 000; comentario de 6000. No aplica automáticamente estilos, índices, bibliografía Word ni maquetación final. Puede detectar solo una instancia de Word y requiere el mismo usuario/nivel de permisos. No desactives políticas de Office ni ejecutes como administrador para sortear un error.

Si ocurre un tiempo de espera o error, puede haber un efecto parcial. **Inspecciona Word antes de repetir.** No hay reintentos automáticos ni deshacer general. El registro local no sustituye una copia de seguridad del documento.

## Consumo, permisos y privacidad

- Máximo dos solicitudes al modelo por turno; la segunda solo se usa después de una búsqueda autorizada. Un error no dispara otra llamada de reparación.
- Contexto de proyecto acotado a 24 000 caracteres, más instrucciones y salida. Se incluyen decisiones y extractos priorizados por el tema, la petición y los IDs de fuentes mencionados; el historial completo permanece local. Puedes pedir revisar un apartado o una fuente antigua por su identificador. Esto no equivale a un límite exacto de tokens ni garantiza recordar cada detalle antiguo.
- Muestra tokens reportados por el proveedor cuando existen; no es el saldo ni el coste de tu cuenta.
- Cambiar de modelo conserva el proyecto. El proveedor recibe contexto solo después de tu autorización para ese proyecto/modelo durante la sesión.
- **Detener** impide nuevos pasos; no puede retirar una petición que ya salió. Espera a que termine o expire su tiempo antes de cerrar. No devuelve cuotas consumidas ni deshace Word.
- No hay terminal general, control de escritorio, envío de correo, compras o ejecución de código procedente de documentos/modelos.
- Guardar una clave utiliza Windows DPAPI del usuario actual cuando marcas Recordar. Sin esa opción, permanece solo en memoria. En otros sistemas no hay guardado en texto plano como alternativa.
- SQLite y exportaciones contienen texto legible del proyecto, **no cifrado**. Usa una cuenta/equipo protegidos y anonimiza los datos de estudiantes.

### Ubicación de datos

`%USERPROFILE%\.nexo-tesis\`

- `projects.sqlite3`: proyectos, checkpoints y registro de eventos.
- `config.json`: perfiles y claves cifradas si elegiste recordarlas.
- `word-audit\<proyecto>.jsonl`: intención/resultado de operaciones y huella de selección, sin texto del documento ni clave.

Respáldala **con Nexo Tesis cerrado**. No borres ni reemplaces `%USERPROFILE%\.nexo-pc`; pertenece al otro programa. Para actualizar futuras versiones del agente, conserva los datos separados.

## Pruebas y límites de la entrega

`PROBAR-TESIS.cmd` ejecuta pruebas con datos temporales, modelos y Word simulados; usa un servidor HTTP solo local para comprobar el transporte Ollama. En Windows incluye DPAPI con secreto inventado y análisis de sintaxis del script, sin conectarse a Word real.

`DIAGNOSTICO-TESIS.cmd` no usa la red, no abre Word ni muestra claves o contenido del proyecto.

Los resultados incluidos en `reports` distinguen:
- Pruebas unitarias y de interfaz real Tk.
- Dos búsquedas reales de metadatos Crossref.
- Transporte Ollama contra un servidor de prueba, **no inferencia real**.
- Parser PowerShell en Linux, **no automatización COM de Word**.

**No se probaron APIs de modelos con credenciales, inferencia de un modelo Ollama real ni Word real en Windows.** La calidad de redacción depende del modelo elegido y requiere evaluación con trabajos reales.

Quedan para ampliaciones posteriores: formato APA/CSL completo, validadores institucionales adicionales, lectura automática de documentos extensos, análisis estadístico especializado, maquetación Word avanzada, conversación por voz y especialización/ajuste de un modelo para Ollama. Nexo PC conserva sus propias funciones de voz; no se modificaron.
