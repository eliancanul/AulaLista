# AulaLista

AulaLista es un nodo educativo local para ofrecer actividades de aprendizaje cuando no hay acceso a Internet. Su contenido público está gobernado por personas y su funcionamiento inicial debe poder demostrarse sin alumnado real ni afirmar validación pedagógica no realizada.

**Instalación local**:
Cada instalación local de AulaLista representa una sola `School`. Tiene una
única `School` configurada y una sola persona `Director` que pertenece a ella y
la administra dentro de esa instalación. No se modelan adscripciones de una
misma persona o entidad entre varias escuelas. Docentes, `ClassroomGroup`,
`ClassroomSession`, resultados y estadísticas de la instalación pertenecen
exclusivamente a esa `School`.
_Avoid_: instalación multi-escuela, Director compartido entre escuelas,
pertenencia institucional implícita.

## Coordinación institucional

**Modalidad pedagógica**:
Configuración institucional que Dirección elige y confirma para la `School`.
AulaLista admite primaria, secundaria general, secundaria técnica y
telesecundaria. El técnico instalador sólo configura la infraestructura y los
parámetros autorizados; no elige la modalidad ni decide adscripciones.
_Avoid_: modalidad elegida por el instalador, nivel inferido por el sistema,
política pedagógica automática.

**School**:
Ámbito institucional único de la instalación local. Conserva salones,
adscripciones, auditoría y la historia curricular institucional aunque cambie la
persona con autoridad sobre él; esos registros sólo se archivan, no se borran
desde la interfaz ordinaria. Una instalación tiene exactamente una `School` y
una sola persona `Director`; no contiene por sí mismo un roster estudiantil.
_Avoid_: propiedad del Director, cuenta institucional, escuela secundaria en la
misma instalación, borrado histórico.

**Director**:
Persona humana única de la instalación, perteneciente a la `School` configurada,
autorizada para decidir adscripciones docentes y acciones de coordinación
dentro de ella. Su autoridad institucional no incluye administrar
credenciales ni publicar currícula; su cuenta puede desactivarse sin borrar la
huella institucional mínima de sus acciones históricas.
_Avoid_: propietario de la Escuela, administrador técnico, Director de varias
escuelas en la misma instalación, cuenta eliminada.

**PlatformAdministrator**:
Persona responsable de configuración, cuentas, credenciales, roles y estado
técnico. Esa capacidad no le concede autoridad pedagógica para decidir
adscripciones, interpretar avances ni publicar currícula.
_Avoid_: Director, autoridad editorial.

**Importación institucional**:
Carga de información de la única `School` configurada, que puede preparar grupos
y adscripciones sin crear otra escuela ni cuentas docentes nuevas.
_Avoid_: importación multi-escuela, alta automática de cuentas.

**Vista previa de importación**:
Revisión que no escribe datos, muestra candidatos y conflictos explícitos, y
requiere confirmación de Dirección para resolver homónimos; una ambigüedad sin
confirmar no se aplica y repetir el mismo archivo no duplica registros.
_Avoid_: coincidencia automática, escritura durante preview, duplicado por reintento.

**TeacherAssignment**:
Relación institucional dentro de una `School` que vincula una cuenta docente
existente con un `ClassroomGroup` y conserva función o materia opcional, vigencia
y estado. No tiene una cardinalidad universal: puede haber cero, una o varias
adscripciones activas para un grupo según la modalidad. En primaria, la regla
general es una persona docente titular por grupo, con especialistas permitidos;
en secundaria general o técnica puede haber varias personas docentes por grupo
y una misma persona en varios grupos, diferenciadas por materia o función; en
telesecundaria una persona docente puede cubrir varias materias del grupo.
Reasignar crea una historia nueva y no sobrescribe la anterior. Al terminar una
adscripción cesa el acceso operativo al grupo, sus sesiones y resultados; la
autoría curricular histórica permanece y Dirección conserva la auditoría y los
agregados institucionales. No equivale a autoría, propiedad de currícula ni
propiedad del salón, y su historia sólo se archiva, no se borra desde la
interfaz ordinaria.
_Avoid_: creador del salón, propietario docente, regla única para todas las
modalidades, reasignación que borra historia.

**CoordinationAction**:
Siguiente decisión o paso institucional confirmado por una persona autorizada, con responsable, fecha objetivo y estado. Puede apoyarse en un resumen agregado, pero no es una inferencia, alerta ni decisión automática.
_Avoid_: recomendación de IA, score de riesgo, evaluación laboral.

**ClassroomRoadmapSummary**:
Proyección agregada por salón y periodo que declara su fuente, actualización y
datos faltantes; puede mostrar posición agregada del roadmap y actividades
trabajadas o participación agregada. No es progreso nominal, ranking,
diagnóstico ni evidencia de aprendizaje.
_Avoid_: expediente estudiantil, semáforo de riesgo, clasificación de docentes.

