# Stanje i plan do predaje (27.10.2026. navečer)

Predaja: **sri 4.11. 21:00 ET = čet 5.11. 03:00 CET**. Interni rok: **sri 4.11. 22:00 CET**.

## 1. Šta radi (testirano)

- **Pipeline:** upload → SAM 3.1 (5 pojmova) → numerisane maske → Muse Spark 1.3 procjena po objektu →
  baza, stanja, retry, budžet, oporavak nakon pada. Validan izlaz 100 %.
- **Agent (koordinator):** zone, ±1 korekcije s dokazima, "molim provjeri", izvještaj EN + BS.
  Server odbija nedozvoljene poteze; sve je u logu.
- **Web aplikacija:** mapa uživo, panel s dokazima, Confirm/Reject, pin, zaključavanje zone, demo samo za
  čitanje, privatni sandbox, mobilni prikaz.
- **Test u pregledniku (27.10.):** 26/26 provjera prolazi, s pravim modelima. Prva slika na mapi za ~18 s,
  agent završi za ~20 s. Pronađena i popravljena 2 bug-a (agent je padao zbog `previous_response_id`;
  demo je nudio dugmad koja ne rade) + 4 UX sitnice.
- **Evaluacija:** E1 makro-F1 0,79 (Open 0,72), E2 geolokacija isključena (5/40 odgovora), E3 19 s / 150 s.
- **26 automatskih testova + 26 provjera u pregledniku.**

## 2. Iskrena procjena: je li dovoljno?

**Tehnički – da, i iznad prosjeka hackathona.** Dva Meta modela rade zajedno (SAM maske su "rječnik" kojim
Muse Spark govori), agent je stvarno ograničen i provjerljiv, postoji prava evaluacija s brojevima. Malo
projekata će imati to.

**Ali za pobjedu tehnika nije glavni problem. Problemi su:**

1. **Priča i demo se ne poklapaju.** Prijava i README pričaju o Bosni, a demo je Kentucky. Žiri pamti priču.
   → Treba scenarij **Jablanica** (ili bar BiH fotografije) u videu.
2. **Demo nije dramatičan.** U Kentucky scenariju skoro sve je prioritet 1–2 (slike su stare, šteta mala).
   Prioriteti, zone i agent najbolje izgledaju kad je stvarno gusto: srušene kuće, ljudi, presječene ceste.
   → Bolji izbor fotografija iz JEDNOG dramatičnijeg događaja (događaje ne miješamo u jedan "izmišljeni"
   incident – to bi bilo nepošteno prema žiriju).
3. **Nema javnog linka.** Žiri gleda "live product". → deploy (čeka Modal kredite).
4. **"Wow" trenutak za Use of Meta AI (25 %).** Sad: SAM + Muse Spark + agent. Što bi iznenadilo:
   **SAM 3.1 praćenje objekata na videu s drona** (malo ko će to koristiti) i/ili **glasovni izvještaj s terena**
   (Muse Voice Transcribe → nalaz na mapi).
5. **Impact bez korisnika.** Niko iz spašavanja to još nije vidio. Jedna izjava GSS-a/Civilne zaštite =
   najjači mogući dokaz za 30 % ocjene.
6. **Rute** su obećane u prijavi ("which routes are safe") – trenutno samo prikazujemo blokirane/oprezne ceste.

Dakle: ostatak NIJE samo tehnička dorada. Najveći dobici su sadržaj (Jablanica, bolji demo), dokaz
korisnosti (GSS), javni link i video.

## 3. Šta možeš SAMO TI

| # | Zadatak | Zašto | Kad |
|---|---|---|---|
| U1 | Dodaj domene `commons.wikimedia.org`, `upload.wikimedia.org` u Settings → Capabilities | Jablanica fotografije | odmah |
| U2 | Modal krediti (mail / Discord), zatim `modal token new` + `modal secret create firsthour-keys ...` | javni link | do pet 30.10. |
| U3 | Poruka GSS-u / Civilnoj zaštiti / vatrogascima (draft pišem ja) | Impact | sri 28.10. |
| U4 | Isprobaj aplikaciju sam, zapiši šta smeta | samo ti vidiš kao korisnik | ove sedmice |
| U5 | Upoznaj kod (vodič pišem ja) – moraš ga moći braniti | pitanja žirija | do vikenda |
| U6 | Snimi glas za video (engleski), odobri scenarij | Demo 25 % | pon–uto |
| U7 | Predaja na CV platformi, X objava, poruke za Community Vote | pravila + bonusi | sri 4.11. |
| U8 | `git reset` u `E:\MetaHACK` (komande u razgovoru) da folder = GitHub | da radiš na istom kodu | odmah |

## 4. Šta radim ja (redom)

| Dan | Zadatak |
|---|---|
| sri 28.10. | **Jablanica scenarij** (Commons, licence, pinovi, `as_of` 4.10.2024.) – čim U1. Do tada: dramatičniji demo iz jednog LADI događaja. **Rute** (osmnx, ručno potvrđene blokade). Draft poruke za U3. |
| čet 29.10. | **SAM 3.1 video praćenje**: kratki snimak s drona → objekti kroz kadrove → nalazi na mapi. |
| pet 30.10. | **Glasovni izvještaj** (Muse Voice Transcribe) → nalaz. **Muse Spark Open** dobija stvarnu ulogu (npr. brza prva procjena dok 1.3 radi, ili prevod izvještaja). Deploy kad stigne U2. |
| sub–ned | Dorada po tvojim bilješkama (U4), vodič kroz kod (U5), scenarij videa. |
| pon 2.11. | **Feature freeze.** Snimanje materijala za video, final README. |
| uto 3.11. | Montaža videa (ja pripremam snimke ekrana/GIF-ove i titlove), provjera checkliste. |
| sri 4.11. | Predaja do 22:00. |

## 5. Odluke od tebe

1. Da li ovaj redoslijed (Jablanica → rute → video praćenje → glas) ima smisla?
2. Ako Commons nema dovoljno dobrih fotografija iz Jablanice: koristimo poplave 2014. (više materijala) ili
   ostajemo na LADI uz Jablanicu samo u uvodu videa?
3. Naziv: ostaje **FirstHour**?
