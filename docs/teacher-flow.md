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

Una corrección de una actividad publicada crea una nueva revisión y, al publicarse, un snapshot nuevo. Una sesión ya iniciada conserva el snapshot inmutable con el que comenzó.

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

## Progreso curricular

`CurriculumProgress` registra únicamente un tema que la persona docente confirma como actual o trabajado. El sistema puede mostrar un siguiente tema sugerido a partir del mapa curricular confirmado y de la actividad previamente trabajada. La sugerencia no es una transición de estado.

Las reglas son:

1. Crear una actividad no cambia `CurriculumProgress`.
2. Publicar una actividad no cambia `CurriculumProgress`.
3. Cerrar una sesión ofrece registrar el tema trabajado, pero nunca avanza `CurriculumProgress` por sí solo.
4. El avance requiere confirmación explícita del maestro.
5. Una nueva versión curricular no reescribe sesiones ya iniciadas.

## Falta de fuente local

Si la propuesta no puede justificarse con fragmentos del currículo confirmado, el sistema debe mostrar exactamente `No hay suficiente fuente local` y dejar la actividad en borrador. No debe completar el hueco inventando contenido ni ocultar la ausencia de fuente.

## Límites de este documento

- No define grado, materia, secuencia ni criterios de aprendizaje concretos.
- No convierte una LLM en autoridad curricular o editorial.
- No afirma validación pedagógica ni sustituye la entrevista y revisión con una docente real.
- No prescribe todavía el modelo de base de datos ni la implementación visual.
