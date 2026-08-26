# Flujo docente de AulaLista

Este documento fija el vocabulario y las transiciones que debe respetar la futura interfaz de Wagtail. No define pantallas concretas ni autoriza decisiones pedagógicas que deban validarse con una docente.

## Flujo principal

```text
Currículo cargado
    ↓ seleccionar
Tema seleccionado
    ↓ solicitar propuesta
Actividad propuesta (ActivityDraft)
    ↓ guardar
Borrador editable
    ↓ enviar a revisión
En revisión docente (ActivityReview)
    ├─ corregir ───────────────→ Borrador editable
    ├─ devolver a regeneración → Borrador editable
    └─ aprobar
          ↓ publicar
     Publicada
          ↓ preparar
     Sesión preparada
          ↓ confirmar
     Sesión activa
          ↓ cerrar
     Sesión cerrada
```

Una corrección de una actividad publicada crea una nueva revisión y, al publicarse, un `PublishedPackageSnapshot` nuevo. La maestra publica el camino desde **Avance curricular**, seleccionando y ordenando snapshots de paquetes; cada actividad queda vinculada a su snapshot exacto dentro del `PublishedRoadmapSnapshot`. Al preparar una sesión se fija el roadmap y un snapshot base; una sesión ya iniciada conserva todas las versiones con las que comenzó.

## Estados y autoridad

| Estado | Puede hacer el maestro | No puede hacer el sistema automático |
| --- | --- | --- |
| Currículo cargado | Consultar, seleccionar versión activa, solicitar análisis | Declarar que el PDF representa correctamente toda la planeación |
| Tema seleccionado | Cambiar el tema y confirmar el objetivo de trabajo | Avanzar el curso por inferencia |
| Actividad propuesta | Aceptar, editar o descartar la propuesta | Convertirla en contenido publicado |
| Borrador editable | Editar contenido y fuentes | Presentarlo a estudiantes |
| En revisión docente | Corregir, devolver o aprobar | Aprobar por puntuación o validación estructural |
| Publicada | Preparar una sesión | Modificar el snapshot publicado |
| Sesión preparada | Revisar distribución y confirmar | Hacerla visible sin confirmación humana |
| Sesión activa | Monitorear y cerrar | Cambiar su snapshot |
| Sesión cerrada | Consultar/exportar/eliminar resultados permitidos | Aceptar nuevas respuestas |

## Dos progresos que no se colapsan

`CurriculumProgress` es el avance curricular que la maestra confirma manualmente desde la pantalla **Avance curricular** (`/tutor/roadmaps/`). Registra que una unidad, lección o tema está `ACTUAL` o `TRABAJADO`; no implica dominio. El sistema puede sugerir un siguiente tema, pero la sugerencia no es una transición de estado.

La sugerencia no es una transición de estado.

`StudentRoadmapProgress` es distinto: un recorrido individual, temporal y pseudónimo. Marca actividades `COMPLETADA` cuando las reglas deterministas se satisfacen y calcula la siguiente actividad `ACTUAL` o `DISPONIBLE`. Completar una actividad no aprueba el currículo, no califica y no cambia `CurriculumProgress`.

Las reglas son:

1. Crear una actividad no cambia `CurriculumProgress`.
2. Publicar una actividad no cambia `CurriculumProgress`.
3. Cerrar una sesión ofrece registrar el tema trabajado, pero nunca avanza `CurriculumProgress` por sí solo.
4. El avance docente requiere confirmación explícita del maestro; ningún estudiante puede editarlo o falsificarlo.
5. El recorrido individual no requiere cuenta ni identidad real. Su relación con el turno temporal se elimina al cerrar la sesión.
6. El algoritmo de `StudentRoadmapProgress` sólo lee el `PublishedRoadmapSnapshot` fijado a la sesión y el `PublishedPackageSnapshot` referenciado por cada actividad. Es determinista y no lee la actividad editorial viva. La corrección de respuestas y la compleción se persisten al responder; la caché de 12 horas sólo sirve para superficies efímeras.
7. Una corrección publicada después del inicio no reescribe ninguno de los snapshots de una sesión ya iniciada.

### Estados legibles del recorrido

La pantalla estudiantil siempre escribe el estado, además de cualquier color o símbolo:

- `ACTUAL`: el paso que corresponde continuar ahora.
- `DISPONIBLE`: el siguiente paso habilitado después del actual.
- `COMPLETADA`: actividad terminada en este recorrido, sin declarar aprendizaje.
- `BLOQUEADA`: paso posterior que todavía espera el orden determinista.

La interfaz docente conserva también la confirmación manual como `ACTUAL` o `TRABAJADO`; nunca sustituye esos estados por un cálculo estudiantil.

## Falta de fuente local

Si la propuesta no puede justificarse con fragmentos del currículo confirmado, el sistema debe mostrar exactamente `No hay suficiente fuente local` y dejar la actividad en borrador. No debe completar el hueco inventando contenido ni ocultar la ausencia de fuente.

## Límites de este documento

- No define grado, materia, secuencia ni criterios de aprendizaje concretos.
- No convierte una LLM en autoridad curricular o editorial.
- No afirma validación pedagógica ni sustituye la entrevista y revisión con una docente real.
- No prescribe todavía el modelo de base de datos ni la implementación visual.
