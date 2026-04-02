# /soittolista $ARGUMENTS

Rakenna uusi soittolista alusta loppuun. Filosofia ohjaa rakennetta, APIen data ohjaa sisältöä.

`$ARGUMENTS` = valinnainen alkukuvaus, esim. "melankolinen syysilta" tai "Nick Cave -vibes"

---

## STOP-FOR -arkkitehtuuri

**Pysähdy ja kysy VAIN kun:**
- Haastattelu on epäselvä: ei tunnelmaa eikä yhtään referenssipistettä
- Kaikki APIen palauttavat 0 tulosta kaikille siemenille
- Unresolved-kappaleet > 20% ennen soittolistan luontia

**ÄLÄ KOSKAAN pysähdy:**
- Filosofian valintaan (valitse automaattisesti — nyt aina symphonic_poem)
- Pisteytysjärjestykseen (ranking päättää)
- Discogs-hakuun (aina taustalle)
- Artistihajonta-rikkomuksiin (korjaa automaattisesti järjestystä)
- Yksittäisiin puuttuviin kappaleisiin jos unresolved < 20%

---

## VAIHE 1 — FILOSOFIA

Lue `curator/philosophies/INDEX.md`. Valitse filosofia:
- Jos vain yksi filosofia: käytä sitä automaattisesti, ilmoita käyttäjälle
- Jos useampia: tunnista sopivin käyttäjän kuvauksen perusteella (ei kysytä)

Lue valitun filosofian tiedosto kokonaan. Se ohjaa kaikkia seuraavia vaiheita.

---

## VAIHE 2 — HAASTATTELU

**STOP:** Kysy nämä ennen kuin jatkat. Vapaamuotoinen keskustelu, ei lomake.

Symphonic Poem -filosofian rakennuskysymykset (muokkaa tilanteen mukaan):
1. Mikä on soittolistan "sää"? — tunnelma tai tilanne
2. Referenssipisteet — artisti, kappale, levy tai genre josta lähdetään
3. Mikä on teema yli genrerajojen — mikä tunne yhdistää kaiken?
4. Mitä EI haluta — genre, artisti tai tunnelma jota vältetään
5. Soittolistan koko (oletus: 20 kpl) ja aikakausi?

Tunnista moodista:
- `normal` — tietää mitä haluaa, on referenssipisteitä
- `expand` — tuttu alue, haluaa löytää lisää
- `trail` — uteliaisuus: vaikutteet, yhteistyöt, tuottajat
- `escape` — haluaa ulos kuplasta

**Vältettävät:** Aja heti haastattelun jälkeen:
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.spotify import SpotifyClient
sp = SpotifyClient()
recent = sp.recently_played(limit=25)
for t in recent:
    print(t.artist, '—', t.name)
"
```
Nämä artistit/kappaleet saavat -2.0 pistettä rakennusvaiheessa.

---

## VAIHE 3 — HAKU

Aja kaikki relevantit haut. Rakenna siemenlistaus haastattelun perusteella.

### Discogs taustalle ENSIN (hidas, ei saa blokata)
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.discogs import DiscogsClient
dc = DiscogsClient()

# Korvaa seed_albums haastattelun perusteella
seed_albums = [
    ('ARTISTI ALBUMI', 3),
    ('ARTISTI2 ALBUMI2', 2),
]
futures = dc.search_background(seed_albums)
import json
# Tallenna futures-avaimet muistiin — noudetaan vaiheessa 3d
print('Discogs käynnistetty:', list(futures.keys()))
"
```

### 3a — Last.fm similar_artists
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.lastfm import LastFmClient
lfm = LastFmClient()

seed_artists = ['ARTISTI1', 'ARTISTI2']  # haastattelun perusteella

for artist in seed_artists:
    similar = lfm.similar_artists(artist, limit=25)
    print(f'\n=== similar_artists({artist}) ===')
    for a in similar:
        print(f'  match={a.match:.2f}  {a.name}')
        # Matala match (<0.3) = potentiaaliset valot ja pakotiet
        if a.match < 0.3:
            print(f'    ^ MATALA MATCH — tarkista genrerajojen ylitys')
