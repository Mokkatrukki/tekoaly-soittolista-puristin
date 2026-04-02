# /tutki $ARGUMENTS

Musiikin tutkimustyökalu. Ei rakenna soittolistaa — seikkailee, löytää, kartoittaa.
Käytä kun tunnelma on epämääräinen, genre tuntematon, tai haluaa löytää jotain uutta.

`$ARGUMENTS` = valinnainen lähtöpiste: tunnelma, tilanne, genre, artisti tai "mitä tänään"

---

## Ennen kaikkea: lue genrekartta

Lue `curator/genre_map.md` ennen kuin ehdotat mitään suuntia.
Koko kenttä on käytössä — ei oletuksia genrestä etukäteen.

---

## VAIHE 1 — LÄHTÖPISTE

Jos `$ARGUMENTS` on annettu, käytä sitä suoraan.
Jos ei, kysy yksi kysymys: **"Minkälainen päivä tai tunnelma tänään?"**

Tunnista lähtöpisteen tyyppi:
- **Tunnelma/tilanne** ("melankolinen", "toimistotyö", "lenkki sateessa") → kartoita genre_mapista 3–5 suuntaa
- **Genre** ("haluaisin tutustua footworkiin") → sukella suoraan sinne
- **Artisti** ("Nick Cave -tyylistä mutta jotain uutta") → laajenna siitä
- **Avoin** ("en tiedä") → näytä laaja kartta, anna käyttäjän valita

**Älä kysy useita kysymyksiä.** Yksi kysymys tai suora ehdotus — sitten liikkeelle.

---

## VAIHE 2 — KARTOITUS

Aja relevantit haut lähtöpisteen mukaan. Valitse näistä:

### Last.fm — tagihaku (nopea, laaja)
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.lastfm import LastFmClient
lfm = LastFmClient()

tag = 'TAG'  # genre_mapista valittu tagi
artists = lfm.tag_top_artists(tag, limit=15)
tracks = lfm.tag_top_tracks(tag, limit=15)

print(f'=== {tag} — top artistit ===')
for a in artists:
    print(f'  {a.item.name}  ({a.weight} kuuntelijaa)')

print(f'\n=== {tag} — top kappaleet ===')
for t in tracks:
    print(f'  {t.item.artist} — {t.item.title}')
"
```

### Last.fm — similar_artists (kun artisti tiedossa)
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.lastfm import LastFmClient
lfm = LastFmClient()

artist = 'ARTISTI'
similar = lfm.similar_artists(artist, limit=20)
tags = lfm.artist_tags(artist, limit=8)

print(f'Tagit: {[t[\"tag\"] for t in tags]}')
print(f'\nSamankaltaiset:')
for a in similar:
    flag = ' ← MATALA (genrerajat)' if a.match < 0.3 else ''
    print(f'  {a.match:.2f}  {a.name}{flag}')
"
```

### Discogs — genre+style haku (laatu ja syvyys)
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.discogs import DiscogsClient
dc = DiscogsClient()

# Hae halutuimmat julkaisut genressä/tyylissä
results = dc._d.search(genre='GENRE', style='STYLE', sort='want', per_page=20, type='master')
items = list(results.page(1))

print(f'=== GENRE / STYLE — rakastetuimmat ===')
for item in items:
    data = item.data
    want = data.get('community', {}).get('want', 0)
    year = data.get('year', '?')
    styles = data.get('style', [])
    print(f'  [{year}] {data[\"title\"]}  want={want}  {styles}')
"
```

### YLE Areena — mitä soi nyt suomalaisessa radiossa
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.yle_areena import YleAreenaClient
areena = YleAreenaClient()

# Kokeile eri kanavia tilanteen mukaan
for show in ['yle_x3m', 'ylex', 'vinyylisalonki']:
    try:
        tracks = areena.latest_tracks(show, limit=10)
        if tracks:
            print(f'\n=== {show} ===')
            for t in tracks[:8]:
                print(f'  {t[\"artist\"]} — {t[\"title\"]}')
    except Exception as e:
        print(f'{show}: {e}')
"
```

### ListenBrainz — tuoreet julkaisut
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from api.listenbrainz import ListenBrainzClient
lb = ListenBrainzClient()

# Tuoreimmat julkaisut ListenBrainzin fresh_releases-datasta
try:
    releases = lb.fresh_releases(days=7, limit=20)
    print('=== Tuoreet julkaisut (7pv) ===')
    for r in releases[:15]:
        print(f'  {r.get(\"artist_credit_name\", \"?\")} — {r.get(\"release_name\", \"?\")}')
except Exception as e:
    print(f'LB fresh_releases: {e}')
"
```

---

## VAIHE 3 — ESITÄ LÖYDÖKSET

Ei ranked-listaa. Ei pisteitä. Kartta josta voidaan navigoida.

```
TUTKIMUS: [tunnelma/genre]
Lähteet: Last.fm | Discogs | [muut käytetyt]

LÖYDÖKSET:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tässä genressä/tunnelmassa:
  [Artisti 1] — tunnetuin, [lyhyt luonnehdinta tagien perusteella]
  [Artisti 2] — [luonnehdinta]
  [Artisti 3] — vähemmän tunnettu, kiinnostava
  ...

Rakastetuimmat levyt (Discogs want):
  [Levy 1] (vuosi) want=XXXX
  [Levy 2] (vuosi) want=XXXX

Nyt soi Areenassa:
  [Artisti — kappale]
  ...

Genrerajat (matala Last.fm match — yllättävät suunnat):
  [Artisti] — normaalisti [genre X], mutta nousee tästä hausta

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Minne haluaisit syventyä?
  A) [Artisti/suunta 1]
  B) [Artisti/suunta 2]  
  C) [Yllättävä suunta matalan matchin alueelta]
  D) Tästä soittolistaksi → /soittolista
```

---

## VAIHE 4 — SEIKKAILU (jatka käyttäjän valinnan mukaan)

Käyttäjä valitsee suunnan → aja lisähaut → näytä uusi kartta.

Voidaan toistaa rajattomasti. Ei tavoitetta, ei pakotettua lopetusta.

**Luonnolliset lopetukset:**
- Käyttäjä sanoo "tästä soittolistaksi" → ehdota `/soittolista [kuvaus]`
- Käyttäjä löysi mitä haki → yhteenveto löydöksistä
- Käyttäjä haluaa tallentaa löydökset → listaa artistit/genret selkeästi

---

## Muistettavaa

- Tämä ei ole soittolistan rakentamista — ei PlaylistBuilderia, ei Spotifyta, ei tavoitetta
- Matala Last.fm match (<0.3) ei ole heikko tulos — se on ovi ulos genrestä
- Discogs `want`-arvo kertoo rakkauden, ei suosion — harvinainen klassikko vs. hitti
- Areena kertoo mitä suomalainen musiikkikenttä tekee nyt
- Genre_mapissa on energiataso-osio — käytä sitä jos tunnelma on selvempi kuin genre
