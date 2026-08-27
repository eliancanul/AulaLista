# ADR-0007: Resultados seudónimos agrupados y retención por salón

- **Estado:** Aceptado
- **Fecha:** 2026-08-27

## Contexto

La docente necesita decidir qué observar o reenseñar a partir de una sesión,
sin convertir AulaLista en un sistema nominal de alumnos. El apodo y la
asignación de dispositivo son datos temporales: no pueden sobrevivir al cierre.
La política de #86 además elimina la respuesta libre de encuesta, que podría
introducir contenido identificable, y requiere un cierre anual recuperable por
salón sin destruir el historial curricular.

## Decisión

1. Cada `StudentTurn` genera una `participant_key` UUID aleatoria independiente
   del apodo, nombre o dispositivo. Al cerrar, cada `PseudonymousResult` copia
   esa clave y una actividad opaca; se eliminan los turnos y sus relaciones
   temporales.
2. `ClassroomGroup` es una etiqueta creada por la maestra y sólo agrupa
   `ClassroomSession`. No mantiene roster. Las sesiones sin grupo siguen
   operando normalmente.
3. La lectura docente ofrece agregados por sesión/salón como superficie
   principal. El registro individual de una sesión muestra una etiqueta de ocho
   caracteres y estado por actividad como señal de observación; no muestra UUID
   completo, apodo ni lenguaje diagnóstico o de calificación. Las
   exportaciones usan esa misma etiqueta corta, sin UUID de resultado ni de
   participante.
4. `PseudonymousSurveyResponse` guarda sólo un entero de 1 a 5. La maestra ve
   exclusivamente el promedio grupal; las respuestas libres históricas se
   eliminan en la migración de cambio de contrato.
5. El cierre de año por salón requiere docente autenticada, POST y confirmación
   visible. Borra resultados y encuestas de ese salón, y conserva paquetes,
   snapshots, roadmaps, `CurriculumProgress` y sesiones sin sus resultados.
6. Las rutas sensibles de una sesión requieren la maestra registrada al
   prepararla. La migración sólo recupera esa relación cuando el salón existente
   ya la prueba; una sesión histórica sin propietaria se marca explícitamente y
   conserva sólo el límite histórico de personal autenticado. Una sesión nueva
   sin esa marca no obtiene ese acceso por omisión.

## Consecuencias

La `participant_key` continúa siendo un seudónimo y no habilita cuentas,
seguimiento nominal ni identificación longitudinal fuera de las filas
conservadas. El flujo no usa LLM ni concede autoridad curricular, editorial o
de calificación al sistema. La capa individual requiere el aviso y
consentimiento institucional definido fuera de este repositorio.
