# Investigación previa y decisiones de implementación

Fecha de referencia del trabajo: 24 de octubre de 2026. Producto: **Nexo Tesis 0.1.0**, independiente de Nexo PC.

## 1. Memoria y ejecución por proyecto

Se revisaron las guías de persistencia e interrupciones de LangGraph. Distinguen el estado de un hilo/proceso de otros datos persistentes y muestran cómo una interrupción guarda estado antes de esperar intervención. También advierten que al reanudar pueden volver a ejecutarse las operaciones previas a la interrupción.

- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/interrupts

**Decisión:** SQLite local con identificador independiente por proyecto, control optimista de revisión, seis checkpoints recientes y registro de intención antes de llamadas. No se comparte un almacén de hechos entre proyectos. Reanudar no reproduce automáticamente llamadas pendientes.

No se incorporó LangGraph como dependencia ni se copió su implementación. Se estudiaron sus contratos y se aplicaron a una máquina de estados propia y acotada, para no instalar un servidor/framework pesado. Las pruebas propias no demuestran equivalencia con LangGraph.

## 2. Investigación bibliográfica acotada

La documentación de Crossref describe una API pública de metadatos depositados por miembros y fuentes de confianza, sin registro obligatorio. Incluye registros bibliográficos y, en algunos casos, resúmenes. Una búsqueda no demuestra lectura del artículo ni adecuación de una referencia a una afirmación.

- https://www.crossref.org/documentation/retrieve-metadata/rest-api/

**Decisión:** consultas a un único endpoint HTTPS conocido, sin navegación arbitraria, máximo cinco resultados y una búsqueda por turno. El usuario autoriza la consulta exacta. Cada resultado registra DOI, procedencia, fecha y estado de lectura; texto completo no se presume. El agente puede hacer una segunda llamada al modelo para trabajar con lo encontrado. No se eluden paywalls ni se aplica un criterio de selección de literatura como si fuera una revisión sistemática terminada.

**Prueba real:** `reports/crossref-live.json` contiene dos consultas temáticas ejecutadas con el adaptador implementado. Se recuperaron metadatos para educación/inglés y para eficiencia energética. No se leyeron artículos completos ni se evaluó su calidad. La búsqueda requiere Internet; no es una promesa de servicio ilimitado o siempre disponible.

## 3. Respuestas estructuradas y proveedor sustituible

Se revisó el modo de respuestas estructuradas de Ollama:

- https://docs.ollama.com/capabilities/structured-outputs

**Decisión:** el modelo propone JSON con explicación, hechos sustentados en una cita literal del último mensaje o del tema aportado, hasta dos borradores, una pregunta y una solicitud de búsqueda opcional. El host valida el esquema, IDs de fuentes, evidencias literales y condiciones de resultados; no ejecuta nombres de herramientas emitidos por el modelo. Las salidas no conformes se rechazan sin reparación/reintento automático que gaste tokens adicionales.

El soporte de JSON no garantiza verdad, calidad metodológica o ausencia de alucinaciones. Una cita literal demuestra procedencia textual, no que la interpretación del modelo sea correcta. Memoria y apartados son revisables.

Transportes Groq/Gemini/Ollama adaptados del Nexo PC anterior, eliminando herramientas de PC y dependencias sobre aquel programa. No se importan sus claves o preferencias. Ollama se restringe a loopback, sin redirecciones, y bloquea identificadores con `cloud`; esto no prueba por sí solo que una instalación local del usuario nunca delegue llamadas.

## 4. Trabajo nativo en Word

Se revisaron las propiedades y métodos oficiales de Word para control de cambios e inserción después de un rango, además de los contratos anteriores de selección y comentarios:

- https://learn.microsoft.com/en-us/office/vba/api/word.document.trackrevisions
- https://learn.microsoft.com/en-us/office/vba/api/word.range.insertafter
- https://learn.microsoft.com/en-us/office/vba/api/word.selection
- https://learn.microsoft.com/en-us/office/vba/api/word.comments.add

**Decisión:** conector COM vía script fijo de Windows PowerShell 5.1. Confirmar un DOCX abierto, leer solo una selección o ancla y aprobar comentario/inserción. Las inserciones activan seguimiento temporalmente y restauran la configuración anterior. No reemplaza texto existente ni acepta revisiones. No llama a Guardar, Guardar como ni altera propiedades de autor. Word AutoSave puede actuar independientemente.

Datos pasan por stdin como JSON, no interpolados en comandos. Valida ruta, ventana, rango y hash. La autorización de lectura se consume al mutar, incluso si falla. Se registra intención antes del efecto y no se reintenta automáticamente. No hay una transacción contra cambios simultáneos del usuario: hay que dejar Word quieto durante la operación.

**Pruebas:** transporte simulado y revisión de sintaxis mediante el parser de PowerShell 7.4.6 en Linux, sin errores. Eso **no prueba COM, Word real ni Windows PowerShell 5.1**. La primera aceptación nativa debe realizarse en una copia local. No se genera un DOCX con una biblioteca Python.

## 5. Reutilización frente al producto anterior

- Reutilizado/adaptado: transporte HTTP de proveedores, protección DPAPI y contrato acotado del puente Word.
- Nuevos: aplicación independiente, almacenamiento SQLite multiproyecto, flujo académico conversacional, memoria tipada con procedencia, invalidación de borradores, preguntas persistentes, catálogo bibliográfico y contexto acotado.
- No reutilizados: panel fijo de tesis dentro de Nexo PC, expediente precargado, automatización general de escritorio/terminal, rutas de datos del otro producto ni permisos amplios.
- El estudio previo parcial de Cline sirvió al runtime original; no se presenta este agente como un clon ni como una implementación equivalente de Cline o LangGraph.

## 6. Cobertura real y límites

- El inicio está vacío. El caso de inglés y los 24 participantes existen solamente en las pruebas, no como proyecto inicial.
- Rutas conversacionales abiertas a distintos temas y métodos; no todas las especialidades o normas universitarias tienen validadores específicos.
- Perfil general provisional y perfil UCE de Educación opcional, basado en el PDF aportado. No hay perfil UASD completo validado.
- No hay motor CSL/APA final, búsqueda en todas las bases, extracción automática de PDFs, validación estadística, dictamen de plagio ni entrenamiento de un modelo especializado.
- Las pruebas con respuestas guionizadas validan el flujo y la persistencia; **no miden calidad de redacción de un modelo real**.

El contexto prioriza fuentes mencionadas por ID y coincidencias temáticas, además de apartados pedidos explícitamente. La selección es determinista y acotada, no una búsqueda semántica exhaustiva ni una prueba de pertinencia de la fuente.
