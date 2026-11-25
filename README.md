# AulaLista · Local-First Educational Platform (MVP)

[![Product tests](https://github.com/eliancanul/AulaLista/actions/workflows/product-tests.yml/badge.svg?branch=main)](https://github.com/eliancanul/AulaLista/actions/workflows/product-tests.yml)

**English Overview**

**AulaLista** is an offline-first educational web application built with **Python, Django, and SQLite** designed to help teachers prepare and run classroom activities even in low-connectivity environments.

From an engineering and quality perspective, this repository emphasizes **contract-driven development and automated verification**:
- **80 test modules in `tests/`** using `pytest` and `pytest-django`: 977 test functions, 1,283 collected cases once parametrized. Workflow tests drive the HTTP views through Django's test client against a SQLite test database; the suite covers functional flows, regression safety, database contracts, and UI review gates.
- **Negative cases assert the rejection itself:** the suite checks 400, 403, 404, 405 and 409 responses and raised exceptions, for example `test_publication_without_human_approval_is_rejected` in `tests/test_t03_publication_snapshot.py`.
- **Deterministic AI & NLI Verification (`curriculum/`):** Hybrid lexical (BM25) and Natural Language Inference (NLI) verification running in *shadow mode*. The model sits behind the `NLIAdapter` protocol in `curriculum/tribunal.py`, and tests replace it with a deterministic `FakeAdapter` (`tests/test_t126_tribunal_nli.py`) and check auditable receipts, so AI proposals never auto-publish or mutate curriculum state without human approval.
- **Continuous Integration:** GitHub Actions runs the full suite on every pull request and on pushes to `main` (`.github/workflows/product-tests.yml`). Actions are pinned by commit SHA, the workflow token is read-only, and dependencies install from a hash-locked `requirements.lock`.

### Run the tests

Requires Python 3.13.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python manage.py check
python -m pytest -q tests
```

`python -m pytest -q` with no path also collects the benchmark harness tests under `scripts/benchmark_curriculum/tests`, which is what CI runs on Ubuntu. On macOS four of those fail because the harness sets `RLIMIT_AS`, which macOS rejects; the `tests/` suite is unaffected.

Expected result on a clean clone: 1273 passed, 10 skipped. Nine tests skip because they need source PDFs that are not distributed with the repository, and the real-model NLI smoke test only runs when `AULALISTA_RUN_REAL_NLI_SMOKE=1` is set. More detail in [docs/installation.md](docs/installation.md).

---

## Descripción en Español

AulaLista es una aplicación educativa local para preparar y ofrecer actividades aun sin Internet. El estado de este repositorio corresponde al prototipo técnico / MVP previo a piloto: las demostraciones usan controles deterministas y requieren validación docente explícita.

### Dónde empezar

- [Glosario canónico](GLOSSARY.md): conceptos del producto y términos de dominio.
- [Modelo de dominio](docs/domain-model.md): fuente, interpretación, revisión docente y publicación, con contratos y límites de autoridad.
- [Contexto histórico](CONTEXT.md): antecedentes del vocabulario y límites de autoridad que conservan vigencia junto con los ADR.
- [Diseño](DESIGN.md) y [decisiones aceptadas](docs/adr/): flujo docente, snapshots y privacidad.
- [Instalación](docs/installation.md) y [estado de implementación](docs/implementation-current.md).
- Aplicación Django: `aulalista/`, `curriculum/`, `templates/` y `static/`.
- Suite de pruebas automatizadas: `tests/`.

La persona docente o revisora editorial conserva las decisiones de aprobación, publicación, activación y progreso curricular. La IA solo prepara propuestas revisables bajo contratos verificables.

### Investigación separada

La investigación aislada de algoritmos se presenta en [aulalista-research](https://github.com/eliancanul/aulalista-research): protocolos, harnesses aislados, pruebas sintéticas y bitácoras con corridas reproducibles. Una variante experimental no se convierte automáticamente en código adoptado por el producto; la adopción requiere una decisión y versión verificable.
