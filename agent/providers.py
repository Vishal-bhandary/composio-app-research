"""
Model backends for stage 3.

Two providers, same contract: given an app, return a validated AppFinding.

Anthropic  one call. Server-side web search and structured output compose, so
           the model researches and emits schema-valid JSON in a single turn.

Gemini     two calls, deliberately. Gemini's Google Search grounding and
           `response_schema` do not reliably combine - the API has historically
           rejected the pair outright ("controlled generation is not supported
           with google_search tool"), and on the models where it is allowed,
           developers report empty grounding metadata and schema drift. So:
             call 1  grounded research, free text, tools=[google_search]
             call 2  structuring, response_schema=AppFinding, no tools
           Call 1's grounding metadata carries the real source URLs, which is
           exactly what the `evidence` field needs, so the split costs one extra
           request and buys better citations than asking the model to recall
           URLs from its own prose.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from agent.models import AppFinding

SYSTEM = """You research SaaS APIs so an engineer can decide whether to build an \
agent toolkit for them. You are not writing marketing copy and you are not \
summarising a landing page.

Rules you must follow:

1. Prefer the vendor's own developer documentation. A third-party integration \
directory is weak evidence; say so in `confidence` when it is all you have.
2. The access classification is the point of the exercise. Distinguish "I can \
sign up and get a working key" (SS) from "I can sign up but production needs \
approval" (REV) from "I must talk to sales" (SALES). A free sandbox behind a \
reviewed production gate is REV, not SS.
3. If two sources disagree, record both in `conflicts`. Do not silently pick one.
4. If you cannot establish a field, return "unknown" and set confidence "low". \
Refusing to fill a cell is a correct answer. Inventing a plausible endpoint, \
header name or price is the worst possible outcome.
5. Every URL in `evidence` must be one you actually saw in search results."""

PROMPT = """Research the API of this app for an agent-toolkit buildability assessment.

App: {name}
Category: {category}
Documentation hint from the brief: {hint}

Establish, with evidence:
- what it does, in one sentence
- every documented auth method, and which one a new integration would use
- whether a developer can obtain working credentials themselves, and exactly \
what gate stands in the way if not (paid plan / approval review / sales contact)
- the API surface (REST, GraphQL, both, none) and whether an official MCP server exists
- whether a toolkit could be built today, and the single biggest blocker if not"""


class Provider(Protocol):
    name: str
    async def research(self, app: dict) -> AppFinding: ...


# --------------------------------------------------------------- Anthropic
class AnthropicProvider:
    name = "anthropic"
    DEFAULT_MODEL = "claude-opus-5-5"

    def __init__(self, model: str | None = None):
        from anthropic import AsyncAnthropic
        self.model = model or self.DEFAULT_MODEL
        self.client = AsyncAnthropic()

    async def research(self, app: dict) -> AppFinding:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": AppFinding.model_json_schema()},
            },
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}],
            messages=[{"role": "user", "content": PROMPT.format(**app)}],
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"refusal: {resp.stop_details}")
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return AppFinding.model_validate_json(text)


# ------------------------------------------------------------------ Gemini
class GeminiProvider:
    name = "gemini"

    # Tried in order against whatever the key can actually see. Google's model
    # IDs churn fast, so nothing here is hardcoded as a hard requirement -
    # resolve_model() asks the API and falls back down this list.
    PREFERRED = [
        "gemini-4-neon", "gemini-4-carbon", "gemini-4-argon",
        "gemini-3.8-flash", "gemini-3.6-flash",
        "gemini-3.1-pro-preview", "gemini-3.5-flash-lite",
    ]

    def __init__(self, model: str | None = None):
        from google import genai
        self.genai = genai
        # Pass the key explicitly. genai.Client() with no argument reads both
        # GEMINI_API_KEY and GOOGLE_API_KEY from the ambient environment, and a
        # stale GOOGLE_API_KEY left over from unrelated Google Cloud work then
        # silently wins over the key in .env - which surfaces as a confusing
        # "API key not valid" against a key that is perfectly good.
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=key)
        self.model = model or self.resolve_model()

    def available_models(self) -> list[str]:
        out = []
        for m in self.client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            out.append((m.name or "").removeprefix("models/"))
        return [m for m in out if m]

    def resolve_model(self) -> str:
        try:
            available = set(self.available_models())
        except Exception as exc:  # noqa: BLE001 - network/key problems surface below
            raise RuntimeError(
                f"could not list Gemini models ({exc!r}). Check GEMINI_API_KEY."
            ) from exc
        for candidate in self.PREFERRED:
            if candidate in available:
                return candidate
        flash = sorted(m for m in available if "flash" in m and "preview" not in m)
        if flash:
            return flash[-1]
        if available:
            return sorted(available)[-1]
        raise RuntimeError("this Gemini key can see no generateContent models")

    async def research(self, app: dict) -> AppFinding:
        from google.genai import types

        # ---- call 1: grounded research, free text -------------------------
        grounded = await self.client.aio.models.generate_content(
            model=self.model,
            contents=PROMPT.format(**app),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        notes = (grounded.text or "").strip()

        # Real source URLs, straight from the grounding metadata rather than
        # from anything the model wrote down.
        urls: list[str] = []
        for cand in grounded.candidates or []:
            meta = getattr(cand, "grounding_metadata", None)
            for chunk in (getattr(meta, "grounding_chunks", None) or []):
                uri = getattr(getattr(chunk, "web", None), "uri", None)
                if uri and uri not in urls:
                    urls.append(uri)

        if not notes:
            raise RuntimeError("grounded call returned no text")

        # ---- call 2: structuring, schema enforced, no tools ---------------
        structuring = (
            "Convert the research notes below into one JSON object matching the "
            "schema. Do not add facts that are not in the notes. For `evidence`, "
            "prefer these URLs, which are the sources the research actually used:\n"
            + ("\n".join(f"- {u}" for u in urls[:10]) or "- (none captured)")
            + f"\n\n--- RESEARCH NOTES for {app['name']} ---\n{notes}"
        )
        shaped = await self.client.aio.models.generate_content(
            model=self.model,
            contents=structuring,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                response_schema=AppFinding,
            ),
        )
        parsed = getattr(shaped, "parsed", None)
        if isinstance(parsed, AppFinding):
            finding = parsed
        else:
            finding = AppFinding.model_validate_json((shaped.text or "").strip())
        if not finding.evidence and urls:
            finding.evidence = urls[:3]
        return finding


def build(provider: str | None, model: str | None):
    """Pick a provider. Explicit flag wins; otherwise whichever key is set."""
    if provider is None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            provider = "gemini"
        else:
            raise SystemExit(
                "No model key found. Set one of:\n"
                "  ANTHROPIC_API_KEY  (https://platform.claude.com -> API keys)\n"
                "  GEMINI_API_KEY     (https://aistudio.google.com/apikey)\n"
                "Stage 3 is the only stage that needs a key; `python3 agent/run.py` "
                "reproduces everything else without one."
            )
    if provider == "anthropic":
        return AnthropicProvider(model)
    if provider == "gemini":
        return GeminiProvider(model)
    raise SystemExit(f"unknown provider {provider!r}; use 'anthropic' or 'gemini'")
