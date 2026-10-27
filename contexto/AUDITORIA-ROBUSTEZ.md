# Auditoría de robustez · Nexo Tesis 0.4.1-dev

Fecha: 26 de octubre de 2026. Alcance: el runtime de `nexo-tesis/` que se entrega
en `releases/nexo-tesis-v0.4.1-dev-windows.zip`. No se rehízo el diagnóstico de
continuidad de Copilot ni se modificaron `launch_desktop`, `launch_auth_window`,
`capture_connection` ni `sanitize_frame` (protegidos por una prueba de igualdad
con 0.3.1/0.4.0, que sigue pasando).

## Método

1. Inventario de 31 módulos runtime y análisis AST propio (sin instalar nada):
   `except` desnudos, `except/pass`, argumentos mutables, `eval`/`exec`,
   `__import__`, `assert` en runtime, llamadas a subprocesos, serialización
   insegura. No se encontraron `eval`/`exec`, `pickle`, `assert` en runtime ni
   argumentos mutables por defecto. Sí hay 15 `except ...: pass`, todos
   revisados: la mayoría son degradaciones intencionales (DPAPI no disponible,
   lectura opcional), y los que podían enmascarar un fallo se corrigieron.
2. Lectura completa de `config`, `routing`, `providers`, `agent`, `autonomy`,
   `project_store`, `materials`, `bibliography`, `copilot_socket`,
   `conversation_state`, `word_bridge`, `native_material`, `secrets_store` y las
   zonas de hilos de `app`/`settings_dialog`.
3. Reproducción de fallos con un caso mínimo antes de tocar el código.
4. Pruebas de regresión nuevas (`tests/test_robustez_v041.py`, 19 casos) y
   actualización de una prueba que fijaba un comportamiento que ahora se
   considera un defecto (bloqueo permanente ante `config.json` dañado).

Resultado: **350 pruebas superadas / 2 omitidas** (antes 331 / 2). Las 2
omitidas siguen siendo las que requieren Windows real.

## Hallazgos corregidos

| # | Gravedad | Falla futura | Corrección |
|---|---|---|---|
| 1 | Alta | `Config.data` se compartía entre el hilo de red (`RoutedAPI`) y el hilo Tk (diálogo de cuentas). `json.dump` sobre el dict mientras otro hilo lo mutaba lanzaba `RuntimeError: dictionary changed size during iteration` (reproducido con 40 000 claves). Se perdía la respuesta del modelo o se corrompía la configuración. | `RLock` reentrante en `Config`, decorador `@locked` en las operaciones públicas, `flush()` serializa una **instantánea** `deepcopy` tomada bajo el lock, y helper `config.edit()` para las escrituras directas desde `routing` y `settings_dialog` (compatible con dobles de prueba). |
| 2 | Alta | Un `config.json` dañado activaba `block_save=True` para siempre: la app arrancaba vacía pero **cualquier** guardado lanzaba `ValueError`. El usuario tenía que borrar el archivo a mano. | Se conserva una copia única `config-invalido-<fecha>.json`, se arranca con valores por defecto y se permite reconfigurar desde la interfaz. El mensaje indica dónde está la copia. Prueba anterior actualizada al nuevo contrato. |
| 3 | Media | Un archivo de esquema 1 con `accounts`/`routes`/`health` a `null` reventaba la migración con `TypeError`. | `Config._normalize()` garantiza los tipos y completa `current` con `DEFAULT` antes de migrar. |
| 4 | Media | `bibliography.add_sources` calculaba `F#` como `max(int(id[1:]))+1`. Un id heredado no numérico tumbaba la búsqueda; borrar la última fuente **reutilizaba su id**, de modo que citas `[F5]` ya escritas pasaban a apuntar a otro documento. | Contador monótono `source_seq` en el proyecto, con parseo tolerante de ids antiguos. Igual para `D#` de materiales (`material_seq`). |
| 5 | Media | `materials.select` indexaba `data['segments']` y `seg['text']` sin validar. Un `extracted.json` dañado o de otra versión abortaba un turno completo con `KeyError`. | Validación de estructura y captura de `OSError/ValueError/KeyError/TypeError/UnicodeError`; se omiten fragmentos inválidos, no el turno. |
| 6 | Media | `project_store.validate` no exigía `run` ni `usage`, que `app.py` y `agent.py` leen con `p['...']`. Un proyecto escrito por una versión anterior podía fallar al cargar. | `validate()` rellena `run`, `usage`, `data_ready`, `profile`, `word_path`, `created/updated` y `materials` solo cuando faltan o son de tipo incorrecto. Los campos centrales siguen rechazándose si son inválidos. |
| 7 | Media | `copilot_socket.complete` comparaba `identity.get('exp',0) < time.time()+30`. Algunos `exp` llegan como cadena (`TypeError`) y otros faltan (`0` → «Sesión caducada» falsa) antes de enviar nada a Microsoft. | `expires_soon()` convierte a número; expiración desconocida **no** se trata como caducada. Una sesión realmente caducada sigue produciendo el error de autenticación del handshake. |
| 8 | Media | En `routing`, el callback `update_secret` indexaba `config.data['accounts'][aid]`; si el usuario borraba la cuenta durante una petición, un `KeyError` descartaba una respuesta ya confirmada. | Se comprueba la existencia de la cuenta y se aísla el guardado; un fallo de bookkeeping nunca invalida la respuesta. |
| 9 | Media | El guardado de `health`/`cooldowns` tras una respuesta exitosa podía lanzar (disco lleno, DPAPI). No estaba protegido y sustituía la respuesta por una excepción; en la rama de error podía reemplazar el `ProviderError` original y cambiar su clasificación. | Ambas escrituras se envuelven en `try/except` sin alterar el resultado ni el `ProviderError`. Detectado por una prueba nueva. |
| 10 | Media | `native_material.read_docx` no comprobaba `returncode` ni la forma del JSON de PowerShell. Un fallo de Word producía `JSONDecodeError`/`KeyError` opacos y, a veces, pérdida de la memoria DPAPI. | Se validan código de salida, JSON, forma de `segments/total/omitted/warnings` y se normalizan valores parciales. |
| 11 | Baja | `bibliography.search` suponía que `message` era un dict; una respuesta de Crossref con forma distinta lanzaba `AttributeError`. | Validación explícita del sobre de respuesta. |
| 12 | Baja | `providers.API.request` (Ollama) indexaba `c['function']` y hacía `json.loads(args)` sin protección. | Validación de forma y parseo tolerante de argumentos de herramientas. |
| 13 | Baja | `secrets_store` pasaba un `POINTER(c_ubyte)` a `LocalFree` (declarado `c_void_p`): en algunos builds de Python eso lanza `ArgumentError` y filtra el buffer DPAPI. | `ctypes.cast(..., c_void_p)` y comprobación de puntero nulo. **Sin verificar en Windows real.** |
| 14 | Baja | Versión inconsistente: la UI mostraba `0.4.0`, `diagnostico.py` decía `0.1.1`, `VERSION.json` y los `.cmd` decían `0.4.1-dev`, y el README del runtime encabezaba `0.4.0`. | Nuevo módulo `version.py` como única fuente; `app`, `verificar_instalacion` y `diagnostico` lo importan. Los `.cmd` no pueden importar Python, así que una prueba comprueba que su literal coincide. |
| 15 | Baja | Faltaba una comprobación previa de la carpeta de datos: si `~/.nexo-tesis` era de solo lectura, todos los guardados fallaban en tiempo de ejecución con errores crípticos. | `verificar_instalacion.check_data_dir()` informa antes de abrir la app, sin leer claves, proyectos ni crear archivos. |
| 16 | Baja | `agent.parse_json` podía intentar un número ilimitado de objetos en una respuesta de 45 000 caracteres. | Límite de 128 candidatos. |

