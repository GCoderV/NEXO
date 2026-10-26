# Ratón y conversación por voz — Nexo PC 0.5.0

## Copiar y pegar sin teclado

No requiere instalar componentes adicionales.

- Cada respuesta de Nexo tiene **Copiar** y **Leer**.
- Con clic derecho en el chat: copiar selección, copiar el mensaje completo y seleccionar todo.
- Con clic derecho en el cuadro de escritura: copiar, cortar, pegar y seleccionar todo.
- El botón **Pegar** junto al micrófono también admite texto con varias líneas. Pegar no envía el mensaje.
- Los menús están disponibles también en detalles, revisiones y campos de configuración. El historial permanece protegido contra edición accidental.
- Los atajos Ctrl+C, Ctrl+V, Enter y Shift+Enter siguen disponibles. Los botones explícitos facilitan el uso táctil aunque no se utilice el menú de clic derecho.

## Las tres funciones de voz son diferentes

| Función | Motor | Qué controla Nexo |
|---|---|---|
| **Mic: conversación continua** | Vosk con modelo local de español | Activación, pausa, transcripción, cuenta atrás, envío y cierre del proceso de micrófono. |
| **Leer: texto a voz** | Voces instaladas de Windows mediante sus APIs nativas | Voz elegida, lectura, detención y pausa de la escucha local para reducir el eco. |
| **Dictado Windows** | Panel del sistema abierto con Win+H | Solo el acceso directo y el foco inicial del editor. Windows controla su escucha y cierre. No hay autoenvío en este modo. |

