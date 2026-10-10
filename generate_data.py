"""
Flotten-Dashboard: Generator für synthetische Flottendaten.

Erzeugt 50 fiktive Fahrzeuge eines Unternehmens in der Region Rhein-Neckar
mit Wartungen, Fahrten und Prüfterminen von 2024 bis zum Stichtag.

Ausgabe:
  daten/fahrzeuge.csv, daten/wartungen.csv, daten/fahrten.csv, daten/termine.csv
  daten/flotte.db   (SQLite-Datenbank mit denselben 4 Tabellen)
  daten.json        (wird vom Dashboard im Browser gelesen)

Alle Daten sind frei erfunden. Durch den festen Seed und den festen Stichtag
liefert jeder Lauf exakt dasselbe Ergebnis.

Aufruf:  python generate_data.py
"""

import csv
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

SEED = 42
STICHTAG = date(2026, 10, 10)        # "Heute" aus Sicht der Daten
HISTORIE_START = date(2024, 1, 1)
ANZAHL_FAHRZEUGE = 50

BASIS = Path(__file__).resolve().parent
DATEN_ORDNER = BASIS / "daten"
JSON_DATEI = BASIS / "daten.json"
DB_DATEI = DATEN_ORDNER / "flotte.db"

# Standorte in der Region Rhein-Neckar: Gewichtung (Zentrale = größter Standort)
# und Unterscheidungszeichen für das Kennzeichen des jeweiligen Zulassungsbezirks
STANDORTE = {
    "Ludwigshafen": (16, "LU"),
    "Mannheim": (11, "MA"),
    "Heidelberg": (9, "HD"),
    "Speyer": (7, "SP"),
    "Frankenthal": (7, "FT"),
}

# Anzahl Fahrzeuge je Typ (Summe = 50)
TYP_VERTEILUNG = {"PKW": 20, "Transporter": 15, "LKW": 8, "Stapler": 7}

# Mögliche Modelle je Typ: (Marke, Modell, Kraftstoff)
MODELLE = {
    "PKW": [
        ("VW", "Golf", "Benzin"),
        ("VW", "Passat Variant", "Diesel"),
        ("Opel", "Astra", "Benzin"),
        ("Skoda", "Octavia Combi", "Diesel"),
        ("BMW", "320d Touring", "Diesel"),
        ("VW", "ID.3", "Elektro"),
        ("Hyundai", "Kona Elektro", "Elektro"),
    ],
    "Transporter": [
        ("Mercedes-Benz", "Sprinter", "Diesel"),
        ("VW", "Crafter", "Diesel"),
        ("Ford", "Transit Custom", "Diesel"),
        ("Mercedes-Benz", "eSprinter", "Elektro"),
    ],
    "LKW": [
        ("MAN", "TGL 12.220", "Diesel"),
        ("Mercedes-Benz", "Atego 1224", "Diesel"),
        ("DAF", "LF 230", "Diesel"),
    ],
    "Stapler": [
        ("Linde", "E20", "Elektro"),
        ("Jungheinrich", "EFG 216", "Elektro"),
        ("Still", "RX70-30", "Diesel"),
    ],
}

# Durchschnittliche Kilometer pro Monat je Typ
KM_PRO_MONAT = {"PKW": 1700, "Transporter": 2900, "LKW": 5600, "Stapler": 140}

# Verbrauch (l/100 km bzw. kWh/100 km) je Typ und Kraftstoff: (min, max)
VERBRAUCH = {
    ("PKW", "Benzin"): (6.2, 7.8),
    ("PKW", "Diesel"): (4.9, 6.3),
    ("PKW", "Elektro"): (14.5, 17.5),
    ("Transporter", "Diesel"): (8.8, 10.9),
    ("Transporter", "Elektro"): (25.0, 30.0),
    ("LKW", "Diesel"): (18.0, 23.5),
    ("Stapler", "Elektro"): (55.0, 70.0),
    ("Stapler", "Diesel"): (28.0, 36.0),
}

