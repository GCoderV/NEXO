# Nexo PC 0.6.0 — Tesis (piloto)

## Qué se entrega

Un módulo dentro de Nexo PC, accesible mediante **Tesis**. Es un primer incremento funcional, no el agente de tesis completo. No instala software, no sustituye Python y no cambia los entornos de voz.

El piloto viene configurado con el tema aportado: juegos de roles cooperativos para fortalecer la producción oral en inglés en 3.º de secundaria del Centro Educativo Divino Maestro, período 2026–2027; UCE, grado, Educación, investigación-acción.

Incluye 24 participantes en el diagnóstico escrito y oral, sus tareas y las observaciones aportadas. Reconoce **dominio limitado para el grado según valoración docente y miedo a hablar**, sin afirmar que una variable cause la otra. No incluye nombres de estudiantes ni frecuencias inventadas.

## Actualizar desde Nexo 0.5.0

1. Cierra Nexo. Haz copia de tu carpeta del programa y de `%USERPROFILE%\.nexo-pc`.
2. Extrae **nexo-pc-v0.6.0-actualizacion.zip**. Copia todo el contenido de su carpeta `NexoPC` **dentro de la carpeta donde ya tienes Nexo 0.5.0**, aceptando reemplazar archivos.
3. **No borres `models`, `.venv` ni `.venv-voz`.** Este ZIP de actualización no repite el modelo de reconocimiento de voz de 40 MB. Usa el que ya tienes en 0.5.0.
4. Abre `INICIAR.cmd`; debe aparecer **0.6.0 · Tesis piloto**. Pulsa **Tesis** arriba.

No necesitas reinstalar bibliotecas para las funciones académicas locales. No se ha ejecutado esta actualización en tu PC. No ejecutes dos versiones simultáneamente.

## Las seis pestañas

### Expediente

Selecciona el campo que deseas editar: título, período, diagnóstico, tareas orales, observaciones, pregunta, objetivos o hipótesis. El número 24 corresponde a participantes del diagnóstico, no a una afirmación de muestreo o matrícula total.

Guarda mediante **Guardar expediente**. Los objetivos y la hipótesis precargados son propuestas, no texto aprobado por el asesor.

### Evidencias

Distingue autopercepción, observación docente, respuestas a pruebas y documentos aportados. Selecciona una evidencia y pulsa **Editar evidencia / frecuencia real**. Deja cantidad y denominador vacíos cuando no existan conteos. El programa rechaza cantidades mayores que el denominador y denominadores superiores al número de participantes.

No convierte «muchos», «algunos» o «la mayoría» en porcentajes. Las frecuencias que introduzcas son datos declarados por ti, no verificados automáticamente por Nexo.

### Plan de acción

Cuatro actividades iniciales propuestas: preparación lingüística, ensayo cooperativo gradual, entrevistas/juegos de roles y reflexión con evaluación comparable. Cada actividad conserva los siete campos del PDF y sus vínculos con evidencias.

Las duraciones permanecen pendientes. No se inventa un calendario de 12 semanas ni una intervención ya realizada. En esta versión puedes editar los campos de estas cuatro actividades; añadir/eliminar actividades desde la interfaz queda para la siguiente ampliación. Las etapas de acción y evaluación se planifican para el proyecto completo; el anteproyecto no presenta sus resultados como realizados.

### Fuentes

Registro manual de título, autoría, año, DOI/URL o referencia local, fragmento, localizador y afirmación respaldada. El estado de lectura es una declaración del usuario. **No es búsqueda bibliográfica automática, verificación externa ni motor APA completo.** No hay referencias ficticias precargadas.

### Guía y revisión

Muestra la estructura del PDF que aportaste, con páginas de procedencia. Comprueba campos ausentes, vínculos de evidencias, frecuencias, metadatos y advertencias metodológicas mediante reglas locales.

No certifica el cumplimiento institucional ni evalúa por sí solo la validez de una fuente o de un diseño. La guía completa, márgenes, portada, formato bibliográfico ambiguo y contraste curricular siguen pendientes. El documento aportado se incluye en `referencia-academica` para consulta.

### Word — experimental, requiere prueba en Windows

Usa **Word de escritorio ya abierto**, mediante su modelo de objetos nativo. No crea archivos DOCX con Python, no abre documentos por su cuenta, no ejecuta macros y no cambia la seguridad de Office. No requiere `pywin32`; utiliza Windows PowerShell 5.1 del sistema con un script fijo y datos separados.

**Primera prueba: usa una COPIA local de un documento sin información sensible.**

