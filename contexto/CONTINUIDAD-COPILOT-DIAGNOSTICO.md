# Continuidad de Copilot: diagnóstico y propuesta de corrección

Fecha: 2026-10-26. Revisado Nexo Tesis 0.4.0. Este informe no es una actualización del programa ni una prueba autenticada con Microsoft.

## Problema confirmado en el código de Nexo

1. `conversation_state.load` devuelve un estado vacío cuando `copilot_continuity` no está activado. La interfaz lo deja desactivado por defecto. `agent.Agent.turn` crea cada operación desde ese estado. `copilot_socket.complete` genera identificadores nuevos si ese estado está vacío. Por tanto, el comportamiento predeterminado reconstruye una conversación para cada turno de Nexo, aunque sus fases internas puedan compartir identificadores.
2. Incluso activándolo, `load` descarta hilos de 40 turnos. Ese umbral es una decisión local del programa, no un límite de Microsoft demostrado en estas pruebas.
3. Los resultados inciertos eliminan el vínculo persistido. La confirmación de contexto actualizado al reanudar también vacía `remote`. Esto puede convertir la recuperación de una operación en el inicio de otro hilo.
4. El identificador de persistencia depende de la generación de credencial. Una reconexión manual que cambie esa generación puede dejar de encontrar el hilo anterior aunque la persona use la misma cuenta. La renovación interna existente no cambia por sí sola ese campo.
5. La ruta actual coloca `XRoutingParameterSessionKey` en la consulta de la URL. La conexión WebSocket no envía la cabecera `X-RoutingParameter-SessionKey`.
6. Copilot recibe las instrucciones y el contexto estructurado cada vez: `providers.API.request` concatena ambas partes como un mensaje de usuario. No existe una estrategia de enviar solo cambios una vez comprobada la continuidad remota.

La primera causa explica directamente el comportamiento comunicado cuando se usa la configuración predeterminada. No puedo confirmar desde este entorno qué opciones estaban activadas en el equipo del usuario.

## Hallazgo externo relevante: una conversación puede bifurcarse

Un trabajo independiente sobre el mismo transporte interno documenta que abrir un WebSocket por turno es compatible con mantener el chat, si se conservan los identificadores de conversación/sesión y se marca correctamente el primer turno. No es necesario equiparar conexión nueva con conversación nueva. [1](https://github.com/cramt/m365-copilot-proxy/blob/main/docs/m365-copilot-api.md)

Una investigación publicada el 5 de octubre de 2026 informa que conservar esos identificadores no bastaba en sus pruebas: las conexiones podían llegar a servidores con estados divergentes. Su corrección envía `X-RoutingParameter-SessionKey: <ConversationId>` como **cabecera** de apertura. Reporta que enviarla como parámetro de URL no conseguía el mismo efecto. También describe contadores de turno que retrocedían como señal del problema. [2](https://github.com/cramt/m365-copilot-proxy/pull/49)

Se revisaron el informe, el diff y el código de sesión de esa referencia de forma estática. No se ejecutó el proyecto externo ni se adoptó su sistema de autenticación. Son observaciones no oficiales de terceros, no una garantía de funcionamiento para la cuenta institucional del usuario. La bifurcación remota es una hipótesis adicional, diferente de la creación local de IDs nuevos, que sí está confirmada en Nexo.

## Diseño recomendado

- **Un chat persistente por proyecto y cuenta Microsoft**, comportamiento normal para Copilot, no una opción experimental que haya que descubrir. No compartir hilos entre proyectos ni cuentas.
- Conservar el vínculo al reiniciar Nexo, entre apartados, correcciones y búsquedas. Quitar la rotación arbitraria de 40 turnos. Mantener los límites de trabajo autónomo: una cosa es limitar tareas y otra romper el chat.
- Separar identidad de la conversación, conexión de transporte e identidad de la cuenta. Una renovación de autenticación no debe cambiar el chat cuando se confirme que sigue siendo la misma cuenta/organización.
- Mantener el login y la captura que funcionan. Probar de forma aislada la cabecera de afinidad descrita por la referencia; no modificar licencias, modelos o permisos para ello.
- Conservar los identificadores y marcar **resultado incierto** cuando no se sepa si llegó una respuesta. No reenviar ni abrir otro chat silenciosamente. Primero comprobar/conciliar el estado; si el protocolo no permite hacerlo, pedir una decisión concreta al usuario.
- Tratar Copilot como una conversación con estado: introducción breve al empezar y mensajes incrementales después de comprobar continuidad. Enviar cambios de datos y documentos, no toda la configuración y el historial repetidamente. Mantener un resumen local de recuperación.
- Mostrar vínculo y estado: chat nuevo, chat retomado, continuidad pendiente de verificar o desajuste detectado. Recoger solo metadatos permitidos, como ID y contador de turno si el servicio los devuelve; no registrar URLs autenticadas, tokens ni cabeceras sensibles.
- Si se pierde continuidad, detener el envío incremental en vez de asumir que el servidor recuerda. Una recuperación contextual o un chat nuevo deben ser explícitos, no un bucle de intentos.
- No usar chats temporales por defecto para esconder el problema. El usuario quiere conservar el historial. Tampoco borrar ni intentar fusionar las conversaciones existentes sin su autorización y sin un método comprobado.
- Revocar un archivo requiere una excepción visible: un hilo remoto ya contiene lo enviado. Nexo debe explicar si necesita un hilo limpio por privacidad; no fingir que revocar borra la memoria de Microsoft.

## Prueba de aceptación real

1. Usar un proyecto de prueba sin datos sensibles y una sola cuenta.
2. Enviar al menos seis mensajes con datos sintéticos distintos, sin volver a incluir los anteriores en cada mensaje.
3. Confirmar que aparece un solo chat en el historial y que se conserva su identificador.
4. Comprobar recuerdo de datos anteriores y evolución de los contadores disponibles. La respuesta del modelo por sí sola no acredita integridad del protocolo.
5. Cerrar y abrir Nexo; continuar en ese mismo chat.
6. Verificar renovación de sesión, interrupción y reanudación sin duplicación ni reinicio oculto.
7. Comprobar que cambiar de proyecto o cuenta sí separa las conversaciones, y que revocar material no reutiliza a escondidas un hilo que todavía contiene ese material.

Las pruebas locales pueden comprobar persistencia, cabeceras y decisiones de recuperación. La continuidad real y el efecto en la lista de chats requieren la sesión del usuario. No se necesitan contraseñas ni exportaciones de tokens para comunicar el resultado de esa comprobación.

## Estado

Diagnóstico e investigación completados. No se modificó el programa ni se publicó una nueva versión durante esta investigación. Activar «Hilo Copilot → Conservar hilo por proyecto y cuenta» en 0.4.0 es una mitigación parcial, no una corrección completa ni una prueba de continuidad remota.
