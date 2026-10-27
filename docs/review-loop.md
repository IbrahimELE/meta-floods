# Vazeci protokol pregleda

Korisnik je dostavio novi protokol u ../PLAN.md i on zamjenjuje prethodni protokol odvojenih fajlova.

Codex provjerava PLAN.md svakih 5 minuta. Samo AWAITING_REVIEW pokrece pregled nove verzije. Nalazi idu u sekciju 15; sekcije 0-14 uredjuje Claude. Reviewer postavlja REVIEW_DONE ili APPROVED i osvjezava LAST_EDITED_BY. Najvise 4 runde; limit rundi nije automatsko odobrenje. Nakon APPROVED, cetvrte runde ili 3 sata bez napretka automatizacija se gasi i javlja rezultat. Implementacija nije dio pregleda.

Stanje posljednjeg pregleda je u review-state.json. Claude prema svom protokolu prati PLAN.md svakih 10 minuta.
