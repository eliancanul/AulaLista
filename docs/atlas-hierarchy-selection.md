# Selección explícita de jerarquía en Atlas

`AtlasIndex.retrieve`, `AtlasIndex.retrieve_for_claim` y los recuperadores
`BM25AtlasRetriever` / `ExactMatchAtlasRetriever` admiten el argumento opcional
keyword-only `hierarchy_filter_mode`:

- `"prefer"` (predeterminado) conserva el contrato histórico. BM25 bonifica
  coincidencias parciales de jerarquía; ExactMatch no usa esa preferencia.
  Ninguno excluye fuentes incompatibles en este modo.
- `"strict"` exige **todas** las claves seleccionadas en `hierarchy_filter`,
  con igualdad normalizada de valores. Un fragmento sin el metadato o con un
  valor incompatible queda excluido antes del truncamiento del recuperador
  (incluida la ventana `2 * top_k`) y antes del reranking. Ambos recuperadores
  aplican la misma restricción. No se completan resultados con otros grados,
  fases, fuentes o índices.

Ejemplo con los valores de jerarquía declarados por los fragmentos del índice:

```python
receipt = atlas.retrieve(
    "lectura de mapas",
    top_k=3,
    hierarchy_filter={"grado": "3°", "fase": "Fase 4"},
    hierarchy_filter_mode="strict",
)
```

La selección no determina ni infiere el grado de un texto. Las claves son
exactas (`grado`, `fase`, etc.); sus valores usan la normalización léxica de
Atlas (mayúsculas, acentos, puntuación y espacios). No hay equivalencias
curriculares inferidas entre, por ejemplo, `tercero` y `3°`. El llamador debe
usar los metadatos declarados por su fuente. `None` o `{}` significa que no
hay claves seleccionadas y, por tanto, no hay restricción. Claves/valores
vacíos o valores no textuales en una selección estricta, y modos desconocidos,
producen `ValueError`; nunca degradan silenciosamente a `prefer`.
Las claves adicionales declaradas por una fuente también se exigen si el
llamador las selecciona; no hay una lista cerrada de niveles admitidos. Elegir
sólo `grado` no exige ni infiere una `fase`, ni a la inversa.

Si no hay coincidencia léxica compatible, el recibo contiene `candidates=[]`,
`is_empty=True` y `total_candidates_found=0`. Un resultado incompleto puede
contener menos de `top_k` candidatos. BM25 conserva las estadísticas del índice
existente y su bonificación de jerarquía; el cambio restringe elegibilidad,
no recalibra los puntajes ni crea un índice nuevo por grado.

## Afirmaciones y auditoría

En `retrieve_for_claim(..., hierarchy_filter_mode="strict")` sólo son
obligatorias las claves elegidas explícitamente por el llamador. El campo,
escenario o metodología que una afirmación propone no se convierte por sí
mismo en condición de inclusión: hacerlo podría eliminar contraevidencia
antes de contrastarla. Si se incluye esa clave explícitamente, sí se exige.
En `prefer` se conservan las pistas derivadas del predicado y el reranking
anterior. En ambos modos, el estado de la afirmación permanece intacto.

El recibo y su serialización declaran `hierarchy_filter` (selección efectiva)
y `hierarchy_filter_mode`. La identidad del recibo distingue `strict` de
`prefer`, incluso si los candidatos coinciden o ambos resultados están vacíos;
los IDs históricos de `prefer` se conservan. Fuente, página, región, ID de
fragmento y versión del índice no se sustituyen ni fusionan. Los manifiestos
conservan las versiones de las fuentes y forman parte del hash del índice.

Los recuperadores personalizados con la firma anterior siguen funcionando en
`prefer`. Para admitir `strict`, deben implementar el nuevo argumento y filtrar
antes de truncar; una firma incompatible falla explícitamente, sin reintento
en modo permisivo. El contrato del reranker sigue siendo reclasificar los
candidatos recibidos, sin añadir fuentes nuevas.

Como comprobación defensiva, el índice verifica en `strict` todos los candidatos
que devuelve el recuperador antes del reranking, y toda la salida del reranker
antes del `top_k` final. Si cualquiera devuelve un fragmento incompatible o sin
un metadato seleccionado, lanza `AtlasRetrievalContractError` e identifica la
etapa que incumplió el contrato. No emite un recibo estricto ni elimina el
candidato silenciosamente para disimular la violación, incluso si estaba fuera
del `top_k` final o apareció como fallback tras una recuperación vacía.

Esta defensa no demuestra que un recuperador personalizado haya buscado todos
los fragmentos compatibles: tampoco puede recuperar evidencia que ya omitió.
El filtrado previo al truncamiento sigue siendo obligatorio dentro del
recuperador. La comprobación no cambia el comportamiento histórico de `prefer`
ni convierte los componentes personalizados en un entorno aislado de seguridad.

## Alcance y comprobación

No cambia los candados de permiso, licencia, versión, identidad o SHA-256 para
registrar fuentes. No habilita libros reales ni acredita precisión pedagógica;
recuperar un fragmento sigue sin equivaler a respaldo de una afirmación.
La selección es optativa en API: no se añade interfaz ni se cambia el modo
de los llamadores existentes.

Las pruebas nuevas usan textos y manifiestos inventados, marcados como
sintéticos, sin atribuirles permisos sobre libros reales:

```sh
python -m pytest -q tests/test_t125_atlas_strict_hierarchy.py tests/test_t125_atlas_retrieval.py
# Compatibilidad con los consumidores existentes de recibos (sin modelos reales):
python -m pytest -q tests/test_t126_tribunal_nli.py tests/test_t127_selective_orchestrator.py
```

Cubren ambos recuperadores y entradas, `top_k=1`, más de `2 * top_k`
distractores, selección de un solo nivel, conjunción de todas las claves,
metadatos faltantes, selecciones imposibles o malformadas, claves exactas,
normalización, texto idéntico con procedencias distintas, recibos, ausencia de
estado compartido entre consultas, reconstrucción determinista, ambos
rerankers, contraevidencia conservada, operación sin red, el modo anterior y
los candados de registro. Incluyen dobles que ignoran el modo estricto o
reintroducen candidatos incompatibles desde el reranker para verificar que el
índice falla explícitamente en ambos límites.
