# Entrada semántica experimental para revisión docente

Estado: candidato OFF por defecto para A/B. No acredita un ahorro de tokens ni
igualdad de respuestas del modelo. No cambia el candidato anterior en uso.

## Activación y reversión

`AULALISTA_TEACHER_REVIEW_CONTEXT_MODE=complete` es el valor predeterminado y
conserva el codec completo/reversible anterior. Sólo `semantic-v1` activa esta
proyección. Un valor desconocido falla antes de enviar el prompt. Volver a
`complete` restaura la representación anterior; no hay migraciones ni cambios a
la base, las respuestas guardadas, el dossier o su historial.

La variable no habilita llamadas, credenciales o proveedores. Mantén las tres
variables LIVE apagadas durante instalación/pruebas locales. Una prueba real
requiere la autorización y el runtime aislado vigentes de ese ensayo; este
paquete y los permisos de ensayos históricos no los sustituyen.

## Contrato teacher-review-task-v1

Este modo es una proyección de tarea, no una compresión reversible del dossier
entero. El dossier persistido permanece íntegro. La salida se valida y aplica
contra el contexto completo original por el backend existente.

Se envía:

- `source_document` íntegro y literal: hash, páginas físicas en orden, texto,
  páginas sin texto, límites de extracción y ausencia de OCR.
- Todos los campos generales y de todas las sesiones, con valor actual y
  original, origen, status, review, reason, original_reason y citas completas.
- Identidad, títulos, contexto y anclas de proyecto/sesión; selección, páginas,
  continuidad, limitaciones de layout; actividades y asociaciones con anexos.
- Candidatos de anexos y sus páginas, menciones y estados. No se confirman solos.
- Política de preguntas, contador y presupuesto. Todos los destinos candidatos,
  más los destinos de preguntas históricas que aún existen, con su vinculación
  exacta de scope/session_id/field_name/reference_id.
- Cada pregunta, respuesta actual y todas sus versiones literales con tiempos y
  hash de fuente; skipped, pending_processing y eligible_targets calculados por
  el backend. `applied` conserva destino/cita/versión, sin repetir snapshots.
- Destinos históricos retirados explícitamente en `unavailable_target_ids`, sin
  hacerlos elegibles ni bloquear preguntas actuales tras reextracción.
- Fallos duros del verificador y diagnósticos no redundantes de revisión. Una cita
  localizada que no respalda el valor o la sesión continúa siendo visible.

No se repiten:

- Historial administrativo completo, actores, timestamps generales y snapshots
  before/after: su efecto de autoridad ya está incorporado en eligible_targets,
  mientras el backend sigue consultando los originales al validar/aplicar.
- Acciones y mensajes de UI derivados (`action_required`, `current_action`),
  nombre de campo cuando es exactamente la clave del mapa y estado operativo
  derivado del campo. Unknown fields se conservan, no se descartan por defecto.
- Reporte mecánico `checked` ni avisos de cola que se derivan de OperationalItem.
- Un aviso de campo vacío sólo puede omitirse si coincide exactamente con el
  esquema, path, scope, status, mensaje y details esperados del verificador, el
  campo realmente está vacío y no hay cita ni metadatos físicos. Cualquier clave,
  mensaje, detalle extra, campo ausente o incertidumbre nueva conserva el aviso.

No se fusionan sesiones con texto igual ni se reasigna una cita por similitud.
No hay referencias genéricas `$value_ref` ni caché de proveedor en este modo.
JSON no finito, tuples y claves no textuales fallan antes de transmitir.

## Evidencia offline y límites

Se prepararon los tres contextos históricos del PDF sintético de dos páginas.
Cada export y su identidad original se verificaron con el auditor existente.
El panel conserva los contextos/respuestas históricas y añade la política actual.
No predice cuántas preguntas o llamadas hará un recorrido adaptativo nuevo.

| Contexto histórico | Complete actual, bytes | Semantic-v1, bytes |
|---|---:|---:|
| 1 | 64.361 | 19.153 |
| 2 | 66.416 | 20.745 |
| 3 | 73.431 | 29.874 |
| Total | 204.208 | 69.772 |

