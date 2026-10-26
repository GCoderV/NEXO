# Continuidad de Copilot: implementación local (0.4.1-dev)

Fecha: 2026-10-26. Continúa `contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md`: el diagnóstico
y la investigación externa ya estaban terminados y **no se rehicieron**. Este documento
describe la corrección aplicada al código de `nexo-tesis/`, qué se pudo comprobar sin red
y qué sigue requiringo la sesión real del usuario.

**No es una nueva versión publicada ni una prueba autenticada con Microsoft.** Se
generó un **paquete Windows de desarrollo** descargable
(`releases/nexo-tesis-v0.4.1-dev-windows.zip`) para poder probar la corrección,
pero no es una release publicada ni verificada. No se ejecutó Word COM, DPAPI,
PowerShell de Windows ni inferencia con una cuenta real. No se instaló ni ejecutó
el proxy externo de referencia.

## Cambios, causa por causa

| # | Hallazgo del diagnóstico | Corrección |
|---|---|---|
| 1 | `load` devuelve vacío si `copilot_continuity` está apagado (por defecto) | Persistencia **por defecto** para rutas `Copilot365`; se eliminó el interruptor experimental. El primer turno crea el vínculo y se guarda. |
| 2 | Hilos de 40 turnos descartados por regla local | Sin rotación. `turns` es metadato. Probado con 40, 41, 4.000 y con seis turnos sobre seis WebSockets distintos. |
| 3 | Errores y reanudaciones descartan los IDs | `save` se ejecuta siempre; un resultado incierto **conserva** los IDs y marca `status=uncertain`. `Agent.turn(resume=True, refresh_context=True)` ya no vacía `remote`. La incertidumbre se registra por cuenta, no globalmente, para no contaminar otra ruta que sí tuvo éxito. |
| 4 | La generación de credencial desvincula el hilo | La clave ahora usa una huella no reversible de `oid`+`tid` de los claims (`identity_fingerprint`), almacenada en la cuenta como `identity`. Renovar la sesión capturada no cambia el chat. Dos entradas de configuración de la misma cuenta Microsoft comparten hilo; otra `oid`/`tid` lo separa. Los hilos 0.4.0 se migran por clave legada en vez de quedar huérfanos. |
| 5 | Falta la cabecera de afinidad | `X-RoutingParameter-SessionKey: <ConversationId>` se envía como **cabecera de apertura** del WebSocket (`opening_headers`), además del parámetro de URL ya existente (que conserva su valor `session`). Aislada tras `copilot_affinity` (activada por defecto) para una comparación A/B sin tocar login/captura/modelos/licencias/permisos. Es evidencia de terceros **no verificada**. |
| 6 | Instrucciones y contexto estructurado repetidos | Con hilo `verified`, sano y **solo** rutas Copilot, se envía un mensaje incremental: contrato breve + cambios desde el último turno. El contexto completo se construye siempre primero (permisos y límites siguen aplicando). Un `ledger` local guarda solo huellas, no texto. Si no hay verificación, hay incertidumbre, se detecta un contador remoto que retrocede, o hay rutas de otro proveedor, se envía el contexto completo. |

Además, alineado con el diseño recomendado:

- **Decisión explícita**: `pending` bloquea cualquier envío cuando el último resultado es
  incierto. «Hilo Copilot» ofrece *conservar el hilo y reenviar contexto completo* o
  *iniciar un hilo limpio*. `Reanudar` abre ese diálogo en lugar de reenviar en silencio.
  No se reenvía ni se abre otro chat automáticamente.
- **Revocación visible**: revocar/retirar un archivo o importar una versión nueva ya no
  borra `copilot_threads` en silencio. `flag_rebind` marca `rebind_required` y explica que
  lo enviado permanece en Microsoft; hace falta una decisión explícita. No se fusionan ni
  borran conversaciones existentes.
- **Estado visible**: el diálogo muestra chat enmascarado, turnos, estado, verificación y
  si un contador remoto disponible retrocedió. Solo se guardan IDs, contadores y estado:
  ni tokens, ni URLs autenticadas, ni cabeceras sensibles, ni cuerpos de mensajes.
- **Contador remoto opcional**: `turn_counter` observa claves numéricas plausibles si el
  servicio las devuelve. Es heurístico y nunca bloquea por sí solo; un retroceso detiene
  el envío incremental y se muestra en la interfaz. Su ausencia es normal.
- **Autenticación intacta**: `launch_desktop`, `launch_auth_window`, `capture_connection`
  y `sanitize_frame` siguen byte a byte como en 0.3.1 (comprobado por la prueba histórica).
  No se automatiza el DOM del chat, no se piden tokens y no se usa el proxy externo.

## Archivos modificados en `nexo-tesis/`

