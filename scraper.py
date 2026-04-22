#!/usr/bin/env python3
"""
Ferry Timetable Scraper — Thassos Ferry
Ανεβάζεις το PDF κάθε Κυριακή, τρέχεις το script, παίρνεις timetable.json.
Διαβάζει και τις δύο γραμμές: Κεραμωτή-Λιμένας (σελ.1) & Καβάλα-Πρίνος (σελ.2)
"""

import pdfplumber, json, re, sys

CO_MAP = {
    "THASSOS\nFERRIES":  "TF",
    "THASSOS FERRIES":   "TF",
    "THASSOS\nSEAWAYS":  "TS",
    "THASSOS SEAWAYS":   "TS",
    "THASSOSLINK":       "TL",
    "ANETH FERRIES":     "AF",
}

def parse_page(page):
    """Επιστρέφει (dates, from_left, from_right) από έναν πίνακα PDF."""
    tables = page.extract_tables()
    if not tables:
        return None, [], []

    t = tables[0]

    # Βρες header με ημερομηνίες
    dates = []
    for row in t:
        if row[0] and "FROM" in str(row[0]).upper():
            for cell in row[1:8]:
                m = re.search(r'(\d+)-(\d+)-(\d{4})', str(cell))
                if m:
                    dates.append(f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}")
                else:
                    dates.append(None)
            break

    from_left  = []  # FROM LIMENAS ή FROM PRINOS
    from_right = []  # FROM KERAMOTI ή FROM KAVALA

    for row in t:
        fl = str(row[0]).strip() if row[0] else ""
        fr = str(row[8]).strip() if len(row) > 8 and row[8] else ""

        # Skip headers
        if any(x in fl.upper() for x in ["FROM","LIMENAS","PRINOS","ΑΠΟ","DEPARTURES","ΠΙΝΑΚ","TIMETABLE","ROUTE","ΑΝΑΧΩ"]):
            continue
        if re.search(r'\d{4}', fl):
            continue

        ops = [CO_MAP.get(str(c).strip(), None) if c else None for c in row[1:8]]

        if re.match(r'\d{1,2}:\d{2}', fr):
            from_right.append([fr] + ops)

        if re.match(r'\d{1,2}:\d{2}', fl):
            from_left.append([fl] + ops)

    from_left.sort(key=lambda x: x[0])
    from_right.sort(key=lambda x: x[0])

    return dates, from_left, from_right


def main(pdf_path: str):
    print(f"Διαβάζω: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) < 1:
            raise RuntimeError("Κενό PDF")

        # Σελίδα 1: Κεραμωτή - Λιμένας
        dates1, from_thassos, from_keramoti = parse_page(pdf.pages[0])

        # Σελίδα 2: Καβάλα - Πρίνος
        from_prinos, from_kavala = [], []
        if len(pdf.pages) > 1:
            _, from_prinos, from_kavala = parse_page(pdf.pages[1])

    week_start = min(d for d in (dates1 or []) if d) if dates1 else "2026-01-01"
    week_end   = max(d for d in (dates1 or []) if d) if dates1 else "2026-01-07"

    timetable = {
        "week_start":    week_start,
        "week_end":      week_end,
        "days":          ["mon","tue","wed","thu","fri","sat","sun"],
        "from_keramoti": from_keramoti,
        "from_thassos":  from_thassos,
        "from_kavala":   from_kavala,
        "from_prinos":   from_prinos,
    }

    out = "timetable.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(timetable, f, ensure_ascii=False, indent=2)

    print(f"✅ {out}")
    print(f"   Εβδομάδα:      {week_start} → {week_end}")
    print(f"   Κεραμωτή→:    {len(from_keramoti)} δρομολόγια")
    print(f"   Λιμένας→:     {len(from_thassos)} δρομολόγια")
    print(f"   Καβάλα→:      {len(from_kavala)} δρομολόγια")
    print(f"   Πρίνος→:      {len(from_prinos)} δρομολόγια")


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "schedule.pdf"
    main(pdf)
