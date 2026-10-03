# Fixtures sintéticas de desarrollo

Esta distribución contiene nueve entradas sintéticas derivadas de código de pruebas público del repositorio. Conserva sus textos, segmentos, expectativas técnicas y procedencia verificable: archivo, commit público, SHA-256, líneas y transformación. No contiene inventarios de documentos reales, datos de docentes, material reservado ni respuestas de proveedores.

`cases.v1.json` y `rubric.v1.json` están fijados por `freeze.v1.json`. La distribución `sprint-corpus-1.0.1-synthetic` conserva las nueve entradas y la rúbrica originales; su manifiesto incluye únicamente esos dos archivos. El número de distribución cambia porque se retiraron metadatos ajenos a los casos sintéticos. No se afirma que sea una nueva muestra ni una evaluación nueva.

Desde la raíz del checkout:

```sh
python -m scripts.sprint_eval.corpus
python -m scripts.sprint_eval.corpus --case SC08
python -m pytest tests/fixtures/sprint_corpus -q
python tests/fixtures/sprint_corpus/check_compatibility.py > /tmp/synthetic-compatibility.json
```

El cargador verifica los hashes y la procedencia contra el código público de la base indicada. Una modificación de entradas o fuentes exige una nueva distribución explícita; no se actualizan hashes para ocultar diferencias. Los reportes se generan fuera del repositorio.

## Alcance

| Casos | Control técnico |
| --- | --- |
| SC01, SC02 | Proyecto, propósito o finalidad explícitos y nivel escolar ausente |
| SC03, SC04 | Títulos multilínea y límites entre campos |
| SC05, SC06, SC07 | Propósito vacío, citas ambiguas y límites de secciones |
| SC08, SC09 | Grados escritos sin un nivel escolar demostrado |

SC01, SC08 y SC09 pertenecen a una familia; SC03 y SC04 están relacionados. No son nueve documentos independientes ni permiten significación estadística. Todos son ejemplos expuestos de desarrollo, seleccionados por agentes y sin validación docente.

La rúbrica comprueba coincidencia literal, incertidumbre, cobertura y referencias. `evaluate` conserva denominadores y marca `semantic_status=NOT_EVALUATED`; no establece implicación semántica ni calidad pedagógica. Los juicios registrados por `score_review` conservan identidad y evidencia del evaluador, sin convertir una revisión de agente en aprobación docente.

Las expectativas no se envían como fuente a modelos. `--case` emite solo `document_id` y `source_segments`. El puente de segmentos verifica texto, páginas y offsets sin cambiar el texto original. Una propuesta, un esquema válido o un control técnico aprobado nunca aprueban un borrador.

No hay corpus FINAL, inferencia real, comparación válida entre modelos ni ganador. Para validar utilidad pedagógica se necesita una evaluación autorizada y revisión humana por separado.
