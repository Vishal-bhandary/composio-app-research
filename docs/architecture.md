# Architecture and design decisions

## The problem

Research 100 apps for agent-toolkit buildability, find the patterns, do it with
an agent, and prove the findings are trustworthy. Accuracy matters most.

The naive shape is "ask a model about 100 apps and tabulate". That produces a
confident, unfalsifiable table. Everything below exists to avoid that.

## Principle 1 — keep the model out of the scoring path

The model's job is reading documentation. Every statistic on the case study is a
`collections.Counter` over `data/findings.json`, computed in `agent/cluster.py`.
Nothing is asked "what are the patterns?".

This is why the headline numbers survive a clean checkout: `python3
agent/cluster.py` recomputes all of them, and `site/build.py` renders the page
from that output, so the prose cannot drift from the data.

## Principle 2 — provenance per row, not per dataset

Each row carries an evidence tier:

| Tier | Meaning | Trust |
|---|---|---|
| `catalog` | Re-fetched from Composio and machine-parsed from a structured section | highest |
| `grounded` | A documentation research pass ran for this app during this run | high |
| `prior` | Model knowledge anchored to a canonical doc URL, not re-fetched | lowest |

A single dataset-level accuracy number averages a machine-parsed field with a
remembered one and hides exactly what a reviewer needs. The audit validated the
tiers empirically: `catalog` scored 5/5, `prior` scored 1/5, and both of the
audit's two outright errors were in `prior`.

## Principle 3 — verification needs ground truth, not a second opinion from the same model

Asking a model to check its own answer measures agreement, not accuracy. Two of
the three loops here have real ground truth.

### Loop A — parser regression

Composio's toolkit pages contain a documented `## Authentication` section whose
entries carry machine-readable `- Type: \`oauth2\`` lines. Those lines are
ground truth, independent of any parser.

The first implementation matched auth keywords across the whole page. It scored
precision 0.739 / recall 0.936 / F1 0.826: recall was fine, but it invented 36
schemes that do not exist, across 30 of 79 pages. Telegram reported
`oauth2, api_key, basic, bearer_token` because the page's *prose* mentions them
while its auth section declares only `api_key`.

Rewriting the parser to read the section structure instead of the page text took
precision to 1.000. The failure mode is the instructive part: a keyword matcher
over documentation does not fail by missing things, it fails by confidently
adding them. For an agent writing into a tool catalog, precision is the metric
that matters.

### Loop B — cross-source agreement

Composio publishes its own auth classification; the research pass extracts one
from the vendor's docs. Two independent sources over 78 comparable rows.

v1 of the comparison scored 96.2% with three conflicts. Investigating them found
that two were bugs in the normaliser, not in the data: it recognised only the
literal strings "api key" and "token", so Plaid's `client_id + secret` and
higgsfield's key-id/secret pair normalised to the empty set and produced phantom
disagreements. v2 treats any issued static credential pair as the API-key family
— 98.7%.

The one surviving conflict is real and worth keeping: **Consensus** exposes a
REST API authenticated with an API key and an MCP server authenticated with
OAuth 2.1 + PKCE. Composio classified the former, the docs pass found the
latter. Forcing a single value would have destroyed information, so the row
records both.

This is the loop's actual value: of three flags, two found bugs in my own code
and one found a genuine two-surface ambiguity. None of them found a
hallucinating model.

### Loop C — human audit

20 of 100, stratified on (evidence tier × access class), over-sampling `prior`.
Verdicts are `OK` / `WEAK` (defensible but under-evidenced) / `MISS` (wrong).

Two misses, both corrected in `data/findings_seed.py` with a `[corrected by
audit]` marker and both shown on the page:

1. **Plaid** `SS → REV`. Sandbox keys are instant, but production access is a
   separate reviewed request. Classifying on the sandbox alone overstated how
   buildable the production path is.
2. **Harvest** — the access class was right but the note claimed a trial was the
   only free route; Harvest has a standing free plan.

`WEAK` exists deliberately. Ahrefs, Consensus, Otter, Neo4j and Binance are not
wrong, but each rests on a source that contradicts another or flattens a real
distinction. Collapsing those into a binary would have made the audit look
better and the dataset worse.

## Why Composio's catalog is a data source and not just a target

`agent/composio_catalog.py` resolves each app to a slug and reads
`composio.dev/toolkits/<slug>.md`. One cheap probe yields four things:

1. **A buildability oracle.** A shipped toolkit is the strongest possible
   evidence that an app is buildable today.
2. **An API-breadth measure.** Tool count per toolkit — GitHub 883, Salesforce
   556, Telegram 18 — is a far better proxy for surface size than counting
   endpoints in prose.
3. **An independent auth classification**, which is what makes Loop B possible.
4. **A coverage gap**, which is what makes the "11 easy wins" list actionable.

The 20 apps with no toolkit are not a judgement on Composio's catalog; they
track the gating pattern closely (84% coverage of self-serve apps vs 74% of
gated ones).

## The access taxonomy

Five codes, chosen because they map to different owners.

| Code | Gate | Who unblocks it |
|---|---|---|
| `SS` | none | an engineer, today |
| `SSP` | a credit card | a budget holder |
| `REV` | an approval queue | time, plus a compliant app |
| `SALES` | a contract | a partnerships conversation |
| `NONE` | no API exists | a product decision |

The hard boundary is `SS` vs `REV`, and the deciding rule is: **classify on the
production path, not the sandbox.** Plaid, Pinterest, Amazon SP-API and Meta Ads
all offer instant sandbox or trial credentials and all gate production. Scoring
them on first-key-in-hand would have put 4 extra apps in the "ship it today"
pile that an engineer could not actually ship.

`NONE` is reserved for Sherlock and Mermaid CLI, which are open-source CLIs with
no hosted service. Calling them "blocked" would imply an API exists and is
inaccessible. The honest finding is that wrapping them is a sandboxed-exec
product decision, not an integration.

## Known weaknesses

- **Egress.** The run environment allowed `composio.dev` and `github.com` only.
  Catalog data is live; vendor documentation came through a search tool that
  returns primary URLs and quoted passages. Evidence links are real and were
  returned by the research pass, but most were not re-opened at render time.
  `audit.json` marks the rows whose verdict depends on a page that could not be
  re-opened (`needs_live_recheck`).
- **MCP detection is opportunistic.** 33 official MCP servers were established
  from evidence encountered during research, not from probing every vendor's
  `/.well-known`. The true number is probably higher.
- **Snapshot, not a feed.** Google sunset Google Ads developer tokens on
  2026-09-09; the ad platforms change their gates frequently. A production
  version of this would re-run stage 2 weekly and diff.
- **Two vendors defeated the research.** iPayX (no documentation found at all)
  and Paygent Connect (identifiable only as NMI-powered). Both are recorded at
  low confidence rather than filled with a plausible guess.
