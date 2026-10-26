# Instrucciones de continuidad

Lee primero CONTINUAR-EN-ARENA.md y contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md.

- Dos bots separados: nexo-pc/ 0.6.0 y nexo-tesis/ 0.4.0. No confundir sus datos/configuraciones.
- La corrección de continuidad Copilot está implementada localmente en `nexo-tesis/` (0.4.1-dev) y probada sin red, pero NO verificada contra una sesión real de Microsoft. No anunciarla como terminada ni presentar las pruebas locales como prueba de recuerdo remoto. Ver `contexto/CONTINUIDAD-COPILOT-IMPLEMENTACION.md`.
- No alterar la autenticación/captura funcional ni adoptar el proxy externo como reemplazo.
- No subir claves, cookies, sesiones, datos personales ni archivos académicos nuevos sin permiso.
- No instalar herramientas al abrir el repositorio. Primero diagnosticar, presentar alcance y obtener aprobación.
- Skill: .agents/skills/reverse-engineer-anything/SKILL.md. Adaptador Arena: rea-arena/AGENTS.md. Tener el skill no equivale a tener un MCP conectado. Para código fuente normal, usar lectura de código en vez de REA.
- Preservar licencias. No afirmar acceso GitHub por existir este respaldo. Verificar conectores/autenticación de la sesión actual.
- Word real y Copilot autenticado no se probaron en el entorno del asistente; distinguir mocks de pruebas reales.
