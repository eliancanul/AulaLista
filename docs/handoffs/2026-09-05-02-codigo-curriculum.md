# HANDOFF 02 — Código curriculum + aulalista
Fecha: 2026-09-05 | Rama: updated-tech | Agente: codigo-curriculum

## 1. Mapa módulo → responsabilidad → LOC
- `curriculum/models.py` (1998): 15 modelos + validación Wagtail + máquina `ClassroomSession` prepare/confirm/stop/close + progreso grupal/individual + import staging.
- `curriculum/views.py` (3504): ~35 vistas: join/turn estudiante, consola tutor, agregación/export resultados, pipeline import async con threads, practice, survey.
- `curriculum/roadmap.py` (242): navegación determinista sobre JSON, sin DB ni cache.
- `curriculum/practice.py` (182): `issue/verify_capability`, `evaluate_response` por position, `request_assistance`.
- `curriculum/distribution.py` (89): contrato T06 puro.
- `curriculum/ephemeral.py` (119): cache Django T08.
- `curriculum/survey.py` (41): 1 pregunta rating 1-5, solo promedio grupal.
- `curriculum/curriculum_import.py` (630): pipeline Ollama local, chunk_pages, chat_json, identify/consolidate, propose.
- `aulalista/settings.py` (125): Django+Wagtail, SQLite WAL timeout:5, LocMemCache, LOGIN_URL=/cms/login/.
- `aulalista/urls.py` (229): 30 rutas /student/*, /tutor/*, /cms/, /health/, /access/.
- `curriculum/migrations/` (0001-0029): package → snapshot → session → T06 → turn → T08 → survey → import job → roadmap → groups.

Total: 7159 líneas en 10 .py.

## 2. Lógica frágil
### A. Joins por strings (no FK)
- `views.py:2875-2876` y `2959-2960`: `entry.get("topic_title")==topic["titulo"] and entry.get("subtopic_title")==sub["titulo"]`. Si maestra edita título en form (`_topics_from_post:2643`, `_subtopics_from_post:2668`), proposals huérfanas desaparecen.
- `models.py:469,477`, `views.py:788,1348-1352`: fallback a título snapshot o strings "Unidad/Lección/Actividad". Export `views.py:1865-1867` contamina reportes.
- IDs roadmap strings opacos en JSON: `GroupRoadmapProgress.current_activity_id:672`, `StudentRoadmapProgress.completed_activity_ids:1517`, `PseudonymousResult.activity_id:1687-1692` con sentinel "actividad-0". Cruce roadmap↔resultados es `str==str` en Python (`models.py:721-722,739-753`).

### B. JSON sin schema DB
- `PublishedPackageSnapshot.payload models.py:383`: forma solo impuesta por `_normalize_published_payload:58-87`. Lectores `practice.py:165-175` asumen shape → PracticeContractError runtime.
- `PublishedRoadmapSnapshot.payload models.py:422`: único guard duplicados `save:519-531`. Orden/keys vive en `roadmap.py:14-30`.
- `GroupRoadmapProgress.completed_activity_ids models.py:671`, `StudentRoadmapProgress ... models.py:1517,1522`, `PseudonymousResult.responses models.py:1702,1704,1705`, `CurriculumImportJob.topics/activities models.py:1799,1804,1837,1843`: sin validación clean(), solo saneado manual.
- Cache `ephemeral.py:15-16,53-71`: sin schema; LocMemCache se pierde entre procesos.

### C. Vistas monolíticas
- `_result_aggregate:1371-1585` (~214 líneas): debería ser `services/results.py` testeable sin request.
- `tutor_import_detail:2458-2546` despacha 8 acciones + `_run_import_job_stage_once:2088-2174` con retry SQLite-lock 8 intentos + threads daemon.
- Resolución cursor actual copiada 7x (`3045-3046,3121-3123,3143-3145,3180-3182,3318-3320,3357-3359,3418-3420`).
- `ClassroomSession.close() models.py:1086-1214` (~128 líneas): fan-out N resultados, `objects.get(pk)` en loop N+1 `1125-1127`.

## 3. Modelos actuales vs faltante
Actuales 15: CurriculumPackage, PublishedPackageSnapshot, PublishedRoadmapSnapshot, CurriculumProgress, ClassroomGroup, GroupRoadmapProgress, ClassroomSession (+Confirmation/Closure), DeviceAssignment, StudentTurn, StudentRoadmapProgress, PseudonymousResult, PseudonymousSurveyResponse, CurriculumImportJob + Wagtail ViewSet con scoping created_by.

Falta:
1. Sin Topic/Subtopic/Activity relacionales — jerarquía solo en JSON import unido por strings.
2. Sin FK RoadmapActivity→Snapshot — vínculo es int en payload, resuelto con get/filter runtime.
3. Sin FK PseudonymousResult→Session — join por (batch UUID + snapshot triple) en Python.
4. Sin modelo RoadmapNode — node_id Char(160) libre.
5. `StudentRoadmapProgress.package_snapshot FK` redundante con session.snapshot.

## 4. Code smells archivo:línea
- `views.py:2996` índice posicional POST `job.activities[int(index)]` — reordenar entre render y POST convierte draft equivocado. Ya existe `_activity_id() 2826-2829` no usado.
- `curriculum_import.py:226-237` solo valida required top-level; ACTIVITY_SCHEMA nunca se valida aquí.
- `curriculum_import.py:386-410` consolidate O(n²) + SequenceMatcher 0.7 + substring fusiona "Fracciones" con "Fracciones impropias".
- `views.py:2335-2347` polling sin rate-limit + LocMemCache + WAL = causa reintentos locked `2122-2126`.
- `settings.py:7-8` SECRET_KEY hardcodeada + DEBUG=True, ALLOWED_HOSTS=*, CACHES LocMemCache no-multiproceso.
- `views.py:1648-1651` lógica invertida confusa `if include_unworked and result is not None: continue`.

## 5. Top 3 refactors para otros agentes
1. Extraer `services/results.py` + `services/roadmap_cursor.py` — vistas <30 líneas, tests sin RequestFactory.
2. IDs estables staging (uuid hex8 ya usado para activities) para topics/subtopics, cambiar 2875-2876 y select posicional a IDs. Elimina bugs renombré-y-perdí.
3. `roadmap_store.py::resolve_activity_snapshot()` con in_bulk + clean() centralizado que valide package_snapshot_ids ⊆ existentes.

## 6. Verificar con tests
- Inmutabilidad snapshots save/delete, duplicados, validate_package_snapshots con snapshot inexistente.
- `CurriculumPackage.publish:288-373` — sin auth/no-owner/sin grupo/sin TaskState → ValidationError; feliz crea snapshot version+1 sha256 canónico.
- Sesión prepare/confirm/save guards/stop/close fan-out, borrado turns, limpieza cache.
- Progreso group/individual, resultados contrato JSON, practice/survey/turn, import chunk/identify/consolidate/convert, rutas/auth teacher_required + advance solo activa.
