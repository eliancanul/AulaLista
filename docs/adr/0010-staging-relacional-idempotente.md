# ADR-0010: Staging relacional idempotente (fusión #53 + #98 + #54)

- **Estado:** Aceptado (diseño; migración pendiente)
- **Fecha:** 2026-09-05
- **Rama:** `updated-tech`
- **Fusiona:** #53 (tablas Topic/Subtopic/ActivityProposal) + #98
  (idempotencia) + #54 (schemas versionados). Hacer uno sin los otros es
  retrabajo: #98 sobre JSON parcha el join que #53 elimina; #53 sin clave
  migra duplicados; #54 sin #53 valida una forma en transición.

## Contexto

- El emparejamiento topic→actividad es por título visible
  (`curriculum/views.py` join `topic_title`/`subtopic_title == titulo`;
  `docs/DATABASE.md` §Deuda-1 lo registra). Causó o agravó #35, #42, #43.
- `curriculum/schemas/` no existía; los contratos vivían solo en
  `tests/test_t24_database_contracts.py`. Paso 1 de este ADR: schemas v1 +
  `curriculum/staging_validation.py` + `CurriculumImportJob.clean()`
  (valida solo payloads no vacíos; `save()` no llama a `clean()` porque el
  pipeline escribe parciales; la revisión humana llama `full_clean()`).
- Reintentos del pipeline pueden duplicar staging (#98, antecedente #47).
  La clave no puede ser el título visible: dos currículas con igual título
  y distinta fuente deben coexistir; el mismo contenido reintentado no debe
  duplicarse; lo ambiguo va a humana, nunca se fusiona en silencio.

## Decisión

1. **Modelo relacional** (migración futura, no en este cambio):
   `Topic(job_fk, titulo, pagina_inicio, pagina_fin, orden)`,
   `Subtopic(topic_fk, titulo, actividades_sugeridas, orden)`,
   `ActivityProposal(subtopic_fk, id_estable hex8, content_hash, is_valid,
   issues_json, proposal_json, selected, added_by_topup)`.
   `CurriculumImportJob` conserva los JSONFields solo como serialización de
   salida durante la transición.
2. **Clave de idempotencia:** `staging_validation.activity_content_hash()` —
   SHA256 canónico de `(topic, subtema, proposal)` normalizados
   (NFKC+casefold+trim); excluye `id/selected/added_by_topup/is_valid/issues`.
   `find_duplicate_groups()` reporta `exact` (mismo hash → deduplicar) y
   `same_title_diff_content` (mismo título visible, distinto hash → AMBIGUO,
   a revisión humana).
3. **Estrategia de migración:** doble escritura → backfill (recalculando
   `content_hash`, reportando ambiguos sin tocar decisiones humanas ni estado
   editorial) → lectura nueva en `_import_action_*`, `_grouped_activities`,
   remove/topup → eliminar JSON de escritura. Prerrequisito #57
   (`scripts/check_migrations.py` + `makemigrations --check` pre-PR;
   antecedente choque 0020 #37 vs #38). Regla #58: ningún cambio de
   modelo/pipeline sin actualizar `docs/DATABASE.md` en el mismo PR.
4. **Contratos que no se tocan:** solo EditorialReviewer humano publica, solo
   maestra activa sesión, IA solo propone; sesiones leen snapshots SHA256
   inmutables; `DemoPackage` sintético sin claims pedagógicos.

## Consecuencias

- Los tests t15/t16/t19/t20/t22/t24 son la red y deben seguir verdes con
  ajustes mínimos; `test_t54_staging_contracts.py` fija v1 + hash + reporte.
- Un cambio de forma que acepte/rechace payloads nuevos crea `schemas/v2/`
  y bump de `SCHEMA_VERSION`, nunca edición silenciosa de v1.
- #55/#56/#65 siguen periféricos; #58 se actualiza con este orden.
