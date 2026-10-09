# Transporte físico opt-in de estructura

`semantic-v2-values-spans` es un modo de transporte experimental explícito de
`AULALISTA_TEACHER_REVIEW_CONTEXT_MODE`. Este cambio no lo activa ni modifica la
configuración, `semantic-v2`, `semantic-v2-values`, `TABLE_SYSTEM`, la guía de
valores citados, el contrato de salida o los controles del backend.

Se aplica **después** de `encode_table_context`. Si no ahorra bytes netos, devuelve
exactamente el sistema y payload de `semantic-v2-values`, sin instrucciones
adicionales. El ahorro debe existir tanto en UTF-8 directo como al escapar el
contenido dentro de otro JSON, incluyendo la guía de transporte. Los límites de
solicitud final de cada adaptador siguen vigentes.

## Contrato `physical-spans-v1`

`_structure_transport` contiene la versión, `fragment_attributes` y
`block_columns`. Sólo se transforma información bajo
`dossier.sessions[*].source_structure` y `dossier.annex_candidates`.

- `{"$fragment":[a,p,s,e]}` representa el objeto exacto de atributos de la fila
  `a`, más `page_number=p`, `text_start=s`, `text_end=e` y `excerpt` igual al slice
  literal `text[s:e]` de la única página física cuyo `page_number` es `p`.
- `p` **no** es el índice del array. Los offsets son índices de codepoints de
  Python, desde cero y con final exclusivo. No son bytes UTF-8 ni unidades UTF-16.
  No se busca texto ni se corrigen offsets, saltos de línea o normalización Unicode.
- Sólo se convierte un fragmento cuyo excerpt coincide exactamente con ese
  rango. Los índices son enteros estrictos, sin booleanos. Si existe SHA de
  documento o fuente, debe corresponder a la fuente propia (incluida su referencia
  v2). Los fragmentos ajenos, no exactos, de página desconocida o ambigua y los
  rangos entre páginas permanecen literales.
- Los atributos son objetos completos compartidos por identidad JSON canónica.
  Conservan ausencia/presencia de SHA, role, reason, null, tipos y futuras claves;
  no hay defaults ni herencia. Los marcadores de v2 permanecen para su propio decoder.
- Sólo un bloque con las nueve claves exactas se convierte a `{"$block":row}`:
  block_id, role, text, phase_id, parent_id, evidence, origin, status, review.
  Un texto idéntico a un excerpt verificado de su propia evidencia puede usar
  `{"$excerpt":n}`. Un texto unido, modificado o perteneciente a otro bloque queda
  literal. Bloques con claves adicionales o ausentes conservan su forma de objeto.
- Toda la fuente por página permanece literal e inline; no se elimina ninguna
  página, rol, estado o revisión. Tampoco se infiere autoridad de una cita localizada.

`restore_structure_context` devuelve el **payload v2**, no el dossier ni la
proyección semántica. Después se puede aplicar `restore_table_context`. Antes de
admitir la compactación, el encoder comprueba round-trip canónico exacto y ausencia
de mutación. El contexto original sigue siendo la entrada de validación del backend.

El decoder rechaza versiones, columnas, formas y referencias inválidas, booleanos
como índices, colisiones reservadas incluso anidadas, atributos duplicados/sin
uso y referencias fuera de los ámbitos permitidos. Serializa la expansión de
forma acotada antes de materializar copias independientes. Su presupuesto por
defecto es 16 MiB, configurable con `max_expanded_bytes`; el encoder usa el tamaño
canónico conocido de la entrada v2. Superar el límite falla sin recortar datos.

## Pruebas y medición exclusivamente sintéticas

Los tests públicos nuevos prueban encode/restore, selección central y los tres
wrappers offline: ejecutables inventados para Pi/Luna y captura inventada para
Gemini. No hay conexión, inferencia, credenciales, caché ni reintentos nuevos.

```sh
python -m pytest -q tests/test_teacher_review_structure_context.py \
  tests/test_teacher_review_task_context.py tests/test_teacher_review_table_context.py \
  tests/test_teacher_review_quote_values.py tests/test_learning_purpose.py
```

La función `structure_fixture()` del test crea 32 bloques y dos fragmentos de
anexo ficticios, con emoji astral, NFD, CRLF y metadatos futuros. En este fixture:

| Componente variable de la solicitud | v2-values | spans con guía |
| --- | ---: | ---: |
| Bytes UTF-8 directos | 25.808 | 17.899 |
| Bytes tras escape JSON | 28.377 | 19.597 |

El payload compacto solo mide 17.232 bytes y la guía 667 bytes. La comparación
incluye esa guía; el sistema base y demás envoltura idénticos se cancelan. No son
bytes de red ni medidas de tokens, costo o calidad. La reversibilidad prueba
conservación, no equivalencia de razonamiento de un modelo. Una evaluación de
calidad o activación requiere autorización separada.