# Kostenbasis in EUR je Wartungsart und Typ (für ein neues Fahrzeug)
KOSTEN_BASIS = {
    "Inspektion": {"PKW": 320, "Transporter": 480, "LKW": 1150, "Stapler": 380},
    "Reifenwechsel": {"PKW": 70, "Transporter": 110, "LKW": 380, "Stapler": 0},
    "Reparatur": {"PKW": 650, "Transporter": 900, "LKW": 1900, "Stapler": 700},
    "Unfallschaden": {"PKW": 2800, "Transporter": 3600, "LKW": 6500, "Stapler": 1800},
}

# Unfallrate pro Jahr je Typ
UNFALL_RATE = {"PKW": 0.08, "Transporter": 0.12, "LKW": 0.10, "Stapler": 0.15}

# Prüfintervalle in Monaten
HU_INTERVALL = {"PKW": 24, "Transporter": 24, "LKW": 12}   # Stapler: keine HU
HU_ERSTE = {"PKW": 36, "Transporter": 24, "LKW": 12}       # erste HU nach Erstzulassung
INSPEKTION_INTERVALL = {"PKW": 12, "Transporter": 12, "LKW": 6, "Stapler": 12}
UVV_INTERVALL = 12                                          # jährlich für alle

rng = random.Random(SEED)


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------

def monate_addieren(d: date, monate: int) -> date:
    """Addiert Monate zu einem Datum (Tag wird bei Bedarf gekürzt)."""
    jahr = d.year + (d.month - 1 + monate) // 12
    monat = (d.month - 1 + monate) % 12 + 1
    tag = min(d.day, [31, 29 if jahr % 4 == 0 else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][monat - 1])
    return date(jahr, monat, tag)


def zufallsdatum(von: date, bis: date) -> date:
    return von + timedelta(days=rng.randint(0, max(0, (bis - von).days)))


def alter_in_jahren(baujahr: int, stichtag: date) -> int:
    return max(0, stichtag.year - baujahr)


