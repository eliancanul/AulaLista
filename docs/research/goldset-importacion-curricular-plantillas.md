# Plantillas de anotación y adjudicación v1

La anotación independiente es JSON Lines y valida contra `goldset-importacion-curricular-schema-v1.json`. Copie esta forma para cada página; sustituya todos los valores entre `<…>`. Una plantilla no es una anotación y no cuenta para cobertura.

```json
{"schema_version":"1.0.0","annotation_id":"<DOCUMENT>_P<NN>_<ANNOTATOR>","annotator":"<identity>","document_id":"<DOCUMENT>","document_sha256":"<64-hex>","page":1,"page_state":"quarantined","page_reason":"<visible reason>","regions":[],"relations":[],"contradictions":[],"review_status":"independent"}
```

Para adjudicar, no sobrescriba A ni B. Cree un archivo separado con `review_status: "adjudicated"`, identidad de la persona adjudicadora y, para cada diferencia, una región o relación nueva respaldada por el PDF renderizado. Registre el desacuerdo original como una entrada en `contradictions` con referencias a los IDs de A/B; no elija por mayoría ni por el extractor.

## Estado de ejecución

El comando histórico de este documento ya no corresponde al CLI vigente. El harness autónomo y sus pruebas sintéticas están en [aulalista-research](https://github.com/eliancanul/aulalista-research). El manifiesto privado de este directorio referencia documentos locales y **no** se traslada al repositorio público. Cualquier nueva corrida sobre ese corpus requiere comprobar primero permiso, fuente y partición, y usar los subcomandos actuales `run-one`, `close-raw` e `interpret` según sus argumentos reales.

Los recibos técnicos pueden resumir cobertura, estado, tiempos y recursos. CER/WER, IoU/mAP, GriTS/TEDS, jerarquía, relaciones y riesgo-cobertura permanecen `not_evaluable` hasta contar con anotaciones independientes completas y adjudicadas. Una plantilla o un recibo de ejecución no cierra ese gate.
