# semantic-v2: tablas tipadas, candidato para ensayo

Estado: OFF por defecto. `complete` y `semantic-v1` conservan su comportamiento.
Sólo `AULALISTA_TEACHER_REVIEW_CONTEXT_MODE=semantic-v2` selecciona el nuevo formato;
no habilita LIVE, autenticación, reintentos ni publicación.

## Punto de partida medido

El ensayo semantic-v1 del mismo PDF sintético completó cuatro preguntas y cinco
llamadas: 26.759 tokens de entrada y 992 de salida, 27.751 totales declarados por
los recibos Pi. Modelo solicitado `gpt-6-luna`, esfuerzo high; identidad remota no
informada. El baseline original es 67.743; la meta sigue siendo ≤20.322 totales.
Se conserva este denominador, no se sustituye por el baseline posterior de 86.408.

La quinta llamada aplica la última respuesta humana y termina. No se eliminó:
retirarla sin interpretar y validar esa respuesta alteraría el resultado. La
protección existente evita llamadas adicionales una vez cerrado el recorrido.

## Contrato de representación

`teacher-review-task-v2` reconstruye canónicamente TODA la proyección semantic-v1
antes de permitir el envío. No es otra selección de información: fuente, valores
actuales/originales, incertidumbre, diagnósticos, historial de respuestas, citas y
asociaciones son los mismos. El dossier persistido y el backend permanecen íntegros.

- `source_document` permanece completo, literal e inline.
- Campos con exactamente el esquema conocido se representan como
  `[estado, ...valores]`. `state_columns` y `field_states` definen el estado;
  `value_columns` y `value_defaults` definen cada valor. Sólo se omiten celdas
  finales que coinciden canónicamente con el default explícito, distinguiendo
  null, vacío, false, cero, listas y objetos. Campos con claves distintas quedan
  como objetos completos.
- Citas completas idénticas comparten catálogo mediante `{"$cite":N}`. Sus defaults
  son explícitos; hashes distintos, páginas, roles, regiones y etiquetas distintas
  no se fusionan.
- Contextos de proyecto completos idénticos comparten `{"$project":N}`; los anclajes
  y la incertidumbre permanecen. No hay ciclos ni resolución externa.
- `{"$source":true}` repite exactamente el SHA inline de `source_document`. Otros
  hashes permanecen explícitos. Se usa sólo cuando el valor original coincide.
- `all_targets` usa filas y `target_columns`. Los controles `*_indices` apuntan a
  esas filas desde cero. Sólo los destinos históricos declarados retirados admiten
  IDs literales; nunca se vuelven candidatos ni elegibles por esta codificación.
- La respuesta del modelo usa SIEMPRE IDs originales, no posiciones. No hay
  remapeo de respuesta ni modificación del esquema; el backend original rechaza
  índices o destinos inválidos.
- En versiones de respuestas, `answer_is_current=true` repite exactamente la
  respuesta actual del turno y `source_is_current=true` su hash de fuente actual.
  Las versiones distintas se conservan literales, incluidos tiempo y fuente.

Un roundtrip exacto falla ante una pérdida de datos. Marcadores desconocidos,
colisiones, bool/float como índice, rangos inválidos, ciclos, defaults/columnas
incorrectos o referencias en estados se rechazan. La expansión se comprueba por
stream antes de materializar copias independientes: el encoder conoce el tamaño
original; el decoder independiente usa 16 MiB salvo presupuesto explícito.

El SYSTEM v2 es más compacto y pide la pregunta en español. Conserva las reglas
sobre datos no confiables, todas las sesiones/páginas, incertidumbre, citas
literales actuales y último turno por destino, saltos, correcciones, límites de
preguntas, anexos, autoridad humana y prohibición de publicación. Su equivalencia
de comportamiento requiere el ensayo real; el roundtrip no demuestra comprensión
por el modelo de tablas e índices.

## Replay offline de los cinco requests reales

Los 111 archivos del export fueron verificados contra su inventario. El auditor
reconstruye los SHA originales de cada request, vincula contexto completo y
proyección semantic-v1, verifica el PDF y exige restauración v2 exacta.

Total de requests serializados UTF-8:

- semantic-v1 real: 106.421 bytes
- Contrafactual v2 de los mismos cinco contextos: 75.455 bytes
- Diferencia: 29,10% adicional en bytes

Estas cifras incluyen SYSTEM, esquema y envoltorio. NO son tokens, ni una
predicción del nuevo recorrido. No se ejecutó inferencia nueva, ni hubo tokenizer
local verificado. La meta de ≤20.322 tokens continúa pendiente del ensayo real.

## Usar el paquete en Mac

En un checkout separado del candidato v1, aplica `semantic-v2.patch` sobre el
candidato semantic-v1 identificado en el manifest. Alternativamente, aplica el
patch combinado desde la base exacta 5c93fb661d17768414449f65daaf77fbbd9d2791.
Nunca apliques ambos. No se requieren migraciones.

```sh
python -m pytest -q tests/test_teacher_review_table_context.py
python scripts/audit_teacher_review_tables.py --evidence /ruta/export-v1 --output /ruta/replay-v2
```

El auditor sólo lee evidencia y escribe métricas/requests de panel. No autentica,
no llama modelos ni concede presupuesto. El ZIP de evidencia v1 es
`AulaLista-semantic-v1-Mac-AB-27751-tokens.zip`, 427.593 bytes, SHA-256
`c6bb75b834711dcf7845900d6bc600a931872683842460703cc61c6613e89c62`.

Para el ensayo autorizado, usar `semantic-v2` únicamente en el nuevo run aislado,
con el mismo PDF, banco de respuestas y controles del ensayo anterior. Si el
harness verifica el payload, debe comparar
`restore_table_context(payload)` con `build_task_context(contexto_completo)`;
no tratar filas v2 como objetos v1. La fuente inline puede compararse directamente.

Conservar todos los intentos/recibos y el contexto completo original por llamada.
Usar el comparador de recorridos `scripts/teacher_review_ab.py compare` sin cambiar
su denominador o controles de fuente, autoridad, respuestas y resultados. Contar
el total de todas las llamadas; no sumar reasoning de nuevo. No reutilizar un
presupuesto anterior, ocultar fallos ni reintentar automáticamente. Un rechazo
cuenta como consumo y detiene la aceptación hasta la revisión correspondiente.

La calidad de preguntas y correcciones sigue necesitando revisión independiente,
además de igualdad de resultados y consumo. Este fixture expuesto no representa
validación pedagógica ni garantiza el mismo ahorro en PDFs reales.
