# Revisión docente acotada

La entrada activa conserva la shell Django: **Currícula y autoría → Importar planeación → Revisar planeación**. `/sprint/` vuelve a Currícula y autoría. Los archivos experimentales Vue se conservan fuera del recorrido activo; no se cambia Wagtail ni se elimina su base o historial.

## Contrato del recorrido

- Desde la primera visita, un aviso basado sólo en configuración distingue proveedor ausente, llamadas deshabilitadas y ruta configurada sin verificar. Abrir la página no consulta un modelo ni sus credenciales. Las respuestas y borradores existentes siguen disponibles al deshabilitarlo.
- Una caja de respuesta y una pregunta generada por proveedor a la vez. Ningún catálogo fijo de preguntas se presenta como LLM.
- Máximo seis preguntas persistidas, aplicado por servidor. Puede terminar antes. Corregir una respuesta no reinicia el contador ni reemplaza una pregunta sin contarla.
- La pregunta, sus destinos exactos, la respuesta literal y cada corrección se persisten. El borrador usa un epoch/CAS independiente: los autosaves se serializan y un envío tardío no puede resucitar una respuesta guardada/descartada ni reemplazar un borrador más reciente. Refrescar no consulta el modelo.
- Los borradores se conservan por pregunta: corregir o descartar una respuesta anterior no borra el texto de la pregunta actual. Guardar una respuesta exige el epoch vigente, incluso entre pestañas. Mientras el texto más reciente no esté confirmado por el servidor, se solicita confirmación antes de salir de la página; ignorar ese aviso puede descartar texto aún no guardado.
- Guardar respuesta y preparar la siguiente pregunta son operaciones separadas. Si falla el proveedor, la respuesta queda guardada y el reintento es explícito.
- Recibos UUID y revisiones evitan doble aplicación; reclamos CAS impiden consultas simultáneas. La recuperación de una consulta interrumpida es manual y queda auditada.
- El proveedor recibe el dossier completo, todas las sesiones, actividades, anexos, procedencia, respuestas acumuladas y elementos faltantes. No recibe un recorte de la primera sesión.
- Además recibe `source_document`, separado del dossier interpretado: SHA del mismo PDF verificado, número de páginas y texto digital literal de cada página física en orden. Así conserva cuerpos de anexos y títulos que todavía no están mapeados a campos. Páginas sin texto o con extracción no disponible quedan explícitas; no se hace OCR ni se afirma interpretar imágenes. La lectura y extracción usan una sola copia de bytes comprobada y ocurren fuera de la transacción de reclamo.
- Los momentos que cruzan páginas conservan su valor completo y citas separadas por página física. Esto corrige la atribución de evidencia; no convierte tablas linealizadas, texto de imagen o límites ambiguos en una extracción semántica garantizada.
- Una mención a una rúbrica en un campo `Evaluación:` posterior a un momento explícito no descarta por sí sola la continuación inmediata. Los encabezados independientes de rúbrica, anexos y nuevos proyectos siguen cortando el bloque. El encabezado plural «Actividades y recursos» se conserva en el texto fuente y no se inventa como actividad singular.
- El transporte Gemini evita repetir los objetos de elementos pendientes: conserva `all_targets` completo una vez y envía `missing_target_ids` en el orden original. Antes de admitir el envío reconstruye `missing_fields` y exige igualdad JSON canónica de todo el contexto; IDs duplicados, desconocidos o copias divergentes se rechazan. El contexto interno y su validación no cambian. Dossier, páginas, citas, respuestas y orden se conservan; sólo se eliminan copias idénticas y espacios de serialización. El límite sigue aplicando al evento UTF-8 final completo, no a una estimación de tokens.
- El modelo sólo puede devolver una pregunta y citas literales de respuestas a destinos previamente preguntados. No puede enviar `origin`, historia, dossier, aprobación ni instrucciones de escritura. Un dato propuesto fuera de esas citas se rechaza.
- Los datos humanos se aplican directamente al dossier con `resolve` y un actor docente autenticado. Se conservan los originales y las citas PDF; no se atribuye el texto humano al PDF. El verificador exige un delta de corrección correspondiente y sigue comprobando hash, página y fragmento de cualquier cita física conservada.
- Los datos irresolubles quedan explícitos al cerrar. Guardar respuestas nunca aprueba ni publica: la aprobación final usa el comando humano existente y sigue bloqueada por requisitos faltantes.
- Las ediciones independientes/reextracción requieren revisar y retomar explícitamente la nueva versión. Las respuestas y el contador se conservan.