def poisson(lam: float) -> int:
    """Einfache Poisson-Ziehung (Knuth), ohne externe Bibliotheken."""
    grenze, k, p = pow(2.718281828, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= grenze:
            return k
        k += 1


def monatsliste(von: date, bis: date):
    """Liefert den ersten Tag jedes Monats von 'von' bis einschließlich 'bis'."""
    d = date(von.year, von.month, 1)
    while d <= bis:
        yield d
        d = monate_addieren(d, 1)


# --------------------------------------------------------------------------
# Fahrzeuge
# --------------------------------------------------------------------------

def erzeuge_kennzeichen(vergeben: set, kuerzel: str, elektro: bool) -> str:
    """Fiktives Kennzeichen wie 'MA-FM 1234' (Kürzel des Standorts);
    E-Fahrzeuge erhalten das E-Kennzeichen."""
    while True:
        nummer = rng.randint(100, 9999 if not elektro else 999)
        kennzeichen = f"{kuerzel}-FM {nummer}{'E' if elektro else ''}"
        if kennzeichen not in vergeben:
            vergeben.add(kennzeichen)
            return kennzeichen


def erzeuge_fahrzeuge():
    fahrzeuge = []
    vergeben = set()
    typen = [t for t, n in TYP_VERTEILUNG.items() for _ in range(n)]
    standorte = list(STANDORTE)
    gewichte = [gewicht for gewicht, _ in STANDORTE.values()]

    for i, typ in enumerate(typen, start=1):
        marke, modell, kraftstoff = rng.choice(MODELLE[typ])
        # E-Fahrzeuge sind jünger, LKW und Stapler laufen länger
        if kraftstoff == "Elektro":
            baujahr = rng.randint(2020, 2025)
        elif typ in ("LKW", "Stapler"):
            baujahr = rng.randint(2012, 2024)
        else:
            baujahr = rng.randint(2014, 2025)

        erstzulassung = date(baujahr, rng.randint(1, 12), rng.randint(1, 28))
        if erstzulassung >= STICHTAG:
            erstzulassung = STICHTAG - timedelta(days=200)

        standort = rng.choices(standorte, weights=gewichte)[0]
        kuerzel = STANDORTE[standort][1]
        fahrzeuge.append({
            "id": i,
            "kennzeichen": erzeuge_kennzeichen(vergeben, kuerzel, kraftstoff == "Elektro"),
            "typ": typ,
            "marke": marke,
            "modell": modell,
            "baujahr": baujahr,
            "kraftstoff": kraftstoff,
            "standort": standort,
            "status": "aktiv",
            # interne Hilfsfelder, werden nicht exportiert
            "_erstzulassung": erstzulassung,
            "_im_bestand_ab": max(HISTORIE_START, erstzulassung),
            "_stillgelegt_am": None,
        })

    # 2 alte Fahrzeuge sind außer Betrieb (seit einigen Monaten stillgelegt)
    alte = sorted(fahrzeuge, key=lambda f: f["baujahr"])[:6]
    for f in rng.sample(alte, 2):
        f["status"] = "außer Betrieb"
        f["_stillgelegt_am"] = monate_addieren(STICHTAG, -rng.randint(2, 7)).replace(day=1)

    # 4 Fahrzeuge stehen aktuell in der Werkstatt
    aktive = [f for f in fahrzeuge if f["status"] == "aktiv"]
    for f in rng.sample(aktive, 4):
        f["status"] = "in Werkstatt"

    # Fahrzeuge nach Kennzeichen sortieren und IDs neu vergeben
    fahrzeuge.sort(key=lambda f: (f["typ"] != "PKW", f["kennzeichen"]))
    for i, f in enumerate(fahrzeuge, start=1):
        f["id"] = i
    return fahrzeuge


# --------------------------------------------------------------------------
# Termine (HU, UVV-Prüfung, Inspektion)
# --------------------------------------------------------------------------

def termin_reihe(start: date, erste_monate: int, intervall: int):
    """Erzeugt Fälligkeiten: erste nach 'erste_monate', dann alle 'intervall' Monate."""
    d = monate_addieren(start, erste_monate)
    while True:
        yield d
        d = monate_addieren(d, intervall)


def erzeuge_termine(fahrzeuge):
    termine = []
    for f in fahrzeuge:
        ez = f["_erstzulassung"]
        reihen = []
        if f["typ"] in HU_INTERVALL:
            reihen.append(("HU", termin_reihe(ez, HU_ERSTE[f["typ"]], HU_INTERVALL[f["typ"]])))
        # UVV und Inspektion folgen eigenen Rhythmen, damit nicht alles am selben Tag fällig ist
        uvv_start = ez + timedelta(days=rng.randint(20, 240))
        reihen.append(("UVV-Prüfung", termin_reihe(uvv_start, UVV_INTERVALL, UVV_INTERVALL)))
        iv = INSPEKTION_INTERVALL[f["typ"]]
        insp_start = ez + timedelta(days=rng.randint(-25, 45))
        reihen.append(("Inspektion", termin_reihe(insp_start, iv, iv)))

        for art, reihe in reihen:
            for faellig in reihe:
                if faellig < f["_im_bestand_ab"]:
                    continue
                stillgelegt = f["_stillgelegt_am"]
                if stillgelegt and faellig >= stillgelegt:
                    break  # stillgelegte Fahrzeuge haben keine offenen Termine
                erledigt = faellig < STICHTAG
                termine.append({
                    "fahrzeug_id": f["id"], "art": art,
                    "faellig_am": faellig, "erledigt": "ja" if erledigt else "nein",
                })
                if not erledigt:
                    break  # nur den nächsten offenen Termin anlegen

    # Einige Termine absichtlich überfällig machen:
    # Der letzte vergangene Termin wurde (noch) nicht erledigt.
    nach_reihe = {}
    for t in termine:
        nach_reihe.setdefault((t["fahrzeug_id"], t["art"]), []).append(t)
    kandidaten = []
    for reihe in nach_reihe.values():
        vergangen = [t for t in reihe if t["faellig_am"] < STICHTAG]
        # nur kürzlich fällige Termine (max. 75 Tage) zählen als realistisch überfällig
        if vergangen and (STICHTAG - vergangen[-1]["faellig_am"]).days <= 75:
            kandidaten.append(reihe)
    for reihe in rng.sample(kandidaten, min(6, len(kandidaten))):
        letzter = [t for t in reihe if t["faellig_am"] < STICHTAG][-1]
        letzter["erledigt"] = "nein"
        # Solange der Termin offen ist, wird kein Folgetermin geplant
        for t in [t for t in reihe if t["faellig_am"] >= STICHTAG]:
            termine.remove(t)

    termine.sort(key=lambda t: (t["faellig_am"], t["fahrzeug_id"]))
    for i, t in enumerate(termine, start=1):
        t["id"] = i
    return termine


# --------------------------------------------------------------------------
# Wartungen
# --------------------------------------------------------------------------

def kosten(art: str, f: dict, datum: date) -> float:
    """Kosten steigen mit dem Alter; E-Fahrzeuge sind in Reparaturen günstiger."""
    basis = KOSTEN_BASIS[art][f["typ"]]
    alter = alter_in_jahren(f["baujahr"], datum)
    faktor = 1 + 0.07 * alter
    if f["kraftstoff"] == "Elektro" and art in ("Inspektion", "Reparatur"):
        faktor *= 0.7
    if art in ("Reparatur", "Unfallschaden"):
        streuung = rng.lognormvariate(0, 0.55)  # wenige sehr teure Fälle
    else:
        streuung = rng.uniform(0.85, 1.15)
    return round(basis * faktor * streuung, 2)


def erzeuge_wartungen(fahrzeuge, termine):
    wartungen = []
    nach_id = {f["id"]: f for f in fahrzeuge}

    def neu(f, datum, art, werkstatt, dauer):
        wartungen.append({
            "fahrzeug_id": f["id"], "datum": datum, "art": art,
            "kosten_eur": kosten(art, f, datum), "werkstatt": werkstatt,
            "dauer_tage": dauer,
        })

    # 1) Inspektionen: zu jedem erledigten Inspektionstermin
    for t in termine:
        if t["art"] == "Inspektion" and t["erledigt"] == "ja":
            f = nach_id[t["fahrzeug_id"]]
            datum = t["faellig_am"] - timedelta(days=rng.randint(0, 21))
            datum = max(datum, f["_im_bestand_ab"])
            werkstatt = "intern" if f["typ"] == "Stapler" or rng.random() < 0.25 else "extern"
            neu(f, datum, "Inspektion", werkstatt, 1 if f["typ"] != "LKW" else rng.randint(1, 2))

    for f in fahrzeuge:
        start = f["_im_bestand_ab"]
        ende = min(STICHTAG, f["_stillgelegt_am"] or STICHTAG) - timedelta(days=1)

        # 2) Reifenwechsel im Frühjahr (April) und Herbst (Oktober/November)
        if f["typ"] != "Stapler":
            for jahr in range(start.year, ende.year + 1):
                for von, bis in ((date(jahr, 3, 25), date(jahr, 4, 30)),
                                 (date(jahr, 10, 1), date(jahr, 11, 15))):
                    datum = zufallsdatum(von, bis)
                    if start <= datum <= ende:
                        werkstatt = "intern" if rng.random() < 0.5 else "extern"
                        neu(f, datum, "Reifenwechsel", werkstatt, 1)

        # 3) Reparaturen: häufiger bei alten Fahrzeugen und LKW
        tage = (ende - start).days
        if tage <= 0:
            continue
        for jahr_offset in range(0, tage // 365 + 1):
            von = start + timedelta(days=365 * jahr_offset)
            bis = min(ende, von + timedelta(days=364))
            if von > bis:
                break
            anteil = ((bis - von).days + 1) / 365
            alter = alter_in_jahren(f["baujahr"], von)
            rate = (0.4 + 0.22 * alter) * (1.4 if f["typ"] == "LKW" else 1.0)
            if f["kraftstoff"] == "Elektro":
                rate *= 0.6
            for _ in range(poisson(rate * anteil)):
                neu(f, zufallsdatum(von, bis), "Reparatur",
                    "intern" if rng.random() < 0.35 else "extern", rng.randint(1, 6))

            # 4) Unfallschäden: selten
            if rng.random() < UNFALL_RATE[f["typ"]] * anteil:
                neu(f, zufallsdatum(von, bis), "Unfallschaden", "extern", rng.randint(3, 14))

        # 5) Fahrzeuge "in Werkstatt": laufender Aufenthalt bis über den Stichtag hinaus
        if f["status"] == "in Werkstatt":
            datum = STICHTAG - timedelta(days=rng.randint(1, 6))
            art = rng.choice(["Reparatur", "Reparatur", "Unfallschaden"])
            neu(f, datum, art, "extern", (STICHTAG - datum).days + rng.randint(2, 8))

    wartungen.sort(key=lambda w: (w["datum"], w["fahrzeug_id"]))
    for i, w in enumerate(wartungen, start=1):
        w["id"] = i
    return wartungen


# --------------------------------------------------------------------------
# Fahrten (Kilometer und Verbrauch pro Monat)
# --------------------------------------------------------------------------

SAISON = {1: 0.92, 2: 0.95, 3: 1.0, 4: 1.02, 5: 1.04, 6: 1.03,
          7: 0.97, 8: 0.85, 9: 1.03, 10: 1.04, 11: 1.0, 12: 0.82}


def erzeuge_fahrten(fahrzeuge, wartungen):
    fahrten = []
    letzter_monat = monate_addieren(date(STICHTAG.year, STICHTAG.month, 1), -1)

    werkstatt_tage = {}
    for w in wartungen:
        key = (w["fahrzeug_id"], w["datum"].year, w["datum"].month)
        werkstatt_tage[key] = werkstatt_tage.get(key, 0) + w["dauer_tage"]

    for f in fahrzeuge:
        # individuelles Fahrprofil: manche Fahrzeuge werden mehr genutzt als andere
        profil = rng.uniform(0.75, 1.25)
        vmin, vmax = VERBRAUCH[(f["typ"], f["kraftstoff"])]
        basis_verbrauch = rng.uniform(vmin, vmax)

        for monat in monatsliste(f["_im_bestand_ab"], letzter_monat):
            stillgelegt = f["_stillgelegt_am"]
            if stillgelegt and monat >= stillgelegt:
                break
            alter = alter_in_jahren(f["baujahr"], monat)
            ausfall = werkstatt_tage.get((f["id"], monat.year, monat.month), 0)
            verfuegbar = max(0.2, 1 - ausfall / 30)
            km = KM_PRO_MONAT[f["typ"]] * profil * SAISON[monat.month]
            km *= max(0.6, 1 - 0.02 * alter)          # ältere Fahrzeuge fahren etwas weniger
            km *= verfuegbar * rng.uniform(0.88, 1.12)

            verbrauch = basis_verbrauch * (1 + 0.01 * alter)
            if f["kraftstoff"] == "Elektro" and monat.month in (12, 1, 2):
                verbrauch *= 1.18                       # Winter: höherer Stromverbrauch
            verbrauch *= rng.uniform(0.96, 1.04)

            fahrten.append({
                "fahrzeug_id": f["id"],
                "monat": monat.strftime("%Y-%m"),
                "kilometer": int(round(km)),
                "verbrauch": round(verbrauch, 1),
            })
    return fahrten


# --------------------------------------------------------------------------
# Export: CSV, SQLite, JSON
# --------------------------------------------------------------------------

SPALTEN = {
    "fahrzeuge": ["id", "kennzeichen", "typ", "marke", "modell", "baujahr",
                  "kraftstoff", "standort", "status"],
    "wartungen": ["id", "fahrzeug_id", "datum", "art", "kosten_eur", "werkstatt", "dauer_tage"],
    "fahrten": ["fahrzeug_id", "monat", "kilometer", "verbrauch"],
    "termine": ["id", "fahrzeug_id", "art", "faellig_am", "erledigt"],
}

SCHEMA = """
CREATE TABLE fahrzeuge (
    id          INTEGER PRIMARY KEY,
    kennzeichen TEXT    NOT NULL UNIQUE,
    typ         TEXT    NOT NULL CHECK (typ IN ('PKW', 'Transporter', 'LKW', 'Stapler')),
    marke       TEXT    NOT NULL,
    modell      TEXT    NOT NULL,
    baujahr     INTEGER NOT NULL,
    kraftstoff  TEXT    NOT NULL CHECK (kraftstoff IN ('Diesel', 'Benzin', 'Elektro')),
    standort    TEXT    NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('aktiv', 'in Werkstatt', 'außer Betrieb'))
);

CREATE TABLE wartungen (
    id          INTEGER PRIMARY KEY,
    fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id),
    datum       TEXT    NOT NULL,
    art         TEXT    NOT NULL CHECK (art IN ('Inspektion', 'Reparatur', 'Reifenwechsel', 'Unfallschaden')),
    kosten_eur  REAL    NOT NULL CHECK (kosten_eur >= 0),
    werkstatt   TEXT    NOT NULL CHECK (werkstatt IN ('intern', 'extern')),
    dauer_tage  INTEGER NOT NULL CHECK (dauer_tage >= 1)
);

CREATE TABLE fahrten (
    fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id),
    monat       TEXT    NOT NULL,
    kilometer   INTEGER NOT NULL CHECK (kilometer >= 0),
    verbrauch   REAL    NOT NULL,
    PRIMARY KEY (fahrzeug_id, monat)
);

CREATE TABLE termine (
    id          INTEGER PRIMARY KEY,
    fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id),
    art         TEXT    NOT NULL CHECK (art IN ('HU', 'UVV-Prüfung', 'Inspektion')),
    faellig_am  TEXT    NOT NULL,
    erledigt    TEXT    NOT NULL CHECK (erledigt IN ('ja', 'nein'))
);

CREATE INDEX idx_wartungen_fahrzeug ON wartungen(fahrzeug_id);
CREATE INDEX idx_termine_fahrzeug   ON termine(fahrzeug_id);
"""


def als_zeile(datensatz: dict, spalten: list) -> list:
    return [datensatz[s].isoformat() if isinstance(datensatz[s], date) else datensatz[s]
            for s in spalten]


def exportiere(tabellen: dict):
    DATEN_ORDNER.mkdir(exist_ok=True)

    # CSV (Semikolon wäre in DE üblich; Komma ist für GitHub/Tools neutraler)
    for name, zeilen in tabellen.items():
        with open(DATEN_ORDNER / f"{name}.csv", "w", newline="", encoding="utf-8") as datei:
            writer = csv.writer(datei)
            writer.writerow(SPALTEN[name])
            writer.writerows(als_zeile(z, SPALTEN[name]) for z in zeilen)

    # SQLite
    if DB_DATEI.exists():
        DB_DATEI.unlink()
    with sqlite3.connect(DB_DATEI) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        for name, zeilen in tabellen.items():
            spalten = SPALTEN[name]
            platzhalter = ", ".join("?" for _ in spalten)
            db.executemany(
                f"INSERT INTO {name} ({', '.join(spalten)}) VALUES ({platzhalter})",
                [als_zeile(z, spalten) for z in zeilen],
            )
    db.close()

    # JSON für das Dashboard
    ausgabe = {
        "meta": {
            "stichtag": STICHTAG.isoformat(),
            "seed": SEED,
            "hinweis": "Daten synthetisch erzeugt",
        },
    }
    for name, zeilen in tabellen.items():
        ausgabe[name] = [dict(zip(SPALTEN[name], als_zeile(z, SPALTEN[name]))) for z in zeilen]
    with open(JSON_DATEI, "w", encoding="utf-8") as datei:
        json.dump(ausgabe, datei, ensure_ascii=False, separators=(",", ":"))


def main():
    fahrzeuge = erzeuge_fahrzeuge()
    termine = erzeuge_termine(fahrzeuge)
    wartungen = erzeuge_wartungen(fahrzeuge, termine)
    fahrten = erzeuge_fahrten(fahrzeuge, wartungen)

    exportiere({
        "fahrzeuge": fahrzeuge,
        "wartungen": wartungen,
        "fahrten": fahrten,
        "termine": termine,
    })

    offen = [t for t in termine if t["erledigt"] == "nein"]
    ueberfaellig = sum(1 for t in offen if t["faellig_am"] < STICHTAG)
    bald = sum(1 for t in offen if 0 <= (t["faellig_am"] - STICHTAG).days <= 30)
    print(f"Stichtag: {STICHTAG:%d.%m.%Y}  (Seed {SEED})")
    print(f"  {len(fahrzeuge)} Fahrzeuge, {len(wartungen)} Wartungen, "
          f"{len(fahrten)} Fahrten-Monate, {len(termine)} Termine")
    print(f"  Offene Termine: {ueberfaellig} überfällig, {bald} in den nächsten 30 Tagen")
    print(f"  Geschrieben: {DATEN_ORDNER.name}/*.csv, {DB_DATEI.name}, {JSON_DATEI.name}")


if __name__ == "__main__":
    main()
