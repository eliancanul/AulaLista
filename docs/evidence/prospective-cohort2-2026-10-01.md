# Segunda evaluación prospectiva: tasas condicionales y regresión de propósito

En un PDF externo de **26 páginas**, B4 no mejora ninguna métrica M/W respecto a B3. Frente a B0, aumenta la proporción de citas literales válidas, pero empeora el acuerdo con la referencia IA del propósito y deja de emitirse una unidad visible. Este caso **no demuestra una mejora general de extracción**.

Los [agregados verificables](./prospective-cohort2-2026-10-01.json) conservan numeradores, denominadores, ambas repeticiones, hashes y recursos. Es **un documento**, una familia provisional y una referencia débil de IA; no hay validación humana o docente.

## Diseño y alcance

Se cerró la búsqueda al alcanzar 40 candidatos, tras 28,1 minutos declarados. Sólo uno completó los requisitos de procedencia, procesamiento privado y cribado de privacidad. Dos PDFs adquiridos se excluyeron por privacidad; otros candidatos quedaron descartados o sin resolver acceso, formato, alcance o derechos. No se reabrió la búsqueda para completar una cuota ni se ejecutaron esos descartes en el producto. Las consultas iniciales quedaron parcialmente reconstruidas por temas/intervalos, por lo que **no existe un historial exacto completo de búsqueda**.

