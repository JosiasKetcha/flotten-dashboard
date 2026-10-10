/* ==========================================================================
   Flotten-Dashboard – lädt daten.json und füllt Kennzahlen und Warnungen.
   Alle Berechnungen beziehen sich auf den Stichtag der Daten (meta.stichtag),
   nicht auf das heutige Datum im Browser – so bleibt das Dashboard stabil.
   ========================================================================== */

"use strict";

const VORLAUF_TAGE = 30;
const TAG_MS = 24 * 60 * 60 * 1000;

const formatEuro = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const formatZahl = new Intl.NumberFormat("de-DE");
const formatDatum = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/** ISO-Datum "2026-10-10" als lokales Datum ohne Zeitzonenverschiebung. */
function parseDatum(iso) {
  const [jahr, monat, tag] = iso.split("-").map(Number);
  return new Date(jahr, monat - 1, tag);
}

function tageZwischen(von, bis) {
  return Math.round((bis - von) / TAG_MS);
}

/** Erzeugt ein Element mit Klasse und Text (sicher, ohne innerHTML). */
function el(tag, klasse, text) {
  const knoten = document.createElement(tag);
  if (klasse) knoten.className = klasse;
  if (text !== undefined) knoten.textContent = text;
  return knoten;
}

function setzeText(id, text) {
  document.getElementById(id).textContent = text;
}

// --------------------------------------------------------------------------
// Kennzahlen
// --------------------------------------------------------------------------

function zeigeKennzahlen(daten, stichtag, offeneTermine) {
  const { fahrzeuge, wartungen } = daten;

  const aktiv = fahrzeuge.filter((f) => f.status === "aktiv").length;
  const werkstatt = fahrzeuge.filter((f) => f.status === "in Werkstatt").length;
  const ausserBetrieb = fahrzeuge.filter((f) => f.status === "außer Betrieb").length;

  setzeText("kpi-aktiv", formatZahl.format(aktiv));
  setzeText("kpi-aktiv-unter", `von ${fahrzeuge.length} Fahrzeugen · ${ausserBetrieb} außer Betrieb`);

  setzeText("kpi-werkstatt", formatZahl.format(werkstatt));
  const quote = ((werkstatt / fahrzeuge.length) * 100).toFixed(0);
  setzeText("kpi-werkstatt-unter", `${quote} % der Flotte`);

  // Kosten im laufenden Jahr bis zum Stichtag, Vergleich mit Vorjahreszeitraum
  const jahr = stichtag.getFullYear();
  const summeBis = (j) =>
    wartungen
      .filter((w) => {
        const d = parseDatum(w.datum);
        return d.getFullYear() === j && d <= new Date(j, stichtag.getMonth(), stichtag.getDate());
      })
      .reduce((summe, w) => summe + w.kosten_eur, 0);
  const kostenJahr = summeBis(jahr);
  const kostenVorjahr = summeBis(jahr - 1);
  const veraenderung = ((kostenJahr / kostenVorjahr - 1) * 100).toFixed(1).replace(".", ",");

  setzeText("kpi-kosten-label", `Wartungskosten ${jahr}`);
  setzeText("kpi-kosten", formatEuro.format(kostenJahr));
  setzeText(
    "kpi-kosten-unter",
    `${kostenJahr >= kostenVorjahr ? "+" : ""}${veraenderung} % ggü. Vorjahreszeitraum`
  );

  const faellig = offeneTermine.filter((t) => t.tage >= 0 && t.tage <= VORLAUF_TAGE).length;
  const ueberfaellig = offeneTermine.filter((t) => t.tage < 0).length;
  setzeText("kpi-faellig", formatZahl.format(faellig));
  setzeText("kpi-faellig-unter", `zusätzlich ${ueberfaellig} überfällig`);
}

// --------------------------------------------------------------------------
// Warnungen
// --------------------------------------------------------------------------

function fristText(tage) {
  if (tage < 0) return `${Math.abs(tage)} ${Math.abs(tage) === 1 ? "Tag" : "Tage"} überfällig`;
  if (tage === 0) return "heute fällig";
  return `in ${tage} ${tage === 1 ? "Tag" : "Tagen"}`;
}

