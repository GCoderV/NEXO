# Agente académico independiente — alcance corregido

## Decisión del usuario

El usuario corrigió la interpretación de la entrega 0.6.0: no quiere un módulo académico dentro de Nexo PC. Quiere un agente independiente para tesis y trabajos académicos, que puede reutilizar componentes de Nexo como base. La investigación de inglés del Centro Educativo Divino Maestro es exclusivamente un caso de prueba, no un proyecto fijo ni la identidad del producto.

Este documento define el alcance corregido. Se implementó Nexo Tesis 0.1.0 como aplicación independiente: conversación, proyectos aislados, memoria, borradores, búsqueda acotada y puente Word experimental. El panel Nexo PC 0.6.0 no satisface este alcance y no es una dependencia. La versión 0.1.0 no cubre aún toda la automatización académica y de formato: el alcance exacto y los pendientes están en LEEME.md.

## Producto

- Aplicación independiente, con nombre provisional Nexo Tesis, lanzador y configuración propios.
- Nexo PC se conserva como producto separado; no se requiere abrirlo para utilizar el agente académico.
- Reutilizar de forma explícita los componentes que resulten apropiados (adaptadores de modelos, conversación, permisos, registro y puente Word), sin depender de una instalación de Nexo PC ni importar sus datos automáticamente.
- Los módulos internos pertenecen al nuevo agente, no a una pestaña añadida al agente generalista.
- Directorio de datos y proyectos separado. No importar claves, sesiones, permisos amplios ni expedientes del agente anterior sin consentimiento.
- Inicio vacío: crear proyecto desde un tema o abrir un proyecto existente. No precargar como investigación activa el caso de inglés.

## Flujo central exigido

1. El usuario introduce un tema o título provisional, aunque aún no tenga los demás datos.
2. El agente identifica lo conocido, lo que puede proponer y lo que no puede inferir con seguridad.
3. Construye una ruta de trabajo y una estructura provisional, sin imponer una metodología o universidad a partir del tema.
4. Hace pocas preguntas, oportunas y relevantes; no exige un formulario extenso antes de empezar ni repite preguntas ya resueltas.
5. Investiga y propone los apartados que puede desarrollar con la información disponible, conforme a los permisos de búsqueda y al presupuesto elegido.
6. Conserva respuestas, decisiones, fuentes, propuestas, borradores y asuntos pendientes dentro del proyecto correcto.
7. Avanza por apartados y revisa consistencia. Cambiar un dato central debe invalidar o marcar para revisión los apartados dependientes, no dejarlos silenciosamente obsoletos.
8. Muestra propuestas y cambios revisables en el documento Word confirmado. La interacción conversacional es el centro; los formularios son auxiliares.

## Preguntas adaptativas

Preguntar solo cuando la respuesta afecte de forma relevante el siguiente paso. Ejemplos: nivel académico, institución/programa y guía, tipo de trabajo, contexto/población, fase de avance y disponibilidad de datos. No todos deben preguntarse a la vez.

Distinguir falta de información bloqueante de falta de información que permite avanzar con una propuesta provisional claramente etiquetada. Las respuestas del usuario se guardan como declaraciones, no como hechos verificados externamente.

## Proyectos y perfiles

- Varios proyectos independientes, cada uno con tema, normas, metodología, fuentes, documentos y memoria propios.
- La información de un proyecto no se transmite al modelo o documento de otro.
- Perfil institucional configurable; UCE/UASD son perfiles iniciales, no restricciones del producto.
- Investigación-acción es una modalidad posible, no un supuesto universal. Diseños cuantitativos, cualitativos, mixtos, documentales u otros requieren rutas y criterios adecuados, con cobertura progresiva y límites explícitos.
- Apoyo a distintos trabajos académicos; el alcance de cada tipo se debe declarar en lugar de fingir que todas sus modalidades ya están implementadas.

## Memoria y planificación

Cada dato debe conservar valor, procedencia, estado (aportado, propuesto, verificado o pendiente), fecha de actualización y dependencias. Las fuentes requieren evidencia de consulta para distinguir metadatos, resumen y texto completo.

Estados mínimos por apartado: pendiente de información, listo para proponer, borrador, revisión del usuario, aprobado para edición, aplicado y pendiente de comprobación. Una respuesta del modelo no convierte por sí sola un apartado en verificado.

El agente debe poder reanudar tras cierre, explicar el siguiente paso y no repetir acciones de efecto desconocido. Debe enviar al modelo contexto acotado y pertinente, conservando la memoria completa local.

## Autonomía y límites

El usuario autorizó continuar desarrollando autónomamente, pero no existe acceso remoto al PC ni autorización para instalaciones ocultas. Las acciones sobre documentos requieren el ámbito y la política de aprobación correspondientes.

Autonomía significa avanzar en investigación, propuestas y tareas autorizadas sin preguntas innecesarias; no significa fabricar datos, citas, intervenciones o autorizaciones. Si faltan resultados empíricos, puede preparar instrumentos, plan de análisis y apartados pendientes, pero no inventar resultados para completar la tesis.

## Word y proveedores

- Trabajo nativo con Word sobre un documento confirmado, no un generador externo DOCX por defecto.
- Reutilizar el puente experimental solo con su estado real: comentarios y selección simulados en Linux, pendiente de validación nativa; edición de texto/formato todavía no implementada.
- Proveedores configurables; integración Ollama disponible como base de transporte cuando se adapte, pero modelo especializado/ajuste queda para después de la base académica.
- No prometer API gratuita ilimitada ni capacidades de búsqueda o formato que todavía no estén implementadas.

## Aceptación prioritaria

1. Arrancar el agente sin abrir ni instalar Nexo PC; directorio de datos separado.
2. Dar solo un tema y obtener un primer plan útil y preguntas relevantes, no el expediente fijo del caso piloto.
3. Contestar una pregunta, reiniciar y continuar sin perder contexto ni repetirla.
4. Crear dos proyectos de temas diferentes y comprobar aislamiento de datos, fuentes y documento destino.
5. Cambiar metodología o contexto y recibir revisión de las propuestas dependientes.
6. Pasar un caso sin datos empíricos: el agente debe avanzar hasta lo justificable sin fabricar resultados.
7. Probar el caso de inglés únicamente como fixture/demostración optativa, fuera del arranque normal.
8. No afirmar búsqueda real, edición Word o calidad académica por superar pruebas con modelos simulados.

## Resultado de la primera implementación

Componentes desacoplados y aplicación independiente implementados. Se probaron dos temas distintos, aislamiento de proyectos, correcciones de datos, preguntas respondidas/aplazadas, llamadas acotadas, rechazo de IDs de fuentes inexistentes y ausencia de resultados sin datos confirmados. Falta validar con un modelo autenticado/inferencia Ollama real y con Word real en Windows. Ampliaciones posteriores: motor APA/CSL, más perfiles, lectura documental y formato Word avanzados; luego especialización del modelo local. No se instaló nada en el PC del usuario.
