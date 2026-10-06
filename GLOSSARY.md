# AulaLista

AulaLista prepara y ofrece actividades de aprendizaje en una instalación educativa local, incluso sin Internet. La interpretación de una planeación conserva sus fuentes e incertidumbres, y las decisiones pedagógicas y editoriales pertenecen a personas autorizadas.

## Lenguaje de la fuente y la planeación

**Documento fuente**:
Documento que aporta el contenido original de una planeación o de sus recursos. Es distinto de la interpretación que AulaLista hace de él.
_Avoid_: planeación interpretada, contenido aprobado.

**Versión de fuente**:
Contenido exacto de un documento fuente sobre el que se realizó una interpretación. Cambiar el documento produce otra versión de fuente, aunque conserve el nombre.
_Avoid_: último archivo, versión del dossier.

**Página física**:
Página en la posición que ocupa dentro de una versión de fuente. Puede tener una numeración impresa diferente o no tener ninguna.
_Avoid_: número impreso, sesión, anexo.

**Fragmento fuente**:
Porción localizada del contenido de una versión de fuente. Una continuación en otra página conserva otro fragmento, aunque ambos pertenezcan a la misma unidad pedagógica.
_Avoid_: resumen, valor inferido, página completa por defecto.

**Cita de fuente**:
Fragmento literal localizado en una versión de fuente y utilizado como apoyo de una afirmación. Encontrarlo acredita su presencia, pero no prueba por sí solo la afirmación ni su ámbito.
_Avoid_: explicación del modelo, evidencia de aprendizaje, dato confirmado.

**Planeación**:
Organización pedagógica del trabajo previsto y de sus recursos, tal como se presenta en una fuente y se revisa por una persona docente. No presupone un formato, una duración ni una división en sesiones.
_Avoid_: PDF, paquete publicado, secuencia de sesiones obligatoria.

**Proyecto**:
Unidad pedagógica reconocible dentro de una planeación, con identidad e intención propias. Su existencia y sus límites se apoyan en la fuente o en una decisión docente explícita.
_Avoid_: nombre del archivo, sesión, paquete curricular.

**Fase**:
División que la planeación identifica como fase de su organización pedagógica. Una fase no establece por sí misma cuántas sesiones habrá.
_Avoid_: sesión, día de clase, momento equivalente por defecto.

**Momento pedagógico**:
Tramo del trabajo pedagógico, como inicio, desarrollo o cierre, cuyo ámbito se reconoce en la planeación. Su relación con una fase, una actividad o una sesión debe estar fundamentada.
_Avoid_: fase por defecto, sesión, intervalo horario inferido.

**Sesión declarada**:
Unidad de trabajo que la fuente delimita explícitamente como una sesión de la planeación. Una planeación puede tener cero sesiones declaradas sin carecer de fases o actividades.
_Avoid_: fase, página, contenedor de revisión, ClassroomSession.

**Actividad de planeación**:
Unidad de trabajo prevista en la planeación, reconocible por su tarea o por las acciones que propone. Puede existir sin una sesión declarada y no es todavía una actividad publicada para el aula.
_Avoid_: cada instrucción, pregunta de aclaración, ActivityDraft.

**Instrucción de planeación**:
Enunciado que orienta una acción de la persona docente o del alumnado dentro del trabajo previsto. Varias instrucciones pueden integrar una actividad, y una instrucción puede describir una acción auxiliar.
_Avoid_: actividad por defecto, reactivo, evidencia de aprendizaje.

**Anexo**:
Recurso complementario identificado en relación con una planeación. Puede ocupar una o varias páginas y su presencia no determina a qué actividad pertenece.
_Avoid_: página, lámina de una sola página, actividad automáticamente asociada.

**Hoja de actividad**:
Recurso que contiene consignas, ejercicios o espacios de trabajo para una actividad. El nombre describe su función y no limita su extensión a una página física.
_Avoid_: página física, sesión, respuesta resuelta.

