# HANDOFF 03 — Investigación / Evidencia / Prototipos
Fecha: 2026-09-05 | Rama: updated-tech | Agente: investigacion-evidencia

## 1. Qué existe y qué valida
- `docs/evidence-demo.md` (T12, 85 líneas): guion reproducible `scripts/run_evidence_demo.py` → `evidence/t12/t12-evidence.json/html` sobre SQLite temporal, DemoPackage sintético, base eliminada. 11 pasos: migrate → EditorialReviewer aprueba → snapshot v1 → sesión fijada v1 → cliente sintético + pista efímera → corrección → v2 → v1 retenido → cierre con pseudónimos → export post-cierre → LAN 192.0.2.10 TEST-NET + QR local cero WAN → T10 30 secuenciales p95. Marca `false` prueba física dos teléfonos + WAN off. Límites: no 30 escritores simultáneos (locked), LocMemCache un proceso.
- `docs/evidence/t12-network.mmd`: flowchart Tutor→Nodo→Phone1/Phone2, WAN desconectada. Solo intención.
- `docs/evidence/t13-common-entry-manual-test.md` (57 líneas): checklist manual T13 enlace/QR único, 2 navegadores, cookies aisladas, WAN off. Registro Fecha/Ejecutada/Resultado vacío — no ejecutado.
- `docs/eval-packs/2026-08-28-p0-results-fix.html` (443 líneas): eval-pack P0 rama codex/p0-reconcile, 300x2 suite, 59 enfocados, 4 capturas base64, 0 assets remotos. Limitations: aceptado local, sin commit/push, sin LAN física, responsive 390px clipping, cero IDs solo resultados.
- `docs/qr-lan-test.md` (31 líneas): protocolo físico QR LAN `AULALISTA_LAN_URL=http://192.168.1.20:8000 scripts/run_wsgi.py`. Spec, no log. Implementado `health/lan.py:9-80`, `health/qr.py:45-95` Segno local, `health/views.py:13-28`.
- `health/templates/health/local_access.html` vs `templates/health/health.html`: soporte QR/LAN.
- `static/health/*` + `static/curriculum/*`: grep http/cdn = 0 hits — valida offline en estas capas.
- `docs/demo-prototipo.md` (107 líneas): guion demo viernes 15-20min MacBook+Ollama qwen2.5:14b. IA solo borradores. Acto1 import PDF, Acto2 revisión snapshot, Acto3 sesión QR + encuesta + cierre. Evidencia prometida `evidence/demo-viernes/*.png` — directorio no existe.

## 2. Prototipos
Tres aislados `prototypes/visual-a|b|c/` cada uno index.html+styles.css+app.js+README+DESIGN+captures:
- A Editorial tranquila: #inicio/#estudiante/#docente/#actividad, DEMO-7K4, QR CSS.
- B Camino unidades→lecciones→actividades: visto/actual/disponible/bloqueado/completada.
- C Aula directa Issue #72: #home/#student/#teacher/#active, QR persistente + conteo límite 20.
Estado: coexisten sin decisión. `demo-prototipo.md:46-48` pedía elegir una antes de tocar producción — sin constancia. `docs/prototypes/` solo tiene visual-c.md. Templates reales `templates/curriculum/` (23 archivos) separados — prototipos declaran no compartir rutas/modelos.

## 3. Prompts LLM `curriculum/prompts/` (6 JSON-only)
- `system.md`: responde exclusivamente JSON válido, no inventes.
- `identify_topics.md`: clasifica tema/actividad/otro con páginas [página N].
- `consolidate_topics.md`: agrupa fragmentos, 1 grupo por índice, ambiguos a humana.
- `propose_subtopics.md`: subtemas orden pedagógico + actividades_sugeridas por densidad.
- `propose_activities.md`: 1 opción única objetivo/microleccion/reactivos[posicion 1.. sin huecos, 1 correcta, retro]/pistas, solo contexto.
- `propose_activities_incremental.md`: +existing_block, NO modifiques/repitas.
Riesgos: guardarraíl solo textual sin enforcement; propose sin citas/trazabilidad; densidad sin rúbrica; incremental prohíbe repetición textual no semántica; sin filtros edad/seguridad; duplican 80% schema.

## 4. Gaps evidencia vs claims
- Pedagogía: `evidence-demo.md:82,85` — validación docente real y estudio posterior en futuro; no afirma impacto, no pilotaje menores.
- Demo sintética técnica, no piloto: fracciones/respuestas/revisor/participantes sintéticos; QR sintético; eval-pack headless sintético.
- Escala: T10/T12 30 secuenciales p95 2000ms, no concurrentes ni multi-worker.
- Física ausente: T12 false, T13 sin llenar, eval-pack sin LAN física, demo-viernes inexistente.
- IP 192.0.2.10 TEST-NET correcto si no se presenta como real.

## 5. Huérfanos/duplicados
1. Doble raíz templates: health/templates vs templates/ — resolución dividida `health/views.py:10,21`.
2. `static/health/font.css` stub solo @font-face local() sin binario.
3. `docs/prototypes/` asimétrico solo visual-c.md; ruta .venv obsoleta /AulaLista-repo/.
4. Ref rota `demo-prototipo.md:106` → evidence/demo-viernes/ inexistente.
5. Prompts duplicados propose_activities vs incremental.
6. Código muerto `health/qr.py:14-42` _reed_solomon_generator docstring admite no usado.
7. Capturas no coinciden nomenclatura acto1-paso3.png pedida.
8. Eval-pack sin fuente/script generador versionado.

## 6. Recomendación limpieza capa
1. Cabecera SINTÉTICO en evidence-demo, demo-prototipo, eval-packs, prototypes README (C ya la tiene).
2. Decidir visual A/B/C, archivar perdedores a prototypes/archive/, crear visual-a/b.md faltantes, corregir ruta .venv.
3. Unificar templates a una raíz, verificar health/views.
4. Ejecutar qr-lan-test + t13 y llenar Fecha/Resultado, o etiquetar PENDIENTE.
5. Crear o borrar evidence/demo-viernes/ — subir pngs o eliminar promesa.
6. Dedup prompts: extraer _activity_schema.md común + exigir citas.
7. Quitar/aislar muerto qr.py, consolidar font.css.
8. Versionar eval-packs: guardar .md fuente + comando/semilla junto a .html.
