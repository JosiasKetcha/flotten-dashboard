-- ==========================================================================
-- Flotten-Dashboard: Auswertungen auf der SQLite-Datenbank daten/flotte.db
--
-- Ausführen z. B. mit:  sqlite3 daten/flotte.db < queries.sql
-- oder einzeln in DB Browser for SQLite / DBeaver.
--
-- Der Stichtag der synthetischen Daten ist der 10.10.2026. Er steht in jeder
-- Abfrage, die ihn braucht, in einer CTE "parameter", damit er an einer
-- Stelle geändert werden kann.
-- ==========================================================================


-- --------------------------------------------------------------------------
-- 1) Wartungskosten pro Fahrzeug (gesamter Zeitraum)
--    LEFT JOIN, damit auch Fahrzeuge ohne Wartung mit 0 EUR erscheinen.
-- --------------------------------------------------------------------------
SELECT
    f.kennzeichen,
    f.typ,
    f.marke || ' ' || f.modell          AS fahrzeug,
    COUNT(w.id)                          AS anzahl_wartungen,
    ROUND(COALESCE(SUM(w.kosten_eur), 0), 2) AS kosten_gesamt_eur
FROM fahrzeuge f
LEFT JOIN wartungen w ON w.fahrzeug_id = f.id
GROUP BY f.id
ORDER BY kosten_gesamt_eur DESC;


-- --------------------------------------------------------------------------
-- 2) Top 10 teuerste Fahrzeuge, normiert auf Kosten pro 1.000 km
--    Zwei Teilsummen in eigenen CTEs, damit sich Wartungen und Fahrten beim
--    JOIN nicht gegenseitig vervielfachen. Stapler werden ausgeschlossen,
--    weil sie kaum Kilometer fahren und der Wert dort nichts aussagt.
-- --------------------------------------------------------------------------
WITH kosten AS (
    SELECT fahrzeug_id, SUM(kosten_eur) AS kosten_eur
    FROM wartungen
    GROUP BY fahrzeug_id
),
strecke AS (
    SELECT fahrzeug_id, SUM(kilometer) AS km
    FROM fahrten
    GROUP BY fahrzeug_id
)
SELECT
    f.kennzeichen,
    f.typ,
    f.baujahr,
    ROUND(k.kosten_eur, 2)                    AS kosten_eur,
    s.km                                      AS kilometer,
    ROUND(k.kosten_eur / s.km * 1000, 2)      AS eur_pro_1000_km
FROM fahrzeuge f
JOIN kosten  k ON k.fahrzeug_id = f.id
JOIN strecke s ON s.fahrzeug_id = f.id
WHERE s.km > 0
  AND f.typ <> 'Stapler'
ORDER BY eur_pro_1000_km DESC
LIMIT 10;


-- --------------------------------------------------------------------------
-- 3) Überfällige Termine, sortiert nach Tagen Verzug
--    julianday() rechnet Datumsdifferenzen in Tagen.
-- --------------------------------------------------------------------------
WITH parameter AS (SELECT '2026-10-10' AS stichtag)
SELECT
    f.kennzeichen,
    f.standort,
    t.art,
    t.faellig_am,
    CAST(julianday(p.stichtag) - julianday(t.faellig_am) AS INTEGER) AS tage_ueberfaellig
FROM termine t
JOIN fahrzeuge f ON f.id = t.fahrzeug_id
CROSS JOIN parameter p
WHERE t.erledigt = 'nein'
  AND t.faellig_am < p.stichtag
ORDER BY tage_ueberfaellig DESC;


-- --------------------------------------------------------------------------
-- 4) Termine in den nächsten 30 Tagen
-- --------------------------------------------------------------------------
WITH parameter AS (SELECT '2026-10-10' AS stichtag)
SELECT
    t.faellig_am,
    t.art,
    f.kennzeichen,
    f.typ,
    f.standort
FROM termine t
JOIN fahrzeuge f ON f.id = t.fahrzeug_id
CROSS JOIN parameter p
WHERE t.erledigt = 'nein'
  AND t.faellig_am BETWEEN p.stichtag AND date(p.stichtag, '+30 days')
