"""
distill — poistaa kohinan API-dokumentaatiotekstistä.

Tavoite: mahdollisimman vähän tokeneita, mahdollisimman paljon signaalia.
Ei LLM-kutsuja — pelkät deterministiset säännöt.
"""

import re


# ─── Boilerplate-patternit jotka poistetaan kokonaan ─────────────────────────

_NOISE: list[tuple[re.Pattern, str]] = [
    # Spotify ML-disclaimer
    (re.compile(
        r"Please note that you can not use the Spotify Platform.*?AI model[^.]*\.",
        re.DOTALL | re.IGNORECASE,
    ), ""),
    (re.compile(r"Spotify content may not be used to train.*?\.", re.IGNORECASE), ""),
    # "More information" ilman kontekstia
    (re.compile(r"^More information\s*$", re.MULTILINE), ""),
    # Spotify usage policy / legal boilerplate
    (re.compile(r"You may not facilitate downloads of Spotify content[^.]*\.", re.IGNORECASE), ""),
    (re.compile(r"Spotify visual content must be kept in its original form[^.]*\.", re.IGNORECASE), ""),
    (re.compile(r"you can not crop album artwork[^.]*\.", re.IGNORECASE), ""),
    (re.compile(r"place a brand/logo on album artwork[^.]*\.", re.IGNORECASE), ""),
    (re.compile(r"Please keep in mind that metadata.*?Spotify Service\.", re.IGNORECASE | re.DOTALL), ""),
    (re.compile(r"You must also attribute content from Spotify[^.]*\.", re.IGNORECASE), ""),
    # Tyhjiä markdown-linkkejä
    (re.compile(r"\[.*?\]\(\s*\)"), ""),
    # Last.fm footer-kohina
    (re.compile(r"^Last\.fm API.*$", re.MULTILINE), ""),
    (re.compile(r"^API TOS.*$", re.MULTILINE | re.IGNORECASE), ""),
    # "Try it" / interaktiiviset napit
    (re.compile(r"^Try it\s*$", re.MULTILINE), ""),
    (re.compile(r"^(Console|Expand all|Collapse all)\s*$", re.MULTILINE), ""),
]

# Backtick-fragmentit omilla riveillään → kootaan samalle riville
# Esim: "`album`\n\n,`artist`\n\n,`track`" → "`album`, `artist`, `track`"
_BACKTICK_FRAGMENT = re.compile(r"`([^`\n]+)`\s*\n\s*,\s*`")

# "nameTypeRequired" → korjattu muoto
# Spotifyn docs yhdistää nimen, tyypin ja required-tilan ilman välilyöntejä
_PARAM_NOTYPE = re.compile(
    r"^[-•]\s*([a-z_]+)(string|integer|boolean|array|number|object)\s*(Required|Optional)?\s*",
    re.MULTILINE | re.IGNORECASE,
)


def _fix_param_line(m: re.Match) -> str:
    name = m.group(1)
    ptype = m.group(2)
    req = m.group(3) or "Optional"
    marker = "✱" if req.lower() == "required" else "○"
    return f"- {marker} `{name}` ({ptype}) "


def _collapse_backtick_lists(text: str) -> str:
    """
    Kerää pilkulla erotetut backtick-fragmentit yhdelle riville.
    Spotifyn docs: jokainen arvo omalla rivillään tyhjillä riveillä ympärillä.
    Esim: '`album`\n\n,`artist`\n\n,`track`' → '`album`, `artist`, `track`'
    """
    # Useampi kierros: poista tyhjät rivit backtick-arvojen ,`xxx` ketjussa
    for _ in range(10):
        prev = text
        # Muoto: `arvo`\n\n,`seuraava` tai `arvo`\n,`seuraava`
        text = re.sub(r"(`[^`\n]+`)\s*\n+\s*,\s*\n*\s*(`)", r"\1, \2", text)
        # Muoto: , and`arvo` (ilman välilyöntiä)
        text = re.sub(r",\s*and\s*`", r", `", text)
        if text == prev:
            break
    # Siivoa myös: "The`arvo`" → "The `arvo`" (puuttuvat välilyönnit)
    text = re.sub(r"([a-zA-Z])(`[^`\s])", r"\1 \2", text)
    # Poista ylimääräiset välilyönnit backtickien sisällä: `arvo ` → `arvo`
    text = re.sub(r"`\s+([^`]+?)\s+`", r"`\1`", text)
    text = re.sub(r"`\s+([^`]+?)`", r"`\1`", text)
    text = re.sub(r"`([^`]+?)\s+`", r"`\1`", text)
    return text


