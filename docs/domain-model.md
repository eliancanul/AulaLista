# Modelo de dominio: de la fuente a una planeación revisada

Estado: fronteras y alcance aprobados para implementar el 5 de octubre de 2026; relaciones particulares todavía revisables. Este documento distingue contratos ya vigentes, brechas observadas en el código y cambios acordados; no acredita una migración implementada ni validación pedagógica.

## Vista breve

AulaLista debe conservar qué dice la fuente, explicar qué interpreta y permitir que la persona docente decida. El recorrido es: reconocer la organización real del documento, presentar una interpretación con citas, aclarar sólo lo necesario, conservar las respuestas y revisar una versión concreta antes de aprobarla; publicar es otra acción.

- Una planeación puede organizarse por proyectos, fases y actividades sin declarar sesiones. No se fabrican sesiones para satisfacer una forma de almacenamiento.
- Un propósito de aprendizaje puede ser implícito. Se propone con evidencia y explicación, separado de lo literal, y queda pendiente de revisión docente.
- Una instrucción no equivale necesariamente a una actividad; un anexo puede continuar en varias páginas; reconocer un recurso no confirma su asociación.
- La conversación usa una sola caja, preguntas adaptativas y un máximo de seis preguntas guardadas. Terminar la conversación no completa por sí mismo los pendientes ni aprueba nada.
- Fuente, interpretación, decisión docente y publicación tienen identidades y autoridad distintas.

El vocabulario canónico está en [GLOSSARY.md](../GLOSSARY.md). Las reglas institucionales y editoriales previas se conservan, especialmente [ADR-0001](adr/0001-published-snapshots-separate-editorial-revisions.md), [ADR-0002](adr/0002-human-editorial-review-owns-publication.md), [ADR-0006](adr/0006-teacher-workflow-and-human-curriculum-progress.md) y [ADR-0010](adr/0010-staging-relacional-idempotente.md).

## 1. Alcance y grado de certeza

### Contratos que ya están resueltos

La fuente literal y el dato aportado por la persona docente conservan procedencias distintas. La aprobación y publicación requieren autoridad humana; la sesión de aula lee versiones publicadas inmutables. Guardar una respuesta precede a pedir otra pregunta, reabrir conserva el trabajo y ninguna llamada al modelo forma parte de una mera lectura de pantalla.

El recorrido solicitado continúa en Django. Luna mediante Pi es una elección de transporte y modelo para la aclaración, no una entidad pedagógica ni una autoridad editorial. Un cambio de transporte no puede cambiar el significado de los datos ni habilitar llamadas reales por sí mismo.

### Distinciones resueltas para este modelo

Fase, momento pedagógico, sesión declarada y ClassroomSession son conceptos diferentes. Una fase no prueba una sesión; la ejecución futura de aula tampoco prueba que una sesión estuviera declarada en la fuente. El propósito implícito puede presentarse como propuesta interpretativa: ausencia de un rótulo no equivale a ausencia de intención de aprendizaje.

### Relaciones que siguen abiertas

No se impone una jerarquía universal fase → momento → sesión → actividad. Algunas fuentes usan momentos dentro de fases, otras dentro de sesiones, y otras no declaran esas relaciones. Se conservará la relación que la fuente o una decisión docente sustente, y la ausencia de relación permanecerá visible.

No se ha decidido que cada instrucción sea una actividad, que cada producto determine un propósito, ni que toda hoja de actividad sea un anexo independiente. Tampoco se fija aquí un número universal de evidencias necesario para inferir: un umbral de un evaluador concreto es una hipótesis técnica que debe probarse.

## 2. Identidades, entidades y relaciones

La siguiente es una descripción conceptual; no prescribe una tabla por fila.

