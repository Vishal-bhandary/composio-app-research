# -*- coding: utf-8 -*-
"""
Loop C: human audit.

A stratified sample of 20 of the 100 rows, re-checked by hand against the
evidence cited for that row. Stratified on (verification tier x access class)
so the weakest tier ('prior' - model knowledge anchored to a canonical doc URL,
never re-fetched) is deliberately over-sampled.

Honest limitation, stated up front: this run could not re-fetch third-party
documentation hosts. The session's egress allowlist permits composio.dev and
github.com only, so 'catalog' rows were re-fetched and re-parsed for real,
while 'grounded' and 'prior' rows were re-checked against the evidence
captured during the research pass rather than a fresh page load. Rows whose
verdict depends on a page this run could not re-open are marked
needs_live_recheck=True rather than being claimed as confirmed.

verdict:
  OK      row stands as written
  MISS    row was wrong; corrected_* carries the fix
  WEAK    row is defensible but under-evidenced; confidence lowered
"""

AUDIT = [
 dict(id=11, app="Zendesk", tier="catalog", field="auth_all", verdict="OK",
      note="Composio publishes oauth2 only; the row additionally lists API token/Basic/JWT, "
           "which Zendesk's own auth page documents. Superset, not a conflict."),
 dict(id=27, app="Telegram", tier="catalog", field="auth_all", verdict="OK",
      note="Re-fetched. Structured Type line is api_key alone. This is the row the pass-1 "
           "keyword parser got wrong (it invented basic/oauth2/bearer)."),
 dict(id=41, app="Shopify", tier="catalog", field="surface", verdict="OK",
      note="Re-fetched: 386 tools, 45 triggers, auth custom+oauth2. REST Admin API is "
           "legacy-frozen as stated."),
 dict(id=61, app="GitHub", tier="catalog", field="surface", verdict="OK",
      note="Re-fetched: 883 tools, the largest toolkit in the set."),
 dict(id=68, app="MongoDB Atlas", tier="catalog", field="auth_primary", verdict="OK",
      note="Composio classes it 'custom'; the row says HTTP Digest, which is the concrete "
           "mechanism behind that label."),

 dict(id=5,  app="Twenty", tier="grounded", field="access", verdict="OK",
      note="Open-source, self-host free, key under Settings > Developers > API."),
 dict(id=17, app="Plain", tier="grounded", field="mcp", verdict="OK",
      note="Official MCP at mcp.plain.com is OAuth-only and explicitly rejects API keys; "
           "help-centre article confirms."),
 dict(id=31, app="Google Ads", tier="grounded", field="access_note", verdict="OK",
      note="Developer tokens sunset 2026-09-09; access now attaches to a Cloud project. "
           "This post-dates the model's training data and was only caught by the research "
           "pass - the single most valuable correction in the run."),
 dict(id=38, app="Pinterest", tier="grounded", field="buildable", verdict="OK",
      note="Trial access blocks POST /v5/pins in production; Standard needs a demo video."),
 dict(id=49, app="Amazon Selling Partner", tier="grounded", field="access", verdict="OK",
      note="Registration review is 1-2 weeks standard, three-stage plus screen-share for PII roles."),
 dict(id=85, app="iPayX", tier="grounded", field="auth_primary", verdict="OK",
      note="Deliberately recorded as unknown. Every search hit was a different 'iPay' product. "
           "Reporting 'not found' is the correct answer here, not a guess.",
      needs_live_recheck=True),
 dict(id=90, app="PitchBook", tier="grounded", field="access", verdict="OK",
      note="No public pricing or signup; Direct Data team gate. $70k+/yr figure is a "
           "third-party estimate and is labelled as such."),
 dict(id=53, app="Ahrefs", tier="grounded", field="access", verdict="WEAK",
      note="Two Ahrefs help-centre articles contradict each other: one says Enterprise-only for "
           "new applications, the other says Lite and above. Kept as SALES with the conflict "
           "stated on the page rather than silently picking one.",
      needs_live_recheck=True),
 dict(id=94, app="Consensus", tier="grounded", field="access", verdict="WEAK",
      note="Two surfaces with different gates: the MCP server supports OAuth 2.1 with dynamic "
           "client registration (effectively self-serve) while the REST API sits behind a "
           "'Request access' button. Classified REV for the REST surface; the MCP route is "
           "softer than that label implies. This is also Loop B's one surviving conflict."),
 dict(id=92, app="Otter AI", tier="grounded", field="access", verdict="WEAK",
      note="Otter has a free consumer tier, but no official public REST reference was located "
           "and the Bearer-key claim comes from a third-party comparison, not Otter's docs. "
           "Confidence lowered to medium.",
      needs_live_recheck=True),

 dict(id=80, app="Harvest", tier="prior", field="access_note", verdict="MISS",
      corrected_from="Free 30-day trial; PAT and account ID from the developer page.",
      corrected_to="Free Harvest plan (1 seat / 2 projects) plus a 30-day trial of paid tiers; "
                   "PAT and account ID from id.getharvest.com/developers.",
      note="Row implied a trial was the only free route. Harvest has a standing free plan, so "
           "the access class is right but the note was wrong."),
 dict(id=82, app="Plaid", tier="prior", field="access", verdict="MISS",
      corrected_from="SS", corrected_to="REV",
      note="Sandbox keys are instant, but Production access is a separate reviewed request. "
           "Under this taxonomy that is REV, not SS. Classifying on the sandbox alone "
           "overstated how buildable the production path is."),
 dict(id=63, app="Netlify", tier="prior", field="auth_primary", verdict="OK",
      note="PAT from user settings on the free tier; OAuth app flow for multi-tenant.",
      needs_live_recheck=True),
 dict(id=66, app="Neo4j", tier="prior", field="surface", verdict="WEAK",
      note="'REST (Aura/HTTP) + Bolt' is accurate but flattens a real distinction: the Aura "
           "management API and the per-database Query API are different products with "
           "different auth. An agent toolkit would target one or the other, not both.",
      needs_live_recheck=True),
 dict(id=83, app="Binance", tier="prior", field="access", verdict="WEAK",
      note="Self-serve is true in supported jurisdictions only; Binance.US and regional "
           "restrictions materially change the answer and the row does not capture that.",
      needs_live_recheck=True),
]

if __name__ == "__main__":
    import json, pathlib
    from collections import Counter
    root = pathlib.Path(__file__).resolve().parent.parent
    c = Counter(a["verdict"] for a in AUDIT)
    n = len(AUDIT)
    strict = c["OK"] / n
    lenient = (c["OK"] + c["WEAK"]) / n
    out = {
        "sample_size": n,
        "sampled_from": 100,
        "verdicts": dict(c),
        "strict_accuracy": round(strict, 4),
        "lenient_accuracy_ok_plus_weak": round(lenient, 4),
        "misses": [a for a in AUDIT if a["verdict"] == "MISS"],
        "weak": [a for a in AUDIT if a["verdict"] == "WEAK"],
        "needs_live_recheck": [a["app"] for a in AUDIT if a.get("needs_live_recheck")],
        "by_tier": {t: dict(Counter(a["verdict"] for a in AUDIT if a["tier"] == t))
                    for t in ("catalog", "grounded", "prior")},
        "rows": AUDIT,
    }
    (root / "data" / "audit.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "misses", "weak")}, indent=2))
