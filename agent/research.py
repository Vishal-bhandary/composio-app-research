"""
Stage 3: documentation research.

For each app, Claude runs server-side web search over the vendor's own
documentation and returns one structured AppFinding. Structured outputs make
the response schema-valid by construction, so nothing downstream has to parse
prose.

Requires ANTHROPIC_API_KEY. Everything else in this repo runs without a key;
this stage is the only part that calls a model.

    python3 agent/research.py                  # all 100
    python3 agent/research.py --only 5 17 94   # named ids
    python3 agent/research.py --model claude-sonnet-5-5 --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.models import AppFinding  # noqa: E402

DEFAULT_MODEL = "claude-opus-5-5"
OUT = ROOT / "data" / "research_raw.jsonl"

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


async def research_one(client, sem, app: dict, model: str) -> dict:
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.messages.create(
                    model=model,
                    max_tokens=8000,
                    system=SYSTEM,
                    thinking={"type": "adaptive"},
                    output_config={
                        "effort": "medium",
                        "format": {
                            "type": "json_schema",
                            "schema": AppFinding.model_json_schema(),
                        },
                    },
                    tools=[{
                        "type": "web_search_20260209",
                        "name": "web_search",
                        "max_uses": 6,
                    }],
                    messages=[{"role": "user", "content": PROMPT.format(
                        name=app["name"], category=app["category"], hint=app["hint"])}],
                )
            except Exception as exc:  # noqa: BLE001 - retry any transient API failure
                if attempt == 2:
                    return {"id": app["id"], "name": app["name"], "error": repr(exc)}
                await asyncio.sleep(2 ** attempt * 3)
                continue

            if resp.stop_reason == "refusal":
                return {"id": app["id"], "name": app["name"],
                        "error": f"refusal: {resp.stop_details}"}

            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            try:
                finding = AppFinding.model_validate_json(text)
            except Exception as exc:  # noqa: BLE001
                return {"id": app["id"], "name": app["name"],
                        "error": f"schema: {exc!r}", "raw": text[:2000]}

            return {"id": app["id"], **finding.model_dump(),
                    "usage": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}}
    return {"id": app["id"], "name": app["name"], "error": "unreachable"}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--only", nargs="*", type=int)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. This is the only stage that needs it; "
                 "agent/composio_catalog.py, agent/verify.py and agent/cluster.py do not.")

    from anthropic import AsyncAnthropic

    apps = json.loads((ROOT / "data" / "apps.json").read_text())["apps"]
    if args.only:
        apps = [a for a in apps if a["id"] in set(args.only)]

    client = AsyncAnthropic()
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(research_one(client, sem, a, args.model) for a in apps))

    with OUT.open("w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")

    ok = [r for r in results if "error" not in r]
    print(f"researched {len(ok)}/{len(results)} apps -> {OUT}")
    for r in results:
        if "error" in r:
            print("  FAILED", r["name"], "-", r["error"][:120])
    if ok:
        tin = sum(r["usage"]["in"] for r in ok)
        tout = sum(r["usage"]["out"] for r in ok)
        print(f"tokens: {tin:,} in / {tout:,} out")


if __name__ == "__main__":
    asyncio.run(main())
