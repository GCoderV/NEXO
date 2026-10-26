# REA para Arena

**Integración local funcional · REA 6.7.0 · Node.js 24.22.1**

Puedes pedirme un análisis en el chat: yo preparo la entrada, ejecuto REA mediante la terminal y te entrego un informe con la evidencia. No necesitas manejar comandos.

## Cómo usarla conmigo

Sube los archivos de una aplicación que tengas autorización para analizar y dime qué quieres averiguar. Por ejemplo:

> «Analiza esta aplicación Electron y explícame cómo funciona su búsqueda».

> «Revisa este paquete JavaScript e identifica sus importaciones y puntos de entrada».

> «Muéstrame qué puedes confirmar y qué sigue siendo incierto».

No tengo acceso directo a las aplicaciones de tu computadora. Debes subir los archivos o indicar una ruta existente en este espacio de trabajo. Para estudiar un repositorio de código fuente normal no hace falta REA; usaré herramientas de lectura de código.

## Qué hace esta primera versión

- Comprueba la versión de REA y los requisitos básicos de JavaScript.
- Restaura las dependencias fijadas si faltan tras un reinicio del entorno.
- Analiza carpetas JavaScript/Electron y admite ASAR a través de REA.
- Guarda un informe Markdown, la evidencia JSON completa, el diagnóstico y los datos de cada ejecución.
- Limita el tiempo y el volumen de salida del proceso, y registra errores sin presentarlos como éxitos.
- Conserva ejecuciones separadas para no sobrescribir resultados anteriores.

No ejecuta deliberadamente el código de la aplicación objetivo ni instala motores nativos. Es un adaptador local; no modifica REA ni publica cambios en GitHub.

## Verificación realizada

| Prueba | Resultado |
|---|---|
| Pruebas unitarias del adaptador | **11 de 11 correctas** |
| Restauración real desde los archivos de dependencias | **Correcta** |
| Análisis de carpeta JavaScript | **Correcto**: 2 archivos JavaScript, 3 archivos relevantes, 0 errores de parseo |
| Generación de informe y evidencia | **Correcta** |
| Rechazo de una entrada incompatible con .NET | **Correcto**, guardado como error |
| ASAR | Admitido por REA; pendiente de prueba propia |
| Ensamblado .NET válido | Pendiente; modo experimental |

La demostración contiene una excepción intencional en el código y está destinada únicamente a inspección estática. REA devolvió evidencia de análisis sin ejecutar la aplicación.

Se probó también una ruta genérica de inspección de artefactos; no aceptó la carpeta de ejemplo. Ese modo **no se incluyó** en la versión final para evitar prometer compatibilidad no comprobada. Sus diagnósticos de desarrollo se conservan en `reports/`.

## Límites importantes

- **No es una conexión MCP nativa a Arena.** Yo la utilizo mediante comandos de terminal.
- La versión inicial no hace descompilación nativa con Ghidra, Hopper o IDA.
- Las relaciones estáticas no prueban qué sucede al ejecutar una aplicación.
- No extrae ZIP automáticamente ni navega por sitios web.
- Los límites de proceso no constituyen una sandbox adicional ni garantizan que un archivo sea seguro.
- Las dependencias instaladas pueden desaparecer al restaurar el entorno. Los scripts y archivos de versiones permiten reinstalarlas con acceso a npm.

## Archivos principales

| Archivo | Función |
|---|---|
| `rea_arena.py` | Adaptador de terminal, sin dependencias Python externas |
| `AGENTS.md` | Procedimiento para que el agente use la integración |
| `test_adapter.py` | Pruebas unitarias |
| `tests.log` | Resultado de las pruebas |
| `smoke-test.json` | Ruta y resultado del último análisis funcional |
| `restore-verification.json` | Comprobación posterior a la restauración |
| `negative-test.json` | Rechazo verificado de una entrada incompatible |
| `examples/demo/` | Ejemplo inerte para inspección |
| `reports/` | Informes, evidencias y diagnósticos por ejecución |

La instalación base y sus archivos de versiones están en `/home/user/rea-setup/`.

## Comandos de referencia

No necesitas ejecutarlos; quedan documentados para reutilizar la integración.

```bash
# Comprobar disponibilidad sin instalar
python /home/user/rea-arena/rea_arena.py status

# Analizar una carpeta; restaura dependencias si están ausentes
python /home/user/rea-arena/rea_arena.py analyze /home/user/rea-arena/examples/demo

# Analizar sin permitir descargas para restauración
python /home/user/rea-arena/rea_arena.py analyze /ruta/a/la/aplicacion --no-restore

# Ver análisis anteriores
python /home/user/rea-arena/rea_arena.py reports

# Restaurar explícitamente las versiones fijadas
python /home/user/rea-arena/rea_arena.py restore

# Repetir las pruebas unitarias
cd /home/user/rea-arena && python -m unittest -v test_adapter
```

Cada informe identifica las limitaciones declaradas por REA y la ubicación de la evidencia original. Para preguntas específicas, leeré esa evidencia y añadiré la explicación correspondiente, diferenciando hechos e inferencias.