## Refactorizaciones

- `config.edit()` + `Config.guard()` centralizan el contrato de concurrencia en
  un solo sitio; `routing` y `settings_dialog` ya no mutan `data` a ciegas.
- `version.py` elimina cuatro etiquetas de versión divergentes.
- `Config._normalize()` separa la validación de la migración (`_migrate`).
- `bibliography._next_source_id` y `materials._next_material_ref` comparten la
  misma idea de contador monótono tolerante con ids heredados.

## Decisiones deliberadas (no se cambiaron)

- No se añadió ninguna dependencia, descarga en tiempo de ejecución ni intérprete
  portable de Windows. El paquete sigue siendo offline y sin instalación.
- No se relajó la validación académica de `agent.unpack`: sigue rechazando texto
  libre, claves desconocidas y borradores incompletos, y sigue sin hacer una
  llamada de «reparación» tras un formato inválido.
- No se tocaron las funciones protegidas de captura/login de Copilot.
- No se activó la rotación ni el envío incremental por defecto; se mantienen las
  decisiones explícitas del usuario.
- No se implementó un sistema de migración de esquema de proyectos: `validate()`
  solo completa campos opcionales que falten. Cambiar `schema` sigue siendo una
  decisión de versión mayor.

## Riesgos residuales (requieren el equipo del usuario)

Esto **no** se puede cerrar desde este entorno Linux y no debe presentarse como
verificado:

1. Tk real, Word COM, PowerShell 5.1 de Windows y DPAPI. Las pruebas usan dobles;
   `LocalFree`/DPAPI solo se razonó por código.
2. Una sesión autenticada de Microsoft 365 Copilot: recuerdo real del servidor,
   renovación de tokens, cabecera de afinidad y políticas institucionales.
3. Comportamiento de los modelos con respuestas largas o truncadas: el analizador
   tolera envoltorios, pero un JSON incompleto sigue rechazándose por diseño.
4. Rendimiento con proyectos cerca del límite de 3 MB: `validate` serializa el
   proyecto en cada guardado; es intencional para aplicar el límite.
5. Concurrencia entre **dos instancias** de Nexo (el mutex es de ventana, no de
   base de datos). SQLite usa `BEGIN IMMEDIATE` y `busy_timeout=5000`, pero dos
   procesos editando el mismo proyecto pueden chocar con `Conflict`; el mensaje
   ya lo indica.

## Cómo reproducir la validación

```bash
cd nexo-tesis
python3 -m unittest discover -s tests -q      # 350 OK / 2 skipped
python3 -m py_compile *.py
cd .. && python3 tools/verificar_respaldo.py
python3 tools/empaquetar_tesis.py             # reconstruye el ZIP
```

La prueba de aceptación real de continuidad de Copilot sigue siendo la descrita
en `CONTINUIDAD-COPILOT-IMPLEMENTACION.md`. No hacen falta contraseñas, tokens
ni URLs autenticadas para comunicar el resultado.