"
```

### 3b — Last.fm tagit + tag_top_tracks
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.lastfm import LastFmClient
lfm = LastFmClient()

seed_artists = ['ARTISTI1']  # pääsiemen
tags = lfm.artist_tags(seed_artists[0], limit=5)
top_tags = [t['tag'] for t in tags[:3]]
print('Tagit:', top_tags)

for tag in top_tags:
    tracks = lfm.tag_top_tracks(tag, limit=20)
    print(f'\n=== tag_top_tracks({tag}) ===')
    for t in tracks:
        print(f'  {t[\"artist\"]} — {t[\"title\"]}')
"
```

### 3c — Last.fm similar_tracks (jos yksittäisiä kappaleita annettu)
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.lastfm import LastFmClient
lfm = LastFmClient()

# Käytä jos käyttäjä antoi yksittäisiä kappaleita referenssiksi
seed_tracks = [('ARTISTI', 'KAPPALE')]

for artist, title in seed_tracks:
    similar = lfm.similar_tracks(artist, title, limit=15)
    print(f'\n=== similar_tracks({artist} — {title}) ===')
    for t in similar:
        # Korkea match = genressä pysytään, matala match = potentiaalinen valo
        flag = ' ← MATALA' if t.match < 0.3 else ''
        print(f'  match={t.match:.2f}  {t.artist} — {t.title}{flag}')
"
```

### 3d — MusicBrainz suhteet (expand/trail -moodissa)
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.musicbrainz import MusicBrainzClient
mb = MusicBrainzClient()

results = mb.search_artist('ARTISTI', limit=1)
if results:
    info = mb.artist(results[0]['mbid'])
    print('Tagit:', info.tags[:8])
    print('Suhteet:')
    for r in info.relationships:
        if r['type'] in ('influenced by', 'collaboration', 'member of'):
            print(f'  [{r[\"type\"]}] {r[\"target_name\"]}')
"
```

### 3e — Nouda Discogs-tulokset
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.discogs import DiscogsClient
dc = DiscogsClient()

# Aja uudelleen synkronisena (tai käytä futures.result() jos sama sessio)
seed_albums = [('ARTISTI ALBUMI', 3)]
results = dc.search(seed_albums[0][0], limit=3)
for r in results:
    want = r.get('community_want', 0)
    stars = '★★★' if want > 2000 else '★★' if want > 500 else '★' if want > 100 else ''
    print(f'{r[\"title\"]} ({r.get(\"year\",\"?\")}) want={want} {stars}')
"
```

---

## VAIHE 4 — KOKOA JA PISTEYTÄ

Aja PlaylistBuilder kaikkien hakutulosten pohjalta:

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from curator.playlist_builder import PlaylistBuilder
from api.lastfm import LastFmClient
lfm = LastFmClient()

builder = PlaylistBuilder()

# Lisää kaikki löydetyt ehdokkaat lähde ja paino merkittynä
# Painot:
#   1.5 — Last.fm similar_artists (korkea match >0.5)
#   1.3 — Last.fm similar_artists (matala match <0.3) — potentiaaliset valot
#   1.2 — Last.fm tag_top_tracks
#   1.0 — MusicBrainz suhteet
#   1.5 — Discogs want > 2000 (klassikko)
#   1.2 — Discogs want > 500

# Esimerkki:
similar = lfm.similar_artists('ARTISTI', limit=25)
high_match = [a for a in similar if a.match >= 0.3]
low_match  = [a for a in similar if a.match < 0.3]

for a in high_match:
    tracks = lfm.artist_top_tracks(a.name, limit=3)
    builder.add(tracks, source=f'lfm_similar(match={a.match:.2f})', weight=1.5)

for a in low_match:
    tracks = lfm.artist_top_tracks(a.name, limit=2)
    builder.add(tracks, source=f'lfm_low_match(match={a.match:.2f})', weight=1.3)

ranked = builder.rank(limit=40)
print(f'Kandidaatteja yhteensä: {len(builder._pool)}')
print()
for i, c in enumerate(ranked[:30], 1):
    src = ' | '.join(c.sources)
    bar = '█' * min(int(c.score), 8)
    print(f'{i:2}. {c.artist:30s} — {c.title:35s} [{c.score:.1f}p] {bar}')
    print(f'    {src}')
"
```

---

