"""Adaptador opcional para ejecutar checkpoints NLI ya presentes en caché local.

No importa Transformers, Torch ni Hugging Face Hub al cargar curriculum.tribunal.
La factoría exige una revisión SHA y usa sólo archivos locales; nunca descarga.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from curriculum.tribunal import (
    ModelUnavailableError,
    NLIClass,
    NLIModelConfig,
    NLIPair,
    RawNLIOutput,
    Tribunal,
)


def checkpoint_label_mapping(id2label: Mapping[int, str]) -> dict[str, NLIClass]:
    """Lee el orden real del checkpoint; rechaza labels genéricos o incompletos."""
    if set(id2label) != {0, 1, 2}:
        raise ValueError("El checkpoint NLI debe declarar exactamente los índices 0, 1 y 2")
    mapping: dict[str, NLIClass] = {}
    for index in range(3):
        label = id2label[index]
        if not isinstance(label, str):
            raise ValueError("Los labels del checkpoint deben ser texto")
        try:
            meaning = NLIClass(label.lower())
        except ValueError as exc:
            raise ValueError(f"Label NLI incompatible en índice {index}: {label}") from exc
        mapping[label] = meaning
    if len(mapping) != 3 or set(mapping.values()) != set(NLIClass):
        raise ValueError("El checkpoint debe declarar entailment, neutral y contradiction una vez cada uno")
    return mapping


class TransformersNLIAdapter:
    """Inferencia batch local con logits crudos, sin softmax ni escrituras de producto."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        model: Any,
        torch_module: Any,
        config: NLIModelConfig,
        batch_size: int = 8,
        max_length: int = 512,
        device: str = "cpu",
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size debe ser un entero positivo")
        if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
            raise ValueError("max_length debe ser un entero positivo")
        if not isinstance(device, str) or not device.strip():
            raise ValueError("device es obligatorio")
        labels = checkpoint_label_mapping(model.config.id2label)
        if labels != dict(config.label_mapping):
            raise ValueError("El mapeo configurado no coincide con id2label del checkpoint")
        self.label_mapping = MappingProxyType(labels)
        self._label_order = tuple(model.config.id2label[index] for index in range(3))
        self._tokenizer = tokenizer
        self._model = model.to(device).eval()
        self._torch = torch_module
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._lock = threading.Lock()

    def infer_batch(self, pairs: tuple[NLIPair, ...]) -> list[RawNLIOutput]:
        if not pairs:
            return []
        # Tras un timeout el worker puede seguir ejecutándose. Evita usar el
        # mismo modelo simultáneamente en una nueva corrida.
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("El adaptador NLI sigue ocupado por otra corrida")
        try:
            results: list[RawNLIOutput] = []
            for start in range(0, len(pairs), self._batch_size):
                chunk = pairs[start : start + self._batch_size]
                encoded = self._tokenizer(
                    [pair.premise for pair in chunk],
                    [pair.hypothesis for pair in chunk],
                    padding=True,
                    truncation=True,
                    max_length=self._max_length,
                    return_tensors="pt",
                )
                encoded = {name: tensor.to(self._device) for name, tensor in encoded.items()}
                with self._torch.inference_mode():
                    logits = self._model(**encoded).logits
                rows = logits.detach().cpu().tolist()
                if len(rows) != len(chunk) or any(len(row) != 3 for row in rows):
                    raise ValueError("El checkpoint no devolvió tres logits por par")
                results.extend(
                    RawNLIOutput(dict(zip(self._label_order, map(float, row))))
                    for row in rows
                )
            return results
        finally:
            self._lock.release()


def load_cached_tribunal(
    model_id: str,
    revision: str,
    *,
    timeout_seconds: float = 30.0,
    batch_size: int = 8,
    max_length: int = 512,
    device: str = "cpu",
) -> Tribunal:
    """Construye un tribunal desde pesos locales fijados por commit SHA.

    Un checkpoint ausente falla al cargar con ModelUnavailableError. No se
    realiza tráfico de red; el llamador puede usar Tribunal(config, None) para
    emitir un recibo operativo model_unavailable si necesita registrar la corrida.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id es obligatorio")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision debe ser el SHA completo de 40 caracteres")
    try:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise ModelUnavailableError("Faltan dependencias opcionales de NLI") from exc

    try:
        # snapshot_download(local_files_only=True) exige también ONNX y .bin;
        # localizar config.json basta para hallar el snapshot selectivo.
        config_path = hf_hub_download(
            repo_id=model_id, filename="config.json", revision=revision, local_files_only=True
        )
        snapshot = Path(config_path).parent
        model = AutoModelForSequenceClassification.from_pretrained(
            snapshot, local_files_only=True, use_safetensors=True, trust_remote_code=False
        )
        tokenizer = AutoTokenizer.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=False
        )
    except (OSError, ValueError) as exc:
        raise ModelUnavailableError("Checkpoint NLI ausente o ilegible en caché local") from exc

    label_mapping = checkpoint_label_mapping(model.config.id2label)
    config = NLIModelConfig(
        model_id=model_id,
        version=revision,
        label_mapping=label_mapping,
        timeout_seconds=timeout_seconds,
        runtime_config={
            "backend": "transformers",
            "device": device,
            "batch_size": batch_size,
            "max_length": max_length,
            "local_files_only": True,
        },
    )
    adapter = TransformersNLIAdapter(
        tokenizer=tokenizer,
        model=model,
        torch_module=torch,
        config=config,
        batch_size=batch_size,
        max_length=max_length,
        device=device,
    )
    return Tribunal(config, adapter)
