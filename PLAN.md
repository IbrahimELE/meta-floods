# PLAN – FirstHour (radni naziv)

```
PLAN_VERSION: v3 (FINAL)
STATUS: APPROVED
LAST_EDITED_BY: claude-planner (2026-10-27 18:05 CET) – finalizirano nakon Codex APPROVED
```

> **REVIEW PROTOCOL (for the reviewing model – please follow exactly)**
>
> 1. Read the whole plan. Do **not** edit sections 0–14 directly.
> 2. At the bottom, under `## 15. Review log`, add a heading `### Review of vN` (N = current PLAN_VERSION).
> 3. List findings as `- **RN-k** [blocker | major | minor] (section X.Y) – problem → suggestion`.
>    Focus on: factual errors (rules, deadlines, API facts), missing steps, unrealistic time estimates,
>    risks to judging criteria, contradictions. Also check whether earlier findings were really closed.
> 4. When done, change the status line at the top to `STATUS: REVIEW_DONE` and set `LAST_EDITED_BY` to your name + time.
> 5. If there are **no blocker or major findings left**, set `STATUS: APPROVED` instead.
> 6. The planner answers every finding under it (`→ v(N+1): accepted / partly / rejected because …`),
>    updates the plan, bumps the version and sets `STATUS: AWAITING_REVIEW` again.
> 7. Maximum 4 review rounds. After round 4 the planner finalizes.
> 8. Context: solo student, ~35 h total, 9 days. Prefer the simplest design that closes a risk over production-grade infrastructure.
>
> Plan je na bosanskom, tehnički pojmovi na engleskom.

**Promjene u v3:** E1 mjeri iste LADI oznake na obje strane (6.2); odvojena stanja obrade, lokacije i segmentacije (5.2); životni ciklus zona i zaključavanja (7.3); procedura trajnosti, atomski budžet i tajni sandbox token (5.5); `scenario_as_of`, nepoznata starost i `unassessed` zone (5.4, 7.2); dopune za edge ID, limit piksela i namjenu rezerve (5.3, 5.5, 8). Testovi T8–T12.

---

## 0. Sažetak

Nakon poplave ili zemljotresa spasioci dobiju stotine fotografija (građani, dronovi, društvene mreže), a nemaju brz način da ih pretvore u sliku stanja na terenu. **FirstHour** prima te fotografije. **SAM 3.1** segmentira vidljive kandidate (zgrade, ceste, mostove, poplavnu vodu; segmentacija može propustiti objekte). **Muse Spark** ocjenjuje štetu i prohodnost **za svaki segmentirani objekat po broju maske**, pa je svaka tvrdnja vezana za konkretan dio fotografije. **Agent** spaja nalaze u zone na mapi, predlaže prioritet koji server računa po fiksnoj formuli, šalje nesigurne nalaze na ljudsku provjeru i piše izvještaj za komandu. Rezultat je mapa uživo: gdje prvo pomoći, koje ceste su **evidentirano** blokirane ili prohodne, i šta još nije provjereno. Sistem je podrška odlučivanju, a lokacije koje je predložio AI ostaju prijedlog dok ih čovjek ne potvrdi.

Motivacija: poplave u BiH 2014. i poplave i klizišta 3./4.10.2024. (prema Wikipediji 27 mrtvih, od toga 19 u općini Jablanica, najviše u Donjoj Jablanici; putevi, mostovi i pruga presječeni; izvor u sekciji 14, brojke prije videa provjeriti u primarnom izvoru).

## 1. Pravila i rokovi

Izvori: `docs/reference/participant-guide.txt` (kopija stranice događaja, 26.10.), `docs/reference/credit-terms.txt`, `docs/reference/acceptable-use-policy.txt`. Folder je lokalni i u `.gitignore`. U zagradi je linija ili sekcija izvora.

| Stavka | Vrijednost |
|---|---|
| Događaj | 26.10. (kickoff) – 4.11. (credit-terms, l. 6); **building period 27.10. – 4.11.** (guide, l. 92) |
| **Predaja** | **4.11. 21:00 ET** (guide l. 83, 193) = **5.11. 03:00 CET**. **Interni rok: 4.11. 22:00 CET** (5 h rezerve) |
| Track / problem statement | Indie Developer (solo) / Build for Your World (guide sekc. 1, 9) |
| Obavezno | Javni repo; video od **3 min** koji pokazuje samo rad s hackathona (guide l. 203); jasno označen novi rad (guide l. 101) |
| Zabranjeno | "Simple Image Analyzers", "Basic RAG", sve vezano za rat/politiku, medicinski savjeti (guide l. 106); podaci bez prava (guide sekc. 4) |
| AUP | Ljudski nadzor za posljedične akcije, objava ograničenja, bez identifikacije osoba, bez predstavljanja AI izlaza kao ljudskog (AUP) |
| Ocjenjivanje | Impact 30 · Meta AI 25 · Tehnika 20 · Demo 25 (guide sekc. 8) |
| Bonusi | Best Agentic, Best Open Weight (Muse Spark Open preko partnera), Community Vote, Most Viral (guide sekc. 9) |

**Postojeći kod (iskreno evidentiranje):** test skripte u `scripts/` i `docs/api-notes.md` napravljene su **26.10. navečer, nakon kickoffa**, dakle tokom događaja, ali dan prije zvaničnog building perioda. README to navodi eksplicitno. Historija se ne mijenja.

Vremenska razlika: do 31.10. ET = CET − 5 h, od 1.11. ET = CET − 6 h. Live sesije u 17:00 CET: Agents 101 (27.10.), **Agents 102 – verifiable agents (28.10.)**, Fireworks (30.10.).

## 2. Resursi

| Resurs | Stanje | Upotreba |
|---|---|---|
| Meta Model API | $150 aktivno, krediti ne ističu (credit-terms 3.5) | `sam-3.1`, `muse-spark-1.3` (agent, geolokacija) |
| Baseten | $100 + 2M TPM | Muse Spark Open (`meta-models/muse-spark-open-1026`) |
| Modal | $100 | Hosting demoa |
| Vrijeme | Student | **Pretpostavka ≈ 35 h** (31 h rad + 4 h rezerve), još nije potvrđeno (13.1) |

Trošak: SAM $2,50 / 1000 zahtjeva, Muse Spark 1.3 $1,25 / $4,25 po 1M tokena (`docs/api-notes.md`, izvor dev.meta.ai/docs/pricing-rate-limits). Cijeli razvoj i eval procijenjen je na < $25.

**Privatnost podataka:** Billing stranica na dev.meta.ai je 27.10. prikazala tekst *"While using free credits your content may be used for product improvement."* (snimak ekrana u razgovoru s korisnikom). To odstupa od opšteg opisa Standard moda u dokumentaciji, pa je to vjerovatno poseban uslov za besplatne kredite. **Posljedica:** u razvoju i demou koristimo samo javne, licencirane slike, a javni upload upozorava da se slike šalju Meti i Basetenu (5.5).

## 3. Korisnici i problem

- **Primarni korisnik:** koordinator spašavanja (GSS, Civilna zaštita, vatrogasci) u prvim satima.
- **Problem:** stotine nestrukturiranih fotografija bez lokacije i prioriteta, koje se pregledaju ručno.
- **Mjerljivi ciljevi (E3, 6.2):** p50 < 30 s od uploada do potpuno obrađenog nalaza (warm); batch od 30 slika obrađen za < 3 min.

## 4. Obim

### 4.0 Minimalni rezervni obim (ako do subote 31.10. u 20:00 nešto kasni)

Upload → SAM → procjena po objektu → **ručni pin** za lokaciju (bez automatske geolokacije) → mapa s nalazima → panel s dokazima → agent **na dugme**, bez automatskog spajanja duplikata i bez ruta. Ovaj obim je dovoljan za predaju i za video.

### 4.1 MUST (cilj: do nedjelje 1.11.)

1. Upload više slika (drag & drop), validacija (5.5).
2. **Lokacija prema modelu iz 5.3:** EXIF GPS kamere → AI prijedlog → ručni pin; izvor i nesigurnost su uvijek vidljivi.
3. SAM 3.1 segmentacija (koncepti nakon E4).
4. Procjena po objektu (strukturisani JSON + semantička validacija, 5.2).
5. Mapa uživo (Leaflet + OSM, SSE).
6. Panel s dokazima: fotografija, maske, nalazi, izvor lokacije; **Potvrdi / Odbaci / Ispravi lokaciju**.
7. Agent (7): zone, prijedlog prilagodbe prioriteta, ljudska provjera, izvještaj; agent log s dokazima.
8. Oznake u UI: "AI procjena – provjeriti na terenu"; "lokacija: kamera / AI prijedlog / potvrđeno".