## VAIHE 5 — RAKENNA SYMPHONIC POEM

Sovella filosofia ranked-listaan. **Tee tämä itse — älä kysy käyttäjältä.**

1. **Valitse pylväät** (4–6 artistia): korkeimmat pisteet, useimmista lähteistä
2. **Valitse kansi**: high match -kappaleet pylväiden välille
3. **Valitse valot** (2–4): matalan matchin kappaleet, eri vuosikymmen tai genre

Järjestä lista Symphonic Poem -energiarakenteen mukaan:
```
Avaus (1–3):       kutsuva, ei huuda
Aalto 1 (4–10):    rakentuu kohti ensimmäistä huippua
Hengähdys (11–12): laskeutuu
Aalto 2 (13–19):   erilainen sävy
Valo (20–22):      yllätys — matalan matchin kappale
Aalto 3 (23–29):   voi mennä syvemmälle
Laskeutuminen:     etääntyy
```

Tarkista artistihajonta: sama artisti vähintään 6 kpl välissä. Korjaa järjestystä tarvittaessa automaattisesti.

**Näytä lista käyttäjälle:**
```
SOITTOLISTA: [nimi]
Filosofia: Symphonic Poem | Moodit: expand | Lähteet: 4 APIa

PYLVÄÄT: Burial, Jon Hopkins, Boards of Canada, Brian Eno

 1. [AVAUS]    Burial — Archangel              [4.2p] lfm_similar(0.89) | Discogs(want=4821) ★★★
 2.            The Caretaker — It's Just...    [2.8p] lfm_low_match(0.21) ← VALO-EHDOKAS
 3.            Jon Hopkins — Open Eye Signal   [3.1p] lfm_similar(0.71) | tag:ambient
...
20. [VALO]     Arvo Pärt — Spiegel im Spiegel  [1.9p] lfm_low_match(0.18) | mb:influenced_by

Yhteensä: 20 kpl | Unresolved: 0
```

**STOP:** Kysy haluaako käyttäjä muokata ennen luontia.

---

## VAIHE 6 — LUO SPOTIFYSSA

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from curator.playlist_builder import PlaylistBuilder
from api.spotify import SpotifyClient

sp = SpotifyClient()
builder = PlaylistBuilder()

# Lisää kappaleet järjestyksessä
tracks = [
    ('ARTISTI1', 'KAPPALE1'),
    ('ARTISTI2', 'KAPPALE2'),
    # ...
]
for artist, title in tracks:
    builder.add_one(artist, title, source='final')

ranked = builder.rank()
uris = builder.resolve(sp, ranked)

unresolved = [c for c in ranked if not c.uri]
total = len(ranked)
unresolved_pct = len(unresolved) / total * 100 if total else 0

print(f'Resolved: {total - len(unresolved)}/{total} ({100-unresolved_pct:.0f}%)')
if unresolved:
    print('Unresolved:')
    for c in unresolved:
        print(f'  {c.artist} — {c.title}')
"
```

**STOP JOS unresolved > 20%:** Listaa kaikki unresolved kerralla. Ehdota:
- Vaihtoehtoinen kappale samalta artistilta
- Vaihtoehtoinen artisti samalla pisteellä
- Poistetaan listalta

Jos unresolved ≤ 20%: luo soittolista ilman kysymistä.

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from curator.playlist_builder import PlaylistBuilder
from api.spotify import SpotifyClient

sp = SpotifyClient()
builder = PlaylistBuilder()  # täytä resolved urit

# uris = [löydetyt uri:t järjestyksessä]
result = sp.create_playlist('SOITTOLISTAN NIMI', description='')
sp.add_tracks(result['id'], uris)
print('Soittolista valmis:', result['url'])
"
```

Ilmoita URL ja lyhyt yhteenveto: montako kappaletta, mistä lähteistä, kuinka monta unresolved.

---

## Muistettavaa

- Spotify = VAIN kohde + vältettävät (recently_played). Ei discovery.
- Discogs AINA taustalle — `search_background()` ei `search()`
- Matala Last.fm match (<0.3) = potentiaaliset valot, EI heikko signaali
- Symphonic Poem: huippu ei tarkoita kovaa. Intensiteetti = tuntuma, ei desibelit.
- Sama albumi max 1 kappale
