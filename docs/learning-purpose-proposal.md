# Propósito de aprendizaje propuesto con evidencia

## Decisión y alcance

La revisión puede proponer el propósito del alumnado en la **misma respuesta del
modelo que prepara la siguiente pregunta**. No añade otra llamada, transporte,
modelo, nivel de razonamiento ni habilitación de consultas reales. El máximo de
seis preguntas y el guardado previo de respuestas permanecen en vigor.

El corte se limita a `general.proposito` vacío, sin corrección humana. Conserva
un propósito explícito existente aunque no tenga producto o evaluación. No
reclasifica una finalidad como extracción literal de propósito y no propaga un
propósito general a sesiones o actividades.

## Contrato público

`assess_learning_purpose(candidate, source_document)` es una función sin efectos
externos. Devuelve `decision=proposed|abstained`, valor o `null`, citas verificadas,
regla, resultados de sus condiciones, incidencias y explicación legible.

El output del turno añade `purpose_proposal`, un objeto o `null`:

- `action`: infinitivo de una acción del alumnado en español, hasta 40 caracteres
- `content`: frase literal de contenido presente en la fuente, hasta 240 caracteres
- `scope_id`: ámbito suministrado en `purpose_policy`, no creado por el modelo
- `evidence`: referencias `{role,page,quote}`; roles `action`, `content`, `product` o `assessment`
- `counterevidence`: referencias de evidencia contraria, con la misma forma

Cada lista admite hasta ocho referencias y cada cita hasta 800 caracteres. Las
citas mantienen sujeto, negación y procedencia. El backend construye el enunciado
`Action content.`; sigue siendo una **formulación inferida**, aunque reutilice
palabras de la fuente. No acepta un ensayo libre que añada habilidades, métodos,
grados o estándares sin referencia.

El esquema de nuevas respuestas requiere el campo nullable. El runtime también
acepta las respuestas históricas de tres campos, sin propuesta. Los modos
`complete`, `semantic-v1`, `semantic-v2` y `semantic-v2-values` conservan la política
y las mismas instrucciones de autoridad.

## Regla del prototipo

`A & C & (P | E) & I & S & !X`

- **A**: acción atribuible al alumnado, no únicamente a la persona docente
- **C**: contenido literal relacionado con esa acción en una afirmación citada
- **P/E**: producto o evaluación relacionado textualmente con la acción/contenido
- **I**: dos afirmaciones fuente independientes; recortes, cambios de puntuación,
  líneas de una misma oración y repeticiones no crean apoyos nuevos
- **S**: primer proyecto anclado en la fuente, con una intención general y apoyo
  de como máximo una unidad numerada; no mezcla fases, momentos ni sesiones
- **X**: contraevidencia declarada o señales textuales de negación/incertidumbre,
  incluidas algunas formulaciones nominales, dentro del ámbito del proyecto

No es una ecuación de probabilidad, un score calibrado ni validación pedagógica.
Una cita localizada sólo acredita localización. La relación entre propósito,
contenido y actividad sigue pendiente del juicio docente.

La regla trata las acciones de producción con especial cautela: elaborar un
artefacto no basta por sí solo. Una producción puede expresar aprendizaje (por
ejemplo, elaborar una argumentación) cuando la evaluación la respalda como
habilidad. Esto es un filtro del candidato, no una definición universal de qué
acciones pueden ser aprendizaje.

### Límites conocidos

La identificación de sujetos, flexiones verbales, demostraciones y
contraevidencias es heurística y conservadora en español. No cubre toda sintaxis,
formas irregulares, paráfrasis o contradicción semántica. La proximidad física al
encabezado de proyecto se etiqueta como interpretación que requiere revisión,
no pertenencia curricular confirmada. La propuesta no cubre proyectos posteriores,
objetivos únicamente locales de una unidad ni OCR o comprensión visual. Texto no
extraído puede ocultar información relevante; no se afirma haberlo comprendido.

El contexto íntegro conserva las páginas y sus advertencias. Una abstención no
significa que el PDF carezca de propósito: significa que este candidato no pasó
las condiciones de este prototipo. El proveedor puede plantear una pregunta
acotada sobre lo que siga sin resolverse, dentro del presupuesto existente.

## Persistencia y autoridad

Una propuesta conserva `origin=proposed`, `status=ambiguous` y `review=pending` en
`InterpretedField`. Las `SourceReference` citan afirmaciones literales completas,
con sus páginas; se deduplican por afirmación y agrupan roles legibles. La
explicación muestra acción, contenido, demostración, páginas y regla aplicada.
No atribuye el texto inferido como cita literal del propósito.

La revisión conserva la evaluación estructurada, SHA de fuente, versión y fecha.
El historial del dossier registra antes/después y origen de propuesta. La
aplicación vuelve a comprobar el campo después de las respuestas humanas y dentro
de la transacción de revisión: una respuesta/corrección humana o un valor ya
existente prevalecen. Los fallos conservan respuestas y recibos previos.

