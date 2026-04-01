"""
Tumma sähkö — Pixel Grip & the Dark Electric
Symphonic poem, 28 kappaletta.

Rakennuspäätös:
  Pixel Grip keskipisteenä, mutta ei ensimmäisenä eikä kokoajan.
  He ilmestyvät neljä kertaa — aina vähän eri puolesta: varjosta,
  koneesta, ruumiista, hautajaishuudosta.

Teema: Kehon kontrolli ja sen hajoaminen.
  Tumma kaupunki, neon, hiki, koneaalto. Ei suru — jännitys.
  Genre on vain puku. Teema on asento.

Pylväät:
  Pixel Grip (4 kpl) — koko listan sydän
  Boy Harsher (3 kpl) — darkwave ankkuri, iso nimi
  Sextile (2 kpl) — LA post-punk kone
  Linea Aspera (2 kpl) — silta klassikoihin

Kansi:
  Kontravoid, NNHMN, Youth Code, Panther Modern,
  S. Product, Zanias, Qual, Spike Hellis, Buzz Kull,
  Riki, Kanga, Patriarchy, Rein, Ultra Sunn

Valot:
  Nitzer Ebb — OG EBM, 1987, yllättää hengähdyskohdassa
  Marie Davidson — Montréal minimalismi, eri suunta

Energiarakenne:
  Avaus (1–4): kutsuu sisään, pulssi alkaa
  Aalto 1 (5–11): rakentuu → HUIPPU 1 (Linea Aspera)
  Hengähdys (12–14): laskeutuu — Nitzer Ebb VALO tässä
  Aalto 2 (15–22): eri sävy, tanssivampi → HUIPPU 2 (Pixel Grip)
  Marie Davidson VALO (22): käänne
  Aalto 3 (23–26): syvemmälle → HUIPPU 3 / KLIIMAKS (Pixel Grip)
  Laskeutuminen (27–28): hiljalleen häipyy

Artisti-hajonta:
  Pixel Grip: 3, 11, 19, 26 — välit: 8, 8, 7 ✓
  Boy Harsher: 4, 13, 28 — välit: 9, 15 ✓
  Sextile: 5, 21 — väli: 16 ✓
  Zanias: 9, 25 — väli: 16 ✓
  Linea Aspera: 10, (ei toistoa — vain kerran, ehkä laskeutumiseen)

API-pohja (Last.fm similar_artists, tag haut, similar_tracks):
  Pixel Grip similar: Panther Modern, Sextile, Patriarchy, Boy Harsher,
    Spike Hellis, Zanias, Kontravoid, Qual, Youth Code, Linea Aspera (via Sextile)
  Discogs: Pixel Grip Arena want=120, Kontravoid want=222, Sextile want=297
  Klassiikot vahvistettu: Nitzer Ebb want=980, Front 242 want=704
"""

NAME = "Tumma sähkö"
DESCRIPTION = (
    "Pixel Grip & the dark electric. "
    "Darkwave · EBM · post-punk · body music. "
    "Kaupungin pulssi, kehon kontrolli ja sen hajoaminen. "
    "Symphonic poem: pylväät, kansi, valot."
)

TRACKS = [
    # ── AVAUS — pulssi alkaa (1–4) ──────────────────────────────────────────
    ("Kontravoid",          "Native State"),           # 1  kylmä avaus, mekaaninen
    ("NNHMN",               "Der Unweise"),             # 2  eurooppalainen kylmä
    ("Pixel Grip",          "Demon Chaser"),            # 3  [PG #1] — varjosta sisään
    ("Boy Harsher",         "Tears"),                   # 4  darkwave tunnelma syvenee

    # ── AALTO 1 — rakentuu → huippu (5–11) ──────────────────────────────────
    ("Sextile",             "Disco"),                   # 5  LA-kone käynnistyy
    ("Youth Code",          "For I Am Cursed"),         # 6  intensiteetti nousee
    ("Panther Modern",      "Creep"),                   # 7  tumma groove
    ("S. Product",          "Waste Your Time"),         # 8  nyrkkiä + kohinaa
    ("Zanias",              "Follow the Body"),         # 9  kehollinen, laskee hieman
    ("Linea Aspera",        "Synapse"),                 # 10 HUIPPU 1 — klassinen EBM-DNA
    ("Pixel Grip",          "Stamina"),                 # 11 [PG #2, väli=8✓] kovempi nyt

    # ── HENGÄHDYS (12–14) ───────────────────────────────────────────────────
    ("Nitzer Ebb",          "Let Your Body Learn"),     # 12 VALO 1 — 1987, OG, yllättää
    ("Boy Harsher",         "Morphine"),                # 13 [BH, väli=9✓] hidas, laantuva
    ("Qual",                "Take Me Higher"),          # 14 meditatiivinen intensiteetti

    # ── AALTO 2 — tanssivampi sävy → huippu (15–22) ─────────────────────────
    ("Spike Hellis",        "Feed"),                    # 15 kineettinen, nousee
    ("Buzz Kull",           "Into the Void"),           # 16 Melbourne coldwave kasvaa
    ("Riki",                "Napoleon"),                # 17 Berliini, pop-kimalto
    ("Kanga",               "Going Red"),               # 18 tumma electropop
    ("Pixel Grip",          "ALPHAPUSSY"),              # 19 [PG #3, väli=8✓] HUIPPU 2
    ("Patriarchy",          "Suffer"),                  # 20 tumma glamour, jälkisoikua
    ("Sextile",             "Contortion"),              # 21 [gap=16✓] teollisuushankaus
    ("Marie Davidson",      "Demolition"),              # 22 VALO 2 — Montréal, yllättävä

    # ── AALTO 3 — syvemmälle → kliimaks (23–26) ─────────────────────────────
    ("Rein",                "Bruises"),                 # 23 keho, tumma teollisuus
    ("Ultra Sunn",          "Keep Your Eyes Peeled"),   # 24 massiivinen ankkuri
    ("Zanias",              "Through This Collapse"),   # 25 [gap=16✓] hajoaa viimein
    ("Pixel Grip",          "Dancing On Your Grave"),   # 26 [PG #4, väli=7✓] KLIIMAKS

    # ── LASKEUTUMINEN — häipyy (27–28) ──────────────────────────────────────
    ("Boy Harsher",         "LA"),                      # 27 [BH, väli=14✓] etääntyy
    ("TR/ST",               "Sulk"),                    # 28 viimeinen hengitys, sammuu
]
