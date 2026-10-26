# Puerta de aceptación nativa — pendiente

**Resultado actual: NO EJECUTADA.** Word real no está disponible en el entorno de desarrollo. Las pruebas automatizadas simulan su transporte.

La prueba siguiente se hará solo en una copia local creada/guardada desde Word, sin datos personales. No debe realizarse sobre el único ejemplar de la tesis.

1. Crear dos documentos de prueba en Word y guardarlos como DOCX. En uno, incluir tres párrafos, una tabla, un campo de índice o referencia y un comentario/revisión previo si se desea comprobar conservación.
2. Abrir Nexo 0.6.0 → Tesis → Word. Buscar abiertos; comprobar que solo aparecen rutas/nombres, no contenido.
3. Elegir el primer archivo, seleccionar un párrafo en él y aprobar lectura. Debe aparecer exactamente ese texto, no el documento completo.
4. Rechazar un comentario propuesto. Comprobar que Word no cambió.
5. Leer de nuevo y editar el párrafo en Word antes de aprobar un comentario. Debe bloquearse por conflicto. No insistir en reintentar sin nueva lectura.
6. Leer de nuevo y activar el otro documento antes de aprobar. Debe bloquearse por documento distinto.
7. Leer de nuevo el primer documento y aprobar un comentario. Comprobar el comentario, su alcance y que el texto original, tabla, campos y revisiones previas permanecen. Nexo no debe aceptar revisiones ni modificar propiedades de autor.
8. Intentar añadir otro comentario sin releer. Debe exigir una selección nueva.
9. Eliminar el comentario desde Word. Comprobar la recuperación del estado previo en la copia. Nexo no incluye un deshacer general ni restaura revisiones por su cuenta.
10. Guardar o descartar desde Word según se prefiera. Si AutoSave está activo, puede haber guardado antes; usar copia local protege el original.

Registrar: versión/compilación de Word, Windows, versión de Nexo, pasos aprobados, errores exactos y si quedaron efectos parciales. No incluir textos o datos de estudiantes.

Si aparece un error de COM, un tiempo de espera o una política de organización: no cambiar seguridad de Office ni ejecutar como administrador a ciegas; detener y diagnosticar. La aplicación no da por exitosa una operación solo porque se inició el proceso de PowerShell.