1. Abre la copia en Word y guárdala como `.docx` mediante Word. Si usas AutoSave/OneDrive, recuerda que Office puede guardar cambios por su cuenta; para el primer ensayo es preferible una copia local.
2. En Tesis → Word, pulsa **Buscar abiertos**. Se listan nombres/rutas, no se lee el contenido.
3. Selecciona el archivo exacto. En Word, selecciona un párrafo de texto normal del cuerpo principal. No tablas, encabezados ni comentarios.
4. Vuelve a Nexo y pulsa **Confirmar y leer**. Confirma el documento. Se leerá únicamente la selección (máximo 12 000 caracteres), que permanece en memoria y no se envía al modelo.
5. Escribe un comentario en el cuadro de propuesta. Pulsa **Revisar y añadir comentario** y aprueba.
6. Nexo comprueba documento activo, ventana, posición y huella del texto antes de comentar. No edites ni cambies la selección durante esa breve operación.
7. Comprueba el comentario en Word. Puedes **eliminarlo** desde Revisar. El texto original no se sustituye. Nexo no llama a Guardar ni cierra Word; guarda tú si deseas conservarlo. AutoSave puede actuar independientemente.

Se añade una marca de operación `[Nexo:…]` al comentario para rastrear la operación y evitar duplicados. No se cambia el nombre de autor de Office. No se aceptan ni rechazan revisiones existentes y no se promete ocultar la asistencia.

Cada comentario consume la selección leída: para otro comentario debes leer de nuevo. Si hay error o espera agotada, la operación puede haber ocurrido parcialmente. **Inspecciona Word antes de reintentar.** No hay reintentos automáticos.

**Límites:** puede detectar solo una instancia de Word. Ejecuta Nexo y Word con el mismo usuario y sin diferencias de elevación. No admite documentos sin guardar, formatos `.doc`/`.docm`, vista protegida, documentos protegidos, selección múltiple, encabezados, tablas o rangos de más de 12 000 caracteres. No reemplaza párrafos, no aplica estilos, no crea índices, no gestiona citas de Word ni control de cambios de texto todavía. La comprobación de rango no constituye una transacción frente a edición simultánea: no edites mientras comenta.

## Revisar con el modelo sin reenviar todo

**Preparar diagnóstico en el chat** o **Preparar plan en el chat** prepara un mensaje de hasta 5 500 caracteres. Si excede ese límite, avisa en lugar de truncarlo silenciosamente.

- Pide confirmación antes de preparar el contexto y no pisa un borrador existente.
- No incorpora la selección de Word.
- Guarda el expediente, deja el chat en **Planificar** y desactiva autonomía, permisos amplios y todas las herramientas (incluida lectura de archivos) para esa revisión.
- **No pulsa Enviar**. Revisa el mensaje y el proveedor antes de enviarlo. Al enviar, el proveedor recibe el contexto; los límites y costes habituales se mantienen. El historial de ese chat puede incluir otros contenidos anteriores.
- El material fuente es información, no autorización para ejecutar instrucciones. Si luego decides reactivar herramientas o Actuar, vuelven a aplicar los permisos generales de Nexo.

La configuración especializada de Ollama no está incluida aún. Los adaptadores anteriores de Groq/Gemini/Ollama siguen disponibles.

## Archivos locales y privacidad

- `%USERPROFILE%\.nexo-pc\academic\project.json`: expediente de trabajo en texto legible, **sin cifrado**. Usa un equipo y una cuenta protegidos; no incluyas nombres ni otros datos sensibles de estudiantes.
- `project.previous.json`: copia anterior después de cada guardado posterior al primero.
- `project.lock`: bloqueo temporal de guardado. Si hubo cierre abrupto y permanece, cierra Nexo, respalda los archivos y elimina solo el bloqueo para reintentar.
- `word-audit.jsonl`: identificadores de operación, estado y huella de selección; no guarda texto, comentario, ruta del documento ni claves.

Los cambios externos al expediente provocan un conflicto, no una sobrescritura silenciosa. No hay edición colaborativa multiusuario ni recuperación ilimitada de versiones.

**Exportar informe .md** genera un informe Markdown del expediente, no un DOCX ni una tesis terminada. La edición nativa se hace exclusivamente a través de Word.

## Pruebas

- `PROBAR.cmd`: incluye las pruebas de regresión anteriores y las nuevas académicas; usa datos temporales y modelos simulados. Las pruebas Windows anteriores incluyen comandos inocuos/DPAPI. No conecta a Word real.
- `PROBAR-TESIS.cmd`: pruebas académicas y de interfaz con Word simulado, sin claves ni documentos personales. En Windows comprueba también la sintaxis del script sin ejecutarlo contra Word.
- La aceptación nativa pendiente es el procedimiento anterior sobre una copia de prueba. No se da por válida por pasar mocks en Linux.

No instales ni cambies políticas de seguridad para sortear un error. Conserva el mensaje exacto, ocultando rutas privadas si lo compartes.
