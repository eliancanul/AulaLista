# AulaLista

AulaLista es un nodo educativo local para ofrecer actividades de aprendizaje cuando no hay acceso a Internet. Su contenido público está gobernado por personas y su funcionamiento inicial debe poder demostrarse sin alumnado real ni afirmar validación pedagógica no realizada.

## Coordinación institucional

**School**:
Ámbito institucional estable que conserva salones, adscripciones y auditoría aunque cambien las personas con autoridad sobre él. No contiene por sí mismo un roster estudiantil.
_Avoid_: propiedad del Director, cuenta institucional.

**Director**:
Persona humana autorizada para decidir adscripciones docentes y acciones de coordinación dentro de una `School`. Su autoridad institucional no incluye administrar credenciales ni publicar currícula.
_Avoid_: propietario de la Escuela, administrador técnico.

**PlatformAdministrator**:
Persona responsable de cuentas, credenciales, roles y cambios técnicos. Esa capacidad no le concede autoridad para decidir adscripciones docentes ni publicación curricular.
_Avoid_: Director, autoridad editorial.

**TeacherAssignment**:
Relación institucional con vigencia e historia que vincula una cuenta docente existente con un `ClassroomGroup` dentro de una `School`. No equivale a autoría, propiedad de currícula ni propiedad del salón.
_Avoid_: creador del salón, propietario docente.

**CoordinationAction**:
Siguiente decisión o paso institucional confirmado por una persona autorizada, con responsable, fecha objetivo y estado. Puede apoyarse en un resumen agregado, pero no es una inferencia, alerta ni decisión automática.
_Avoid_: recomendación de IA, score de riesgo, evaluación laboral.

**ClassroomRoadmapSummary**:
Proyección agregada por salón y periodo que declara su fuente, actualización y datos faltantes. No es progreso nominal, ranking, diagnóstico ni evidencia de aprendizaje.
_Avoid_: expediente estudiantil, semáforo de riesgo, clasificación de docentes.

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

**ActivityDraft**:
Propuesta editable de actividad asociada a un tema y a fuentes curriculares concretas. Puede ser producida con asistencia automática, pero no es publicable hasta atravesar la revisión y aprobación humana.
_Avoid_: actividad aprobada, contenido generado publicado.

**ActivityReview**:
Estado en el que una persona docente verifica objetivo, ejemplos, problemas, respuestas, explicaciones y fuentes de una actividad antes de autorizar su publicación.
_Avoid_: validación de IA, revisión automática.

## Actividad de aula

**ClassroomSession**:
Ejecución temporal de una actividad publicada para un conjunto de participantes y dispositivos. Una sesión conserva la versión publicada con la que comenzó.
_Avoid_: curso, instancia editable.

Una `ClassroomSession` puede estar en preparación mientras una persona revisa su distribución; solo una confirmación humana explícita la vuelve activa y disponible para actividad estudiantil. La sesión conserva la maestra que la preparó, un `PublishedPackageSnapshot` base y, cuando usa camino, un `PublishedRoadmapSnapshot` inmutables. El roadmap congela además la referencia al snapshot de paquete de cada actividad: cambiar el contenido editorial no modifica una sesión ya iniciada.

**ClassroomGroup**:
Salón institucional perteneciente a una `School`, distinguido por grado, grupo y una etiqueta legible. Agrupa `ClassroomSession`, pero no contiene lista, cuenta, nombre ni otro dato de alumnos.
_Avoid_: propiedad del Director, propiedad de la maestra, lista nominal.

**LocalDeviceQueue**:
Cola local asociada a un `DeviceAssignment`, identificada mediante un identificador opaco del nodo y limitada por una capacidad asignada. No contiene nombres, matrículas ni otras identidades estudiantiles.
_Avoid_: lista nominal, grupo por nombre.

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
Métrica individual conservada después del cierre sin la relación temporal entre nombre, dispositivo e intento. Incluye sólo la `participant_key` para agrupar actividades del mismo participante; en UI se muestra una etiqueta opaca corta, nunca el UUID completo. Es eliminable y no requiere nombre, correo, matrícula ni contraseña.
_Avoid_: expediente estudiantil, historial personal.

**PseudonymousSurveyResponse**:
Una valoración numérica de 1 a 5 estrellas para la dinámica. No se vincula a turno, dispositivo ni participante; la maestra sólo consulta el promedio grupal.
_Avoid_: comentario libre, respuesta individual, evaluación del alumno.