## Luna seleccionado, ruta pendiente

La selección predeterminada de `AULALISTA_TEACHER_REVIEW_PROVIDER` es `luna`.
El adaptador local invoca Codex CLI con `gpt-6-luna` y esfuerzo `high`, stdin,
salida estructurada, límites locales y ledger privado. No espera una API key.
Su contrato se prueba con una CLI sintética; la ejecución real sigue pendiente.

Las rutas explícitas, el registro de revisión de restricciones y la habilitación
se describen en [la guía de Luna CLI](luna-cli.md). Sin ellos, la interfaz informa
configuración pendiente o llamadas deshabilitadas. La preflight real debe pasar
antes de enviar el prompt; no se evita un fallo del sandbox. No hay fallback a
Gemini, Ollama o una API. Los límites de tiempo/bytes no son topes de tokens/costo,
y la detección de eventos no garantiza prevenir toda herramienta.

El contrato compartido de preguntas, máximo seis, procedencia, contexto completo
y guardado durable permanece vigente. Una prueba de la CLI inventada o un aviso
de configuración no demuestra acceso, calidad de Luna o seguridad efectiva.

El intento histórico desconocido de Gemini se conserva con su identidad;
seleccionar Luna no lo convierte en un intento Luna ni concilia su consumo.
Las revisiones ya bloqueadas por ese intento continúan bloqueadas hasta la
resolución explícita correspondiente.

## Ruta Gemini histórica, conservada para auditoría

La selección anterior fue Gemini high. La ruta implementada usa exclusivamente la CLI oficial Google Antigravity y su conexión autenticada existente; no lee ni copia sus credenciales y no imita endpoints privados. El catálogo autenticado de CLI 1.2.15, consultado el 3 de octubre de 2026, anuncia el identificador exacto `gemini-3.8-flash-high`. Se fijan tanto ese ID como `--effort high`; no hay fallback a otros modelos, esfuerzos ni Ollama.

La configuración histórica explícita `gemini` se conserva, pero ya no es la selección predeterminada. Sus variables no habilitan Luna y no deben usarse como fallback:

- `AULALISTA_GEMINI_AGY_LAUNCHER`: launcher oficial comprobado que ya gestiona su autenticación
- `AULALISTA_GEMINI_AGY_AGENT_FILE`: perfil de sólo respuesta comprobado, sin herramientas, comandos, MCP, skills ni plugins
- `AULALISTA_GEMINI_ATTEMPT_DIR`: carpeta privada para recibos y solicitudes; nunca un directorio estático público
- `AULALISTA_GEMINI_LIVE_ENABLED=1`: habilitación explícita; vacía/cero impide llamadas reales
- `AULALISTA_GEMINI_TIMEOUT_SECONDS`: límite local de 90 segundos por defecto, hasta 120

El modelo, versión y hashes de launcher/perfil se comprueban antes de transmitir. Un cambio de identidad exige revisión explícita. Cada llamada usa un ID/directorio exclusivo y un recibo de admisión antes de lanzar un único proceso. El prompt entra por stdin desde archivo, nunca por argumentos del shell. El recorder v3 conserva streams, un resultado terminal y uso declarado, verifica identidad real, ausencia de herramientas/permisos y salida estructurada. El wrapper no continúa conversaciones ni relanza procesos automáticamente. La CLI puede reintentar internamente; ese número y los envíos efectivos al proveedor no se observan de forma independiente. Los recibos nuevos precisan `automatic_retries_scope=wrapper_process_relaunches`, y dejan `transport_internal_retries` y `provider_dispatch_count` en `null`. `max_attempts=1` limita lanzamientos del wrapper, no acredita una sola petición backend. Los recibos históricos se conservan sin reescribirlos.

