"""Multi-turn LLM client over Azure AI Foundry (v1 API).

Pattern from the azure-openai / azure-foundry user skills: SDK `openai`, v1 API
(`OpenAI` with base_url, no api_version), `model` = the DEPLOYMENT name,
`max_completion_tokens` (not max_tokens), temperature omitted (GPT-5+ only
supports 1.0). The point of THIS class is the multi-turn plumbing (accumulating
messages + usage) — the integration-first surface the harness is built around.

Credentials come from env (.env, gitignored): AZURE_FOUNDRY_BASE_URL,
AZURE_INFERENCE_CREDENTIAL, AZURE_MODEL.
"""

import os
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI


@dataclass
class Turn:
    role: str
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    latency_s: float = 0.0


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    calls: int = 0

    def add(self, t: Turn) -> None:
        self.prompt_tokens += t.prompt_tokens
        self.completion_tokens += t.completion_tokens
        self.reasoning_tokens += t.reasoning_tokens
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class FoundryChat:
    """A single multi-turn conversation. `ask()` appends a user message, calls
    the model, appends the assistant reply, and returns the assistant Turn."""

    def __init__(
        self,
        system: str | None = None,
        model: str | None = None,
        max_completion_tokens: int = 8000,
        max_retries: int = 3,
        timeout_s: float = 180.0,
    ) -> None:
        load_dotenv()
        base = os.environ["AZURE_FOUNDRY_BASE_URL"].rstrip("/") + "/"
        self.model = model or os.environ.get("AZURE_MODEL", "gpt-5.4")
        self.max_completion_tokens = max_completion_tokens
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._client = OpenAI(
            base_url=base,
            api_key=os.environ["AZURE_INFERENCE_CREDENTIAL"],
            timeout=timeout_s,
        )
        self.messages: list[dict] = []
        if system:
            self.messages.append({"role": "system", "content": system})
        self.usage = Usage()
        self.turns: list[Turn] = []

    def ask(self, content: str) -> Turn:
        self.messages.append({"role": "user", "content": content})
        text, pt, ct, rt, dt = self._call()
        self.messages.append({"role": "assistant", "content": text})
        turn = Turn("assistant", text, pt, ct, rt, dt)
        self.usage.add(turn)
        self.turns.append(turn)
        return turn

    def _call(self):
        last_error = None
        for attempt in range(self.max_retries):
            try:
                t0 = time.perf_counter()
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    max_completion_tokens=self.max_completion_tokens,
                )
                dt = time.perf_counter() - t0
                choice = resp.choices[0]
                text = choice.message.content or ""
                u = resp.usage
                rt = 0
                if u and getattr(u, "completion_tokens_details", None):
                    rt = getattr(u.completion_tokens_details, "reasoning_tokens", 0) or 0
                return (
                    text,
                    (u.prompt_tokens if u else 0),
                    (u.completion_tokens if u else 0),
                    rt,
                    dt,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM call failed after {self.max_retries} retries: {last_error}")
