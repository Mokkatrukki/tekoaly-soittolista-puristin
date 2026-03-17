# /checkpoint

Päivitä LETSBUILD.md ja tee git commit tästä valmistuneesta osiosta.

## Ohjeet

1. Kysy käyttäjältä lyhyt kuvaus mitä tässä osiossa tehtiin (jos ei ole jo selvää kontekstista)
2. Päivitä `LETSBUILD.md` kohtaan **Valmiit osat** uusi merkintä muodossa:
   ```
   ### [YYYY-MM-DD] Osion nimi
   - mitä tehtiin
   - mitä tiedostoja luotiin/muutettiin
   - mahdolliset huomiot / tunnetut puutteet
   ```
3. Tee git commit kaikista muuttuneista tiedostoista. **Älä käytä Claude Code -attribuutiota** commit-viestissä.
   Commit-viesti muodossa: `feat: lyhyt kuvaus osiosta`
4. Ilmoita käyttäjälle mitä committiin meni ja muistuta että push on käyttäjän vastuulla.

## Tärkeää
- Ei `Co-Authored-By` -riviä
- Ei `--no-verify`
- Stage vain relevantit tiedostot, ei `.env`:iä
