#!/usr/bin/env python3
"""
fetch_doc — hakee ja parsii API-dokumentaation URL:sta tai nimetystä avaimesta.

Käyttö:
    python tools/fetch_doc.py spotify.search
    python tools/fetch_doc.py https://developer.spotify.com/...
    python tools/fetch_doc.py --list
    python tools/fetch_doc.py --list spotify
"""

import sys
import textwrap
import httpx
import trafilatura
import yaml
from api.sources import DOCS, list_keys
from tools.distill import distill, token_estimate

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_TRAFILATURA_OPTS = dict(
    include_tables=True,
    include_links=False,
    include_formatting=True,
    no_fallback=False,
)


def _fetch_content(url: str) -> str | None:
    """
    Hakee URL:n sisällön kolmella menetelmällä:
    1. trafilatura.fetch_url  — nopein, ei JS
    2. httpx + trafilatura    — fallback staattisille sivuille
    3. Playwright + trafilatura — JS-renderöidyt sivut (Last.fm jne.)
    """
    # 1. trafilatura suoraan
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        content = trafilatura.extract(downloaded, **_TRAFILATURA_OPTS)
        if content and len(content) > 100:
            return content

    # 2. httpx
    try:
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
        resp.raise_for_status()
        content = trafilatura.extract(resp.text, **_TRAFILATURA_OPTS)
        if content and len(content) > 100:
            return content
    except httpx.HTTPError:
        pass

    # 3. Playwright — JS-renderöinti
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=20000)
            html = page.content()
            browser.close()
        content = trafilatura.extract(html, **_TRAFILATURA_OPTS)
        if content and len(content) > 100:
            return content
    except Exception:
        pass

    return None


def fetch_doc(url_or_key: str, output: str = "text", clean: bool = True, aggressive: bool = False) -> str:
    """
    Hakee API-dokumentaation.

    Args:
        url_or_key: Nimetty avain (esim. "spotify.search") tai suora URL
        output:     "text" | "yaml" — palautusmuoto
        clean:      True = aja distill() kohinanpoisto (oletus: True)
        aggressive: True = aggressiivisempi tiivistys (lyhyempi, vähemmän tokeneita)

    Returns:
        Parsittu sisältö merkkijonona
    """
    # Resolve nimetty avain
    if url_or_key in DOCS:
        url = DOCS[url_or_key]
        key_used = url_or_key
    else:
        url = url_or_key
        key_used = url

    content = _fetch_content(url)

    if not content:
        return (
            f"[HUOM] Kaikki hakumenetelmät epäonnistuivat.\n"
            f"Avain: {key_used}\nURL: {url}"
        )

    # Kohinanpoisto
    if clean:
        content = distill(content, aggressive=aggressive)

    tokens = token_estimate(content)

    if output == "yaml":
        return yaml.dump(
            {"key": key_used, "url": url, "tokens_approx": tokens, "content": content},
            allow_unicode=True,
            default_flow_style=False,
        )

    # Teksti-output: header + token-arvio + sisältö
    separator = "─" * 60
    header = f"# {key_used}\n# {url}\n# ~{tokens} tokenia\n{separator}\n"
    return header + content


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if args[0] == "--list":
        prefix = args[1] if len(args) > 1 else ""
        keys = list_keys(prefix)
        print(f"\nSaatavilla olevat doc-avaimet{f' (prefix: {prefix})' if prefix else ''}:\n")
        for k in keys:
            print(f"  {k:<45} {DOCS[k]}")
        sys.exit(0)

    output_fmt = "yaml" if "--yaml" in args else "text"
    aggressive = "--aggressive" in args
    no_clean = "--raw" in args
    target = next(a for a in args if not a.startswith("--"))

    result = fetch_doc(target, output=output_fmt, clean=not no_clean, aggressive=aggressive)
    print(result)


if __name__ == "__main__":
    main()
