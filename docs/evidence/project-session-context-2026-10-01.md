# Contexto Proyecto → Sesión, #141

Fecha: 2026-10-01. Base: `main` `1aae48b93c2d83aec80c1248a38c24d5960a3d2a`.

## Problema reproducido

Un fixture sintético con dos Proyectos y dos encabezados `SESIÓN 1` en una página
conservaba IDs distintos, pero asignaba ambos al primer título. El cierre del
primero absorbía el segundo Proyecto. La auditoría buscaba la primera aparición
del número para ambas unidades, admitiendo citas trasladadas. La reextracción
existente reemplazaba decisiones de campo y sólo guardaba historial/selección.

## Cambio acotado

Recorrido compartido por página y ocurrencia, límite en Proyecto o sesión,
anclas de texto versionadas recomputadas por el verificador y contexto de
proyecto propuesto/pendiente. No es una relación curricular certificada. La
metadata no modifica tipos, predicados ni cantidad de claims. Preservación de
decisiones sólo con la misma fuente y ocurrencia probada; cambios de base y
abstenciones quedan explícitos en historial. Contrato en `docs/DATABASE.md`.

## Evidencia y límites

- TDD inicial: 23 fallos y 5 pases antes de implementar los nuevos contratos
- TDD de preservación: 7 fallos antes de añadir la fusión segura
- TDD de días/fases: 3 fallos antes de compartir sus límites físicos
- Casos authored sintéticos: proyectos y sesiones repetidos/idénticos,
  homónimos, sesión antes de Proyecto, títulos vacíos/multilínea, prosa,
  cambios de contexto y continuación entre páginas, días, fases, citas
  trasladadas, subconjuntos/reordenamiento del dossier, anclas omitidas,
  trasplantadas o manipuladas, SHA ajeno, legacy/nuevo y revisión humana
- C01 versionado se mantiene como regresión de software; no es validación
  pedagógica. Los 20 PDFs históricos no se consultaron ni se publicaron y su
  referencia IA Luna no se considera gold independiente ni holdout
- Sin llamadas a AGY ni proveedores externos. No cambia la autoridad editorial,
  la activación de sesiones ni el progreso curricular humano

Resultados finales de suite y checks se registran al cerrar la implementación.