### 4.2 SHOULD (samo ako je MUST gotov)

1. **Prijedlog rute** koji izbjegava **ručno potvrđene** blokade (5.3); nepoznate dionice nisu označene kao prohodne.
2. Muse Spark Open kao zadani backend, ako prođe kriterij iz 6.2 E1.
3. Izvještaj na bosanskom i engleskom.
4. Eval brojevi u README i videu.

### 4.3 COULD

SAM praćenje na videu s drona; glasovni izvještaji (Muse Voice Transcribe); poređenje s Copernicus EMS kartom.

### 4.4 NE radimo

Login, mobilnu aplikaciju, scraping društvenih mreža, prepoznavanje lica, trening modela, satelitske snimke, automatsko blokiranje cesta na osnovu AI lokacije.

## 5. Arhitektura

```
[Preglednik: Leaflet + upload + panel + agent log]
   │ POST /incidents/{id}/images      ▲ SSE /incidents/{id}/events (id = event_seq)
   ▼                                  │ GET /incidents/{id}/snapshot?after=seq
[FastAPI, JEDAN proces = jedini pisac u bazu]
   ├─ jobs tabela (trajna) + asyncio radnici (max 8 paralelno, po fazi semafor)
   ├─ faze: ingest → locate → segment → assess → done
   └─ agent run (na dugme ili nakon svakih 10 novih nalaza; jedan run istovremeno po incidentu)
[SQLite, WAL] – svi upisi kroz jedan async lock (serijalizacija)
```

### 5.1 Model podataka i ID-jevi

| Tabela | Ključna polja |
|---|---|
| `incidents` | `id`, `name`, `region_text`, `region_bbox`, `created_at`, `mode` (`demo_readonly` / `sandbox` / `dev`) |
| `images` | `id` (uuid), `incident_id`, `sha256` (dedup), `captured_at` (EXIF ili `null` = nepoznato), `uploaded_at`, `camera_lat/lon` (EXIF), `viewpoint`, `processing_state`, `stage`, `location_state`, `segmentation_state`, `published` (bool) |
| `locations` | `image_id`, `kind` (`camera_exif` / `ai_scene_estimate` / `human_pin`), `lat`, `lon`, `uncertainty_m`, `source_detail`, `confirmed_by_human` (bool), `created_at` |
| `objects` | `id` = `{image_id}:{n}` (n = broj na overlayu), `concept`, `box`, `sam_confidence`, `mask_path` |
| `findings` | `id`, `image_id`, `object_id` (ili `null` za nivo scene), `damage`, `passability`, `hazards`, `people_visible` i `people_may_need_help` (**nullable boolean**: `true` / `false` / `null` = ne može se procijeniti), `self_confidence`, `evidence_text`, `model`, `revision` |
| `image_labels` | `image_id`, LADI oznake na nivou slike (6.2 E1), samo za evaluaciju |
| `reviews` | `id`, `finding_id` ili `location_id`, `action` (`confirm` / `reject` / `correct`), `value`, `created_at` – **ljudska odluka ima prednost i agent je ne može mijenjati** |
| `zones` | `id`, `incident_id`, `revision`, `member_image_ids`, `base_priority`, `agent_adjustment`, `human_priority` (opcionalno, zaključava), `reason`, `evidence_ids` |
| `agent_actions` | `id`, `run_id`, `tool`, `args`, `result` (`applied` / `rejected:<razlog>`), `created_at` |
| `jobs` | `image_id`, `stage`, `attempts`, `api_calls_used`, `last_error`, `updated_at` |
| `budget` | `day`, `images_reserved`, `agent_runs_reserved`, `api_calls_reserved` (trajno, 5.5) |
| `sessions` | `token_hash`, `incident_id`, `created_at`, `expires_at` (sandbox, 5.5) |

Enum vrijednosti su iste kao u JSON shemi u `scripts/02_test_muse_spark.py`, plus `unknown` svugdje gdje se ne vidi.

### 5.2 Stanja i greške (dopunjeno u v3, R2-2)

Četiri **nezavisna** polja na slici umjesto jednog lanca:

| Polje | Vrijednosti | Značenje |
|---|---|---|
| `processing_state` | `queued` / `running` / `done` / `failed` | Obrada modelima (segmentacija + procjena) |
| `stage` | `ingest` / `segment` / `assess` | Faza u kojoj je `running` ili `failed` |
| `location_state` | `pending` / `proposed` (AI) / `camera` (EXIF) / `confirmed` (čovjek) / `needs_pin` | Lokacija se radi **paralelno** s obradom |
| `segmentation_state` | `pending` / `objects` / `no_objects` | `no_objects` = SAM ništa nije našao; procjena ostaje na nivou scene, objekti se ne izmišljaju |

- **Objava na mapi:** `published = processing_state == done AND location_state ∈ {camera, proposed, confirmed}`. Slika s `done` i `needs_pin` čeka u listi "Treba lokaciju". **Ručni pin nakon završene procjene samo postavlja `location_state = confirmed` i objavljuje nalaz, bez ponovnih API poziva.** Kombinacija "bez lokacije + bez objekata + uspješno procijenjena" je validna.
- **Retry:** za 429, 5xx i timeout najviše 3 ponovna pokušaja po pozivu (backoff 2/8/30 s + jitter), a **svaki pokušaj rezerviše budžet** (5.5). Za 400 nema retryja.
- **Vremenski budžeti po pozivu:** SAM 60 s po konceptu, procjena 90 s, geolokacija 90 s.
- **Validacija procjene:** JSON shema + semantika (ID-jevi objekata ⊆ SAM lista, bez duplikata, `confidence` ∈ [0,1], `passability = not_applicable` za zgrade). Nevalidan odgovor dobije 1 ponovni pokušaj s porukom o grešci, a zatim `failed`, `stage = assess`, `last_error = invalid_output`.
- **Oporavak pri startu:** svaka slika s `processing_state = running` vraća se u `queued` (pokušaji + 1, max 3), **bez obzira na `location_state`**. Lokacijski poslovi u `pending` se ponovo pokreću, a `confirmed` lokacije se nikad ne diraju.
- **Agent:** max 15 koraka, 120 s i 1 run po incidentu istovremeno; na limitu `run_status = incomplete`, validne akcije ostaju.

### 5.3 Model lokacije (zatvara R1-1)

1. **Lokacija kamere ≠ lokacija objekta.** EXIF GPS je pozicija kamere. Na kosim snimcima iz zraka objekti mogu biti stotine metara dalje.
2. Svaka slika ima jednu **lokaciju prizora** s izvorom i nesigurnošću:
   - `camera_exif`: tačka kamere, `uncertainty_m` = 300 za kose i 50 za nadir/tlo (pretpostavka, prilagoditi nakon E2);
   - `ai_scene_estimate`: prijedlog modela s njegovom preciznošću (`street` = 200 m, `neighborhood` = 1 km, `town` = 5 km);
   - `human_pin`: korisnik klikne na mapu; `confirmed_by_human = true`.
3. **Na mapi se crta krug nesigurnosti, ne samo tačka.** AI lokacija je isprekidana i nosi oznaku "prijedlog".
4. **Spajanje duplikata:** agent samo **predlaže** "možda isti objekat" (`request_human_review`). Automatskog spajanja po blizini kamera nema.
5. **Ceste i rute (SHOULD):** nalaz "neprohodno" utiče na rutu **samo ako ga čovjek poveže s dionicom**. Klikom na cestu sprema se konkretan edge grafa `(u, v, key)` i **smjer**: korisnik bira "oba smjera" ili jedan, a UI prikazuje strelicom šta je blokirano. `osm_way_id` se čuva samo kao informacija. Nepotvrđeni nalazi su upozorenje i ne mijenjaju graf.
6. **Test:** nalaz `impassable` s AI lokacijom i bez ljudske veze ne mijenja rutu (12.2, T4).

### 5.4 Vrijeme, incident, konflikti (dopunjeno u v3, R2-5)

- Svaka slika pripada **jednom incidentu**; mapa prikazuje jedan incident.
- **Referentno vrijeme incidenta `as_of`:**
  - sandbox / stvarna upotreba: `as_of = sada`;
  - **historijski demo scenarij** (LADI, Jablanica): fiksni `scenario_as_of` (npr. 2024-10-04 12:00 za Jablanicu), uz traku u UI **"Historijski scenarij – stanje na <datum>"**. Replay je zato reproducibilan, a historijski dokazi se ne prepolovljavaju zbog današnjeg datuma.
