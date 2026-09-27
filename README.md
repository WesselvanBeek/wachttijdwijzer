# Wachttijdwijzer GGZ

Een webapp met de wachttijden van GGZ-aanbieders rond Veenendaal. Een Python-script haalt de wachttijden elke ochtend van de websites van de aanbieders en bouwt de app opnieuw. Er is geen AI bij nodig.

```
data/aanbieders.json    aanbieders, vaste gegevens en per aanbieder de leesregels
data/wachttijden.json   de opgehaalde wachttijden (maakt het script zelf)
scraper/ophalen.py      het ophaalscript
app/template.html       de app, zonder gegevens
index.html              de app met gegevens (maakt het script zelf)
.github/workflows/      de automatische dagelijkse run op GitHub
```

## Eenmalig installeren op GitHub

1. Maak een account op [github.com](https://github.com) als je dat nog niet hebt.
2. Klik rechtsboven op **+** en kies **New repository**. Geef hem een naam, bijvoorbeeld `wachttijdwijzer-ggz`. Kies **Public** (GitHub Pages is gratis voor openbare repositories) en klik **Create repository**.
3. Klik op **uploading an existing file**. Sleep de **inhoud** van deze map erin, dus de mappen `app`, `data`, `scraper` en de losse bestanden. Klik **Commit changes**.
4. De map `.github` wordt door Windows vaak verborgen en dan niet meegesleept. Controleer of je repository een map `.github/workflows/ophalen.yml` heeft. Zo niet: klik **Add file → Create new file**, typ als naam `.github/workflows/ophalen.yml` en plak de inhoud van dat bestand erin.
5. Ga naar **Settings → Pages**. Kies bij **Source** de optie **GitHub Actions**.
6. Ga naar **Actions**, kies links **Wachttijden ophalen** en klik **Run workflow**. Na een tot twee minuten staat de site online.
7. Het webadres staat onder **Settings → Pages**, meestal `https://<jouw-gebruikersnaam>.github.io/wachttijdwijzer-ggz/`.

Daarna draait het script elke ochtend rond 6 uur vanzelf. Wil je tussendoor vernieuwen, klik dan in de app op **Nu vernieuwen** of in GitHub op **Actions → Wachttijden ophalen → Run workflow**.

GitHub zet geplande runs stil als er 60 dagen niets in de repository verandert. Omdat het script elke dag de datum bijwerkt, gebeurt dat hier niet.

## Wat doet het script bij een probleem?

Kan een leesregel een pagina niet meer lezen, bijvoorbeeld omdat de aanbieder zijn website heeft aangepast, dan:

- blijven de oude cijfers staan;
- krijgt de kaart in de app het rode label **Controle nodig**, met de reden erbij;
- staat de aanbieder in de samenvatting bovenaan de app.

Het script gokt nooit. Pas dan de leesregel aan (zie hieronder).

## Leesregels

Per aanbieder staan in `data/aanbieders.json` onder `regels` de leesregels voor:

| veld | betekenis |
|---|---|
| `aanm` | wachttijd van aanmelding tot intake |
| `beh` | wachttijd van intake tot behandeling |
| `videoAanm` | wachttijd tot intake via beeldbellen (optioneel) |
| `bijgewerkt` | datum waarop de aanbieder de pagina bijwerkte (optioneel) |

Het script zet elke pagina om naar losse tekstregels, zonder opmaak. Een leesregel werkt zo:

```json
"aanm": {"ankers": ["Intake volwassenzorg (BGGZ)", "Veenendaal"], "regels": 1}
```

- **ankers**: teksten die het script na elkaar zoekt. Een tekstregel moet met het anker **beginnen**. Begin je het anker met `~`, dan mag de tekst ook midden in de regel staan. Hoofdletters maken niet uit.
- **regels**: hoeveel regels na het laatste anker meetellen (0 = alleen de ankerregel zelf).
- Het script neemt de eerste wachttijd die het daar vindt, zoals `6 weken`, `10-12 weken`, `2 tot 3 maanden` of `twee weken`. Maanden worden omgerekend naar weken (× 4,33).
- Staat er vóór de wachttijd `aanmeldstop`, `aanmeldpauze`, `aannamestop` of `gesloten`, dan telt het als aanmeldstop.

Extra opties:

| optie | betekenis |
|---|---|
| `"nr": 2` | neem de tweede gevonden wachttijd in plaats van de eerste |
| `"kaal": true` | tel ook losse getallen zonder "weken" mee (voor tabellen die "in weken" in de kop hebben) |
| `"vanaf_nul": true` | "binnen 12 weken" wordt 0 tot 12 weken |
| `"url": "..."` | lees een andere pagina dan de `bron` van de aanbieder |
| `"zoek": "...", "vast": [0, 0]` | als deze tekst er staat, is de wachttijd de vaste waarde; staat hij er niet meer, dan volgt "controle nodig" |
| `"type": "regex_alle", "regex": "...", "groep": 1` | zoek met een reguliere expressie alle getallen en neem de laagste en hoogste (voor tabellen per verzekeraar) |
| `"regex": "..."` | bij `bijgewerkt`: de datum is groep 1 van deze reguliere expressie |

### Een leesregel testen op je eigen computer

Installeer [Python](https://www.python.org/downloads/) en open een opdrachtprompt in deze map:

```
pip install -r requirements.txt
python scraper/ophalen.py
```

Het script meldt welke regels veranderd zijn en welke een controle nodig hebben. Open daarna `index.html` in je browser. Met `python scraper/ophalen.py --alleen-bouwen` bouw je alleen de app opnieuw, zonder iets op te halen.

## Een aanbieder toevoegen

Voeg in `data/aanbieders.json` een blok toe met een unieke `id` en de vaste gegevens:

- `plaats` moet in de lijst `PLAATSEN` in `app/template.html` staan. Voeg een nieuwe plaats daar toe met haar coördinaten.
- `zorgvorm`: `"Basis GGZ"`, `"Specialistische GGZ"` of `null`.
- `doel`: lijst met `"Volwassenen"`, `"Jeugd"` en/of `"Ouderen"`, of `null`.
- `video`: `true`, `false` of `null` (niet vermeld).
- `contract`: `"alle"`, `"geen"`, `{"ja": ["CZ", ...]}` of `null` (niet vermeld). Met `stopVoor` geef je verzekeraars op waarvoor een aanmeldstop geldt.

Beeldbellen en contracten worden niet opgehaald, omdat ze zelden veranderen. Houd ze hier met de hand bij.

## Netjes ophalen

Het script haalt elke pagina één keer per dag op en maakt zich bekend als "Wachttijdwijzer-GGZ". Vraagt een aanbieder om te stoppen, haal die aanbieder dan uit `data/aanbieders.json`.
