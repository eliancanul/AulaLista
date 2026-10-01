# Títulos y objetivos: límites de portada y evidencia física

Trabajo acotado de [#139](https://github.com/eliancanul/AulaLista/issues/139),
posterior a [#138](https://github.com/eliancanul/AulaLista/pull/138), sobre
`a2c6d1c3ac7d4777d2fa57a50d2f93e0717bfdcd`.

## Problemas reproducidos

- Un título con salto de línea se cortaba aunque su estado fuera `supported`.
- Propósito y finalidad explícita podían absorber Producto, Evaluación o Campo.
- Una etiqueta vacía podía consumir el encabezado siguiente como su valor.
- La búsqueda sobre páginas concatenadas unía fragmentos de páginas distintas.
- Palabras como «propósito» dentro de prosa podían crear un campo explícito falso;
  palabras al inicio de una línea podían cortar un objetivo sin ser encabezados.

## Cambio de producto

`curriculum/overview_fields.py` reconoce etiquetas completas y límites físicos.
Trabaja en cada una de las tres primeras páginas por separado, conservando las
subcadenas originales, sin localizar la página mediante un prefijo reconstruido.
El intérprete usa este módulo exclusivamente para `proyecto`, `proposito` y
`finalidad` **explícita**.

Se distinguen etiquetas con dos puntos o aisladas, separadores tabulares y unas
filas de metadatos sin puntuación compatibles con el formato existente. Estas
últimas requieren valores completos y corroboración estructural; si tienen prosa
libre a continuación, se preserva el bloque y se marca ambiguo. Para delimitar
un objetivo ante filas sin puntuación se exige también un cierre de oración
previo. Esta regla es conservadora y puede aumentar la revisión de formatos
inciertos; no mide ni promete una reducción del trabajo humano.

Un título multilinea se conserva completo como candidato ambiguo cuando su
alcance no es inequívoco. Las comillas sólo cierran un título si no queda un
sufijo: `"Guardianes" de nuestra comunidad` conserva todo su texto. Una línea en
blanco puede separar el título del bloque posterior, pero no convierte una
frase que termina en preposición en un título completo.

Ejemplos sintéticos de comportamiento:

| Entrada | Resultado |
|---|---|
| `Proyecto: Guardianes de` + salto + `la comunidad` | Candidato completo, pendiente por ambigüedad |
| `Propósito: Observar plantas.` + salto + `Producto: Herbario` | Propósito delimitado, cita literal de su página |
| `Propósito:` + salto + `Producto: Herbario` | Propósito ausente |
| Texto de un objetivo que continúa en otra página | Sólo el fragmento localizado, ambiguo; no se unen páginas |
| Una fila aparente `Campo Lenguajes` dentro de prosa partida | Se conserva el bloque para revisión |

Todas las revisiones permanecen `pending`. No cambia aprobación, publicación,
activación, progreso curricular, esquema de dossier ni contrato agregado de
claims. La finalidad implícita y los campos/asociaciones de sesiones conservan
sus rutas anteriores. No se añadió un proveedor ni una llamada a modelos al
importador.

## Evidencia reproducible

Las pruebas se escribieron como ejemplos de desarrollo. **No son holdout ni
referencia humana independiente.** Las primeras 49 reprodujeron 43 fallos antes
del cambio y 6 pases. Las pruebas negativas adicionales surgieron de revisión
adversarial y forman parte del mismo conjunto de desarrollo.

- 83 pruebas específicas pasan, incluidos campos vacíos, prosa, títulos citados,
  Unicode/CRLF, columnas, advertencias, páginas y roundtrip de un PDF sintético
- 176 regresiones dirigidas pasan, con 8 omitidas por fuentes opcionales
- La revisión independiente reprodujo y cerró los cortes residuales por comillas
  y filas sin puntuación antes de la publicación
- Django `check`, deriva de migraciones, sintaxis y `git diff --check` pasan
- La suite completa y CI deben comprobarse contra el commit exacto del PR; los
  tests dirigidos no se presentan como sustituto de esa ejecución

El control C01 existente conserva 5 páginas, 2 sesiones, 21 comprobaciones
textuales, 31 pendientes, 0 bloqueadas y 52 elementos en total. Su SHA-256 es
`33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648`.
No se repitió la campaña de veinte PDFs; la referencia histórica de IA no permite
atribuir validación docente ni medir aquí precisión semántica.

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pytest -q tests/test_overview_field_boundaries.py
python -m pytest -q
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Límites y siguiente trabajo

- Se usan señales de texto plano, sin geometría de tablas ni clasificación
  semántica. Formatos desconocidos y columnas separadas sólo por un espacio
  pueden quedar como candidatos ambiguos
- Una comilla sin cerrar antes de las etiquetas puede ocultarlas. Es una pérdida
  conservadora de extracción pendiente de resolver, no una afirmación respaldada
- `SessionPlan.project_title` aún usa su parser previo. Su alineación con el
  título general exige representar también incertidumbre y relaciones; este
  cambio no altera silenciosamente las asociaciones existentes
- La corrección no declara que un título/objetivo sea pedagógicamente correcto
  ni que los documentos históricos formen una evaluación independiente

Este código y sus fixtures fijan una regresión para revisiones futuras. Evaluar
calidad y trabajo humano requiere documentos autorizados independientes, una
referencia adjudicada y denominadores que incluyan ausencias y abstenciones.
