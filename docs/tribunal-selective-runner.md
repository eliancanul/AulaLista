# Orquestador selectivo del tribunal (#127)

`curriculum.tribunal_orchestrator.SelectiveRunner` conecta afirmaciones atómicas, recuperación de Atlas y los dos jueces NLI de #126. Está **apagado por defecto**. Todo resultado es una señal experimental en `shadow_mode`: `accept` significa que la política seleccionó una afirmación para el estudio, no que una persona aprobó currículo. Nunca cambia `AtomicClaim.state`, la revisión editorial, la publicación o `CurriculumProgress`.

## Ruta

1. `run_dossier()` usa el compilador de #124 y recibe hipótesis explícitas por `claim_id`; las que faltan se abstienen. También puede usarse `run()` con una afirmación ya compilada.
2. Atlas entrega candidatos y recibo. Cero candidatos, índice no disponible o error terminan en abstención.
3. El primer juez emite su recibo de #126. Una regla `primary_gate` versionada puede detener la ruta si el veredicto es respaldo o contradicción.
4. Si la regla no acepta, la ruta registra `escalated` y llama a un segundo modelo distinto. Desacuerdo, neutralidad, timeout o modelo ausente terminan en abstención. Acuerdo entre jueces se registra como acuerdo, **no como exactitud**; sólo una regla `agreement_gate` explícita puede seleccionar una salida.

No hay umbral numérico incorporado ni ganador de modelo. Las reglas deben recibir ID y versión; cambiar su comportamiento exige cambiar la versión para que la llave de idempotencia no reutilice resultados viejos. La interfaz `AppealAdapter` reserva una extensión local futura; este runner no ejecuta apelaciones generativas.

## Recibos y reintentos

El llamador elige `InMemoryReceiptStore` para pruebas o `SQLiteReceiptStore(path)` para persistencia local. El recibo JSON conserva identidad de la solicitud, hash de fuente e hipótesis, versión/hash del índice, política, transiciones, candidatos por referencia y puntuación, logits crudos, modelo/versión, motivo de abstención y telemetría. No persiste premisas, hipótesis literales, extractos, consultas, PDF, mensajes de excepción ni configuración arbitraria del runtime. El archivo SQLite se crea con permiso `0600`.

La misma entrada y `attempt=1` devuelve el mismo recibo sin repetir inferencia. Para reintentar un fallo temporal, llamar con `attempt=2`; el recibo nuevo contiene `previous_run_id` y preserva el primero. `summarize_runs()` calcula cobertura con el último intento de cada solicitud y costo operativo con todos los intentos únicos. Estos datos miden operación, nunca precisión o calidad semántica. Un hook opcional `on_receipt` recibe el recibo ya persistido y no puede alterar la decisión.

Si falla la persistencia, la llamada falla sin entregar una selección. La aplicación productiva no importa ni activa este runner automáticamente; el harness de #119 puede consumir `receipt.to_dict()` como registro derivado junto con su captura raw separada. El gold/adjudicación y la evaluación de calidad siguen fuera de #127.

## Verificación

```sh
.venv/bin/pytest -q tests/test_t127_selective_orchestrator.py tests/test_t126_tribunal_nli.py tests/test_t125_atlas_retrieval.py tests/test_t124_atomic_claims.py
```

Las pruebas de #127 usan fixtures sintéticos y adaptadores falsos. No necesitan pesos, corpus SEP real ni red.
