# Guía de anotación v1: importación curricular PDF

Usar [el schema v1](goldset-importacion-curricular-schema-v1.json) y [el manifiesto](goldset-importacion-curricular-manifest-v1.json). Esta guía no autoriza importar, crear ni publicar contenido curricular.

Cada anotador trabaja desde el PDF renderizado y una copia independiente de las anotaciones. Nunca lea ni modifique la anotación de la otra persona; la adjudicación vive en un archivo separado.

1. Cree una entrada por página: aun portada, publicidad, imagen o página ambigua recibe uno de `included`, `reference_only`, `quarantined` o `excluded`, más una razón.
2. Dibuje regiones en `normalized_top_left_xywh` (origen arriba-izquierda, 0-1). Use `unknown` o `quarantined` si la región o su lectura no es defendible.
3. Registre texto visible con `method: visual`; texto de extracción u OCR conserva su propio método. No invente texto de una imagen ni clave de respuesta.
4. Para tablas, conserve la región `table`; sólo complete estructura de celdas si se puede verificar visualmente. Ordene bloques por el orden humano de lectura, no por el orden que devuelva un parser.
5. Declare jerarquía y relaciones sólo con evidencia: por ejemplo, sesión → anexo/cuadernillo. Una contradicción de calendario se conserva como contradicción, no se resuelve silenciosamente.
6. Todo campo que se aceptara en el futuro exige `evidence` con página y `bbox` resoluble. Este corpus semilla no acepta campos curriculares ni genera actividades.

Cobertura: todas las 75 páginas locales requieren una anotación ligera. Las páginas de `deep_sample_pages` reciben además regiones, tablas, orden, jerarquía y relaciones. Los cuadernillos son `reference_only`: puede registrarse su texto, pero sus imágenes no se vuelven reactivos ni claves.

Calibración usa C01/C02; prueba reservada usa C03/C04. C01 es un derivado de C02 y no puede cruzar splits. La plantilla B se conserva independiente; compare ambas sólo durante adjudicación. Los resultados se reportan como incompletos hasta que haya dos anotaciones, adjudicación, y revisión de la fuente renderizada.
