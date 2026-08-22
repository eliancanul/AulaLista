# AulaLista

AulaLista es un nodo educativo local para ofrecer actividades de aprendizaje cuando no hay acceso a Internet. Su contenido público está gobernado por personas y su funcionamiento inicial debe poder demostrarse sin alumnado real ni afirmar validación pedagógica no realizada.

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

## Actividad de aula

**ClassroomSession**:
Ejecución temporal de una actividad publicada para un conjunto de participantes y dispositivos. Una sesión conserva la versión publicada con la que comenzó.
_Avoid_: curso, instancia editable.

**StudentTurn**:
Intento individual realizado durante una `ClassroomSession`. Usa un identificador aleatorio local y no equivale al nombre o apodo que pueda mostrarse temporalmente en la interfaz.
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
Métrica individual conservada después del cierre sin la relación temporal entre nombre, dispositivo e intento. Es eliminable y no requiere nombre, correo, matrícula ni contraseña.
_Avoid_: expediente estudiantil, historial personal.