**Vista institucional de Dirección**:
Consulta autorizada de grupos activos o archivados, adscripciones e historial,
sesiones, resúmenes agregados, auditoría y exportación institucional agregada;
no muestra alias, dispositivos, respuestas individuales, perfiles de alumnado,
riesgo, rankings, predicciones ni comparaciones docentes o editoriales.
_Avoid_: CRM nominal, expediente estudiantil, tablero de riesgo.

**Exportación institucional agregada**:
Salida autorizada con etiquetas y nombres de presentación institucionales,
sesiones, adscripciones, auditoría y agregados por grupo o roadmap. Excluye
username, correo, UUID, claves pseudónimas, IDs de base de datos y cualquier
identificador técnico o capa estudiantil.
_Avoid_: exportación nominal, volcado de base de datos, resultado individual.

## Currículo y publicación

**CurriculumPackage**:
Paquete estructurado y editable que reúne una microlección, actividades de práctica, fuentes autorizadas, respuestas esperadas y límites de asistencia. Es un borrador de trabajo hasta que una persona revisora editorial lo aprueba y publica.
_Avoid_: curso, contenido aprobado.

**PublishedPackageSnapshot**:
Versión publicada e inmutable de un `CurriculumPackage`, identificable para que una actividad pueda conservar exactamente el contenido con el que comenzó.
_Avoid_: revisión publicada, copia viva.

**EditorialReviewer**:
Persona humana que revisa, aprueba y publica un paquete. El rol queda preparado para que lo ocupe una docente real; ningún sistema automático o modelo de lenguaje tiene esa autoridad.
_Avoid_: aprobador automático, evaluador de IA.

**DemoPackage**:
Paquete sintético usado para verificar el software. No representa una planeación autorizada ni debe presentarse como contenido curricular validado para alumnado.
_Avoid_: paquete piloto, material aprobado.

**TeacherWorkflow**:
Recorrido editorial y operativo mediante el que una persona docente selecciona un tema, prepara una actividad, la revisa, la publica y ejecuta una sesión. Sus estados expresan autoridad y disponibilidad, no progreso automático del aprendizaje.
_Avoid_: flujo automático, pipeline de IA.

Cada `CurriculumPackage`, propuesta de importación y borrador asistido pertenece
a la cuenta de la maestra que lo creó. Listar, revisar, editar, publicar, incluir
en un roadmap o lanzar una actividad conserva ese límite de propiedad. La
propiedad no concede publicación automática: `EditorialReviewer` y la revisión
humana continúan siendo obligatorios.

**CurriculumProgress**:
Registro del tema curricular que una persona docente confirma como actual o trabajado dentro de un curso. Puede recibir una sugerencia del sistema, pero no avanza por crear, publicar o cerrar una actividad sin confirmación humana.
_Avoid_: dominio automático, avance de IA.

**PublishedRoadmapSnapshot**:
Roadmap publicado e inmutable con unidades, lecciones y actividades en orden determinista. Cada actividad referencia el `PublishedPackageSnapshot` exacto que contiene sus reglas y contenido; por eso un recorrido puede combinar varios paquetes. Una sesión fija este roadmap y su snapshot base; una corrección posterior sólo sirve para sesiones nuevas.
_Avoid_: roadmap vivo, secuencia inferida.

**StudentRoadmapProgress**:
Recorrido individual, temporal y pseudónimo que registra actividades completadas y calcula la siguiente actividad habilitada leyendo la secuencia del roadmap y el snapshot de paquete referenciado por cada actividad. La decisión de compleción y los reactivos correctos se persisten al responder; no dependen de la caché efímera. No es cuenta, expediente, aprobación curricular, dominio ni calificación; al cerrar la sesión se elimina con el turno temporal.
_Avoid_: progreso docente automático, identidad estudiantil.

**GroupRoadmapProgress**:
Registro temporal 1:1 con una `ClassroomSession` que conserva el cursor y las
actividades completadas por el grupo sobre el `PublishedRoadmapSnapshot` fijado.
Todos los turnos de la sesión leen el mismo estado; una respuesta válida puede
avanzar el grupo y una maestra puede adelantarlo manualmente desde el control
autenticado. No sustituye `CurriculumProgress` ni conserva identidad.
_Avoid_: progreso individual, dominio, aprobación curricular.

**ActivityDraft**:
Propuesta editable de actividad asociada a un tema y a fuentes curriculares concretas. Puede ser producida con asistencia automática, pero no es publicable hasta atravesar la revisión y aprobación humana.
_Avoid_: actividad aprobada, contenido generado publicado.

