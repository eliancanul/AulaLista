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

## Contexto físico de proyecto en `interpretation_dossier` (#141, 2026-10-01)

Contrato aditivo de `SessionPlan`, sin migración SQL ni cambio del staging v1:

- `project_title` sigue siendo una etiqueta de presentación, nunca identidad ni
  prueba de pertenencia. No se rellena con el título general si falta contexto
  local. `session_id` conserva `p{página}_s{número}` y sufijo de ocurrencia para
  números repetidos; seleccionar y corregir siguen operando por ID.
- `header_anchor` es opcional (`null` en dossiers legacy y unidades por fases).
  Su esquema v1 contiene `schema_version`, `kind` (`session` o `day`),
  `document_sha256`, `page_number` físico 1-indexado, `occurrence` 1-indexada
  entre los encabezados de sesión de esa página, `text_start`, `text_end` y
  `excerpt`. Los offsets son caracteres Python sobre el texto extraído por
  pypdf, intervalo `[start,end)`, **no coordenadas ni regiones del PDF**.
- `project_context` también es opcional. Esquema v1: `schema_version`,
  `project_id` (SHA + página + ocurrencia, no título), `title`, `title_status`,
  `origin`, `status`, `review`, `reason` y `anchor`. El ancla usa el mismo
  esquema con `kind=project` y ocurrencia de Proyecto dentro de la página.
  `title_status` distingue título explícito, ambiguo y ausente. La asociación
  por proximidad conserva `origin=proposed`, `review=pending` y
  `status=ambiguous` (o `missing`); no afirma pertenencia curricular.
  Sin encabezado anterior, `project_id`/`anchor` son `null`, el título está
  vacío y el motivo queda visible. Un Proyecto vacío sustituye el contexto
  anterior y corta la sesión; no lo oculta con un fallback global.
- La serialización conserva los valores de estas metadata sin coerción. La
  auditoría exige enteros JSON reales en versión, página, ocurrencia y offsets:
  ni booleanos ni cadenas, incluso numéricas, constituyen anclas válidas.

`source_segments.py` recorre los encabezados en orden físico y comparte límites
entre extracción y verificación. El whitespace horizontal Unicode se reconoce
sin unir líneas en el formato ordinario. Desde #149 se admite además una forma
partida estricta, dentro de una sola página: etiqueta completa de sesión,
exactamente un salto LF/CRLF, entero positivo aislado (admite ceros iniciales),
y otro LF/CRLF seguido inmediatamente de `Inicio`, `Desarrollo` o `Cierre` como
etiqueta independiente o con dos puntos. El ancla conserva el fragmento literal
con su salto y offsets originales; no reescribe la fuente ni une páginas.
Números con títulos/puntuación, listas, fechas, líneas intermedias y separadores
U+2028/U+2029 no habilitan esta forma. Las comillas siguen excluyendo entidades,
sin desactivar los cortes de seguridad. Si recuperar una ocurrencia cambia los
IDs de ocurrencias repetidas, una decisión docente anterior no puede trasladarse
por coincidencia del número: se conserva para revisión cuando su ancla no casa.
Un encabezado numerado de formato desconocido corta el alcance
y deshabilita el fallback de página completa, sin inferir una sesión de la prosa.
Ese límite débil no certifica un cierre completo: conserva el tramo literal sin
asignar y su página en `layout_notes`, visibles en la revisión. Marca la sesión
y sus campos no vacíos como ambiguos/propuestos. La auditoría recomputa también
esa incertidumbre; quitar las notas o cambiar estados no vuelve `checked` ese
alcance. La detección conservadora no depende de comillas, tanto para deshabilitar el
fallback como para limitar sesiones ya emparejadas. Una comilla sin cerrar no
puede ocultar un posible Proyecto, sesión o día. Los días de formato no resuelto
sólo delimitan el modo sin encabezados numerados posibles; no crean unidades.
Los límites débiles conservan siempre el tramo sin asignar y su incertidumbre.
Desde #144, un reinicio sin título también puede proponer un corte: después de
actividad previa deben aparecer, en la misma página y en este orden,
`DATOS GENERALES`, `Campo(s) formativo(s)` con nombres conocidos distintos del
último campo explícito e `INTENCIÓN DIDÁCTICA`. Son etiquetas al inicio de línea,
no menciones sueltas; las señales no pueden cruzar otra actividad o Proyecto.
La repetición del mismo campo (incluido un conjunto con orden/capitalización/
acentos distintos) no corta una tabla. Tampoco bastan una palabra aislada,
prosa, citas balanceadas o un campo vacío/desconocido. Una comilla incompleta
no puede ocultar el reinicio compuesto a la comprobación conservadora. Un
Proyecto explícito nuevo reinicia el estado de actividad anterior: sus datos
generales posteriores no anulan ese título por herencia de una sesión previa.
Esta regla estrecha no
resuelve reinicios con el mismo campo, campos desconocidos, señales repartidas
entre páginas ni formatos de tabla fuera de esas etiquetas; sigue requiriendo
revisión de la fuente y no declara cobertura general de planeaciones.
El corte usa la incertidumbre y las notas literales existentes, sin crear
Proyecto ni sesión. Una sesión explícita posterior no hereda el Proyecto
anterior al reinicio: conserva título vacío, contexto `missing` y motivo,
hasta otro encabezado de Proyecto. Las unidades existentes de revisión por
fases comparten el límite y conservan los tramos sin asignar de las páginas que
el corte excluyó de la unidad anterior: hasta el siguiente Proyecto, fin de
fuente o sus stops previos de Anexos/Productos y evidencias. No se amplía la
unidad ni su superficie de revisión a páginas posteriores a esos stops.
La auditoría vuelve a calcular el corte y su incertidumbre aun si se quitan las
notas/anclas o se cambian los estados. Un reinicio reconocido tampoco habilita
la comprobación legacy de toda la página sin una unidad delimitada.
La unidad por fases se recomputa desde la primera página admitida por el
detector de la fuente; cambiar `pages[0]` o el ID canónico no permite trasladarla
a un bloque posterior. Un ID legacy puede resolver esa misma unidad, sin
habilitar otra a partir de páginas declaradas por el dossier.
No cambian los esquemas, predicados, gates ni la autoridad humana. Las pruebas
de `test_sequence_boundaries_development.py` son texto sintético de desarrollo
derivado del patrón, no un holdout ni una evaluación humana. No se modifican ni
reejecutan los documentos/resultados del piloto ni las métricas del benchmark.
Cada sesión termina ante el siguiente Proyecto,
sesión **o** reinicio reconocido; la continuación heurística sólo puede tomar el prefijo de la página
inmediata siguiente antes de otro encabezado. Los títulos multilínea y vacíos
reutilizan las reglas de `overview_fields.py`; su proyección general conserva
el primer campo del documento. Desde #149, sólo para propósito/finalidad, una
oración terminada en puntuación puede delimitarse antes de una pareja de filas
corroborada: metodología con valor completo reconocido, seguida en la línea
física adyacente por Campo(s), Contenido(s) y PDA/Proceso(s) de desarrollo. No
puede haber prosa entre las pistas. El cuerpo posterior de esa tabla no vuelve
a incorporarse al objetivo. Se preservan los cortes literales y la revisión
pendiente; una captura advertida sigue ambigua. Una sola pista, columnas
incompletas, citas o un objetivo sin cierre conservan el candidato completo
para revisión. Esta heurística de texto no reconstruye tablas geométricamente
ni distingue una transcripción no entrecomillada con exactamente la misma forma.
No se amplía el recorte de títulos ni el esquema del dossier.
Las fases no se convierten en clases: se conserva
la primera unidad sintética de revisión existente y se corta antes de otro
Proyecto o reinicio reconocido; no se generan varias unidades para documentos con varios proyectos
organizados sólo por fases. La detección por días es un modo de documento,
utilizado cuando no hay encabezados numerados posibles; no combina ambos modos.
Formatos no resueltos y comillas incompletas pueden forzar abstención y tramos
sin asignar. No se promete cobertura general de PDFs ni reconstrucción de tablas.

