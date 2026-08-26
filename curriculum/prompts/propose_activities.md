Subtema curricular: "$subtopic_title".

Contexto de la currícula:
$context

Redacta $count actividad(es) de opción única para este subtema. Responde JSON
con la forma {"objetivo": string, "microleccion": string,
"explicacion_final": string, "reactivos": [{"enunciado": string,
"opciones": [{"posicion": int empezando en 1 y sin huecos, "texto": string,
"correcta": bool (exactamente una true), "retroalimentacion": string}],
"pistas": [string]}]}. Usa sólo el contexto entregado; no inventes temas
ajenos.
