A continuación aparece la lista numerada de temas candidatos detectados en
una currícula escolar, cada uno con sus páginas entre corchetes. Varios
candidatos pueden ser fragmentos del mismo tema curricular real (por ejemplo
"El uso de las vocales", "Aprendizaje de vocales" y "Vocales" son UN tema).
También puede haber títulos de actividades sueltas ("Colorear según números",
"Escribir números del 1 al 10") que NO son temas por sí solos y deben
agruparse bajo el tema curricular al que pertenecen.

Agrúpalos: responde JSON con la forma
{"temas": [{"titulo": string, "indices": [int]}]} donde cada entrada es un
TEMA curricular real con su nombre canónico (sin verbos de actividad como
"colorea", "resuelve" o "escribe"), y "indices" lista los números de los
candidatos que forman ese tema.

Reglas:
- Usa solo los índices de la lista; no inventes temas sin candidatos.
- Cada índice debe aparecer en exactamente un grupo.
- Los candidatos que no pertenezcan claramente a ningún tema curricular
  déjalos fuera de los grupos: los conservaremos tal cual para revisión
  humana.
- No repitas temas equivalentes: un tema curricular = una entrada.

Candidatos:

$candidates
