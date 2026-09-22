# Evaluación de valor: tablero directivo y desempeño agregado de salones/roadmap en México

**Fecha:** 27 de agosto de 2026
**Propósito:** decidir si AulaLista debe extenderse desde coordinación de salones hacia un tablero directivo y, eventualmente, un CRM nominal alumno–director.

## Dictamen ejecutivo

Sí vale la pena validar una capa pequeña de coordinación institucional (nivel A) y, sólo si existe una fuente autorizada y una decisión recurrente que mejorar, un tablero agregado de salones/roadmap (nivel B). No se recomienda construir todavía el nivel C, un CRM nominal alumno–director.

La razón no es que los datos carezcan de valor. La SEP ya define como objetivos del SIGED reducir cargas administrativas, facilitar la comunicación director–autoridad y fortalecer la autonomía de gestión ([SEP, SIGED](https://siged.sep.gob.mx/SIGED/quienes_somos.html)). La OECD, sin embargo, advierte que enlazar registros personales entre sistemas aumenta los riesgos de privacidad y seguridad, y que los beneficios dependen de gobernanza, interoperabilidad y capacidad de uso ([OECD, Digital Education Outlook 2023](https://www.oecd.org/en/publications/oecd-digital-education-outlook-2023_c74f03de-en/full-report/data-and-technology-governance-fostering-trust-in-the-use-of-data_171e56b9.html)).

El valor potencial está en reducir consolidación manual y hacer visibles pendientes agregados. El costo y riesgo crecen mucho al pasar a expedientes nominales: permisos, calidad de identidad, seguridad, retención, atención de derechos, capacitación y responsabilidad frente a menores. Una LLM puede interpretar una plantilla o resumir datos ya autorizados, pero no debe decidir asignaciones, etiquetar riesgo ni operar sobre datos personales sin revisión humana. UNESCO recomienda protección de datos, límites de edad y un enfoque humano para GenAI en educación ([UNESCO, Guidance for generative AI](https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research)).

## Tres niveles comparados

| Nivel | Qué resuelve | Decisiones que mejora | Datos/infraestructura/permisos | Valor esperado | Riesgo y recomendación |
|---|---|---|---|---|---|
| **A. Asignación y coordinación de salones** | Qué salones existen, grado/grupo, docente responsable, cambios y pendientes | Distribuir docentes, detectar salón sin responsable, preparar reunión y actualizar plantilla | Datos de escuela/salón/docente; importación Excel; acceso de director y administrador; auditoría de cambios | Alto si hoy se usan hojas y mensajes duplicados; fácil de medir | Bajo–medio. **Fase 1**, sin alumnos ni desempeño |
| **B. Tablero agregado de roadmap** | Actividad/roadmap por salón: sesiones, actividades completadas y bloqueos agregados | Elegir qué salón necesita apoyo, preparar CTE, priorizar acompañamiento; comparar tendencias sin identificar alumnos | Fuente de eventos confiable; definiciones de actividad y periodo; agregación mínima; permisos de director por escuela; operación local/offline y sincronización eventual | Medio–alto si cambia una reunión o intervención; depende de adopción y calidad | Medio. **Fase 2 condicionada** a una decisión observada y pruebas de privacidad |
| **C. CRM nominal alumno–director** | Historial individual, contactos, incidencias, riesgo, progreso y seguimiento | Intervenir con un alumno/familia, derivar casos, documentar acciones | Identidad nominal, datos sensibles, consentimiento/base jurídica, roles finos, cifrado, retención, exportación/eliminación, soporte y capacitación | Desconocido; podría duplicar control escolar/SIGED y protocolos | Alto–crítico. **No fase ahora**; sólo investigación con datos sintéticos |

## Quién obtiene valor

**Estudiante.** Puede beneficiarse indirectamente de una respuesta más oportuna a inasistencia, bloqueos de actividad o necesidad de apoyo. El beneficio no está demostrado por mostrar un tablero; se requiere medir una intervención concreta. Los datos nacionales de UNICEF hacen relevante la permanencia y protección: su análisis 2018–2025 reporta 24.9% de sintomatología depresiva en población de 10–19 años en 2023 y brechas fuertes de aprendizaje; esto justifica atención humana, no un algoritmo de riesgo ([UNICEF México](https://www.unicef.org/mexico/informes/situacion-derechos-ninez-adolescencia-mexico)).

**Docente.** El nivel A reduce ambigüedad de responsabilidades; el B puede ayudar a preparar colaboración entre salones. Pero un tablero usado para vigilar o rankear docentes podría producir resistencia y conductas de cumplimiento superficial. La OECD reporta que alrededor de la mitad de docentes considera estresante el trabajo administrativo en TALIS 2024, lo que hace plausible el valor de quitar captura, no de añadir otra ([OECD, TALIS 2024](https://www.oecd.org/en/publications/results-from-talis-2024_90df6235-en/full-report/the-demands-of-teaching_0e941e2f.html)).

**Dirección.** El beneficio principal es una vista confiable para coordinar y decidir, no controlar cada alumno. UNESCO encuentra que los directivos soportan exceso de gestión rutinaria y recomienda compartir liderazgo; un tablero debe mostrar próximos pasos y responsables, no concentrar toda la autoridad en la cuenta del director ([UNESCO GEM 2024/5](https://www.unesco.org/reports/gem-report/en/2024)).

**Administración avanzada.** Integrar plantillas, ciclos, reportes y auditoría puede generar valor operativo, pero SIGED ya tiene el mandato de articular información educativa, automatizar procesos y reducir cargas ([SIGED, términos](https://siged.sep.gob.mx/SIGED/terminos.html)). Antes de construir, hay que demostrar que AulaLista llena un hueco local y no duplica un sistema obligatorio.

## Modelo de valor/costo y ROI

No es responsable inventar un ahorro monetario sin conocer salarios, número de escuelas, frecuencia de reportes y tiempos actuales. La primera estimación debe ser de horas y decisiones:

`valor operativo mensual = (minutos actuales − minutos con prototipo) × frecuencia × número de usuarios`.

Agregar valor educativo sólo cuando exista una cadena observable: `vista → decisión → acción → resultado`. No atribuir al tablero una mejora de aprendizaje o permanencia sin diseño comparativo.

**Señales de ROI para A:** al menos 30% menos tiempo para crear/actualizar la plantilla de salones; menos asignaciones ambiguas; cero duplicados en una carga de prueba; cambios auditables; adopción por al menos 4 de 6 directores piloto.

**Señales de ROI para B:** al menos 25% menos tiempo para preparar una reunión; una decisión documentada por salón cada periodo; reducción de pendientes vencidos sin aumento de captura docente; directores pueden explicar el significado de cada métrica y sus límites.

**Señales para no construir B:** la vista no cambia una decisión; el director debe corregir manualmente la mayoría de eventos; los datos se generan sólo para alimentar el tablero; o la misma información está disponible de forma suficiente en SIGED/Control Escolar.

**Umbral para considerar C:** sólo después de evidencia de dos ciclos de uso de A/B, una necesidad repetida de seguimiento individual, autorización institucional explícita, análisis de impacto de privacidad, controles de acceso probados y un protocolo humano de protección. Si el caso se reduce a “queremos saber quién va mal”, no construirlo.

## Costos y dependencias que suelen subestimarse

- **Calidad:** nombres de docentes, grupos, cambios de adscripción, periodos y eventos incompletos; Excel no es una fuente de verdad.
- **Interoperabilidad:** SIGED y sistemas estatales ya concentran datos; importar manualmente puede crear doble captura.
- **Infraestructura:** conectividad desigual, operación local, sincronización, copias, recuperación y soporte. El B debe funcionar con datos faltantes explícitos, no presentar ceros como éxito.
- **Gobernanza:** finalidad, minimización, base jurídica, roles, registro de accesos, retención, corrección, exportación y eliminación. SIGED señala que los datos personales están clasificados como confidenciales bajo la normativa mexicana ([SIGED, estadística educativa](https://www.siged.sep.gob.mx/SIGED/estadistica_educativa.html)).
- **Adopción:** capacitación y tiempo de docentes/directores; si el tablero se percibe como evaluación laboral, puede dañar confianza.
- **LLM:** costo de inferencia, dependencia de proveedor, filtración de prompts/archivos, errores de homónimos y falta de explicabilidad. Para A, una validación determinista de columnas debe preceder a cualquier asistencia lingüística.

## Hipótesis falsables y prueba mínima

1. **Ahorro:** seis directores completan la asignación de 20 salones al menos 30% más rápido con A que con su proceso actual, sin aumentar errores. Medir con datos sintéticos y plantilla anonimizada.
2. **Decisión:** durante cuatro semanas, B produce al menos una acción distinta por escuela que el director pueda vincular a una métrica agregada. Si no, el tablero es ornamental.
3. **Calidad:** al menos 98% de filas válidas se importan correctamente y 100% de homónimos/ambigüedades se marcan para confirmación.
4. **Carga:** la captura adicional de docentes no supera 10 minutos semanales por salón. Si supera ese umbral, eliminar campos o integrar una fuente existente.
5. **Confianza:** en pruebas de acceso, ningún director ve otra escuela, ningún rol ve datos fuera de su finalidad y los participantes entienden qué no significa la métrica.
6. **No necesidad de C:** en ocho entrevistas, la mayoría de casos se resuelve con acuerdos y pendientes de salón, sin exigir expediente nominal. Si se confirma, detener C.

## Fase recomendada

**Fase 1 — construir/validar A.** Salones, grado/grupo, docente asignado, importación con vista previa, conflictos, confirmación y auditoría. Sin alumnos, desempeño ni LLM autónoma.

**Fase 2 — sólo si se cumplen los umbrales.** Métricas agregadas del roadmap por salón y periodo, con diccionario de métricas, datos mínimos, no ranking, retención corta y vista de “qué acción sigue”. Iniciar con datos sintéticos y una escuela colaboradora.

**No fase — C.** No crear CRM nominal alumno–director, scoring de riesgo ni historial sensible hasta que entrevistas, evidencia de uso y revisión de privacidad demuestren una necesidad concreta que no puedan cubrir los sistemas y protocolos existentes.

**Recomendación final:** posicionar AulaLista como una capa local de coordinación y evidencia agregada, no como sistema paralelo de expediente estudiantil. La pregunta de inversión inmediata es “¿qué decisión directiva mejora y cuánto tiempo/errores elimina?”, no “¿qué campos de cada alumno podemos almacenar?”.

## Fuentes y limitaciones

- [SEP, SIGED: quiénes somos](https://siged.sep.gob.mx/SIGED/quienes_somos.html) y [términos](https://siged.sep.gob.mx/SIGED/terminos.html): describen objetivos y responsabilidades del sistema federal; no miden el uso real en cada escuela.
- [OECD, Digital Education Outlook 2023](https://www.oecd.org/en/publications/oecd-digital-education-outlook-2023_c74f03de-en/full-report/data-and-technology-governance-fostering-trust-in-the-use-of-data_171e56b9.html): análisis comparativo de gobernanza digital; sus ejemplos no son equivalentes automáticamente a México.
- [OECD, Results from TALIS 2024](https://www.oecd.org/en/publications/results-from-talis-2024_90df6235-en/full-report/the-demands-of-teaching_0e941e2f.html): encuesta internacional de docentes; evidencia de carga percibida, no cálculo de ahorro para AulaLista.
- [UNESCO, GEM 2024/5](https://www.unesco.org/reports/gem-report/en/2024): revisión global de liderazgo; no es una encuesta local de directores de Quintana Roo.
- [UNICEF México, situación 2018–2025](https://www.unicef.org/mexico/informes/situacion-derechos-ninez-adolescencia-mexico): análisis nacional publicado en 2026; presenta asociaciones y fuentes secundarias, no causalidad de un tablero.
- [UNESCO, Guidance for generative AI](https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research): orientación normativa/ética, no evaluación de un producto específico.