La verificación vuelve a leer la fuente y a calcular las ocurrencias. No confía
en offsets, fragmentos, título, orden del dossier ni subconjuntos declarados.
Anclas/contextos presentes y manipulados, o una proyección `project_title` que
contradice ese contexto, son contradicción mecánica (`blocked`).
La ausencia de metadata legacy no bloquea por sí misma: se resuelve el ID físico
existente o una coincidencia única de número/página. Si hay estructura de sesiones
pero la identidad no es inequívoca, no se usa toda la página como segmento;
las citas trasladadas requieren revisión. Un documento legacy sin encabezados de
sesión conserva la comprobación textual de página, sin afirmar una nueva
pertenencia estructural.

El contexto y su ancla viajan sólo en metadata de la afirmación `es_entidad`.
No se añaden tipos, predicados, claims ni `pertenece_a_proyecto`, y metadata no
entra en el hash del claim. Corregir un valor mal segmentado sí puede cambiar el
ID de ese claim de valor. No se añade `project_context` a campos obligatorios,
ni se alteran tribunal, aprobación, publicación, activación o progreso humano.
La UI expone motivo, incertidumbre, fragmento y enlace a página física sin una
acción nueva de confirmación ni un gate adicional.

### Reextracción y decisiones humanas

El flujo anterior sustituía los valores del dossier y sólo conservaba historial
y selección. Desde #141, antes de guardar se preservan decisiones únicamente
si coinciden SHA y ocurrencia física inequívoca, sin joins por título. Un ancla
completa se contrasta con la fuente; legacy sin ancla exige número/página únicos
y evidencias contenidas en ese segmento. No se trasladan decisiones entre SHA,
anclas cambiadas ni homónimos ambiguos. La decisión que no puede reaplicarse
queda en historial con `decision_not_reapplied`, incluido un snapshot completo
del valor/procedencia anterior aunque el historial legacy estuviera vacío.

La misma base extraída conserva valor, revisión, procedencia y evidencia de la
corrección/confirmación/aplazamiento (`retained_decision`). Si la segmentación cambia, un valor
corregido se conserva como autoría docente pero vuelve a `pending` con motivo;
una confirmación o aplazamiento no se aplica al nuevo valor
(`decision_requires_review`). Los
anexos requieren además la misma referencia, mención, páginas y evidencia.
El historial registra tanto el delta de extracción como la decisión de retener
o abstenerse; las aprobaciones editoriales siguen invalidándose al reextraer.