**Continuación de fuente**:
Relación por la que dos fragmentos pertenecen a una misma unidad de contenido a través de un salto de página u otra interrupción material. La cercanía de los fragmentos es una pista, no una confirmación suficiente.
_Avoid_: nuevo anexo por página, unión automática de páginas.

**Asociación de recurso**:
Relación fundamentada entre una actividad o unidad de planeación y un anexo u otro recurso. Reconocer ambos extremos no equivale a haber confirmado la relación.
_Avoid_: coincidencia por título, pertenencia por proximidad, recurso confirmado.

**Ámbito pedagógico**:
Proyecto, fase, momento, sesión declarada o actividad al que corresponde una afirmación de la planeación. Un dato general no se atribuye automáticamente a todos sus componentes.
_Avoid_: página, campo global por defecto, primera sesión.

**Propósito de aprendizaje**:
Intención acerca de lo que el alumnado trabajará, comprenderá o será capaz de hacer en un ámbito pedagógico. Puede estar expresada literalmente o formularse como propuesta interpretativa apoyada en la fuente.
_Avoid_: producto por entregar, finalidad intercambiable, aprendizaje demostrado.

**Finalidad del proyecto**:
Resultado o intención general que la planeación atribuye al proyecto. Puede aportar evidencia para un propósito de aprendizaje, pero no constituye automáticamente ese propósito.
_Avoid_: propósito de aprendizaje idéntico por defecto, título, producto obligatorio.

**Producto esperado**:
Resultado material, expresión o actuación que una actividad pide elaborar o realizar. Su elaboración no demuestra por sí sola un aprendizaje ni define todo el propósito de aprendizaje.
_Avoid_: aprendizaje logrado, propósito, aprobación pedagógica.

## Lenguaje de interpretación y revisión

**Dossier de interpretación**:
Conjunto revisable de unidades de planeación, valores, citas, asociaciones y pendientes obtenido de una versión de fuente. Conserva tanto lo reconocido como las incertidumbres de la interpretación.
_Avoid_: fuente original, planeación aprobada, respuesta del modelo.

**Valor extraído**:
Dato atribuido a un ámbito y a un papel de la planeación mediante evidencia literal suficiente. Copiar palabras presentes en el documento no basta para establecer esa atribución.
_Avoid_: dato verdadero por coincidencia, valor confirmado, inferencia literal.

**Propuesta interpretativa**:
Interpretación que explica un valor o una relación mediante evidencia de la fuente, sin presentarlo como declaración literal de esta. Sigue siendo revisable aunque una comprobación automática no encuentre conflictos.
_Avoid_: extracción, cita, hecho confirmado, aprobación automática.

**Dato docente**:
Información aportada explícitamente por una persona docente para el ámbito que está revisando. Conserva esa procedencia aunque complete o corrija un dato de la planeación.
_Avoid_: cita del PDF, extracción, respuesta generada.

**Confirmación de dato**:
Decisión explícita de una persona docente que acepta un valor o una relación para el ámbito revisado. No equivale a aprobar la importación ni a publicar contenido.
_Avoid_: cita localizada, respuesta guardada, aprobación editorial.

**Pendiente de revisión**:
Valor, propuesta o relación que aún necesita una decisión docente. No todo pendiente representa un dato ausente ni exige una pregunta automática.
_Avoid_: faltante obligatorio, error del documento, cuestionario.

**Bloqueo de aclaración**:
Ausencia necesaria o conflicto que requiere resolución para continuar el recorrido correspondiente. Una confirmación pendiente o un dato opcional vacío no son bloqueos por ese solo hecho.
_Avoid_: cualquier pendiente, dato que el parser no encontró, aprobación rechazada por la IA.

**Aclaración docente**:
Conversación acotada que ayuda a resolver bloqueos de una planeación mediante preguntas adaptativas y respuestas docentes conservadas. Es parte de la preparación y no concede aprobación ni publicación.
_Avoid_: interrogatorio completo, revisión editorial, validación pedagógica.

**Pregunta de aclaración**:
Pregunta dirigida a uno o varios destinos relacionados de la misma aclaración docente. Su propósito es resolver un foco concreto, no ocultar un cuestionario de asuntos distintos.
_Avoid_: llamada al modelo, campo, catálogo fijo.

