# HANDOFF 04 — Tech-debt y Tests
Fecha: 2026-09-05 | Rama: updated-tech | Agente: techdebt-tests. Sin implementación.

## 1. Inventario numerado
- **#58 Épica Deuda estructural** (tech-debt, OPEN): tracker, checklist + regla ningún cambio modelo/pipeline sin ADR, DATABASE.md en mismo PR.
- **#53 Normalizar jerarquía a relacional** (enhancement+tech-debt, OPEN): más grande. Topic(job_fk,titulo,paginas,orden)+Subtopic(topic_fk...)+ActivityProposal(subtopic_fk,id_estable,is_valid,issues_json,proposal_json,selected,added_by_topup). Job conserva JSON solo serialización. Motivo join frágil `subtopic_title==titulo` causa #35,#42,#43. Plan ADR + doble escritura→backfill→lectura nueva + reescribir _import_action_*, _grouped_activities. Red t15/t16/t19/t20/t22/t24.
- **#54 JSON Schemas versionados** (tech-debt, OPEN): elevar `test_t24_database_contracts.py` a `curriculum/schemas/*.json` (topics,activities,llm_log,llm_trace) y validar runtime signal/full_clean, no solo test.
- **#57 Anti-colisión migraciones** (tech-debt, OPEN): script/check pre-PR makemigrations --check, detectar doble número. Antecedente colisión 0020 entre #37 y #38.
- **#55 Streaming asistente residual #34** (enhancement+tech-debt, OPEN): Ollama streaming en espera. Alternativa mínima polling N/total #36 ya cubre.
- **#56 Landing /** (enhancement, NO tech-debt, OPEN): / real rol maestro/alumno + noticias. Hoy / redirige /student/ (#41).
- **#98 Importaciones idempotentes** (bug+tech-debt+ready-for-agent, OPEN): no estaba en #58. Reintento no duplica, dedup por clave+reglas, conservar fuentes/estado/decisiones, ambigüedades reportadas no fusionadas, tests reintento/parcial/dos currículas mismo título. Antecedente #47.
- **#65 Half-Life Regression** (tech-debt, OPEN): solo investigación duolingo/halflife-regression MIT, fuera MVP, no toca scoring determinista.

## 2. Orden #58 y vigencia
Orden literal: #53 (bloqueada por #47 y demo) > #54 > #57 (pequeño, adelantable) > #55 > #56. Relacionados #47 consolidación semántica, #48 UI Wagtail.
¿Válido? Estructuralmente sí (modelo→contratos→tooling→UX), pero incompleto:
- #98 compite mismo código que #53. Hacer #98 sobre JSON es parche sobre join que #53 elimina; hacer #53 sin clave #98 migra duplicados.
- #57 más urgente ahora porque #53+#98 implican migraciones nuevas.
- #55/#56 periféricos correctamente al final.

## 3. Estado tests
- Escala: 41 ficheros test_*.py, 268 funciones def test_ (rg). 42 con helpers.
- Runner pytest.ini solo DJANGO_SETTINGS_MODULE + python_files. requirements.txt solo Django==5.2.9,Wagtail==7.4.3,pypdf==6.1.3,segno==1.6.6 — sin pytest/pytest-django declarado, `python3 -m pytest` falla No module named pytest aquí.
- t24 (4 tests): topics payload TOPIC_KEYS subtemas 1..5 pagina_inicio<=fin; activities ACTIVITY_KEYS PROPOSAL_KEYS inválida⇒selected False; llm_trace TRACE_KEYS ok False⇒errors; worker failure STATUS_FAILED error_message traceback. Conclusión contratos solo-en-test — lo que #54 quiere cerrar.
- t15: staging sin tocar editoriales, chunk_pages, consolidate dedup case-insensitive, chat_json retries, extract/confirm_topics/confirm_subtopics, filtro #33 tipo tema.
- t16 (4 tests): propose mapea ES→EN, generate marca is_valid (micro vacía→inválida), convert_selected crea drafts ai_assisted válidos sin publicaciones, sin selección→STATUS_FAILED.

## 4. Riesgo colisión migraciones
- Confirmado #57 colisión 0020 #37 vs #38.
- Actual 0001..0029 lineal sin duplicados (0001_initial … 0029_progress_finished_at). Riesgo latente no activo.
- Futuro alto si apilan #53+#98 sin #57: ambas tocan Job/staging → repetir 0020. Respetar ADR + DATABASE.md mismo PR.

## 5. Cuello botella real
#53 acoplado con #98. #53 toca corazón (_import_action_*, _grouped_activities, remove/topup) exige ADR+migración datos. #98 único ready-for-agent+bug exige clave idempotencia que ADR #53 debe definir. Atacar uno sin otro = retrabajo. #54 depende que #53 no rompa t24; #57 prerrequisito tooling; #55/#56/#65 independientes.

## 6. Siguiente verificación (sin implementar)
1. `gh issue view 47 --json state,title,body` — ¿sigue OPEN y qué falta consolidación?
2. `ls curriculum/schemas/` + `rg "subtopic_title" curriculum/ tests/` — confirmar #54 pendiente y localizar join frágil #53.
3. `cat docs/DATABASE.md` + `python -m django makemigrations --check` (con env con pytest) — línea base antes de ADR #53/#98 y cierre #57.