**El modo continuo no utiliza el mismo reconocedor de Win+H.** La documentación de Microsoft exige identidad de paquete para las APIs Windows.Media.SpeechRecognition y documenta restricciones de idioma en dictado continuo de PC. No presentamos un simple atajo de teclado como integración continua de español de México. [8](https://learn.microsoft.com/en-us/windows/apps/develop/input/speech-recognition) [3](https://learn.microsoft.com/en-us/windows/apps/develop/input/enable-continuous-dictation)

Vosk es un componente maduro de reconocimiento local. El modelo incluido es de **español general**, no un modelo certificado específicamente para acento mexicano. Su precisión para tu voz y términos como los de agrimensura debe comprobarse; el paquete pequeño prioriza consumo moderado y no promete la misma precisión de servicios en línea. El catálogo oficial describe los modelos pequeños y sus usos de escritorio. [1](https://alphacephei.com/vosk/models)

## Preparación automática, sin elegir carpetas

El ZIP 0.5.0 incluye el archivo oficial del modelo español, sin modificar. **Copia también la carpeta `models`** al actualizar, conservando `.venv` y `.venv-voz` en la ubicación donde estaban.

1. Abre Nexo y pulsa **Mic**. Busca primero la ruta guardada, la ubicación habitual del instalador y unas pocas ubicaciones conocidas; no explora todo el disco ni otras cuentas de Windows. Reconoce también carpetas padre o doblemente anidadas.
2. Si una preferencia guardada apunta a una carpeta antigua, utiliza automáticamente la copia válida encontrada y guarda la ruta corregida.
3. Si falta el modelo o está incompleto, comprueba el SHA-256 del ZIP incluido y lo prepara localmente en `%USERPROFILE%\.nexo-pc\speech-models\vosk-model-small-es-0.42`. **No descarga nada desde la interfaz ni abre un selector de carpetas.** Una copia incompleta se conserva como respaldo, después de verificar la nueva. Ocupa unos 60 MB extraído.
4. Si Nexo sigue enfocado, solicita consentimiento para activar la conversación; si cambiaste de ventana, pulsa Mic al volver. Durante la preparación, pulsar Mic otra vez cancela la activación posterior, no borra los datos preparados.
5. La lectura usa es-MX de forma predeterminada si hay una voz compatible instalada. No necesitas seleccionar una carpeta para leer ni dictar.

**Si ya instalaste los componentes de audio en 0.4.1, no repitas esa instalación.** Si de verdad faltan Vosk/sounddevice/PyWinRT, cierra Nexo y ejecuta `instalar-VOZ.cmd` una vez. Detecta un Python compatible ya instalado y prepara `.venv-voz`, separado de la interfaz. Las dependencias se obtienen desde PyPI con tu confirmación. Utiliza el modelo incluido; solo el instalador explícito puede descargarlo si falta el ZIP. La interfaz no ejecuta pip automáticamente.

En **Ajustes → Voz → Comprobar / reparar modelo incluido** puedes sustituir una copia dañada por la original sin escoger una carpeta. Se conserva la copia anterior como respaldo. No soluciona permisos, un dispositivo desconectado o una biblioteca ausente; cada etapa informa su error por separado.

Windows conserva el control de sus permisos de micrófono y de la instalación de voces TTS. Si falta una voz es-MX, puedes instalarla desde Windows o elegir otra explícitamente; Nexo no sustituye silenciosamente el idioma ni modifica estos permisos. Se utiliza el dispositivo de entrada predeterminado de Windows.

Los componentes de voz están dirigidos a **Windows 10/11 con CPython estándar 3.11–3.14 de 64 bits, plataforma `win-amd64`**. La interfaz puede continuar con Python 3.15; no se reemplaza ese Python ni se cambian los valores predeterminados. No se elige PyPy ni una compilación sin GIL. Las dependencias de voz son opcionales; copiar/pegar y el resto del agente no las necesitan. El modelo se conserva en `%USERPROFILE%\.nexo-pc\speech-models\vosk-model-small-es-0.42`, fuera de la carpeta del programa, para reutilizarlo en futuras actualizaciones.

Si extraes una actualización en otra carpeta, esa carpeta no tendrá la `.venv-voz` anterior: vuelve a ejecutar el instalador de voz allí. El modelo existente se reutiliza. No copies entornos virtuales entre carpetas: contienen rutas ligadas a su ubicación. Si además necesitas navegador o escritorio en una carpeta nueva, ejecuta `instalar-EXTRAS.cmd`; ese instalador sigue utilizando `.venv`, separado de la voz.

**Corrección 0.4.1:** antes se comprobaba solamente `py -3`, que en tu equipo selecciona 3.15.1 aunque también exista Astral/uv 3.11.16. Ahora se consultan las rutas del lanzador y de uv, se inicia cada candidato con una comprobación aislada y se elige uno compatible. `DIAGNOSTICO-VOZ.cmd` permite ver el resultado sin instalar ni descargar nada (muestra rutas locales, no claves). El instalador no descarga otro Python. Si un entorno de voz anterior está incompleto, pide permiso adicional para conservarlo como respaldo antes de crear otro. No toca `.venv`, perfiles ni sesiones.

Si ya tenías la voz de 0.4.0 instalada en `.venv`, se mantiene ese funcionamiento cuando no exista `.venv-voz`; preparar el nuevo entorno la separa de la interfaz. Un entorno de voz incompleto no se oculta recurriendo silenciosamente a otro Python: se pide repararlo.

## Conversación continua

1. Configura tu proveedor/modelo de chat, carpeta y permisos como siempre.
2. Pulsa **🎙 Mic** junto al cuadro de escritura y acepta el aviso de uso del micrófono y autoenvío.
3. Espera a que indique **Escuchando**.
4. Habla. Los fragmentos reconocidos aparecerán en el editor.
5. Por defecto, espera **3 segundos desde el último fragmento reconocido**, prorrogando la espera mientras llega más dictado, y envía el mensaje una sola vez. La detección de fin de frase del reconocedor añade su propia latencia.
6. Mientras Nexo trabaja o lee, la escucha local se pausa y el dispositivo se libera. Al terminar, vuelve a escuchar sin pulsar Mic otra vez, si el chat sigue activo.
7. Pulsa de nuevo **Mic** para apagar el modo. También detiene la lectura actual y cancela el envío pendiente; conserva el borrador.

Es una conversación **por turnos**, no un canal de interrupción por voz permanente: mientras Nexo habla o trabaja, no procesa lo que digas. Para interrumpir entonces utiliza **■ Voz**, **Mic** o **Detener** con el ratón. Se recomienda usar auriculares; la pausa y el pequeño margen posterior reducen el riesgo de eco, pero no certifican eliminación acústica perfecta.

### Comandos hablados

Se interpretan únicamente como frases independientes y con confianza suficiente:

- **«Nexo enviar»**: envía el borrador sin esperar el temporizador.
- **«Nexo cancelar»**: cancela el envío pendiente y conserva el texto.
- **«Nexo borrar»**: vacía el editor; no borra archivos ni ejecuta herramientas.
- **«Nexo apagar micrófono»** o **«Nexo silenciar»**: apaga el modo local.

No basta con decir «sí» o «aprobar» para autorizar un plan, un comando o un cambio de permisos. Esas revisiones mantienen sus botones. Si quieres menos revisiones durante una tarea, configura la política de Nexo por separado; la voz no altera esa política.

### Ajustes

En Ajustes → Voz puedes:

- Desactivar **Enviar después de una pausa**. El texto queda como borrador hasta usar Enviar o «Nexo enviar».
- Cambiar la espera entre **2 y 10 segundos**.
- Activar/desactivar la lectura automática de respuestas mientras Mic esté activo.
- Comprobar o reparar el modelo incluido automáticamente; ya no hay selector de carpeta.
- Elegir una voz instalada y cambiar su velocidad entre **0.5 y 2**.

Cuando una transcripción tiene baja confianza, se añade al borrador pero **no se envía automáticamente**. Debes revisarla y pulsar Enviar; una frase posterior de alta confianza o «Nexo enviar» no elimina esa revisión. Si el texto supera los 6000 caracteres admitidos por la tarea, se conserva y se apaga el micrófono para que puedas dividirlo.

Editar o pegar manualmente, apagar Mic, cambiar de conversación, abrir otra ventana o perder el foco cancela el envío pendiente. Al volver al chat no se envía silenciosamente un borrador antiguo. Una nueva frase puede añadir contenido a ese borrador y volver a armar un envío: revísalo antes de continuar hablando.

## Lectura con voces de Windows

Puedes pulsar **Leer** en una respuesta, o el botón de altavoz junto al editor para leer la selección del chat o la respuesta más reciente. El mismo botón detiene la reproducción.

La preferencia inicial es **es-MX**. Si no está instalada una voz compatible, se muestra un aviso: no cambia a inglés ni inventa una voz disponible. Puedes escoger una variante distinta de manera explícita. El adaptador usa SpeechSynthesizer y MediaPlayer, a través de PyWinRT, siguiendo la integración nativa documentada por ese proyecto. [1](https://github.com/pywinrt/pywinrt)

- No utiliza SSML ni ejecuta contenido del mensaje.
- Quita marcadores de formato y URLs de la lectura; anuncia los bloques de código como omitidos. El texto copiable no se modifica.
- No lee automáticamente registros de herramientas ni todo el historial al abrirlo: solo la respuesta final de una tarea terminada normalmente, si Mic sigue activo y Nexo tiene el foco.
- Máximo 12 000 caracteres por lectura. Si se supera, pide una selección más corta; no trunca silenciosamente.
- Ante un fallo de lectura, no insiste en cada respuesta: la lectura automática queda pausada hasta detectar voces o volver a activar Mic.

## Acceso al dictado nativo de Windows

**Dictado Windows** coloca el foco en el editor y abre Win+H, sin abrir el teclado táctil completo. Utiliza el idioma de dictado configurado en Windows; puedes mantener español de México.

Es un acceso al panel del sistema, **no** el reconocedor continuo local de Nexo:

- Puede usar procesamiento en línea según la configuración de Windows.
- No envía mensajes automáticamente.
- Nexo no puede consultar con fiabilidad si ese micrófono sigue abierto ni cerrarlo mediante un supuesto toggle ciego.
- Ciérralo y apágalo desde su panel. Después pulsa el botón que muestra **Win+H abierto** para confirmar que lo cerraste.
- Mientras se marque como abierto, Nexo bloquea su lectura en voz alta para evitar que Windows transcriba la respuesta.
- Cerrar Nexo o pulsar su Mic **no apaga el micrófono que controla Windows**. La aplicación avisa de esta separación.

## Privacidad y límites

- El micrófono local siempre empieza **apagado**, aunque se hayan guardado otras preferencias.
- Vosk procesa el audio en un proceso local separado; Nexo no escribe archivos de audio ni envía ese audio a una API de voz.
- **El texto enviado sí entra en la conversación y se transmite al proveedor de chat elegido**, salvo la inferencia local que hayas configurado. El historial sigue guardándose localmente sin cifrar.
- No existe identificación de hablante: puede reconocer a otra persona, una televisión o audio cercano. No dictes claves y evita acceso autónomo amplio en ambientes con otras voces.
- La pausa de escucha impide aceptar resultados atrasados de antes de la pausa. Un proceso que falla no vuelve a activar el micrófono sin tu intervención.
- No se omiten ni se aprueban revisiones de seguridad mediante voz.

## Qué está comprobado

- **36 comprobaciones de interfaz adicionales** con Tk y portapapeles reales: menús, botones, varios turnos, cuenta atrás, cancelación, foco, rechazo de eventos antiguos, pausa de escucha, lectura y selección de idioma. ASR/TTS y el atajo Win+H se simularon: no se grabó ni reprodujo audio.
- La suite automatizada completa define **204 pruebas: 201 correctas y 3 omitidas** en Linux por requerir componentes Windows de pruebas anteriores.
- Se cargó el **modelo real Vosk de español** y se procesaron diez segundos de silencio sintético sin obtener texto. Esto no mide precisión de dictado real.
- Las 28 regresiones de 0.5.0 comprueban, entre otros casos, rutas obsoletas, carpetas anidadas, modelo incompleto, preparación sin red y respaldo de una copia anterior. Hay 16 comprobaciones Tk nuevas de continuidad y preparación de voz.
- Las 29 regresiones de 0.4.1 comprueban selección 3.15/3.11, consentimiento, respaldo, conservación del entorno principal y lanzamiento de los tres procesos con el Python de voz. Son pruebas con fixtures; no una instalación ejecutada en tu PC.
- También se arrancó el reconocedor real desde un entorno virtual separado en Linux, sin Vosk en el Python principal: cargó el modelo y permaneció pausado sin abrir el micrófono (`pruebas-aislamiento-voz.json`). Se comprobó en los metadatos de PyPI que los paquetes fijados publican wheels Windows x64 para 3.11–3.14; no sustituye una instalación nativa.
- En 0.5.0 se extrajo offline el ZIP real incluido, se detectó desde una preferencia obsoleta y se cargó con Vosk real desde un entorno separado: `pruebas-modelo-automatico.json`. No hubo captura de micrófono.
- Se conservaron las **27 comprobaciones base de interfaz** y las **9 de Chromium**.
- **Pendiente en tu PC:** permisos y captura de tu micrófono, precisión con tu español de México, voces instaladas, reproducción nativa, Win+H y funcionamiento completo en Windows.

Puedes ejecutar `PROBAR.cmd` y `PROBAR-INTERFAZ.cmd` sin abrir el micrófono ni usar tus claves. Las pruebas de interfaz sustituyen el portapapeles por texto de prueba: no las ejecutes mientras necesites conservar su contenido. Para la comprobación real, comienza con Planificar y una frase corta; después prueba varios turnos, reproducción y apagado del micrófono antes de habilitar acciones sobre archivos.
