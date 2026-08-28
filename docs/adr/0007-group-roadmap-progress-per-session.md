# ADR-0007: El roadmap visible es progreso grupal aislado por sesión

- **Estado:** Aceptado
- **Fecha:** 2026-08-26

`GroupRoadmapProgress` es un registro temporal 1:1 con `ClassroomSession`. Lee
únicamente el `PublishedRoadmapSnapshot` fijado y su lista de snapshots de
paquetes; no consulta `CurriculumProgress` global ni editorial vivo para decidir
la navegación. Completar una actividad válida avanza el cursor de forma
determinista para todos los turnos, incluidos los que entren después.

La maestra autenticada puede adelantar el cursor hacia adelante mediante POST y
CSRF desde el control de esa sesión. El estudiante y la superficie pública no
pueden escribirlo. `StudentRoadmapProgress` continúa registrando resultados
individuales pseudónimos y `CurriculumProgress` conserva exclusivamente la
confirmación curricular humana; ninguno de los dos decide por sí solo el
roadmap grupal. Esta decisión no afirma validación pedagógica.
