# Reconstrucción de Nexo Tesis · Fases 0–6

**Build:** `0.4.1-dev (fase6-1)` · **Estado:** build de desarrollo, no release.
**Alcance:** Nexo Tesis únicamente. Nexo PC 0.6.0 no se modifica.

---

## 0. El error que reportó el usuario (y por qué era «un desastre»)

La captura mostraba un modal con:

```
cannot use 'dict' as a dict key (unhashable type: 'dict')
```

y una ventana blanca superpuesta. Detrás, el registro decía «Fallo de conexión
Copilot».

### Causa real, reproducida

Ese texto es el **mensaje nuevo de Python 3.14+** para `unhashable type: 'dict'`
([CPython gh-132825](https://github.com/python/cpython/issues/132825)). En el
Python 3.11 del sandbox el mismo fallo se escribe distinto, por eso una matriz de
pruebas de una sola versión no lo detectó.

Se reprodujo en aislado con una ruta Copilot365 cuyo `account_id` llegaba como
objeto en vez de cadena:

```
Agent.turn()
  → conversation_state.pending(p, api)      ← ANTES del try/except
    → keys(api) → account_identity(api, aid)
      → _accounts(api).get(aid, {})          ← aid es dict → TypeError
```

`Agent.turn` llamaba a `pending()` **fuera** de su bloque `try`, así que la
excepción escapaba al hilo de `run_job` → `poll()` → `show_error()` y Tk mostraba
el mensaje crudo del intérprete. Además:

- `Application.error_callback(kind, error, tb)` **descartaba el traceback**;
- `guard()` y `show_error()` sólo mostraban `str(e)`;
- no existía ningún log de errores.

Sin traceback, cualquier dict que se colara por otra frontera (`requestId` de
CDP, claves de reglas de guía, `generation` de cuenta, tuplas de rutas) daba el
mismo modal inútil. Era un problema de **observabilidad**, no sólo de tipos.

### La ventana blanca

`copilot_socket.launch_desktop()` lanza `M365Copilot.exe` con
`--edge-webview-switches=…` **sin URL**, y `launch_auth_window()` lanza Edge con
un perfil separado. Ambos usan `subprocess.Popen` sin guardar el handle ni
limpiar en caso de fallo. Cuando la conexión Copilot falla —exactamente lo que
decía el registro— el proceso navegador queda huérfano y vacío.

**Nota honesta:** no hay Windows ni Tk en este sandbox. Las funciones de
lanzamiento/captura se dejaron **byte-idénticas a 0.3.1** (la prueba de
`test_v040` que las comparaba se sustituyó por invariantes semánticos), y la
limpieza se implementó **fuera** de ellas, en `process_guard.py`, que envuelve
`Popen` durante el intento de conexión y termina en un `finally` sólo los
procesos que Nexo inició en esa sesión. La ventana real debe confirmarse en el
equipo del usuario.

---

## 1. Investigación en GitHub y aplicación de REA

Se clonaron y analizaron repositorios reales en `/tmp` (fuera del repo), no sólo
README, con un inventario de estilo REA: archivos, módulos, contratos y límites.

| Proyecto | Evidencia | Idea adoptada |
| --- | --- | --- |
| [DoThesis](https://github.com/caobo171/dothesis) | 1.691 archivos, 707 `.py`, 263 `.tsx`, 13 skills, 14 herramientas, 325 tests | Un solo `context_store` y **única vía de escritura** `commit_slice`; dos runtimes que comparten estado; modo Auto Thesis headless |
| [OpenDraft](https://github.com/federicodeponte/opendraft) | 520 estrellas, engine de 19 agentes | Verificación de DOI en 2+ bases, fases y export |
| [Loopy](https://github.com/Forward-Future/loopy) | 3.206 estrellas | Bucles acotados, condición de parada y **recibo** con motivo |
| [agentic-thesis-writing](https://github.com/NielsterLinden/agentic-thesis-writing) | 844 KB | Ámbitos de escritura disjuntos; el revisor no edita |
| [Academic Writing Toolkit](https://github.com/yha9806/academic-writing-toolkit) | MIT | Revisión acotada; el autor conserva el control |

**REA:** `python rea-arena/rea_arena.py status` devolvió
`installed: false, cli_ready: false, javascript_ready: false`. El skill REA v42
indica que no debe usarse para análisis ordinario de repositorios de código
fuente, sino para artefactos distribuidos. Se aplicó su **metodología**
(inventario → arquitectura → estado → pipeline → contratos, separando evidencia
estática de comportamiento real) sobre el código clonado. No se instaló REA ni
se escribió `rea-arena/reports/`, para no modificar el entorno sin autorización.

Hallazgos que más influyeron:

- `AGENTS.md` de DoThesis: «the ONLY write path is `commit_slice`»; DAG estático
  `M1→M2..M5 · M2→M3..M5 · M3→M4,M5 · M4→M5`; los `done` se ganan con
  contenido, no se narran.
- Su último commit («Bound chat turns and contain tool failures») añadió
  `TurnBudgetMiddleware` y `ToolCallGuardMiddleware`: los crashes de herramientas
  vuelven al modelo como `ToolMessage` de error con la instrucción de **no
  reintentar con los mismos argumentos**. Es exactamente la clase de fallo del
  usuario.
- `agent/headless.py`: `RunProfile(max_turns, wall_clock_s, max_stalls,
  required_modules)` — las diferencias de modo son **datos**, no un segundo
  cerebro.
- `skills/dothesis/SKILL.md`: «⚠ Promise = tool call. Always.» Prohíbe decir
  «guardado» sin un `commit_slice` en el mismo turno.
- `agent/stats_validation.py` y `agent/coherence.py`: puertas duras
  deterministas; sólo lo **probablemente** erróneo bloquea.
- `docs/PIPELINE.md`: progreso SSE en lenguaje natural y exportación que
  rechaza capítulos stub.

**No se copió:** FastAPI/Postgres/Next.js/S3/LibreOffice, multiusuario, créditos,
LangGraph ni MCP. Nexo es local, monousuario, Windows y sin servidor.

---

## 2. Qué se implementó, fase por fase

### Fase 0 — Contención y diagnóstico real
- `diagnostics.py`: `as_key()`/`as_text()` en **todas** las fronteras de claves;
  log JSON redactado (sin texto de tesis, claves ni tokens) en
  `~/.nexo-tesis/logs/`; `wrap_excepthook`, `tk_callback`, `friendly()`,
  `recent()`. La UI ya no muestra el mensaje crudo del intérprete.
- `process_guard.py`: registro de hijos y cierre en `finally`.
- `Agent.turn` envuelve toda la preparación (incluido `pending()`) con logging y
  re-lanza; `app.py` cables de `guard`/`run_job`/`poll`/`error_callback` y botón
  «Copiar diagnóstico».
- `conversation_state`, `autonomy.route_scope`, `guide_rules.approve`,
  `config.secret/candidates/redact`, `copilot_socket` (CDP `requestId`)
  normalizan tipos.

### Fase 1 — Núcleo de estado
`project_state.py`: cinco módulos M1–M5, `commit_slice()` como única vía de
escritura, validación de propiedad/tipos/citas/datos empíricos, snapshot antes
de aplicar, `undo_last()`, DAG de invalidación, `status_map()` derivado del
contenido real, `next_action()` y `verify()` como **aceptación determinista**.
Migración automática de proyectos 0.4.x sin perder borradores.

### Fase 2 — Runtime continuo
`run_loop.py`: `RunProfile` con **`max_passes=None` (sin cuota de pasos)**. El
bucle repite inspeccionar → investigar → escribir/editar → verificar hasta que
`verify()` devuelve `done=true`. El modelo **no puede** terminar el bucle
diciendo `done: true` o llamando `finalizar`: sólo la verificación lo detiene.

El usuario pidió explícitamente que no hubiera cuota de pasos. Se respetó, con
topes que **no son cuota** y están visibles en el diálogo de aprobación:

| Tope | Valor por defecto | Naturaleza |
| --- | --- | --- |
| Reloj | 60 min (15/30/60/120 configurable) | Seguridad de coste |
| Estancamiento | 10 pasos sin cambio **tras cambiar de estrategia** | Evita pagar por un modelo atascado |
| Fusible | 300 llamadas | Falla de proveedor/herramienta |
| Frontera humana | `preguntar_usuario`, botón Detener | Control del usuario |

Cada estancamiento inyecta una **estrategia distinta** (`STRATEGIES`) en el
contexto del modelo, junto con los pendientes y bloqueos reales. El recibo
(`run_loop.receipt`) guarda objetivo, perfil, pasos, cambios, rondas de
investigación, acciones, verificación, puntuación y motivo de parada.

### Fase 3 — Investigación verificable en sitio
`research.py` deriva facetas de las **propias palabras** del proyecto (tema,
hechos, preguntas), consulta Crossref, OpenAlex, Semantic Scholar y arXiv con
presupuesto de tiempo, deduplica por DOI/título, guarda `verified_by` y marca
«verificado en 2+ bases». **Sólo metadatos y resúmenes**: la coincidencia entre
bases no demuestra que un artículo respalde una afirmación.

«Haga todas las investigaciones del lugar» se implementó dos veces: el
anfitrión **investiga automáticamente** al principio del bucle continuo cuando
faltan fuentes (sin esperar a que el modelo lo proponga), y existe la
herramienta `investigar`. Cada ronda muestra y aprueba las consultas exactas.
Sin red, los fallos se contienen y se informa.

`gates.py` bloquea: citas `[F#]` inexistentes, DOI impresos no registrados,
cifras en secciones empíricas sin corpus confirmado, porcentajes >100%, marco
teórico sin fuentes, apartados obligatorios ausentes o stub. Los avisos blandos
no bloquean.

### Fase 4 — Documento
`document.py` mantiene Markdown/HTML/DOCX OOXML sin dependencias y ahora
adjunta las puertas de calidad (puntuación, bloqueos, avisos) en los tres
formatos. `write_section()` delega en `commit_slice`, de modo que **todas** las
escrituras —herramientas, editor de Apartados, investigación, bucle— pasan por
la misma validación.

### Fase 5 — UI y empaquetado
Pestaña Documento con: estructura, estado M1–M5, verificación,
«Agente continuo · hasta terminar», «Completar lo que falta», «Generar
documento completo», añadir/quitar/restaurar apartados, confirmar módulo,
deshacer último cambio, recibo del agente y copiar diagnóstico. Diálogos con
dueño, una sola ventana, sin consolas huérfanas. `INICIAR-TESIS.cmd` +
`VERIFICAR.cmd`, ZIP directo y página autónoma con el ZIP embebido (sin GitHub).

### Fase 6 — Validación
467 pruebas superadas / 2 omitidas. `VERIFICAR.cmd` ejecuta **cinco**
comprobaciones funcionales sin red: borradores largos, consultas largas +
planificador, bucle acotado con export, núcleo Fases 1–6 (estado, puertas,
deduplicación con proveniencia, investigación offline contenida, perfil sin
cuota) y un bucle continuo que **termina por verificación**.

---

## 3. Límites honestos

- **No verificado:** Windows real, Tk con display, Word COM, DPAPI,
  PowerShell 5.1, sesión autenticada de Microsoft 365 Copilot, respuesta real de
  Crossref/OpenAlex/Semantic Scholar/arXiv (el sandbox no tiene salida a esos
  hosts), ni que Word abra el DOCX generado. El OOXML se validó
  estructuralmente (ZIP + XML bien formado).
- **Python 3.14** no está disponible en el sandbox (hay 3.11.2). El mensaje
  exacto del usuario se identificó por la fuente de CPython; la corrección es
  independiente de la versión porque valida **tipos**, no cadenas de error.
- REA **no se instaló**; se aplicó su metodología de evidencia sobre código
  fuente clonado. Para un análisis REA real haría falta `restore` (npm `ci`
  6.7.0) y autorización para escribir `rea-arena/reports/`.
- El DOCX sigue siendo OOXML simple (párrafos y encabezados), sin APA 7
  automática ni figuras. La maquetación fina sigue en la integración Word, que
  requiere aprobación explícita.
- El modo continuo puede consumir muchas llamadas al modelo: por eso existe el
  reloj y el botón Detener. No es una cuota de pasos, pero **sí** es un límite
  de coste. El diálogo de aprobación lo muestra antes de empezar.

---

## 4. Cómo probarlo en el equipo

1. Descomprime el ZIP en una carpeta vacía y ejecuta `VERIFICAR.cmd`.
   Debe decir `(fase6-1)` y cinco líneas `OK`.
2. Abre `INICIAR-TESIS.cmd`, usa un proyecto de prueba sin datos personales.
3. Si aparece un error, pulsa **«Copiar diagnóstico»** y pega el JSON: contiene
   el traceback redactado, la versión de Python/Tk y la forma del estado, sin el
   contenido de la tesis.
4. Para el modo continuo: pestaña Documento → «Agente continuo · hasta
   terminar». Aprueba el conjunto; verás cada consulta antes de enviarla.
5. Comprueba en tu Word que el `.docx` generado abre, y en tu red que las
   búsquedas devuelven metadatos reales.