- **Starost nalaza** = `as_of − captured_at`:
  - `captured_at` poznat i starost ≤ 12 h → puna težina;
  - starost > 12 h → oznaka "staro", bodovi × 0,5 (naniže);
  - **`captured_at` nepoznat → "starost nepoznata"**: bodovi × 0,5 i automatski `request_human_review` ("potvrdi da je snimak aktuelan"). **`uploaded_at` se nikad ne koristi kao vrijeme snimka.**
- **Konflikt:** dva nalaza za isti potvrđeni objekat ili dionicu s različitim statusom → važi noviji ljudski potvrđen, a bez potvrde se prikazuju oba i otvara se provjera.
- **`unknown` / `null` nije negativan dokaz.** Izvještaj ima obaveznu sekciju "Nije provjereno".
- Ruta se zove "prijedlog koji izbjegava evidentirane blokade".

### 5.5 Deploy i javni link (dopunjeno u v3, R2-4, R2-6b)

**Trajnost: jedna procedura za SVE potvrđene mutacije** (završen posao, ljudska potvrda/pin, agent akcija, rezervacija budžeta, nova sesija):
1. upis u radnu SQLite bazu na lokalnom disku kontejnera, u jednoj transakciji pod globalnim async lockom (serijalizovano);
2. `sqlite3.Connection.backup()` u fajl na Modal Volume (konzistentan snapshot, nikad kopiranje otvorene baze);
3. `volume.commit()`;
4. **tek tada** server vraća uspjeh klijentu, odnosno šalje SSE event.

Pri startu se baza vraća iz posljednjeg snapshota na Volume. Pri malom obimu demoa (desetine mutacija u minuti) trošak je prihvatljiv. Ako bude spor, mutacije se grupišu u prozor od 1 s, ali uspjeh se i dalje javlja tek nakon koraka 3.

- **Modal:** tačno jedan kontejner (`max_containers=1`), konkurentnost unutar procesa.
- **SSE:** svaki event ima `event_seq` (u bazi); `Last-Event-ID` ili `/snapshot?after=seq` za ponovno povezivanje.
- **Režimi:**
  - `demo_readonly`: unaprijed obrađen historijski scenarij (5.4); sve mutacije vraćaju 403.
  - `sandbox`: server izdaje **tajni token sesije** (32 nasumična bajta, HttpOnly cookie, u bazi samo hash). Incident je vezan za token, a **svako čitanje i pisanje** (slike, maske, SSE, snapshot, review, agent) provjerava token. ID incidenta sam po sebi ne daje pristup. Sesija ističe za 24 h, a uploadi se tada brišu.
- **Globalni dnevni budžet, atomski i trajan:** prije **svakog** API poziva (uključujući retry) u istoj transakciji se provjerava i povećava brojač u tabeli `budget` (limiti: 150 slika, 30 agent runova, 1500 API poziva dnevno za sve posjetioce). Ako je limit pun, server vraća 429. Rezervacija prolazi kroz proceduru trajnosti, pa restart ne resetuje potrošnju. Nova sesija ne dobija novi budžet.
- **Validacija slike prije dekodiranja:** veličina fajla ≤ 15 MB; `Image.open()` čita samo header, a ako je `width × height > 40 MP`, slika se odbija **prije** `load()`. Dodatno `Image.MAX_IMAGE_PIXELS = 40_000_000`. Zatim slijedi dekodiranje, smanjivanje na ≤ 1600 px i uklanjanje EXIF-a iz sačuvane kopije nakon čitanja GPS-a i vremena.
- Upload forma upozorava da se slike šalju Meta Model API-ju i Basetenu na obradu.
- **Rani smoke test deploya u petak 30.10.:** deploy → upload → potvrda → **restart odmah nakon potvrde** → potvrda i potrošnja budžeta ostaju.

## 6. Podaci i evaluacija

### 6.1 Izvori (licence u `DATA_SOURCES.md` prije upotrebe)

| Izvor | Licenca | Upotreba |
|---|---|---|
| **LADI v2** (MIT LL / Civil Air Patrol), labele `Labels/v2/ladi_v2_labels_*.csv` (**v2, ne v2a**) | CC BY 4.0 (registry.opendata.aws/ladi) | Razvoj i eval |
| Wikimedia Commons – poplave BiH 2024 i 2014 | Po fajlu, autor obavezno | Scenarij Jablanica |
| Copernicus EMS (EMSR770 / EMSR087 – provjeriti) | Provjeriti | COULD |

Podjela LADI v2:
- **Smoke set** = 25 slika u `samples/ladi_dev_set.csv` (iz test splita; samo za provjeru da sve radi, ne za podešavanje).
- **Tuning set** = 40 slika iz `ladi_v2_labels_val.csv` (podešavanje promptova i koncepata).
- **Test set** = 100 slika iz `ladi_v2_labels_test.csv` **bez smoke seta i bez slika iz istih letova (folder `A00xx`) kao smoke set**. Slučajan izbor sa seed = 42 i stratifikacijom po `flooding_any`.

### 6.2 Evaluacija

**E1 – kvalitet na nivou slike (dopunjeno u v3, R2-1).** Obje strane mjere **isti događaj**: procjena dobija poseban blok `image_labels` u istom pozivu (bez dodatnog troška), u kojem model direktno odgovara na LADI oznake na nivou slike. Blok je **odvojen** od xBD štete po objektu i od prohodnosti, koji se ne porede s LADI-jem.

| Klasa (fiksni skup) | LADI v2 strana | Naša strana (`image_labels`) |
|---|---|---|
| `flooding_any` | `flooding_any` | isto ime, definicija: "poplavna voda vidljiva bilo gdje na slici" |
| `flooding_structures` | `flooding_structures` | "poplavna voda dodiruje ili okružuje zgrade" |
| `buildings_affected_or_greater` | `affected ∨ minor ∨ major ∨ destroyed` (eksplicitna unija, ista kao v2a) | "vidljiva bilo kakva šteta na zgradi" |
| `buildings_major_or_greater` | `major ∨ destroyed` | "teška šteta ili uništena zgrada (FEMA major/destroyed)" |
| `roads_damage` | `roads_damage` | "vidljivo oštećenje ceste (urušen, odnesen ili ispucan kolovoz, krhotine na kolovozu)" – **ne** prohodnost |
| `debris_any` | `debris_any` | "vidljive krhotine" |

Napomena: LADI rad formalno definiše samo FEMA nivoe štete na zgradama. Za ostale klase gornje definicije su naša operativna tumačenja i to se navodi kao ograničenje.
- **Makro-F1** se računa samo nad klasama s **≥ 10 pozitivnih primjera** u test setu. Ostale klase se prijavljuju zasebno (P/R, broj primjera), bez ulaska u makro-F1. `bridges_damage` je isključen (u v2a uklonjen zbog premalo primjera).
- Metrike: P/R/F1 po klasi + broj pozitivnih primjera; neodgovor se računa kao 0 i posebno broji. Poredi se Muse Spark 1.3 i Muse Spark Open.
- **Kriterij izbora backenda:** Open postaje zadani ako je makro-F1 ≥ (1.3 − 0,05), validan JSON ≥ 98% i p95 latencija ≤ 1,5 × 1.3.

**E1b – provjera na nivou objekta:** 20 slika iz tuning seta, ručni pregled (vremenski ograničen na 1 h): je li ID maske ispravno povezan s opisom, je li dokaz tačan i je li `unknown` korišten kad treba. Ograničenje: jedan anotator, bez mjerenja slaganja.

**E2 – geolokacija:** mjeri se **lokacija kamere** (jedini dostupni ground truth; zbog 5.3 to nije lokacija objekta).
- 40 slučajnih slika s GPS-om iz test seta (provjeriti da LADI v2 slike imaju EXIF GPS; ako nemaju, uzeti GPS iz `Labels/ladi_images_metadata.csv`);
- slike se re-enkodiraju **bez ikakvih metapodataka** i preimenuju u nasumičan ID;
- regija se zadaje na nivou države ili okruga događaja (npr. "Vermont, USA"), nezavisno od pojedinačne slike;
- baseline: centar regije;
- izvještaj: broj pokušaja, coverage (koliko puta je model dao koordinatu), medijan i p90 greške za odgovore, % **svih** pokušaja unutar 1 km i 5 km. Svi rezultati se označavaju kao "web-assisted", jer se koristi `web_search`.
- **Pravilo odluke:** ako je < 30% svih pokušaja unutar 5 km, zadani tok postaje **ručni pin**, a AI prijedlog samo pomoćna opcija. To se radi već u četvrtak 29.10.

**E3 – brzina:** vrijeme od uploada do stanja `done`, p50/p95 po slici, batch od 30 slika ukupno, posebno cold start (prvi zahtjev nakon deploya) i warm.