function zeigeWarnungen(offeneTermine) {
  const liste = document.getElementById("alarme");
  liste.replaceChildren();

  // Überfällige und in 30 Tagen fällige Termine, dringendste zuerst
  const warnungen = offeneTermine
    .filter((t) => t.tage <= VORLAUF_TAGE)
    .sort((a, b) => a.tage - b.tage);

  if (warnungen.length === 0) {
    liste.append(el("li", "leer", "Keine fälligen Termine."));
    return;
  }

  for (const t of warnungen) {
    const ueberfaellig = t.tage < 0;
    const li = el("li", `alarm ${ueberfaellig ? "alarm-rot" : "alarm-orange"}`);

    const kennzBlock = el("div", "alarm-kennzeichen-block");
    kennzBlock.append(
      el("div", "alarm-kennzeichen", t.fahrzeug.kennzeichen),
      el("div", "alarm-fahrzeug", `${t.fahrzeug.typ} · ${t.fahrzeug.standort}`)
    );

    const datum = el("time", "alarm-datum", formatDatum.format(t.datum));
    datum.dateTime = t.faellig_am;

    li.append(
      kennzBlock,
      el("div", "alarm-art", t.art),
      datum,
      el("div", "alarm-frist", fristText(t.tage))
    );
    liste.append(li);
  }
}

// --------------------------------------------------------------------------
// Diagramme (Chart.js)
// --------------------------------------------------------------------------

const MONATSNAMEN = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

function chartGrundeinstellungen() {
  const css = getComputedStyle(document.documentElement);
  Chart.defaults.font.family = css.getPropertyValue("--mono").trim();
  Chart.defaults.font.size = 11;
  Chart.defaults.color = css.getPropertyValue("--text-gedaempft").trim();
  Chart.defaults.borderColor = css.getPropertyValue("--linie").trim();
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = "#0F100E";
  Chart.defaults.plugins.tooltip.borderColor = css.getPropertyValue("--akzent").trim();
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 2;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.maintainAspectRatio = false;
  return {
    akzent: css.getPropertyValue("--akzent").trim(),
    gedaempft: "#5C5F56",
  };
}

const euroKurz = (wert) =>
  wert >= 1000 ? `${formatZahl.format(Math.round(wert / 1000))} T€` : `${formatZahl.format(wert)} €`;

function zeigeDiagramme(daten, stichtag, kmNachFahrzeug, kostenNachFahrzeug) {
  if (typeof Chart === "undefined") {
    for (const id of ["chart-monat", "chart-typ", "chart-km"]) {
      const flaeche = document.getElementById(id).parentElement;
      flaeche.replaceChildren(el("p", "fehler", "Chart.js konnte nicht geladen werden (keine Internetverbindung?)."));
    }
    return;
  }
  const farben = chartGrundeinstellungen();

  // 1) Kosten pro Monat – vom ersten Monat der Historie bis zum Stichtag
  const summeProMonat = new Map();
  for (const w of daten.wartungen) {
    const monat = w.datum.slice(0, 7);
    summeProMonat.set(monat, (summeProMonat.get(monat) || 0) + w.kosten_eur);
  }
  const monate = [];
  for (let d = new Date(2024, 0, 1); d <= stichtag; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    monate.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  const laufenderMonat = monate[monate.length - 1];
  document.getElementById("monat-hinweis").textContent =
    `${MONATSNAMEN[stichtag.getMonth()]} ${stichtag.getFullYear()} bis Stichtag`;

  new Chart(document.getElementById("chart-monat"), {
    type: "bar",
    data: {
      labels: monate.map((m) => `${MONATSNAMEN[Number(m.slice(5)) - 1]} ${m.slice(2, 4)}`),
      datasets: [{
        label: "Wartungskosten",
        data: monate.map((m) => Math.round(summeProMonat.get(m) || 0)),
        // der laufende (unvollständige) Monat wird gedämpft dargestellt
        backgroundColor: monate.map((m) => (m === laufenderMonat ? farben.gedaempft : farben.akzent)),
        borderRadius: 1,
        maxBarThickness: 22,
      }],
    },
    options: {
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
        y: { beginAtZero: true, ticks: { callback: euroKurz } },
      },
      plugins: { tooltip: { callbacks: { label: (c) => ` ${formatEuro.format(c.raw)}` } } },
    },
  });

  // 2) Kosten nach Fahrzeugtyp – absteigend sortiert
  const proTyp = new Map();
  for (const f of daten.fahrzeuge) {
    const eintrag = proTyp.get(f.typ) || { kosten: 0, anzahl: 0 };
    eintrag.kosten += kostenNachFahrzeug.get(f.id) || 0;
    eintrag.anzahl += 1;
    proTyp.set(f.typ, eintrag);
  }
  const typen = [...proTyp.entries()].sort((a, b) => b[1].kosten - a[1].kosten);

  new Chart(document.getElementById("chart-typ"), {
    type: "bar",
    data: {
      labels: typen.map(([typ]) => typ),
      datasets: [{
        label: "Kosten",
        data: typen.map(([, e]) => Math.round(e.kosten)),
        backgroundColor: farben.akzent,
        borderRadius: 1,
        maxBarThickness: 28,
      }],
    },
    options: {
      indexAxis: "y",
      scales: {
        x: { beginAtZero: true, ticks: { callback: euroKurz } },
        y: { grid: { display: false } },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (c) => ` ${formatEuro.format(c.raw)}`,
            afterLabel: (c) => {
              const e = typen[c.dataIndex][1];
              return ` ${e.anzahl} Fahrzeuge · Ø ${formatEuro.format(e.kosten / e.anzahl)}`;
            },
          },
        },
      },
    },
  });

  // 3) Kilometer – Top 10 Fahrzeuge
  const top10 = daten.fahrzeuge
    .map((f) => ({ f, km: kmNachFahrzeug.get(f.id) || 0 }))
    .sort((a, b) => b.km - a.km)
    .slice(0, 10);

  new Chart(document.getElementById("chart-km"), {
    type: "bar",
    data: {
      labels: top10.map(({ f }) => f.kennzeichen),
      datasets: [{
        label: "Kilometer",
        data: top10.map(({ km }) => km),
        backgroundColor: farben.akzent,
        borderRadius: 1,
        maxBarThickness: 18,
      }],
    },
    options: {
      indexAxis: "y",
      scales: {
        x: { beginAtZero: true, ticks: { callback: (v) => `${formatZahl.format(v / 1000)} Tkm` } },
        y: { grid: { display: false } },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (c) => ` ${formatZahl.format(c.raw)} km`,
            afterLabel: (c) => ` ${top10[c.dataIndex].f.typ} · ${top10[c.dataIndex].f.standort}`,
          },
        },
      },
    },
  });
}

