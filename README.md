# Respaldo Nexo + REA para Arena

Código y contexto para continuar el desarrollo en una sesión limpia.

| Componente | Versión |
|---|---|
| Nexo PC | 0.6.0 (sin cambios) |
| Nexo Tesis | 0.4.0 publicada · árbol de desarrollo 0.4.1-dev |
| REA CLI fijado | 6.7.0 |
| Skill REA, versión de sus metadatos | 42 |

**Empieza por [CONTINUAR-EN-ARENA.md](CONTINUAR-EN-ARENA.md).** Incluye el mensaje que puedes pegar al nuevo agente, restricciones y el estado de Copilot.

> **Continuidad de Copilot (2026-10-26):** la corrección diagnosticada está implementada
> localmente en `nexo-tesis/` y probada sin red (305 pruebas, 2 omitidas), pero **no**
> verificada contra una sesión real de Microsoft ni publicada como release. Detalles,
> límites y prueba de aceptación pendiente en
> [contexto/CONTINUIDAD-COPILOT-IMPLEMENTACION.md](contexto/CONTINUIDAD-COPILOT-IMPLEMENTACION.md).
> El diagnóstico original se conserva sin rehacer en
> [contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md](contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md).
>
> **Descarga (build de desarrollo, no release):**
> [nexo-tesis-v0.4.1-dev-windows.zip](releases/nexo-tesis-v0.4.1-dev-windows.zip)
> (629.073 bytes, 117 archivos, build `agentloop-1`). SHA-256:
> `d4200de4a021b1e9d4fdb934324f8b4e398c801321ce026248588ae514f47094`.
> Página autónoma con el ZIP embebido (sin GitHub ni servidor):
> [descarga/descargar-nexo-tesis.html](descarga/descargar-nexo-tesis.html).
>
> **Correcciones de esta copia:** consultas booleanas largas que antes se
> rechazaban y nunca llegaban a Crossref; botón «Buscar fuentes»; planificador
> que ya no declara «no hay tareas» mientras falten apartados; borradores de
> 20 000 caracteres con recorte visible; Copilot365 sin API key; JSON válido
> envuelto aceptado; auditoría de robustez. Ver
> [AGENTE-LOOP-Y-DOCUMENTO.md](contexto/AGENTE-LOOP-Y-DOCUMENTO.md) y
> [INCIDENCIA-FORMATO-BORRADOR.md](contexto/INCIDENCIA-FORMATO-BORRADOR.md).
>
> **Nuevo:** agente con herramientas en bucle acotado (15 herramientas, 2–12
> pasos, recibo auditable) para inspeccionar el documento, buscar fuentes,
> escribir o **editar solo la parte que falta**, añadir/quitar apartados y
> **generar el documento completo** en Markdown, HTML y DOCX OOXML sin Word,
> sin red y sin dependencias. Ideas funcionales de DoThesis, Loopy,
> agentic-thesis-writing, Academic Writing Toolkit, OpenDraft,
> open-paper-machine, paper-revision-skill y agentic-research (enlaces en el
> informe). 416 pruebas superadas / 2 omitidas. `VERIFICAR.cmd` debe mostrar
> `(agentloop-1)` y tres líneas «OK» para confirmar la copia correcta.
>
> **Listo para usar:** descomprimir en una carpeta vacía y hacer doble clic en
> `INICIAR-TESIS.cmd` (se autoverifica y abre la app). Requiere Python 3.11+ con
> Tkinter; no instala nada. Incluye `LEER-PRIMERO.txt`, `VERIFICAR.cmd`, aviso de
> estado y `CONTINUIDAD-COPILOT.md`. Los ZIP 0.4.0 y 0.3.1
> originales siguen en `releases/` sin cambios.

## Estado de la copia

Este respaldo se preparó el 26 de octubre de 2026. **No está subido a GitHub**: el entorno que lo creó no expuso el conector ni una autenticación Git. No hay una URL de repositorio remoto inventada.

La copia de fuentes conserva los archivos incluidos sin modificarlos. Se omiten caches, entornos, informes generados voluminosos, capturas y documentos personales de referencia de las carpetas fuente. Las exclusiones figuran en `RESPALDO.json`. Los ZIP originales incluidos en `releases/` se conservan byte a byte y pueden contener documentación adicional de las entregas anteriores.

**Usa un repositorio privado.** No se incluyen claves, cookies, sesiones de las apps ni bases de datos. El bot PC conserva el piloto académico incorporado en su código, con institución/centro y diagnóstico agregado. Publicar este respaldo requiere una revisión adicional del contenido académico y de las licencias.

## Comprobar sin instalar nada

```bash
python tools/verificar_respaldo.py
```

El script compara todos los archivos enumerados con `SHA256SUMS.txt`. La verificación de hashes no es una auditoría de seguridad ni una prueba de Windows.

## Subir a GitHub desde un equipo con acceso

Crea un repositorio **privado y vacío**, sin README inicial. En la carpeta descomprimida, usa Git autenticado normalmente. Sustituye `TU_USUARIO` y `TU_REPOSITORIO` por los valores reales:

```bash
git init -b main
git add .
git commit -m "Respaldo Nexo PC, Nexo Tesis y skill REA para Arena"
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

Si Git solicita identidad de autor, configura la tuya localmente en el repositorio. Para autenticación usa el gestor de credenciales o el acceso interactivo de GitHub CLI (`gh auth login`) en tu equipo. **No pegues tokens en el chat ni en la URL remota.** Si ya hay un repositorio con archivos o commits, revisa/integra el contenido: no uses `push --force` ni sobrescribas sin revisar.

Alternativamente puedes subir los archivos descomprimidos desde la web de GitHub, en lotes si supera el límite de archivos. Incluye la carpeta oculta `.agents`; no basta con subir únicamente el ZIP si quieres que el nuevo agente pueda leer el código directamente.

## Abrir en una sesión limpia

Proporciona al nuevo agente la URL del repositorio y el mensaje de `CONTINUAR-EN-ARENA.md`. Si el repositorio es privado, esa sesión necesitará acceso autorizado; este ZIP no transporta autenticación. También puedes adjuntar el ZIP directamente a la nueva sesión sin depender de GitHub.

`tools/restaurar_sesion.py` prepara las rutas históricas de Arena, sin descargas. Por defecto solo muestra el plan; `--aplicar` copia y no sobrescribe archivos diferentes.

## Dependencias que no viajan en Git

- Python/Tk, Microsoft Word, PowerShell de Windows y cuentas de proveedores.
- Entornos de voz/Extras de Nexo PC.
- Modelo Vosk de unos 40 MB: no hace falta para trabajar el código. `python tools/recuperar_modelo_voz.py` muestra URL y huella; `--descargar` autoriza la descarga verificada a `nexo-pc/models/`. El archivo queda ignorado por Git. No instala Python ni bibliotecas.
- Node/REA instalados: `rea-setup/` contiene manifests y locks para restaurar versiones, no `node_modules`. Revisar/aprobar antes de ejecutar `restore.sh`.
- Xvfb/PowerShell Linux usados en las pruebas históricas.

Las instrucciones de los README internos conservan su contexto de entrega original. Nexo PC 0.6.0 era una actualización sobre 0.5.0; sus fuentes actuales están aquí, pero el modelo de voz base se recupera por separado.

## Licencias

Conserva los LICENSE y avisos de cada componente. Nexo tiene su licencia incluida; websocket-client, pypdf y Vosk conservan sus respectivos avisos. El skill REA se conserva junto con la licencia MIT de su repositorio de origen: https://github.com/morluto/rea. El adaptador local no registra automáticamente un conector MCP en Arena.
