# School owns the institutional scope

Una `School`, no la cuenta de la persona Directora, conserva `ClassroomGroup`, `TeacherAssignment` y auditoría institucional. Dirección recibe autoridad para decidir adscripciones dentro de su ámbito, mientras `PlatformAdministrator` administra cuentas y roles sin heredar esa decisión; así un cambio de Director no mueve, reescribe ni pierde la historia de la Escuela.

## Límite de instalación

La unidad local desplegada de AulaLista representa una sola `School` configurada
y tiene exactamente una persona `Director`. Esa persona pertenece a la escuela
y la administra dentro de la instalación; no se modelan adscripciones
multi-escuela ni una Dirección compartida entre escuelas. Docentes,
`ClassroomGroup`, `ClassroomSession`, resultados y estadísticas quedan dentro
del ámbito exclusivo de esa `School`.

Este límite fija el alcance institucional del prototipo; no crea roster
estudiantil, identidad nominal ni autoridad editorial para Dirección.

## Decisión D2: modalidad y adscripción docente

AulaLista soporta, mediante configuración institucional, primaria, secundaria
general, secundaria técnica y telesecundaria. Dirección elige y confirma la
modalidad de su `School`; el técnico instalador sólo configura infraestructura y
parámetros autorizados. La elección pedagógica no se infiere de la instalación
ni se delega a la administración técnica.

`TeacherAssignment` no fija una cardinalidad universal. Puede haber cero, una o
varias adscripciones activas para un `ClassroomGroup`, siempre dentro de la
única `School`, según la modalidad:

- En primaria, la regla general es una persona docente titular por grupo, con
  especialistas permitidos.
- En secundaria general y técnica, un grupo puede tener varias personas
  docentes y una persona puede atender varios grupos; materia o función las
  diferencia.
- En telesecundaria, una persona docente puede cubrir varias materias del
  grupo.

Toda adscripción conserva función o materia opcional, vigencia y estado. Una
reasignación crea una relación histórica nueva y no sobrescribe la anterior.
Cuando termina una adscripción, cesa el acceso operativo al grupo, sus sesiones
y resultados; la autoría curricular histórica permanece, y Dirección conserva
la auditoría y los agregados institucionales.

### Tradeoff

Se rechaza imponer “una docente = un grupo” porque funciona como default de
primaria pero falsea la organización por materias de secundaria y la cobertura
multimateria de telesecundaria. También se rechaza asumir un dispositivo
personal por alumno: los dispositivos son medios temporales o compartidos y la
modalidad no determina una política de celulares.

## Decisión D3: retención institucional y transición de autoridad

`School`, `ClassroomGroup`, `TeacherAssignment`, `ClassroomSession`, la
auditoría y los objetos curriculares históricos son append-only o archivables.
La interfaz ordinaria no permite su borrado duro. Antes de archivar, cada sesión
debe conservar una referencia institucional estable a su grupo; archivar no
puede romper esa historia ni convertirla en una referencia nula (`SET_NULL`).

Archivar la institución no autoriza retener la capa estudiantil o temporal. Al
invocar la purga de privacidad de #86 se eliminan `StudentTurn`, alias,
`DeviceAssignment`, cachés, respuestas libres, `PseudonymousResult` y
`PseudonymousSurveyResponse`. No se introduce ningún TTL automático nuevo.

Las cuentas de docentes y Dirección se desactivan, no se borran. La auditoría
conserva sólo el actor institucional mínimo e inmutable necesario para leer la
historia —nombre de presentación y función histórica— y no exporta credenciales,
correo electrónico ni datos de acceso. Anonimizar posteriormente al actor
requiere una política institucional explícita y queda fuera de P1.

El cambio de Dirección es atómico: después de una autorización institucional,
`PlatformAdministrator` revoca el acceso operativo anterior, activa a la única
persona Directora nueva y preserva actor e historia. Los grupos se archivan al
final del ciclo; el cierre anual continúa siendo por grupo y no activa una
purga de toda la `School` en P1. La desinstalación o el decommissioning quedan
fuera de la interfaz ordinaria y requieren respaldo y procedimiento separado.

### Tradeoff de retención