`copilot_socket.py`, `conversation_state.py`, `context_policy.py`, `prompt_policy.py`,
`agent.py`, `config.py`, `routing.py`, `materials.py`, `material_dialog.py`, `app.py`,
`VERSION.json`, `INICIAR-TESIS.cmd`, `LEER-PRIMERO.txt`, `VERIFICAR.cmd`,
`verificar_instalacion.py`, `tests/test_v040.py` (4 pruebas actualizadas),
`test_ui_v040.py` (guion Tk actualizado) y `tests/test_continuidad_v041.py`
(29 pruebas nuevas). Fuera de `nexo-tesis/`: `tools/empaquetar_tesis.py` y las
notas de entrega (`README.md`, `CONTINUAR-EN-ARENA.md`, `AGENTS.md`).

`providers.py` **no se modificó**: el slot `remote` por cuenta ya llegaba a
`copilot_socket.complete` a través de `RoutedAPI`, de modo que la cabecera y el
contador de turnos pudieron añadirse sin tocar el enrutado de proveedores ni la
autenticación. Tampoco se modificaron `nexo-pc/`, los ZIP originales de `releases/`,
el skill REA ni `nexo-tesis/SHA256SUMS.txt` (manifiesto de la release 0.4.0 ya
publicada). A `releases/` solo se **añadió** el paquete de desarrollo nuevo.

`nexo-tesis/SHA256SUMS.txt` describe el paquete **publicado 0.4.0** y se conserva como
referencia histórica; el paquete nuevo lleva su propio `SHA256SUMS.txt` interno. El
`SHA256SUMS.txt` de la raíz se regeneró para el árbol de trabajo actual y
`contexto/SHA256SUMS-RESPALDO-0.4.0.txt` conserva el manifiesto prístino del respaldo.

## Paquete descargable de desarrollo

`releases/nexo-tesis-v0.4.1-dev-windows.zip` (111 archivos, prefijo
`Nexo-Tesis-0.4.1-dev/`; su tamaño y SHA-256 exactos se anotan en el `README.md`
de la raíz, ya que un ZIP no puede contener su propia huella). Se construye sin red con `python3 tools/empaquetar_tesis.py`,
que toma la lista de archivos runtime del paquete 0.4.0 publicado y **no puede** incluir
tests, caches, informes ni credenciales. Incluye únicamente el runtime (módulos Python,
`websocket/`, `pypdf/`, perfiles, scripts PowerShell, lanzadores `.cmd`, licencias),
`README.md` con un aviso de desarrollo al inicio, `VERSION.json`,
`CONTINUIDAD-COPILOT.md` y su `SHA256SUMS.txt` interno.

**Listo para usar:** `LEER-PRIMERO.txt` (inicio rápido en texto plano con CRLF),
`INICIAR-TESIS.cmd` (busca `.venv`, `py -3` o `python`; ejecuta el autochequeo y
solo entonces abre `app.py`) y `VERIFICAR.cmd` / `verificar_instalacion.py` (comprueba
sin red los hashes, los 20 módulos básicos, los 4 de interfaz, Tk y SQLite). El único
requisito externo es Python 3.11+ con Tkinter y SQLite: el paquete no instala ni
modifica nada, y `websocket`/`pypdf` ya van incluidos. No se puede empaquetar un
intérprete de Windows desde este entorno Linux; quien no tenga Python debe instalarlo
desde python.org.

Validación del paquete: hashes internos de 110 archivos comprobados, CRC del ZIP,
sin patrones de credenciales, 97 módulos runtime compilan, **ambas ramas del
autochequeo** ejercitadas (fallo por Tk ausente en Linux y éxito con Tk simulado),
y las **305 pruebas (2 omitidas) pasan ejecutadas contra el paquete extraído**, no
solo contra el árbol de desarrollo. Sigue sin ejecutarse la interfaz Tk real (no hay
Xvfb en este entorno), Word real ni una sesión autenticada de Microsoft.

Para usarlo: descomprimir en una carpeta vacía y hacer doble clic en
`INICIAR-TESIS.cmd`. Probar primero con un proyecto sintético. Los ZIP originales
0.4.0 y 0.3.1 siguen en `releases/` sin modificaciones.

## Comprobación local realizada

```
python3 tools/verificar_respaldo.py          # integridad del respaldo, sin red
cd nexo-tesis && python3 -m unittest discover -s tests -q
# Ran 305 tests — OK (skipped=2)
```

Base anterior: 276 pruebas (2 omitidas). Se añadieron 29 pruebas con fixtures sintéticas
y un emulador de socket local. Cubren: persistencia por defecto, ausencia de rotación,
migración 0.4.0, identidad de cuenta y renovación, incertidumbre por cuenta, decisión
requerida, revocación, cabecera de afinidad (activada/desactivada, valor
`ConversationId`), seis mensajes = un chat, contadores que retroceden, contexto
incremental y reanudación con contexto actualizado.