| Concepto | Identidad y límite | Relaciones permitidas | Situación del código inspeccionado |
| --- | --- | --- | --- |
| Documento fuente | Documento de trabajo; su nombre visible no identifica su contenido | Tiene versiones de fuente | Archivo de `CurriculumImportJob`; no hay entidad independiente para toda su historia documental |
| Versión de fuente | Bytes exactos y páginas físicas de una fuente | Sostiene fragmentos y dossiers; no cambia por una corrección docente | `source_sha256`, archivo verificado y `CurriculumSourceBlob` en la aprobación |
| Fragmento y cita de fuente | Localización dentro de una versión, página y tramo | Apoya valores, roles, límites y relaciones concretos | `SourceReference` y segmentos; no se presupone lectura de imágenes |
| Planeación / proyecto | Unidad pedagógica, independiente del archivo y del paquete editorial | Puede contener fases, momentos, sesiones declaradas y actividades | Dossier y contexto de proyecto; representación de varios ámbitos todavía parcial |
| Fase / momento pedagógico | División o tramo reconocido, con rótulo original y ámbito | Orden, pertenencia y continuación sólo cuando se sustentan | El fallback de fases ocupa un `SessionPlan`; falta distinción uniforme |
| Sesión declarada | Unidad explícitamente delimitada por la fuente | Puede agrupar actividades y momentos | `SessionPlan` sirve también de contenedor técnico y no prueba esta identidad |
| Actividad / instrucción | Tarea reconocida / enunciado de acción | Varias instrucciones pueden pertenecer a una actividad; relación no siempre determinada | `SessionActivity` está anidada en la representación de sesión; no basta para todo documento por fases |
| Anexo / hoja de actividad | Recurso reconocible, no una página | Puede tener varios fragmentos y relacionarse con más de una actividad | `annex_candidates` y `AnnexReference`; `confirmed_page` no expresa por sí solo un recurso multipágina |
| Propuesta interpretativa | Valor o relación propuestos para un ámbito y versión concretos | Conserva apoyos, explicación, incertidumbre y revisión | `InterpretedField` con origen `proposed`; relaciones estructurales necesitan contrato equivalente |
| Dossier / versión revisada | Estado revisable de la interpretación ligado a una versión de fuente | Reúne unidades, propuestas, selección, pendientes e historia | `ImportDossier`, versión, historial y verificaciones |
| Aclaración docente | Conversación de una importación, ligada a fuente y versión revisada | Preguntas, respuestas, correcciones y aplicación de datos | `CurriculumTeacherReview`; tiene revisión independiente de la del dossier |
| Aprobación docente de importación | Decisión humana sobre fuente y versión exactas | Produce o actualiza un borrador editorial; conserva aceptación e historia | `CurriculumImportApproval` y `execute_teacher_approval` |
| Paquete / versión publicada | Contenido editorial editable / contenido publicado inmutable | Revisión y aprobación editorial antes de publicación; ClassroomSession fija la publicación | `CurriculumPackage`, `PublishedPackageSnapshot` y `PublishedRoadmapSnapshot` |

Cardinalidades que el modelo debe admitir:

1. Una versión de fuente puede contener más de un proyecto; no se hereda el último título a otro ámbito sin evidencia.
2. Un proyecto puede tener cero sesiones declaradas y aun así tener fases, instrucciones, actividades y recursos útiles.
3. Una fase o una actividad puede continuar en varias páginas; una página puede contener varias unidades. Sus cuentas son independientes.
4. Un anexo puede tener varias páginas y varias asociaciones. Su encabezado, cuerpo y mención desde una actividad son evidencias diferentes.
5. Una cita puede apoyar más de una propuesta sólo si se explica cada atribución; repetirla no crea apoyos independientes.
6. Una fuente puede tener varias versiones revisadas y decisiones históricas. La última edición no reescribe una aprobación anterior.
7. Una actividad de planeación puede servir de fuente para un borrador editorial, pero no se convierte automáticamente en él ni en una actividad de aula.

La fuente y el dossier no forman una cadena en la que una entidad sustituya a la anterior. Coexisten: una propuesta apunta a sus citas y a su ámbito; una decisión docente apunta a la propuesta o dato revisado; una aprobación apunta a una versión completa.

