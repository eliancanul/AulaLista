# Preguntas necesarias, agrupadas y acotadas

## Hallazgo observado

En un ensayo real previo con un PDF sintético, la segunda consulta contenía 21
pendientes: cinco faltantes obligatorios, siete confirmaciones de información
extraída/anexos y nueve vacíos opcionales. El modelo aplicó correctamente cinco
citas humanas, pero añadió una pregunta de 271 caracteres con los otros 16
destinos. Contar signos de pregunta, caracteres o turnos no detectaba esa carga.
Las confirmaciones con `is_required=true` no eran valores ausentes.

La evidencia saneada quedó congelada como
`tests/fixtures/teacher_review/oversized_question_v1.json`, con hashes canónicos
del contexto y la respuesta y procedencia del export. Sólo contiene datos
sintéticos. Su respuesta es una observación del modelo solicitado; no es gold
pedagógico, identidad independiente del modelo retornado ni permiso para otra
invocación. El PDF se regenera en el test y su SHA coincide con el observado.

## Contrato nuevo

- `missing_fields` y `all_targets` mantienen todos sus registros. El dossier,
  páginas literales, citas, sesiones, anexos, respuestas e historial permanecen
  íntegros. La cola completa de revisión no se confunde con un cuestionario.
- `question_policy` selecciona sólo `priority_state=requires_resolution`:
  requisitos ausentes o conflictos que bloquean el recorrido. Un dato extraído
  por confirmar o un vacío opcional no se pregunta automáticamente. Los campos
  opcionales con un conflicto real siguen siendo bloqueos, no se ocultan.
- Cada pregunta admite hasta tres destinos de un mismo grupo: identificación
  del proyecto/campo formativo; propósito/finalidad; inicio/desarrollo/cierre
  de una misma sesión. Otros conflictos y anexos sin vincular se tratan como
  focos individuales. No se mezclan sesiones ni ámbitos no relacionados.
- La redacción sigue siendo del proveedor y adaptativa; los grupos no son un
  catálogo de preguntas fijas. Se limita a 500 caracteres. El servidor valida
  destinos, agrupación y longitud antes de aplicar la salida, y vuelve a
  verificar el ámbito de la pregunta después de aplicar las citas válidas.
- El proveedor debe procesar primero las citas humanas y elegir la siguiente
  pregunta sobre los faltantes que todavía quedan. Si resolvió los últimos,
  debe devolver `question=null`, aunque sigan pendientes las confirmaciones
  humanas y los campos opcionales. No se recorta ni reescribe una salida
  incorrecta: se rechaza, conserva su recibo y mantiene la respuesta literal.
- Sin nuevos bloqueos y sin respuesta pendiente de procesar, el servidor cierra
  la aclaración sin consultar al proveedor. La revisión y aprobación explícita
  continúan disponibles. Pendientes opcionales y confirmaciones no se marcan
  completos ni se convierten silenciosamente en evidencia comprobada.
- Las preguntas y respuestas guardadas antes de este cambio no se borran. Una
  pregunta histórica con más destinos puede conservar sus respuestas y aplicar
  citas elegibles. El límite nuevo afecta a las nuevas preguntas, no reduce
  `answer_updates` de respuestas históricas ni reinicia el contador.
- Se conservan el máximo de seis preguntas persistidas, el guardado antes de
  avanzar, los recibos, CAS, procedencia y la aprobación exclusivamente humana.

## Evidencia offline del cambio

`test_teacher_review_question_policy.py` reproduce el contexto exacto exportado
y rechaza la respuesta histórica de 16 destinos. Una respuesta corregida,
**declarada como doble**, aplica las mismas cinco citas y cierra con siete
confirmaciones y nueve opcionales visibles. El grado ya está en el texto de
la página 1; no se interroga por él ni se corrige silenciosamente el parser.
La omisión del grado por el parser permanece como limitación de extracción.

La aceptación prueba también:

- Más de seis requisitos: diez se resuelven en cuatro preguntas agrupadas;
  dieciséis, en seis. Diecinueve dejan tres requisitos pendientes tras seis
  preguntas; la aprobación continúa bloqueada y no se finge completitud.
- Rechazo de mezclas entre sesiones, temas generales incoherentes, opcionales,
  confirmaciones redundantes y una pregunta sobre un dato recién resuelto.
- Continuidad de una pregunta opcional antigua, conservación y corrección de
  su respuesta, sin habilitar nuevas preguntas opcionales automáticas. Retomar
  una versión editada conserva visible una pregunta histórica sin responder,
  aunque no haya borrador ni nuevos bloqueos, sin consultar otra vez al modelo.
- El recorrido público HTTP del mismo PDF se adapta a cuatro preguntas
  enfocadas y conserva borradores, reapertura, fallo/reintento y aprobación.

```sh
AULALISTA_PI_LIVE_ENABLED=0 AULALISTA_LUNA_LIVE_ENABLED=0 AULALISTA_GEMINI_LIVE_ENABLED=0 \
python -m pytest -q tests/test_teacher_review_question_policy.py \
  tests/test_teacher_review_same_document.py tests/test_teacher_review_pi.py \
  tests/test_teacher_review_context_encoding.py
```

Estos tests no prueban que el modelo real responda bien al prompt nuevo. El
límite de destinos declarados tampoco verifica por sí solo el significado de
cada frase: la siguiente aceptación real debe revisar que la redacción no pida
datos adicionales fuera de ese foco. No hubo nuevas llamadas reales para este
candidato.

## Coste y compensaciones

Pi ahora serializa contexto, esquema y envoltorio JSON sin espacios de formato,
sin alterar el contenido ni recortar páginas. En los tres requests históricos
con SYSTEM y datos sin cambiar, la reconstrucción coincide con sus SHA: esta
compactación reduce 239.222 a 228.204 bytes, un 4,61 %. Es una comparación de
bytes, no una medida de tokens ni de dinero. El prompt y `question_policy`
nuevos agregan instrucciones, por lo que ese porcentaje no es el ahorro neto
del candidato ni su coste total.

Los 65.894 tokens de entrada y 1.849 de salida del ensayo previo pertenecen a
sus tres llamadas originales; no se suman otra vez los 938 de razonamiento.
No se conoce un cargo monetario. En la segunda llamada, el contexto compacto
contenía 37.096 bytes de dossier, de los cuales 22.290 eran verificación;
`all_targets` añadía 22.449 bytes. La fuente literal completa ocupaba sólo 545
bytes. Recortar el PDF no aborda la duplicación principal.

El foco más breve puede aumentar las invocaciones: el fixture del recorrido
completo ahora usa cuatro preguntas, normalmente cinco consultas incluyendo la
aplicación final. La primera pregunta histórica reunía cinco datos de tres
ámbitos. Se favorece una carga comprensible por pregunta, sin prometer menor
consumo total. Los reintentos y correcciones tampoco están limitados por el
contador de seis preguntas.

Una mejora posterior puede introducir referencias provider-only para objetos
canónicamente idénticos de fuentes y snapshots repetidos en historia/turnos,
siempre con restauración exacta obligatoria antes de admitir un envío. Esa
optimización requiere un contrato y evaluación separados: preservar bytes
no demuestra que el modelo comprenda igual las referencias. No se elimina el
reporte de verificación ni la historia en este cambio.
