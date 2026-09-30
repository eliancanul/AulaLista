# Campos formativos: reconocimiento y evidencia física

## Alcance

Corrección de producto sobre `2541faf04bda4dad1215a4673e3802567ca7c5c9`.
No cambia el esquema del dossier, el contrato agregado de claims, las decisiones
editoriales ni la base de datos. La revisión humana permanece pendiente.

Se corrigen dos problemas deterministas:

1. La búsqueda de nombres oficiales no reconocía algunas variantes de tildes y
   Unicode. Después de reconocer mayúsculas o saltos de línea, podía atribuir una
   cita canónica inventada a la página 1. También unía fragmentos entre páginas.
2. El verificador exigía toda la lista de campos en cada página individual.
   Una lista correctamente citada en varias páginas no pasaba esa comprobación.

Ahora cada nombre completo se busca por separado en cada página. La normalización
se usa sólo para comparar; la cita se obtiene como subcadena exacta del texto
original mediante un índice de posiciones. Se conservan las tres páginas de
portada, el orden canónico y la deduplicación. Una advertencia de la página citada
degrada el campo a ambiguo.

Para una lista canónica, cada valor debe aparecer completo en alguna cita válida
del mismo documento y página. Cada cita comprobada debe respaldar un valor.
No se concatenan páginas/citas, ni se ignoran valores vacíos, hashes distintos o
páginas inválidas. Las listas antiguas no canónicas conservan su ruta anterior.

## Pruebas y límites de las cifras

Las pruebas nuevas son ejemplos sintéticos de desarrollo, escritos para esta
corrección. No son un holdout ni anotaciones docentes. Antes de cambiar producto,
las primeras 32 pruebas dieron **26 fallos y 6 pases**. Después, las 32 pasaron.
La revisión añadió una comprobación negativa de página booleana en el formato
serializado: **33 pruebas específicas pasan**.

Se cubren tildes omitidas, NFC/NFD, mayúsculas, caracteres fullwidth, ligaduras
anteriores al fragmento, espacios Unicode, saltos de línea, páginas reales,
duplicados, advertencias, cobertura multipágina y negativos adversariales.
Además se genera un PDF sintético que recorre lectura → extracción → verificación
→ compilación → serialización. Una revisión automatizada independiente ejercitó 10,556 casos
Unicode adicionales sin encontrar desplazamientos de citas; ese barrido tampoco
es una medición de exactitud curricular.

La suite inicial de producto obtuvo **859 pases, 10 omitidos y 2 fallos** en
Python 3.13.5 con `requirements.lock` y sus hashes. Ambos fallos precedían al cambio:

- La expectativa de C01 no contemplaba el nuevo campo obligatorio de duración
  global introducido en `3d593dc`. Se mantiene un conteo exacto y se comprueba
  explícitamente que su ausencia requiere revisión.
- Una prueba de migración dependía de una base privada de una máquina concreta y
  modificaba variables de entorno después de que Django hubiera abierto su
  conexión. Ahora crea una base vacía temporal, ejecuta migraciones en procesos
  separados, verifica el esquema en cada etapa y conserva intacta la conexión de
  pytest. No se omitió la prueba ni se copió información privada.

Los dos archivos de pruebas corregidos obtuvieron **70 pases** por separado.
El resultado de la suite completa posterior debe consultarse en la ejecución CI
del commit exacto; una ejecución local no sustituye ese resultado remoto.

### Control de regresión C01

Se repitió el fixture ya versionado, SHA-256
`33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648`:

- Antes y después: 5 páginas, 2 sesiones, 21 claims
- Antes y después: 21 comprobaciones textuales, 31 pendientes de revisión,
  0 bloqueadas; 52 elementos en total

Estos conteos no son precisión, recall ni validación pedagógica. La campaña
histórica de veinte planeaciones no se ejecutó: los PDFs no estaban disponibles
en este entorno. Su referencia procede de IA y no es un gold humano independiente;
los documentos ya expuestos tampoco pueden presentarse como holdout.

## Limitaciones conocidas

- La presencia literal de un nombre no prueba que sea aplicable al proyecto. La
  búsqueda conserva el alcance de portada existente; no resuelve asociaciones
  semánticas de tablas ni relaciones entre proyecto, fase, sesión y recurso.
- No se incorporan aliases, cambios de puntuación interna, reparación OCR ni
  nombres partidos entre páginas. Esos casos requieren otra evidencia o revisión.
- La localización de otros campos conserva sus heurísticas previas. Este cambio
  no resuelve títulos truncados ni propósitos mezclados con productos.
- La serialización antigua de `SourceReference` convierte algunos valores a
  entero. Un objeto construido incorrectamente con `page_number=True` puede
  llegar como página 1 antes del verificador. La nueva prueba usa el booleano
  crudo del dossier para comprobar el rechazo; endurecer esa coerción es trabajo
  separado, no una garantía de este cambio.

## Reproducción y evaluación siguiente

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pytest -q tests/test_campos_source_provenance.py
.venv/bin/python -m pytest -q
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```

El workflow `Product tests` fija Ubuntu 24.04, Python 3.13.5 y acciones oficiales
por SHA. Sólo pide lectura de contenido, no conserva credenciales en el checkout,
ni usa secretos, despliegues o modelos externos. Comprueba sintaxis, espacios,
configuración, deriva de migraciones y la suite completa. No añade un linter de
estilo ni afirma haberlo ejecutado.

Los hashes de acciones se verificaron contra los repositorios oficiales el
30 de septiembre de 2026: [checkout](https://github.com/actions/checkout/tree/3d3c42e5aac5ba805825da76410c181273ba90b1)
y [setup-python](https://github.com/actions/setup-python/tree/5fda3b95a4ea91299a34e894583c3862153e4b97).

Este commit y sus pruebas fijan una regresión temporal para versiones futuras.
Una evaluación de calidad posterior debe congelar de antemano código, familias
documentales, entradas, ontología y reglas de abstención; buscar documentos
independientes autorizados y adjudicar su referencia antes de estimar precisión.
Reutilizar estos ejemplos o la campaña ya observada sólo mide regresión/desarrollo.
