# Piloto prospectivo de extracción en tres documentos externos

Fecha de corrida: 2026-10-01 UTC. Relacionado con #143.

Las regresiones sintéticas no bastan para estimar el comportamiento en formatos
externos. Este piloto congeló tres planeaciones publicadas por terceros antes
de ejecutar tres versiones de AulaLista. Mejoró la validez literal de las citas,
pero permanecen errores de contenido y apareció un cruce entre secuencias. **No
hay una medida de precisión humana ni una conclusión de superioridad global.**

## Diseño y trazabilidad

- Tres PDFs de primaria/NEM en español, 50 páginas físicas, tres familias de
  procedencia/plantilla provisionales: D01 (7 páginas), D02 (18) y D03 (25)
- Dos portafolios de formación docente y un proyecto institucional publicado.
  Su publicación externa no prueba aplicación efectiva en una clase
- Selección por procedencia, alcance, tamaño y cribado de privacidad. Un
  candidato con datos identificables de escolares quedó excluido antes de la
  corrida; no se creó un recorte sustitutivo
- Se redujo explícitamente el objetivo inicial de seis familias mediante una
  enmienda de factibilidad anterior a los resultados. Es una muestra pequeña,
  sin un split desarrollo/holdout completo y sin representatividad nacional
- Los documentos no se usaron en las tres iteraciones de desarrollo cloud
  registradas. Faltan hashes individuales de los 20 PDFs históricos: no puede
  demostrarse disjunción con ellos ni ausencia en entrenamiento de modelos
- El protocolo, manifiesto, configuración, evaluador y referencia se cerraron
  antes de la primera salida. No se modificó el producto ni se sustituyeron
  fuentes al observar resultados

| Versión | Commit | Comparación |
|---|---|---|
| B0 | `2541faf04bda4dad1215a4673e3802567ca7c5c9` | Antes de las tres mejoras |
| B2 | `1aae48b93c2d83aec80c1248a38c24d5960a3d2a` | Antes de contexto por ocurrencia |
| B3 | `a4dfe5cf9975d9e9b74a256aff718aec35f11f39` | Después de PR142 |

Se ejecutó `prepare → compile claims → verify` con Python 3.13.5, pypdf 6.1.3 y
las mismas dependencias. Un lector separado comprobó bytes, páginas y citas sin
usar el scanner ni las decisiones del verificador como verdad. Comparte la
biblioteca PDF genérica; por eso sólo comprueba la representación textual y no
garantiza fidelidad de columnas o comprensión de la página.

Hubo **18/18 corridas terminadas y 9/9 pares canónicos idénticos**: tres
documentos × tres versiones × dos repeticiones. Son tres documentos, no 18
observaciones independientes. Sólo se excluyeron del hash canónico los
timestamps de creación/actualización y de entradas de historial `prepare`.

El freeze original tiene SHA-256
`ab3c05bfdd179429abbc5117aa463ad58246820a52ea279d33c0af9867028788`.
Los restantes recibos, hashes, conteos y pareados públicos están en
[el agregado JSON](prospective-benchmark-2026-10-01.json).

Los PDFs, textos extraídos, anotaciones, capturas y salidas completas permanecen
fuera del repositorio público. Acceso público no equivale a licencia abierta.
La réplica exacta requiere los originales autorizados y el paquete privado de
congelación; los hashes públicos permiten cotejarlo, no reconstruirlo.

## Integridad mecánica de evidencia

Las tasas de citas y campos usan denominadores emitidos que pueden cambiar.
No son cobertura del documento ni corrección semántica.

| Métrica | B0 | B2 | B3 |
|---|---:|---:|---:|
| PDFs procesados | 3/3 | 3/3 | 3/3 |
| Páginas con texto independiente no vacío | 49/50 | 49/50 | 49/50 |
| Citas literales válidas / citas emitidas | 15/19 (78,95%) | 19/19 (100%) | 21/21 (100%) |
| Citas literales inválidas | 4 | 0 | 0 |
| Campos no vacíos con toda su evidencia válida | 12/15 (80%) | 15/15 (100%) | 16/16 (100%) |
| Campos fuertes sin evidencia mecánica suficiente | 3/15 (20%) | 0/13 | 0/13 |
| PDFs con algún defecto mecánico de evidencia/identidad | 2/3 | 0/3 | 0/3 |
| Unidades emitidas con ancla propia mecánicamente válida | 0/6 | 0/6 | 6/6 |

B0→B3 aumenta **21,05 puntos porcentuales** la validez condicional de citas.
Las cuatro citas inválidas observadas bajan a cero, una reducción de 100% de ese
conteo dentro de estos tres documentos. Sin embargo, las citas emitidas cambian
de 19 a 21 y su composición cambia. B2 ya alcanzaba 19/19; B3 añade citas y
anclas, sin mejorar esa tasa. Ninguno de estos resultados significa «extracción
100% correcta».

El universo de citas incluye la evidencia del dossier, también actividades y
anexos, sin duplicar snapshots de auditoría/historial. Las métricas de campos
se limitan a `InterpretedField` de `general_fields` y `sessions.fields`. Un campo
fuerte es `supported` o tiene un ítem `checked`; esos estados son técnicos y no
indican revisión humana. Las anclas válidas acreditan hash/página/fragmento y
offsets, no la identidad lógica de una sesión ni su relación curricular.

