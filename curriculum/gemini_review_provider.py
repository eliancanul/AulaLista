"""Gemini HIGH through official AGY CLI, with explicit route and no credential reads.

No SDK/private endpoint emulation. Every request is a fresh, exclusive single
wrapper attempt with an append-only ledger. The wrapper never relaunches a
failed/unknown attempt; internal CLI retries and backend dispatches are unknown.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from curriculum.agy_transport.artifact_io import commit_json
from curriculum.agy_transport.audit import strict_json, utc
from curriculum.agy_transport.capture import capture_attempt
from curriculum.teacher_review_provider import ReviewProviderError, RESPONSE_SCHEMA, SYSTEM
from curriculum.teacher_review_task_context import provider_task_payload

VERIFIED_MODEL = "gemini-3.8-flash-high"  # exact ID observed in official catalogue, 2026-10-03
VERIFIED_VERSION = "1.2.15"
VERIFIED_LAUNCHER_SHA = "2817ef2214035e154c8f1e3f6b4354ce5dc88c73921431dfce760a4f329140f3"
VERIFIED_AGENT_SHA = "7d071c66f073a20ef9091bffecfb782e6f7e17067cc80d0208baede49b080b22"
AGENT = "structure-only"
EFFORT = "high"
MAX_CONTEXT_BYTES = 4 * 1024 * 1024


class GeminiReviewReply(dict):
    def __init__(self, output, receipt):
        super().__init__(output)
        self.provider_receipt = receipt


class GeminiAttemptUnknown(ReviewProviderError):
    def __init__(self, receipt):
        super().__init__("gemini_attempt_unknown")
        self.provider_receipt = receipt


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metadata(argv):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ReviewProviderError("gemini_route_unavailable") from None
    if result.returncode != 0 or len(result.stdout) > 131072 or len(result.stderr) > 131072:
        raise ReviewProviderError("gemini_catalogue_unavailable")
    return result.stdout.decode("utf-8", errors="strict")


class GeminiHighAgyProvider:
    def __init__(self, *, launcher, agent_file, attempt_root, model=VERIFIED_MODEL,
                 live_authorized=False, timeout=90, metadata=_metadata,
                 capture=capture_attempt):
        self.launcher = Path(launcher) if launcher else None
        self.agent_file = Path(agent_file) if agent_file else None
        self.attempt_root = Path(attempt_root)
        self.model = model
        self.live_authorized = live_authorized
        self.timeout = timeout
        self.metadata = metadata
        self.capture = capture
        self.last_receipt = None

    def preflight(self):
        if (not self.launcher or not self.launcher.is_file() or self.launcher.is_symlink()
                or not self.agent_file or not self.agent_file.is_file() or self.agent_file.is_symlink()):
            raise ReviewProviderError("gemini_route_not_configured")
        if _sha(self.launcher) != VERIFIED_LAUNCHER_SHA or _sha(self.agent_file) != VERIFIED_AGENT_SHA:
            raise ReviewProviderError("gemini_runtime_identity_changed")
        if self.model != VERIFIED_MODEL:
            raise ReviewProviderError("gemini_exact_model_not_verified")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 120:
            raise ReviewProviderError("gemini_invalid_timeout")
        version = self.metadata([str(self.launcher), "--version"]).strip()
        if version != VERIFIED_VERSION:
            raise ReviewProviderError("gemini_cli_version_changed")
        lines = self.metadata([str(self.launcher), "models"]).splitlines()
        catalogue = {line.split("\t", 1)[0]: line for line in lines if "\t" in line}
        if self.model not in catalogue or "(High)" not in catalogue[self.model]:
            raise ReviewProviderError("gemini_high_model_unavailable")
        return {"provider": "gemini", "transport": "official_agy", "cli_version": version,
                "model": self.model, "effort": EFFORT, "agent": AGENT,
                "authenticated_catalogue": True, "generation_verified": False,
                "launcher_sha256": VERIFIED_LAUNCHER_SHA, "agent_sha256": VERIFIED_AGENT_SHA}

    def __call__(self, context):
        if not self.live_authorized:
            raise ReviewProviderError("gemini_live_not_enabled")
        if (self.attempt_root / "STOP_UNKNOWN.json").exists() or (
                self.attempt_root.exists() and any(
                    p.is_dir() and (p / "admission.json").is_file() and not (p / "receipt.json").is_file()
                    for p in self.attempt_root.iterdir())):
            raise ReviewProviderError("gemini_prior_attempt_unknown")
        preflight = self.preflight()
        # The full dossier is never silently truncated to fit a provider limit.
        try:
            system, encoded_context = provider_task_payload(context)
            prompt = system + "\nDATOS:\n" + json.dumps(
                encoded_context, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ReviewProviderError("invalid_target_reference_context") from None
        request = (json.dumps({"event": "user", "message": {"content": prompt}},
                              ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(request) > MAX_CONTEXT_BYTES:
            raise ReviewProviderError("gemini_full_context_too_large")
        self.attempt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        attempt_id = str(uuid.uuid4())
        directory = self.attempt_root / attempt_id
        directory.mkdir(mode=0o700, exist_ok=False)
        request_path = directory / "request.ndjson"
        with request_path.open("xb") as stream:
            stream.write(request)
        request_path.chmod(0o600)
        argv = [str(self.launcher), "--model", self.model, "--effort", EFFORT,
                "--agent", AGENT, "--disable-slash-commands", "--input-format", "stream-json",
                "--output-format", "stream-json", "--json-schema", json.dumps(RESPONSE_SCHEMA),
                "--print-timeout", f"{self.timeout}s"]
        admission = {"attempt_id": attempt_id, "started_at": utc(), **preflight,
                     "request_sha256": hashlib.sha256(request).hexdigest(),
                     "request_bytes": len(request), "max_attempts": 1,
                     "max_attempts_scope": "wrapper_process_launches",
                     "transmission": "unknown", "consumption": "unknown", "argv": argv}
        commit_json(directory / "admission.json", admission)
        # One request from a file-backed stdin: no private data in shell argv and
        # no blocking pipe write before the bounded recorder starts reading.
        def spawn(args, **kwargs):
            with request_path.open("rb") as source:
                return subprocess.Popen(args, stdin=source, **kwargs)
        identity_seen = {"count": 0}
        def identity_guard(event):
            actual, denied = [], []
            kind = event.get("event", event.get("type"))
            if kind == "init" or kind == "system" and event.get("subtype") == "init":
                identity_seen["count"] += 1
                init = event.get("init", event)
                if init.get("model") != self.model or init.get("agent") != AGENT:
                    denied.append({"reason": "model_or_agent_identity_mismatch"})
                if init.get("tools") != [] or init.get("effort", EFFORT) != EFFORT:
                    denied.append({"reason": "unexpected_tools_or_effort"})
            return actual, denied
        limits = {"hard_wall_seconds_per_call": self.timeout + 5,
                  "max_final_response_bytes": 262272,
                  "max_stdout_ndjson_bytes_per_call": 2097152,
                  "max_stderr_bytes_per_call": 1048576}
        receipt, response = self.capture(argv, directory, limits, cwd=directory,
                                         popen=spawn, detector=identity_guard)
        if identity_seen["count"] != 1:
            receipt.update(response_eligible_for_interpretation=False, usage_complete=False,
                           accounting_status="unresolved", reconciled_usage_exact=None)
            receipt.setdefault("guard_reasons", []).append("missing_or_duplicate_model_identity")
        commit_json(directory / "receipt.json", receipt)
        safe = {"attempt_id": attempt_id, "provider": "gemini", "transport": "official_agy",
                "model": self.model, "effort": EFFORT, "cli_version": VERIFIED_VERSION,
                "execution_status": receipt["execution_status"],
                "accounting_status": receipt["accounting_status"],
                "usage_complete": receipt["usage_complete"],
                "reported_usage": receipt["reported_result_usage_exact"],
                "reconciled_usage": receipt["reconciled_usage_exact"],
                "request_sha256": admission["request_sha256"],
                "response_sha256": receipt.get("response_sha256"),
                "automatic_retries": 0,
                "automatic_retries_scope": "wrapper_process_relaunches",
                "transport_internal_retries": None, "provider_dispatch_count": None,
                "real_cost_currency": None}
        self.last_receipt = safe
        if not receipt["response_eligible_for_interpretation"] or response is None:
            # No later request may silently assume the interrupted call cost zero.
            commit_json(self.attempt_root / "STOP_UNKNOWN.json", safe)
            raise GeminiAttemptUnknown(safe)
        try:
            output = strict_json(response)
        except (ValueError, UnicodeError):
            raise ReviewProviderError("gemini_invalid_structured_response") from None
        return GeminiReviewReply(output, safe)