**E4 – SAM koncepti:** na 20 slika iz tuning seta uporediti `road` / `street` / `flooded road` i `building` / `house` / `damaged building` (ručni pregled overlaya, 45 min).

Rezultati idu u `docs/eval.md`. Brojevi u videu samo ako su izmjereni.

## 7. Agent

### 7.1 Alati

**Model:** `muse-spark-1.3`, Responses API, `reasoning.effort = high`, limiti iz 5.2.

| Alat | Validacija na serveru |
|---|---|
| `get_findings(zone_id?)` | Samo tekući incident |
| `cluster_zones(radius_m ∈ [100, 2000])` | Deterministički kod (DBSCAN na lokacijama prizora, potvrđene lokacije imaju prednost); nova `revision` zona |
| `adjust_zone_priority(zone_id, zone_revision, delta ∈ {−1, 0, +1}, reason, evidence_ids)` | Revizija mora biti aktuelna; svi `evidence_ids` postoje i pripadaju toj zoni; zona s `human_priority` se **odbija**; isti poziv dva puta = isti rezultat (idempotentno) |
| `flag_possible_duplicate(finding_ids, reason)` | Samo otvara ljudsku provjeru, ne spaja ništa |
| `request_human_review(target_id, question)` | – |
| `write_briefing(language ∈ {bs, en})` | Briefing se generiše iz stanja baze: top 5 zona, potvrđene blokade, opasnosti, sekcija "Nije provjereno" |

**Svi** alati (uključujući `flag_possible_duplicate` i `request_human_review`) provjeravaju da svaki ID pripada tekućem incidentu. Agent **nema** alat koji mijenja ljudske potvrde ni lokacije. Sve akcije, i odbijene, idu u `agent_actions`.

### 7.2 Prioritet – deterministička funkcija (računa server)

Bodovi slike `P(image)`, za nalaze koji nisu odbijeni:
- `people_may_need_help = true` → **+3**
- najgora šteta zgrade: `destroyed` **+2**, `major` **+1**
- voda: `waist` / `above_waist` **+1**, `roof_level` **+2**
- opasnosti iz {`collapse_risk`, `landslide`, `fast_current`, `downed_power_lines`, `deep_water`}: **+1** svaka, najviše **+2**
- `unknown` daje 0
- zastario nalaz (5.4): bodovi × 0,5, zaokruženo naniže

Bodovi zone: `Z = max(P)` po slikama u zoni (max umjesto sume, pa duplikati ne napuhuju rezultat) **+1** ako zona ima ljudski potvrđenu neprohodnu dionicu.
Mapiranje: `Z = 0 → 1`, `1–2 → 2`, `3–4 → 3`, `5–6 → 4`, `≥ 7 → 5`.
Konačno: `human_priority` ako postoji, inače `clamp(base + agent_delta, 1, 5)`.

Primjeri:
| Ulaz | Z | Prioritet |
|---|---|---|
| 1 slika: voda do struka, major zgrada | 2 | 2 |
| ljudi možda trebaju pomoć + destroyed + klizište | 6 | 4 |
| isto + potvrđena neprohodna dionica | 7 | 5 |
| samo `unknown` / `null` | – | **`unassessed`** (vidi ispod) |

**`unassessed` zone (R2-5):** zona u kojoj nijedan nalaz nema procjenjiv dokaz (sve `unknown` / `null`, `no_objects` bez procjene scene ili `failed`) dobija `priority = null` i status `unassessed`. Takve zone su **uvijek** prikazane u zasebnoj listi "Za provjeru" iznad rang-liste, posebnom bojom na mapi i u obaveznoj sekciji izvještaja "Nije provjereno". Nikad ne ulaze u rang kao nizak prioritet i ne mogu ispasti iz top 5.

`self_confidence` iz modela prikazuje se kao "samoprocjena modela", a ne kao kalibrisana vjerovatnoća.

### 7.3 Životni ciklus zona (R2-3)

- **Zaključavanje:** kad čovjek postavi `human_priority`, zona postaje `locked`: **članstvo je zamrznuto**. `cluster_zones` ne može dodati, ukloniti ni premjestiti njene slike. Nove slike u blizini idu u nove ili nezaključane zone, a UI predlaže "dodaj u zaključanu zonu?", što čovjek odobrava.
- **Svaka relevantna promjena** (članstvo zone, pin ili ispravka lokacije, potvrda ili odbijanje nalaza, novi nalaz u zoni): server ponovo računa `base_priority`, povećava `revision` i **poništava `agent_delta`** ako se bilo koji njegov `evidence_id` promijenio, odbijen je ili više nije u zoni. Briefing generisan prije te revizije označava se "zastario" (dugme "Regeneriši").
- **Odbijen nalaz** odmah prestaje doprinositi bodovima, uključujući doprinos kroz agentovu korekciju.
- Otključavanje zone radi samo čovjek.


## 8. Raspored (35 h = 31 h rada + 4 h rezerve)

| Dan | h | Zadaci | Gotovo kad |
|---|---|---|---|
| **Uto 27.10.** | 3 | ✅ krediti, setup, `00`. Preuzeti smoke set; pokrenuti 01–03. Javni GitHub repo + prvi commit (README navodi kod od 26.10.) | Maske i JSON za 10 slika |
| **Sri 28.10.** | 3 | E4 + preuzeti tuning set; Baseten test; 17:00 Agents 102 | Koncepti odabrani, oba backenda rade |
| **Čet 29.10.** | 3 | Pipeline modul + SQLite shema (5.1) + stanja i retry (5.2). **E2 geolokacija → odluka** | Folder → nalazi u bazi; odluka o pinu |
| **Pet 30.10.** | 3 | FastAPI: upload, SSE + snapshot, incident. **Modal smoke test** (deploy + restart) | Lokalni API + prazan deploy radi |
| **Sub 31.10.** | 7 | Frontend: mapa, upload, krugovi nesigurnosti, panel, potvrde, ručni pin. **20:00 provjera → 4.0 ako kasni** | Prevučeš slike → mapa se puni |
| **Ned 1.11.** | 7 (5 + 2 rezerve) | Agent + alati + validacija + log + briefing; E1 u pozadini | **MUST kompletan** |
| **Pon 2.11.** | 3 (2 + 1 rezerva) | Testovi prihvatanja (12.2); scenarij Jablanica (licence, pinovi); scenarij videa | Demo radi od početka do kraja |
| **Uto 3.11.** | 3 (2 + 1 rezerva) | **Feature freeze.** Pun deploy, režimi i budžet (5.5), README, `DATA_SOURCES.md`, snimanje | Live link radi |
| **Sri 4.11.** | 3 | Montaža, checklista, **predaja do 22:00**, X objava | Predano |

Zbir: 3+3+3+3+7+7+3+3+3 = **35 h**. **Rezerva od 4 h služi prvo za kvarove, popravke i testove prihvatanja.** SHOULD stavke (rute, Open kao zadani, dva jezika) rade se samo iz stvarnog viška vremena, **nakon što MUST testovi (12.2) prođu**.

Budžet za "nevidljive" zadatke uključen u gornje sate: licence i atribucije (Pon, 45 min), ručne anotacije (E1b 1 h, E4 45 min), deploy (Pet 1 h, Uto 1 h), montaža videa (Sri 2 h).

## 9. Demo video (3:00)

**Osnovna verzija (samo MUST):**
| Vrijeme | Sadržaj |
|---|---|
| 0:00–0:20 | Jablanica 2024 (Commons fotografije uz atribuciju, brojke s izvorom) |
| 0:20–0:35 | Problem: stotine fotografija, nula pregleda |
| 0:35–1:05 | **Stvarni live upload 3–5 slika u realnom vremenu** → tačke s krugovima nesigurnosti → panel s maskama i dokazima |
| 1:05–1:35 | **Replay** unaprijed obrađenog scenarija od 30 slika (na ekranu oznaka "replay, ubrzano 4×") → zone se pune |
| 1:35–2:15 | Agent: prioriteti s obrazloženjem, nesiguran nalaz → ljudska provjera → potvrdim; ručni pin |
| 2:15–2:35 | Izvještaj za komandu sa sekcijom "Nije provjereno" |
| 2:35–2:50 | Ispod haube: SAM 3.1 → numerisane maske → Muse Spark → agent; eval brojevi ako su izmjereni |
| 2:50–3:00 | Zatvaranje + link |

**Uslovni dodaci** (samo ako su urađeni): ruta (u 1:35–2:15), drugi jezik izvještaja, "pokreće Muse Spark Open" (u 2:35–2:50).

## 10. Repo i dokumentacija

