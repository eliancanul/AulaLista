# Base de datos — referencia para agentes y personas

Estado de la verdad sobre el modelo de datos de AulaLista. Si este archivo y
el código discrepan, el código gana: abre un issue. Convención de este repo:
los payloads JSON grandes tienen su forma documentada aquí y están cubiertos
por `tests/test_t24_database_contracts.py`.

## Entidades

| Modelo | Rol | Notas clave |
|---|---|---|
| `CurriculumPackage` | Borrador editable de actividad | `ai_assisted=True` marca origen IA; nunca se auto-publica |
| `PublishedPackageSnapshot` | Versión publicada inmutable | SHA256 identificable; las sesiones congelan esta versión |
| `PublishedRoadmapSnapshot` | Roadmap publicado inmutable | Orden de unidades → lecciones → actividades; cada actividad contiene `package_snapshot_id`; la publicación calcula SHA256 en el modelo |
| `CurriculumProgress` | Confirmación manual docente | Tema actual/trabajado; nunca lo modifica la actividad estudiantil |
| `StudentRoadmapProgress` | Recorrido individual pseudónimo | Actividades completadas y reactivos correctos persistidos por turno; eliminable con los datos temporales |
| `CurriculumImportJob` | Staging del pipeline PDF→actividades | El más complejo; ver máquinas de estado abajo |
| `ClassroomSession` | Ejecución de una sesión de aula | Conserva la maestra que la preparó; las filas históricas sin propietario recuperable llevan una marca de acceso legado de personal. Congela un snapshot base y, si aplica, un roadmap cuyos nodos resuelven todos sus snapshots de paquete |
| `ClassroomGroup` | Etiqueta docente para agrupar sesiones | No tiene roster ni datos de alumnos; una sesión puede no tener salón |
| `DeviceAssignment` | Cupo por dispositivo en una sesión | |
| `StudentTurn` | Turno de participación estudiantil | Genera una `participant_key` UUID aleatoria, sin derivarla de apodo ni dispositivo |
| `PseudonymousResult` | Resultado individual seudónimo | Conserva `participant_key` y actividad, nunca apodo, turno o dispositivo |
| `PseudonymousSurveyResponse` | Valoración de dinámica | Sólo `rating` entero 1–5 y referencias opacas de lote/snapshot; no texto libre ni relación individual |

## Máquinas de estado

### `CurriculumImportJob.status`

```
uploaded ──extract──▶ topics_proposed ──confirm_topics──▶ subtopics_proposed
     ▲                                                          │
     │                                              confirm_subtopics
     │                                                          ▼
   failed ◀─────────────────────────────────────────────── completed
                                                                │
                                              generate_activities / add_missing
                                                                ▼
                                                 activities_proposed ──convert──▶ converted
```

Invariantes:
- `failed` sólo lo produce la etapa `extract`; las demás etapas conservan su
  estado `*_proposed` con el error visible (`error_message`) para no perder
  trabajo parcial.
- Nunca existe `CurriculumPackage` antes de `convert_selected`, y siempre con
  `ai_assisted=True`.

### Ciclo `progress_*` (#32/#36)

`progress_stage ∈ {"", "extract", "subtopics", "activities", "add_missing"}`.

- Al iniciar etapa: `progress_stage=<etapa>`, `done=0`, `total=0..N`,
  `started_at=ahora`.
- Durante: `done` crece con persistencia incremental (cada elemento).
- Al terminar (éxito o fallo): `progress_stage=""`.
- Significado de `total`: `extract`=bloques del PDF, `subtopics`=temas,
  `activities`/`add_missing`=actividades.
- Válvula: si `started_at` tiene >90 min, la vista de espera libera el job.

**Trampa conocida**: el worker `_run_import_job_stage` atrapa TODA excepción
y la guarda en `error_message` + `llm_trace` (con traceback). Al depurar
tests de flujo, afirma siempre `job.error_message == ""` — un fallo silencio
se ve como "no pasó nada".

## Formas de los JSONField

### `topics` (jerarquía confirmada)

```json
[{"titulo": "str ≤200", "pagina_inicio": int, "pagina_fin": int,
  "subtemas": [{"titulo": "str ≤200", "actividades_sugeridas": 1..5}]}]
```

⚠️ Los emparejamientos topic→actividad usan `titulo` como clave de texto
(deuda conocida; ver «Deuda estructural»).

### `activities` (propuestas de staging)

```json
[{"id": "hex8",                          // estable; viejos jobs pueden no tenerlo
  "topic_title": "str", "subtopic_title": "str",
  "is_valid": bool, "issues": ["str"],
  "proposal": {"title": "str", "objective": "str", "micro_lesson": "str",
               "final_explanation": "str",
               "questions": [{"block_type": "reactivo", "value": {...}}]},
  "selected": bool,
  "added_by_topup": true?}]              // sólo en top-ups (#35)
```

### `llm_log` (resumen por llamada) y `llm_trace` (intercambio completo, #34)

`llm_log`: `{stage, pages?|topic?|subtema?, proposed_count?|reactivos?,
candidates?}`. Etapas: `identify_topics`, `consolidate_topics` (#47, con
`candidates`=candidatos entrantes), `propose_subtopics`,
`propose_activities`, `add_missing_activities`.

`llm_trace`: `{stage, model, system, prompt, response_raw, duration_ms,
attempts, errors[], ok}` + entradas sintéticas de fallo de worker con
`traceback`.

## Deuda estructural registrada

1. **Jerarquía en JSON en vez de tablas relacionales**: Topic/Subtopic/
   ActivityProposal como FKs eliminarían los joins por título. Decisión
   consciente para el prototipo; revisar antes de escalar (nuevo ADR).
2. **SQLite single-node**: WAL + timeout finite; concurrencia limitada es
   aceptada para el nodo local (ADR 0004).
3. **Migraciones numeradas a mano**: dos ramas pueden chocar el número
   (ocurrió con 0020). Al abrir rama desde otra rama, renumerar y ajustar
   `dependencies`.

## Retención de resultados por salón (#86)

- Al cerrar una sesión, cada `PseudonymousResult` recibe la `participant_key`
  aleatoria de su `StudentTurn` y una `activity_id` opaca. El turno y su apodo
  se eliminan; no existe FK conservada hacia identidad temporal.
- La encuesta elimina el canal de texto libre. `rating` tiene un constraint de
  base de datos de 1 a 5 y la superficie docente recibe únicamente el promedio
  de las filas del lote o salón.
- La acción docente autenticada de cierre de año por `ClassroomGroup` borra
  `PseudonymousResult` y `PseudonymousSurveyResponse` de sus sesiones. Conserva
  paquetes, snapshots, roadmaps, `CurriculumProgress` y las sesiones históricas.
- La migración 0025 borra las respuestas antiguas de encuesta con texto libre
  antes de sustituir su esquema; no intenta reinterpretar ni conservar ese canal.

## Convenciones para agentes

- Campos nuevos en `CurriculumImportJob`: `editable=False` salvo motivo;
  `makemigrations` + renumerar si la rama viene apilada.
- Tests que disparan etapas LLM: `@override_settings(AULALISTA_IMPORT_ASYNC=
  False)` para modo inline determinista; para probar el hilo real usar
  `pytest.mark.django_db(transaction=True)` (los hilos no ven la transacción
  del test) y mantener el `patch` activo durante el polling — si no, el
  worker llama al Ollama real de la máquina.
- Los fakes de funciones del pipeline deben aceptar `feedback_issues=None`
  (contrato actual de propose_activities*).
- Los prompts viven en `curriculum/prompts/*.md`; editarlos no requiere
  reiniciar el server.