| Documento | Citas válidas B0→B3 | Campos no vacíos B0→B3 | Slots emitidos vacíos B0→B3 |
|---|---:|---:|---:|
| D01 | 6/9 → 8/8 | 6 → 5 | 1 → 2 |
| D02 | 7/8 → 11/11 | 7 → 9 | 35 → 33 |
| D03 | 2/2 → 2/2 | 2 → 2 | 4 → 4 |

Los slots vacíos son los que el sistema emite, no un inventario independiente
de todo lo que debió extraer. El número de unidades emitidas permanece en seis,
todas en D02; no se puntuó que equivalgan a seis clases distintas.

## Acuerdo con referencia visual IA

Dos anotadores IA leyeron las fuentes sin ver código ni salidas y conservaron
sus anotaciones por separado. Se inspeccionaron 12 páginas objetivo y dos
vecinas. Esta capa puntúa únicamente cuatro grupos de campos generales en las
tres primeras páginas: proyecto, propósito, finalidad y conjunto de campos
formativos. No puntúa el panel interior, segmentación ni relaciones.

De **12 slots**, seis quedaron presentes, dos ausentes y cuatro `unknown`:
**8/12 (66,67%) evaluables**. Se conservaron desacuerdos de transcripción,
título genérico y ambigüedad de mapeo propósito/finalidad; no se resolvieron
consultando las salidas. La comparación usa NFC, espacios normalizados y
`casefold`, sin corregir puntuación ni inferir equivalencias semánticas.

| Sobre los seis slots positivos | B0 | B2 | B3 |
|---|---:|---:|---:|
| Acuerdo textual normalizado | 2/6 (33,33%) | 3/6 (50%) | 3/6 (50%) |
| Desacuerdo textual | 4/6 (66,67%) | 2/6 (33,33%) | 2/6 (33,33%) |
| Abstención | 0/6 (0%) | 1/6 (16,67%) | 1/6 (16,67%) |
| Cobertura de respuesta | 6/6 (100%) | 5/6 (83,33%) | 5/6 (83,33%) |

B0→B3 aporta **+16,67 puntos de acuerdo**, pero también **+16,67 puntos de
abstención**. Los desacuerdos pasan de cuatro a dos (−50% relativo); sólo uno
se convierte en acuerdo y el otro en abstención. B2→B3 no cambia estos
resultados. Los dos slots ausentes no reciben candidatos en ninguna versión;
no se suman como aciertos para inflar una tasa global.

Los pareados positivos son: dos acuerdos conservados, un desacuerdo convertido
en acuerdo, uno convertido en abstención y dos desacuerdos persistentes. El
acuerdo nuevo es el título de D03; la abstención nueva es el propósito de D01.
No se observaron transiciones acuerdo→desacuerdo/abstención en este pequeño
universo puntuado. Esto no excluye regresiones fuera de él.

**Es acuerdo con una referencia IA débil, no accuracy humana, gold docente ni
validación pedagógica.** Dos anotaciones coincidentes de IA no convierten una
interpretación en verdad. El punto añadido o una referencia bibliográfica
conservada pueden afectar el acuerdo textual sin medir adecuación pedagógica.

## Hallazgos y regresiones fuera de las tasas

La revisión posterior a la corrida encontró limitaciones que la integridad
literal no revela. Se registran como análisis exploratorio asistido por IA,
sin modificar la referencia congelada ni convertirlos en una tasa semántica:

- D01 conserva opciones impresas de campos formativos como si todas aplicaran;
  la referencia sólo considera aplicado uno. También conserva paginación
  bibliográfica en el título y deja sin candidato un propósito explícito
- D02 conserva cuatro valores de actividad que contienen sólo el rótulo
  «Actividades:», sin una actividad sustantiva
- **Regresión B2→B3 de ámbito en D02:** la página física 4 cierra una secuencia
  y la 5 comienza otro bloque con nuevos datos generales e intención didáctica.
  B2 limita la unidad a `[4]`; B3 la extiende a `[4, 5]` y añade una actividad
  de ese bloque siguiente. La cita es literal válida, pero pertenece a otro
  ámbito. La actividad añadida tiene además un encabezado mal formado

Este último caso impide interpretar el aumento de citas/campos como una mejora
uniforme. La segmentación semántica no tenía una puntuación congelada, por lo
que no se inventa retrospectivamente un porcentaje para ese hallazgo.
Se mantiene abierto en [#144](https://github.com/eliancanul/AulaLista/issues/144),
separado de la publicación del harness y sin modificar esta medición.

Una auditoría de software separada verificó hashes, cronología, snapshots,
repeticiones y recomputación de métricas guardadas. Su revisión visual IA
confirmó el cruce de páginas descrito; no fue una validación humana ni una nueva
ejecución del producto sobre el corpus.

## Repetición y trabajo siguiente

El [harness portable](../../scripts/benchmark_curriculum/README.md) se adapta
después del piloto para repetir el procedimiento con manifiestos explícitos.
**No fue el ejecutable de esta corrida**; el agregado conserva el hash del
harness original. Sus tests públicos son sintéticos; CI no descarga ni procesa
estos PDFs. El guard de red/escritura actúa dentro del proceso Python y no es
un sandbox frente a código hostil.

No se afinó AulaLista contra estos resultados. Los documentos y defectos ahora
son conocidos: cualquier corrección posterior deberá tratarlos como regresión
expuesta y conservar esta primera medición. Para estimar generalización harán
falta otras fuentes reservadas y, para métricas humanas, una referencia humana
independiente con cobertura suficiente. Los 20 documentos históricos siguen
fuera de este piloto; Luna es referencia IA, no docente.