ORDER BY t.faellig_am;


-- --------------------------------------------------------------------------
-- 5) Wartungskosten pro Monat und Jahr (Grundlage für das Monatsdiagramm)
--    strftime() zerlegt das ISO-Datum in Jahr und Monat.
-- --------------------------------------------------------------------------
SELECT
    strftime('%Y-%m', datum)   AS monat,
    COUNT(*)                   AS anzahl,
    ROUND(SUM(kosten_eur), 2)  AS kosten_eur
FROM wartungen
GROUP BY monat
ORDER BY monat;


-- --------------------------------------------------------------------------
-- 6) Kosten nach Fahrzeugtyp und Wartungsart (Pivot mit CASE WHEN)
-- --------------------------------------------------------------------------
SELECT
    f.typ,
    COUNT(DISTINCT f.id)                                                   AS fahrzeuge,
    ROUND(SUM(CASE WHEN w.art = 'Inspektion'    THEN w.kosten_eur ELSE 0 END), 0) AS inspektion,
    ROUND(SUM(CASE WHEN w.art = 'Reparatur'     THEN w.kosten_eur ELSE 0 END), 0) AS reparatur,
    ROUND(SUM(CASE WHEN w.art = 'Reifenwechsel' THEN w.kosten_eur ELSE 0 END), 0) AS reifen,
    ROUND(SUM(CASE WHEN w.art = 'Unfallschaden' THEN w.kosten_eur ELSE 0 END), 0) AS unfall,
    ROUND(SUM(w.kosten_eur) / COUNT(DISTINCT f.id), 0)                     AS kosten_pro_fahrzeug
FROM fahrzeuge f
JOIN wartungen w ON w.fahrzeug_id = f.id
GROUP BY f.typ
ORDER BY kosten_pro_fahrzeug DESC;


-- --------------------------------------------------------------------------
-- 7) Reparaturkosten nach Fahrzeugalter (zeigt: ältere Fahrzeuge = teurer)
--    Das Alter wird zum Zeitpunkt der Reparatur berechnet.
-- --------------------------------------------------------------------------
SELECT
    CASE
        WHEN CAST(strftime('%Y', w.datum) AS INTEGER) - f.baujahr <= 3 THEN '0-3 Jahre'
        WHEN CAST(strftime('%Y', w.datum) AS INTEGER) - f.baujahr <= 7 THEN '4-7 Jahre'
        ELSE '8+ Jahre'
    END                                   AS altersklasse,
    COUNT(*)                              AS reparaturen,
    ROUND(AVG(w.kosten_eur), 2)           AS durchschnitt_eur,
    ROUND(SUM(w.kosten_eur), 2)           AS summe_eur
FROM wartungen w
JOIN fahrzeuge f ON f.id = w.fahrzeug_id
WHERE w.art = 'Reparatur'
GROUP BY altersklasse
ORDER BY altersklasse;


-- --------------------------------------------------------------------------
-- 8) Standortvergleich: Fahrzeuge, Kilometer im letzten Jahr, Werkstattquote
--    Fensterfunktion RANK() ordnet die Standorte nach Fahrleistung.
-- --------------------------------------------------------------------------
WITH km_12_monate AS (
    SELECT fahrzeug_id, SUM(kilometer) AS km
    FROM fahrten
    WHERE monat >= '2025-10'
    GROUP BY fahrzeug_id
)
SELECT
    f.standort,
    COUNT(*)                                                         AS fahrzeuge,
    SUM(f.status = 'in Werkstatt')                                   AS in_werkstatt,
    COALESCE(SUM(k.km), 0)                                           AS km_letzte_12_monate,
    RANK() OVER (ORDER BY COALESCE(SUM(k.km), 0) DESC)               AS rang
FROM fahrzeuge f
LEFT JOIN km_12_monate k ON k.fahrzeug_id = f.id
GROUP BY f.standort
ORDER BY rang;