def _mark_deprecated(raw_before_cleaning: str, cleaned: str) -> str:
    """
    Liputa endpoint deprecated:ksi vain jos koko endpoint on deprecated —
    ei jos ainoastaan yksittäiset kentät ovat deprecated.
    Tarkistus tehdään raakasisällöstä ennen kenttäparsintaa.
    """
    # Endpoint-tason deprecated: esiintyy otsikossa tai intro-kappaleessa
    # eikä pelkästään kenttäkuvauksissa
    intro = raw_before_cleaning[:800]
    endpoint_deprecated = bool(re.search(
        r"(this endpoint is deprecated|deprecated endpoint|"
        r"\[DEPRECATED\]|endpoint.*?deprecated|deprecated.*?endpoint)",
        intro, re.IGNORECASE,
    ))
    if endpoint_deprecated:
        return "⚠️  DEPRECATED\n\n" + cleaned
    return cleaned


def _compress_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)   # trailing spaces
    text = re.sub(r"\n{3,}", "\n\n", text)                      # max 2 tyhjää riviä
    return text.strip()


def _aggressive_trim(text: str) -> str:
    """
    Aggressiivinen tila: poimitaan vain endpoint + parametrilista + deprecation.
    Kaikki selitystekstit, esimerkit, responset ja curl-blokit poistetaan.
    Tavoite: ~200-400 tokenia per endpoint.
    """
    lines = text.splitlines()
    result: list[str] = []
    in_params = False

    for line in lines:
        stripped = line.strip()

        # Aina pidä: otsikot, endpoint-rivit, deprecated-merkinnät
        if stripped.startswith("#") or "⚠️" in stripped:
            result.append(line)
            in_params = False
            continue

        # HTTP-metodi + polku
        if re.match(r"(GET|POST|PUT|DELETE|PATCH)\s+/", stripped):
            result.append(line)
            continue

        # Parametririvi (meillä ✱/○ muoto tai alkuperäinen "- name")
        if re.match(r"[-•]\s*[✱○]?\s*`[a-z_]", stripped):
            # Ota nimi, tyyppi, required — leikkaa pitkä selitys 80 merkissä
            short = stripped[:120].rstrip()
            result.append(short)
            in_params = True
            continue

        # Lyhyt example-rivi parametrin perässä (pidä)
        if in_params and re.match(r"(Default|Range|Example|Allowed):", stripped):
            result.append(f"  {stripped[:80]}")
            continue

        # Kaikki muu: skipataan
        in_params = False

    return "\n".join(result)


# ─── Pääfunktio ──────────────────────────────────────────────────────────────

def distill(raw: str, aggressive: bool = False) -> str:  # noqa: C901
    """
    Poistaa kohinan API-dokumentaatiotekstistä.

    Args:
        raw:        fetch_doc():n palauttama raakasisältö
        aggressive: True = lyhyempi mutta saattaa kadottaa detaljeja

    Returns:
        Tiivistetty teksti
    """
    text = raw

    # 1. Poista boilerplate
    for pattern, replacement in _NOISE:
        text = pattern.sub(replacement, text)

    # 2. Korjaa Spotifyn epäsiisti parametriformaatti
    text = _PARAM_NOTYPE.sub(_fix_param_line, text)

    # 3. Kerää hajonneet backtick-listat yhdelle riville
    text = _collapse_backtick_lists(text)

    # 4. Merkitse deprecated (verrataan raakatekstiin ennen siivousta)
    text = _mark_deprecated(raw, text)

    # 5. Aggressiivinen tiivistys
    if aggressive:
        text = _aggressive_trim(text)

    # 6. Siisti whitespace
    text = _compress_whitespace(text)

    return text


def token_estimate(text: str) -> int:
    """Karkea token-arvio: ~4 merkkiä per token."""
    return len(text) // 4
