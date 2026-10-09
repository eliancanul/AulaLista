# Aceptación de un mismo PDF hasta la revisión humana

## Alcance comprobable sin inferencia

`tests/test_teacher_review_same_document.py` usa un PDF sintético nuevo de dos
páginas y los endpoints públicos de Django. No prepara un dossier completo por
fuera del recorrido ni usa las rutas experimentales Vue. El selector real
`pi_luna` construye el adaptador; únicamente su método de llamada se sustituye
por un doble declarado. Las tres habilitaciones live permanecen en cero. No se
ejecuta Pi, no se leen credenciales y no se hace una petición al modelo.

La prueba comprueba en el **mismo CurriculumImportJob**:

- Carga del PDF y extracción local real, con dos sesiones y cinco requisitos
  ausentes; el contexto conserva las dos páginas y el cuerpo de un anexo.
- Cuatro preguntas sintéticas agrupadas por sentido y ámbito, una caja a la vez. Las
  respuestas se comprueban en base de datos dentro de la llamada siguiente.
- Borradores recuperables desde otra sesión autenticada, respuestas literales
  y un fallo simulado posterior al guardado. GET no vuelve a generar; el
  reintento es explícito.
- Aportes humanos aplicados a los destinos preguntados, sin alterar la cita de
  un campo extraído ni confirmar automáticamente el anexo.
- Cierre con requisitos resueltos y pendientes visibles; aprobación de esa
  misma versión mediante confirmación humana explícita. La falta de
  confirmación y una versión antigua fallan; repetir la aprobación no duplica.
- Un borrador curricular, ninguna publicación, ninguna sesión de alumnado y
  ningún directorio de intento real.

Esta comprobación complementa la aceptación previa: la prueba de navegador
existente recorre seis preguntas y aprueba otro dossier completo preparado por
el fixture. Ni una ni otra demuestra calidad de Luna, aislamiento de Pi,
extracción general de PDFs reales o validación pedagógica.

El límite de seis corresponde a preguntas persistidas, no a invocaciones ni
consumo. El recorrido puede necesitar una llamada inicial y otra tras cada
respuesta: hasta siete para seis preguntas, además de correcciones o reintentos
explícitos. No constituye un presupuesto fijo de llamadas, tokens o costo.

## Reproducción acotada

Usar el entorno Python 3.13 ya instalado del proyecto y una copia de código sin
entradas privadas. Las pruebas generan y aíslan sus propios PDF, medios y base
de datos. No iniciar el servidor ni habilitar un proveedor para ejecutarlas.

```sh
export AULALISTA_PI_LIVE_ENABLED=0
export AULALISTA_LUNA_LIVE_ENABLED=0
export AULALISTA_GEMINI_LIVE_ENABLED=0
python -m pytest -q tests/test_teacher_review_same_document.py tests/test_teacher_review_provider_notice.py
node --test tests/test_teacher_review_dom.mjs
python manage.py check
python manage.py makemigrations --check --dry-run
```

La suite existente de límite de seis, corrección, recuperación y procedencia
está en `test_teacher_review.py`, `test_teacher_review_durability.py`,
`test_teacher_review_recovery.py` y los módulos de `source_context`,
`source_disclosure`, `crosspage_evidence` y `continuation_boundaries`. Mantener
sus resultados separados de la inferencia y del navegador real. No llamar a
esta selección «suite completa».

## Criterios para aceptar después una planeación real

No ejecutar estos pasos online sin la autorización y preparación correspondientes.
Primero debe cerrarse la aceptación técnica del transporte descrita en
[la ruta Pi](pi-luna.md). El objetivo es `openai-codex/gpt-6-luna`, esfuerzo
`high`, mediante Pi 0.84.4, sin sustitución de modelo o proveedor. Un catálogo,
un login o una respuesta inventada no satisfacen ese requisito.

1. **Congelar el candidato y el alcance.** Registrar commit, cambios locales si
   existen, versiones instaladas, configuración no secreta y revisión del
   aislamiento. Identificar una planeación de desarrollo elegida por la persona
   usuaria y los datos concretos autorizados para OpenAI. No usar FINAL/holdout
   ni incorporar el PDF privado al repositorio.
2. **Fijar las referencias antes de observar al modelo.** Registrar SHA-256 de
   los bytes PDF, número de páginas físicas, sesiones, actividades y referencias
   a anexos esperadas mediante lectura humana. Declarar quién hizo la revisión
   y la exposición previa. El SHA del texto extraído no reemplaza al del PDF.
3. **Comprobar la extracción con live OFF.** Importar por Django y contrastar
   todas las páginas y unidades contra el mapa anterior. Registrar omisiones,
   límites dudosos, continuaciones y páginas sin texto. Si el PDF requiere OCR,
   este recorrido no puede aprobarse como extracción completa: no tiene OCR.
   Un valor o página candidata conserva su condición de propuesta.
4. **Verificar una inferencia real acotada y autorizada.** Antes del PDF privado,
   obtener un resultado sintético real con identidad, esfuerzo, terminal y
   recibo admitidos. Luego, sólo con permiso que cubra PDF, dossier y respuestas,
   verificar en el mismo expediente el contexto de todas las sesiones y las
   páginas. Si transmisión o consumo quedan desconocidos, detener la ejecución
   y preservar el intento; nunca considerar el consumo cero ni reintentar para
   averiguar si funcionó.
5. **Evaluar preguntas y respuestas, no sólo JSON.** La persona revisora debe
   comprobar que cada pregunta corresponde a un faltante o ambigüedad real,
   incorpora la respuesta anterior y considera sesiones posteriores/anexos
   cuando corresponde. Máximo seis preguntas persistidas, una caja y una
   pregunta cada vez; correcciones y reaperturas no reinician el contador.
   Una salida sintácticamente válida o acuerdo entre modelos no es aceptación
   curricular. Cerrar con datos obligatorios ausentes sigue bloqueando aprobación.
6. **Comprobar guardado antes de avanzar.** Esperar el acuse de borrador, cerrar
   y reabrir el mismo expediente desde otra sesión. Guardar y corregir una
   respuesta; verificar texto recibido por el servidor, historial, destino y
   contador. Comprobar conflictos de dos pestañas sin sobrescritura silenciosa.
   No provocar interrupciones reales del proveedor para repetir pruebas que ya
   cubren los dobles; un fallo real obliga a aplicar el criterio de parada.
7. **Aprobar el mismo expediente y la versión revisada.** Revisar fuentes,
   originales, aportes humanos y pendientes explícitos. La aprobación exige la
   confirmación humana y, cuando corresponde, aceptación separada de pendientes.
   No sustituir el expediente por un fixture ya completo. Guardar una respuesta
   o terminar preguntas nunca debe publicar, activar una sesión ni atribuir
   autoridad editorial al modelo.
8. **Conservar evidencia y límites.** Guardar en privado las identidades de
   intento, versión, SHA PDF, resultado terminal, consumo reportado, número de
   preguntas y resultado de cada criterio. Mantener fallos y abstenciones. No
   adjuntar PDF, respuestas, credenciales ni recibos sin redactar a un issue o
   reporte público. Aceptar una planeación acredita ese caso observado, no el
   rendimiento general ni un piloto con alumnado.

Mientras falten la llamada real y la revisión de esa planeación, el estado es
«recorrido comprobado con dobles; aceptación real pendiente».
