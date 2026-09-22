# Qué debería capturar el docente en AulaLista

**Fecha:** 2026-08-28  
**Pregunta:** ¿AulaLista debe pedir una planeación semanal, el plan de estudios o alguna otra cosa?

## Decisión recomendada

No conviene pedirle al maestro que vuelva a escribir el Plan de Estudio ni que llene desde cero un documento largo cada semana. La mejor unidad de producto es una combinación de dos capas:

1. **Mapa curricular de trabajo por docente y ciclo escolar.** Es editable durante todo el ciclo y se apoya en anclas oficiales (fase/grado, campo o disciplina, contenido y proceso de desarrollo de aprendizaje) más la contextualización que el docente necesite.
2. **Planeación didáctica ligera por semana o periodo.** Relaciona una o varias anclas del mapa con el propósito de ese periodo, la actividad/proyecto, la evidencia que se observará y el siguiente ajuste. Debe ser opcional y rápida, no otro formulario burocrático.

En términos del modelo actual de AulaLista, el mapa del docente es una vista de trabajo propia; no debe presentarse como el **Programa Analítico de la escuela**, que la SEP describe como una construcción del colectivo docente. Una escuela podría compartir o importar su programa analítico, pero el docente debe poder ajustar su secuencia y sus notas dentro de su ámbito de autoridad.

## Qué dicen las fuentes oficiales

### 1. El Plan de Estudio y los programas sintéticos son el punto de partida nacional

El Plan de Estudio 2022 es aplicable y obligatorio para la educación preescolar, primaria y secundaria en la República. El propio documento separa el Plan y los programas, la formación docente y el codiseño contextual como partes de una propuesta curricular en construcción permanente ([SEP, Plan de Estudio 2022, pp. 7–8](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/06/Plan-de-Estudio-ISBN-ELECTRONICO-1.pdf)).