## 3. Fronteras de responsabilidad

El repositorio sigue siendo de un solo contexto. Estas son fronteras de responsabilidad dentro de él, no una propuesta de microservicios ni un mapa de contextos ya adoptado.

### A. Lectura y procedencia

Posee la identidad de fuente, las páginas físicas, los fragmentos y los avisos de extracción. Responde «¿qué texto se obtuvo y dónde?». No decide qué pretende enseñar el documento ni qué puede publicarse.

Una página vacía en la extracción puede contener imágenes. Se informa la limitación; no se registra «no tiene ejercicios» ni se afirma que se hizo OCR. Texto encontrado y cobertura visual son evidencias diferentes.

### B. Estructura e interpretación pedagógica

Propone unidades, ámbitos, valores y asociaciones. Responde «¿qué parece significar este contenido, en qué unidad y con qué apoyos?». Consume fragmentos de A sin modificar el original.

Conserva por separado el rótulo original, el rol interpretado y el motivo de asignar ese rol. El encabezado «Finalidad» puede aportar una intención de aprendizaje, pero interpretar esa intención como propósito no cambia retrospectivamente la etiqueta ni convierte la propuesta en extracción literal de otro campo.

### C. Revisión y aclaración docente

Conserva preguntas, respuestas literales, cambios y decisiones de una persona autorizada. Responde «¿qué falta decidir y qué decidió la docente?». La cola completa de revisión incluye confirmaciones y datos opcionales, por lo que no es una lista de preguntas automáticas.

La interfaz debe presentar juntos valor, procedencia y pendiente, sin obligar a consultar campos ocultos para distinguir una cita de una propuesta. Los fallos del modelo no eliminan respuestas guardadas ni borradores de otras preguntas.

### D. Edición y publicación

Posee el borrador editorial, la aprobación editorial y las versiones publicadas. Recibe una importación aprobada como entrada revisable; no interpreta una conversación terminada como permiso para publicar.

La operación de aula conserva sus propias sesiones, permisos y publicaciones fijadas. El vocabulario «sesión declarada» evita confundir una descripción de la fuente con una ClassroomSession real.

## 4. Contrato de afirmación y evidencia

Toda afirmación de interpretación necesita poder responder:

- ¿Cuál es el valor o la relación afirmada?
- ¿A qué versión de fuente y ámbito pedagógico pertenece?
- ¿Qué fragmentos exactos la apoyan y qué papel tiene cada uno?
- ¿El valor está declarado, fue inferido o lo aportó la docente?
- ¿Qué falta comprobar y qué decisión humana existe realmente?

No se sustituye esta información por una única confianza numérica. Se separan al menos cuatro dimensiones:

| Dimensión | Pregunta que responde | Lo que no demuestra |
| --- | --- | --- |
| Presencia literal | ¿Existe este fragmento en la página de esta fuente? | Que pertenezca a un campo o ámbito concreto |
| Atribución estructural | ¿Este fragmento corresponde a esta unidad, papel o continuación? | Que una inferencia pedagógica sea correcta |
| Apoyo interpretativo | ¿Estas acciones, contenidos y resultados justifican la propuesta? | Confirmación docente o aprendizaje logrado |
| Revisión humana | ¿Qué aceptó o corrigió una persona, en qué versión y ámbito? | Publicación o cambio de la fuente original |

Correspondencia mínima con los contratos existentes:

- El dossier usa `origin`: `extracted`, `proposed`, `teacher_entered`; `status`: `supported`, `missing`, `ambiguous`, `conflicting`; y `review`: `pending`, `confirmed`, `corrected`. Son ejes distintos y no deben reducirse a «válido».
- El adaptador `interpretation_schema.py` usa `status`: `extracted`, `suggested`, `unknown`, más `evidence_ids` y `reason`. `suggested` no es una aprobación ni una nueva procedencia de la fuente. Este DTO no reemplaza el estado canónico del dossier.
- `SourceReference` conserva huella de documento, página física, fragmento, etiqueta impresa y rol cuando existe. La explicación de una inferencia no se introduce dentro de `excerpt` como si fuera texto de fuente.
- Una respuesta docente aplicada conserva el texto humano, su pregunta y su ámbito. Si conserva citas PDF anteriores, estas siguen siendo originales; el texto humano no se atribuye a ellas.

