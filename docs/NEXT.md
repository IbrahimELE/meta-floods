# Stanje i plan do predaje (27.10.2026. kasno navečer)

Predaja: **sri 4.11. 21:00 ET = čet 5.11. 03:00 CET**. Interni rok: **sri 4.11. 22:00 CET**.

## 1. Šta radi (testirano)

- **Pipeline fotografija:** SAM 3.1 (5 pojmova) → numerisane maske → Muse Spark 1.3 po objektu → prioritet
  po fiksnom pravilu. Dekodiranje maski sada 2× brže (keš validacije parsera).
- **Snimak s drona (NOVO):** SAM 3.1 **prati** kuće, ceste i vodu kroz klip → svaka kuća se broji jednom →
  ključni kadrovi idu kroz pipeline → klip s ucrtanim tragovima u panelu. Demo: Nagano 2019 (GSI, CC BY 4.0).
- **Glasovni izvještaj (NOVO):** snimi ili učitaj zvuk na mapi → Muse Voice Transcribe → Muse Spark Open
  izvlači cestu / ljude / opasnosti → kartica + marker, podiže prioritet zone, agent ga vidi. ~7 s.
- **Ceste i rute:** ručno potvrđene blokade (tačna OSM dionica), prijedlog rute koji ih izbjegava.
- **Agent:** zone, ±1 s dokazima, "molim provjeri", izvještaj EN + BS; zna za klipove i glasovne izvještaje.
- **Demo scenariji (3):** **Poplave BiH, maj 2014** (Zenica, Doboj, Prud – Commons, zasluge ispod svake
  fotografije), Nagano 2019 (drone), Kentucky 2022 (LADI).
- **Testovi:** 30 Python + preglednik: 26 provjera (`e2e_browser.js`), rute, glas (stvarni modeli),
  drone klip (stvarni modeli).

## 2. Iskrena procjena

Tehnički: jak projekat – četiri Meta modela (SAM 3.1 slike + video, Muse Spark 1.3, Muse Spark Open, Muse
Voice Transcribe) rade zajedno i svaki ima jasnu ulogu. Ostaje:

1. **Javni link** (U2 – Modal krediti). Bez njega žiri ne može probati.
2. **Dokaz korisnosti** (U3 – GSS / Civilna zaštita). Najveći mogući dobitak za Impact (30 %).
3. **Video** (U6) – scenarij je u `docs/video-script.md`.
4. Doboj fotografije su uglavnom "poslije poplave" i bez tačnog vremena → prioriteti su niski i to je
   pošteno prikazano ("nepoznata starost ≠ sigurno"). Najdramatičnije fotografije (srušene kuće) nemaju
   imenovano mjesto pa čekaju pin – i to je dio priče.

## 3. Šta možeš SAMO TI

| # | Zadatak | Kad |
|---|---|---|
| U2 | Modal krediti, zatim `modal token new` + `modal secret create firsthour-keys MODEL_API_KEY=... BASETEN_API_KEY=...` – javi i ja deployam | čim prije |
| U3 | Pošalji poruku iz `docs/poruka-gss.md` (dopuni link kad bude deploy; može i bez linka s videom/screenshotima) | sri 28.10. |
| U4 | Isprobaj aplikaciju (posebno glas i drone klip), zapiši šta smeta | ove sedmice |
| U5 | Pročitaj `docs/VODIC.md` – moraš moći braniti kod | do vikenda |
| U6 | Snimi glas za video po `docs/video-script.md` | pon–uto |
| U7 | Predaja, X objava, Community Vote | sri 4.11. |
| U8 | `git pull` u `E:\MetaHACK`; obriši folder `data\_to_delete` (stari arhivi) | odmah |

## 4. Šta radim ja

| Kad | Zadatak |
|---|---|
| sri 28.10. | E3 ponovo (brže dekodiranje), eval brojevi za video i glas u `docs/eval.md`; dorada UI-a (drone klip više na vrhu panela, mobilni prikaz). |
| čet–pet | Deploy čim stigne U2; test javnog linka (sandbox, glas, klip). Ispravke po U4. |
| sub–ned | Snimci ekrana i GIF-ovi za video, README završno. |
| pon 2.11. | **Feature freeze.** |
| uto 3.11. | Montaža materijala, provjera checkliste. |
| sri 4.11. | Predaja do 22:00. |
