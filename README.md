# AulaLista · Local-First Educational Platform (MVP)

**English Overview:**  
**AulaLista** is an offline-first educational web application built with **Python, Django, and SQLite** designed to help teachers prepare and run classroom activities even in low-connectivity environments.  
From an engineering and quality perspective, this repository emphasizes **contract-driven development and automated verification**:
- **70+ automated test modules (`tests/`)** using `pytest` and `pytest-django` covering functional flows, regression safety, database contracts, and UI review gates.
- **Deterministic AI & NLI Verification (`curriculum/`):** Hybrid lexical (BM25) and Natural Language Inference (NLI) verification running in *shadow mode* with deterministic fakes (`FakeNLIReferee`) and auditable receipts—ensuring AI proposals never auto-publish or mutate curriculum state without human approval.
- **Continuous Integration:** Automated test execution via GitHub Actions (`.github/workflows/product-tests.yml`).

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