Conservar la historia institucional y separar de ella la purga estudiantil
permite auditoría y autoría curricular sin convertir los resultados temporales
en un expediente permanente. Se rechazan tanto el borrado en cascada al
archivar como los TTL automáticos, porque impedirían reconstruir decisiones
institucionales o aplicar una política de privacidad explícita y verificable.

## Decisión D4: importación institucional e idempotencia

La importación desde Excel opera únicamente sobre la única `School` configurada
y nunca crea otra `School`. Tampoco crea cuentas docentes: las filas
desconocidas o ambiguas son conflictos explícitos en la vista previa. `staff_code`
no es obligatorio ni se implementa ahora; queda como campo opcional para una
decisión futura.

En el caso de homónimos, la vista previa presenta candidatos de cuentas
existentes y Dirección debe confirmar explícitamente la cuenta antes de aplicar.
Una ambigüedad sin confirmar no produce escritura. La selección confirmada
conserva actor, fecha y fuente en la auditoría; no se exportan username, correo,
IDs de base de datos ni identificadores técnicos.

La identidad estable de `ClassroomGroup` dentro de la `School` es la combinación
de ciclo escolar, modalidad, grado, clave de grupo y turno. El nombre visible es
editable y no define identidad ni idempotencia. La validación contextual acepta
grados 1–6 para primaria y 1–3 para secundaria general, secundaria técnica y
telesecundaria. La importación puede expresar materia o función en secundaria;
en primaria la materia es opcional para especialistas.

La vista previa no escribe y muestra todos los conflictos. Aplicar dos veces el
mismo archivo es idempotente: no crea duplicados ni cambia silenciosamente la
identidad estable del grupo.

### Tradeoff de importación

Se rechazan la creación automática de cuentas y la coincidencia silenciosa por
nombre porque convierten una hoja ambigua en una atribución institucional o una
identidad nueva sin autorización de Dirección. Se mantiene una clave de
personal opcional para no hacer depender el primer alcance de un identificador
que no existe de forma uniforme; la confirmación humana y la auditoría cubren
la resolución mientras esa decisión futura permanece abierta.

## Decisión D5: visibilidad y exportación institucional de Dirección

Dirección puede consultar, dentro de su única `School`, grupos activos y
archivados, adscripciones y su historial, sesiones, posición agregada del
roadmap, actividades trabajadas y participación agregada, auditoría y una
exportación institucional agregada. La proyección y la exportación muestran sólo
metadatos institucionales, nombres de presentación necesarios y agregados por
grupo o roadmap.

Quedan fuera de toda vista o exportación de Dirección los alias, dispositivos,
respuestas individuales, perfiles de alumno, riesgo, rankings, predicciones y
comparaciones docentes o editoriales. Tampoco se exponen username, correo,
UUID, claves pseudónimas, IDs de base de datos ni identificadores técnicos. La
purga de #86 conserva su frontera separada y no se convierte en una consulta de
Dirección.

`PlatformAdministrator` sólo opera configuración, cuentas, roles y estado
técnico. No obtiene por ello autoridad pedagógica, acceso a adscripciones como
decisión institucional, interpretación de resultados ni publicación editorial.

### Tradeoff de visibilidad

Se elige una proyección agregada con auditoría porque permite que Dirección
coordine grupos, sesiones y adscripciones sin convertir AulaLista en un CRM
nominal ni en un sistema de evaluación. Se rechazan el detalle individual, la
comparación entre docentes y la exportación de identificadores técnicos porque
amplían el propósito y crean superficies de privacidad o autoridad que D1–D4 no
autorizan.

## Considered options

- Hacer que cada salón pertenezca directamente al Director: rechazado porque confunde autoridad temporal con propiedad institucional y obliga a trasladar historia cuando cambia la persona.
- Reutilizar autoría (`created_by`) como adscripción docente: rechazado porque crear un registro, impartir en un salón y ser propietaria de currícula son relaciones distintas.

## Consequences

Los permisos y la unicidad se evalúan dentro de `School`. Las adscripciones necesitan vigencia e historia propias; ni Dirección ni administración técnica obtienen por su rol autoridad editorial o acceso a datos nominales de alumnado.