La propuesta no confirma evidencia ni aprueba o publica. La aprobación existente
requiere la confirmación humana de revisión, incluida la aceptación explícita de
los elementos todavía pendientes. Abrir o recargar la pantalla no genera otra
consulta ni otra pregunta.

## Verificación reproducible, sin modelo real

Los tests usan fuentes sintéticas, PDFs generados y un proveedor doble declarado.
No prueban calidad de Luna ni constituyen evaluación pedagógica del PDF real.

- `tests/test_learning_purpose.py`: contrato y regla; caso implícito válido;
  citas inventadas, sujeto docente antes/después del verbo, producto decorativo,
  incertidumbre/contraevidencia nominal, recortes y saltos de línea, fases,
  sesiones, proyectos y encabezados legados sin dos puntos
- `tests/test_teacher_review_learning_purpose.py`: importación y formulario HTTP;
  una respuesta prepara propuesta sin pregunta adicional; reapertura; propósito
  explícito intacto; prioridad de respuesta humana y aprobación humana obligatoria
- La regresión `tests/test_teacher_review*.py` verifica respuestas, contextos,
  codecs, adaptadores, límites, concurrencia e historial previamente existentes

Comando focal: `python -m pytest tests/test_learning_purpose.py tests/test_teacher_review_learning_purpose.py -q`.

## Revisión o corrección directa en la misma caja

El enlace visible «Revisar o corregir propósito» abre una propuesta de la fuente
actual en la caja existente. Mientras se revisa el propósito, la pregunta
pendiente se conserva; no aparece una segunda caja ni se consume otra pregunta.

La revisión requiere una confirmación explícita del texto mostrado. Si cambia,
se guarda como `teacher_entered/corrected`, preservando propuesta original,
citas y deltas de historial. Si se conserva, la confirmación humana marca ese
campo `confirmed` sin reclasificarlo como extracción literal. Ninguna opción
aprueba o publica la planeación ni invoca un proveedor.

El borrador del propósito utiliza una entrada separada del guardado existente,
con control de época, versión y fuente. Reabrir conserva el texto; «Volver sin
cambiar» descarta sólo ese borrador. La pregunta pendiente, su borrador y las
respuestas anteriores permanecen intactos. El backend rechaza envíos sin
confirmación, obsoletos o con un recibo reutilizado para otro texto. La repetición
del mismo envío es idempotente. Se conserva también el texto literal de la
revisión humana, incluso cuando el campo normaliza espacios externos.

Los límites de unidades reconocen también marcadores como `Fase #1`,
`Fase # 1`, `Sesión #1` y `Momento # 1`. El marcador no vuelve compatibles dos
unidades diferentes. La variante con una sola unidad y una intención general
sigue siendo candidata a propuesta; estos límites no crean sesiones declaradas.

Los envíos rechazados por conflicto conservan un respaldo de texto en la sesión
del navegador, separado del respaldo de una pregunta. Guardar o descartar un
destino no limpia el del otro. Si la fuente física cambia antes del envío, se
bloquea la aplicación y se muestra el texto conservado en una vista de sólo
lectura; no se ofrece guardar ni aprobar sobre una fuente sin verificar.
Cuando una reextracción deja válida una fuente distinta, el respaldo anterior
sigue accesible mediante recuperación de sólo lectura desde la página principal.
No se precarga ni se aplica como corrección de la nueva fuente.

## Propuesta rechazada y respuesta sin pregunta

Una propuesta cuya cita no es literal o cuya evidencia es insuficiente permanece
rechazada. No se completa el campo ni se relaja la comprobación. El rechazo y el
recibo de la consulta quedan conservados, incluido el consumo que el proveedor
haya contabilizado; rechazo no equivale a consumo cero o desconocido.

Si la respuesta trae `question=null` y todavía hay datos obligatorios sin
resolver, el estado pasa a `needs_input`. Recargar o repetir `continue` no envía
otra solicitud. Los registros anteriores guardados como `limited` o `complete`
con obligatorios pendientes reciben la misma vista de recuperación, sin escribir
ni volver a consultar por un GET.

El propósito vacío, nulo o ausente puede completarse en la caja manual existente.
La caja inicia vacía, sin insertar el texto rechazado ni el marcador `None`.
Guardar exige confirmación humana y conserva borradores, citas previas válidas,
historial y recibos. El valor nuevo es `teacher_entered`, no extracción ni una
propuesta aceptada retrospectivamente. Si resuelve el último obligatorio, vuelve
al estado normal de revisión, sin aprobar ni publicar.

Cuando quedan otros datos obligatorios y hay cupo, «Pedir otra pregunta» es una
acción explícita separada. El aviso informa que enviará la planeación y las
respuestas al modelo configurado e iniciará otra consulta. Guardar propósito,
abrir, recargar y los envíos duplicados no ejecutan esa acción. Se vuelven a
comprobar propiedad, fuente, versión, revisión, generación activa y los STOP de
transporte o consumo sin conciliar. Al agotar seis preguntas no se muestra ni se
admite esta acción; se conservan los pendientes y las vías de edición existentes.
