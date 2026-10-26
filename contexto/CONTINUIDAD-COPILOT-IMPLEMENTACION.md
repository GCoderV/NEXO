# Continuidad de Copilot: implementación local (0.4.1-dev)

Fecha: 2026-10-26. Continúa `contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md`: el diagnóstico
y la investigación externa ya estaban terminados y **no se rehicieron**. Este documento
describe la corrección aplicada al código de `nexo-tesis/`, qué se pudo comprobar sin red
y qué sigue requiringo la sesión real del usuario.

**No es una nueva versión publicada ni una prueba autenticada con Microsoft.** No se
construyó un paquete de release, no se ejecutó Word COM, DPAPI, PowerShell de Windows
ni inferencia con una cuenta real. No se instaló ni ejecutó el proxy externo de referencia.

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
`VERSION.json`, `tests/test_v040.py` (4 pruebas actualizadas), `test_ui_v040.py`
(guion Tk actualizado) y `tests/test_continuidad_v041.py` (29 pruebas nuevas).

`providers.py` **no se modificó**: el slot `remote` por cuenta ya llegaba a
`copilot_socket.complete` a través de `RoutedAPI`, de modo que la cabecera y el
contador de turnos pudieron añadirse sin tocar el enrutado de proveedores ni la
autenticación. Tampoco se modificaron `nexo-pc/`, los ZIP de `releases/`, el skill REA
ni `nexo-tesis/SHA256SUMS.txt` (manifiesto de la release 0.4.0 ya publicada).

`nexo-tesis/SHA256SUMS.txt` describe el paquete **publicado 0.4.0** y se conserva como
referencia histórica; no se regeneró porque no se construyó una release nueva. El
`SHA256SUMS.txt` de la raíz se regeneró para el árbol de trabajo actual y
`contexto/SHA256SUMS-RESPALDO-0.4.0.txt` conserva el manifiesto prístino del respaldo.

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
