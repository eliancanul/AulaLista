# Issue #96: benchmark de la fixture aislada de cinco páginas

Este benchmark compara el flujo LLM existente con la interfaz pública
`curriculum.curriculum_import.build_annex_fast_path`, cuando está disponible.
No crea `CurriculumImportJob`, no publica contenido y sólo escribe JSON en
stdout. El resultado puede redirigirse a un archivo de evidencia por quien
ejecute la prueba.

## Ejecución

Desde la raíz del checkout:

```bash
./.venv/bin/python scripts/benchmark_issue96_annexes.py \
  --mode both --candidate-scope job --warmup 1 --runs 5
```

La salida registra SHA-256 del PDF, modelo, URL local de Ollama, opciones del
cliente (temperatura, formato estructurado, timeout, reintentos y tamaño de
chunk), hardware/versión de Python, estado de `ollama ps`, tiempos por etapa,
conteo de llamadas y `llm_trace` del baseline. El límite externo por corrida
usa `CHAT_TIMEOUT_SECONDS` si no se proporciona `--deadline-seconds`; cuando
vence, la corrida queda como `timeout_censored` y no se permite que los
reintentos internos conviertan una prueba de minutos en una espera indefinida.

El número de corridas y warm-up son configurables. La mediana y p95 se calculan
sólo sobre corridas completas. Cuando ambos lados tienen medianas completas,
el JSON incluye `median_speedup_percent` y un booleano de la compuerta de 50%.
Ese booleano no sustituye la revisión de calidad.

Para una comprobación rápida que no llama a Ollama:

```bash
./.venv/bin/python scripts/benchmark_issue96_annexes.py \
  --quality-only --mode candidate
```

Si el checkout no expone `build_annex_fast_path`, candidate termina con
`unavailable` y un mensaje explícito. Si la interfaz existe pero devuelve
`None` para el documento, termina con `failed`; no se inventa una medición de
la vía rápida.

El alcance candidate por defecto es `job`: sube el mismo PDF a un
`CurriculumImportJob` temporal, ejecuta `_import_action_extract` hasta
`STATUS_ACTIVITIES_PROPOSED` y revierte la transacción. Los hashes visuales del
candidate se calculan reabriendo el archivo desde `job.pdf.path` (storage
persistido) y se comparan con la referencia del PDF de entrada; no se reutiliza
el path original para ambos lados. Este alcance no convierte drafts ni publica
packages; esas garantías pertenecen a las pruebas core de package/snapshot.
`--candidate-scope
adapter` mide únicamente el adaptador público y sirve como smoke test rápido;
no es el gate final.

## Compuerta determinista de calidad

La fuente debe conservar exactamente tres anexos (`ANEXO # 01`, `02`, `03`),
cada uno con su URL exacta, hash de `source_text` y página fuente. El PDF
aislado tiene cinco páginas; los anexos ocupan las páginas 3, 4 y 5.
Además, el benchmark confirma que las cinco páginas tienen recursos PDF,
objetos gráficos/imágenes, streams de contenido no vacíos y un render PNG no
vacío.

También se verifica:

- Anexo 1: exactamente tres líneas con cinco huecos, además de la instrucción
  de las cinco vocales. Su companion debe declarar
  `requires_human_answer_key=true`, ser `non_evaluable` y no inventar una
  clave ni auto-score.
- Anexo 2: exactamente las correspondencias ordenadas `A→verde`,
  `E→amarillo`, `I→rojo`, `O→azul`, `U→anaranjado`, sin colores repetidos.
- Anexo 3: exactamente estas cuatro relaciones ordenadas: grupo minúsculo →
  vocales minúsculas, grupo mayúsculo → vocales mayúsculas, menor → vocales
  minúsculas y mayor → vocales mayúsculas.
- Candidate: el manifiesto y cada companion deben conservar exactamente el
  `source_text` (también verificado por hash), página, anchor, URLs y details
  derivados de la fuente. Se mantienen 5 preguntas del mapa de color y 4
  relaciones del anexo 3; esas preguntas tienen exactamente una respuesta
  esperada y al menos una pista. El harness ejecuta además un mutation
  self-test: cambia en memoria una respuesta de color y una de matching y
  exige que el gate las rechace.

Los hashes ordenados de XObjects y streams de las páginas 3–5 se registran en
la salida y se comparan de nuevo durante cada corrida candidate. Si cambia el
recurso visual respecto de la referencia de la misma ejecución, candidate
queda como `quality_failed`.

La calidad de la fuente y la calidad de candidate son campos separados. Un
baseline que sólo alcance a cronometrar la generación no se considera prueba
de que el modelo haya preservado los anexos.

## Línea base real observada

Fixture: `output/pdf/prueba-issue-96-paginas-4-a-8.pdf`, modelo
`qwen2.5:14b`, Ollama local, contexto 4096 y temperatura 0.

Mediciones completas hasta actividades:

| Etapa | Tiempo |
| --- | ---: |
| Extracción PDF | 90 ms |
| `identify_topics`, chunk 1 (páginas 1–3) | 120.086 s |
| `identify_topics`, chunk 2 (páginas 4–5) | 54.912 s |
| Consolidación semántica | 20.758 s |
| `propose_subtopics` | 66.047 s |

La primera llamada real de `propose_activities`, con el contexto completo y
`count=2`, superó el timeout de 180 s sin devolver respuesta. Se interrumpió
antes de los reintentos internos. Por ello el baseline real se documenta como
`timeout_censored >180 s` para esa etapa, no como un tiempo completo ni como
una mediana final. El flujo acumulaba aproximadamente 261.8 s antes de la
primera actividad. Esta evidencia no demuestra todavía una reducción de 50%.

La medición candidate de cinco corridas realizada con el mismo fixture y la
interfaz pública, con alcance `job`, ejecutó el worker real hasta
`activities_proposed` dentro de una transacción revertida. Produjo 3
actividades y 0 llamadas LLM, con mediana de 1,585 ms y p95 de 1,601 ms; el
gate de los tres anexos, la comprobación semántica y el render del PDF pasaron
en las cinco corridas. El alcance `adapter` sigue disponible para un smoke test
mínimo. Esta medición candidate no es una comparación final, porque el
baseline equivalente no terminó.

## Criterio de aceptación de rendimiento

Para declarar el objetivo de issue #96, se deben ejecutar las cinco corridas
completas de baseline y candidate con el mismo PDF, modelo y opciones, sin
`timeout_censored`, y comprobar:

```text
candidate.median_ms <= baseline.median_ms * 0.5
candidate.quality.pass == true
```

Si el baseline continúa censurado, se puede proporcionar explícitamente un
`--baseline-lower-bound-elapsed-ms` respaldado por esta evidencia. En la
medición observada, 261.8 s transcurrieron antes de la primera actividad y esa
llamada superó 180 s, por lo que `441800` ms es un límite inferior conservador
para esa corrida. El JSON sólo puede emitir entonces:

```text
proven_at_least_50_percent_faster = candidate.p95_ms <= 0.5 * lower_bound
```

No emite mediana/p95 del baseline censurado ni un claim estadístico. Si no se
proporciona ese argumento, el resultado correcto continúa siendo
“no concluyente”.

La comprobación conservadora ejecutada con `--candidate-scope job` obtuvo
`candidate_p95_ms=1622` y `proven_at_least_50_percent_faster=true` frente al
límite inferior de `441800` ms. Esto sólo prueba que el p95 candidate observado
queda por debajo de la mitad del límite inferior censurado; no convierte ese
límite en una mediana baseline.
