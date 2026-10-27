# Plan – Rescue Map (Meta Global AI Developer Hackathon)

Predaja: **srijeda 4.11. u 21:00 ET = četvrtak 5.11. u 03:00 po našem vremenu.**
Cilj: predati u srijedu navečer, ne u 2 ujutro.

Vremenska razlika: do 31.10. ET je 5 sati iza nas, od 1.11. (u SAD-u se tada mijenja vrijeme) 6 sati.
Office hours (Discord, tekstualno): do petka 15–16h, od 2.11. 16–17h po našem vremenu.

## Šta žiri boduje → šta to znači za nas

| Kriterij | Težina | Šta radimo |
|---|---|---|
| Impact | 30% | Priča iz BiH + jasno "ko ovo koristi" (GSS, Civilna zaštita, vatrogasci) |
| Use of Meta AI | 25% | SAM i Muse Spark rade ZAJEDNO: Muse Spark ocjenjuje svaki SAM objekat po broju (#1, #2…). Plus agent s alatima, web_search za geolokaciju, Muse Spark Open, možda SAM video tracking |
| Tehnička dubina | 20% | Provjerljivost: svaka tačka na mapi → slika + maska + obrazloženje |
| Demo | 25% | Video od 3 min: prevučeš 30 slika, mapa se puni uživo, agent pokaže rutu |

Zabranjeno je "Simple Image Analyzer". Zato je centar priče **mapa, prioriteti i rute**, a ne klasifikacija pojedinačne slike.

## Arhitektura

```
slike / video (dron) ──► 1. INGEST
                          EXIF GPS? ── da ──► lokacija
                             └─ ne ──► Muse Spark + web_search (natpisi, mostovi, rijeka)
                                        └─ i dalje nesigurno ► ručni pin
                       ──► 2. SAM 3.1  (zgrada / cesta / most / poplavna voda → maske)
                       ──► 3. Muse Spark: original + overlay s brojevima
                             → po objektu: šteta (xBD skala), prohodnost, opasnosti, ljudi
                       ──► 4. AGENT (Muse Spark + alati)
                             grupiše nalaze u zone, prioritet 1–5, blokira neprohodne
                             dionice, računa sigurnu rutu, traži potvrdu čovjeka
                       ──► 5. WEB MAPA (Leaflet + OSM), uživo preko SSE
                             klik na tačku → slika, maska, obrazloženje, "potvrdi / odbaci"
```

Tehnologije (prijedlog): Python + FastAPI backend, Leaflet frontend,
`osmnx` + `networkx` za rute (OSM ceste, izbacimo blokirane dionice),
`@meta-sam/graphics` za crtanje maski u pregledniku.

## Plan po danima

| Dan | Šta | Gotovo kad |
|---|---|---|
| **Uto 27.10.** | Krediti stigli? `00_check_setup.py`. Skinuti 10–20 slika. Pokrenuti 01, 02, 03. **17:00 Agents 101.** Napraviti javni GitHub repo i prvi commit | Vidiš maske i JSON procjene za 10 slika |
| **Sri 28.10.** | Podesiti promptove na ~30 slika (koji SAM koncepti rade: "building" ili "damaged building"?). Pipeline kao modul. **17:00 Agents 102** (provjerljivi agenti, bitno!) | Pipeline obradi folder slika u JSON nalaze |
| **Čet 29.10.** | Geolokacija + FastAPI backend, nalazi → GeoJSON | Nalazi imaju koordinate |
| **Pet 30.10.** | Agent s alatima: `get_findings`, `cluster_zones`, `score_priority`, `block_road`, `plan_route`, `request_review`. **17:00 Fireworks sesija** | Agent iz nalaza složi zone i prioritete |
| **Sub 31.10.** | Frontend: mapa, drag & drop upload, uživo ažuriranje, panel s dokazima | Prevučeš slike, mapa se puni |
| **Ned 1.11.** | Rute (osmnx). Muse Spark Open backend preko Basetena (bonus Open Weight) | Ruta zaobilazi neprohodne ceste |
| **Pon 2.11.** | Demo scenarij + dorada. Ako ima vremena: video s drona → SAM praćenje | Cijeli demo radi od početka do kraja |
| **Uto 3.11.** | STOP za nove funkcije. Bugovi, deploy (link koji žiri može otvoriti), README, prva verzija videa | Live link radi |
| **Sri 4.11.** | Finalni video, predaja, objava na X | Predano do večeri |

Svaki dan commit na GitHub, jer historija commitova dokazuje da je sve rađeno tokom hackathona.

## Podaci (provjeriti licencu za SVAKI izvor prije upotrebe)

| Izvor | Šta je | Licenca | Za šta |
|---|---|---|---|
| **LADI v2** (MIT Lincoln Lab / Civil Air Patrol) | Kose fotografije iz zraka, katastrofe u SAD-u 2015–2023, uključujući poplave | **CC BY 4.0** (provjereno na registry.opendata.aws/ladi) | Glavni testni skup. `scripts/download_ladi_samples.py`. Provjeriti imaju li slike GPS |
| **Wikimedia Commons**, kategorija o poplavama u BiH 2024. (link je na Wikipediji, članak "2024 Bosnia and Herzegovina floods") i o poplavama 2014. | Prave fotografije iz BiH | Za svaku sliku posebno (obično CC BY-SA), navesti autora | Bosanski scenarij u videu |
| **Copernicus EMS** aktivacije EMSR770 (2024, vjerovatno Jablanica, provjeriti) i EMSR087 (2014) | Službene karte štete EU | Besplatno uz navođenje izvora, provjeriti uslove | Poređenje "naš sistem vs. službena karta" (jak trenutak za video!) |
| xBD / xView2 | Satelitski snimci prije i poslije, ocjene štete | Vjerovatno CC BY-NC-SA 4.0, provjeriti | Samo ako treba satelitski prikaz |
| Vlastite fotografije ili fotografije uz dozvolu | Npr. GSS ili Civilna zaštita | Pismena dozvola | Bonus: izjava spasioca u videu = ogroman Impact |

Ne koristiti: slike s društvenih mreža i iz medija bez dozvole (pravilo hackathona: diskvalifikacija).

## Najveći rizici

1. **Geolokacija** → testirati prvi dan (`03_test_geolocation.py`). Ako ne radi dobro: koristiti slike s GPS-om (LADI, dron), a ručni pin predstaviti kao funkciju, ne kao nedostatak.
2. **SAM na kosim fotografijama s poplavom**: ceste pod vodom se možda neće segmentirati kao "road". Testirati koncepte: "road", "flooded road", "street".
3. **Previše funkcija** → od utorka 3.11. ništa novo.
4. **Video**: 25% ocjene. Scenarij napisati već u ponedjeljak 2.11.

## Pitanja za Discord #office-hours

- Ima li SAM 3.1 ograničenje veličine slike ili broja objekata?
- Može li se SAM 3.1 pozvati s više koncepata u jednom zahtjevu (batch)?
- Računa li se za Open Weight nagradu ako je samo dio pipelinea na Muse Spark Open?
