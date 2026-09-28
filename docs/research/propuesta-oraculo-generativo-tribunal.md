# Propuesta de investigación: juez generativo como oráculo diagnóstico

**Estado:** propuesta exploratoria. No describe una implementación, un resultado medido ni un modelo seleccionado.

## Pregunta

¿Un juez generativo local puede ayudar a distinguir errores de extracción y recuperación de evidencia de errores de clasificación NLI, cuando revisa una afirmación junto con su evidencia y los recibos de las etapas anteriores?

“Oráculo” es un nombre de trabajo para esta comparación. El juez generativo no se considera verdad de referencia ni reemplaza la adjudicación humana.

## Hipótesis

En una muestra adjudicada independientemente, un juez generativo podría aportar una categoría diagnóstica útil en algunos desacuerdos o abstenciones de MiniLM y mDeBERTa. También podría repetir los errores de esos componentes, introducir otros o aumentar latencia y costo sin mejorar el diagnóstico. Ambas posibilidades deben permanecer abiertas.

## Diseño propuesto

1. **Congelar el protocolo y la evidencia.** Usar primero fixtures sintéticos. Incorporar documentos reales solo con permiso, identidad y procedencia verificadas. Congelar afirmaciones, fragmentos recuperados, versiones/configuración y recibos para que los jueces comparen el mismo material.
2. **Crear una referencia independiente.** Definir una guía de adjudicación humana que separe error de extracción, asociación estructural, recuperación, clasificación NLI, falta de evidencia y caso no evaluable. Conservar desacuerdos humanos como tales; no forzar una etiqueta.
3. **Comparar condiciones.** Medir MiniLM y mDeBERTa por separado y en el flujo selectivo existente. Ejecutar el juez generativo como brazo diagnóstico sobre la muestra completa y reportar aparte el subconjunto de desacuerdos. Esto evita confundir el efecto del modelo con el criterio que decide cuándo invocarlo.
4. **Mantenerlo fuera de la ruta de producto.** El juez opera en sombra: no confirma afirmaciones, no aprueba planeaciones, no publica contenido ni modifica `CurriculumProgress`. Sus salidas son hipótesis diagnósticas para revisión humana.
5. **Registrar límites operativos.** Comparar acuerdo con la referencia, cobertura, abstenciones y errores por categoría, además de latencia, memoria, consumo y fallos. Conservar recibos sanitizados; no enviar documentos docentes a servicios externos.

## Candidatos y factores

Como candidatos iniciales de un experimento local pueden evaluarse modelos instructivos como Qwen2.5-7B-Instruct o Llama-3.1-8B-Instruct con cuantización de 4 bits. Son ejemplos, no recomendaciones ni ganadores. Antes de fijar uno habría que verificar licencia, disponibilidad local, compatibilidad del runtime y consumo en el hardware objetivo. La cuantización y el formato de ejecución serían factores del experimento, no supuestos de equivalencia.

## Criterio para continuar

Implementar un adaptador de apelación generativa solo tendría sentido si el protocolo congelado muestra una mejora diagnóstica reproducible frente a los jueces NLI, con límites aceptables de abstención, latencia, memoria y privacidad. Si no, conservar el resultado como evidencia negativa y mantener el flujo actual.

## Límites de interpretación

- El resultado mide utilidad diagnóstica en el conjunto y condiciones definidos; no demuestra comprensión, calidad curricular general ni impacto pedagógico.
- El acuerdo con anotadores no elimina errores de adjudicación ni sesgos del conjunto.
- Ningún umbral o salida generativa debe tratarse como probabilidad calibrada sin evaluación específica.
- No se debe afirmar que el juez identifica causalmente el origen de un error sin validar la taxonomía y el procedimiento de adjudicación.

Esta propuesta puede evaluarse dentro de la campaña de investigación y benchmarks de #119. El tribunal selectivo de #127 ya está integrado como infraestructura experimental; eso no implica que el juez generativo esté implementado.