// --------------------------------------------------------------------------
// Fahrzeugtabelle: Suche, Filter, Sortierung
// --------------------------------------------------------------------------

const STATUS_KLASSE = { aktiv: "status-aktiv", "in Werkstatt": "status-werkstatt", "außer Betrieb": "status-ausser" };

const tabellenZustand = { spalte: "kennzeichen", richtung: 1 };

function fuelleAuswahl(id, werte) {
  const auswahl = document.getElementById(id);
  for (const wert of werte) auswahl.append(new Option(wert, wert));
}

function zeileWerte(f, kmNachFahrzeug, kostenNachFahrzeug) {
  return {
    ...f,
    fahrzeug: `${f.marke} ${f.modell}`,
    km: kmNachFahrzeug.get(f.id) || 0,
    kosten: kostenNachFahrzeug.get(f.id) || 0,
  };
}

function initTabelle(zeilen, oeffneDetail) {
  const sortiere = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const eindeutig = (feld) => [...new Set(zeilen.map((z) => z[feld]))].sort((a, b) => a.localeCompare(b, "de"));

  fuelleAuswahl("filter-typ", ["PKW", "Transporter", "LKW", "Stapler"]);
  fuelleAuswahl("filter-status", ["aktiv", "in Werkstatt", "außer Betrieb"]);
  fuelleAuswahl("filter-standort", eindeutig("standort"));

  const suche = document.getElementById("suche");
  const filterTyp = document.getElementById("filter-typ");
  const filterStatus = document.getElementById("filter-status");
  const filterStandort = document.getElementById("filter-standort");
  const koerper = document.getElementById("tabelle-koerper");
  const kopfzellen = document.querySelectorAll(".tabelle th[data-spalte]");

  function zeichne() {
    const begriff = suche.value.trim().toLowerCase();
    const sichtbar = zeilen
      .filter((z) => !filterTyp.value || z.typ === filterTyp.value)
      .filter((z) => !filterStatus.value || z.status === filterStatus.value)
      .filter((z) => !filterStandort.value || z.standort === filterStandort.value)
      .filter((z) => !begriff || `${z.kennzeichen} ${z.fahrzeug}`.toLowerCase().includes(begriff))
      .sort((a, b) => {
        const { spalte, richtung } = tabellenZustand;
        const x = a[spalte], y = b[spalte];
        const ergebnis = typeof x === "number" ? x - y : String(x).localeCompare(String(y), "de", { numeric: true });
        return ergebnis * richtung || sortiere(a.id, b.id);
      });

    koerper.replaceChildren(
      ...sichtbar.map((z) => {
        const tr = document.createElement("tr");
        const knopf = el("button", "link-kennzeichen", z.kennzeichen);
        knopf.type = "button";
        knopf.setAttribute("aria-label", `${z.kennzeichen}: Details öffnen`);
        knopf.addEventListener("click", (e) => { e.stopPropagation(); oeffneDetail(z.id); });

        const zelleKennz = el("td");
        zelleKennz.append(knopf);
        const zelleStatus = el("td");
        zelleStatus.append(el("span", `status ${STATUS_KLASSE[z.status]}`, z.status));

        tr.append(
          zelleKennz,
          el("td", "", z.typ),
          el("td", "", z.fahrzeug),
          el("td", "zahl", String(z.baujahr)),
          el("td", "", z.kraftstoff),
          el("td", "", z.standort),
          zelleStatus,
          el("td", "zahl", formatZahl.format(z.km)),
          el("td", "zahl", formatEuro.format(z.kosten))
        );
        tr.addEventListener("click", () => oeffneDetail(z.id));
        return tr;
      })
    );
    if (sichtbar.length === 0) {
      const tr = document.createElement("tr");
      const td = el("td", "leer", "Keine Fahrzeuge für diese Auswahl.");
      td.colSpan = 9;
      tr.append(td);
      koerper.append(tr);
    }

    document.getElementById("treffer").textContent = `${sichtbar.length} von ${zeilen.length} Fahrzeugen`;
    kopfzellen.forEach((th) => {
      if (th.dataset.spalte === tabellenZustand.spalte) {
        th.setAttribute("aria-sort", tabellenZustand.richtung === 1 ? "ascending" : "descending");
      } else {
        th.removeAttribute("aria-sort");
      }
    });
  }

  kopfzellen.forEach((th) => {
    th.querySelector("button").addEventListener("click", () => {
      const spalte = th.dataset.spalte;
      if (tabellenZustand.spalte === spalte) {
        tabellenZustand.richtung *= -1;
      } else {
        tabellenZustand.spalte = spalte;
        // Zahlen zuerst absteigend (größte oben), Text aufsteigend
        tabellenZustand.richtung = th.classList.contains("zahl") ? -1 : 1;
      }
      zeichne();
    });
  });

  for (const feld of [suche, filterTyp, filterStatus, filterStandort]) {
    feld.addEventListener("input", zeichne);
  }
  document.getElementById("filter").addEventListener("reset", () => setTimeout(zeichne));

  zeichne();
}

