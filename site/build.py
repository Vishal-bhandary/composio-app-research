"""
Render the case study.

Emits two files from one template:
  site/index.html     standalone document, for GitHub Pages
  site/artifact.html  same content without the document skeleton, for publishing
                      as a Claude Artifact (the platform supplies the skeleton)

Every number on the page is read from data/*.json at build time. Nothing is
typed in by hand, so the page cannot drift from the dataset.

Usage:  python3 site/build.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"

rows = json.loads((D / "findings.json").read_text())
pat = json.loads((D / "patterns.json").read_text())
ver = json.loads((D / "verification.json").read_text())
aud = json.loads((D / "audit.json").read_text())

ACCESS_ORDER = ["SS", "SSP", "REV", "SALES", "NONE"]
ACCESS_SHORT = {"SS": "Self-serve", "SSP": "Self-serve · paid",
                "REV": "Review gate", "SALES": "Sales gate", "NONE": "No API"}

# compact per-row payload for the in-page table (full records stay in data/findings.json)
compact = [{
    "n": r["name"], "c": r["category_no"], "o": r["one_liner"],
    "a": r["auth_primary"], "x": r["access"], "an": r["access_note"],
    "s": r["surface"], "b": r["buildable"], "bl": r["blocker"],
    "e": r["evidence"], "v": r["verification"], "cf": r["confidence"],
    "ck": r["composio_toolkit"], "cm": r["composio_managed"],
    "ct": r["composio_tools"], "m": r["mcp"],
} for r in rows]

cats = [c["category"] for c in sorted(pat["per_category"], key=lambda c: c["category"])]
cat_names = {}
for r in rows:
    cat_names[r["category_no"]] = r["category"]
CATS = [cat_names[i] for i in sorted(cat_names)]


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------- gate matrix
def gate_matrix() -> str:
    pc = sorted(pat["per_category"], key=lambda c: -c["open_pct"])
    bars = []
    for c in pc:
        segs, x = [], 0.0
        for code, key in (("SS", "self_serve_free"), ("SSP", "self_serve_paid"),
                          ("REV", "review_gate"), ("SALES", "sales_gate"), ("NONE", "no_api")):
            v = c[key]
            if not v:
                continue
            w = v / c["n"] * 100
            segs.append(
                f'<div class="seg s-{code}" style="width:{w:.4f}%" '
                f'title="{esc(c["category"])} — {ACCESS_SHORT[code]}: {v} of {c["n"]}">'
                f'{"<span>" + str(v) + "</span>" if w >= 9 else ""}</div>')
            x += w
        bars.append(
            '<div class="mrow">'
            f'<div class="mlabel">{esc(c["category"])}</div>'
            f'<div class="mbar">{"".join(segs)}</div>'
            f'<div class="mpct">{c["open_pct"]}%</div>'
            '</div>')
    return "\n".join(bars)


# ---------------------------------------------------------------- auth bars
def auth_bars() -> str:
    fam = pat["auth_family"]
    total = sum(fam.values())
    out = []
    for k, v in fam.items():
        out.append(
            '<div class="abar">'
            f'<div class="alabel">{esc(k)}</div>'
            f'<div class="atrack"><div class="afill" style="width:{v / total * 100:.3f}%"></div></div>'
            f'<div class="aval">{v}</div></div>')
    return "\n".join(out)


# ---------------------------------------------------------------- table rows
def table_rows() -> str:
    out = []
    for i, r in enumerate(rows):
        ev = "".join(
            f'<a href="{esc(u)}" target="_blank" rel="noopener">{j + 1}</a>'
            for j, u in enumerate(r["evidence"]))
        ck = ('<span class="chip ok">yes</span>' if r["composio_toolkit"] else
              '<span class="chip no">no</span>')
        tools = f'<span class="mono dim">{r["composio_tools"]}</span>' if r["composio_tools"] else ""
        out.append(
            f'<tr data-cat="{r["category_no"]}" data-access="{r["access"]}" '
            f'data-build="{r["buildable"]}" data-verif="{r["verification"]}" '
            f'data-ck="{int(r["composio_toolkit"])}" '
            f'data-q="{esc((r["name"] + " " + r["one_liner"] + " " + r["auth_primary"]).lower())}">'
            f'<td class="num mono">{r["id"]}</td>'
            f'<td class="nm"><strong>{esc(r["name"])}</strong>'
            f'<span class="sub">{esc(r["one_liner"])}</span></td>'
            f'<td class="mono sm">{esc(r["auth_primary"])}</td>'
            f'<td><span class="pill p-{r["access"]}">{ACCESS_SHORT[r["access"]]}</span></td>'
            f'<td class="sm">{esc(r["surface"])}</td>'
            f'<td><span class="bd b-{r["buildable"]}"></span>'
            f'<span class="sm">{esc(r["blocker"]) if r["blocker"] != "None material." else "—"}</span></td>'
            f'<td class="ctr">{ck} {tools}</td>'
            f'<td class="ctr"><span class="tier t-{r["verification"]}">{r["verification"][:4]}</span></td>'
            f'<td class="ev">{ev}</td>'
            '</tr>')
    return "\n".join(out)


def misses_html() -> str:
    out = []
    for m in aud["misses"]:
        out.append(
            '<div class="miss">'
            f'<div class="mh"><span class="vd MISS">MISS</span>'
            f'<strong>{esc(m["app"])}</strong>'
            f'<span class="tier t-{m["tier"]}">{m["tier"]}</span>'
            f'<span class="fld mono">{esc(m["field"])}</span></div>'
            f'<div class="md"><span class="was">was</span> '
            f'<code>{esc(m.get("corrected_from", ""))}</code></div>'
            f'<div class="md"><span class="now">now</span> '
            f'<code>{esc(m.get("corrected_to", ""))}</code></div>'
            f'<p>{esc(m["note"])}</p></div>')
    for w in aud["weak"]:
        out.append(
            '<div class="miss weak">'
            f'<div class="mh"><span class="vd WEAK">WEAK</span>'
            f'<strong>{esc(w["app"])}</strong>'
            f'<span class="tier t-{w["tier"]}">{w["tier"]}</span>'
            f'<span class="fld mono">{esc(w["field"])}</span></div>'
            f'<p>{esc(w["note"])}</p></div>')
    return "\n".join(out)


def tier_table() -> str:
    out = []
    for tier in ("catalog", "grounded", "prior"):
        v = aud["by_tier"][tier]
        n = sum(v.values())
        ok = v.get("OK", 0)
        out.append(
            f'<tr><td><span class="tier t-{tier}">{tier}</span></td>'
            f'<td class="mono">{n}</td>'
            f'<td class="mono">{ok}</td>'
            f'<td class="mono">{v.get("WEAK", 0)}</td>'
            f'<td class="mono">{v.get("MISS", 0)}</td>'
            f'<td class="mono strong">{round(100 * ok / n)}%</td></tr>')
    return "\n".join(out)


def chips(items, cls="") -> str:
    return "".join(f'<span class="wchip {cls}">{esc(i["name"])}</span>' for i in items)


la = ver["loop_a_parser_regression"]
lb = ver["loop_b_cross_source"]
cx = pat["composio"]

REPL = {
    "{{DATE}}": date.today().isoformat(),
    "{{N}}": str(pat["n"]),
    "{{SS}}": str(pat["by_access_code"]["SS"]),
    "{{SSP}}": str(pat["by_access_code"]["SSP"]),
    "{{OPEN}}": str(pat["by_access_code"]["SS"] + pat["by_access_code"]["SSP"]),
    "{{REV}}": str(pat["by_access_code"]["REV"]),
    "{{SALES}}": str(pat["by_access_code"]["SALES"]),
    "{{NONEAPI}}": str(pat["by_access_code"]["NONE"]),
    "{{GATED}}": str(pat["by_access_code"]["REV"] + pat["by_access_code"]["SALES"]),
    "{{BUILD}}": str(pat["by_buildable"]["Buildable today"]),
    "{{CAVEAT}}": str(pat["by_buildable"]["Buildable with caveats"]),
    "{{BLOCKED}}": str(pat["by_buildable"]["Blocked"]),
    "{{AUTH_KEY}}": str(pat["auth_family"]["API key / token"]),
    "{{AUTH_OAUTH}}": str(pat["auth_family"]["OAuth2"]),
    "{{CX_FOUND}}": str(cx["toolkits_found"]),
    "{{CX_MANAGED}}": str(cx["composio_managed"]),
    "{{CX_TOOLS}}": f'{cx["total_tools"]:,}',
    "{{CX_MED}}": str(cx["median_tools"]),
    "{{CX_MAX}}": str(cx["max_tools"]),
    "{{CX_OPEN}}": str(cx["coverage_open_pct"]),
    "{{CX_GATED}}": str(cx["coverage_gated_pct"]),
    "{{MCP}}": str(pat["mcp_official"]),
    "{{EASY_N}}": str(len(pat["easy_wins"])),
    "{{OUTREACH_N}}": str(len(pat["outreach"])),
    "{{GATE_MATRIX}}": gate_matrix(),
    "{{AUTH_BARS}}": auth_bars(),
    "{{TABLE_ROWS}}": table_rows(),
    "{{MISSES}}": misses_html(),
    "{{TIER_TABLE}}": tier_table(),
    "{{EASY_CHIPS}}": chips(pat["easy_wins"]),
    "{{OUTREACH_CHIPS}}": chips(pat["outreach"], "warn"),
    "{{A1_P}}": f'{la["pass1_keyword_match"]["precision"]:.3f}',
    "{{A1_R}}": f'{la["pass1_keyword_match"]["recall"]:.3f}',
    "{{A1_F}}": f'{la["pass1_keyword_match"]["f1"]:.3f}',
    "{{A2_P}}": f'{la["pass2_structured_parse"]["precision"]:.3f}',
    "{{A2_R}}": f'{la["pass2_structured_parse"]["recall"]:.3f}',
    "{{A2_F}}": f'{la["pass2_structured_parse"]["f1"]:.3f}',
    "{{A_PAGES}}": str(la["pages_evaluated"]),
    "{{A_WRONG}}": str(la["rows_pass1_got_wrong"]),
    "{{A_FP}}": str(la["pass1_keyword_match"]["fp"]),
    "{{B1}}": f'{lb["pass1"]["agreement_rate"] * 100:.1f}',
    "{{B2}}": f'{lb["pass2"]["agreement_rate"] * 100:.1f}',
    "{{B_N}}": str(lb["rows_comparable"]),
    "{{B_CONF}}": str(len(lb["pass2"]["conflicts"])),
    "{{AUD_N}}": str(aud["sample_size"]),
    "{{AUD_OK}}": str(aud["verdicts"].get("OK", 0)),
    "{{AUD_WEAK}}": str(aud["verdicts"].get("WEAK", 0)),
    "{{AUD_MISS}}": str(aud["verdicts"].get("MISS", 0)),
    "{{AUD_STRICT}}": f'{aud["strict_accuracy"] * 100:.0f}',
    "{{AUD_LEN}}": f'{aud["lenient_accuracy_ok_plus_weak"] * 100:.0f}',
    "{{CAT_OPTIONS}}": "".join(
        f'<option value="{i + 1}">{esc(c)}</option>' for i, c in enumerate(CATS)),
    "{{V_GROUNDED}}": str(pat["by_verification"]["grounded"]),
    "{{V_CATALOG}}": str(pat["by_verification"]["catalog"]),
    "{{V_PRIOR}}": str(pat["by_verification"]["prior"]),
}

tpl = (ROOT / "site" / "template.html").read_text()
for k, v in REPL.items():
    tpl = tpl.replace(k, v)

(ROOT / "site" / "artifact.html").write_text(tpl)

(ROOT / "index.html").write_text(
    "<!doctype html>\n<html lang=\"en\">\n<head>\n"
    "<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
    "<meta name=\"description\" content=\"Auth, access gates and agent-toolkit buildability "
    "across 100 SaaS apps, researched by an agent and verified in three loops.\">\n"
    "<style>:root{color-scheme:light}body{margin:0;font:14px system-ui}"
    "img{max-width:100%}[hidden]{display:none!important}</style>\n"
    "</head>\n<body>\n" + tpl + "\n</body>\n</html>\n")

print("wrote index.html (%d bytes) and site/artifact.html (%d bytes)" %
      ((ROOT / "index.html").stat().st_size,
       (ROOT / "site" / "artifact.html").stat().st_size))