El caso C2D01 es una [propuesta de planeación publicada por Material Educativo](https://materialeducativo.org/planeacion-didactica-por-proyectos-dia-de-muertos-del-tercer-grado-de-primaria-semana-10-del-ciclo-escolar-2024-2025/), con anexos de terceros. Se procesaron los bytes completos, sin recorte, reparación ni OCR. No se acreditó aplicación en aula ni una licencia abierta de redistribución. La revisión IA de texto y renders cubrió las 26 páginas y no detectó datos identificables de alumnado; esto no es una garantía humana de privacidad. Los originales, renders, anotaciones y salidas con texto permanecen privados.

El documento se seleccionó después de congelar B4 y no se usó para desarrollar las correcciones cloud registradas. **Faltan los hashes de los veinte PDFs históricos**: no se puede comprobar disjunción con ellos o con desarrollo no registrado. Es una evaluación prospectiva pequeña, sin división D/H ni afirmación de generalización entre familias. El piloto anterior no se reejecutó ni se mezcló con estas cifras.

| Versión | Commit de producto congelado |
|---|---|
| B0 | `2541faf04bda4dad1215a4673e3802567ca7c5c9` |
| B3 | `a4dfe5cf9975d9e9b74a256aff718aec35f11f39` |
| B4 | `bf1ae21eae80ed38ef02179ea5724b7b0aa7b1c7` |

El harness 1.2.0-portable añade el perfil explícito `b0-b3-b4` y conserva `b0-b2-b3` como default. Verifica identidad de configuración, snapshots, freeze y recibos de workers antes de puntuar. Las fórmulas M/W, lector, normalización y límites permanecen iguales. El código local ejecutado `4a7b63a…` y el commit publicado `d5dbb55ec6b13cd11913f66a27dbb975e8129c47` tienen el mismo árbol `9abbb33ad4c537f58fc9fe58543b3e5c6ec0d533`; difieren los metadatos Git de publicación.

Dos lectores IA independientes vieron primero el panel físico 1/2/3/6, con contexto 4/5/7, sin código de producto, salidas ni anotaciones ajenas. W puntúa sólo cuatro slots de vista general en las primeras tres páginas: proyecto, propósito, finalidad y campos formativos como conjunto. La referencia cerró **3 positivos, 1 ausente y 0 desconocidos**. El inventario interior de unidades/relaciones no se convirtió en un score semántico.

## Resultados mecánicos de la repetición primaria

| Medida | B0 | B3 | B4 |
|---|---:|---:|---:|
| Pipelines completados / documentos | 1/1 | 1/1 | 1/1 |
| Páginas con texto extraíble, lectura común | 24/26 | 24/26 | 24/26 |
| Citas literales válidas / citas emitidas | 25/29 (86,21%) | 24/26 (92,31%) | 24/26 (92,31%) |
| Campos no vacíos con todas sus citas válidas (M4) | 23/27 (85,19%) | 22/24 (91,67%) | 22/24 (91,67%) |
| Campos fuertes con evidencia inválida/ausente | 4/27 (14,81%) | 2/22 (9,09%) | 2/22 (9,09%) |
| Documentos con algún defecto mecánico | 1/1 | 1/1 | 1/1 |

B0→B4 aumenta la tasa de citas válidas **6,10 puntos porcentuales**, y reduce las citas inválidas de 4 a 2 (50% del conteo observado). Sin embargo, se emiten menos citas: 29→26, y el número de citas válidas baja 25→24. Los denominadores condicionales y su composición cambian; esto no equivale a recuperar más contenido del documento. M4 aumenta 6,48 puntos, con la misma limitación. M2 sólo describe presencia de texto, no comprensión de páginas, imágenes o tablas.

El inventario emitido cambia: unidades **10→9**, campos candidatos **27→24**, slots vacíos **40/67→37/61**, claims **77→70** y tramos sin asignar **0→1**. B3/B4 tienen 18/18 anclas mecánicamente válidas y 9/9 unidades emitidas con ancla propia; eso no demuestra corrección de límites, pertenencia ni recuperación de unidades omitidas.

## Regresión contra la referencia IA

| Resultado sobre los mismos 3 slots positivos | B0 | B3 | B4 |
|---|---:|---:|---:|
| Acuerdo C | 3/3 (100%) | 2/3 (66,67%) | 2/3 (66,67%) |
| Desacuerdo W | 0/3 | 1/3 | 1/3 |
| Abstención A | 0/3 | 0/3 | 0/3 |
| Cobertura de respuesta | 3/3 | 3/3 | 3/3 |
| Emisión sobre el slot ausente | 0/1 | 0/1 | 0/1 |

El acuerdo IA B0→B4 cae **33,33 puntos porcentuales**: el propósito pasa C→W. Los otros dos positivos mantienen C→C. No hay mejora incremental B3→B4 ni cambio de abstención. Estos porcentajes describen tres oportunidades de un caso; **no son precisión semántica humana**. No se sumó la abstención correcta del negativo para inflar una tasa de acierto.

La revisión descriptiva posterior explica tres límites, sin cambiar referencia ni puntuación:

- **Propósito:** B0 coincide con los 592 caracteres normalizados de referencia. B3/B4 preservan ese prefijo, pero añaden 1384 caracteres de metodología, tabla curricular y cabecera editorial (1976 en total), fuera de la celda de propósito. Lo marcan `ambiguous/pending`; sigue siendo un candidato, por lo que cuenta W y no abstención
- **Unidad no emitida:** la fuente muestra la sexta sesión partida entre etiqueta/número en p6, con continuación en p7. Los dos lectores ya la inventariaron antes de las salidas. B0 la emite; B3/B4 guardan sólo su inicio de p6 como tramo sin asignar en notas de la sesión anterior. Esto no se convierte retrospectivamente en una tasa de segmentación
- **Dos citas remanentes:** cierre y contexto de ejecución de la primera unidad contienen cambios de whitespace respecto de p3. Coinciden bajo normalización de espacios, pero conservan su invalidez literal estricta en M3/M6. Ese fallo mecánico no prueba contenido inventado

## Congelación, recursos y verificación

Freeze ejecutado: `56342c9afa0634b6b65b10024ec34f93e6e9a2ceaa9fefa9d4d637a161f547a0`, con 33 artefactos. Una primera versión no ejecutada quedó preservada; la segunda completó eventos de procedencia y separó el registro histórico de descubrimiento de la admisión final. No cambió corpus, referencias, releases ni scoring.

La corrida única registró 6/6 pipelines completos, del 01-10-2026 09:09:15,101 al 09:09:25,318 UTC: **10,22 segundos**. Las tres parejas, una por release, fueron completas e idénticas. La repetición 1 es primaria; la 2 no aumenta n. B3 y B4 tienen métricas e inventarios iguales, pero sus JSON canónicos difieren en 11 rutas de notas/razones diagnósticas: no se afirma igualdad de todas sus salidas.

Los workers sumaron 9,24 segundos; máximo 1,68 segundos y 41.283.584 bytes de RSS reportado por worker. No hubo llamadas a modelos externos; la referencia visual sí fue producida por IA nativa. El costo monetario no fue medido y no se activaron nuevos servicios de pago o billing.

La validación de software cerró con **1203 tests aprobados y 10 omitidos**. Los dos fallos iniciales eran Node ausente del PATH del proceso de checks; se preservaron y se corrigió sólo ese entorno, sin tocar código ni el allowlist del harness. Los dos controles focales y la global final pasaron. La revisión independiente añadió 59 controles de instrumentación, 314 comprobaciones de resultados y 20 de integridad. Son controles de software/cómputo, no nuevas planeaciones ni observaciones humanas.

Se conserva el resultado negativo. No se ajustó el producto al caso, no se repararon sus bytes y no se modificó la referencia tras las salidas. El caso ahora está expuesto para futuras decisiones de desarrollo. Las siguientes prioridades requieren decidir alcance: límites de campos en tablas, conservación de unidades partidas y una base autorizada más diversa; no se implementa otro parche dentro de esta evaluación.
