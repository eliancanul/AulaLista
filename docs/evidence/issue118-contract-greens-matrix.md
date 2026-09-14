# Matriz de reconciliación — contrato #118 (structure/procedencia/comprobación)

**Fecha:** 14-sep-2026 · **Rama:** `codex/ui-institucional` · **Baseline:** 718 → **746** passed con UX8
**Estado:** técnico. La aceptación final (GREEN de usuario) corresponde al usuario.

## 1. Estado de los GREENs del contrato (#118)

| # | Criterio (issue #118) | Estado técnico | Evidencia |
|---|----------------------|----------------|-----------|
| 1 | Fixtures 1/2/5 actividades por clase, multi-clase por página, sesión multiespágina, sin semanas, anexos compartidos: orden y relaciones preservadas sin estructura inventada | **Cubierto** | `tests/test_t118_contract_greens.py::TestGreen1FixtureVariety` (7 pruebas) + fixtures C01–C04 existentes en `test_v0_source_interpreter.py` |
| 2 | Solo positivos inequívocos se marcan comprobados; negativos (mismo texto en otra sesión, encabezados repetidos, OCR incompleto, contradicción, resumen inferido) explícitos — nunca cero ni autoaprobados | **Cubierto** | `TestGreen2AdversarialVerification` (6 pruebas) + `test_f7_deriver_conflicting_is_red` y afines en task5 |
| 3 | Un fragmento fuente no confirma automáticamente interpretaciones derivadas (prueba negativa) | **Cubierto** | `TestGreen3DerivedTraceability`: negativo (`proposed` nunca `checked` aunque la fuente esté localizada) + contraste positivo (`extracted`+evidencia→`checked`) |
| 4 | Reproceso/reintento y corrección humana preservan trazabilidad y no duplican entidades (#98) | **Cubierto** | `TestGreen4ReprocessAndCorrection` (3 pruebas) + cadenas resolve A→B→C en task3/source_interpreter |
| 5 | Contadores por alcance sin doble conteo (documento/sesión/cotejos de campo) | **Cubierto** | `TestGreen5CountersByScope` (5 pruebas): aritmética cruzada doc=sum(sesiones)+general, partición de estados, unicidad de item_id, 1 ítem de cola por campo con evidencia múltiple |
| 6 | Sin regresión de permisos, aprobación y snapshots | **Cubierto** | `TestGreen6NoRegression` (5 pruebas: esquema canónico, rechazo de contadores forjados, invariantes `proposed`/anexo, roundtrip) + suites T2–T7 en verde |

## 2. Comprobación de causalidad de las pruebas (auditoría GLM, independiente)

Sonda por mutación sobre copia temporal del repo (`/tmp`, el repo real nunca se tocó):

| Mutación en `curriculum/verification.py` | Efecto observado |
|---|---|
| Guarda `origin in ("proposed","inferred")` (línea 531) desactivada | Falla `test_inferred_summary_stays_needs_review_even_if_text_on_page` |
| Además, fallback de la segunda capa (`STATUS_NEEDS_TEACHER_REVIEW`→`CHECKED`, ~línea 679) | Fallan 3 pruebas: GREEN2, `test_source_located_does_not_confirm_derived_interpretation` y `test_proposed_field_never_auto_approved_by_verifier` |

Conclusión: las pruebas nuevas **no son tautológicas**; el verificador tiene defensa en profundidad (2 capas) y la red de pruebas detecta el debilitamiento de cualquiera de ellas.

## 3. Gates reproducidos de forma independiente (GLM)

| Gate | Resultado |
|---|---|
| Suite completa `pytest -q` | **746 passed** (183.3 s) — `/tmp/aulalista-glm-t8-global.log` |
| `manage.py check` | 0 issues |
| `makemigrations --check --dry-run` | No changes detected |
| `git diff --check` | Limpio |
| Integridad `db.sqlite3` | SHA-256 estable (`e8f71c0a…`) |
| Integridad `media/` | 9 paths, SHAs idénticos a baseline (incluye el PDF C01 del flujo manual) |

## 4. Cambio respecto a HEAD `95d1ab8`

- `tests/test_t118_contract_greens.py` (nuevo, ~1120 líneas, 28 pruebas).
- **Cero cambios de producción**: la implementación existente (`curriculum/verification.py`, `curriculum/source_interpreter.py`) ya satisfacía el contrato; UX8 añadió la cobertura explícita que faltaba.

## 5. Límites y pendientes

- Los GREENs técnicos de este contrato no equivalen a calidad semántica de extracción: eso se evalúa en #119 con gold adjudicado (no_evaluable mientras tanto).
- La calidad de la suite T7 en concurrencia tiene un flaky conocido de SQLite (threads reales) que pasa en aislamiento; registrado sin ocultar.
- No se declara GREEN de usuario. Revisión independiente Luna T8: **READY, sin bloqueadores** (`/tmp/aulalista-luna-ux-import-task8-review.md`) — 12 sondas adversariales independientes (26/26 assertions) y 2 pruebas de causalidad verificadas.
