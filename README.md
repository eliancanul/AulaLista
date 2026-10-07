# AulaLista · Producto

AulaLista se construye como un SaaS conectado que usa IA para apoyar la validación y preparación curricular, con revisión y aprobación humanas. Su código de producto, flujos docentes, permisos y publicación editorial viven en este repositorio **público**. La implementación actual está en pruebas locales y es previa a piloto: las demostraciones no acreditan validación pedagógica con alumnado real.

## Dónde empezar

- [Contexto y vocabulario](CONTEXT.md): conceptos del producto y límites de autoridad.
- [Diseño](DESIGN.md) y [decisiones aceptadas](docs/adr/): flujo docente, snapshots y privacidad.
- [Instalación](docs/installation.md) y [estado de implementación](docs/implementation-current.md).
- Aplicación Django: `aulalista/`, `curriculum/`, `templates/` y `static/`.
- Pruebas de producto: `tests/`.

La persona docente o revisora editorial conserva las decisiones de aprobación, publicación, activación y progreso curricular. La IA solo prepara propuestas revisables.

## Investigación separada

La investigación de algoritmos se presenta en [aulalista-research](https://github.com/eliancanul/aulalista-research): protocolos, harnesses aislados, pruebas sintéticas y bitácoras con corridas congeladas. El harness `shadow_import` y sus pruebas se trasladaron allí. Una variante experimental no se convierte automáticamente en código adoptado por el producto; la adopción requiere una decisión y versión verificable.

`docs/research/` conserva material histórico y de descubrimiento del producto. Los inventarios privados de corpus y los documentos fuente requieren su propio control de acceso: no deben incluirse en paquetes distribuibles ni compartirse como evidencia pública. `scripts/benchmark_issue96_annexes.py` permanece aquí porque ejecuta un recorrido del importador Django; su eventual extracción exige desacoplarlo y sustituir el PDF de prueba por un fixture con permiso claro.

Los issues y PR anteriores mantienen su historial en este repositorio. El trabajo nuevo de investigación debe registrarse en el repositorio de investigación; los cambios del producto se siguen aquí.

## Revisión docente activa

El recorrido activo usa la shell Django: **Currícula y autoría → Importar
planeación → Revisar planeación**. `/sprint/` redirige a Currícula y autoría.
Véase [el contrato, las comprobaciones y los bloqueos actuales de la revisión
docente](docs/teacher-review.md). La integración experimental Vue + Django +
FastAPI conserva su [documentación técnica](docs/integration-night.md).

Para probar el modelo localmente, la selección de preguntas es GPT-6 Luna
mediante Pi (`pi_luna`), con llamadas
reales deshabilitadas y contexto completo por defecto. La ruta local necesita
configuración, aislamiento revisado y aceptación real separada; véase
[integración local de Pi](docs/pi-luna.md). El guardado y el recorrido Django
tienen aceptación sintética; eso no acredita un piloto con documentos reales.
La conexión API del SaaS se hará después. El perfil OFF de las pruebas no es una
restricción de red de la arquitectura del producto.
