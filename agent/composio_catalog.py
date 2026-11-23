"""
Composio catalog probe.

Signal source #1 of the research pipeline.

For each app in the research set, ask Composio's own public catalog whether a
toolkit already exists, whether Composio manages its auth, and which auth
schemes the catalog advertises. A toolkit that already ships is the strongest
possible evidence that an app is buildable today; its absence is a prompt to
look harder, not a verdict.

Endpoints used (all public, no key required):
  https://composio.dev/toolkits/<slug>.md   -> JSON front-matter + prose
  https://composio.dev/auth/<slug>          -> auth-scheme guide

Network: only composio.dev is required.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import httpx

ROOT = Path(__file__).resolve().parent.parent
TOOLKIT_MD = "https://composio.dev/toolkits/{slug}.md"
AUTH_PAGE = "https://composio.dev/auth/{slug}"

# Slugs that simple normalisation will not produce. Kept explicit and small so
# a reviewer can audit every manual intervention; see docs/architecture.md.
SLUG_OVERRIDES: dict[str, list[str]] = {
    "Zoho CRM": ["zoho", "zoho_crm"],
    "Zoho Cliq": ["zoho_cliq", "zohocliq"],
    "DealCloud": ["dealcloud"],
    "Help Scout": ["helpscout", "help_scout"],
    "Lark (Larksuite)": ["lark", "larksuite"],
    "WhatsApp Business": ["whatsapp", "whatsapp_business"],
    "Telegram": ["telegram", "telegram_bot"],
    "Google Ads": ["google_ads", "googleads"],
    "Meta Ads": ["meta_ads", "facebook_ads", "facebook"],
    "LinkedIn Ads": ["linkedin_ads", "linkedin"],
    "GoHighLevel": ["gohighlevel", "highlevel"],
    "systeme.io": ["systeme_io", "systeme"],
    "Threads (Meta)": ["threads", "meta_threads"],
    "Magento (Adobe Commerce)": ["magento", "adobe_commerce"],
    "Salesforce Commerce Cloud": ["salesforce_commerce_cloud", "sfcc"],
    "Amazon Selling Partner": ["amazon_selling_partner", "amazon", "sp_api"],
    "Monday.com": ["monday"],
    "MongoDB Atlas": ["mongodb", "mongodb_atlas"],
    "Jira": ["jira", "atlassian"],
    "YouTube Transcript": ["youtube_transcript", "transcript_api", "youtube"],
    "Mermaid CLI": ["mermaid", "mermaid_cli"],
    "NotebookLM": ["notebook_lm", "notebooklm"],
    "Otter AI": ["otter_ai_mcp", "otter_ai", "otterai"],
    "Devin": ["devin", "devin_mcp"],
    "Consensus": ["consensus", "consensus_mcp"],
    "higgsfield": ["higgsfield"],
    "Bright Data": ["brightdata", "bright_data"],
    "SE Ranking": ["seranking", "se_ranking"],
    "DataForSEO": ["dataforseo", "data_for_seo"],
    "Waterfall.io": ["waterfall", "waterfall_io"],
    "Paygent Connect": ["paygent", "paygent_connect", "nmi"],
    "iPayX": ["ipayx", "ipay_x"],
    "fanbasis": ["fanbasis"],
    "Binance": ["binance"],
    "QuickBooks": ["quickbooks", "qbo"],
    "Amazon Selling Partner ": ["amazon_selling_partner"],
    "Sherlock": ["sherlock"],
    "Firecrawl": ["firecrawl"],
    "Twenty": ["twenty", "twenty_crm"],
    "Pylon": ["pylon"],
}


def candidate_slugs(name: str) -> list[str]:
    """Deterministic slug candidates, most likely first."""
    out: list[str] = list(SLUG_OVERRIDES.get(name, []))
    base = name.lower().strip()
    base = re.sub(r"\(.*?\)", " ", base)
    base = base.replace("&", " and ").replace(".", " ").replace("-", " ")
    base = re.sub(r"[^a-z0-9]+", " ", base).strip()
    if base:
        out.append(base.replace(" ", "_"))
        out.append(base.replace(" ", ""))
        out.append(base.split()[0])
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


@dataclass
class CatalogHit:
    app: str
    slug: str | None
    found: bool
    is_composio_managed: bool | None
    categories: list[str]
    auth_page: bool
    auth_schemes: list[str]
    auth_types_raw: list[str]
    tool_count: int | None
    trigger_count: int
    one_liner: str
    toolkit_url: str | None
    evidence_url: str | None
    tried: list[str]


AUTH_TYPE_LABEL = {
    "oauth2": "OAuth2",
    "oauth1": "OAuth1",
    "api_key": "API key",
    "bearer_token": "Bearer token",
    "basic": "Basic",
    "basic_with_jwt": "Basic+JWT",
    "jwt": "JWT",
    "no_auth": "No auth",
    "calcom_auth": "Vendor-specific",
    "billcom_auth": "Vendor-specific",
    "snowflake_auth": "Vendor-specific",
    "google_service_account": "Service account",
}


def _section(text: str, heading: str) -> str:
    """Return the body of a '## <heading>' section, or ''."""
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def parse_toolkit_md(text: str) -> dict:
    """Parse Composio's published toolkit markdown into structured fields.

    Only reads the documented section layout (## Authentication, ## Toolkit
    Details, ...). Free-text keyword matching is deliberately avoided: it
    over-matched badly on the first pass (Telegram came back with four auth
    schemes because the prose mentions them), and that miss is recorded in
    docs/architecture.md.
    """
    meta: dict = {}
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError:
            meta = {}

    auth_body = _section(text, "Authentication")
    types = re.findall(r"^\s*-\s*Type:\s*`([a-z0-9_]+)`", auth_body, re.M)
    schemes, seen = [], set()
    for t in types:
        label = AUTH_TYPE_LABEL.get(t, t)
        if label not in seen:
            seen.add(label)
            schemes.append(label)

    details = _section(text, "Toolkit Details")
    tm = re.search(r"-\s*Tools:\s*(\d+)", details)
    tools = int(tm.group(1)) if tm else None

    trig_body = _section(text, "Supported Triggers")
    triggers = len(re.findall(r"^\|\s*`[A-Z0-9_]+`", trig_body, re.M))

    desc = _section(text, "Description").strip().split("\n")[0].strip()

    return {
        "meta": meta,
        "auth_schemes": schemes,
        "auth_types_raw": sorted(set(types)),
        "tool_count": tools,
        "trigger_count": triggers,
        "one_liner": desc,
    }


async def probe_app(client: httpx.AsyncClient, name: str, sem: asyncio.Semaphore) -> CatalogHit:
    tried: list[str] = []
    for slug in candidate_slugs(name)[:6]:
        tried.append(slug)
        async with sem:
            try:
                r = await client.get(TOOLKIT_MD.format(slug=slug), timeout=25.0)
            except httpx.HTTPError:
                continue
        if r.status_code != 200 or "```json" not in r.text:
            continue
        p = parse_toolkit_md(r.text)
        meta = p["meta"]
        if meta.get("slug") and meta["slug"] != slug:
            slug = meta["slug"]
        async with sem:
            try:
                ar = await client.get(AUTH_PAGE.format(slug=slug), timeout=25.0)
                auth_ok = ar.status_code == 200
            except httpx.HTTPError:
                auth_ok = False
        return CatalogHit(
            app=name, slug=slug, found=True,
            is_composio_managed=meta.get("is_composio_managed"),
            categories=meta.get("categories", []),
            auth_page=auth_ok,
            auth_schemes=p["auth_schemes"],
            auth_types_raw=p["auth_types_raw"],
            tool_count=p["tool_count"],
            trigger_count=p["trigger_count"],
            one_liner=p["one_liner"],
            toolkit_url=meta.get("url") or f"https://composio.dev/toolkits/{slug}",
            evidence_url=TOOLKIT_MD.format(slug=slug), tried=tried,
        )
    return CatalogHit(name, None, False, None, [], False, [], [], None, 0, "", None, None, tried)


async def run(apps: Iterable[dict], concurrency: int = 8) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    headers = {"user-agent": "composio-app-research/1.0 (take-home research agent)"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        hits = await asyncio.gather(*(probe_app(client, a["name"], sem) for a in apps))
    return [asdict(h) for h in hits]


if __name__ == "__main__":
    apps = json.loads((ROOT / "data" / "apps.json").read_text())["apps"]
    rows = asyncio.run(run(apps))
    out = ROOT / "data" / "composio_catalog.json"
    out.write_text(json.dumps(rows, indent=2))
    found = sum(1 for r in rows if r["found"])
    managed = sum(1 for r in rows if r["is_composio_managed"])
    print(f"probed {len(rows)} apps -> {found} toolkits found, {managed} composio-managed")
    print(f"wrote {out}")
