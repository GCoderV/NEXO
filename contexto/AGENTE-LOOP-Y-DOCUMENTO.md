# Agente con herramientas, bucle acotado y documento completo

**Estado:** implementado en `0.4.1-dev (agentloop-1)`. Build de desarrollo, no release.
**Alcance:** Nexo Tesis únicamente. Nexo PC 0.6.0 no se toca.

## 1. Punto de partida (lo que ya estaba corregido en este mismo turno)

Antes del bucle se eliminaron dos causas reales del punto muerto:

- `agent.unpack` rechazaba cualquier `search.query` de más de 250 caracteres.
  Las consultas booleanas reales del usuario tenían 340 y 414 caracteres, de modo
  que **la búsqueda nunca se autorizaba ni llegaba a Crossref**. Ahora se aceptan
  hasta 2000 caracteres y `bibliography.normalize_queries()` las convierte en un
  máximo de 3 consultas simples de ≤180 caracteres: conserva las frases entre
  comillas, elimina `AND/OR/site:/filetype:`, genera una consulta núcleo enfocada
  y dos variantes con calificadores rotados. Cada subconsulta se ejecuta por
  separado y sus resultados se agregan con IDs `F#` monótonos.
- `autonomy.plan()` excluía `instrumentos` salvo que existiera un **dato** de
  metodología (no bastaba el borrador), excluía `cronograma/presupuesto/anexos`
  salvo guía aprobada, `referencias` sin fuentes, `plan_accion` sin «acción» y los
  borradores ya revisados para la huella actual. Ahora: un borrador de metodología
  desbloquea instrumentos; los apartados opcionales se generan como **plantillas**
  con campos «Por definir» (activados por defecto en la UI); el aviso, cuando no
  hay tareas, enumera las causas concretas y la acción que las desbloquea;
  «Antecedentes» se exige como subapartado del Marco teórico; Referencias se
  reconstruye desde el registro de fuentes, nunca desde texto del modelo.

Además se añadió el botón **«Buscar fuentes»**, que no depende de que el modelo
proponga la búsqueda: el usuario escribe términos, ve las consultas exactas antes
de aprobarlas y puede añadir fuentes a mano si no hay conexión con Crossref.

## 2. Investigación de proyectos similares (26 oct 2026)

Se revisaron repositorios públicos y sus README, sin copiar código. Ideas
funcionales que sí se adoptaron:

| Proyecto | Idea aprovechada | Cómo se aplicó aquí |
| --- | --- | --- |
| [DoThesis](https://github.com/caobo171/dothesis) | Un único `context_store` por proyecto con **una sola vía de escritura** (`commit_slice`) que valida y propaga `needs_review`; modo «Auto Thesis» de un clic; herramientas de búsqueda y exportación; actividad de herramientas visible en lenguaje natural. | `document.write_section()` / `patch_section()` son la única vía de mutación; `start_agent_loop()` es el equivalente acotado de un clic; cada paso emite un registro legible. |
| [Loopy / Loop Library](https://github.com/Forward-Future/loopy) | Un bucle no es «sigue mejorando»: tiene **pasos acotados**, una comprobación de aceptación tras cada pasada, una condición de parada explícita y un **recibo** con acciones, evidencia, resultado y motivo de parada. «Los bucles no son permiso para ejecutar indefinidamente». | `Agent._loop_pass()` con `max_passes` (1–12), parada por `finalizar`, `done`, pregunta al usuario, sin herramientas, límite de pasos o falta de progreso medible tras dos pasadas. `p['last_loop']` e `p['loop_receipts']` guardan el recibo. |
| [agentic-thesis-writing](https://github.com/NielsterLinden/agentic-thesis-writing) | **Ámbitos de escritura disjuntos**: el revisor no edita, el redactor no ejecuta código; las notas de traspaso son el único canal; una reescritura se aplica solo ante una orden literal. | El agente nunca toca Word, ni la configuración, ni `~/.nexo-tesis` fuera de su carpeta de documentos. Los apartados aprobados/editados por la persona están protegidos. `editar_texto` exige un anclaje exacto y único. |
| [Academic Writing Toolkit](https://github.com/yha9806/academic-writing-toolkit) | Revisión acotada, «clean-room review» y gobierno de la entrega: **la autora conserva el control de afirmaciones, límites, aprobaciones y del artefacto exacto que se entrega**. | Toda exportación es local y explícita; el documento marca «Por redactar» en vez de rellenar; el recibo indica los huecos. |
| [OpenDraft](https://github.com/federicodeponte/opendraft) | Fases separadas investigación → estructura → redacción → citas → exportación, con DOI verificados contra varias bases. | No se copió la verificación multi-base (requiere red y varias API), pero sí la separación de fases y la negativa a imprimir una referencia no registrada. |
| [open-paper-machine](https://github.com/TobiasBlask/open-paper-machine) | Un plan de cambio se presenta en tabla y **nada se ejecuta sin aprobación**; verificación desde el PDF compilado. | El diálogo de «Agente con herramientas» muestra objetivo, número de pasos, carpeta de exportación y permisos antes de iniciar. |
| [paper-revision-skill](https://github.com/lachlanchen/paper-revision-skill) | «Plan first. Edit second. Verify.» Revisiones planificadas, no ediciones impulsivas. | El prompt del bucle obliga a inspeccionar antes de escribir y a comprobar el resultado en el paso siguiente. |
| [agentic-research](https://github.com/djjay0131/agentic-research) | Matriz de citas y agentes con responsabilidades separadas (redacción, citas, originalidad, revisión). | Las citas `[F#]`/`[D#]` se validan contra el registro antes de guardar; `referencias` se genera en el anfitrión. |

**Decisión deliberada:** no se usa *function calling* nativo. Copilot365 es un
puente de chat sobre la sesión M365 del usuario, no una API de herramientas;
Gemini, Groq y Ollama tampoco exponen el mismo contrato. El bucle usa **JSON en
texto** (`{"reply","tool_calls","done"}`), validado por `agent_tools.validate_calls`,
para que funcione con todas las rutas ya soportadas. El campo `calls` nativo que
devuelve `api.request` sigue rechazándose: ninguna herramienta se ejecuta por un
canal no declarado.

## 3. Arquitectura añadida

```
document.py      estructura ordenada del documento + ÚNICA vía de escritura
                 + export Markdown / HTML / OOXML .docx (stdlib, sin Word)
agent_tools.py   15 herramientas: 5 de lectura, 8 de escritura/edición,
                 búsqueda, exportación, dato del usuario, pregunta, finalizar
agent.py         Agent.turn(..., loop=...) + Agent._loop_pass()
prompt_policy.py LOOP + loop_instructions() (contrato completo en cada pasada)
app.py           pestaña «Documento», botón «Agente con herramientas»,
                 recibo, exportación manual, alta/ocultado de apartados
```

Herramientas disponibles para el modelo (nombres exactos):

`ver_documento`, `ver_estado`, `ver_pendientes`, `leer_apartado`, `listar_fuentes`,
`buscar_fuentes`, `escribir_apartado`, `editar_texto`, `anadir_apartado`,
`quitar_apartado`, `restaurar_apartado`, `generar_documento`, `registrar_dato`,
`preguntar_usuario`, `finalizar`.

### Reglas duras (anfitrión, no prompt)

1. **Límites:** máximo 4 herramientas por pasada, 1–12 pasadas, argumentos
   ≤25 000 caracteres, texto de apartado recortado a 20 000 con aviso visible.
2. **Una acción de escritura por pasada** recomendada en el contrato; se
   comprueba el estado (`with_draft`, `missing`, `needs_revision`, `hidden`,
   `sources`) tras cada pasada. Dos pasadas consecutivas sin cambio medible →
   parada `sin_progreso`.
3. **Fallos contenidos:** `agent_tools.execute` nunca propaga una excepción al
   bucle; devuelve `{ok:false, summary}` y el recibo lo registra.
4. **Citas:** `document.write_section` verifica que todo `[F#]`/`[D#]` exista en
   el proyecto. `referencias` se reconstruye desde `p['sources']`.
5. **Sin invención:** `resultados/discusion/conclusiones` exigen `data_ready` y el
   dato `datos`; `registrar_dato` exige origen `usuario` y evidencia literal;
   los apartados aprobados, editados por la persona o insertados en Word son
   inmutables para el agente.
6. **Búsqueda:** requiere «Permitir búsqueda» **y** aprobación de la consulta
   exacta. Sin red, el fallo se informa y se ofrece alta manual.
7. **Word:** el agente no modifica Word. Escribe archivos nuevos en
   `~/.nexo-tesis/documentos/`; ocultar un apartado conserva su borrador.
8. **Recibo:** `last_loop` con objetivo, pasos, cambios, motivo de parada,
   acciones y estado final; se conservan los últimos 5 en `loop_receipts`.

### Exportación del documento completo

`document.export()` genera tres archivos a partir del mismo estado:

- `.md` — tesis completa con estado, índice, apartados y huecos.
- `.html` — página autónoma, imprimible, abrible directamente en Word.
- `.docx` — paquete OOXML mínimo (`[Content_Types].xml`, relaciones,
  `word/document.xml`, `word/styles.xml`) escrito con `zipfile` de la biblioteca
  estándar. No requiere `python-docx` ni Word.

Los apartados sin borrador se imprimen como `**[Por redactar]**`, no se rellenan.
Las Referencias se generan solo con fuentes registradas.

## 4. Uso

1. Pestaña **Documento** → «Completar lo que falta» (o botón «Agente con
   herramientas» en Conversación, con objetivo propio y 2/4/6/8/12 pasos).
2. Aprobar el diálogo: muestra objetivo, pasos, carpeta de exportación y límites.
3. El chat muestra cada paso y el resultado de cada herramienta.
4. «Generar documento completo» exporta sin consumir llamadas al modelo.
5. «Ver recibo del agente» muestra acciones, parada y huecos pendientes.

## 5. Pruebas y límites honestos

- 416 pruebas locales superadas / 2 omitidas (fixtures sintéticas).
- `VERIFICAR.cmd` ejecuta `check_long_draft()`, `check_research()` y
  `check_loop()`: este último corre un bucle completo de 3 pasos con un modelo
  stub, **sin red**, escribe un apartado, genera los tres formatos y valida el
  ZIP/XML del DOCX. Marca de build: `(agentloop-1)`.
- **NO verificado en este entorno:** Tk real (no hay display), Word COM, que
  Microsoft Word abra el DOCX generado, DPAPI, PowerShell de Windows, sesión
  real de Microsoft 365 Copilot ni respuesta real de Crossref (el sandbox no
  tiene salida a `api.crossref.org`). El formato OOXML se validó
  estructuralmente; la apertura en Word debe comprobarse en el equipo del
  usuario.
- El DOCX es deliberadamente simple: párrafos y encabezados, sin numeración
  APA 7 automática, sin tablas de contenido de Word, sin figuras. Para
  maquetación fina sigue estando la integración Word existente, que requiere
  aprobación explícita.