**Respuesta docente guardada**:
Texto que la persona docente ha aportado y que ya quedó conservado para una pregunta de aclaración. Estar guardado no significa que todos sus datos hayan sido aplicados o confirmados.
_Avoid_: borrador sin guardar, cita de fuente, aprobación.

**Versión revisada**:
Estado del dossier que conserva las decisiones y cambios aceptados hasta ese punto junto con su procedencia. Corregir una interpretación crea otra versión revisada sin alterar retrospectivamente la fuente.
_Avoid_: nueva fuente, publicación, sobrescritura de historia.

**Aprobación docente de importación**:
Aceptación explícita, por una persona docente autorizada, de una versión concreta del dossier y su fuente para preparar contenido editorial. No vuelve público el contenido ni sustituye la revisión editorial.
_Avoid_: dato confirmado, conversación terminada, publicación.

**Aprobación editorial**:
Decisión de una persona EditorialReviewer que acepta el contenido de un CurriculumPackage para su publicación. Es distinta de resolver campos de una importación y de hacer el contenido disponible en el aula.
_Avoid_: validación automática, aprobación de importación, publicación implícita.

**Publicación**:
Acción editorial autorizada que hace disponible una versión inmutable del contenido para su uso. No ocurre por interpretar una fuente, guardar una respuesta ni aprobar una importación.
_Avoid_: guardado, revisión terminada, activación de sesión.

## Lenguaje institucional

**Instalación local**:
Ámbito operativo de AulaLista que corresponde a una sola School y a una única persona Director perteneciente a ella. Sus grupos, adscripciones, sesiones y agregados pertenecen exclusivamente a esa School.
_Avoid_: instalación multi-escuela, Director compartido, pertenencia implícita.

**Modalidad pedagógica**:
Configuración institucional elegida y confirmada por Dirección para la School entre primaria, secundaria general, secundaria técnica o telesecundaria. No es una decisión del instalador ni una inferencia del sistema.
_Avoid_: modalidad técnica, nivel inferido, política automática.

**School**:
Institución única de la instalación local, que conserva grupos, adscripciones, auditoría e historia curricular aunque cambie su Director. No es propiedad de esa persona ni contiene por sí misma una lista nominal de alumnado.
_Avoid_: cuenta institucional, propiedad del Director, segunda escuela local.

**Director**:
Persona humana única que administra la coordinación institucional y decide adscripciones dentro de la School a la que pertenece. Esa autoridad no incluye administrar credenciales ni publicar currícula.
_Avoid_: propietario de la School, administrador técnico, autoridad editorial automática.

**PlatformAdministrator**:
Persona responsable de configuración, cuentas, credenciales, roles y estado técnico de la instalación. Esa responsabilidad no le otorga autoridad pedagógica o editorial.
_Avoid_: Director, EditorialReviewer, decisor de adscripciones.

**Importación institucional**:
Carga de información de la School configurada que puede preparar grupos y adscripciones. No crea otra School ni cuentas docentes nuevas.
_Avoid_: importación curricular, importación multi-escuela, alta automática de docentes.

**Vista previa de importación**:
Revisión de candidatos y conflictos antes de aplicar una importación institucional. No modifica los registros y conserva las ambigüedades para confirmación de Dirección.
_Avoid_: coincidencia automática, importación ya aplicada, autorización implícita.

**TeacherAssignment**:
Adscripción vigente o histórica de una cuenta docente a un ClassroomGroup, con función o materia cuando corresponda a la modalidad pedagógica. No implica autoría ni propiedad curricular, y reasignar no borra la historia de la relación anterior.
_Avoid_: creador del grupo, propietario docente, titular único universal.

**CoordinationAction**:
Decisión o siguiente paso institucional confirmado por una persona autorizada, con responsable, fecha objetivo y estado. No es una inferencia ni una evaluación laboral automática.
_Avoid_: alerta de IA, score de riesgo, recomendación confirmada por defecto.

