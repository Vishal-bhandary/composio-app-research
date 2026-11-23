# Setup

Two ways to use this: **view the case study** (no install, no keys) or **run the
research pipeline** (Python, optional keys).

---

## 1. Just view the case study

**Hosted:** https://vishal-bhandary.github.io/composio-app-research/

**Locally**, after cloning — `index.html` is fully self-contained, so opening the
file works:

```bash
git clone https://github.com/Vishal-bhandary/composio-app-research.git
```

```bash
cd composio-app-research && python3 -m http.server 8000
```

Then open http://localhost:8000. (Double-clicking `index.html` also works; the
local server only matters if you want the same origin behaviour as the hosted
copy.)

---

## 2. Run the pipeline

### Prerequisites

| Thing | Version | Check |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| pip | any | `python3 -m pip --version` |

```bash
python3 -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

### Run everything that needs no credentials

```bash
python3 agent/run.py
```

About a minute. Only talks to `composio.dev`. This runs:

| Stage | What it does |
|---|---|
| 2 Catalog probe | Resolves 100 apps against Composio's public toolkit pages |
| 4 Verify | Loop A parser regression, Loop B cross-source agreement |
| 4c Audit | Scores the 20-row hand audit |
| 5 Cluster | Recomputes every statistic into `patterns.json` |
| 5 Render | Rebuilds `index.html` from the data |

If the numbers in `data/patterns.json` match what the page shows, the whole
analysis reproduced from scratch.

---

## 3. API keys

**You need none of these to reproduce the published results.** Each one unlocks
an extra stage.

### `ANTHROPIC_API_KEY` — unlocks stage 3 (documentation research)

| | |
|---|---|
| Where | https://platform.claude.com → **API keys** → *Create key* |
| Format | `sk-ant-...` |
| Unlocks | `agent/research.py` — Claude + server-side web search produces one schema-valid finding per app |
| Cost | ~100 requests with web search. On `claude-opus-5-5` roughly **$3–8** for all 100; `--model claude-sonnet-5-5` is roughly a quarter of that |
| Billing | Pay-as-you-go. Add credit in the Console before the first call or requests 400 |

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

```bash
python3 agent/research.py --only 5 17 94
```

Start with `--only` on three apps. That costs cents and confirms the key works
before you spend on all 100. Then:

```bash
python3 agent/run.py --research
```

### `COMPOSIO_API_KEY` — unlocks stage 2b (authenticated catalog check)

| | |
|---|---|
| Where | https://platform.composio.dev → **Settings** → *API Keys* |
| Header | sent as `x-api-key` |
| Unlocks | `agent/composio_api.py` — re-checks the catalog through Composio's REST **v3.1** API instead of its public pages, giving a third independent auth source |
| Cost | Free tier is sufficient; these are catalog reads, not tool executions |

Run the self-test first. It fetches one toolkit and tells you whether the
response shape still matches what the code expects:

```bash
export COMPOSIO_API_KEY=...
```

```bash
python3 agent/composio_api.py --selftest
```

If it prints `MISSING EXPECTED KEYS: none`, run the full stage:

```bash
python3 agent/run.py --composio-api
```

> This stage was written against Composio's published v3.1 OpenAPI reference but
> could **not** be executed during the build — the sandbox could not reach
> `backend.composio.dev`. The self-test exists precisely so the first real run
> tells you if a field has moved. Stage 2, which produced the shipped data,
> needs no key and was fully exercised.

### Keys you do **not** need

OpenAI, Firecrawl, Tavily, Exa, or accounts with any of the 100 apps. The
assignment explicitly does not require paid accounts, and recording an app as
gated *is* the finding.

### Using a `.env` file instead of exports

```bash
cp .env.example .env
```

Fill it in, then `set -a && source .env && set +a`. `.env` is gitignored —
never commit it.

---

## 4. Publishing the page

GitHub Pages serves `index.html` from the repository root.

1. **github.com/Vishal-bhandary/composio-app-research/settings/pages**
2. **Source** → *Deploy from a branch*
3. **Branch** → `main`, folder → `/ (root)` → **Save**

First build takes 1–2 minutes, then the page is live at
`https://vishal-bhandary.github.io/composio-app-research/`.

To update it after changing the data:

```bash
python3 agent/run.py && git add -A && git commit -m "Refresh findings" && git push
```

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: httpx` | deps not installed | `pip install -r requirements.txt` |
| Stage 2 finds 0 toolkits | no egress to `composio.dev` | check proxy/firewall; the probe needs that one host |
| `ANTHROPIC_API_KEY is not set` | only stage 3 needs it | run `python3 agent/run.py` without `--research` |
| `401 - check COMPOSIO_API_KEY` | wrong or expired key | regenerate in the Composio dashboard |
| Stage 3 reports `schema:` errors | model returned off-schema JSON | re-run those ids with `--only`; the row is skipped, not corrupted |
| Pages shows a 404 | source not set to root | Settings → Pages → branch `main`, folder `/ (root)` |
| Page renders unstyled | Google Fonts blocked | cosmetic only; the fallback stack still reads correctly |
