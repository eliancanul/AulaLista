# Gate sintético Dirección A→B

Fecha de corte: 2026-09-01. Este documento verifica funcionamiento técnico con datos sintéticos; no mide aprendizaje, adopción ni impacto pedagógico.

| Evidencia/decisión | Prueba reproducible | Resultado |
| --- | --- | --- |
| Dirección coordina salones y adscripciones, no un CRM nominal | `tests/test_t95_school_assignments.py` y `tests/test_t104_institutional_security.py` | Pasa: autoridad de Dirección, aislamiento por School, auditoría y exportación sin identificadores técnicos o estudiantiles. |
| Excel sólo propone; homónimos y conflictos requieren confirmación humana | `tests/test_t103_institutional_import.py` | Pasa: preview sin escritura, School ajena y homónimos detenidos, aplicación atómica e idempotente. |
| El alcance A soporta 0, 1 y N sin colisión | `tests/test_t107_direction_level_a_gate.py` | Pasa: 20 salones/docentes sintéticos con 100% de las filas válidas importadas y sin duplicados. |
| No atribuir historia ambigua a una School o persona | `tests/test_t95_institutional_migration.py` | Pasa: los datos legados quedan explícitamente no recuperables y no reciben autoridad implícita. |

## Dictamen

**Nivel A técnico: aprobado para demo sintética.** El resultado demuestra permisos, importación, auditoría y aislamiento con los fixtures indicados.

**Corte A→B: no aprobado automáticamente.** Nivel B requiere un diccionario de métricas aprobado, una fuente agregada reconciliada y una decisión humana observable. No se autorizan ranking, riesgo, diagnóstico, perfiles nominales ni claims de mejora de aprendizaje. Entrevistas o trabajo de campo futuros requieren consultar primero al tutor, conforme a #107.
