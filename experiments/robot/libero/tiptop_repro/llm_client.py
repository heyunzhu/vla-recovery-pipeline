from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMClientConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-5.5"
    reasoning_effort: str = "xhigh"
    timeout_sec: float = 60.0
    disable_response_storage: bool = True

    @classmethod
    def from_env(cls) -> "LLMClientConfig":
        return cls(
            base_url=os.environ.get("OPENAI_BASE_URL", os.environ.get("TIPTOP_LLM_BASE_URL", "")).rstrip("/"),
            api_key=os.environ.get("OPENAI_API_KEY", os.environ.get("TIPTOP_LLM_API_KEY", "")),
            model=os.environ.get("TIPTOP_LLM_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5.5")),
            reasoning_effort=os.environ.get("TIPTOP_LLM_REASONING_EFFORT", "xhigh"),
            timeout_sec=float(os.environ.get("TIPTOP_LLM_TIMEOUT_SEC", "60")),
            disable_response_storage=os.environ.get("TIPTOP_LLM_STORE", "false").lower() not in {"1", "true", "yes"},
        )


class OpenAIResponsesClient:
    """Tiny OpenAI-compatible Responses API client.

    This intentionally depends only on the Python standard library so the recovery
    stack can run in existing robot environments without another package install.
    """

    def __init__(self, cfg: Optional[LLMClientConfig] = None) -> None:
        self.cfg = cfg or LLMClientConfig.from_env()
        if not self.cfg.base_url:
            raise ValueError("OPENAI_BASE_URL or TIPTOP_LLM_BASE_URL is required for the LLM backend")
        if not self.cfg.api_key:
            raise ValueError("OPENAI_API_KEY or TIPTOP_LLM_API_KEY is required for the LLM backend")

    def complete_json(self, prompt: str, system: str = "") -> str:
        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system or "Return valid JSON only."}]},
                {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
            ],
            "store": not self.cfg.disable_response_storage,
        }
        if self.cfg.reasoning_effort:
            payload["reasoning"] = {"effort": self.cfg.reasoning_effort}

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.cfg.base_url}/v1/responses",
            data=data,
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.cfg.timeout_sec) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {err[:500]}") from exc
        parsed = json.loads(body)
        text = self._extract_output_text(parsed)
        if not text:
            raise RuntimeError(f"LLM response did not include output text: {body[:500]}")
        return text

    @staticmethod
    def _extract_output_text(response: Dict[str, Any]) -> str:
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        chunks = []
        for item in response.get("output", []) or []:
            for content in item.get("content", []) or []:
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks).strip()