// --------------------------------------------------------------------------
// Detailansicht eines Fahrzeugs (natives <dialog>: Fokus und Escape inklusive)
// --------------------------------------------------------------------------

function alterText(jahre) {
  if (jahre <= 0) return "neu";
  return `${jahre} ${jahre === 1 ? "Jahr" : "Jahre"}`;
}

function initDetail(daten, stichtag, zeilenNachId) {
  const dialog = document.getElementById("detail");
  document.getElementById("detail-schliessen").addEventListener("click", () => dialog.close());
  // Klick auf den abgedunkelten Hintergrund schließt ebenfalls
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });

  let ausloeser = null;
  dialog.addEventListener("close", () => ausloeser?.focus());

  return function oeffneDetail(id) {
    ausloeser = document.activeElement;
    const z = zeilenNachId.get(id);

    document.getElementById("detail-titel").textContent = z.kennzeichen;
    document.getElementById("detail-unter").textContent = `${z.typ} · ${z.fahrzeug}`;

    const infos = [
      ["Status", z.status],
      ["Standort", z.standort],
      ["Baujahr", `${z.baujahr} (${alterText(stichtag.getFullYear() - z.baujahr)})`],
      ["Kraftstoff", z.kraftstoff],
      ["Kilometer seit 01/2024", `${formatZahl.format(z.km)} km`],
      ["Wartungskosten gesamt", formatEuro.format(z.kosten)],
    ];
    document.getElementById("detail-infos").replaceChildren(
      ...infos.map(([titel, wert]) => {
        const div = el("div");
        div.append(el("dt", "", titel), el("dd", "", wert));
        return div;
      })
    );

    // Offene Termine des Fahrzeugs
    const termine = daten.termine
      .filter((t) => t.fahrzeug_id === id && t.erledigt === "nein")
      .map((t) => ({ ...t, tage: tageZwischen(stichtag, parseDatum(t.faellig_am)) }))
      .sort((a, b) => a.tage - b.tage);
    const terminListe = document.getElementById("detail-termine");
    terminListe.replaceChildren(
      ...termine.map((t) => {
        const li = el("li");
        const klasse = t.tage < 0 ? "frist-rot" : t.tage <= VORLAUF_TAGE ? "frist-orange" : "";
        li.append(
          el("span", "", `${t.art} · ${formatDatum.format(parseDatum(t.faellig_am))}`),
          el("span", klasse, fristText(t.tage))
        );
        return li;
      })
    );
    if (termine.length === 0) terminListe.append(el("li", "", "Keine offenen Termine."));

    // Wartungshistorie, neueste zuerst
    const wartungen = daten.wartungen
      .filter((w) => w.fahrzeug_id === id)
      .sort((a, b) => b.datum.localeCompare(a.datum));
    document.getElementById("detail-wartungen").replaceChildren(
      ...wartungen.map((w) => {
        const tr = document.createElement("tr");
        tr.append(
          el("td", "", formatDatum.format(parseDatum(w.datum))),
          el("td", "", w.art),
          el("td", "", w.werkstatt),
          el("td", "zahl", String(w.dauer_tage)),
          el("td", "zahl", formatEuro.format(w.kosten_eur))
        );
        return tr;
      })
    );

    dialog.showModal();
    dialog.scrollTop = 0;
  };
}