**Solicitud de apoyo**:
Petición manual y no nominal de una maestra a Dirección sobre recursos, operación, comunicación general con familias o apoyo técnico para un ClassroomGroup. Conserva responsable, fecha objetivo y estado, sin convertirse en un caso individual de alumnado.
_Avoid_: CRM familiar, reporte disciplinario nominal, recomendación automática.

**Diccionario de métricas institucional**:
Definición visible de los conteos de actividades trabajadas, participantes únicos, posición del roadmap y sesiones cerradas, con fuente, periodo, actualización y disponibilidad. No representa evidencia de aprendizaje ni admite convertir datos ausentes en cero.
_Avoid_: score, ranking, diagnóstico, progreso inferido.

**ClassroomRoadmapSummary**:
Resumen agregado por grupo y periodo de la posición del roadmap, actividades trabajadas o participación, con su fuente y datos faltantes. No es un registro nominal ni un diagnóstico de aprendizaje.
_Avoid_: expediente estudiantil, semáforo de riesgo, ranking docente.

**Vista institucional de Dirección**:
Consulta autorizada de grupos, adscripciones, sesiones, historia institucional, auditoría y agregados. Excluye identidades, respuestas individuales, perfiles, predicciones y comparaciones de personas docentes o alumnado.
_Avoid_: CRM nominal, tablero de riesgo, expediente individual.

**Exportación institucional agregada**:
Salida autorizada de información institucional y agregados por grupo o roadmap, identificada con nombres de presentación institucionales. Excluye la capa estudiantil temporal y los identificadores técnicos de personas o registros.
_Avoid_: resultado individual, volcado de datos, exportación nominal.

## Lenguaje editorial y curricular

**CurriculumPackage**:
Paquete editable que reúne una microlección, actividades de práctica, fuentes autorizadas, respuestas esperadas y límites de asistencia. Es un borrador hasta que atraviesa revisión, aprobación editorial y publicación.
_Avoid_: curso, planeación de origen, contenido aprobado por generación.

**PublishedPackageSnapshot**:
Versión publicada e inmutable de un CurriculumPackage. Permite conservar exactamente el contenido con el que comenzó una actividad de aula.
_Avoid_: revisión editorial viva, última versión automática.

**EditorialReviewer**:
Persona humana autorizada para revisar, aprobar y publicar un CurriculumPackage. Ningún modelo o sistema automático tiene esa autoridad.
_Avoid_: aprobador automático, evaluador de IA, Director por defecto.

**DemoPackage**:
CurriculumPackage sintético destinado a verificar el funcionamiento del software. No representa una planeación autorizada ni validación pedagógica con alumnado.
_Avoid_: paquete piloto validado, material aprobado para alumnado.

**TeacherWorkflow**:
Recorrido por el que una persona docente selecciona un tema, prepara una actividad, la revisa y publica, y ejecuta una ClassroomSession. Sus estados expresan decisiones y disponibilidad, no aprendizaje automático.
_Avoid_: pipeline de IA, aprobación implícita, avance automático.

**CurriculumProgress**:
Registro del tema curricular que una persona docente confirma como actual o trabajado dentro de un curso. No cambia sólo por crear, publicar o cerrar una actividad.
_Avoid_: dominio del alumnado, avance de IA, actividad completada.

**PublishedRoadmapSnapshot**:
Recorrido publicado e inmutable de unidades, lecciones y actividades, cada una ligada a su PublishedPackageSnapshot exacto. Una corrección publicada después sólo sirve para nuevas ClassroomSession.
_Avoid_: roadmap vivo, secuencia inferida, un solo paquete obligatorio.

**StudentRoadmapProgress**:
Recorrido individual, temporal y pseudónimo que registra actividades completadas dentro del roadmap fijado a una ClassroomSession. No representa identidad, expediente, aprobación curricular, dominio ni calificación.
_Avoid_: cuenta estudiantil, progreso docente automático, historial personal.

**GroupRoadmapProgress**:
Posición y actividades completadas del grupo dentro del roadmap fijado a una ClassroomSession. Es un estado temporal compartido y no sustituye CurriculumProgress.
_Avoid_: progreso individual, identidad, aprobación curricular.

