#!/usr/bin/env python3
"""
Ferry Timetable Scraper — Thassos Ferry
Τρέχει κάθε Κυριακή μέσω GitHub Actions.
Διαβάζει τον πίνακα δρομολογίων από την ANETH (εικόνα JPG)
χρησιμοποιώντας Claude Vision API και αποθηκεύει timetable.json.
"""

import os
import json
import base64
import requests
import anthropic
from bs4 import BeautifulSoup

ANETH_URL = "https://anethferries.gr/dromologia/"

def find_timetable_image(url: str) -> str | None:
    """Βρίσκει το URL της εικόνας δρομολογίων στη σελίδα ANETH."""
    print(f"Ψάχνω εικόνα στο {url}...")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"Σφάλμα κατά την ανάκτηση σελίδας: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    candidates = []

    for tag in soup.find_all(["img", "a"]):
        src = tag.get("src") or tag.get("href") or ""
        if not src:
            continue

        # Κάνε absolute URL
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://anethferries.gr" + src

        # Φίλτραρε: πρέπει να είναι από uploads και εικόνα
        if "uploads" not in src:
            continue
        if not any(src.lower().endswith(x) for x in [".jpg", ".jpeg", ".png"]):
            continue

        # Αποκλεισμός λογοτύπων και άλλων μη-δρομολογίων
        skip_keywords = ["logo", "icon", "flag", "avatar", "banner", "footer"]
        if any(kw in src.lower() for kw in skip_keywords):
            continue

        # Προτεραιότητα σε εικόνες που περιέχουν ημερομηνία (π.χ. 21-04-2026)
        import re
        has_date = bool(re.search(r'\d{2}-\d{2}-\d{4}', src))
        candidates.append((src, has_date))

    # Προτίμησε εικόνες με ημερομηνία
    dated = [s for s, has_date in candidates if has_date]
    if dated:
        print(f"Βρέθηκε (με ημερομηνία): {dated[0]}")
        return dated[0]

    # Fallback: πρώτη υποψήφια
    if candidates:
        print(f"Βρέθηκε (χωρίς ημερομηνία): {candidates[0][0]}")
        return candidates[0][0]

    print("Δεν βρέθηκε εικόνα.")
    return None


def read_timetable_from_image(image_url: str) -> dict | None:
    """
    Στέλνει την εικόνα στο Claude API και επιστρέφει
    τα δρομολόγια σε JSON format.
    """
    print(f"Κατεβάζω εικόνα: {image_url}")
    try:
        r = requests.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"Σφάλμα κατεβάσματος εικόνας: {e}")
        return None

    img_b64 = base64.standard_b64encode(r.content).decode("utf-8")

    # Καθόρισε media type
    url_lower = image_url.lower()
    if url_lower.endswith(".png"):
        media_type = "image/png"
    elif url_lower.endswith(".pdf"):
        print("PDF δεν υποστηρίζεται ακόμα — χρησιμοποίησε JPG.")
        return None
    else:
        media_type = "image/jpeg"

    prompt = """This is a Greek ferry timetable image.

Extract ALL departure times and the company that operates each departure for BOTH directions.

Return ONLY a JSON object in this COMPACT format (arrays instead of objects for days):

{
  "week_start": "YYYY-MM-DD",
  "week_end": "YYYY-MM-DD",
  "days": ["mon","tue","wed","thu","fri","sat","sun"],
  "from_keramoti": [
    ["04:30", "TF", "TL", "TS", "AF", "TF", "TL", "TS"],
    ["05:00", "TL", "TS", "AF", "TF", "TL", "TS", "AF"]
  ],
  "from_thassos": [
    ["04:30", "TF", "TL", "TS", "AF", "TF", "TL", "TS"],
    ["05:00", "TL", "TS", "AF", "TF", "TL", "TS", "AF"]
  ]
}

Each inner array: [time, mon, tue, wed, thu, fri, sat, sun]
Company codes: TF=Thassos Ferries, TL=Thassos Link, TS=Thassos Seaways, AF=Aneth Ferries
Use null if a company is not visible for that day/time.

IMPORTANT: Include ALL departures. Return ONLY the JSON, no other text."""

    print("Στέλνω στο Claude API...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        )
    except Exception as e:
        print(f"Σφάλμα Claude API: {e}")
        return None

    raw = message.content[0].text.strip()

    # Καθάρισε markdown code fences αν υπάρχουν
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    # Αν το JSON κόπηκε, προσπάθησε να το κλείσεις
    if not raw.endswith("}"):
        print("Προειδοποίηση: JSON φαίνεται κομμένο, προσπαθώ επιδιόρθωση...")
        # Μέτρα ανοιχτά/κλειστά brackets
        open_b = raw.count("{") - raw.count("}")
        open_sq = raw.count("[") - raw.count("]")
        # Κλείσε ανοιχτά arrays και objects
        raw = raw.rstrip(",\n ")
        for _ in range(open_sq):
            raw += "]"
        for _ in range(open_b):
            raw += "}"

    try:
        data = json.loads(raw)
        print(f"✅ Εβδομάδα: {data.get('week_start')} → {data.get('week_end')}")
        print(f"   Αναχωρήσεις από Κεραμωτή: {len(data.get('from_keramoti', []))}")
        print(f"   Αναχωρήσεις από Θάσο:     {len(data.get('from_thassos', []))}")
        return data
    except json.JSONDecodeError as e:
        print(f"Σφάλμα ανάλυσης JSON: {e}")
        print("Raw output (πρώτα 500 χαρακτήρες):", raw[:500])
        return None


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY δεν βρέθηκε στα environment variables.")

    # 1. Βρες την εικόνα
    image_url = find_timetable_image(ANETH_URL)
    if not image_url:
        raise RuntimeError("Δεν βρέθηκε εικόνα δρομολογίων.")

    # 2. Διάβασε τα δρομολόγια με Claude
    timetable = read_timetable_from_image(image_url)
    if not timetable:
        raise RuntimeError("Αποτυχία εξαγωγής δρομολογίων.")

    # 3. Αποθήκευσε
    out_path = "timetable.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(timetable, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Αποθηκεύτηκε: {out_path}")


if __name__ == "__main__":
    main()