**No ejecutado aquí**: Tk/Xvfb (no disponible en este entorno), por lo que el guion
`test_ui_v040.py` solo se actualizó y comprobó sintácticamente, no se ejecutó. Las
pruebas nativas con dobles no equivalen a Word real.

## Incidencia del usuario: «al elegir Copilot pide API o credenciales»

Reportada al probar el paquete 0.4.1-dev en Windows. No era un fallo del transporte
de Copilot ni una petición real de clave: era un defecto de la interfaz de
configuración, que trataba a Copilot365 como si fuera un proveedor con API key.

Causas concretas, todas en la configuración (no en `launch_desktop`,
`launch_auth_window`, `capture_connection` ni `sanitize_frame`, que siguen sin
modificarse):

1. `settings_dialog.py` mostraba siempre la etiqueta y el campo «API key» en la
   pestaña Cuentas, también con Copilot365 seleccionado. El aviso que aclaraba
   que no se usa clave era pequeño y fácil de pasar por alto.
2. «Guardar cuenta» con Copilot365 y sin cuenta lanzaba
   `Usa Conectar escritorio M365; no pegues una API key.` En la práctica el botón
   que parecía guardar no servía y el usuario interpretaba que faltaba una clave.
3. «Guardar y usar» desde Modelos y rutas, sin cuenta Copilot365, devolvía
   `Selecciona una cuenta configurada de este proveedor.` Desde la vista del
   usuario era equivalente a «configura credenciales».
4. Editar una cuenta Copilot365 cuya conexión de solo sesión había caducado
   terminaba en `Configura una credencial antes de guardar la cuenta.`

Corrección aplicada:

- El formulario de Cuentas se adapta al proveedor: con Copilot365 se ocultan la
  etiqueta y el campo «API key», el botón pasa a **Conectar / guardar M365** y el
  aviso explica que se usa la sesión propia, sin pegar claves, tokens ni URLs.
- «Guardar cuenta» con Copilot365 reutiliza una conexión legible o inicia
  directamente **Conectar escritorio M365**. Nunca pide una clave escrita.
- «Guardar ruta»/«Guardar y usar» sin conexión Copilot365 ofrece abrir esa
  conexión, en vez de exigir una cuenta con credencial. Si se rechaza, no se
  selecciona ninguna ruta y se explica el motivo.
- Los mensajes de `config.account`, `config.route` y `providers.API` nombran la
  conexión a M365 en lugar de hablar de claves o credenciales.
- `connect_copilot` conserva ahora el estado «Cuenta habilitada» al guardar.

No se añadió ninguna vía para introducir claves de Copilot. La app sigue sin
almacenar contraseñas, tokens pegados por el usuario ni URLs autenticadas; la
conexión se observa de la sesión que el propio usuario inicia. Se añadieron 9
pruebas de regresión con un doble de Tk (este entorno no tiene Tk/Xvfb): el total
local queda en **314 superadas / 2 omitidas**. No sustituyen la ejecución en Tk
real de Windows ni una sesión autenticada de Microsoft.

Pasos para el usuario, también en `LEER-PRIMERO.txt`: Modelos y cuentas →
Cuentas → Nueva cuenta → Proveedor **Copilot365** → nombre → **Conectar
escritorio M365** → autorizar y enviar la frase copiada en un chat nuevo →
volver a Modelos y rutas → **Guardar y usar**. Si no hay app de escritorio de
Copilot, probar el modo «Acceso con Edge». Si no se desea usar la sesión de M365,
elegir un proveedor con API key.

## Lo que aún requiere la sesión del usuario

Sigue vigente la «Prueba de aceptación real» del diagnóstico. En resumen, con un
proyecto de prueba sin datos sensibles y una sola cuenta:

1. Enviar al menos seis mensajes con datos sintéticos distintos, sin repetir los
   anteriores; comprobar que aparece **un solo chat** en el historial y que el ID no cambia.
2. Verificar recuerdo de datos anteriores y la evolución de los contadores disponibles.
   La respuesta del modelo por sí sola no acredita integridad del protocolo.
3. Cerrar y abrir Nexo; continuar en el mismo chat. Probar renovación de sesión,
   interrupción y reanudación sin duplicación ni reinicio oculto.
4. Cambiar de proyecto y de cuenta para confirmar que las conversaciones se separan.
5. Comparar con la cabecera de afinidad activada y desactivada («Hilo Copilot»), sin
   cambiar nada más, y anotar si el comportamiento difiere. Es una hipótesis de terceros.
6. Marcar «Continuidad verificada por mi prueba» solo si el historial real lo confirma;
   eso habilita los mensajes incrementales. Si hay dudas, usar «Conservar el hilo y
   reenviar contexto completo» para volver al modo seguro.

No hacen falta contraseñas, tokens ni exportaciones de URLs autenticadas para comunicar
el resultado. Si la continuidad remota falla, no la ocultes con chats temporales:
documenta el caso y decide con el usuario.