La SEP presenta los Programas Sintéticos de las Fases 2 a 6 como el primer nivel de concreción curricular: contienen campos formativos, contenidos y procesos de desarrollo de aprendizaje, y son obligatorios pero flexibles para contextualizar y elaborar el Programa Analítico ([SEP, infografía oficial de Fase 2](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/06/Preescolar_Programa-de-estudio-para-la-Fase-2.pdf); [DOF, Acuerdo 08/08/23](https://dof.gob.mx/nota_detalle.php?codigo=5698665&fecha=15/08/2023)).

Por eso AulaLista debe ofrecer un catálogo de anclas curriculares y selección guiada. El docente no debería capturar manualmente todo el contenido nacional.

### 2. El Programa Analítico contextualiza, secuencia y temporaliza

El Plan de Estudio explica que el Programa Analítico es una segunda etapa: parte del conocimiento del Plan, analiza las condiciones de la escuela y las experiencias docentes, y adecua los contenidos a las necesidades, estilos y ritmos de aprendizaje del alumnado. También incorpora problemas, temas y asuntos locales mediante codiseño del colectivo docente ([SEP, Plan de Estudio 2022, pp. 154–156](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/06/Plan-de-Estudio-ISBN-ELECTRONICO-1.pdf)).

Las orientaciones de la SEP son más explícitas: el colectivo observa el Programa Sintético, diseña el Programa Analítico, y allí determina la **secuenciación y temporalidad** de contenidos y procesos; sobre esa base cada docente elabora la planeación didáctica de su grupo ([SEP, Orientaciones de la Tercera Sesión Ordinaria, p. 5](https://educacionbasica.sep.gob.mx/wp-content/uploads/2023/11/2324_s3_Orientaciones_Tercera_Sesion_Preescolar_Primaria_Secundaria.pdf)).

La SEP también señala que el Programa Analítico se mejora y reconstruye durante el ciclo escolar, no es un documento congelado ([SEP, Quinta Sesión Ordinaria CTE](https://educacionbasica.sep.gob.mx/quinta-sesion-ordinaria-cte/)).

### 3. La planeación didáctica sí es del docente, pero no tiene un formato nacional único

La planeación didáctica es la concreción cotidiana de esas decisiones curriculares. El Plan de Estudio reconoce la autonomía profesional del magisterio para decidir contenidos, didácticas, tiempos, espacios, evaluación y ajustes según el contexto ([SEP, Plan de Estudio 2022, pp. 67–70](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/06/Plan-de-Estudio-ISBN-ELECTRONICO-1.pdf)).

En el seguimiento oficial a la apropiación del Plan 2022, la SEP contempla que los colectivos diseñen un formato propio, acuerden sus elementos, usen propuestas de los libros de texto o adapten formatos enviados por una autoridad. Esto es evidencia de que no hay una plantilla semanal universal que AulaLista deba imponer ([SEP, Seguimiento a la apropiación del Plan y Programas de Estudio 2022, preguntas 12–13](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/09/Seguimiento-a-la-apropiacion-del-plan-y-programas-de-estudio-2022.pdf)).

La evaluación formativa debe estar vinculada a la planeación y servir para retroalimentar la siguiente acción docente; no basta con acumular registros ([SEP, Tercera Sesión Ordinaria](https://educacionbasica.sep.gob.mx/tercera-sesion-ordinaria/)).

## Traducción al producto

### Objeto canónico

Nombrarlo **Mapa curricular del docente — ciclo escolar** (o simplemente “Mi mapa” en la interfaz), con:

- ciclo escolar, fase, grado, grupo y campo/disciplina;
- anclas seleccionadas del Programa Sintético (contenido y proceso de desarrollo de aprendizaje);
- orden o periodo estimado (mes, bloque o rango de semanas, no una fecha rígida);
- contextualización breve: problema de la comunidad, saber local, adecuación o prioridad del grupo;
- orientación didáctica/evidencia sugerida;
- estado manual: por abordar, en curso, trabajado o revisado;
- historial de cambios y versiones publicadas.

Para **educación primaria**, esta jerarquía no debe ser un campo de texto libre: la primaria se distribuye en tres fases de aprendizaje —**Fase 3 (1.º–2.º), Fase 4 (3.º–4.º) y Fase 5 (5.º–6.º)**— y en cuatro campos formativos: **Lenguajes; Saberes y Pensamiento Científico; Ética, Naturaleza y Sociedades; y De lo Humano y lo Comunitario** ([SEP, Plan de Estudio 2022, pp. 138–144 y 156–160](https://educacionbasica.sep.gob.mx/wp-content/uploads/2024/06/Plan-de-Estudio-ISBN-ELECTRONICO-1.pdf)). El selector debe partir de esa estructura y después mostrar los contenidos y procesos de desarrollo de aprendizaje correspondientes a la fase, grado y campo.

El mapa debe tener exactamente una versión de trabajo activa por docente y ciclo, con edición continua. Publicar crea un snapshot inmutable para que una sesión ya iniciada no cambie retrospectivamente. Esto conserva la decisión de dominio existente sobre confirmación humana y snapshots.

### Capa operativa

Agregar una entrada de **planeación de semana o periodo** con pocos campos:

1. rango de fechas (o “esta semana”);
2. ancla(s) del mapa, elegidas con autocompletado;
3. propósito o pregunta guía, en texto corto;
4. actividad/proyecto y materiales;
5. qué se observará o qué evidencia se recogerá;
6. ajuste para la siguiente sesión (opcional);
7. estado: borrador, en curso, realizado y reflexión breve.

No obligar a escribir un “nombre de roadmap” si ya existe el ciclo y el mapa. La navegación principal debe ser mapa → semana → sesión, no un conjunto de textboxes independientes.

### Avance docente

“Avance docente” debe ser una lectura estadística del mapa y de las planeaciones, no una evaluación laboral:

- anclas planeadas, en curso, confirmadas y pendientes;
- distribución aproximada por campo y periodo;
- semanas con planeación y sesiones asociadas;
- últimos ajustes o anclas que el docente marcó para retomar;
- cobertura del **mapa de trabajo**, nunca una afirmación de aprendizaje individual ni un ranking de docentes.

La confirmación debe seguir siendo explícita. Crear una actividad, publicarla o cerrar una sesión no debe marcar automáticamente un contenido como trabajado.

## Flujo UX mínimo

**Inicio de ciclo:** elegir fase/grado/campo, importar o seleccionar anclas oficiales y crear el mapa. Ofrecer una plantilla inicial, sin exigir que el maestro conozca toda la terminología curricular.

**Durante el ciclo:** la pantalla principal muestra “Esta semana” con las anclas próximas y un botón “Planear periodo”. El docente puede cambiar fechas, añadir una nota local o saltar una ancla sin romper el mapa.

**Al preparar una sesión:** seleccionar una planeación o ancla existente; AulaLista sugiere materiales/actividad, pero el docente revisa y confirma. La sesión queda ligada al snapshot publicado.

**Al terminar:** registrar “trabajado”, “parcial” o “retomar”, más una nota opcional de evidencia. No inferir progreso por el simple uso de la actividad.

## Lo que no debemos construir todavía

- un editor para que cada docente reescriba el Plan de Estudio completo;
- una plantilla semanal rígida presentada como requisito oficial;
- un Programa Analítico escolar falso creado por una sola cuenta si la escuela no lo ha acordado;
- un porcentaje de “efectividad” o ranking docente;
- una métrica de aprendizaje individual derivada de la planeación.

## Decisiones abiertas para una sesión de diseño

1. ¿AulaLista se enfocará primero en educación básica SEP (Fases 2–6) o también en otros niveles? El catálogo oficial y los campos cambian.
2. ¿La escuela podrá importar un Programa Analítico acordado por el colectivo, o la primera versión será solo el mapa personal del docente?
3. ¿La unidad de temporalidad inicial será semana, quincena o un rango flexible? Recomiendo rango flexible con vista semanal.
4. ¿Qué tan completa debe ser la biblioteca de anclas oficiales antes de permitir texto libre?

## Conclusión

La pregunta no es “semanal **o** plan de estudios”. El plan/programa oficial debe estar disponible como referencia; el mapa contextualizado organiza el ciclo; y la planeación semanal sirve como capa ligera para decidir la próxima acción. Para AulaLista, esa combinación respeta la autonomía docente, reduce captura y encaja con el flujo ya decidido: un mapa editable por ciclo, confirmación humana, snapshots para sesiones y Avance docente como estadística descriptiva.
