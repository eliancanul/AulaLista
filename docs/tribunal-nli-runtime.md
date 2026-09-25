# Tribunal NLI local (#126)

El runtime de Transformers es opcional. Instalarlo con `pip install -r requirements-nli.txt` sólo si se van a ejecutar checkpoints reales. Las pruebas ordinarias usan fakes y no requieren pesos ni red.

Checkpoints verificados localmente el 2026-09-25:

| Candidato | Revisión SHA fijada | `id2label` |
| --- | --- | --- |
| `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli` | `0a71e92a985b6e1ad1828cf67ce9c459639c1dca` | `0=entailment, 1=neutral, 2=contradiction` |
| `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | `b5113eb38ab63efdd7f280f8c144ea8b13f978ce` | `0=entailment, 1=neutral, 2=contradiction` |

`load_cached_tribunal()` sólo busca `config.json`, `model.safetensors` y tokenizer ya descargados en la caché de Hugging Face. Exige un SHA de 40 caracteres, usa `local_files_only=True` y `trust_remote_code=False`; si faltan archivos, falla con `ModelUnavailableError`. No usa `snapshot_download`, que exigiría también ONNX y PyTorch `.bin` del repositorio completo.

```python
from curriculum.tribunal import MINILM_CANDIDATE
from curriculum.tribunal_transformers import load_cached_tribunal

tribunal = load_cached_tribunal(
    MINILM_CANDIDATE,
    "0a71e92a985b6e1ad1828cf67ce9c459639c1dca",
    timeout_seconds=30,
    batch_size=8,
    device="cpu",
)
receipt = tribunal.evaluate(claim, atlas_receipt, "El proyecto se llama El nombrario del grupo.")
payload = receipt.to_dict()
```

La hipótesis debe ser explícita. El recibo conserva logits crudos, decisiones por fragmento, estado operativo, veredicto opcional y procedencia. `neutral` y empate producen evidencia insuficiente con motivos distintos; una ejecución fallida no tiene veredicto. La salida permanece en shadow mode y no cambia `AtomicClaim.state`, aprobación, publicación ni `CurriculumProgress`.

El timeout limita la espera del llamador. Un worker bloqueado puede continuar; el adaptador impide usar simultáneamente el mismo modelo hasta que termine. `max_length=512` trunca pares largos y queda registrado en `runtime_config`. La campaña semántica y la selección de modelo pertenecen a #119/#122.

## Smoke local con planeación real

```sh
AULALISTA_RUN_REAL_NLI_SMOKE=1 .venv/bin/pytest -q -s tests/test_t126_real_pipeline_smoke.py
```

La prueba optativa lee C02, un compendio privado de 44 páginas del corpus de calibración, desde la ruta ya registrada en `docs/research/goldset-importacion-curricular-manifest-v1.json`. Comprueba SHA-256, `CurriculumSourceInterpreter.prepare()` y su verificación mecánica, compilación de `AtomicClaim`, recuperación del Atlas, inferencia batch con ambos checkpoints y recibos serializables. Bloquea llamadas de red y comprueba que el PDF y el estado de la afirmación no cambien. No copia el PDF ni sus fragmentos al repositorio.

**Límite:** el Atlas disponible para esta corrida es el fixture sintético de #125. No existe todavía un índice real de SEP incorporado con permiso, versión e identidad verificados. Por ello la prueba demuestra integración técnica con una planeación real, no corroboración curricular frente a una fuente oficial. C02 pertenece a calibración; el gold semántico y la adjudicación no están cerrados. No se fija un veredicto esperado ni se calcula precisión.
