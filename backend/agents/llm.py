"""Multi-brain runtime for SwarmTrade Darwin V0.11.

Research reasoning can use OpenAI models through the Responses API. Execution,
paper accounting and hard risk gates stay deterministic. A Vercel AI Gateway
adapter remains available for deployments that already use it.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import time
from typing import Any

import httpx
from jsonschema import validate


BRAIN_DEFAULTS: dict[str, dict[str, str]] = {
    "atlas": {"runtime": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
    "curie": {"runtime": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
    "evolve": {"runtime": "openai", "model": "gpt-5.6-terra", "reasoning": "medium"},
    "forge": {"runtime": "deterministic", "model": "deterministic-paper-engine", "reasoning": "none"},
    "judge": {"runtime": "openai", "model": "gpt-5.6-terra", "reasoning": "medium"},
    "mnemosyne": {"runtime": "openai", "model": "gpt-5.6-luna", "reasoning": "low"},
    "cerberus": {"runtime": "deterministic", "model": "deterministic-risk-gate", "reasoning": "none"},
    "hermes": {"runtime": "deterministic", "model": "deterministic-executor", "reasoning": "none"},
}

# USD per million tokens, current OpenAI list prices for the default GPT-5.6 family.
# Kept in code only for observability; billing truth always comes from the provider.
MODEL_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (4.0, 20.0),
    "gpt-5.6": (4.0, 20.0),
    "gpt-5.6-terra": (2.0, 12.0),
    "gpt-5.6-luna": (0.20, 1.20),
}


def _canonical_model(model: str) -> str:
    return model.split("/", 1)[-1] if "/" in model else model


def estimate_cost_usd(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    price = MODEL_PRICES_PER_MTOK.get(_canonical_model(model))
    if not price or prompt_tokens is None or completion_tokens is None:
        return None
    return (float(prompt_tokens) * price[0] + float(completion_tokens) * price[1]) / 1_000_000.0


@dataclass
class LLMResult:
    ok: bool
    agent_id: str
    model: str
    data: dict[str, Any]
    latency_ms: int
    error: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    runtime: str = "openai"
    provider: str = "openai"
    reasoning_effort: str = "none"
    prompt_version: str = "v1"
    estimated_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "agent_id": self.agent_id,
            "model": self.model,
            "data": self.data,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "runtime": self.runtime,
            "provider": self.provider,
            "reasoning_effort": self.reasoning_effort,
            "prompt_version": self.prompt_version,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


class AgentBrain:
    """Schema-constrained brain with per-agent runtime selection.

    Runtime values:
      - openai: direct OpenAI Responses API (OPENAI_API_KEY)
      - gateway: Vercel AI Gateway Chat Completions compatibility
      - deterministic: no model call, returns validated fallback
    """

    def __init__(self, agent_id: str, system_prompt: str, *, prompt_version: str = "v1"):
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.prompt_version = prompt_version
        defaults = BRAIN_DEFAULTS[agent_id]
        default_runtime = defaults["runtime"] if defaults["runtime"] == "deterministic" else os.getenv("DARWIN_RESEARCH_PROVIDER", defaults["runtime"])
        self.runtime = os.getenv(f"DARWIN_BRAIN_{agent_id.upper()}", default_runtime).strip().lower()
        self.provider_trace = None
        self.enabled = os.getenv("DARWIN_LLM_ENABLED", "true").lower() in {"1", "true", "yes"}
        self.model = os.getenv(f"DARWIN_MODEL_{agent_id.upper()}", defaults["model"]).strip()
        if self.runtime == "openrouter-free":
            self.model = os.getenv("OPENROUTER_FREE_MODEL", "unselected :free model")
        self.reasoning_effort = os.getenv(f"DARWIN_REASONING_{agent_id.upper()}", defaults["reasoning"]).strip().lower()
        self.timeout = float(os.getenv("DARWIN_LLM_TIMEOUT_SECONDS", "60"))
        self.max_context_chars = int(os.getenv("DARWIN_LLM_MAX_CONTEXT_CHARS", "60000"))
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.gateway_api_key = (os.getenv("AI_GATEWAY_API_KEY") or os.getenv("VERCEL_OIDC_TOKEN") or "").strip()
        self.gateway_base_url = os.getenv("DARWIN_LLM_BASE_URL", "https://ai-gateway.vercel.sh/v1").rstrip("/")
        self.max_output_tokens = max(128, min(8192, int(os.getenv("DARWIN_LLM_MAX_OUTPUT_TOKENS", "4096"))))
        self.reserve_budget = None
        self.last_result: LLMResult | None = None

    @property
    def provider(self) -> str:
        if self.runtime in {"openrouter-free", "ollama"}:
            return self.runtime
        if self.runtime == "gateway":
            return "vercel-ai-gateway"
        if self.runtime == "deterministic":
            return "local-code"
        return "openai"

    @property
    def available(self) -> bool:
        if self.runtime == "deterministic":
            return True
        if not self.enabled:
            return False
        if self.runtime == "openrouter-free":
            return bool(os.getenv("OPENROUTER_API_KEY", "").strip())
        if self.runtime == "ollama":
            return False  # prepared selector; no local inference installed in V3
        if self.runtime == "gateway":
            return bool(self.gateway_api_key)
        return bool(self.openai_api_key)

    @property
    def authority(self) -> str:
        return "ADVISORY" if self.runtime != "deterministic" else "DETERMINISTIC"

    def state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled if self.runtime != "deterministic" else True,
            "available": self.available,
            "unavailable_reason": None if self.available else "DISABLED" if not self.enabled else "MISSING_API_KEY",
            "runtime": self.runtime,
            "provider": self.provider,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "prompt_version": self.prompt_version,
            "authority": self.authority,
            "last": self.last_result.to_dict() if self.last_result else None,
            "provider_trace": self.provider_trace,
        }

    def _result(
        self,
        *,
        ok: bool,
        data: dict[str, Any],
        started: float,
        error: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> LLMResult:
        result = LLMResult(
            ok=ok,
            agent_id=self.agent_id,
            model=self.model,
            data=data,
            latency_ms=max(0, int((time.time() - started) * 1000)),
            error=error,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            runtime=self.runtime,
            provider=self.provider,
            reasoning_effort=self.reasoning_effort,
            prompt_version=self.prompt_version,
            estimated_cost_usd=estimate_cost_usd(self.model, prompt_tokens, completion_tokens),
        )
        self.last_result = result
        return result

    def _context_text(self, context: dict[str, Any]) -> str:
        text = json.dumps(context, separators=(",", ":"), default=str)
        if len(text) <= self.max_context_chars:
            return text
        # Explicit truncation marker avoids silently pretending all context was seen.
        return text[: self.max_context_chars] + "...<CONTEXT_TRUNCATED>"

    @staticmethod
    def _extract_responses_text(body: dict[str, Any]) -> str:
        direct = body.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        for item in body.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    return content["text"]
        raise ValueError("Responses API returned no output_text")

    def _openai_json(self, *, task: str, context: dict[str, Any], schema_name: str, schema: dict[str, Any]) -> tuple[dict[str, Any], int | None, int | None]:
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": self.system_prompt,
            "input": task + "\n\nCONTEXT_JSON:\n" + self._context_text(context),
            "store": False,
            "max_output_tokens": self.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if self.reasoning_effort not in {"", "none"}:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.openai_base_url}/responses",
                headers={"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        data = json.loads(self._extract_responses_text(body))
        usage = body.get("usage") or {}
        return data, usage.get("input_tokens"), usage.get("output_tokens")

    def _gateway_json(self, *, task: str, context: dict[str, Any], schema_name: str, schema: dict[str, Any]) -> tuple[dict[str, Any], int | None, int | None]:
        model = self.model if "/" in self.model else f"openai/{self.model}"
        payload = {
            "model": model,
            "max_completion_tokens": self.max_output_tokens,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": task + "\n\nCONTEXT_JSON:\n" + self._context_text(context)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.gateway_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.gateway_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        data = json.loads(body["choices"][0]["message"]["content"])
        usage = body.get("usage") or {}
        return data, usage.get("prompt_tokens"), usage.get("completion_tokens")

    def ask_json(
        self,
        *,
        task: str,
        context: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
        fallback: dict[str, Any],
    ) -> LLMResult:
        started = time.time()
        if self.runtime == "deterministic":
            return self._result(ok=True, data=fallback, started=started)
        if self.runtime == "openrouter-free" and self.enabled:
            from .openrouter_free import FreeProvider
            self.provider_trace = FreeProvider().ask(system=self.system_prompt,task=task,context=context,schema=schema)
            self.model = self.provider_trace.get("model") or "unselected :free model"
            ok = self.provider_trace["status"] in {"connected", "cached"}
            return self._result(ok=ok,data=self.provider_trace.get("data",fallback),started=started,
                error="" if ok else self.provider_trace["status"]+": "+self.provider_trace.get("reason",""),
                prompt_tokens=(self.provider_trace.get("usage") or {}).get("prompt_tokens"),
                completion_tokens=(self.provider_trace.get("usage") or {}).get("completion_tokens"))
        if not self.available:
            key_name = "OPENAI_API_KEY" if self.runtime == "openai" else "AI_GATEWAY_API_KEY / VERCEL_OIDC_TOKEN"
            return self._result(
                ok=False,
                data=fallback,
                started=started,
                error=f"{self.runtime} brain unavailable: configure {key_name} or switch this agent to deterministic",
            )
        try:
            if self.reserve_budget is not None:
                price = MODEL_PRICES_PER_MTOK.get(_canonical_model(self.model))
                if price is None:
                    raise ValueError("Model pricing is unknown; budget reservation unavailable")
                # Conservative byte bound, including schema/instructions and token framing.
                input_bound = len((self.system_prompt + task + self._context_text(context) + json.dumps(schema)).encode("utf-8")) + 2048
                reservation = (input_bound * price[0] + self.max_output_tokens * price[1]) / 1_000_000
                if not self.reserve_budget(reservation):
                    return self._result(ok=False, data=fallback, started=started, error="Persistent research budget exhausted; deterministic fallback")
            if self.runtime == "gateway":
                data, prompt_tokens, completion_tokens = self._gateway_json(task=task, context=context, schema_name=schema_name, schema=schema)
            elif self.runtime == "openai":
                data, prompt_tokens, completion_tokens = self._openai_json(task=task, context=context, schema_name=schema_name, schema=schema)
            else:
                raise ValueError(f"unsupported brain runtime {self.runtime!r}")
            validate(instance=data, schema=schema)
            return self._result(
                ok=True,
                data=data,
                started=started,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception as exc:
            return self._result(
                ok=False,
                data=fallback,
                started=started,
                error=f"{type(exc).__name__}: provider request or validation failed; deterministic fallback",
            )