### Propósito de aprendizaje implícito

Una propuesta debe diferenciar acción o capacidad del alumnado, contenido trabajado y los apoyos que aporta la actividad, producto o evaluación. Un producto aislado, un material, una acción administrativa del docente o un verbo pedagógico sin contenido no bastan por sí mismos para atribuir aprendizaje.

La evidencia puede estar bajo otro rótulo o distribuida en varios fragmentos. La propuesta explica el salto interpretativo, no cambia el rótulo de origen y no se copia a todos los ámbitos del proyecto. Una reformulación permanece propuesta aunque sus palabras coincidan parcialmente con la fuente.

Si la evidencia es contradictoria, se conserva el conflicto. Si no alcanza para la regla del evaluador, se registra abstención de ese evaluador y se pide la decisión pertinente; no se afirma que la intención no existe en el documento. Un propósito ya confirmado o corregido no se reemplaza automáticamente al volver a interpretar.

## 5. Eventos y transiciones

Los nombres siguientes describen hechos del dominio que deben poder auditarse. No implican implementar event sourcing ni una tabla nueva por evento.

| Hecho | Actor / condición | Efecto permitido | Efecto que no implica |
| --- | --- | --- | --- |
| Fuente incorporada | Persona autorizada entrega una fuente | Fijar la versión de fuente y permitir lectura | Aprobación de su contenido |
| Lectura de fuente registrada | Extractor termina con cobertura y avisos | Conservar páginas y fragmentos obtenidos | Comprensión semántica completa |
| Interpretación preparada | Intérprete produce unidades y propuestas | Crear dossier revisable con pendientes | Confirmar citas o decisiones humanas |
| Pregunta guardada | Servicio valida una pregunta adaptativa admisible | Añadir una pregunta al historial y al contador | Considerar resueltos sus destinos |
| Respuesta guardada | Docente entrega texto para esa pregunta | Conservarlo antes de solicitar otra pregunta | Aplicarlo a todo el dossier |
| Dato docente aplicado | Cita elegible de respuesta actual y destino preguntado | Cambiar el ámbito autorizado y conservar la versión anterior | Reatribuirlo al PDF o publicarlo |
| Dato confirmado o corregido | Decisión docente explícita | Resolver el dato o relación concretos | Aprobar el conjunto |
| Aclaración cerrada | No quedan bloqueos preguntables o se agota el límite | Detener nuevas preguntas y mostrar pendientes | Completitud o aprobación |
| Revisión retomada | Docente revisa cambio de versión | Continuar sobre estado vigente preservando historia | Reiniciar el contador o aplicar respuestas obsoletas |
| Importación aprobada | Comando humano sobre fuente y versión verificadas | Conservar aprobación y preparar borrador editorial | Publicar el paquete |
| Paquete aprobado editorialmente | EditorialReviewer revisa el contenido | Autorizar la publicación correspondiente | Activar una ClassroomSession |
| Paquete publicado | Acción editorial autorizada | Crear versión publicada inmutable | Cambiar sesiones ya iniciadas |

Fuente modificada, resultado obsoleto, llamada fallida y conflicto de edición son sucesos operativos que interrumpen una transición; no se registran como decisiones pedagógicas. Un reintento no constituye una nueva respuesta ni autoriza ocultar un resultado desconocido.

## 6. Invariantes

### Fuente y estructura

