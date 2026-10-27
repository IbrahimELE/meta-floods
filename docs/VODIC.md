# Vodič kroz kod (za odbranu pred žirijem)

Cilj: da za svaki dio aplikacije znaš **šta radi, zašto je tako napravljen i gdje je u kodu**.
Čitaj redom; svaki dio je 5–10 minuta.

## 1. Tok podataka u jednoj rečenici

Fotografija → `pipeline.py` (SAM 3.1 maske → numerisani overlay → Muse Spark procjena po objektu)
→ baza (`db.py`) → prioritet po fiksnom pravilu (`priority.py`) → zone i agent (`state.py`, `zones.py`, `agent.py`)
→ mapa uživo (`server.py` SSE → `static/app.js`).

Dodatni ulazi: **snimak s drona** (`video.py`), **glasovni izvještaj** (`voice.py`), **ručno potvrđene blokade
cesta** i **rute** (`server.py` + `static/routes.js`).

## 2. Fajlovi

| Fajl | Šta radi | Na šta paziti kad te pitaju |
|---|---|---|
| `app/config.py` | Sve postavke na jednom mjestu (pojmovi za SAM, limiti, budžet, putanje). | `FH_DATA_DIR`, `FH_ALLOW_DEV=0` na javnom deployu. |
| `app/db.py` | SQLite, **jedan pisac** (`tx()` s lockom), tabela `events` za SSE, snapshot nakon svakog commita (trajnost na Modalu). | Zašto SQLite: jedan proces, jednostavno, snapshot = backup API + atomski `os.replace`. |
| `app/api.py` | Pozivi Meta Model API-ja i Basetena; retry samo za prolazne greške; budžet se rezerviše **prije** poziva. | `final_text()` – kod web_search odgovora uzimamo zadnju poruku. |
| `app/sam.py` | Parsiranje SAM izlaza, maske (lokalne u boxu, štedi memoriju), spajanje building+house, poplavljene ceste, numerisanje, overlay. | **Keš dekodiranja maski**: parser dekodira masku da je provjeri pa je baci; mi taj rezultat ponovo koristimo → 2× brže. |
| `app/schema.py` | JSON shema za Muse Spark + `validate()` koja provjerava i da ID-jevi objekata postoje. | Model ne smije izmisliti objekat #17 ako ga SAM nije našao. |
| `app/pipeline.py` | Ingest (EXIF GPS/vrijeme), SAM po pojmu paralelno, dekodiranje u process poolu, procjena s 1 ponovnim pokušajem, objava na mapu. | Slika ide na mapu tek kad ima i procjenu i lokaciju. |
| `app/priority.py` | Bodovi → prioritet 1–5. Nepoznata ili stara fotografija = pola bodova. | **Model nikad ne postavlja prioritet.** |
| `app/state.py` | Sve što UI vidi, računato pri čitanju: zone, korekcije agenta (ističu ako se dokaz promijeni), blokade, glasovni izvještaji. | Zašto pri čitanju: nema "zaglavljenih" starih vrijednosti. |
| `app/zones.py` | Grupisanje u zone, ±1 korekcija s dokazima, zaključavanje od strane čovjeka. | Agent ne može dirati zaključanu zonu. |
| `app/agent.py` | Koordinator: Muse Spark 1.3 + 6 alata. Server validira svaki poziv; odbijeni pozivi su u logu. | Max 15 koraka / 120 s. Šalje cijelu historiju (bez `previous_response_id`). |
| `app/video.py` | Snimak s drona: normalizacija (5 fps, 1280 px, ≤30 s), **SAM 3.1 praćenje** kuća/cesta/vode, izbor ključnih kadrova, video s ucrtanim tragovima. | SAM prati najviše 16 objekata po kadru → piše "najmanje 16". |
| `app/voice.py` | Glas: WAV → Muse Voice Transcribe → Muse Spark Open izvlači stanje ceste, ljude, opasnosti. | Bosanski nije među 25 jezika ASR-a → izvještaji na engleskom. |
| `app/server.py` | FastAPI: rute, kontrola pristupa (demo samo za čitanje, privatni sandbox s kolačićem), SSE, pozadinski zadaci. | Javno: niko ne može mijenjati demo. |
| `app/static/app.js` | Mapa (Leaflet), lista, detalji, zone, agent, alati (ruta, blokada, glas), drone klipovi. | Sve se osvježava preko SSE događaja. |
| `app/static/routes.js` | OSM ceste preko Overpass API-ja, graf u pregledniku, Dijkstra koja izbjegava **samo ručno potvrđene** blokade. | AI "neprohodno" je samo upozorenje, nikad zatvaranje ceste. |
| `scripts/build_demo.py` | Pravi demo scenarij stvarnim modelima (fotografije, pinovi, zasluge, opcionalno drone klip, agent). | |
| `deploy/modal_app.py` | Modal: jedan kontejner, volumen, demo se kopira pri prvom startu. | `max_containers=1` jer SQLite ima jednog pisca. |
| `eval/` | E1 (oznake vs LADI), E2 (geolokacija), E3 (brzina). | Brojevi u `docs/eval.md`. |
| `tests/` | 30 Python testova + testovi u pregledniku (`e2e_*.js`). | |

## 3. Odluke koje treba znati odbraniti

1. **Zašto SAM prije Muse Sparka?** Maske su "rječnik": Muse Spark ne opisuje sliku općenito, nego objekat #3,
   koji ima tačan obris. Svaki nalaz se može provjeriti na pikselima.
2. **Zašto fiksno pravilo za prioritet?** Odgovornost. Spasilac mora znati zašto je zona prioritet 4.
   Agent smije predložiti ±1 samo s ID-jevima nalaza, i to ističe čim se dokaz promijeni.
3. **Zašto je AI geolokacija isključena?** E2: model je dao odgovor za 5 od 40 slika, i ti odgovori nisu bili
   dovoljno tačni. Pogrešna tačka na mapi je opasnija od fotografije bez tačke.
4. **"Nepoznato nije sigurno."** Zona bez procjene ide u posebnu listu, ne na dno.
5. **Video:** praćenje sprječava da ista kuća bude procijenjena 50 puta; ključni kadrovi su izabrani tako da
   zajedno pokažu sve praćene kuće.
6. **Glas:** izvještaj s terena je **ljudsko opažanje** i prikazan je drugačije od AI nalaza.
7. **Privatnost:** ljudi se samo broje kao "vidljivi / možda trebaju pomoć / ne vidi se", bez identifikacije.

## 4. Vjerovatna pitanja žirija

- *Šta ako model pogriješi?* → Svaki nalaz ima dugme Confirm/Reject; odbijen nalaz ne daje bodove, a agentova
  korekcija koja se na njega oslanja automatski ističe.
- *Koliko košta?* → SAM $2,50 / 1000 slika, Muse Spark ~$0,004 po slici, video $0,20 / 1000 kadrova.
  100 fotografija < $1.
- *Koliko je brzo?* → Prva slika na mapi ~15 s; 26 slika za ~1,5 min na 2 CPU jezgre (E3). Drone klip: brojevi za 16 s. Glas: 7 s.
- *Zašto ne satelit?* → Satelitske snimke stižu za dane; FirstHour je za prve sate, kad postoje samo
  fotografije građana i dronova.
- *Šta je novo tokom hackathona?* → Sve; vidi historiju commitova.

## 5. Kako pokrenuti lokalno

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
set FH_DATA_DIR=data\demo
uvicorn app.server:app --port 8000
```
Ključevi su u `.env` (nikad na GitHub). Za drone klipove treba `ffmpeg` u PATH-u.
