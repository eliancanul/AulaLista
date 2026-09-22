# Plantillas de anotación y adjudicación v1

La anotación independiente es JSON Lines y valida contra `goldset-importacion-curricular-schema-v1.json`. Copie esta forma para cada página; sustituya todos los valores entre `<…>`. Una plantilla no es una anotación y no cuenta para cobertura.

```json
{"schema_version":"1.0.0","annotation_id":"<DOCUMENT>_P<NN>_<ANNOTATOR>","annotator":"<identity>","document_id":"<DOCUMENT>","document_sha256":"<64-hex>","page":1,"page_state":"quarantined","page_reason":"<visible reason>","regions":[],"relations":[],"contradictions":[],"review_status":"independent"}
```

Para adjudicar, no sobrescriba A ni B. Cree un archivo separado con `review_status: "adjudicated"`, identidad de la persona adjudicadora y, para cada diferencia, una región o relación nueva respaldada por el PDF renderizado. Registre el desacuerdo original como una entrada en `contradictions` con referencias a los IDs de A/B; no elija por mayoría ni por el extractor.

## Ejecución read-only

```bash
.venv/bin/python scripts/shadow_import_curriculum.py \
  --manifest docs/research/goldset-importacion-curricular-manifest-v1.json \
  --output-dir /tmp/aulalista-shadow-raw
```

Cada corrida deja un JSON por documento/adaptador y `comparison-matrix.json`. La matriz sólo resume cobertura, estado, tiempos, RSS del proceso y tamaño de artefacto; CER/WER, IoU/mAP, GriTS/TEDS, jerarquía, relaciones, provenance y riesgo-cobertura permanecen `not_evaluable` hasta tener dos anotaciones completas y adjudicadas. `--resume` reutiliza sólo un resultado con el mismo hash fuente y adapter; hay que borrar el artefacto para forzar una corrida nueva.