1. Toda cita corresponde a la versión de fuente indicada y a una página física real. La comparación mecánica no convierte el resultado en verdad pedagógica.
2. No se unen fragmentos a través de páginas para fingir una cita literal continua. La unidad puede continuar; sus citas conservan cada localización.
3. No se equiparan fase, momento, sesión declarada y ClassroomSession. La ausencia de sesiones declaradas es válida en una planeación por fases.
4. Una continuación, una pertenencia y una asociación de anexo son afirmaciones independientes. Cada una necesita sus apoyos o una decisión docente explícita.
5. Instrucciones, actividades, anexos y páginas tienen denominadores distintos. No se comunica un conteo bajo el nombre de otro.
6. Lo no asignado no desaparece ni se asigna al ámbito más cercano por comodidad. Un título al pie de página no queda separado automáticamente de su cuerpo siguiente.

### Interpretación y autoridad

7. Una inferencia conserva origen de propuesta y revisión pendiente; no rellena retroactivamente la fuente ni sustituye un dato docente confirmado.
8. No exigir un rótulo «Propósito» para formular una propuesta no elimina la exigencia de evidencia. Finalidad, materiales y producto no se renombran automáticamente como propósito.
9. Una cita localizada, un esquema válido, una propuesta apoyada y un dato confirmado representan comprobaciones distintas. Ninguna concede publicación automática.
10. Cambiar fuente o ámbito exige revisar la elegibilidad de los datos anteriores. Una respuesta de otra fuente o anterior a una corrección independiente no sustituye la decisión vigente.
11. Una aprobación pertenece a fuente y versión exactas. Editar después requiere una nueva decisión pertinente; no modifica la aprobación histórica ni una publicación ya usada.

### Aclaración y continuidad

12. Se conservan como máximo seis preguntas persistidas; una corrección, reapertura, fallo o reintento no reinicia el contador. El límite de preguntas no es un tope de llamadas, tokens o coste.
13. Se guarda la respuesta antes de preparar la siguiente pregunta. Un fallo posterior deja disponible esa respuesta y distingue los cambios todavía sin confirmar por el servidor.
14. Las preguntas son adaptativas, de un foco relacionado y sobre bloqueos todavía vigentes. Confirmaciones y opcionales siguen visibles sin convertirse en un cuestionario automático.
15. Se aplica primero la respuesta elegible y después se decide si hace falta preguntar otra cosa. No se pregunta otra vez por un dato recién resuelto.
16. Agotar seis preguntas con bloqueos pendientes deja los bloqueos explícitos. Cerrar la aclaración no aprueba la importación, no publica y no anuncia completitud.
17. Lectura, reapertura y consulta de historial no disparan llamadas al proveedor. La autorización de una prueba sintética no cubre transmisión de fuentes privadas.

Las reglas institucionales de propiedad, acceso y privacidad no cambian: la maestra conserva sus importaciones y borradores; una adscripción no concede propiedad editorial; las identidades de menores no forman parte de la aclaración curricular.

## 7. Escenarios que tensionan el modelo

Todos estos son escenarios sintéticos de diseño. No contienen ni requieren una fuente docente privada y no representan pruebas ejecutadas por este cambio documental.

