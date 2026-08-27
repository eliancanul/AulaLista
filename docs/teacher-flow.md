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

### Entrada común por LAN

Cuando la sesión está activa, la revisión docente, el control activo y la
proyección pública muestran el mismo enlace
`/student/sessions/<id>/join/`. El enlace se construye con la base explícita de
`AULALISTA_LAN_URL`, por ejemplo `http://192.168.1.20:8000`; el QR local
codifica la URL completa, no un código o etiqueta intermedia. La URL escrita
permanece visible como alternativa en las tres superficies.

Si `AULALISTA_LAN_URL` falta o no es una URL `http(s)` válida, no se inventa
una IP ni se genera un QR potencialmente inutilizable: se muestra el enlace
visible del host de la petición junto con un aviso para configurar la base
LAN. Para una prueba física, el servidor debe escuchar en `0.0.0.0` y el
operador debe verificar la dirección desde la misma red.

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

## Salones, lectura y cierre de año

La maestra puede crear un `ClassroomGroup` con un nombre corto (por ejemplo,
`6° A`) y elegirlo opcionalmente al preparar una sesión. El salón sólo agrupa
sesiones: no contiene lista de alumnos, cuentas ni identificadores de dispositivo.

La vista de resultados empieza con agregados por sesión y por salón. Al abrir una
sesión cerrada, la maestra puede consultar el registro individual seudónimo:
actividades `Completado` o `Interrumpido` agrupadas bajo una etiqueta opaca de
ocho caracteres. Es una señal para mirar más de cerca; no es diagnóstico,
calificación ni identidad. Nunca se muestran apodos ni UUID completos.

Al terminar un año, la maestra confirma explícitamente la acción de cerrar año
para un salón. La acción requiere sesión docente autenticada y POST: elimina los
resultados seudónimos y las valoraciones de estrellas de las sesiones del salón,
pero conserva las sesiones históricas, currícula, snapshots, roadmaps y
`CurriculumProgress` docente. Los estados vacíos comunican que no quedan datos
conservados para ese salón.

La encuesta estudiantil sólo pregunta «¿Te gustó la dinámica?» con 1–5 estrellas.
La maestra ve únicamente el promedio grupal; no hay comentarios libres ni
respuestas por alumno.

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
