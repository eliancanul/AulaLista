# Contexto compartido sin pérdida

El codec de revisión docente reduce repeticiones en el transporte. No cambia el
dossier persistido, la fuente física, las reglas de preguntas, las citas humanas,
la elegibilidad de destinos, la verificación ni la autoridad editorial.

## Contrato

1. Se conserva la codificación previa: `missing_target_ids` apunta a los registros
   completos de `all_targets`, con identidad y orden comprobados.
2. Sólo valores JSON completos canónicamente idénticos de al menos 64 bytes pueden
   compartirse. No hay resúmenes, poda de metadatos, equivalencia semántica,
   normalización de texto, rangos reconstruidos ni plantilla con campos implícitos.
3. `_context_encoding: shared-values-v1` y `_shared_values` declaran una tabla de
   valores. Un objeto cuyo único campo es `{"$value_ref": N}` representa el valor
   completo de esa posición. Los valores de la tabla no contienen referencias:
   no hay ciclos, enlaces externos ni herencia de campos o autoridad.
4. El documento por página permanece literal e inline, así como las preguntas,
   respuestas actuales, todas las versiones de respuesta, destinos y elegibilidad
   de cada turno, política de preguntas y lista de pendientes. Las sesiones,
   actividades, anexos, citas, versiones y snapshots before/after conservan todos
   sus campos y el orden de sus arrays. Sólo el orden de claves de objetos JSON
   no es parte de la identidad canónica.
5. Antes de admitir una solicitud se restauran las referencias y `missing_fields`;
   el JSON canónico debe ser idéntico al contexto interno original. El backend
   valida la salida contra ese contexto original, nunca contra la tabla compacta.
6. Se rechazan colisiones con marcadores reservados, referencias inexistentes o
   de tipo incorrecto (incluido `true` como índice), campos añadidos a referencias,
   valores compartidos duplicados/sin usar, versiones desconocidas, referencias
   anidadas, tipos no JSON y números no finitos.
7. El decoder calcula el tamaño expandido antes de copiar valores compartidos.
   Al codificar, el presupuesto es el tamaño conocido tras sustituir `missing_fields` por
   `missing_target_ids` y antes de compartir valores. El
   uso independiente del decoder tiene un presupuesto por defecto de 16 MiB,
   configurable explícitamente. No se recorta nada al superar un presupuesto.
8. La nueva representación se usa sólo cuando ahorra bytes netos incluyendo las
   instrucciones y su escape tanto en UTF-8 directo (Luna CLI) como envuelto en
   JSON (Pi/Gemini). Sin ahorro suficiente se conserva el codec anterior y no
   se añaden instrucciones. El límite de solicitud sigue aplicándose al request
   final completo de cada adaptador.

La aplicación del codec no habilita un proveedor, no solicita credenciales, no
cambia límites de ejecución, no añade caché ni reintentos y no publica contenido.

## Medición offline de las tres solicitudes históricas

Los exports corresponden a un PDF sintético de dos páginas y tres llamadas ya
completadas. Se verificaron manifiesto, SHA del PDF, identidad de cada contexto y
reconstrucción del SHA de los bytes originales de cada request. La comparación
retiene el SYSTEM histórico y añade sólo las instrucciones del codec: es un
contrafactual de representación, no una nueva ejecución ni una evaluación de la
política de preguntas integrada después.

| Llamada | Original | Sólo JSON compacto | Codec, con instrucciones |
|---|---:|---:|---:|
| 1 | 73.560 | 70.193 | 61.934 |
| 2 | 75.775 | 72.348 | 63.989 |
| 3 | 89.887 | 85.663 | 71.813 |
| Total | 239.222 | 228.204 | 197.736 |

Unidades: bytes UTF-8 del JSON serializado, no bytes de red. La reducción es
41.486 bytes (17,34 %) frente al original, o 30.468 bytes (13,35 %) adicionales
frente a compactar sólo JSON. Las tres restauraciones canónicas son exactas.
Los 65.894 tokens de entrada históricos no se usan para deducir un ahorro.
No había tokenizer local verificado en los runtimes comprobados; no se descargó
ninguno. No se midieron tokens nuevos, costo ni calidad de interpretación.

Reproducción, suministrando expresamente el export sintético autorizado:

```sh
python scripts/audit_teacher_context.py --evidence /ruta/al/export --output /ruta/al/informe
python -m pytest -q tests/test_teacher_review_context_encoding.py tests/test_teacher_review_shared_context.py
```

`measurements.json` contiene los hashes separados de exports, solicitudes
originales reconstruidas, contexto original/restaurado, candidato e identidad del
codec, además de los conteos por llamada. No contiene literales privados.

## Límites de validación

La reversibilidad exacta prueba conservación de datos, no que un modelo razone
igual al seguir referencias. La nueva representación requiere una evaluación
posterior autorizada para medir calidad y tokens reales. En particular, no se
infiere que el modelo remoto observado sea el solicitado ni que un PDF real vaya
a comportarse como el fixture. El historial sigue creciendo con las correcciones;
compartir copias idénticas no lo vuelve de tamaño constante.