// --------------------------------------------------------------------------
// Start
// --------------------------------------------------------------------------

async function start() {
  let daten;
  try {
    const antwort = await fetch("daten.json");
    if (!antwort.ok) throw new Error(`HTTP ${antwort.status}`);
    daten = await antwort.json();
  } catch (fehler) {
    const liste = document.getElementById("alarme");
    liste.replaceChildren(
      el(
        "li",
        "fehler",
        "daten.json konnte nicht geladen werden. Bitte über einen lokalen Server öffnen " +
          "(python -m http.server) statt die Datei direkt per Doppelklick."
      )
    );
    console.error(fehler);
    return;
  }

  const stichtag = parseDatum(daten.meta.stichtag);
  const zeit = document.getElementById("stichtag");
  zeit.textContent = formatDatum.format(stichtag);
  zeit.dateTime = daten.meta.stichtag;

  const fahrzeugNachId = new Map(daten.fahrzeuge.map((f) => [f.id, f]));

  // Offene Termine einmal anreichern (Fahrzeug, Datum, Tage bis Fälligkeit)
  const offeneTermine = daten.termine
    .filter((t) => t.erledigt === "nein")
    .map((t) => {
      const datum = parseDatum(t.faellig_am);
      return { ...t, datum, tage: tageZwischen(stichtag, datum), fahrzeug: fahrzeugNachId.get(t.fahrzeug_id) };
    });

  zeigeKennzahlen(daten, stichtag, offeneTermine);
  zeigeWarnungen(offeneTermine);

  // Summen je Fahrzeug einmal berechnen und überall wiederverwenden
  const kmNachFahrzeug = new Map();
  for (const f of daten.fahrten) {
    kmNachFahrzeug.set(f.fahrzeug_id, (kmNachFahrzeug.get(f.fahrzeug_id) || 0) + f.kilometer);
  }
  const kostenNachFahrzeug = new Map();
  for (const w of daten.wartungen) {
    kostenNachFahrzeug.set(w.fahrzeug_id, (kostenNachFahrzeug.get(w.fahrzeug_id) || 0) + w.kosten_eur);
  }

  const zeilen = daten.fahrzeuge.map((f) => zeileWerte(f, kmNachFahrzeug, kostenNachFahrzeug));
  const zeilenNachId = new Map(zeilen.map((z) => [z.id, z]));
  const oeffneDetail = initDetail(daten, stichtag, zeilenNachId);

  initTabelle(zeilen, oeffneDetail);
  zeigeDiagramme(daten, stichtag, kmNachFahrzeug, kostenNachFahrzeug);
}

start();
