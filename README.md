# AulaLista · Producto

AulaLista es una aplicación educativa local para preparar y ofrecer actividades aun sin Internet. Su código de producto, flujos docentes, permisos y publicación editorial viven en este repositorio **privado**. El estado actual es una beta técnica cerrada y previa a piloto: las demostraciones no acreditan validación pedagógica con alumnado real.

## Dónde empezar

- [Glosario canónico](GLOSSARY.md): conceptos del producto y términos que no deben confundirse.
- [Modelo de dominio](docs/domain-model.md): fuente, interpretación, revisión docente y publicación, con contratos y brechas de implementación.
- [Contexto histórico](CONTEXT.md): antecedentes del vocabulario y límites de autoridad que conservan vigencia junto con los ADR.
- [Diseño](DESIGN.md) y [decisiones aceptadas](docs/adr/): flujo docente, snapshots y privacidad.
- [Instalación](docs/installation.md) y [estado de implementación](docs/implementation-current.md).
- Aplicación Django: `aulalista/`, `curriculum/`, `templates/` y `static/`.
- Pruebas de producto: `tests/`.

La persona docente o revisora editorial conserva las decisiones de aprobación, publicación, activación y progreso curricular. La IA solo prepara propuestas revisables.

## Investigación separada

La investigación de algoritmos se presenta en [aulalista-research](https://github.com/eliancanul/aulalista-research): protocolos, harnesses aislados, pruebas sintéticas y bitácoras con corridas congeladas. El harness `shadow_import` y sus pruebas se trasladaron allí. Una variante experimental no se convierte automáticamente en código adoptado por el producto; la adopción requiere una decisión y versión verificable.

`docs/research/` conserva material histórico y de descubrimiento del producto, además de inventarios privados de corpus usados en investigaciones anteriores. Esos archivos no son documentación pública del repositorio de investigación. `scripts/benchmark_issue96_annexes.py` permanece aquí porque ejecuta un recorrido del importador Django; su eventual extracción exige desacoplarlo y sustituir el PDF de prueba por un fixture con permiso claro.

Los issues y PR anteriores mantienen su historial en este repositorio. El trabajo nuevo de investigación debe registrarse en el repositorio de investigación; los cambios del producto se siguen aquí.
