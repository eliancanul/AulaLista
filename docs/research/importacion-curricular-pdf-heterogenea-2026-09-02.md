# Importación curricular heterogénea: diagnóstico, método fiable e interfaz flexible

**Fecha de corte:** 2026-09-02

**Ámbito:** PDF nacido digital, PDF escaneado o mixto y planeaciones HTML; extracción local/offline como primera opción.

**Estado:** investigación y propuesta de diseño; no es una especificación aprobada ni evidencia de validación pedagógica.

> Esta nota distingue **hechos observados**, **evidencia técnica publicada** e
> **inferencias para AulaLista**. Las planeaciones comerciales se usan como
> muestras de formato, no como autoridad curricular. Ninguna extracción,
> confianza automática o modelo puede aprobar ni publicar un
> `CurriculumPackage`.

## Conclusión ejecutiva

El salto de calidad no vendrá de enviar más texto plano a una LLM. El problema
es anterior: un PDF conserva una apariencia visual, pero no necesariamente la
semántica de encabezados, tablas, orden de lectura, anexos o sesiones. La propia
documentación de pypdf explica que PDF carece de una capa semántica y que pypdf
no hace OCR ni puede extraer texto de imágenes
([pypdf, extracción de texto](https://pypdf.readthedocs.io/en/6.12.0/user/extract-text.html)).

La opción fiable es un pipeline **layout-aware, por página y por región**, que:

1. preserve el archivo original y su hash;
2. enrute cada página/región entre extracción nativa y OCR;
3. represente texto, tablas, figuras y orden de lectura antes de interpretar;
4. construya una jerarquía documental sin forzar un único formato de planeación;
5. vincule cada afirmación a página, `bbox` y fragmento textual;
6. mida confianza por etapa y se abstenga ante ambigüedad;
7. entregue un expediente revisable, no una actividad aprobada;
8. evalúe cada capa contra un corpus anotado de planeaciones reales.

Recomendación inicial: hacer un **benchmark en shadow mode** de dos adapters
locales (Docling y una ruta explícita PDF nativo + OCR), usando las muestras de
esta nota y más documentos anotados. No elegir un parser por su demo o por una
tabla de resultados externa. Docling ofrece una representación estructurada,
tablas, OCR y geometría, y declara ejecución en hardware común
([artículo original](https://arxiv.org/abs/2501.17887),
[CLI oficial](https://github.com/docling-project/docling/blob/main/docs/reference/cli.md));
MinerU es una alternativa útil para contraste y reconoce explícitamente que los
layouts complejos pueden fallar
([repositorio oficial](https://github.com/opendatalab/MinerU)).

## 1. Hechos observados en las muestras

La inspección se hizo visualmente y con pypdf por página. Los conteos de texto
son diagnóstico de extracción actual, no evaluación de fidelidad semántica.

| Referencia | Huella SHA-256 | Forma observada | Riesgo principal |
| --- | --- | --- | --- |
| `output/pdf/prueba-issue-96-paginas-4-a-8.pdf` | `33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648` | 5 páginas verticales: ficha de planeación, tabla de sesiones y 3 anexos/cuadernillo con texto e imagen | El recorte parece un documento completo aunque sólo sea un fragmento |
| `/Users/dojo/Downloads/curricula completa.pdf` | `c5a5455b52aa55dba2c9f58b650c8d37cdf1a486c07ce6a4645230d296bc043a` | 44 páginas; portadas/separadores sin texto extraíble, 4 bloques por campo, sesiones, anexos, continuaciones, rúbricas y publicidad | Un fast path global todo-o-nada confunde bloques hermanos, anexos y páginas auxiliares |
| `/Users/dojo/Downloads/Planeacio5toGradoSemana02MeReconozco_a_Através_De_Mi_Familia.docx.pdf` | `12f24c6b2ea356edfde1fb31c1f112644d72b386a87798d17d8a66e8c04f0354` | 15 páginas horizontales; tabla compleja, proyecto y sesiones; anexos 01-04 casi sólo visuales; 5 páginas finales promocionales | El texto plano pierde columnas/celdas y omite el contenido visual de los anexos |
| `/Users/dojo/Downloads/planeacion-julio-quinto-grado.pdf` | `065e5bed6bddf2f88035c1088f6b4dd450136ab0b2a718825da03239ff41aadb` | 11 páginas horizontales; varios proyectos, semanas/días, evaluación, rúbrica y adecuaciones | La unidad no es siempre “un tema”: puede ser mes → semana → día → proyecto/actividad |
| [Red Magisterial, Español 5.º, bloque I](https://www.redmagisterial.com/planeacionesnme/primaria/5-5to/53-espanol/1) | URL consultada 2026-09-02 | 5 sesiones de 50 minutos; cada sesión tiene Inicio, Desarrollo, Cierre, tiempos, recursos y evaluación | Una página HTML puede ser estructurada sin compartir la taxonomía exacta de los PDF |

En Red Magisterial, por ejemplo, una sesión distribuye 15 minutos de inicio, 25
de desarrollo y 10 de cierre; otra usa 20/15/15. Esto demuestra variación incluso
dentro de una misma fuente. Es referencia de forma, no prueba de que esa
temporalización sea normativa ni adecuada para todos los grupos.

### Diagnóstico del importador actual

**Hechos del checkout:**

- `extract_pdf_pages()` devuelve un `str` por página con `pypdf.extract_text()`.
- `chunk_pages()` concatena páginas hasta un máximo de caracteres y conserva
  sólo rangos de página, no regiones, tablas ni coordenadas.
- `identify_topics()` pide a la LLM títulos y páginas; luego filtros de texto y
  una consolidación semántica intentan eliminar contenedores o duplicados.
- El fast path de anexos exige que todos los anexos reconocidos coincidan con
  uno de tres builders; si uno no coincide, hace fallback global.
- El recorte contiene exactamente el patrón para el que existen esos tres
  builders. El PDF de 44 páginas incluye anexos 01-13, páginas de continuación,
  cuatro proyectos y otros tipos de actividad.

**Inferencia para AulaLista:** la discrepancia recorte/completo no es un fallo
aislado de prompt. Es una incompatibilidad entre una representación plana y un
documento compuesto. Extender expresiones regulares por editorial aumentaría la
cobertura aparente, pero mantendría la pérdida silenciosa y haría más costoso
incorporar nuevas familias.

## 2. Método propuesto

### 2.1 Ingesta inmutable y manifiesto de cobertura

Conservar los bytes originales, MIME, tamaño, número de páginas, hash SHA-256,
versión de cada extractor y configuración. Cada página y cada región detectada
debe terminar en uno de cuatro estados explícitos:

- `included`: aporta evidencia textual/estructural;
- `reference_only`: figura o cuadernillo conservado para consulta;
- `quarantined`: posible contenido útil que requiere revisión;
- `excluded`: portada, publicidad u otro material excluido con razón visible.

La suma debe cubrir el 100 % de las páginas y regiones. “Ignorar cuadernillos”
debe significar **no convertir su gráfica en actividad automática por ahora**,
no borrar la página: su texto extraíble/OCR, imagen, ubicación y vínculo con la
sesión permanecen en `reference_only`.

### 2.2 Enrutamiento por página y región: nativo, OCR o híbrido

No clasificar todo el PDF como nacido digital o escaneado. Medir por página:
density y calidad Unicode del texto nativo, cobertura de imágenes, geometría de
glifos, discrepancia entre render y texto, rotación y skew. Una página puede
combinar texto vectorial con un anexo rasterizado.

- **Ruta nativa:** conserva caracteres y geometría del PDF cuando son útiles.
- **Ruta OCR:** renderiza sólo páginas/regiones sin texto fiable; idioma
  `spa` y resolución/preprocesamiento registrados.
- **Ruta híbrida:** conserva texto vectorial y aplica OCR a imágenes o regiones
  faltantes; reconcilia duplicados por solapamiento geométrico.

OCRmyPDF distingue modos `skip`, `redo` y `force`; `redo` puede conservar texto
visible y reemplazar capas OCR previas, mientras `force` rasteriza todo
([documentación oficial](https://ocrmypdf.readthedocs.io/en/latest/advanced.html)).
Tesseract advierte que skew, resolución, ruido y segmentación de página cambian
la calidad; recomienda inspeccionar el preprocesamiento y ajustar el modo de
segmentación al layout
([guía oficial](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)).
Por eso `force` no debe ser el default y el OCR nunca debe reemplazar en silencio
una extracción nativa mejor.

### 2.3 Representación layout-aware antes de interpretar

El resultado intermedio debe ser un árbol/graph de evidencia, no Markdown ni un
string concatenado:

```text
Document
└─ Page
   └─ Region (title | paragraph | list | table | figure | form | header | footer)
      ├─ Block/Line/Token
      ├─ bbox + reading_order
      ├─ text_native / text_ocr
      └─ extraction_evidence + confidence
```

DocLayNet contiene 80,863 páginas anotadas de fuentes diversas, 11 clases de
layout y acuerdo entre anotadores; sus autores muestran que modelos entrenados
en colecciones de artículos científicos generalizan peor a layouts diversos
([artículo original](https://arxiv.org/abs/2206.01062)). Esto respalda evaluar
layouts educativos propios y no asumir que un modelo general basta.

Las tablas requieren estructura de filas, columnas, celdas combinadas y
encabezados. PubTables-1M separa detección, reconocimiento de estructura y
análisis funcional
([artículo original](https://arxiv.org/abs/2110.00061)); la estructura de una
planeación horizontal no debe convertirse prematuramente en una secuencia de
texto.

### 2.4 Segmentación jerárquica y tipado semántico

Después del layout, construir contenedores anidados y contiguos:

```text
colección → documento → bloque curricular/proyecto → periodo → sesión
→ fase de sesión (inicio/desarrollo/cierre) → actividad/recurso/evaluación
```

No todos los niveles tienen que existir. La jerarquía se infiere con evidencia
combinada:

1. encabezados y estilo/posición;
2. tablas y celdas contenedoras;
3. numeración, fechas y temporalidad;
4. continuidad entre páginas;
5. anclas semánticas (`SESIÓN`, `Inicio`, `Desarrollo`, `Cierre`, `Anexo`, etc.);
6. coherencia de lectura y vecinos;
7. adapter de familia documental sólo cuando haya varias muestras y pruebas.

El resultado debe permitir `plan`, `session`, `phase`, `activity`, `resource`,
`assessment`, `worksheet`, `rubric`, `cover` y `promotional`, más `unknown`.
`unknown` es un resultado válido. Una regla de editorial puede elevar precisión,
pero no debe ser requisito para extraer la estructura común.

### 2.5 Provenance verificable

Cada campo interpretado debe apuntar a uno o más `EvidenceSpan` con:

- hash del archivo y página física;
- `bbox` normalizado y sistema de coordenadas;
- texto exacto y offsets cuando existan;
- método (`native`, `ocr`, `derived`) y versión/configuración;
- relación de derivación y, si hay conflicto, alternativas.

ALTO modela layout y contenido OCR con coordenadas por bloque/línea/palabra
([estándar mantenido por Library of Congress](https://www.loc.gov/standards/alto/)).
El Web Annotation Data Model permite selectores de fragmento, texto y regiones
`xywh`
([Recomendación W3C](https://www.w3.org/TR/annotation-model/)); PROV define un
modelo interoperable de entidades, actividades y agentes
([familia W3C PROV](https://www.w3.org/TR/prov-overview/)). No es necesario
adoptar los tres formatos completos, pero sí copiar sus propiedades útiles:
identidad estable, selector preciso, derivación y versión.

Docling ya representa `page_no`, `bbox` y `charspan` en sus items
([tipos oficiales](https://github.com/docling-project/docling-core/blob/main/docling_core/types/doc/document.py)).
El ledger canónico de AulaLista debe ser independiente del adapter para que una
actualización de Docling, Tesseract o un parser futuro no cambie la Interface.

### 2.6 Confianza y abstención

No usar un único promedio. Mantener un vector al menos por estas capas:

- `capture`: ¿la página/región fue procesada y reconciliada?;
- `ocr`: confianza y calidad de caracteres;
- `layout`: clase y geometría;
- `reading_order`;
- `table_structure`;
- `semantic_role`;
- `curriculum_mapping`.

Las invariantes duras dominan al score: una tabla incompleta, página sin estado,
actividad sin fuente o conflicto de lectura obliga a `needs_human_resolution`
aunque el promedio sea alto. Las probabilidades de un modelo suelen estar mal
calibradas; temperature scaling es un método de calibración posproceso, no una
garantía universal
([Guo et al., artículo original](https://arxiv.org/abs/1706.04599)). La
abstención debe evaluarse como curva **riesgo-cobertura** sobre datos reservados,
siguiendo la idea de clasificación selectiva a un riesgo objetivo
([Geifman y El-Yaniv, artículo original](https://arxiv.org/abs/1705.08500)).

**Inferencia para AulaLista:** la confianza decide entre “proponer”, “pedir
revisión” y “no interpretar”; nunca decide publicación, corrección pedagógica o
`CurriculumProgress`.

### 2.7 Del documento a apoyo de clase, sin sustituir al docente

El parser debe preservar la duración de la sesión fuente y permitir una
`online_window_minutes` separada. Para una clase de 50 minutos como las muestras
de Red Magisterial, AulaLista puede proponer una ventana online de 20-30 minutos
dentro de Inicio/Desarrollo/Cierre, pero no convertir automáticamente toda la
sesión en cuestionario. Deben permanecer visibles:

- lo que explica, modela o conversa la maestra;
- la actividad en línea opcional y su alternativa offline/compartida;
- los materiales y cuadernillos de referencia;
- el cierre y la observación/evaluación formativa docente.

Una salida breve debe limitar propósito, instrucciones y reactivos por tiempo,
no por truncar la fuente. Si el tiempo no alcanza, el sistema divide o pide una
decisión; no omite silenciosamente actividades.

## 3. Evaluación reproducible

OmniDocBench propone evaluar texto, fórmulas, tablas y orden de lectura sobre
documentos diversos
([artículo original](https://arxiv.org/abs/2412.07626)). Para AulaLista hace
falta además un gold set específico, estratificado por fuente, grado, orientación,
PDF nativo/escaneado/mixto, tablas, anexos y páginas promocionales.

### Corpus inicial

Las cuatro huellas PDF y la URL anteriores forman un **corpus semilla**, no un
benchmark representativo. Antes de copiar materiales comerciales a fixtures del
repositorio hay que confirmar licencia/permiso; mientras tanto el manifiesto de
hashes permite reproducir localmente la inspección sin confundir archivos.

Anotar por duplicado una muestra de páginas y resolver desacuerdos. El gold set
debe incluir:

- región, clase y `bbox`;
- líneas/tokens y orden de lectura;
- tabla/celdas;
- árbol documental y continuaciones entre páginas;
- rol semántico y relación sesión-cuadernillo;
- campos extraídos con provenance;
- decisión `include/reference/quarantine/exclude`.

### Métricas por capa

| Capa | Métrica | Fallo que revela |
| --- | --- | --- |
| OCR | CER/WER por tipo de página e idioma | Texto visual mal reconocido |
| Layout | mAP/IoU por clase y recall de regiones | Bloques omitidos o mal clasificados |
| Orden | precisión de relaciones predecesor-sucesor o edit distance | Columnas/celdas mezcladas |
| Tablas | GriTS para topología, ubicación y contenido; TEDS como contraste | Filas, columnas o celdas combinadas rotas |
| Jerarquía | F1 por nivel + similitud de árbol + exactitud de continuaciones | Sesiones/anexos asociados al bloque equivocado |
| Campos | precision/recall/F1 y exact match normalizado | Fechas, tiempos, actividades o PDA incorrectos |
| Provenance | exactitud página+bbox, cobertura y resolubilidad del selector | Afirmaciones no auditables |
| Abstención | risk-coverage y error aceptado a cobertura dada | Sistema seguro sólo porque rechaza todo, o confiado pero erróneo |
| End-to-end | expediente aceptable por revisor, tiempo, memoria y latencia por página | Parser preciso pero inviable en el nodo local |

GriTS evalúa una tabla en su forma matricial y separa topología, ubicación y
contenido
([artículo original](https://arxiv.org/abs/2203.12555)); TEDS usa similitud por
edición de árbol HTML
([PubTabNet, artículo original](https://arxiv.org/abs/1911.10683)). Ninguna de
estas métricas por sí sola prueba una importación curricular correcta.

### Gates propuestos (decisión de producto, todavía no validados)

- 100 % de páginas/regiones con estado de cobertura.
- 100 % de campos aceptados con al menos un `EvidenceSpan` resoluble.
- Cero publicación o conversión automática desde regiones `quarantined`.
- Cero pérdida silenciosa al cambiar de adapter; las diferencias quedan en el
  expediente.
- Umbrales de OCR/layout/tablas y risk-coverage se fijan **después** del
  baseline y se validan en un set reservado; no se inventa hoy un “95 % fiable”.
- Rendimiento se informa por ruta, página y percentiles; timeout produce parcial
  reanudable, no reinicio o descarte.

## 4. Alternativa de interfaz flexible y extensible

### Module y Seam externos

**Module:** `CurriculumSourceInterpreter`

**Seam:** entre la carga autorizada de una fuente y la UI de revisión docente.

**Objetivo de profundidad:** ocultar detección PDF/OCR, layout, reconciliación,
tablas, jerarquía, confidence, provenance y checkpoints tras dos operaciones.

```text
Interface CurriculumSourceInterpreter
  prepare(source: SourceArtifact, intent: ImportIntent) -> ImportDossier
  resolve(dossier_id: DossierId, resolutions: HumanResolution[]) -> ImportDossier
```

No se exponen etapas como `extract`, `ocr`, `chunk`, `identify_topics` o
`consolidate_topics`. Hacerlo obligaría a cada caller a orquestar el algoritmo y
convertiría el Module en una colección shallow.

### Tipos visibles en la Interface

```text
SourceArtifact
  bytes | stable_local_handle
  media_type
  display_name?                 # nunca identidad

ImportIntent
  owner                         # cuenta docente autenticada
  teaching_context?             # fase/grado/campo si la maestra lo confirma
  online_window_minutes: 20..30
  worksheet_policy: text_only | reference_only
  locale: es-MX

ImportDossier
  source_identity              # sha256, MIME, páginas
  status: ready_for_teacher_review
        | needs_human_resolution
        | unsupported
        | partial
        | failed
  document_tree
  interpreted_units[]          # periodo, sesión, fase, actividad, recurso, evaluación
  coverage_manifest[]
  evidence_ledger[]
  conflicts[]
  review_questions[]
  adapter_receipt[]             # nombre/versión/config, sin filtrar detalles internos
  checkpoint?

HumanResolution
  conflict_id
  choice | corrected_value | exclude_with_reason
  actor
```

`ImportDossier` no es `CurriculumPackage`, `ActivityDraft`,
`PublishedPackageSnapshot` ni `CurriculumProgress`. Otro Module puede convertir
unidades seleccionadas en `ActivityDraft`; la persona docente las edita y un
`EditorialReviewer` conserva la única autoridad de publicación.

### Invariantes de la Interface

1. El hash identifica la fuente; nombre y URL no activan reglas.
2. Toda unidad/campo aceptado tiene provenance resoluble al original.
3. Toda página/región tiene estado de cobertura y razón.
4. `text_only` no borra imágenes/cuadernillos: los conserva como referencia.
5. Un resultado parcial nunca se presenta como completo.
6. Reintentar con igual fuente, versiones e intent no duplica unidades; el
   expediente declara si cambió cualquier adapter/configuración.
7. Confidence y una LLM pueden proponer, pero no resolver conflictos, aprobar,
   publicar ni avanzar `CurriculumProgress`.
8. `resolve()` sólo acepta decisiones sobre conflictos ya enumerados y registra
   actor/fecha; no es una puerta trasera para texto sin fuente.
9. Propiedad y consulta del expediente permanecen en la cuenta docente creadora.
10. La duración online es una restricción de diseño de la propuesta posterior,
    no una orden de recortar la planeación original.

### Orden, performance y errores

`prepare()` valida/preserva la fuente antes de extraer y puede devolver
`partial` con checkpoint. `resolve()` sólo opera después de `prepare()` y puede
producir nuevas preguntas si una resolución descubre otro conflicto.

Errores observables y estables:

- `invalid_source`, `encrypted_source`, `unsupported_media`;
- `resource_limit` y `deadline_reached`, ambos con parcial/checkpoint si existe;
- `adapter_failed`, con receipt y regiones afectadas;
- `evidence_conflict`, que es revisable y no fallo técnico;
- `invariant_violation`, que bloquea cualquier conversión posterior;
- `stale_resolution`, si el expediente o adapter cambió.

La Interface promete progreso y parcial reanudable, no una latencia fija antes
de medir. Los presupuestos se aplican por página/etapa con cancelación
cooperativa, no como timeout global de un PDF de 50-60 páginas.

### Seams internos y Adapters

Estos seams pertenecen a la Implementation y no deben filtrarse a callers:

| Seam interno | Adapters reales | Categoría de dependencia |
| --- | --- | --- |
| `DocumentEvidenceAdapter` | `NativePdfLayoutAdapter`, `OcrLayoutAdapter`, `HtmlPlanAdapter` | Local-substitutable; test con fixtures/gold |
| `LayoutEngine` | Docling y un adapter de contraste validado | Local-substitutable; modelos/versiones fijados |
| `OcrEngine` | Tesseract `spa` y un segundo adapter sólo si el benchmark lo justifica | Local-substitutable |
| `FamilyInterpreter` | genérico; adapters por familias recurrentes con varias muestras | In-process; registry versionado interno |
| `CheckpointStore` | filesystem local y memoria en tests | Local-substitutable |

Hay seams reales donde ya existen dos comportamientos: PDF nativo/OCR y
PDF/HTML. No se propone un “plugin para cada editorial” hasta demostrar variación
repetida; una sola regla sería un seam hipotético.

### Ejemplo de uso

```text
dossier = interpreter.prepare(
  source = full_44_page_pdf,
  intent = {
    owner: teacher,
    online_window_minutes: 25,
    worksheet_policy: text_only,
    locale: "es-MX"
  }
)

# La UI muestra bloques/sesiones, anexos reference_only, páginas promocionales
# excluidas con razón y conflictos de asociación. La maestra corrige únicamente
# las preguntas explícitas.

dossier = interpreter.resolve(dossier.id, [
  { conflict_id: "...", choice: "attach_to_session_3", actor: teacher }
])
```

La forma exacta del expediente del PDF completo es resultado del futuro
benchmark, no una afirmación en esta nota.

### Tradeoffs

**A favor:** Interface pequeña, alta leverage, cambios de parser locales,
comparación de adapters sin cambiar callers, auditoría por región y pruebas a
través del mismo seam que usa la UI.

**Costes:** mayor almacenamiento, más CPU que pypdf plano, anotación manual del
gold set, versionado de adapters y una UI de resolución. Las confidencias de
distintos motores no son directamente comparables y deben calibrarse por ruta.

**Alternativas descartadas por ahora:**

- exponer un pipeline configurable de muchas etapas: flexible para la
  Implementation, shallow para callers;
- añadir regex/builders hasta cubrir cada PDF conocido: rápido en el corpus
  pequeño, frágil ante nuevas familias;
- VLM end-to-end que emite JSON curricular: pierde determinismo/provenance y
  mezcla lectura con interpretación;
- OCR total: destruye información nativa útil y aumenta latencia/errores;
- escoger Docling o MinerU sin benchmark local: sus datasets y layouts no son
  los de planeaciones mexicanas.

## 5. Secuencia recomendada antes de codificar producto

1. Congelar el corpus semilla mediante manifiesto; resolver licencia antes de
   copiar PDF comerciales al repositorio.
2. Definir el schema del gold set y anotar páginas representativas por dos
   personas.
3. Ejecutar un spike aislado de adapters en shadow mode; no tocar aún
   `CurriculumImportJob`.
4. Comparar pypdf actual, Docling y ruta híbrida nativo+OCR con la matriz de
   métricas y recursos del nodo local.
5. Fijar gates y política de abstención con set de calibración/test separados.
6. Validar con docentes si el expediente y las preguntas de resolución son
   comprensibles, y si la ventana online de 20-30 minutos deja espacio real para
   enseñanza, conversación y cierre.
7. Sólo después redactar spec/ADR si la decisión de seam/adapter resulta difícil
   de revertir y abrir tickets verticales independientemente verificables.

## Fuentes técnicas primarias y oficiales

- pypdf, [Extract Text from a PDF](https://pypdf.readthedocs.io/en/6.12.0/user/extract-text.html).
- OCRmyPDF, [Advanced features](https://ocrmypdf.readthedocs.io/en/latest/advanced.html).
- Tesseract OCR, [Improving the quality of the output](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) y [Command Line Usage](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
- Livathinos et al., [Docling: An Efficient Open-Source Toolkit for AI-driven Document Conversion](https://arxiv.org/abs/2501.17887), y [repositorio oficial](https://github.com/docling-project/docling).
- OpenDataLab, [MinerU, repositorio oficial](https://github.com/opendatalab/MinerU).
- Pfitzmann et al., [DocLayNet](https://arxiv.org/abs/2206.01062).
- Smock et al., [PubTables-1M](https://arxiv.org/abs/2110.00061) y [GriTS](https://arxiv.org/abs/2203.12555).
- Zhong et al., [PubTabNet y TEDS](https://arxiv.org/abs/1911.10683).
- Opendatalab, [OmniDocBench](https://arxiv.org/abs/2412.07626).
- Library of Congress, [ALTO](https://www.loc.gov/standards/alto/).
- W3C, [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) y [PROV Overview](https://www.w3.org/TR/prov-overview/).
- Guo et al., [On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599).
- Geifman y El-Yaniv, [Selective Classification for Deep Neural Networks](https://arxiv.org/abs/1705.08500).
