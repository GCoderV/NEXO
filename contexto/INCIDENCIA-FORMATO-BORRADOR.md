# Incidencia real: «La respuesta no cumple el formato académico» en Marco teórico

El usuario envió la respuesta exacta del modelo. Era un **JSON válido**:

```json
{"text": "### Marco teórico\n\n...11 000 caracteres...", "sources": [], "reply": "..."}
```

No era un problema de JSON, ni de texto envolvente, ni de comillas. El fallo
estaba en el **validador de longitud**: `agent.unpack` rechazaba cualquier
borrador con más de 10 000 caracteres, mientras:

- `project_store.update_draft` aceptaba hasta 20 000,
- `prompt_policy.DRAFT` (el contrato que recibe el modelo en una tarea
  automática) **no mencionaba ningún límite**,
- `prompt_policy.DIALOGUE` sí decía 10 000, pero no se usa en tareas.

Por eso fallaba siempre el apartado más largo —el marco teórico— y no los
anteriores (delimitación, problemática, pregunta, objetivos, justificación). El
mensaje nuevo de la versión anterior lo confirmaba: «el borrador propuesto no
cumple el contrato».

## Corrección (sin reformular el mensaje: eliminando la causa)

1. **`limits.py`** como única fuente de verdad:
   `MAX_RESPONSE_CHARS=150000`, `MAX_DRAFT_CHARS=20000`,
   `MAX_REPLY_CHARS=10000`, `MAX_CONTEXT_CHARS=40000`.
   `agent`, `prompt_policy`, `project_store` y `context_policy` lo importan.
   Se subió el contexto de 24 000 a 40 000 para que un borrador de 20 000
   caracteres pueda revisarse sin que el contexto esencial reviente.
2. **Nunca rechazar por longitud**: `_fit_draft` recorta en un límite de
   párrafo y escribe **dentro del borrador** el aviso
   «Borrador recortado por el límite local de 20000 caracteres…». El usuario ve
   qué pasó y puede continuar; no se inventa contenido.
3. **Normalización del borrador en tareas**: se ignora el campo `section` del
   modelo (ya sabemos qué apartado se pidió), se aceptan etiquetas con acentos,
   alias en español (`borrador`, `contenido`, `fuentes`, `resumen`), texto como
   lista de párrafos, y `sources` con dicts/enteros/prosa (solo se conservan
   ids `F#`/`D#` bien formados). Si el modelo manda el apartado completo dentro
   de `reply`, se promueve a borrador solo cuando es texto sustancial
   (≥1200 caracteres y varias frases/párrafos), nunca una promesa corta.
4. **Prompt explícito**: `DRAFT` e `INCREMENTAL_TASK` indican el límite de
   20 000 caracteres y piden entregar la primera parte completa con nota de
   continuación si hace falta, en lugar de responder solo con una promesa.
5. **Errores más granulares** (`Apartado de borrador no reconocido`,
   `Texto de borrador ausente`, `Borrador con estructura inválida`) por si
   queda algún caso: el registro dirá exactamente qué pasó sin volcar la
   respuesta del modelo.

Se **revirtió** un intento de sanear citas desconocidas dentro de
`apply_proposal`: las pruebas demostraron que rompía la garantía de privacidad
que impide guardar un borrador que cite un archivo no autorizado. Esa regla
queda intacta.

## Otros dos errores del mismo registro

- **Gemini 404 «model no longer available»**: el propio proveedor nombra el
  sustituto (`models/gemini-3.8-flash`). Ahora, cuando la petición se hace
  desde `RoutedAPI`, se actualiza la ruta en `config.json` (misma cuenta, mismo
  proveedor; no cambia el destinatario autorizado) y se envía **una sola vez**
  al modelo nuevo. Un 404 no procesó nada, así que no hay riesgo de duplicar.
  Sin ese contexto (prueba directa de `API`), se conserva el error accionable
  de siempre. Se respeta la decisión de no cambiar el modelo **al cargar** la
  configuración sin una acción del usuario.
- **HTTP 400**: si elproveedor rechaza `response_format` /
  `responseMimeType`, se reintenta **una vez** sin ese parámetro opcional (un
  400 tampoco procesó nada). Cualquier otro 400 informa ahora de un motivo
  corto y saneado: sin claves, sin URLs y sin cadenas largas.

## Pruebas

Nuevas: `tests/test_borrador_largo_v041.py` (11 casos, incluido el marco
teórico real de 11 000 caracteres de extremo a extremo y uno de 30 000 con
recorte visible) y `tests/test_errores_http_v041.py` (5 casos). Total local:
**366 superadas / 2 omitidas**. Las respuestas se generaron con fixtures; no
hubo sesión autenticada de Microsoft ni Word real.

## Qué debe hacer el usuario

Cerrar Nexo, descomprimir el **ZIP nuevo** en una carpeta vacía y abrir
`INICIAR-TESIS.cmd`. Sus proyectos siguen en `%USERPROFILE%\.nexo-tesis`, así
que conserva los apartados ya guardados. Pulsar **Reanudar** para el apartado
pendiente: ahora el marco teórico se guardará. Si apareciera de nuevo un aviso
de formato, el registro indicará el motivo concreto.
