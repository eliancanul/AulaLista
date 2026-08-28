# School owns the institutional scope

Una `School`, no la cuenta de la persona Directora, conserva `ClassroomGroup`, `TeacherAssignment` y auditoría institucional. Dirección recibe autoridad para decidir adscripciones dentro de su ámbito, mientras `PlatformAdministrator` administra cuentas y roles sin heredar esa decisión; así un cambio de Director no mueve, reescribe ni pierde la historia de la Escuela.

## Considered options

- Hacer que cada salón pertenezca directamente al Director: rechazado porque confunde autoridad temporal con propiedad institucional y obliga a trasladar historia cuando cambia la persona.
- Reutilizar autoría (`created_by`) como adscripción docente: rechazado porque crear un registro, impartir en un salón y ser propietaria de currícula son relaciones distintas.

## Consequences

Los permisos y la unicidad se evalúan dentro de `School`. Las adscripciones necesitan vigencia e historia propias; ni Dirección ni administración técnica obtienen por su rol autoridad editorial o acceso a datos nominales de alumnado.