| Escenario | Resultado que el modelo exige | Error que debe detectar |
| --- | --- | --- |
| Planeación de tres fases, sin sesiones explícitas | Tres fases y cero sesiones declaradas; unidades e instrucciones conservadas | Crear tres sesiones, o una sesión ficticia para poder validar |
| Varias instrucciones incluyen reunir materiales y hacer preguntas auxiliares | Conservar instrucciones y roles; proponer actividades sólo con delimitación suficiente | Contar cada viñeta, material o interrogación como una actividad |
| Cinco anexos abarcan ocho páginas; uno tiene título al pie y cuerpo en las siguientes | Cinco recursos si la evidencia lo sustenta, con fragmentos y continuaciones separadas | Anexo nuevo por página, perder el título o anexar el cuerpo al recurso anterior |
| Un texto bajo «Finalidad» expresa una acción de aprendizaje corroborada por la actividad | Mantener el texto y rótulo literal; presentar el propósito como propuesta explicada | Rechazar por falta de etiqueta o declarar extracción de «Propósito» |
| «Hacer un cartel» es el único dato del objetivo | Conservar producto esperado; no inventar el aprendizaje específico | Atribuir una capacidad sólo por reconocer un producto |
| Dos proyectos usan el mismo título y anexos numerados desde uno | Identidades y asociaciones separadas por ámbito y fuente | Unir proyectos o anexos sólo por título o número |
| La docente responde «No sé» o corrige una respuesta anterior | Conservar texto literal; mantener lo desconocido y revisar sólo destinos elegibles | Recortar una frase positiva y presentarla como dato apoyado |
| La sexta pregunta termina con tres bloqueos aún abiertos | Mostrar límite y bloqueos; conservar respuestas; permitir revisión humana dentro del flujo autorizado | Séptima pregunta, contador reiniciado o aprobación fingida |
| Se guarda respuesta, falla el proveedor y se reabre en otra pestaña | Respuesta y contador intactos; versión vigente y texto local diferenciados | Pérdida de texto, doble aplicación o consulta automática al abrir |
| Se corrige un propósito después de una aprobación o publicación | Nueva versión revisada y decisión correspondiente; publicación anterior intacta | Actualizar en vivo una ClassroomSession que ya empezó |

## 8. Divergencias comprobadas y evolución acotada

La inspección de código parte de la base `5c93fb661d17768414449f65daaf77fbbd9d2791` y de los candidatos locales de preguntas enfocadas, contexto semántico y citas de valor derivados de ella. No se atribuyen automáticamente esos cambios a la cabeza publicada del PR.

### D1. Contenedor técnico presentado como sesión

`ImportDossier.sessions` contiene `SessionPlan`; el verificador requiere campos generales y al menos una sesión. `first_phase_review_page` y `phase_review_scope` admiten una unidad provisional de revisión por fases, reconocida también como `pN_project_review`. Eso permite conservar contenido, pero no prueba que el documento declare una sesión ni modela todas las fases por separado.

Evolución propuesta: discriminar unidad de revisión de proyecto frente a sesión declarada, conservar unidades y bloques de fuente y adaptar cola, selección, verificación, aprobación, exportación y presentación. Un nombre distinto en la pantalla no corrige consumidores que siguen exigiendo inicio/desarrollo/cierre a un contenedor de fases. Datos antiguos sin evidencia del tipo no se convierten por defecto en sesiones declaradas.

### D2. Instrucciones y recursos dentro de actividades

`SessionActivity` presupone un ámbito de sesión; los detectores de unidades por fases pueden reutilizarlo. El lenguaje del dominio exige conservar instrucciones y roles de bloques sin afirmar una segmentación pedagógica que no se ha establecido.

Evolución propuesta: separar bloques/instrucciones de actividades reconocidas, y hacer explícitos los candidatos o fragmentos no asignados. El número de instrucciones recuperadas no se informa como número de actividades. Mantener compatibilidad no autoriza mezclar candidatos sin tipo en una lista que otros consumidores cuentan como actividades reales.

### D3. Anexo confundido con página confirmada

`AnnexReference` conserva menciones, páginas candidatas, evidencia y una sola `confirmed_page`. Esa página puede localizar el recurso, pero no define todos sus límites ni su contenido multipágina.

Evolución propuesta: conservar un recurso con fragmentos, continuación y asociación independientes. La revisión de la página inicial no confirma automáticamente el cuerpo de páginas siguientes ni sus actividades asociadas.

### D4. Protección de literalidad que bloquea interpretar un rol

`overview_supported` y `tests/test_night_source_roles.py` protegen los roles extraídos: un valor presente en materiales o en otro campo no se convierte en propósito literal. Esa protección es válida para extracción, pero no debe convertirse en una prohibición general de proponer un propósito implícito.

