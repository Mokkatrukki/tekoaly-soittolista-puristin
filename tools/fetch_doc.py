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

    # Yritä ensin trafilatura.fetch_url (osaa käsitellä redirectit + perustason JS)
    downloaded = trafilatura.fetch_url(url)
    content = None

    if downloaded:
        content = trafilatura.extract(
            downloaded,
            include_tables=True,
            include_links=False,
            include_formatting=True,
            no_fallback=False,
        )

    # Fallback: httpx + trafilatura
    if not content:
        try:
            resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
            resp.raise_for_status()
            content = trafilatura.extract(
                resp.text,
                include_tables=True,
                include_links=False,
                include_formatting=True,
            )
        except httpx.HTTPError as e:
            return f"[VIRHE] HTTP-haku epäonnistui: {e}\nURL: {url}"

    if not content:
        return (
            f"[HUOM] Automaattinen parsinta ei onnistunut — sivu saattaa vaatia JS-renderöintiä.\n"
            f"Avain: {key_used}\nURL: {url}\n\n"
            f"Voit hakea sen manuaalisesti WebFetch-työkalulla."
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
