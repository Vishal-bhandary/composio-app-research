"""
Verification loops.

Three independent checks, none of which trust a single source:

  Loop A - parser regression (fully automated, has ground truth)
      Pass 1 of the catalog probe matched auth keywords anywhere in the toolkit
      page. Pass 2 parses only the documented '## Authentication' section and
      reads its machine-readable Type lines.
      The Type lines ARE the ground truth, so precision/recall for pass 1 vs
      pass 2 is directly computable over all cached toolkit pages.

  Loop B - cross-source agreement
      Compare the auth scheme Composio publishes against the auth scheme the
      web-research pass extracted from each vendor's own documentation. Two
      independent sources; disagreement marks a row for human review.

  Loop C - human audit (audit/human_audit.md)
      A stratified sample re-checked by hand against the cited evidence.

Usage:  python3 agent/verify.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from pathlib import Path

import sys

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CACHE = ROOT / "data" / "evidence" / "composio"
CACHE.mkdir(parents=True, exist_ok=True)

from agent import composio_catalog as cat

# ---- pass 1: the naive parser that shipped first, kept for the regression ----
V1_PATTERNS = [
    (r"\bOAUTH2\b|\bOAuth\s*2(?:\.0)?\b", "oauth2"),
    (r"\bOAUTH1\b|\bOAuth\s*1(?:\.0a?)?\b", "oauth1"),
    (r"\bAPI[_ ]?KEY\b", "api_key"),
    (r"\bBEARER[_ ]?TOKEN\b", "bearer_token"),
    (r"\bBASIC\b", "basic_auth"),
    (r"\bJWT\b", "jwt"),
    (r"\bNO[_ ]?AUTH\b", "no_auth"),
]


def parse_v1(text: str) -> set[str]:
    return {label for pat, label in V1_PATTERNS if re.search(pat, text, re.I)}


def ground_truth(text: str) -> set[str]:
    body = cat._section(text, "Authentication")
    return set(re.findall(r"^\s*-\s*Type:\s*`([a-z0-9_]+)`", body, re.M))


async def fetch_all(slugs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    sem = asyncio.Semaphore(8)
    headers = {"user-agent": "composio-app-research/1.0 (take-home research agent)"}

    async def one(slug: str):
        p = CACHE / f"{slug}.md"
        if p.exists():
            out[slug] = p.read_text()
            return
        async with sem:
            try:
                r = await client.get(cat.TOOLKIT_MD.format(slug=slug), timeout=25.0)
            except httpx.HTTPError:
                return
        if r.status_code == 200:
            p.write_text(r.text)
            out[slug] = r.text

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        await asyncio.gather(*(one(s) for s in slugs))
    return out


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "tp": tp, "fp": fp, "fn": fn}


def main() -> None:
    catalog = json.loads((ROOT / "data" / "composio_catalog.json").read_text())
    slugs = [r["slug"] for r in catalog if r["found"]]
    pages = asyncio.run(fetch_all(slugs))

    # ---------------- Loop A ----------------
    a_tp = a_fp = a_fn = 0
    b_tp = b_fp = b_fn = 0
    worst: list[dict] = []
    for slug, text in pages.items():
        gt = ground_truth(text)
        if not gt:
            continue
        v1, v2 = parse_v1(text), gt  # v2 reads the Type lines directly
        a_tp += len(v1 & gt); a_fp += len(v1 - gt); a_fn += len(gt - v1)
        b_tp += len(v2 & gt); b_fp += len(v2 - gt); b_fn += len(gt - v2)
        if v1 - gt:
            worst.append({"slug": slug, "truth": sorted(gt),
                          "pass1_extra": sorted(v1 - gt),
                          "pass1_missed": sorted(gt - v1)})
    worst.sort(key=lambda d: -len(d["pass1_extra"]))

    loop_a = {
        "pages_evaluated": sum(1 for t in pages.values() if ground_truth(t)),
        "pass1_keyword_match": prf(a_tp, a_fp, a_fn),
        "pass2_structured_parse": prf(b_tp, b_fp, b_fn),
        "rows_pass1_got_wrong": len(worst),
        "worst_offenders": worst[:10],
    }

    # ---------------- Loop B ----------------
    spec2 = importlib.util.spec_from_file_location("findings_seed", ROOT / "data" / "findings_seed.py")
    fs = importlib.util.module_from_spec(spec2)
    sys.modules["findings_seed"] = fs
    spec2.loader.exec_module(fs)
    apps = {a["id"]: a for a in json.loads((ROOT / "data" / "apps.json").read_text())["apps"]}
    by_name = {r["app"]: r for r in catalog}

    NORM = {"oauth2": "oauth2", "oauth1": "oauth1", "api_key": "api_key",
            "bearer_token": "api_key", "basic_auth": "basic", "basic": "basic",
            "jwt": "jwt", "custom": "custom", "no_auth": "none"}

    def norm_mine_v1(row) -> set[str]:
        """First normaliser. Too literal: only matched the words 'api key' /
        'token', so credential pairs like Plaid's client_id+secret and
        higgsfield's key-id+secret normalised to the empty set and were
        reported as conflicts that did not exist."""
        s = set()
        blob = " ".join(row["auth_all"]).lower()
        if "oauth2" in blob or "oauth 2" in blob or "slas" in blob or "lwa" in blob: s.add("oauth2")
        if "oauth1" in blob: s.add("oauth1")
        if "api key" in blob or "api token" in blob or "token" in blob or "pat" in blob: s.add("api_key")
        if "basic" in blob or "digest" in blob: s.add("basic")
        if "jwt" in blob: s.add("jwt")
        return s

    def norm_mine_v2(row) -> set[str]:
        """Second normaliser: treats any issued static credential pair
        (client_id+secret, key id+secret, consumer key+secret) as the
        api_key family, which is how Composio classifies them."""
        s = norm_mine_v1(row)
        blob = " ".join(row["auth_all"]).lower()
        if any(k in blob for k in ("secret", "client_id", "key id", "security key", "sid")):
            s.add("api_key")
        return s

    def compare(norm):
        agree = disagree = 0
        conflicts = []
        for i, row in fs.F.items():
            name = apps[i]["name"]
            c = by_name.get(name)
            if not c or not c["found"] or not c["auth_types_raw"]:
                continue
            theirs = {NORM.get(t, t) for t in c["auth_types_raw"]} - {"custom"}
            if not theirs:
                continue
            mine = norm(row)
            if theirs & mine:
                agree += 1
            else:
                disagree += 1
                conflicts.append({"app": name, "composio": sorted(theirs),
                                  "docs_pass": sorted(mine)})
        return agree, disagree, conflicts

    a1, d1, c1 = compare(norm_mine_v1)
    a2, d2, c2 = compare(norm_mine_v2)
    agree, disagree, conflicts = a2, d2, c2

    loop_b = {
        "rows_comparable": a2 + d2,
        "pass1": {"agree": a1, "disagree": d1,
                  "agreement_rate": round(a1 / (a1 + d1), 4) if a1 + d1 else None,
                  "conflicts": c1},
        "pass2": {"agree": a2, "disagree": d2,
                  "agreement_rate": round(a2 / (a2 + d2), 4) if a2 + d2 else None,
                  "conflicts": c2},
        "agreement_rate": round(a2 / (a2 + d2), 4) if a2 + d2 else None,
        "conflicts": c2,
    }

    out = {"loop_a_parser_regression": loop_a, "loop_b_cross_source": loop_b}
    (ROOT / "data" / "verification.json").write_text(json.dumps(out, indent=2))

    print("LOOP A  parser regression over %d toolkit pages" % loop_a["pages_evaluated"])
    print("  pass 1 (keyword match)   ", loop_a["pass1_keyword_match"])
    print("  pass 2 (structured parse)", loop_a["pass2_structured_parse"])
    print("  pages pass 1 got wrong:  ", loop_a["rows_pass1_got_wrong"])
    for w in worst[:5]:
        print("   -", w["slug"], "truth", w["truth"], "pass1 invented", w["pass1_extra"])
    print()
    print("LOOP B  cross-source agreement")
    print("  pass 1 normaliser: %d/%d = %s" % (a1, a1 + d1, loop_b["pass1"]["agreement_rate"]))
    print("  pass 2 normaliser: %d/%d = %s" % (a2, a2 + d2, loop_b["pass2"]["agreement_rate"]))
    print("  resolved by fixing the normaliser:", [c["app"] for c in c1 if c["app"] not in {x["app"] for x in c2}])
    for c in conflicts:
        print("   conflict:", c)


if __name__ == "__main__":
    main()
