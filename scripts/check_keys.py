"""
Diagnose API key problems.

"API key not valid" has several different causes that look identical from the
terminal. This checks each one and says which it is.

    python3 scripts/check_keys.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.env import load_env  # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
OK, BAD, WARN = f"{GREEN}  OK  {RESET}", f"{RED} FAIL {RESET}", f"{YELLOW} WARN {RESET}"


def mask(v: str) -> str:
    if len(v) <= 10:
        return "*" * len(v)
    return f"{v[:6]}...{v[-4:]}  (length {len(v)})"


def inspect(name: str, from_file: list[str]) -> str | None:
    raw = os.environ.get(name)
    if not raw:
        print(f"{DIM}  --    {name}: not set{RESET}")
        return None
    src = ".env" if name in from_file else "shell environment"
    print(f"{OK}  {name}: {mask(raw)}   [{src}]")
    if raw != raw.strip():
        print(f"{WARN}    value has leading/trailing whitespace")
    for ch in ('"', "'", " "):
        if ch in raw:
            print(f"{WARN}    value contains a {ch!r} character - is that intentional?")
    if raw.lower().startswith(("your-", "paste", "<", "sk-ant-...")):
        print(f"{BAD}    this is still the placeholder text, not a real key")
    return raw


def main() -> None:
    print(f"\n{'='*66}\n  API KEY CHECK\n{'='*66}\n")

    env_file = ROOT / ".env"
    if env_file.exists():
        print(f"{OK}  .env found at {env_file}")
    else:
        print(f"{BAD}  no .env file at {env_file}")
        print(f"       create it with:  python3 -c \"import shutil; shutil.copy('.env.example','.env')\"")
    loaded = load_env()
    print(f"{DIM}       keys read from .env: {', '.join(loaded) if loaded else '(none - all blank?)'}{RESET}\n")

    print("-- values " + "-" * 55)
    gem = inspect("GEMINI_API_KEY", loaded)
    goog = inspect("GOOGLE_API_KEY", loaded)
    inspect("ANTHROPIC_API_KEY", loaded)
    comp = inspect("COMPOSIO_API_KEY", loaded)

    if gem and goog and gem != goog:
        print(f"\n{WARN}  BOTH GEMINI_API_KEY and GOOGLE_API_KEY are set, to different values.")
        print("       The SDK may pick either one. Unset the one you do not want:")
        print("         PowerShell:  Remove-Item Env:GOOGLE_API_KEY")
        print("         Mac/Linux:   unset GOOGLE_API_KEY")

    key = gem or goog
    if key and not key.startswith("AIza"):
        print(f"\n{WARN}  Gemini key does not start with 'AIza'.")
        print("       AI Studio keys do. A Vertex AI / service-account credential will")
        print("       not work here - get an AI Studio key at aistudio.google.com/apikey")

    # ---- live tests ----
    print("\n-- live tests " + "-" * 51)
    try:
        import httpx
    except ImportError:
        sys.exit("httpx missing - run: pip install -r requirements.txt")

    if key:
        try:
            r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                          params={"key": key, "pageSize": 5}, timeout=30.0)
            if r.status_code == 200:
                names = [m.get("name", "").removeprefix("models/")
                         for m in r.json().get("models", [])]
                print(f"{OK}  Gemini key works. Sample models: {', '.join(names[:5])}")
            elif r.status_code == 400:
                print(f"{BAD}  Gemini rejected the key (400 API_KEY_INVALID).")
                print("       The key is wrong, revoked, or from a different Google product.")
                print("       Fix: aistudio.google.com/apikey -> delete the old key ->")
                print("            Create API key -> copy the whole string -> paste into .env")
            elif r.status_code == 403:
                print(f"{BAD}  Gemini returned 403. The key exists but is restricted,")
                print("       or the Generative Language API is not enabled on its project.")
            else:
                print(f"{BAD}  Gemini returned HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as exc:
            print(f"{BAD}  could not reach Gemini: {exc!r}")
    else:
        print(f"{DIM}  --    no Gemini key to test{RESET}")

    if comp:
        try:
            r = httpx.get("https://backend.composio.dev/api/v3.1/toolkits/github",
                          headers={"x-api-key": comp}, timeout=30.0)
            if r.status_code == 200:
                print(f"{OK}  Composio key works. Fetched toolkit: {r.json().get('name')}")
            elif r.status_code in (401, 403):
                print(f"{BAD}  Composio rejected the key (HTTP {r.status_code}).")
                print("       Fix: platform.composio.dev -> Settings -> API Keys -> regenerate")
            else:
                print(f"{BAD}  Composio returned HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as exc:
            print(f"{BAD}  could not reach Composio: {exc!r}")
    else:
        print(f"{DIM}  --    no Composio key to test{RESET}")

    print(f"\n{'='*66}\n")


if __name__ == "__main__":
    main()