Repo javan od 27.10., commit svaki dan. README sadrži: problem, GIF, arhitekturu, Meta modele, eval, ograničenja i etiku (AUP, 5.3, 5.4), setup, sekciju **"Built during the hackathon"** (uz napomenu o kodu od 26.10.) i licence podataka. `DATA_SOURCES.md` navodi izvor, autora i licencu za svaku demo sliku. Licenca koda: MIT.

## 11. Checklista za predaju

- [ ] Repo javan; video ≤ 3:00 (link radi u incognito prozoru); live link radi u režimu `demo_readonly` i u sandboxu s budžetom
- [ ] README: "Built during the hackathon", Meta modeli, licence, ograničenja
- [ ] CV platforma: Indie, Build for Your World
- [ ] Muse Spark Open označen **samo ako je stvarno korišten** (podobnost za bonus pitati na office hours, 13.2)
- [ ] X objava s videom, link predat
- [ ] Poruka za Community Vote (nakon 9.11.)

## 12. Rizici i testovi

### 12.1 Rizici

| Rizik | Ublažavanje |
|---|---|
| Geolokacija loša | E2 u četvrtak; pravilo odluke → ručni pin (6.2) |
| Pogrešna lokacija utiče na odluke | Model lokacije 5.3; nepotvrđeno ne mijenja rute |
| SAM ne hvata poplavljene ceste | E4; koncept `flood water`; procjena scene |
| Open lošiji od 1.3 | Kriterij iz E1; prekidač backenda |
| Fakultet / kašnjenje | 4.0 minimalni obim; provjera u subotu u 20:00; feature freeze 3.11. |
| Gubitak podataka na deployu | 1 kontejner, 1 pisac, smoke test u petak |
| Zloupotreba javnog linka | Režimi i globalni budžet (5.5) |
| Diskvalifikacija zbog podataka | Samo licencirano, `DATA_SOURCES.md` |
| "Simple image analyzer" utisak | Video počinje mapom i agentom |

### 12.2 Testovi prihvatanja (pytest, mock API gdje treba)

- **T1 mješoviti batch:** uspjeh + prazan SAM + 429 pa uspjeh + nevalidan JSON dva puta + slika bez GPS-a → batch završava bez zastoja; očekivano: `done/objects`, `done/no_objects`, `done/objects`, `failed (assess, invalid_output)`, `done` + `needs_pin` (nije objavljena).
- **T2 restart:** prekid usred obrade → nakon starta posao se ponavlja; ljudske potvrde ostaju.
- **T3 agent validacija:** nepostojeći `evidence_id`, delta = 3, zastarjela revizija i izmjena zone s `human_priority` → sve odbijeno i logirano.
- **T4 lokacija:** nalaz `impassable` s AI lokacijom bez ljudske veze ne mijenja rutu ni prioritet zbog blokade.
- **T5 zastario i konfliktan nalaz:** prikazan izblijeđeno, bodovi upola; konflikt otvara ljudsku provjeru.
- **T6 budžet:** 151. slika u danu → 429 i iz nove sesije; sandbox A ne može mijenjati sandbox B ni demo.
- **T7 SSE:** prekid veze → ponovno povezivanje s `Last-Event-ID` → nema izgubljenih evenata.
- **T8 kombinacije stanja (dopuna T1):** slika `needs_pin` + `no_objects` + `done` → u listi "Treba lokaciju", nakon pina objavljena **bez novih API poziva** (broj poziva u mocku se ne mijenja).
- **T9 restart s pinom (dopuna T2):** restart usred procjene slike koja čeka pin → procjena se ponavlja, `location_state` ostaje `needs_pin`, a ručni pin postavljen prije restarta ostaje `confirmed`.
- **T10 trajnost:** restart **odmah** nakon ljudske potvrde i nakon rezervacije budžeta (bez novog završenog posla) → potvrda i brojač ostaju; sandbox bez ispravnog tokena dobija 403 na slike, SSE i snapshot.
- **T11 zone:** potvrdi prioritet → `cluster_zones` ne mijenja članstvo zaključane zone; odbaci ključni dokaz → nestaje njegov doprinos i agentova korekcija koja se na njega oslanja; briefing označen kao zastario.
- **T12 vrijeme:** stara slika bez EXIF-a ne postaje svježa uploadom (bodovi × 0,5 + review); historijski replay daje identične prioritete u dva pokretanja; zona sa samo `unknown` nalazima je u listi "Za provjeru" i u izvještaju.

## 13. Otvorena pitanja

### 13.1 Za Ibrahima
1. Koliko sati realno imaš dnevno do 4.11.? Ima li kolokvijuma ili zadaća?
2. Naziv projekta?
3. Želiš li kontaktirati GSS ili Civilnu zaštitu?

### 13.2 Za Discord #office-hours
4. Limit veličine slike i broja objekata za SAM 3.1?
5. Podobnost za Open Weight bonus ako je samo dio pipelinea na Muse Spark Open?
6. Je li u redu što su test skripte napravljene 26.10. nakon kickoffa (uz jasnu oznaku)?

## 14. Reference