Son bytes UTF-8 del request serializado incluyendo SYSTEM y esquema. Frente a
los 239.222 bytes originales son aproximadamente 70,83% menos bytes. Esto NO es
70% menos tokens. No había tokenizer local verificado y no se descargó ninguno.
Los 67.743 tokens históricos siguen siendo el baseline real; la meta del recorrido
comparable es como máximo 20.322 tokens totales, contando todas sus llamadas.
No se han medido tokens nuevos, costo o calidad con un modelo en este candidato.

## Preparar el panel offline en Mac

En un checkout separado del candidato que ya se está validando, aplica el patch
del experimento sobre la versión completa anterior, o el combinado desde la base
exacta indicada en el manifest. Usa el entorno Python del proyecto.

```sh
python -m pytest -q tests/test_teacher_review_task_context.py tests/test_teacher_review_ab_scoring.py
python scripts/teacher_review_ab.py prepare --evidence /ruta/export-autorizado --output /ruta/panel-offline
```

El comando sólo verifica archivos y escribe seis requests de panel (tres por
modo) más métricas/hashes. No autentica, no llama modelos ni concede presupuesto.
No sumar el consumo de un panel fijo para afirmar éxito del recorrido adaptativo.

## Comparar el recorrido completo después del ensayo autorizado

Conserva en cada run el mismo esquema de export: validation-summary.json,
validation/real-validation-plan.json, PDF sintético, initial/final-dossier.json,
context-1.json, final-review-state.json y TODAS las carpetas de attempts con sus
recibos. No omitas intentos rechazados, fallidos o de consumo incierto. Un run
incompleto no se convierte en cero ni en una reducción favorable.

```sh
python scripts/teacher_review_ab.py compare --baseline /ruta/baseline --candidate /ruta/candidato --output /ruta/comparacion.json
```

El comparador verifica fuente, estado inicial y autoridad (incluido historial),
texto de fuente y turnos iniciales, ruta/modelo/esfuerzo solicitados, mismo banco
congelado de respuestas, hechos realmente suministrados y resultado semántico
final. Sólo acepta respuestas del banco literal, solas o con las etiquetas
exactas de sus destinos; una respuesta libre no autorizada exige revisar la
comparabilidad. No sustituye una revisión docente ni de calidad de preguntas.

Cuenta `totalTokens` de cada recibo completo de todos los intentos, comprueba sus
sumas y no vuelve a sumar reasoning. Compara los 67.743 con la suma completa del
nuevo recorrido, nunca con bytes ni sólo una llamada. Recibos/modelos/rutas
inconsistentes o consumo desconocido hacen el resultado inconcluso. Un nombre
remoto sólo se informa cuando aparece en recibos, sin llamarlo atestación
independiente del modelo.

Para aceptar «manteniendo resultados», además de la comparación mecánica, revisa:

1. Las cinco carencias necesarias del fixture quedan resueltas con las mismas
   citas humanas exactas y en las mismas sesiones; fuente/citas originales intactas.
2. No aparecen confirmaciones autónomas de anexos, datos inventados, aprobación,
   publicación ni sesiones de aula. La aceptación pedagógica sigue siendo humana.
3. Preguntas breves, adaptativas, de un grupo coherente, como máximo tres destinos
   y seis preguntas. No vuelve a pedir datos ya respondidos ni opcionales en bloque.
4. Correcciones y saltos conservan texto literal y elegibilidad; una edición
   humana independiente o nueva fuente no vuelve a autorizar respuestas anteriores.
5. El último resultado cierra cuando corresponde. Abrir/refrescar/repetir un
   avance ya cerrado no genera otra llamada; esta protección ya existía y tiene
   una regresión específica del modo semántico.

Un buen resultado en este fixture expuesto no demuestra rendimiento general con
PDFs reales. En documentos grandes, el texto fuente íntegro puede dominar el
costo y hacer imposible el 70% sin cambiar otro componente o el contrato.