Evolución propuesta: conservar la protección de `extracted` e incorporar una salida de propuesta evidenciada, explicada y pendiente. El contrato existente `InterpretedField(origin='proposed', status='ambiguous', review='pending')` puede alojar ese mínimo sin simular que ya se completó una migración estructural. Si hay abstención, distinguir evidencia insuficiente para esa regla de ausencia de intención en toda la fuente.

### D5. Faltantes del parser convertidos en preguntas a la docente

El dossier puede no incluir un dato que sí está en las páginas literales de `source_document`. La política candidata de preguntas reduce la cola a `requires_resolution`, hasta tres destinos relacionados y 500 caracteres, sin eliminar el contexto completo; esos límites de tamaño no garantizan por sí solos coherencia semántica.

Evolución propuesta: consultar la fuente antes de preguntar; separar «no reconocido», «propuesto pendiente de revisar», «dato ausente» y «fuente ilegible». Un error de extracción no justifica pedir a la docente que vuelva a escribir todo el documento. La salida actual de aclaración sólo aplica citas humanas: una inferencia de la fuente necesita su propia frontera de propuesta y validación, no disfrazarse de `answer_updates`.

### D6. Importación aprobada no es contenido publicado

`execute_teacher_approval` conserva `CurriculumImportApproval` y prepara o actualiza un `CurriculumPackage`; no publica una versión. Además, la proyección editorial histórica usa el propósito y, si falta, la finalidad, y toma el título de la primera unidad como microlección: estas proyecciones no demuestran equivalencia entre los conceptos.

Evolución propuesta: revisar esas proyecciones al admitir fases y propósitos propuestos, preservando evidencia y autoridad. No corregir el modelo sólo cambiando nombres mientras se mantiene una conversión pedagógica implícita en el borde editorial.

### Corte de compatibilidad acordado

La implementación inicial mantiene el almacenamiento y el recorrido Django existentes. El discriminante aditivo acordado es `unit_kind`, con valores `project_review`, `declared_session` y `unknown`: distingue la unidad de revisión del proyecto de una sesión declarada, conserva el contenido histórico y no promueve unidades antiguas de tipo desconocido a sesiones reales. Las instrucciones y los bloques con rol quedan separados de las actividades; la primera y la última instrucción no se convierten automáticamente en inicio y cierre.

El contrato estructural del candidato es `source_structure` con `schema_version: 1`, `phases` y `blocks`. Cada bloque conserva rol (`instruction`, `activity`, `resource`, `question`, `step`, `unassigned`, `heading` o `resource_heading`), `phase_id`, `parent_id` y evidencia por fragmento con `document_sha256`, `page_number`, `text_start`, `text_end` y `excerpt`. La lista de actividades histórica se alimenta sólo de delimitaciones explícitas de actividad; los demás bloques siguen visibles con su rol y no se cuentan como actividades. El verificador recomputa estos metadatos desde la fuente: coincidir acredita consistencia estructural con el detector, no revisión docente ni corrección pedagógica. Esta descripción de contrato no afirma que el candidato ya esté integrado o probado.

La propuesta de propósito se incorpora de forma opcional a la respuesta del mismo turno del modelo, mediante `purpose_proposal`, sin una llamada adicional y sin alterar el máximo de seis preguntas. El candidato distingue acción, contenido, ámbito, evidencias de acción/contenido/producto/evaluación y contraevidencia; las citas conservan página y texto literal. La frontera de validación debe comprobar identidad, localización, vínculo y alcance antes de guardar una propuesta pendiente.

El corte inicial sólo puede proponer sobre `general.proposito` vacío y no confirmado ni corregido. No sobrescribe un valor actual ni propaga el propósito a fases, sesiones o actividades; una formulación compuesta por el backend sigue siendo inferida. El mismo turno descuenta la propuesta admitida antes de elegir otra pregunta, sin presentar la propuesta como confirmada ni admitirla mediante citas de respuestas humanas.