- `docs/reference/` – participant guide, credit terms, AUP (lokalne kopije, `.gitignore`)
- `docs/api-notes.md` – Meta API (izvori: dev.meta.ai/docs/models, /pricing-rate-limits, /sam/*, /structured-output, /tool-calling)
- LADI: registry.opendata.aws/ladi (licenca), github.com/LADI-Dataset/ladi-overview (dokumentacija)
- Jablanica 2024: en.wikipedia.org/wiki/2024_Bosnia_and_Herzegovina_floods (brojke provjeriti u primarnom izvoru prije videa)
- Modal Volumes: modal.com/docs/guide/volumes

## 15. Review log

### Review of v1

Pregled: Codex, 27.10.2026. Procitani cijeli plan, API biljeske i postojece skripte procjene/geolokacije. Ishod: REVIEW_DONE; koncept ima smisla, ali plan jos nije spreman za implementaciju bez sljedecih ispravki. Ovo je pregled dizajna, ne potvrda rada API-ja; placeni pozivi nisu izvrsavani.

- **R1-1** [blocker] (sekcije 4.1.2, 4.2.1, 5, 7) – GPS kamere nije koordinata zgrade/ceste na kosoj fotografiji. Plan iz koordinata fotografija prelazi na spajanje istih zgrada, blokiranje dionica i rute bez definisane veze s konkretnim objektom/grafom. → Odvojiti `camera_location`, procijenjenu lokaciju prizora i ljudski potvrdenu lokaciju objekta/OSM edge ID; cuvati izvor, nesigurnost i status potvrde. Za MVP dozvoliti rucno povezivanje cestovnog nalaza s dionicom; bez toga nema automatskog blokiranja grafa ni spajanja zgrada samo po blizini kamera. AI geolokacija ostaje prijedlog do potvrde. Zatvoreno kada plan navodi ove granice i test da pogresna/nepotvrdena lokacija ne blokira pogresnu cestu.
  - **→ v2:** accepted → v2: novi model lokacije (5.3): kamera / AI prijedlog / ručni pin s izvorom, nesigurnošću i potvrdom; krugovi nesigurnosti na mapi; nema automatskog spajanja duplikata (samo prijedlog); ceste utiču na rutu samo uz ručnu vezu s OSM dionicom; test T4 (12.2).

- **R1-2** [major] (sekcije 0, 4, 7) – Iz vidljivog dijela ceste nije moguce zakljuciti sigurnost cijele rute; statusi nemaju vrijeme, nepoznato stanje ni pravilo zastarijevanja, a stari nalazi iz razlicitih katastrofa mogu zavrsiti u istoj zoni. → Dodati incident ID, vrijeme snimka ili oznaku da je nepoznato, status `unknown`, vrijeme potvrde i jasno pravilo konflikta/zastarijevanja. Rutu nazvati prijedlogom koji izbjegava evidentirane blokade; nepoznate dionice nisu potvrdeno prohodne. Nepoznato/nevidljivo nije `no_damage` niti negativan dokaz o ljudima. Zatvoreno kada izvjestaj i UI cuvaju te razlike, a test ukljucuje zastarjeli i konfliktni nalaz.
  - **→ v2:** accepted → v2: incident po slici, `captured_at` ili nepoznato, pravilo zastarijevanja 12 h (bodovi upola), pravilo konflikta (noviji ljudski potvrđen pobjeđuje, inače review), `unknown` ≠ negativan dokaz, sekcija "Nije provjereno" u izvještaju, ruta = "prijedlog koji izbjegava evidentirane blokade" (5.4); test T5.

- **R1-3** [major] (sekcije 5, 8) – SQLite na Modal Volume + memorijski asyncio red nema opis vlasnika baze, opstanka poslova i SSE nakon restarta. Skaliranje na vise kontejnera moze dovesti do izgubljenih upisa; Modal dokumentuje last-write-wins za isti fajl i nedostatak distribuiranog zakljucavanja. → Izabrati jedan konkretan MVP nacin rada: npr. jedan kontejner/proces koji jedini pise, serijalizacija DB upisa, eksplicitno konzistentno cuvanje/checkpoint, trajni statusi poslova i oporavak; ili odgovarajuca vanjska baza/red. Definisati ponovno povezivanje SSE preko ID-ja/snapshot endpointa. Deploy smoke test pomjeriti prije zadnjeg dana razvoja: upload → obrada → restart → nalazi i ljudske potvrde ostaju, prekinuti posao se ponovi ili jasno oznaci neuspjelim. Izvor: [Modal Volumes](https://modal.com/docs/guide/volumes).
  - **→ v2:** accepted → v2: tačno 1 Modal kontejner i 1 proces kao jedini pisac, serijalizovani upisi, trajna `jobs` tabela i oporavak pri startu, SSE s `event_seq` + `Last-Event-ID` + `/snapshot`, smoke test deploya pomjeren na petak 30.10. (5.5, 5.2, 8); testovi T2 i T7.

- **R1-4** [major] (sekcije 4.1.4, 6.2 E1) – LADI oznake su na nivou slike, ne SAM objekta; v2 koristi FEMA kategorije, dok podrazumijevani v2a spaja kategorije. Zato ne mogu direktno potvrditi xBD ocjenu svakog objekta ni prohodnost za vozilo. → Zakljucati verziju dataseta i eksplicitno mapiranje oznaka; za E1 agregirati izlaze na odgovarajuce image-level klase i mjeriti precision/recall/F1 po klasi uz broj pozitivnih primjera. Odvojiti tuning od testnih slika. Dodati mali, vremenski ogranicen rucno oznacen skup za provjeru ID-jeva maski, objektnog dokaza i `unknown`; ogranicenja rucnih oznaka navesti. Dogovoriti kriterij izbora backenda, ne samo 'slican kvalitet'. Izvor: [LADI dokumentacija](https://github.com/LADI-Dataset/ladi-overview).
  - **→ v2:** accepted → v2: zaključan LADI v2 (ne v2a), eksplicitno mapiranje na oznake slike, P/R/F1 po klasi s brojem pozitivnih primjera, odvojeni smoke/tuning(val)/test split bez istih letova, kriterij izbora backenda (makro-F1 ≥ 1.3 − 0,05, JSON ≥ 98%, p95 ≤ 1,5×), E1b ručna provjera na nivou objekta od 1 h uz navedena ograničenja (6.1, 6.2).

- **R1-5** [major] (sekcije 6.2 E2, 12) – E2 ne odredjuje da li mjeri lokaciju kamere ili vidljivog mjesta, broj/slucajan izbor slika i tretman odustajanja. Preostali metapodaci, imena fajlova i prepoznavanje javne fotografije preko weba mogu dati privid vizuelne geolokacije. → Navesti cilj i granicu interpretacije zbog R1-1; koristiti anonimizirane re-enkodirane slike bez lokacijskih metapodataka i identifikatora, regiju zadanu nezavisno od pojedinacnog ground trutha, odvojen testni uzorak i baseline (npr. centar regije). Prijaviti broj svih pokusaja, coverage/odustajanja, medijan/p90 greske za odgovore i udio svih pokusaja unutar 1 km. Web-assisted rezultat posebno oznaciti kao takav. Testirati rano; los rezultat mora aktivirati rucni pin, a ne ostati samo stavka rizika.
  - **→ v2:** accepted → v2: E2 mjeri lokaciju kamere (granica interpretacije navedena), 40 slučajnih slika, re-enkodirane bez metapodataka i preimenovane, regija na nivou države/okruga, baseline centar regije, coverage + medijan/p90 + % svih pokušaja unutar 1/5 km, oznaka web-assisted, pravilo odluke → ručni pin; urađeno već u četvrtak (6.2, 8).

- **R1-6** [major] (sekcija 7) – Formula prioriteta nije izvrsiva specifikacija: nema mapiranja zbira u 1–5, agregacije zone, tretmana duplikata/unknown ni jasnog mjesta gdje se racuna osnovni rezultat. `set_zone_priority(score, reason)` dopusta modelu proizvoljan broj; tekstualna zabrana izmjene ljudskih potvrda nije dovoljan mehanizam. → Definisati deterministicku funkciju, pragove, ogranicenja i par ulaz/izlaz primjera. Server racuna osnovicu i dozvoljava samo validan ±1; provjerava da evidence ID-jevi postoje i pripadaju istom incidentu/zoni, da su revizije aktuelne i da ljudske potvrde nisu prepisive agentom. Mutacije moraju biti idempotentne; paralelne konfliktne akcije serijalizovati/odbiti. Prikazati self-reported confidence kao heuristiku, ne kalibrisanu vjerovatnocu. Dodati test odbijanja nevalidnih ID-jeva, bodova i izmjene potvrdenog nalaza.
  - **→ v2:** accepted → v2: deterministička funkcija s pragovima, max po zoni (duplikati ne napuhuju), primjeri ulaz/izlaz, server računa osnovicu, agent samo delta ∈ {−1,0,+1} uz validne evidence ID-jeve iz iste zone i aktuelnu reviziju, `human_priority` zaključava, idempotentno, confidence prikazan kao samoprocjena (7.1, 7.2); test T3.

- **R1-7** [major] (sekcije 4.1, 5, 7) – Nedostaje minimalni ugovor pipelinea i obrada neuspjeha. Prazna maska, pogresan object ID, nevalidan JSON, 429/timeout ili `needs_pin` trenutno nemaju definisan tok. → Navesti ID-jeve i veze image/object/finding/review, stanja posla, dozvoljene enum vrijednosti i semanticku validaciju odgovora; ogranicene retry/backoff i vremenske budzete po fazi. `needs_pin` ne smije blokirati ostale slike; prazna segmentacija mora dati vidljiv status, a ne izmisljene objekte. Agent ima budzet poziva/vremena i jasan ishod dostizanja 15 koraka. Minimalni acceptance test: mjesoviti batch s uspjehom, praznim SAM-om, 429, nevalidnim odgovorom i rucnim pinom zavrsi bez zastoja.
  - **→ v2:** accepted → v2: tabele i ID-jevi (5.1), stanja posla uključujući neblokirajući `needs_pin` i `no_objects`, retry/backoff samo za 429/5xx/timeout, budžeti po fazi, shema + semantička validacija s jednim ponovnim pokušajem, budžet agenta i ishod `incomplete` (5.2); test T1.

- **R1-8** [major] (sekcije 3, 4, 8, 9, 11) – Zbir rasporeda je 38 h, bez jasno odvojene rezerve; MUST se ne smije rezati iako raspolozivost nije potvrdena. Video i checklista bezuslovno obecavaju SHOULD stavke (rute, dva jezika, Open), a limit 10 novih slika po sesiji je u sukobu s live uploadom 30. → Ispraviti zbir, izdvojiti rezervu i imenovati minimalni rezervni obim unutar jezgre (npr. rucni pin umjesto automatskog trazenja lokacije, agent na dugme, bez automatskog spajanja objekata). Napraviti osnovni demo bez SHOULD funkcija i uslovne dodatke. Razlikovati 30 unaprijed obradjenih demo slika od stvarnog live testa; oznaciti replay/ubrzanje. Budzetirati licence, anotacije, deploy i montazu; E3 precizirati kao potpuno obradjen nalaz, uz p50/p95, cijeli batch i cold/warm mjerenja.
  - **→ v2:** accepted → v2: zbir ispravljen na 35 h = 31 h + 4 h izdvojene rezerve; minimalni rezervni obim 4.0 s provjerom u subotu u 20:00; osnovni video bez SHOULD stavki, uslovni dodaci odvojeni; live upload 3–5 slika u realnom vremenu odvojen od označenog replaya 30 slika; budžetirani licence, anotacije, deploy, montaža; E3 precizan (p50/p95, batch, cold/warm) (4.0, 8, 9, 6.2).

- **R1-9** [major] (sekcije 1, 2, 10, 11) – Vazne tvrdnje iz participant guidea/Credit Terms nemaju dostupnu referencu; javna stranica navodi pocetak 26.10., a plan 27.10. i repo vec ima pocetne skripte. Standard Muse Spark dokumentacija kaze da se sadrzaj ne koristi za trening, dok plan tvrdi posebno pravilo besplatnih kredita: moguc poseban uslov, ali nije ovdje dokazan. → Dodati putanju/link i relevantan odjeljak guidea/terms za build period, 3 min, anti-projekte, bonus podobnost, kredite i obradu podataka; nedostupno oznaciti 'za potvrdu', ne provjereno. Razrijesiti datum pocetka i iskreno evidentirati prethodno postojeci kod bez mijenjanja historije. Rok predaje i konverzija u 5.11. 03:00 CET odgovaraju javno navedenom 4.11. 21:00 ET; interni rok ima 5 h rezerve. Izvori: [Meta event](https://dev.meta.ai/events/global-hackathon), [Meta modeli i Standard/Contributor](https://dev.meta.ai/docs/models).
  - **→ v2:** accepted → v2: dodane lokalne kopije guidea, Credit Terms i AUP u `docs/reference/` s brojevima linija (sekcija 1). Datum: događaj od 26.10. (kickoff, credit-terms l. 6), a building period od 27.10. (guide l. 92); skripte od 26.10. navečer iskreno se navode u README, bez mijenjanja historije, i pitanje ide na office hours (13.2). Tvrdnja o besplatnim kreditima: izvor je tekst s Billing stranice dev.meta.ai od 27.10. (snimak ekrana kod korisnika), sad citiran u sekciji 2.

- **R1-10** [major] (sekcije 5, 11, 12) – Limit 'po sesiji' na javnom linku bez logina moze se zaobici novom sesijom, a zajednicka mapa moze dozvoliti posjetiocu da mijenja tudje potvrde/demo. Ukupni dnevni limit nije definisan kao serverski troskovni budzet. → Za demo odvojiti nepromjenjiv pripremljeni scenarij od posjetiocevog prostora ili zakljucati mutacije. Dodati serverski globalni budzet i rate/concurrency limite za upload i agent run, maksimalni broj bajtova/piksela i validaciju dekodirane slike; novi session ne resetuje globalni limit. Navesti cuvanje/brisanje uploadova i upozorenje o slanju provajderu. Testirati da se budzet ne moze zaobici ponovljenim klikovima/sesijama i da jedan posjetilac ne mijenja tudje nalaze.
  - **→ v2:** accepted → v2: režimi `demo_readonly` (mutacije 403) i izolovani `sandbox` po posjetiocu; serverski globalni dnevni budžet (150 slika, 30 agent runova), limiti konkurentnosti i veličine, dekodiranje i smanjivanje slike, brisanje nakon 24 h, upozorenje o slanju provajderima (5.5); test T6.

- **R1-11** [minor] (sekcije 0, 9) – Broj zrtava u uvodu i tvrdnja '19 mrtvih u jednom selu' nemaju izvor, a 'segmentira svaku' obecava potpunost koju evaluacija jos nije pokazala. → Navesti pouzdan izvor i precizno mjesto/datum za istorijske brojke ili ih izostaviti; opisati SAM kao detekciju/segmentaciju vidljivih kandidata uz moguce propuste.
  - **→ v2:** accepted → v2: brojke sada s izvorom (Wikipedia, uz napomenu da se prije videa provjere u primarnom izvoru) i precizirane (19 u općini Jablanica, najviše u Donjoj Jablanici); "segmentira svaku" zamijenjeno sa "vidljive kandidate, moguće propuste" (0).

Za v2: odgovoriti na svaki ID i prilagoditi plan. Nije potrebno dodavati produkcijsku infrastrukturu niti sve SHOULD funkcije; jednostavnije rjesenje koje eksplicitno zatvara navedeni problem je prihvatljivo. Odgovori korisnika o satima, nazivu i kontaktu ostaju otvoreni; nisu pretpostavljeni.

### Review of v2

Pregled: Codex, 27.10.2026. Procitani cijeli v2, svih 11 odgovora i lokalne kopije participant guidea, Credit Terms i AUP. Ishod: REVIEW_DONE. Veliki napredak: prvobitni blocker R1-1 je zatvoren za MVP (rute su opcionalne, nema automatskog povezivanja objekata). Zatvaram R1-5, R1-8 i R1-9 na nivou plana; potvrda podobnosti koda od 26.10. ostaje jasno evidentirana obaveza prije predaje. R1-11 je prihvatljiv uz vec planiranu provjeru brojki prije videa. Preostale korekcije ispod su dopuna konkretnih nedovrsenih ugovora, ne zahtjev za produkcijskim sistemom.

- **R2-1** [major] (sekcije 6.2 E1; nastavak R1-4) – Novo mapiranje jos poredi razlicite pojmove: `roads_damage` nije isto sto i `passability=caution/impassable` (neoštećena poplavljena cesta moze biti neprohodna, a oštećena prohodna). `buildings_affected` ne treba bez dokaza tumaciti kao uniju svih nivoa štete; LADI v2 i v2a imaju razlicitu semantiku kategorija. → Najjednostavnije: za E1 od oba backenda traziti iste image-level LADI oznake, s izvornim definicijama, odvojeno od procjene prohodnosti/xBD objekata. Alternativa je evaluirati samo dokazano kompatibilne eksplicitne unije na obje strane i izbaciti prohodnost iz LADI damage metrike. Navesti sta se radi s klasom bez pozitivnih primjera i fiksirati skup klasa za makro-F1. Zatvoreno kada obje strane svake metrike mjere isti dogadjaj. Izvor: [LADI v2/v2a dokumentacija](https://github.com/LADI-Dataset/ladi-overview).
  - **→ v3:** accepted → v3: E1 sada poredi iste oznake na obje strane: model u istom pozivu daje poseban blok `image_labels` s LADI klasama i našim operativnim definicijama, odvojeno od xBD štete i prohodnosti (koji se više ne porede s LADI). Unije su eksplicitne na obje strane (`affected_or_greater`, `major_or_greater`), `roads_damage` ≠ prohodnost, fiksan skup od 6 klasa, makro-F1 samo za klase s ≥ 10 pozitivnih, `bridges_damage` isključen; ograničenje definicija navedeno (6.2).

- **R2-2** [major] (sekcije 5.1–5.2, 12.2 T1/T2; nastavak R1-7) – `needs_pin` i `no_objects` su predstavljeni kao stanja istog niza kao `segmenting/assessing`, iako istovremeno trebaju postojati s obradom. Slika moze biti bez lokacije, bez objekata i uspjesno procijenjena; restart trenutno vraca samo tri radna stanja. → Odvojiti `processing_state` (queued/running/done/failed), `stage`, `location_state` (pending/proposed/confirmed/needs_pin) i `segmentation_state` (pending/objects/no_objects), ili opisati ekvivalentan nedvosmislen ugovor. Rucni pin nakon zavrsene procjene samo objavljuje nalaz i ne ponavlja API pozive. `unknown` za people polja mora imati konkretan tip (npr. nullable boolean), jer trenutna skripta dozvoljava samo bool. T1 treba provjeriti kombinacije, a T2 restart usred procjene slike koja ceka pin. Ovo zatvara problem bez dodavanja nove funkcije.
  - **→ v3:** accepted → v3: četiri nezavisna polja `processing_state` / `stage` / `location_state` / `segmentation_state` + `published`; pin nakon procjene samo objavljuje, bez API poziva; oporavak ne zavisi od lokacije; people polja su nullable boolean (5.1, 5.2); testovi T1 (ažuriran), T8, T9. Shema u `scripts/02` biće usklađena pri izradi pipeline modula (čet 29.10.).

- **R2-3** [major] (sekcije 5.1, 7.1–7.2; nastavak R1-6) – `cluster_zones` pravi nove revizije, ali nije definisano sta se desava s `human_priority` i starim `agent_delta` kada se promijene clanovi zone, pin ili potvrda/odbijanje nalaza. Trenutni dizajn moze zaobici ljudsko zakljucavanje ponovnim klasterisanjem ili zadrzati poviseni prioritet zasnovan na odbijenom dokazu. → Za MVP je dovoljno: nakon ljudskog zakljucavanja zamrznuti clanstvo te zone dok covjek ne odobri promjenu; nove slike mogu u nove/nezakljucane zone. Svaka relevantna izmjena ponovo racuna osnovicu, povecava reviziju i ponistava zastarjeli agent_delta/evidence; stari briefing oznaciti zastarjelim ili regenerisati. Svi alati, ukljucujuci review/duplicate, provjeravaju incident ID. Test: potvrdi prioritet → recluster ne zaobilazi lock; odbaci kljucni dokaz → nestaje njegov doprinos i prethodna agentova korekcija.
  - **→ v3:** accepted → v3: nova sekcija 7.3 – zaključana zona zamrzava članstvo, recluster je ne može mijenjati, svaka relevantna promjena ponovo računa osnovicu, povećava reviziju i poništava zastarjeli `agent_delta`, briefing se označava zastarjelim; svi alati provjeravaju incident; test T11.

- **R2-4** [major] (sekcije 5.5, 12.2 T2/T6; nastavak R1-3/R1-10) – Volume commit samo nakon zavrsenog posla ne definise trajnost kasnije ljudske potvrde ni rezervacije globalnog budzeta. Nije dovoljno reci 'WAL + commit' bez konzistentne granice snimanja. → Definisati jednu kratku durability proceduru za sve priznate mutacije (posao, review, agent akcija, budzet), npr. serijalizovan SQLite commit i konzistentan checkpoint/snapshot pa Volume commit prije potvrde uspjeha; dopusten je jednostavan SQLite backup snapshot umjesto kopiranja otvorene baze. Globalni dnevni brojac rezervisati atomski prije API poziva i cuvati ga trajno; retry mora imati ogranicen broj poziva/tokenski budzet. Izolaciju sandboxa vezati za server-provjeravan tajni session token/cookie, ne samo javni incident ID; provjeravati i citanje slika, SSE i snapshot. Testirati restart odmah nakon ljudske potvrde i potrosnje limita, bez novog zavrsenog posla. Izvor za konzistentan snapshot: [SQLite Backup API](https://sqlite.org/backup.html).
  - **→ v3:** accepted → v3: jedna procedura trajnosti za sve potvrđene mutacije (transakcija → SQLite backup API snapshot na Volume → `volume.commit()` → tek onda uspjeh/SSE); budžet se atomski rezerviše prije svakog API poziva uključujući retry i trajno čuva; sandbox vezan za tajni HttpOnly token koji se provjerava i na čitanju slika, SSE i snapshotu; test T10 (5.5).

- **R2-5** [major] (sekcije 5.4, 7.2, 9; nastavak R1-2) – Pravilo vremena automatski prepolovi sve istorijske LADI/Jablanica dokaze u demou, dok upload stare slike bez EXIF-a dobija punu tezinu narednih 12 h. Uz to, iskljucivo `unknown` dobija prioritet 1, pa neprocijenjena zona moze nestati iza top-5 rangiranja i izgledati kao nizak rizik. → Za istorijski demo navesti fiksno `scenario_as_of` vrijeme i jasno 'historijski scenario'; za stvarni sandbox nepoznata starost ostaje nepoznata i trazi provjeru, ne tretira se kao svjez dokaz preko uploaded_at. Zone bez procjenjivih dokaza dobivaju poseban `unassessed` status (prioritet null ili jasno izdvojen red za provjeru), odvojeno od provjereno niskog prioriteta. Dodatni testovi: stara fotografija bez EXIF-a ne postaje svjeza uploadom; istorijski replay je reproducibilan; all-unknown zona ostaje vidljiva u redu za provjeru i izvjestaju.
  - **→ v3:** accepted → v3: `scenario_as_of` za historijski demo uz jasnu oznaku, nepoznat `captured_at` = "starost nepoznata" (× 0,5 + review), `uploaded_at` nikad kao vrijeme snimka; `unassessed` zone s `priority = null` uvijek u listi "Za provjeru" i u izvještaju (5.4, 7.2); test T12.

- **R2-6** [minor] (sekcije 5.3, 5.5, 8) – Tri ogranicene dopune prije implementacije: (a) `osm_way_id` nije nuzno jedna usmjerena dionica grafa: ako se SHOULD ruta radi, spremiti konkretne edge identifikatore (u,v,key) i prikazati koje smjerove covjek potvrdjuje; (b) ograniciti dekodirani broj piksela PRIJE punog dekodiranja, smanjenje na 1600 px nakon dekodiranja nije ta zastita; (c) 4 h rezerve prvo sluze za kvarove/provjere, SHOULD samo iz stvarnog viska nakon prolaska MUST testova. Nista od ovoga ne zahtijeva prosirenje MVP-a.
  - **→ v3:** accepted → v3: (a) sprema se edge `(u, v, key)` i smjer, `osm_way_id` samo informativno (5.3); (b) limit od 40 MP provjeren iz headera prije `load()` + `MAX_IMAGE_PIXELS` (5.5); (c) rezerva prvo za kvarove i testove, SHOULD tek nakon prolaska MUST testova (8).

Zavrsna granica: ne trazim implementirane testove u fazi plana; trazim da v3 odredi gore navedeno ponasanje i ukljuci odgovarajuce provjere. Ostale ranije primjedbe ne otvaram ponovo. Nema potrebe dodavati nove funkcije.

### Review of v3

Pregled: Codex, 27.10.2026. Procitan cijeli v3 i promjene u odnosu na v2. **APPROVED – plan je dovoljno definisan za pocetak implementacije hackathon MVP-a. Nema preostalih blocker/major nalaza na nivou plana.**

Zatvaranje druge runde:
- R2-1 zatvoren: E1 koristi poseban image-level izlaz, eksplicitne unije i navodi ogranicenja operativnih definicija; prohodnost vise nije ground truth za ostecenje ceste.
- R2-2 zatvoren: stanja obrade/lokacije/segmentacije su nezavisna, people polja nullable, a T8/T9 definisu kombinacije i oporavak bez ponovnog poziva nakon pina.
- R2-3 zatvoren: ljudsko zakljucavanje cuva clanstvo, promjene revidiraju osnovicu i odbaceni dokazi prestaju doprinositi; T11 provjerava mehanizam.
- R2-4 zatvoren na nivou dizajna: konzistentan backup i Volume commit prethode potvrdi mutacije; rezervacije su trajne, session token provjerava citanje i pisanje, T10 pokriva restart. Stvarna trajnost i latencija moraju se potvrditi ranim deploy testom.
- R2-5 zatvoren: istorijski scenario ima fiksno vrijeme, nepoznata starost ne postaje svjeza uploadom, a unassessed zone imaju poseban red za provjeru.
- R2-6 zatvoren: konkretni edge/smjer, limit piksela prije load() i rezerva prvenstveno za popravke su navedeni.

Preostale male implementacijske napomene, bez potrebe za cetvrtim krugom plana:
- **R3-1** [minor] (sekcije 5.2, 12.2 T1) – T1 jos koristi staru skracenu notaciju stanja → pri pisanju testa koristiti kombinacije polja iz 5.2 i T8; isto vazi za stari sekvencijalni dijagram lokacije, jer tekst 5.2 sada eksplicitno propisuje paralelnu obradu.
  - **→ final:** noted → final: T1 je već u v3 napisan s kombinacijama polja iz 5.2 (Codexova kopija je slučajno vratila staru liniju; vraćeno). Dijagram u 5 je samo pregled, a 5.2 je mjerodavan.
- **R3-2** [minor] (sekcije 5.4–5.5, 6.2) – Razraditi rubne slucajeve u kodu: buduci/nevalidni captured_at ide na provjeru, prazan skup podobnih E1 klasa ne bira automatski Open, a neuspjela trajna rezervacija ne smije pokrenuti API poziv. Backup/commit dio serijalizovati tako da paralelni radnici ne prepisuju isti snapshot; pri neuspjelom cuvanju ne vracati uspjeh.
  - **→ final:** noted → implementacija: rubni slučajevi idu u kod i testove (budući/nevalidan `captured_at` → review; bez podobnih E1 klasa ostaje 1.3; neuspjela rezervacija budžeta → nema API poziva; backup/commit pod istim lockom, neuspjelo čuvanje → greška klijentu).
- **R3-3** [minor] (sekcije 1, 2, 10, 13) – Tvrdnje 'README navodi' i partnerski krediti treba da odgovaraju stvarnom stanju pri predaji. Raspolozivih 35 h, naziv i kontakt s GSS ostaju korisnikove otvorene odluke; ranije evidentirana podobnost koda od 26.10. i istorijske brojke ostaju provjere prije objave, ne razlog da se odgodi rad na novom MVP-u.
  - **→ final:** noted → provjera prije predaje (checklista 11).

Odobrenje se odnosi na projektni plan, ne na vec dokazanu tacnost modela, postignutu latenciju ili spremnost za operativno spasavanje. Prvo implementirati i provjeriti minimalni tok iz 4.0, a zatim siriti samo prema rasporedu i rezultatima testova. Implementacija nije pokrenuta u ovom pregledu. Automatska petlja pregleda zavrsava prema protokolu jer je status APPROVED.

**Plan finaliziran 27.10.2026. nakon 3 kruga reviewa (Codex APPROVED). Dalje se mijenja samo kroz implementaciju i rezultate testova.**
