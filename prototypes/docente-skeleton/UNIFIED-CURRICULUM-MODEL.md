# Modelo de mapa curricular unificado (propuesta para prototipo)

> Documento de decisión provisional. No modifica el dominio ni la aplicación de producción.

## La idea en una frase

El mapa curricular no debe guardar todo como si fuera el mismo tipo de dato. Debe **unir por referencias** tres capas que conservan autoridades distintas:

1. **Referencia SEP**: fase, campo formativo, contenido y PDA. Es versionada y no se edita desde AulaLista.
2. **Planeación local**: contextualización del programa analítico y ejes articuladores elegidos por personas autorizadas.
3. **Trabajo en aula**: actividades publicadas, sesiones y avance confirmado por la docente.

## Modelo mental

```text
Catálogo SEP (versión y fuente)
└── Fase 3, 4 o 5
    └── Campo formativo
        └── Contenido nacional
            └── PDA
                │ referencia
                ▼
Programa analítico de la escuela / ciclo
└── Contextualización local
    └── Ejes articuladores (varios)
        │ referencia
        ▼
Mapa curricular docente / ciclo
└── Tema planeado
    ├── Actividades publicadas
    └── CurriculumProgress confirmado por la docente
        │ snapshot al preparar
        ▼
ClassroomSession
```

La jerarquía oficial sirve para encontrar y justificar el contenido. La docente opera principalmente en el mapa del ciclo y en sus actividades; no debe recorrer una taxonomía completa cada vez que prepara una sesión.

## Modelo de código sencillo

Estos nombres son deliberadamente conceptuales; no son una migración propuesta todavía.

```python
@dataclass(frozen=True)
class SepReference:
    source_version: str
    phase: int
    field: str
    content_id: str
    content_text: str
    pda: tuple[str, ...]

@dataclass
class AnalyticPlanItem:
    sep_reference_id: str
    local_context: str
    articulating_axes: set[str]
    confirmed_by: User | None

@dataclass
class TeacherMapItem:
    analytic_item_id: str
    order: int
    activity_snapshot_ids: list[int]
    progress: Literal["pending", "current", "worked"]

@dataclass
class TeacherCurriculumMap:
    teacher_id: int
    school_cycle: str
    items: list[TeacherMapItem]
```

### Módulo profundo propuesto

La interfaz de aplicación debe ser pequeña aunque internamente resuelva versiones, permisos y snapshots:

```python
class CurriculumMapService:
    def load_map(self, *, teacher, school_cycle) -> CurriculumMapView: ...
    def apply(self, *, teacher, command: MapCommand) -> CurriculumMapView: ...
    def prepare_session(self, *, teacher, activity_id, capacity) -> SessionDraft: ...
```

`MapCommand` puede representar acciones humanas explícitas: contextualizar un contenido, asociar ejes, ordenar un tema o confirmar su avance. `prepare_session` reutiliza los límites existentes de `PublishedPackageSnapshot`, `PublishedRoadmapSnapshot` y `ClassroomSession`.

Sólo hace falta un adaptador real al inicio: `SepCatalogAdapter`, que lee una copia local, versionada y verificable del catálogo SEP. No conviene crear todavía adaptadores abstractos para IA, otros países o proveedores inexistentes.

## Reglas que el sistema debe hacer imposibles de violar

- La referencia SEP es inmutable y conserva versión, fuente e identificador estable.
- Una contextualización local no se presenta como texto oficial de la SEP.
- Los ejes articuladores son etiquetas transversales muchos-a-muchos; no sustituyen campos ni contenidos.
- Una actividad se vincula a uno o más contenidos/PDA, pero sigue siendo una actividad revisada y publicada.
- Existe un mapa docente por ciclo escolar; sus ediciones producen historia, no borrado silencioso.
- Crear o cerrar una actividad no avanza el mapa. Sólo una confirmación docente cambia `CurriculumProgress`.
- Una sesión conserva los snapshots publicados con los que comenzó.

## Alcance incremental y tiempo orientativo

Estimación para una persona desarrolladora concentrada, después de estabilizar el trabajo P0/P1 que ya está abierto:

| Entrega | Incluye | Tiempo |
|---|---|---:|
| Prototipo de decisión | 3 interacciones, datos sintéticos, prueba con docentes | 0.5–1 día |
| MVP de consulta | catálogo SEP local versionado, fases/campos/contenidos/PDA, filtros y trazabilidad | 4–7 días |
| Planeación operativa | programa analítico local, ejes, mapa docente por ciclo, vínculo con actividades | +7–12 días |
| Endurecimiento | permisos, migración, auditoría, importación offline, pruebas y manejo de versiones | +1–2 semanas |

Un corte de producción razonable completo es **3–5 semanas** para una persona. Intentar ingerir todo el plan nacional, añadir IA y migrar roadmaps simultáneamente aumenta mucho el riesgo sin validar primero la interacción.

## Riesgos

| Riesgo | Nivel | Mitigación |
|---|---|---|
| Confundir contenido oficial con ejemplos o contextualización local | Alto | capas y etiquetas visibles, fuente/versionado, texto local separado |
| Migrar los roadmaps actuales sin perder snapshots o avance | Alto | modelo aditivo, migración reversible y pruebas con datos históricos |
| Sobrecargar a la docente con taxonomía y formularios | Alto | configuración institucional previa, vista resumida y detalle bajo demanda |
| Cambios o correcciones en las fuentes SEP | Alto | catálogo versionado; nuevas versiones no reescriben sesiones ni mapas históricos |
| Decidir quién confirma el programa analítico | Medio | fijar autoridad antes del backend: colectivo escolar, Dirección o docente según flujo acordado |
| Densidad visual y rendimiento en el nodo local | Medio | carga por fase/campo, búsqueda local y listas virtualizadas si el volumen lo exige |
| Atribuir aprendizaje al porcentaje de avance | Medio | llamarlo “contenidos trabajados/confirmados”; nunca dominio o calificación |

## Corte recomendado

Primero probar una sola fase y los cuatro campos con 12–20 contenidos sintéticos, contextualización breve, ejes y actividades ya publicadas. Si las docentes entienden las tres capas y llegan a “Preparar sesión” sin explicación externa, entonces se implementa el catálogo SEP real y la persistencia.

