# Privacidad y analítica en AulaLista: marco jurídico y técnico para escuelas rurales mexicanas

## Resumen ejecutivo

AulaLista opera en LAN en escuelas públicas de educación básica; sus "alumnos" son menores de edad sin cuentas, en dispositivos compartidos. El derecho mexicano distingue dos regímenes: la **LGPDPPSO** (sujetos obligados: la escuela pública) y la **LFPDPPP** (particulares: un proveedor privado). Un nombre en una lista de calificaciones **es dato personal**; y un seudónimo persistente también lo es, porque permite identificar indirectamente. La **recomendación** es: (a) **estadísticas solo por salón/grupo**, como opción por defecto —es la única que puede funcionar sin consentimiento de tutores si se agrega con mínimos de grupo (k-anonimato) y sin conservar filas individuales enlazables—; (b) **registro individual seudónimo**, solo con **consentimiento de tutores + aviso de privacidad + minimización + seguridad**, asumiendo que en salones de 15–30 alumnos el seudónimo es trivialmente reidentificable por la docente y los compañeros; (c) **identificación nominal**, solo con consentimiento expreso de tutores, aviso, **evaluación de impacto (EIPD)** y anclada en el mandato educativo de calificar/registrar, reservada para cuando exista obligación legal de expediente. La evidencia científica (Sweeney 2000; Narayanan & Shmatikov 2008) confirma que **el anonimato en grupos pequeños no es realista**; la literatura de *learning analytics* (Drachsler & Greller 2016; SHEILA; Hoel & Chen 2018) prescribe privacidad por diseño y consentimiento informado.

---

## 1. Marco legal mexicano

### 1.1 Qué ley aplica: dos regímenes distintos (punto que decide el análisis)

México tiene dos leyes de protección de datos que importan aquí, y **cuál aplica depende de quién trata los datos**, no del tipo de dato:

- **LGPDPPSO — Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados** (texto vigente, última reforma DOF 14-11-2025). Aplica a *sujetos obligados*: entes públicos. **Una escuela pública de educación básica es sujeto obligado**, por lo que el tratamiento que haga la escuela/la docente de datos de sus alumnos se rige por esta ley [Cámara de Diputados, texto vigente LGPDPPSO, https://www.diputados.gob.mx/LeyesBiblio/pdf/LGPDPPSO.pdf].
- **LFPDPPP — Ley Federal de Protección de Datos Personales en Posesión de los Particulares** (texto vigente; nueva versión publicada en DOF el 20-03-2025, que **abrogó** la ley federal de 2010 a partir del 21-03-2025). Aplica a *sujetos regulados*: "personas físicas o morales de carácter privado" (art. 2, fr. XVI) [Cámara de Diputados, texto vigente LFPDPPP, https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf; Decreto DOF 20-03-2025, https://www.diputados.gob.mx/LeyesBiblio/ref/lfpdppp/LFPDPPP_orig_20mar25.pdf].

> **Consecuencia práctica para AulaLista.** Si AulaLista se distribuye como herramienta operada por la escuela/la docente (nodo local, sin WAN), la **escuela es la "responsable"** bajo la LGPDPPSO; si existiera un proveedor privado que tratara los datos por cuenta propia, ese proveedor quedaría bajo la LFPDPPP. Ambas leyes comparten la lógica central (consentimiento + aviso + disociación), pero los detalles de aviso y de *evaluación de impacto* difieren. Este documento cita ambas.

La reforma de 2025 (paquete del 20-03-2025) **disolvió el INAI** y transfirió la supervisión a la **Secretaría Anticorrupción y Buen Gobierno**, y expidió simultáneamente la nueva LGPDPPSO y la nueva LFPDPPP [Greenberg Traurig, 2025, https://www.gtlaw.com/es/insights/2025/3/nueva-ley-general-proteccion-de-datos; Basham, 2025, https://basham.com.mx/nueva-ley-federal-de-proteccion-de-datos-personales-en-posesion-de-los-particulares-publicada-en-el-diario-oficial-de-la-federacion/].

### 1.2 ¿Un nombre en una lista de calificaciones es dato personal? Sí.

Ambas leyes definen dato personal de forma idéntica:

> "**Datos personales**: Cualquier información concerniente a una persona identificada o **identificable**. Se considera que una persona es identificable cuando su identidad pueda determinarse **directa o indirectamente** a través de cualquier información." [LFPDPPP, art. 2, fr. V, texto vigente; LGPDPPSO, art. 3, fr. IX].

Por tanto:
- Un **nombre + calificación** es dato personal (identificación directa).
- Un **seudónimo persistente** (p. ej., un ID estable que enlaza varios intentos de la misma persona) es dato personal por identificación **indirecta**: la identidad puede determinarse combinando el seudónimo con información auxiliar (quién usaba qué dispositivo, quién estaba presente, etc.). Esto es exactamente la doctrina del *Recital 26* del GDPR (ver §2.1).
- Solo la **disociación** —"procedimiento mediante el cual los datos personales no pueden asociarse a la persona titular ni permitir, por su estructura, contenido o grado de desagregación, la identificación de la misma"— saca el dato del régimen [LFPDPPP, art. 2, fr. IX; LGPDPPSO, art. 3, fr. XIII].

> **Hallazgo importante (rigor):** las leyes mexicanas no usan el término "seudonimización"; usan "disociación" y la definen como *no poder* identificar. Un dato *seudonimizado* que sí permite reidentificar con información adicional **no es disociado** y sigue siendo dato personal. Esta distinción es la que decide la viabilidad de las opciones (b) y (c) frente a (a).

### 1.3 Menores de edad: consentimiento de tutores

- **LGPDPPSO (escuela pública):** la ley es explícita.
  - "En el tratamiento de datos personales de **menores de edad** se deberá privilegiar el **interés superior de la niña, el niño y el adolescente**…" [LGPDPPSO, art. 7, último párrafo].
  - "En la obtención del **consentimiento** de personas **menores de edad**… se estará a lo dispuesto en las **reglas de representación** previstas en la legislación civil que resulte aplicable" [LGPDPPSO, art. 14, último párrafo]. En la práctica: **el consentimiento lo otorgan los padres o tutores** (quienes ejercen la patria potestad/tutela conforme al Código Civil aplicable).
  - Los derechos ARCO de menores se ejercen también mediante representante [LGPDPPSO, art. 43].
- **LFPDPPP (particular):** aquí hay que ser riguroso. **La LFPDPPP vigente (2025) no contiene una disposición expresa sobre consentimiento de menores.** La búsqueda en el texto íntegro no arroja ningún artículo sobre menores, capacidad, representación, patria potestad o tutela (solo la palabra "menores" aparece en el contexto de "medidas de seguridad"). La ley de 2010 tampoco regulaba a menores en el articulado; lo hacía su **Reglamento** (2011), y la propia reforma de 2025 ordenó al Ejecutivo adecuar el Reglamento en un plazo de 90 días [Greenberg Traurig, 2025, *supra*]. **Conclusión honesta:** para un responsable *privado*, el deber de recabar el consentimiento de los tutores por datos de menores no está hoy en el texto de la LFPDPPP; se deriva del régimen general de consentimiento (art. 7), de las reglas civiles de representación y —por coherencia con la LGPDPPSO y con el interés superior del menor— de la buena práctica. **No debe afirmarse que la LFPDPPP "exige" expresamente consentimiento de tutores: la ley no lo dice textualmente.** En cambio, para la **escuela pública sí lo dice la LGPDPPSO** (arts. 7 y 14).

> **Matiz clave (cuándo NO se necesita consentimiento).** Aun tratándose de menores, el consentimiento no se exige en supuestos tasados. Para la escuela pública: cuando lo disponga la legislación aplicable (p. ej., la obligación de evaluar y llevar control escolar), cuando se requiera para "ejercer un derecho o cumplir obligaciones derivadas de una relación jurídica" entre titular y responsable, o cuando los datos se sometan a "un procedimiento previo de **disociación**" [LGPDPPSO, art. 16, frs. I, V y IX]. Es decir: **calificar y llevar la lista nominal puede estar amparado por el mandato educativo sin consentimiento; pero cualquier tratamiento adicional** (analítica longitudinal, perfiles, conservación seudónima más allá de la calificación) **sale de esa excepción y vuelve a requerir consentimiento (de tutores) o disociación.**

### 1.4 Aviso de privacidad simplificado

- **LFPDPPP:** el aviso debe contener, al menos: (I) identidad y domicilio del responsable; (II) los datos personales a tratar, identificando los sensibles; (III–IV) entre otros, las finalidades que requieran consentimiento y los mecanismos de ejercicio de derechos ARCO; (VI) procedimiento para comunicar cambios (art. 15). Cuando los datos se obtienen por medios electrónicos, el aviso debe darse en **modalidad simplificada**, que contendrá **al menos las fracciones I a IV del art. 15 y señalará el sitio donde consultar el aviso integral** (art. 16, fr. II) [LFPDPPP, texto vigente].
- **LGPDPPSO:** el aviso debe difundirse por medios electrónicos/físicos y **ponerse a disposición en modalidad simplificada** (art. 20). Su contenido mínimo incluye: denominación y domicilio; datos tratados (identificando sensibles); **fundamento legal** que faculta al responsable; **finalidades** distinguiendo las que requieren consentimiento; mecanismos ARCO; domicilio de la Unidad de Transparencia; transferencias que requieran consentimiento; medios para oponerse; y medios para comunicar cambios (art. 21). El **aviso simplificado** contendrá las fracciones **I, IV, VII y III** del art. 21 (denominación/domicilio, finalidades, transferencias, fundamento legal) y el sitio del aviso integral (art. 22) [LGPDPPSO, texto vigente].

> **Lectura para AulaLista:** en un entorno LAN sin internet, "medios electrónicos" es factible (el propio nodo puede mostrar el aviso antes de la actividad); si no fuera posible notificar directamente, la LGPDPPSO prevé **medidas compensatorias** de comunicación masiva (art. 20, último párrafo). Aun así, el aviso simplificado de una escuela pública debe indicar el **fundamento legal** del tratamiento (art. 21, fr. III), cosa que obliga a la escuela a identificar su atribución educativa.

### 1.5 ¿Excepciones para fines "exclusivamente estadísticos o de investigación"?

Aquí la ley mexicana es **más estrecha de lo que suele creerse**, y conviene decirlo con precisión:

- La LFPDPPP exime de dar a conocer el aviso (cuando los datos **no se obtuvieron directamente del titular**) "cuando el tratamiento sea con **fines históricos, estadísticos o científicos**" [LFPDPPP, art. 17, 2º párrafo]. **Es una exención de aviso, no de consentimiento.**
- La exención de **consentimiento** relevante para estadística es la **disociación**: no se requiere consentimiento "cuando los datos personales se sometan a un procedimiento previo de **disociación**" [LFPDPPP, art. 9, fr. III; LGPDPPSO, art. 16, fr. IX].
- En el capítulo de **cancelación**, el responsable puede negarse a cancelar cuando los datos "sean necesarios para realizar una acción en función del **interés público**" [LFPDPPP, art. 25, fr. V].

> **Conclusión rigurosa:** en México **no existe una excepción general de consentimiento para "fines estadísticos o de investigación"** comparable a la del GDPR (art. 89). Para tratar datos *personales* (incluso seudónimos) con fines estadísticos **sin consentimiento**, la vía legal es la **disociación/anonimización efectiva** (art. 9 III LFPDPPP / art. 16 IX LGPDPPSO). Si los datos no quedan realmente disociados, se requiere consentimiento (de tutores, tratándose de menores) o una atribución legal de la escuela. Esto es decisivo para la opción (b).

---

## 2. Comparativos breves

### 2.1 GDPR (Unión Europea)

- **Menores:** el art. 8 GDPR regula el consentimiento del menor solo "en relación con la oferta de servicios de la sociedad de la información directamente a un niño": por debajo de 16 años (los Estados pueden bajar hasta 13), el tratamiento exige **consentimiento dado o autorizado por el titular de la responsabilidad parental**, con esfuerzos razonables de verificación [GDPR, art. 8, https://gdpr-info.eu/art-8-gdpr/; texto consolidado CELEX 32016R0679, https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679]. Además, el *Recital 38* ordena protección específica de los datos de niños [https://gdpr-info.eu/recitals/no-38/]. **Atención:** el art. 8 se aplica a servicios *online directos al niño*; la actividad escolar presencial suele basarse en otras bases jurídicas.
- **Base "interés público en educación":** el art. 6(1)(e) permite tratar datos cuando es necesario "para el cumplimiento de una tarea realizada en **interés público** o en el ejercicio de poderes públicos", con base en Derecho de la Unión o del Estado miembro [GDPR, art. 6(1)(e) y 6(3), https://gdpr-info.eu/art-6-gdpr/]. Esta es la base típica para que un centro educativo trate datos de alumnos **sin consentimiento** (calificaciones, expediente). Nótese la afinidad con la LGPDPPSO art. 16 fr. I/V.
- **Seudonimización ≠ anonimización:** el *Recital 26* es taxativo: "los datos personales que han sido objeto de **seudonimización**… deben considerarse información sobre una persona física **identificable**"; solo la información **anónima** (que ya no permite identificar) queda fuera del Reglamento [GDPR, Recital 26, https://gdpr-info.eu/recitals/no-26/].
- **Investigación/estadística:** el art. 89(1) exige **salvaguardas apropiadas** (incluida la seudonimización cuando baste) para fines de archivo en interés público, investigación científica/histórica o estadística, y —dato clave— "cuando esos fines puedan cumplirse mediante un tratamiento ulterior que **no permita o deje de permitir la identificación**, se cumplirán de esa manera" (es decir, **preferencia por el dato anónimo/agregado**) [GDPR, art. 89, https://gdpr-info.eu/art-89-gdpr/; estudio del EDPB sobre las salvaguardas del art. 89(1), https://www.edpb.europa.eu/system/files/2022-01/legalstudy_on_the_appropriate_safeguards_89.1.pdf]. La misma preferencia por el dato no identificable es la que inspira el art. 16 IX LGPDPPSO y el art. 9 III LFPDPPP.

### 2.2 FERPA (Estados Unidos)

FERPA (20 U.S.C. § 1232g; 34 CFR Part 99) protege los *education records* y la *personally identifiable information (PII)* de los estudiantes; exige **consentimiento escrito de los padres** para revelar PII, salvo excepciones [U.S. Dept. of Education, Protecting Student Privacy, https://studentprivacy.ed.gov/ferpa]. Conceptos relevantes para este debate:

- ***Directory information*** (nombre, dirección, teléfono, fecha de nacimiento, etc.): puede revelarse **sin consentimiento** salvo que los padres ejerzan *opt-out* —pero es la excepción, no la regla, y **no** ampara calificaciones ni desempeño.
- ***De-identified data:*** "Las escuelas **no necesitan obtener consentimiento escrito ni informar** a los padres… al divulgar información **correctamente desidentificada**" [FAQ, https://studentprivacy.ed.gov/frequently-asked-questions]. La definición es estricta y **sensible al tamaño de la comunidad**: se desidentifica cuando se elimina "cualquier información que, sola o en combinación, sea vinculable a un estudiante concreto y que **una persona razonable de la comunidad escolar**, sin conocimiento personal de las circunstancias, pudiera usar para identificar al estudiante con **certeza razonable**" [FAQ "What constitutes de-identified records and information?", *ibídem*]. **Esta cláusula es la traducción normativa exacta del problema de AulaLista:** en un salón pequeño, "una persona razonable de la comunidad escolar" (la docente) *sí* tiene conocimiento personal (quién falta, quién terminó, qué dispositivo usa quién) para reidentificar.
- ***Student-created data en apps:*** FERPA alcanza los datos generados por el estudiante en una aplicación si el registro es "mantenido por la agencia/institución educativa" y "directamente relacionado con un estudiante" (34 CFR § 99.3). Un expediente que el proveedor mantiene *por cuenta de* la escuela puede ser un *education record*; por eso los acuerdos *school official* y las cláusulas de minimización son la práctica estándar. FERPA también permite que los estudiantes opten por no aparecer en *directory information*, pero "no pueden usar ese derecho para impedir que los funcionarios de la escuela los identifiquen por nombre… en clase" [FAQ, *ibídem*] — un matiz útil: la identificación nominal *dentro* del aula legítima es distinta de la divulgación a terceros.

### 2.3 UNESCO y OECD (analítica de aprendizaje)

- **UNESCO, "Minding the data: protecting learners' privacy and security" (2022):** guía específica que sitúa la privacidad de los estudiantes como condición para el uso de datos y tecnologías en educación, con énfasis en **minimización de datos, limitación de finalidad, transparencia y medidas técnicas/organizativas** [UNESCO, 2022, DOI 10.54675/NNAA4843, https://unesdoc.unesco.org/ark:/48223/pf0000381494]. Es la referencia más directa para el caso de AulaLista (educación básica, poblaciones vulnerables, datos de menores).
- **OECD, "Smart Data and Digital Technology in Education" (proyecto en curso):** reconoce que los datos y la tecnología son impulsores de innovación en educación "pero también crean nuevos problemas de política" y que el reto es "aprovechar los beneficios de la digitalización **minimizando sus riesgos**" [OECD, https://www.oecd.org/en/about/projects/smart-data-and-digital-technology-in-education--artifical-intelligence,-learning-analytics-and-beyond.html]. Aporta el marco de "beneficio con gestión de riesgo", no una regla operativa.

---

## 3. Base científica de privacidad

### 3.1 Seudonimización y sus límites de reidentificación

- **Sweeney (2000):** demostró que "**87 %** (216 de 248 millones) de la población de EE. UU. tenía características que probablemente los hacían **únicos** usando solo {código postal de 5 dígitos, sexo, fecha de nacimiento}"; y que el **53 %** es identificable por {lugar, sexo, fecha de nacimiento} [L. Sweeney, *Simple Demographics Often Identify People Uniquely*, 2000, http://dataprivacylab.org/projects/identifiability/]. Es la prueba canónica de que pocos atributos "inofensivos" bastan para reidentificar. De ahí derivó el modelo de **k-anonimato**: un conjunto es *k*-anónimo si cada registro es indistinguible de al menos *k−1* otros [Sweeney, *k-anonymity: a model for protecting privacy*, 2002].
- **Narayanan & Shmatikov (2008):** mostraron la **desanonimización robusta** del dataset del *Premio Netflix* cruzando calificaciones de películas con datos públicos de IMDb; con un adversario que conoce **pocas calificaciones** de una persona, una fracción sustancial de los registros "anónimos" se reidentifica [Narayanan & Shmatikov, *Robust De-anonymization of Large Sparse Datasets*, IEEE S&P 2008, https://ieeexplore.ieee.org/document/4531148].
- **Dwork (2006) / Dwork & Roth (2014):** la **privacidad diferencial** formaliza que la salida de un análisis no debe cambiar materialmente por la inclusión/exclusión de un individuo (ruido calibrado); es el estándar técnico más fuerte para agregados, y su mensaje es que **ninguna transformación "una sola vez" de un microdato garantiza privacidad**: hay que proteger la *salida* del análisis, no solo el dato [Dwork, *Differential Privacy*, ICALP 2006; Dwork & Roth, *The Algorithmic Foundations of Differential Privacy*, 2014, https://dl.acm.org/doi/10.1561/0400000042].

### 3.2 ¿Es realista el anonimato en salones de 15–30 alumnos? No.

Combinando las tres fuentes: la reidentificación depende de **información auxiliar** y del **tamaño del grupo**. En un salón de 15–30 alumnos la docente conoce de hecho mucha información auxiliar (lista de asistencia, quién usa cada dispositivo compartido, quién terminó primero, a quién se le explicó algo). Por tanto:

- Un **seudónimo estable por alumno** es reidentificable en la práctica por la docente y por los propios compañeros (un "insider" con conocimiento de la comunidad), incluso si el sistema no guarda el nombre. Es exactamente el estándar que FERPA captura con "persona razonable de la comunidad escolar" (§2.2).
- Los **agregados de grupo** no eliminan el riesgo por sí solos: un agregado muy desagregado (p. ej., "promedio de 3 alumnos", o un conteo con un solo individuo en una celda) también reidentifica. La protección de agregados exige **mínimos de tamaño de celda (k)** y supresión/agregación de celdas pequeñas —una forma de *k*-anonimato— o ruido diferencial en la salida.
- **Consecuencia para AulaLista:** "seudónimo" no equivale a "anónimo", y en este contexto "anonimato robusto" es inalcanzable frente al docente/colegio. Lo que sí es alcanzable y valioso es **minimizar y reducir enlazabilidad** (seudónimo efímero por sesión, borrado de la relación nombre↔dispositivo↔intento, como ya hace AulaLista) y **no persistir** identificadores estables cuando no hay consentimiento.

### 3.3 Learning Analytics: privacidad por diseño

- **Drachsler & Greller (2016):** tras revisar los temores y realidades de la adopción de *learning analytics*, proponen el checklist **DELICATE** (ocho dimensiones: *Determination, Explain, Legitimate, Involve, Consent, Anonymise, Technical, External*) para una implementación **confiable** de la analítica [Drachsler & Greller, *Privacy and analytics: it's a DELICATE issue*, LAK 2016, https://dl.acm.org/doi/10.1145/2883851.2883893]. La "A" de *Anonymise* y la "C" de *Consent* son directamente aplicables: anonimizar donde sea posible y consentir donde no lo sea.
- **SHEILA (Tsai et al., 2018):** marco de **política y estrategia institucional** para *learning analytics* construido con 78 directivos de 51 universidades europeas; insiste en que la adopción requiere **procesos de política, participación de partes interesadas y gobernanza**, no solo tecnología [Tsai et al., *The SHEILA Framework*, Journal of Learning Analytics, 2018, https://learning-analytics.info/index.php/JLA/article/view/6096]. Aunque es de educación superior, su lección de **gobernanza previa a la analítica** aplica igual a educación básica.
- **Hoel & Chen (2018):** argumentan que la privacidad en *learning analytics* debe motivarse por un "**máximo educativo**": el consentimiento por sí solo no resuelve el problema en educación porque se balancea con el interés legítimo de la institución y el contrato; proponen **separar el análisis de la intervención** y basar la privacidad en valores pedagógicos, con tres principios [Hoel & Chen, *Privacy and data protection in learning analytics should be motivated by an educational maxim*, Int. J. Educ. Technol. High. Educ., 2018, https://link.springer.com/article/10.1186/s41039-018-0086-8]. Este punto es central para AulaLista: **decidir qué analítica es realmente necesaria para enseñar** es una decisión pedagógica antes que legal.

---

## 4. Conclusión práctica

### 4.1 Lectura de las tres opciones a la luz de la evidencia

- **(a) Estadísticas solo por salón/grupo.** Es la opción **más defendible sin consentimiento**, porque puede apoyarse en la **disociación/agregación** (LFPDPPP art. 9 III; LGPDPPSO art. 16 IX) y coincide con la preferencia legal por el dato no identificable (GDPR art. 89(1); FERPA *de-identified data*). **Condición técnica no negociable:** las estadísticas deben ser agregadas con **mínimos de grupo (k)** y sin celdas de tamaño 1 (un salón con 15–30 alumnos produce celdas pequeñas con facilidad); si se necesita granularidad, aplicar ruido (privacidad diferencial) o suprimir celdas. Pierde utilidad individual para la docente (no puede ver el recorrido de un alumno concreto), lo cual es el costo deliberado de no pedir consentimiento.
- **(b) Registro individual seudónimo por alumno.** Técnicamente útil, pero **jurídicamente es dato personal** (identificación indirecta; LFPDPPP art. 2 V; GDPR Recital 26). Por tanto, para menores en escuela pública, **requiere consentimiento de tutores + aviso de privacidad** (LGPDPPSO arts. 7, 14, 20–22) **+ minimización y seguridad** (art. 19 LGPDPPSO / art. 12 LFPDPPP) **+ borrado efectivo**. Además, la ciencia muestra que en salones pequeños el seudónimo es **trivialmente reidentificable** (Sweeney 2000; FERPA "comunidad escolar"), de modo que "seudónimo" no debe venderse como "anónimo". Es defendible **solo si** hay consentimiento informado real de tutores y el seudónimo se trata como dato personal (derechos ARCO, finalidad limitada, retención mínima).
- **(c) Identificación nominal por alumno (lista nominal / cuentas creadas por padres / MAC).** Es el máximo de utilidad y el máximo de carga. Es **defendible solo cuando exista obligación legal de identificar** (calificación/expediente/control escolar, que en México deriva de la Ley General de Educación y las normas de control escolar —artículos específicos **no verificados en este documento** y que la escuela debe confirmar), en cuyo caso puede operar sin consentimiento por la vía de atribución legal (LGPDPPSO art. 16 I/V). Si **no** hay obligación legal, requiere **consentimiento expreso de tutores** (LGPDPPSO art. 15; tratándose de datos sensibles, art. 7/art. 15). Al ser un tratamiento de datos de un colectivo vulnerable ("público objetivo" de menores), es altamente probable que califique como **tratamiento intensivo o relevante** y dispare la obligación de **Evaluación de Impacto (EIPD)** con presentación a la autoridad 30 días antes (LGPDPPSO arts. 68–72; criterios en art. 69: riesgos inherentes, datos sensibles, transferencias; y art. 70 fr. II "público objetivo"). Sobre el identificador, **la MAC es un identificador de dispositivo, no de persona**, y en dispositivos compartidos no distingue alumnos; además es un dato personal técnico que no resuelve (y complica) la identificación del menor —no debe usarse como sustituto de identidad.

### 4.2 Tabla comparativa de las tres opciones

| Dimensión | (a) Solo por salón/grupo | (b) Registro individual seudónimo | (c) Identificación nominal |
|---|---|---|---|
| ¿Es "dato personal"? | No, **si** la agregación es efectiva (sin celdas de tamaño 1 y sin filas individuales enlazables) | **Sí** (identificación indirecta) | **Sí** (identificación directa) |
| Base legal en México | Disociación/agregación: LFPDPPP art. 9 III; LGPDPPSO art. 16 IX | Consentimiento (tutores) + aviso: LGPDPPSO arts. 7, 14, 20–22 | Atribución legal educativa (LGPDPPSO art. 16 I/V) **o** consentimiento expreso de tutores |
| Consentimiento de tutores | No requerido (si realmente disociado) | **Requerido** | Requerido **salvo** obligación legal de identificar |
| Aviso de privacidad | Recomendable (transparencia), no estrictamente obligatorio sobre dato disociado | **Obligatorio** (simplificado + integral) | **Obligatorio** (con fundamento legal, art. 21 III) |
| Riesgo de reidentificación en salón 15–30 | Bajo **solo con** k-anonimato/ruido en celdas | **Alto**: trivial para la docente/compañeros | Nulo (ya es nominal) |
| Evaluación de impacto (EIPD) | Generalmente no | Posible (menores + perfiles) | **Probablemente sí** (art. 69 II "público objetivo", art. 68) |
| Utilidad pedagógica | Baja–media (grupo) | Media–alta (recorrido individual) | Alta (expediente, longitudinal) |
| Carga de cumplimiento | Mínima | Media | Alta |
| Veredicto | **Opción por defecto** | Defendible **con consentimiento** y tratado como dato personal | Solo cuando la ley obliga a identificar, con EIPD |

### 4.3 Condiciones de defensa en México (resumen operativo)

1. **Por defecto, agregar por grupo** (opción a) con mínimos de celda (k) o ruido diferencial; no conservar filas individuales persistentes; borrar la relación nombre↔dispositivo↔intento (AulaLista ya lo hace).
2. Si se quiere **registro individual** (opción b), tratarlo como **dato personal de menor**: consentimiento de tutores, aviso simplificado+integral, finalidad limitada, retención mínima, seguridad, y derechos ARCO ejercibles por los tutores.
3. Reservar **identificación nominal** (opción c) para cuando una obligación de control escolar lo exija; documentar la atribución legal y, en su caso, realizar **EIPD** (LGPDPPSO arts. 68–72).
4. **No** usar la **MAC** como identidad de alumno: identifica dispositivo, no persona, y no es estable en dispositivos compartidos.
5. Para un **proveedor privado** (si lo hubiera), recordar que la **LFPDPPP 2025 no regula expresamente el consentimiento de menores** (vacío a señalar ante la autoridad); aplicar por prudencia el mismo estándar que la LGPDPPSO (consentimiento de tutores + interés superior del menor).
6. Ante la duda, la **preferencia por el dato no identificable** es la regla convergente de las tres jurisdicciones revisadas (GDPR art. 89(1); FERPA *de-identified data*; LGPDPPSO art. 16 IX) y de la literatura de *learning analytics*.

---

## 5. Fuentes

**Normativa mexicana (primarias):**
1. Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP), texto vigente (publicada DOF 20-03-2025; última reforma DOF 14-11-2025). https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf
2. Decreto original LFPDPPP, DOF 20-03-2025. https://www.diputados.gob.mx/LeyesBiblio/ref/lfpdppp/LFPDPPP_orig_20mar25.pdf
3. Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados (LGPDPPSO), texto vigente (última reforma DOF 14-11-2025). https://www.diputados.gob.mx/LeyesBiblio/pdf/LGPDPPSO.pdf
4. Greenberg Traurig, "Nueva Ley Federal de Protección de Datos Personales en Posesión de los Particulares" (27-03-2025). https://www.gtlaw.com/es/insights/2025/3/nueva-ley-general-proteccion-de-datos
5. Basham, Ringe y Correa, "Nueva Ley Federal de Protección de Datos Personales en Posesión de los Particulares publicada en el DOF" (2025). https://basham.com.mx/nueva-ley-federal-de-proteccion-de-datos-personales-en-posesion-de-los-particulares-publicada-en-el-diario-oficial-de-la-federacion/

**GDPR:**
6. Reglamento (UE) 2016/679 (GDPR), texto consolidado. https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679
7. GDPR, art. 6. https://gdpr-info.eu/art-6-gdpr/ — art. 8. https://gdpr-info.eu/art-8-gdpr/ — art. 89. https://gdpr-info.eu/art-89-gdpr/ — Recital 26. https://gdpr-info.eu/recitals/no-26/ — Recital 38. https://gdpr-info.eu/recitals/no-38/
8. EDPB, "Study on the appropriate safeguards under Article 89(1) GDPR". https://www.edpb.europa.eu/system/files/2022-01/legalstudy_on_the_appropriate_safeguards_89.1.pdf

**FERPA:**
9. U.S. Department of Education, Protecting Student Privacy — FERPA. https://studentprivacy.ed.gov/ferpa
10. U.S. Department of Education, FERPA Frequently Asked Questions (directory information; de-identified data; school officials). https://studentprivacy.ed.gov/frequently-asked-questions

**UNESCO / OECD:**
11. UNESCO, "Minding the data: protecting learners' privacy and security" (2022). DOI 10.54675/NNAA4843. https://unesdoc.unesco.org/ark:/48223/pf0000381494
12. OECD, "Smart Data and Digital Technology in Education: Artificial Intelligence, Learning Analytics and Beyond". https://www.oecd.org/en/about/projects/smart-data-and-digital-technology-in-education--artifical-intelligence,-learning-analytics-and-beyond.html

**Literatura científica:**
13. Sweeney, L., "Simple Demographics Often Identify People Uniquely" (2000). http://dataprivacylab.org/projects/identifiability/
14. Sweeney, L., "k-anonymity: a model for protecting privacy" (2002).
15. Narayanan, A. & Shmatikov, V., "Robust De-anonymization of Large Sparse Datasets", IEEE S&P (2008). https://ieeexplore.ieee.org/document/4531148
16. Dwork, C., "Differential Privacy", ICALP (2006); Dwork, C. & Roth, A., "The Algorithmic Foundations of Differential Privacy" (2014). https://dl.acm.org/doi/10.1561/0400000042
17. Drachsler, H. & Greller, W., "Privacy and analytics: it's a DELICATE issue. A checklist for trusted learning analytics", LAK (2016). https://dl.acm.org/doi/10.1145/2883851.2883893
18. Tsai, Y.-S. et al., "The SHEILA Framework: Informing Institutional Strategies and Policy Processes of Learning Analytics", Journal of Learning Analytics (2018). https://learning-analytics.info/index.php/JLA/article/view/6096
19. Hoel, T. & Chen, W., "Privacy and data protection in learning analytics should be motivated by an educational maxim", Int. J. Educ. Technol. High. Educ. (2018). https://link.springer.com/article/10.1186/s41039-018-0086-8

**Advertencias de rigor:**
- La **LFPDPPP vigente (2025) no contiene disposiciones expresas sobre menores**; el régimen de consentimiento de tutores para responsables privados se deriva de la LGPDPPSO (arts. 7, 14, 43) y de la legislación civil de representación, y el Reglamento de la LFPDPPP estaba pendiente de adecuación tras la reforma de 2025. Este vacío se señala explícitamente y no debe darse por resuelto.
- Los **artículos específicos de la Ley General de Educación** que obligan a la escuela a calificar y llevar expediente/control escolar **no fueron verificados en este documento**; deben confirmarse con la normativa de control escolar aplicable antes de invocar la excepción de consentimiento de la LGPDPPSO art. 16 I/V.
- La traducción de "fines estadísticos" como exención en México **no equivale** a una exención de consentimiento (es de aviso, LFPDPPP art. 17); la vía de consentimiento-cero es la **disociación**.
