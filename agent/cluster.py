"""
Pattern analysis.

Deliberately deterministic: no model is asked 'what are the patterns?'. Every
number on the case-study page is a count over data/findings.json, so a
reviewer can recompute all of them from the committed JSON.

Usage:  python3 agent/cluster.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ACCESS_LABEL = {
    "SS": "Self-serve (free)",
    "SSP": "Self-serve (paid plan)",
    "REV": "Review / approval gate",
    "SALES": "Sales / partnership gate",
    "NONE": "No public API",
}
BUILD_LABEL = {
    "yes": "Buildable today",
    "yes_with_caveats": "Buildable with caveats",
    "blocked": "Blocked",
}


def load() -> list[dict]:
    apps = {a["id"]: a for a in json.loads((ROOT / "data" / "apps.json").read_text())["apps"]}
    cat = {c["app"]: c for c in json.loads((ROOT / "data" / "composio_catalog.json").read_text())}
    spec = importlib.util.spec_from_file_location("findings_seed", ROOT / "data" / "findings_seed.py")
    fs = importlib.util.module_from_spec(spec)
    sys.modules["findings_seed"] = fs
    spec.loader.exec_module(fs)

    rows = []
    for i in range(1, 101):
        a, f = apps[i], fs.F[i]
        c = cat.get(a["name"], {})
        rows.append({
            "id": i, "name": a["name"], "category": a["category"],
            "category_no": a["category_no"], "hint": a["hint"],
            "one_liner": f["one_liner"],
            "auth_primary": f["auth_primary"], "auth_all": f["auth_all"],
            "access": f["access"], "access_label": ACCESS_LABEL[f["access"]],
            "access_note": f["access_note"],
            "surface": f["surface"], "mcp": f["mcp"],
            "buildable": f["buildable"], "buildable_label": BUILD_LABEL[f["buildable"]],
            "blocker": f["blocker"], "evidence": f["evidence"],
            "verification": f["verification"], "confidence": f["confidence"],
            "composio_toolkit": bool(c.get("found")),
            "composio_slug": c.get("slug"),
            "composio_managed": bool(c.get("is_composio_managed")),
            "composio_tools": c.get("tool_count"),
            "composio_triggers": c.get("trigger_count") or 0,
            "composio_auth": c.get("auth_schemes") or [],
        })
    return rows


def analyse(rows: list[dict]) -> dict:
    n = len(rows)
    by_access = Counter(r["access"] for r in rows)
    by_build = Counter(r["buildable"] for r in rows)
    by_auth = Counter(r["auth_primary"] for r in rows)
    by_verif = Counter(r["verification"] for r in rows)

    # auth family rollup
    fam = Counter()
    for r in rows:
        p = r["auth_primary"].lower()
        if "oauth2" in p or "slas" in p or "lwa" in p:
            fam["OAuth2"] += 1
        elif "oauth1" in p:
            fam["OAuth1 / token pair"] += 1
        elif "api key" in p or "bearer" in p or "pat" in p or "key-pair" in p:
            fam["API key / token"] += 1
        elif "basic" in p or "digest" in p:
            fam["Basic / digest"] += 1
        elif p == "n/a":
            fam["No auth surface"] += 1
        else:
            fam["Other / unknown"] += 1

    cat_rows = defaultdict(list)
    for r in rows:
        cat_rows[r["category"]].append(r)

    per_category = []
    for cname, rs in sorted(cat_rows.items(), key=lambda kv: kv[1][0]["category_no"]):
        acc = Counter(r["access"] for r in rs)
        open_n = acc["SS"] + acc["SSP"]
        per_category.append({
            "category": cname,
            "n": len(rs),
            "self_serve_free": acc["SS"],
            "self_serve_paid": acc["SSP"],
            "review_gate": acc["REV"],
            "sales_gate": acc["SALES"],
            "no_api": acc["NONE"],
            "open_pct": round(100 * open_n / len(rs)),
            "blocked": sum(1 for r in rs if r["buildable"] == "blocked"),
            "composio_coverage": sum(1 for r in rs if r["composio_toolkit"]),
            "oauth2": sum(1 for r in rs if "oauth2" in r["auth_primary"].lower()),
        })

    blockers = [{"name": r["name"], "category": r["category"], "blocker": r["blocker"],
                 "access": r["access"], "evidence": r["evidence"][0] if r["evidence"] else None}
                for r in rows if r["buildable"] == "blocked"]
    caveats = [{"name": r["name"], "blocker": r["blocker"], "access": r["access"]}
               for r in rows if r["buildable"] == "yes_with_caveats"]

    gated = [r for r in rows if r["access"] in ("REV", "SALES")]
    gated_cov = sum(1 for r in gated if r["composio_toolkit"])
    open_apps = [r for r in rows if r["access"] in ("SS", "SSP")]
    open_cov = sum(1 for r in open_apps if r["composio_toolkit"])

    # easy wins: open access, buildable today, no Composio toolkit yet
    easy_wins = sorted(
        [r for r in rows if r["access"] in ("SS", "SSP")
         and r["buildable"] == "yes" and not r["composio_toolkit"]],
        key=lambda r: r["id"])

    # needs outreach: sales-gated or blocked
    outreach = sorted([r for r in rows if r["access"] == "SALES"], key=lambda r: r["id"])

    tool_counts = [r["composio_tools"] for r in rows if r["composio_tools"]]
    return {
        "n": n,
        "by_access": {ACCESS_LABEL[k]: v for k, v in by_access.most_common()},
        "by_access_code": dict(by_access),
        "by_buildable": {BUILD_LABEL[k]: v for k, v in by_build.most_common()},
        "by_auth_primary": dict(by_auth.most_common()),
        "auth_family": dict(fam.most_common()),
        "by_verification": dict(by_verif),
        "per_category": per_category,
        "blockers": blockers,
        "caveats": caveats,
        "composio": {
            "toolkits_found": sum(1 for r in rows if r["composio_toolkit"]),
            "composio_managed": sum(1 for r in rows if r["composio_managed"]),
            "total_tools": sum(tool_counts),
            "median_tools": sorted(tool_counts)[len(tool_counts) // 2] if tool_counts else 0,
            "max_tools": max(tool_counts) if tool_counts else 0,
            "coverage_open_pct": round(100 * open_cov / len(open_apps)),
            "coverage_gated_pct": round(100 * gated_cov / len(gated)) if gated else 0,
            "open_n": len(open_apps), "gated_n": len(gated),
        },
        "easy_wins": [{"name": r["name"], "category": r["category"],
                       "auth": r["auth_primary"], "surface": r["surface"]} for r in easy_wins],
        "outreach": [{"name": r["name"], "category": r["category"],
                      "blocker": r["blocker"]} for r in outreach],
        "mcp_official": sum(1 for r in rows if r["mcp"].startswith("official")),
    }


def main() -> None:
    rows = load()
    (ROOT / "data" / "findings.json").write_text(json.dumps(rows, indent=2))
    pat = analyse(rows)
    (ROOT / "data" / "patterns.json").write_text(json.dumps(pat, indent=2))
    print(json.dumps({k: v for k, v in pat.items()
                      if k not in ("per_category", "blockers", "caveats", "easy_wins", "outreach")},
                     indent=2))
    print("\nper-category open%:",
          {c["category"][:22]: c["open_pct"] for c in pat["per_category"]})
    print("easy wins:", len(pat["easy_wins"]), "| outreach:", len(pat["outreach"]))


if __name__ == "__main__":
    main()
