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
- QA independiente: 12 negativos fallaron antes de reparar whitespace horizontal
  Unicode, abstención ante formatos no resueltos y proyección contradictoria
- QA residual: 2 negativos fallaron antes de conservar tramos literales sin
  asignar con incertidumbre visible y evitar el bypass por comilla sin cerrar
- QA de fronteras ya emparejadas y días: 5 negativos fallaron antes de aplicar
  límites conservadores independientes de comillas, sin crear entidades nuevas
- Aplazamientos: 3 controles de campo fallaron antes de incluir `postponed`; cobertura de la acción
  real de cola en campo general, sesión y anexo, y snapshots de abstención
- Casos authored sintéticos: proyectos y sesiones repetidos/idénticos,
  homónimos, sesión antes de Proyecto, títulos vacíos/multilínea, prosa,
  cambios de contexto y continuación entre páginas, días, fases, citas
  trasladadas, subconjuntos/reordenamiento del dossier, anclas omitidas,
  trasplantadas o manipuladas, SHA ajeno, legacy/nuevo y revisión humana
- C01 versionado se mantiene como regresión de software; no es validación
  pedagógica. Los 20 PDFs históricos no se consultaron ni se publicaron y su
  referencia IA Luna no se considera gold independiente ni holdout
- Sin llamadas a AGY ni modelos externos. No cambia la autoridad editorial,
  la activación de sesiones ni el progreso curricular humano

## Verificación final local

Código y tests congelados y verificados en
`97ff1bd9d40cf62c0ce391caffa107e73625c267`, con Python 3.13.5 y dependencias
instaladas desde `requirements.lock` con hashes:

- `python -m pytest -q`: **1063 passed, 10 skipped**, 538.64 segundos
- `python -m compileall -q aulalista curriculum health scripts tests`: sin errores
- `python manage.py check`: sin incidencias
- `python manage.py makemigrations --check --dry-run`: sin cambios
- `git diff --check 1aae48b HEAD`: sin incidencias
- QA de software independiente: **135 aserciones**, incluidas **70 mutaciones**,
  sin bloqueadores residuales. No son 135 tests pytest ni revisión pedagógica.
  Replay: `final_independent_135.py`, SHA-256
  `21a70d3fb69193da336cbbf8ecd2dae40894b7d01e71ae5ecf93b7eb86652575`.
  El script y sus resultados se conservaron en el paquete técnico de entrega

La edición posterior sólo documenta estos resultados; no cambia código ni tests.
Esto registra verificación local, no publicación ni CI remota.

## Comparación puntual de ocho diagnósticos de desarrollo

Comparación reproducida entre la base `1aae48b` y el código `97ff1bd`:

| Diagnóstico agregado | Antes | Después |
|---|---:|---:|
| Casos con títulos/contextos y cantidad de unidades exactamente esperados | 2/8 | 8/8 |
| Unidades detectadas / esperadas | 16/16 | 16/16 |
| Contextos distintos del esperado | 7 | 0 |
| Momentos que absorbían una etiqueta Proyecto posterior | 7 | 0 |
| Citas trasladadas a otra ocurrencia que obtuvieron `checked` | 1/2 | 0/2 |

Los ocho casos son: dos proyectos en una página, encabezados idénticos, proyecto
vacío que reinicia contexto, sesión anterior al primer proyecto, contexto desde
la página anterior, título multilínea, whitespace horizontal Unicode y tres
números de sesión repetidos. «Exacto» compara títulos esperados y cardinalidad;
la absorción de Proyecto y las citas se cuentan por separado. Estos diagnósticos
fueron authored para desarrollar la corrección: no son holdout, una estimación de
precisión humana, una evaluación pedagógica ni evidencia sobre los 20 PDFs.

## Límites deliberados

- Días y sesiones numeradas son modos a nivel de documento; no se mezclan
- Formatos desconocidos y comillas incompletas pueden forzar abstención y
  conservar tramos literales sin asignar, con página y motivo revisables
- Varios proyectos organizados sólo por fases conservan únicamente la primera
  unidad sintética existente, limitada antes del siguiente Proyecto
- Se trabaja con texto lineal extraído; no se garantiza reconstrucción de
  columnas, tablas, geometría PDF ni cobertura general de documentos
- El contexto sigue propuesto/pendiente; no prueba pertenencia curricular ni
  sustituye decisiones humanas. La comparación semántica legacy de historial
  no gobierna la reaplicación de decisiones, que exige identidad física segura
