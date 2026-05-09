"""Generate a 50-row synthetic demo dataset for Flipbook.

Writes sample_data/demo_50.xlsx with the same Norwegian column headers as
kunder.xlsx (Navn, Firma, Stilling, Telefon, E-post, Etiketter, Notater).
Deterministic: uses a fixed RNG seed so re-running produces an identical file
(and the import_log row-hash dedupe behaves predictably across runs).
"""
from __future__ import annotations

import random
from pathlib import Path

import openpyxl


SEED = 1709
OUT = Path(__file__).parent.parent / "sample_data" / "demo_50.xlsx"

FIRST_NAMES = [
    "Erik", "Marit", "Lars", "Anne", "Tom", "Ingrid", "Ola", "Kari", "Jon",
    "Silje", "Magnus", "Hanne", "Per", "Liv", "Bjørn", "Astrid", "Kjetil",
    "Solveig", "Håkon", "Linn", "Espen", "Ida", "Sindre", "Mette", "Trond",
    "Vibeke", "Stian", "Camilla", "Andreas", "Nina", "Frode", "Tone", "Geir",
    "Ellen", "Roar", "Heidi", "Ketil", "Wenche", "Arild", "Janne", "Pål",
    "Beate", "Sigurd", "Randi", "Tor", "Grete", "Knut", "Berit", "Dag",
    "Torill",
]
LAST_NAMES = [
    "Hansen", "Solberg", "Pettersen", "Berg", "Nordli", "Lien", "Andersen",
    "Olsen", "Larsen", "Johansen", "Nilsen", "Karlsen", "Kristiansen",
    "Eriksen", "Bakken", "Haugen", "Moen", "Lund", "Strand", "Sørensen",
    "Dahl", "Iversen", "Henriksen", "Aas", "Fossum", "Kvam", "Riise", "Vik",
    "Engen", "Røed",
]

CITIES = [
    ("Oslo", "oslo"), ("Bergen", "bergen"), ("Trondheim", "trondheim"),
    ("Stavanger", "stavanger"), ("Drammen", "drammen"),
    ("Kristiansand", "kristiansand"), ("Tromsø", "tromsø"),
    ("Ålesund", "ålesund"), ("Fredrikstad", "fredrikstad"),
    ("Bodø", "bodø"), ("Lillehammer", "lillehammer"), ("Hamar", "hamar"),
    ("Sandefjord", "sandefjord"), ("Tønsberg", "tønsberg"), ("Moss", "moss"),
    ("Haugesund", "haugesund"), ("Sarpsborg", "sarpsborg"),
    ("Skien", "skien"), ("Arendal", "arendal"), ("Molde", "molde"),
]

COMPANY_PATTERNS = [
    "{city} Verktøy", "{city} Bygg AS", "{city} Maskin", "Bygg{city}",
    "{city} Pro", "{city} Industri", "{city} Trelast", "Verktøyhuset {city}",
    "{city} Entreprenør", "{city} Snekkerlag", "{city} Servicesenter",
    "Byggvarehuset {city}", "{city} Mek", "{city} Anleggsservice",
    "Nord{city} Bygg",
]

ROLES = [
    "Innkjøpssjef", "Daglig leder", "Verkstedleder", "Innkjøper", "CFO",
    "Eier", "Driftsleder", "Prosjektleder", "Butikksjef", "Servicesjef",
    "Formann", "Anleggsleder", "Lagersjef", "Teknisk sjef",
]

BRANDS = ["makita", "dewalt", "bosch", "milwaukee", "hilti", "festool", "würth", "hitachi", "ryobi"]
STATUS_TAGS = ["hot", "cold", "vip", "quarterly", "prospect", "kreditt", "ny"]

NOTE_TEMPLATES = [
    "Kjøper {brand}-serien jevnlig. Liker tidlig morgen.",
    "Vil ha demo av nye {brand} slagdrill.",
    "Sammenligner alltid pris med Würth.",
    "Stort konto. Kjøper både {brand} og {brand2}.",
    "Sier ja kun til kvartalsbestillinger.",
    "Bestemmer alt selv. Ring direkte.",
    "Henviser til innkjøp før beslutning.",
    "Trenger katalog på e-post i forkant.",
    "Foretrekker besøk fremfor telefon.",
    "Spør alltid om volumrabatt.",
    "Skifter ut hele {brand}-flåten i Q3.",
    "Bygger nytt verksted neste år. Stort potensial.",
    "Har vært misfornøyd med leveringstid sist.",
    "Ny kontakt. Anbefalt av Hansen i Oslo.",
    "Liker SMS bedre enn e-post.",
    "Vil ha tilbud på batteripakker til {brand}.",
    "Bytter til {brand} fra {brand2} i 2026.",
    "Ferie i juli. Ikke ring.",
    "Følges opp etter messen i Lillestrøm.",
    "Krever signert tilbud før ordre.",
    "Liten butikk, men jevn omsetning.",
    "Familiebedrift. Sønnen overtar snart.",
    "Kun kontant ved levering. Ingen kreditt.",
    "Spurte om opplæring på {brand} systemet.",
    "Skal teste {brand} mot Hilti i sommer.",
    "Bestiller mest skruer og bits.",
    "Stor entreprenørjobb i {city2} til høsten.",
    "Holder hus til kontoret i Bergen.",
    "Foreslo demo av nye akkuverktøy.",
    "Trenger ny pristliste i januar.",
]


def slugify(name: str) -> str:
    table = str.maketrans({"ø": "o", "å": "a", "æ": "ae", "Ø": "O", "Å": "A", "Æ": "Ae"})
    return name.translate(table).lower().replace(" ", "")


def gen_phone(rng: random.Random) -> str:
    a = rng.randint(900, 989)
    b = rng.randint(10, 99)
    c = rng.randint(100, 999)
    return f"+47 {a} {b} {c}"


def gen_row(rng: random.Random) -> tuple[str, str, str, str, str, str, str]:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    name = f"{first} {last}"

    city, city_tag = rng.choice(CITIES)
    company = rng.choice(COMPANY_PATTERNS).format(city=city)
    role = rng.choice(ROLES)

    phone = gen_phone(rng)
    email = f"{slugify(first)}.{slugify(last)}@{slugify(company.split()[0])}.no"

    tags: list[str] = [city_tag]
    n_brands = rng.choices([0, 1, 2], weights=[2, 5, 3])[0]
    tags.extend(rng.sample(BRANDS, n_brands))
    if rng.random() < 0.55:
        tags.append(rng.choice(STATUS_TAGS))
    tag_str = ", ".join(dict.fromkeys(tags))

    template = rng.choice(NOTE_TEMPLATES)
    other_city = rng.choice([c for c, _ in CITIES if c != city])
    note = template.format(
        brand=rng.choice(BRANDS).capitalize(),
        brand2=rng.choice(BRANDS).capitalize(),
        city2=other_city,
    )

    return name, company, role, phone, email, tag_str, note


def main() -> None:
    rng = random.Random(SEED)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Kunder"
    ws.append(["Navn", "Firma", "Stilling", "Telefon", "E-post", "Etiketter", "Notater"])

    seen: set[tuple[str, str]] = set()
    written = 0
    while written < 50:
        row = gen_row(rng)
        key = (row[0], row[1])  # (name, company) — match the import_log dedupe key spirit
        if key in seen:
            continue
        seen.add(key)
        ws.append(row)
        written += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {written} rows to {OUT}")


if __name__ == "__main__":
    main()