**ActivityReview**:
Estado en el que una persona docente verifica objetivo, ejemplos, problemas, respuestas, explicaciones y fuentes de una actividad antes de autorizar su publicación.
_Avoid_: validación de IA, revisión automática.

## Actividad de aula

**ClassroomSession**:
Ejecución temporal de una actividad publicada para un conjunto de participantes
y dispositivos. Conserva la versión publicada y la referencia institucional
estable al `ClassroomGroup` con la que comenzó, incluso cuando queda archivada.
_Avoid_: curso, instancia editable, sesión huérfana.

Una `ClassroomSession` puede estar en preparación mientras una persona revisa su distribución; solo una confirmación humana explícita la vuelve activa y disponible para actividad estudiantil. La sesión conserva la maestra que la preparó, un `PublishedPackageSnapshot` base y, cuando usa camino, un `PublishedRoadmapSnapshot` inmutables. El roadmap congela además la referencia al snapshot de paquete de cada actividad: cambiar el contenido editorial no modifica una sesión ya iniciada.

**ClassroomGroup**:
Salón institucional perteneciente a una `School`, cuya identidad estable combina
ciclo escolar, modalidad, grado, clave de grupo y turno; su nombre visible puede
editarse y no define identidad ni idempotencia. Agrupa `ClassroomSession`, no
contiene lista, cuenta, nombre ni otro dato de alumnos, y sus grados se validan
según la modalidad: primaria 1–6 y secundaria general, técnica o telesecundaria
1–3. Al finalizar el ciclo puede archivarse y su historia no se pierde.
_Avoid_: propiedad del Director, propiedad de la maestra, lista nominal, borrado
histórico.

**LocalDeviceQueue**:
Cola local asociada a un `DeviceAssignment`, identificada mediante un
identificador opaco del nodo y limitada por una capacidad asignada. Los
dispositivos son medios temporales y pueden ser compartidos; ninguna modalidad
pedagógica implica que cada alumno tenga un celular personal. No contiene
nombres, matrículas ni otras identidades estudiantiles.
_Avoid_: lista nominal, grupo por nombre, celular personal obligatorio.

**StudentTurn**:
Intento individual realizado durante una `ClassroomSession`. Genera una `participant_key` UUID aleatoria, nunca derivada del apodo, dispositivo o nombre. El apodo sólo puede existir durante la sesión y no equivale a identidad.
_Avoid_: cuenta estudiantil, identidad del estudiante.

**DeviceAssignment**:
Relación temporal que indica en qué dispositivo puede continuar un `StudentTurn`. Es una asignación de uso, no una identidad.
_Avoid_: propiedad del dispositivo, inicio de sesión personal.

## Práctica y resultados

**DeterministicPracticeResult**:
Resultado calculado mediante reglas explícitas del paquete publicado para una respuesta concreta. La misma respuesta bajo las mismas reglas produce el mismo resultado.
_Avoid_: calificación de IA, evaluación generativa.

**RegulatedAssistance**:
Ayuda autorizada por el paquete publicado, como una pista, una analogía o una explicación final. Puede apoyar la actividad, pero solicitarla no cambia por sí mismo la puntuación ni constituye evidencia de aprendizaje.
_Avoid_: tutor autónomo, respuesta libre.

**PseudonymousResult**:
Métrica individual que puede conservarse después del cierre sin la relación temporal entre nombre, dispositivo e intento. Incluye sólo la `participant_key` para agrupar actividades del mismo participante; en UI se muestra una etiqueta opaca corta, nunca el UUID completo, y no requiere nombre, correo, matrícula ni contraseña.
_Avoid_: expediente estudiantil, historial personal.

**PseudonymousSurveyResponse**:
Una valoración numérica de 1 a 5 estrellas para la dinámica. No se vincula a turno, dispositivo ni participante; la maestra sólo consulta el promedio grupal.
_Avoid_: comentario libre, respuesta individual, evaluación del alumno.

**Archivado institucional**:
Estado histórico de una `School`, `ClassroomGroup`, `TeacherAssignment`,
`ClassroomSession` u objeto curricular institucional que conserva su referencia,
auditoría y autoría sin aparecer como activo en la operación ordinaria.
_Avoid_: borrado duro, purga de datos estudiantiles, TTL automático.

**Capa estudiantil temporal**:
Datos de participación y uso que incluyen turnos, alias, asignaciones de
dispositivo, cachés, respuestas libres y resultados o encuestas seudónimos; se
purga según la política de privacidad aunque exista archivado institucional.
_Avoid_: expediente estudiantil permanente, retención por archivar.

**Transición de Dirección**:
Cambio institucional autorizado que desactiva el acceso operativo de la persona
saliente, activa a la nueva persona única y conserva la autoría histórica y la
auditoría mínima de ambas.
_Avoid_: transferencia de propiedad, borrado del Director anterior.