**ActivityDraft**:
Propuesta editable de actividad asociada a un tema y a fuentes curriculares concretas. Puede recibir asistencia automática y necesita revisión humana antes de publicarse.
_Avoid_: actividad de planeación literal, actividad aprobada, contenido generado publicado.

**ActivityReview**:
Revisión humana del objetivo, ejemplos, problemas, respuestas, explicaciones y fuentes de una ActivityDraft antes de autorizar su publicación. No es una comprobación automática ni una medición del aprendizaje.
_Avoid_: validación de IA, aclaración docente, revisión automática.

## Lenguaje de aula y resultados

**ClassroomSession**:
Ejecución temporal de contenido publicado para participantes y dispositivos, vinculada a un ClassroomGroup y a las versiones publicadas con las que comenzó. Sólo una confirmación humana explícita la vuelve activa y disponible al alumnado.
_Avoid_: sesión declarada, fase, curso, contenido editorial vivo.

**ClassroomGroup**:
Salón institucional de una School identificado por ciclo, modalidad, grado, clave de grupo y turno, con un nombre visible que puede cambiar. Agrupa ClassroomSession y no contiene una lista nominal de alumnado.
_Avoid_: propiedad de la maestra, nombre como identidad, roster estudiantil.

**LocalDeviceQueue**:
Cola temporal de participación asociada a la capacidad asignada a un dispositivo de la instalación. No requiere dispositivos personales ni conserva identidades del alumnado.
_Avoid_: lista nominal, grupo por nombre, celular personal obligatorio.

**StudentTurn**:
Intento individual y temporal de participación durante una ClassroomSession, con una clave pseudónima independiente del nombre o dispositivo. Un apodo de sesión no constituye identidad estudiantil.
_Avoid_: cuenta, identidad del estudiante, propiedad del dispositivo.

**DeviceAssignment**:
Asignación temporal de uso que permite continuar un StudentTurn en un dispositivo. No identifica a la persona ni acredita propiedad del dispositivo.
_Avoid_: inicio de sesión personal, dueño del dispositivo, identidad.

**DeterministicPracticeResult**:
Resultado de una respuesta bajo las reglas explícitas de un PublishedPackageSnapshot. La misma respuesta bajo las mismas reglas produce el mismo resultado.
_Avoid_: calificación de IA, evaluación generativa, validación pedagógica.

**RegulatedAssistance**:
Ayuda permitida por el contenido publicado, como una pista, analogía o explicación final. Solicitarla no cambia por sí solo la puntuación ni demuestra aprendizaje.
_Avoid_: tutor autónomo, respuesta libre, evaluación del alumno.

**PseudonymousResult**:
Resultado que puede conservarse después del cierre sin la relación temporal entre nombre, dispositivo e intento. Permite agrupar actividades de una misma participación mediante una clave pseudónima, sin formar un expediente personal.
_Avoid_: expediente estudiantil, identidad, historial personal.

**PseudonymousSurveyResponse**:
Valoración de una a cinco estrellas sobre la dinámica, sin vínculo a un turno, dispositivo o participante. La consulta docente muestra únicamente el promedio grupal.
_Avoid_: comentario libre, valoración individual visible, evaluación del alumno.

**Archivado institucional**:
Estado histórico que conserva las relaciones, auditoría y autoría institucionales fuera de la operación activa. No justifica retener la capa estudiantil temporal.
_Avoid_: borrado histórico, purga estudiantil, retención indefinida de participantes.

**Capa estudiantil temporal**:
Datos de participación y uso sujetos a la política de privacidad, incluidos turnos, apodos, asignaciones, respuestas y resultados seudónimos. El archivado institucional no prolonga su conservación.
_Avoid_: expediente permanente, historia institucional, retención por archivado.

**Transición de Dirección**:
Cambio autorizado de la persona Director que conserva la historia y auditoría institucionales y retira el acceso operativo de quien sale. No transfiere la propiedad de la School ni borra las acciones anteriores.
_Avoid_: transferencia de propiedad, borrado del Director anterior.