La aceptación de este corte no valida semánticamente cualquier regla booleana del evaluador. Los apoyos independientes, las exclusiones de acciones y los casos de abstención deben exponerse y probarse como reglas del candidato; producir una argumentación o una explicación puede constituir aprendizaje, por lo que no se excluyen todos los verbos de producción sólo por su forma. Se conservan las respuestas anteriores sin propuesta y las decisiones humanas vigentes.

## 9. Cómo validar una implementación posterior

Este cambio sólo introduce documentación. Una implementación que adopte el modelo deberá aportar evidencia en capas separadas:

1. Contratos puros con texto y PDFs sintéticos: citas, ámbitos, continuaciones, identidad y rechazo de falsas equivalencias.
2. Integración del mismo documento: almacenamiento, reapertura, selección, cola, corrección, aprobación y proyección editorial, con casos de cero sesiones declaradas.
3. Navegador real del recorrido Django: caja única, guardado antes de avanzar, fallos, correcciones, pestañas y recuperación sin pérdida de texto.
4. Evaluación semántica separada: atribución de propósito, actividad y anexo comparada con revisión humana. Verificar forma o encontrar una cita no mide esa calidad.
5. Si se autoriza una llamada real: modelo, transporte, fuente permitida, solicitud y resultado observados, sin extrapolar un doble offline a calidad real ni un smoke sintético a permisos sobre documentos privados.

No se añade un ADR sólo por crear un glosario. Las relaciones estructurales todavía abiertas y los puentes de compatibilidad deben discutirse y comprobarse antes de convertirlos en una decisión arquitectónica difícil de revertir.

## 10. Fuentes y puntos de lectura

Método de modelado utilizado: [domain-modeling de Matt Pocock](https://github.com/mattpocock/skills/blob/4588b32ecab9ecc9fc8cc6b6c5e7d675b6004b0d/skills/engineering/domain-modeling/SKILL.md), fijado al commit `4588b32ecab9ecc9fc8cc6b6c5e7d675b6004b0d`, y su [formato de glosario](https://github.com/mattpocock/skills/blob/4588b32ecab9ecc9fc8cc6b6c5e7d675b6004b0d/skills/engineering/domain-modeling/GLOSSARY-FORMAT.md). Sus reglas se aplican aquí separando definiciones breves de escenarios, contratos e implementación.

Las referencias públicas siguientes están fijadas a la cabeza `82f7676e8d964f5fbf53ebac40c1d55405351f27` del [PR #159](https://github.com/eliancanul/AulaLista/pull/159). Los cambios candidatos descritos arriba no se atribuyen a esa versión publicada.

Puntos de código y documentación inspeccionados:

- [source_interpreter.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/source_interpreter.py): `SourceReference`, `InterpretedField`, `SessionPlan`, `SessionActivity`, `AnnexReference`, `ImportDossier` y cola operativa.
- [source_segments.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/source_segments.py), [overview_fields.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/overview_fields.py) y [verification.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/verification.py): límites de fuente, roles y verificación.
- [interpretation_schema.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/interpretation_schema.py) e [interpretation_service.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/interpretation_service.py): adaptación a extracción, propuesta y desconocido.
- [teacher_review.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/teacher_review.py), [teacher_review_provider.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/teacher_review_provider.py) y [teacher_review_source.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/teacher_review_source.py): conversación, autoridad y fuente literal.
- [models.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/models.py) y [approval_commands.py](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/curriculum/approval_commands.py): persistencia y aprobación separada de publicación.
- [Contrato de revisión docente](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/docs/teacher-review.md) y [modelo de datos](DATABASE.md). El contrato candidato de aceptación del mismo documento sigue pendiente de publicación.
- [Pruebas de roles literales](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/tests/test_night_source_roles.py) y [pruebas de interpretación](https://github.com/eliancanul/AulaLista/blob/82f7676e8d964f5fbf53ebac40c1d55405351f27/tests/test_sprint_interpretation.py): protecciones existentes; su lectura no se presenta como una nueva ejecución.
