# ADR-0006: El flujo docente conserva el progreso curricular bajo control humano

- **Estado:** Aceptado
- **Fecha:** 2026-08-26

## Contexto

`TeacherWorkflow` separa seleccionar un tema, preparar un `ActivityDraft`, realizar `ActivityReview`, publicar una actividad y ejecutar una `ClassroomSession`. Una inferencia del sistema no es una decisión curricular: el currículo cargado puede ser ambiguo y una actividad puede carecer de fuente local suficiente.

Además, una sesión publicada debe seguir siendo reproducible aunque cambie el material editorial. `ClassroomSession` debe conservar el `PublishedPackageSnapshot` inmutable con el que comenzó.

## Decisión

`CurriculumProgress` sólo cambia cuando el maestro confirma explícitamente el tema actual o trabajado. Crear una actividad, publicarla o cerrar una `ClassroomSession` nunca lo avanza. Al cerrar, el sistema puede ofrecer registrar el tema trabajado, pero esa oferta no constituye el registro ni la transición.

El sistema puede sugerir un siguiente tema basado en un mapa curricular confirmado y en la actividad trabajada; una sugerencia no es una transición de estado. La autoridad para corregir, aprobar, publicar y confirmar el avance permanece en la persona docente. La asistencia automática puede preparar una propuesta, pero no aprobarla ni presentarla como contenido publicado.

Si no existe suficiente evidencia en fuentes locales confirmadas, `ActivityDraft` conserva exactamente el estado `No hay suficiente fuente local` y permanece como borrador. El sistema no inventa contenido para completar la ausencia.

## Consecuencias

- El estado editorial y el progreso curricular son conceptos distintos y auditables.
- La interfaz debe hacer explícita la confirmación docente del progreso.
- Las sesiones iniciadas no cambian cuando se publica una nueva versión curricular.
- Esta decisión documenta un contrato de autoridad y no afirma validación pedagógica ni prescribe políticas específicas por materia.

## Relación con decisiones previas

Esta decisión conserva la autoridad humana de ADR-0002, la separación de snapshots de ADR-0001 y el papel no crítico de la asistencia automática establecido en ADR-0003. ADR-0005 continúa describiendo privacidad de sesiones activas y no se reutiliza para este contrato.