Un timeout local no es un tope de tokens/costo ni prueba que el proveedor haya dejado de trabajar. Si resultado o consumo quedan sin conciliar, se bloquea otra llamada hasta nueva autorización/conciliación. Los tokens se toman del único recibo terminal; thinking/cache no se suman de nuevo al total. La CLI no expone un cap monetario/duro de tokens. El contexto completo admite hasta 4 MiB de solicitud serializada: al superarlo, se informa el bloqueo sin recortar ni enviar parte del documento.

El registro de respuestas conserva SHA y versión. Una respuesta de otra fuente, una declaración completa de desconocimiento o una respuesta anterior a una corrección humana independiente no puede volverse un valor apoyado por el docente sin confirmación humana renovada.

El perfil existente se identifica como `structure-only` por su nombre histórico; sus límites reales se comprueban por hash e init. Su cuerpo exige trabajar sólo sobre texto suministrado y no usar herramientas ni archivos. Los datos de la persona docente y su PDF sólo deben transmitirse bajo la autorización aplicable, al destino Google indicado; la autorización de un smoke sintético no autoriza PDFs privados.

Fuentes técnicas oficiales: [modo headless y salida estructurada](https://antigravity.google/docs/cli/headless), [perfiles sin herramientas](https://antigravity.google/docs/subagents/), [niveles de thinking Gemini](https://ai.google.dev/gemini-api/docs/generate-content/thinking). El catálogo actual de la CLI es la autoridad del ID callable; no se deduce de un nombre comercial ni del ID de otro transporte.

Las pruebas locales usan doubles explícitos; no acreditan calidad de modelo ni validación pedagógica. La comprobación real queda acotada al smoke sintético autorizado y se comunica por separado con sus recibos.

## Comprobaciones locales

`python manage.py check`

`python manage.py makemigrations --check --dry-run`

`python -m pytest -q tests/test_teacher_review.py tests/test_teacher_review_gemini.py tests/test_t_project_duration_verification.py tests/test_ux9_blocker2_verification.py tests/test_t18_task5_verification.py::TestNormalization`

`python -m pytest -q tests/test_teacher_review_durability.py tests/test_teacher_review_source_disclosure.py tests/test_teacher_review_source_context.py tests/test_teacher_review_crosspage_evidence.py tests/test_teacher_review_continuation_boundaries.py tests/test_local_package_privacy.py`

`node --test tests/test_teacher_review_dom.mjs`

Las migraciones son aditivas (`0044_curriculumteacherreview` y `0045_curriculumteacherreview_draft_state_and_more`). Ningún corpus privado es necesario para las comprobaciones indicadas. La QA visual de navegador debe realizarse en un entorno que permita abrir la aplicación local; un bloqueo de localhost no se evita con otro mecanismo de acceso.

El harness JS usa eventos DOM sintéticos: no acredita renderizado ni navegación real. CI exige por separado `tests/test_teacher_review_browser.py`: Chrome real, Django, PDF generado y proveedor adaptativo simulado explícito. Se mantienen las cuatro regresiones de navegador de Vue/edición masiva bajo URLconfs exclusivos de tests; no describen el recorrido activo. Falta de Chrome en CI es un fallo, no una omisión. Un workflow editado o el harness DOM no acreditan que esa ejecución de navegador haya pasado. Véase la [lista de aceptación real y operación conservadora](teacher-review-acceptance.md).

Las regresiones de lógica y plantillas de staging/cola anteriores se conservan
con las fixtures optativas `legacy_import_routes` y `legacy_vue_routes`, cuyo URLconf existe sólo en
`tests/`. Las rutas de edición `_test_legacy/` y la shell Vue experimental sólo existen al activar esos URLconfs; el producto sigue redirigiendo `/sprint/`. Esas
pruebas conservan las comprobaciones de fuente, propietario, aprobación y
publicación; las pruebas de revisión docente verifican por separado que las
rutas públicas usan una sola caja y rechazan las acciones de la interfaz retirada.

## Resultado del smoke real autorizado

Se admitió un único proceso wrapper para el smoke sintético del 3 de octubre de 2026, sin relanzarlo. Los reintentos internos de CLI y el número de peticiones backend no se observaron de forma independiente. La identidad de init confirmó el modelo/agent pedidos, pero la CLI anunció un catálogo completo de herramientas a pesar del perfil acotado. El guard lo rechazó y terminó el proceso; no se aceptó ninguna respuesta. No se observaron eventos de uso de herramientas, pero eso no acredita que la configuración haya deshabilitado sus capacidades.

No hubo resultado terminal ni recibo de tokens. El estado de transmisión y consumo queda desconocido, nunca cero. Se conserva el ledger original y se bloquea otra llamada. El proveedor real queda **no validado para usar PDFs privados**. Para continuar hace falta resolver la capacidad efectiva de la CLI y obtener nueva autorización que cubra el intento pendiente; no se sustituye por otro modelo, esfuerzo, ruta ni credenciales.

La [nota oficial de cambios de AGY](https://antigravity.google/docs/changelog) documenta reintentos internos desde v1.2.1 y cambios de descubrimiento de perfiles. Que una opción esté documentada no demuestra que el proceso observado haya eliminado herramientas. Las pruebas nuevas requieren una configuración efectiva admitida; no se debilita el guard de herramientas ni se borra un intento desconocido.

## Alcance sintético de CI

Antes de las pruebas, `scripts/prepare_synthetic_ci.py` materializa el árbol Git
exacto en un directorio nuevo, sin PDFs, bases, archivos de entorno, fuentes
privadas, investigación ni corpus congelado. Examina sus rutas antes de leer
blobs; un archivo de código inesperadamente ausente es un fallo. El manifiesto
registra código y conteos de exclusión, sin hashes/rutas de PDFs privados.

`scripts/run_synthetic_backend.py` conserva el alcance declarado del agregado:
excluye explícitamente diez módulos históricos dependientes de PDFs privados y
tres selecciones de corpus congelado, e imprime sus nombres. Los dos módulos de
finalidad implícita dependientes de entrada privada tampoco se materializan.
Sus pruebas no se borran ni se presentan como aprobadas. Los seis casos puros
`TestNormalization` del módulo mixto se ejecutan por separado, igual que los
cuatro contratos de timeout PDF. También quedan fuera otros casos sintéticos
mezclados con esos módulos privados; no se llama «suite completa» a este gate.
El detalle versionado de la selección está en el runner y no depende de que haya
un PDF accidentalmente presente en la máquina.

Las pruebas de navegador actuales e históricas usan PDFs generados y bases
separadas dentro del mismo snapshot. Los checks reales de GitHub corresponden
al commit publicado; un resultado local parcial no los sustituye. La evaluación
con documentos de desarrollo o un proveedor real es otra ejecución autorizada y
privada, nunca un paso automático del CI público.


## Fallos esperados de seguridad conservados

El hallazgo S18-F01 afectaba al verificador usado por el recorrido activo: un
valor distinto del citado podía marcarse comprobado sólo por aparecer en la
misma página. Su regresión ahora exige que el valor esté ligado a la cita;
la única compatibilidad de preview corresponde a una cita de exactamente
200 caracteres para un valor más largo de inicio, desarrollo, cierre, materiales
o evaluación de sesión, tal como la emite el parser. Exige el prefijo exacto y
el valor completo en esa página y segmento. Los campos generales y los prefijos
triviales no reciben esa excepción. No acredita corrección pedagógica.

S18-F02 sigue declarado como `xfail(strict=True)` en
`tests/sprint_security/test_s18_known_findings.py`: el adaptador histórico
`identify_topics` acepta un título propuesto y páginas fuera del chunk. Ese
adaptador pertenece al worker de etapas anterior, no al recorrido activo de
revisión Django. No se presenta como corregido; su cambio requiere conservar
el contrato de propuestas y la validación de fuentes del flujo antiguo. La
suite sigue mostrando explícitamente ese fallo esperado.
