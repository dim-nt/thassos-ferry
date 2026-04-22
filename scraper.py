#!/usr/bin/env python3
"""
Ferry Timetable Scraper — Thassos Ferry
Τρέχει κάθε Κυριακή μέσω GitHub Actions.
"""

import os, json, base64, re, requests
import anthropic
from bs4 import BeautifulSoup

ANETH_URL = "https://anethferries.gr/dromologia/"


def find_timetable_image(url: str) -> str | None:
    print(f"Ψάχνω εικόνα στο {url}...")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"Σφάλμα σελίδας: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    candidates = []

    for tag in soup.find_all(["img", "a"]):
        src = tag.get("src") or tag.get("href") or ""
        if not src or "uploads" not in src:
            continue
        if not any(src.lower().endswith(x) for x in [".jpg", ".jpeg", ".png"]):
            continue
        if src.startswith("//"): src = "https:" + src
        elif src.startswith("/"): src = "https://anethferries.gr" + src

        skip = ["logo", "icon", "flag", "avatar", "banner", "footer"]
        if any(k in src.lower() for k in skip):
            continue

        has_date = bool(re.search(r'\d{2}-\d{2}-\d{4}', src))
        candidates.append((src, has_date))

    dated = [s for s, d in candidates if d]
    if dated:
        print(f"Βρέθηκε: {dated[0]}")
        return dated[0]
    if candidates:
        print(f"Βρέθηκε (fallback): {candidates[0][0]}")
        return candidates[0][0]

    print("Δεν βρέθηκε εικόνα.")
    return None


def call_claude(client, img_b64: str, media_type: str, direction: str) -> list | None:
    """Μία κλήση για μία κατεύθυνση."""
    if direction == "keramoti":
        side = "FROM KERAMOTI (right side, column header: ΑΠΟ ΚΕΡΑΜΩΤΗ)"
    else:
        side = "FROM THASSOS/LIMENAS (left side, column header: ΑΠΟ ΛΙΜΕΝΑ)"

    prompt = f"""Greek ferry timetable image. Extract ONLY: {side}

Return ONLY a JSON array. Each element: ["HH:MM","MON","TUE","WED","THU","FRI","SAT","SUN"]
Codes: TF=Thassos Ferries, TL=Thassos Link, TS=Thassos Seaways, AF=Aneth Ferries, null=unclear.
Include ALL rows. Return ONLY the array, no other text, no markdown."""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=6000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                {"type": "text", "text": prompt}
            ]}]
        )
    except Exception as e:
        print(f"  Σφάλμα API ({direction}): {e}")
        return None

    raw = msg.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
        raw = raw.strip()

    # Επιδιόρθωση κομμένου array
    if not raw.endswith("]"):
        print(f"  Κομμένο JSON ({direction}), επιδιόρθωση...")
        raw = raw.rstrip(",\n ")
        open_sq = raw.count("[") - raw.count("]")
        raw += "]" * open_sq

    try:
        data = json.loads(raw)
        print(f"  ✅ {direction}: {len(data)} δρομολόγια")
        return data
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON error ({direction}): {e}")
        print(f"  Raw: {raw[:300]}")
        return None


def read_timetable_from_image(image_url: str) -> dict | None:
    print(f"Κατεβάζω εικόνα...")
    try:
        r = requests.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"Σφάλμα κατεβάσματος: {e}")
        return None

    img_b64 = base64.standard_b64encode(r.content).decode("utf-8")
    media_type = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("Κλήση 1: από Κεραμωτή...")
    from_k = call_claude(client, img_b64, media_type, "keramoti")

    print("Κλήση 2: από Θάσο...")
    from_t = call_claude(client, img_b64, media_type, "thassos")

    if not from_k or not from_t:
        return None

    # Εξαγωγή ημερομηνιών από URL
    dates = re.findall(r'(\d{2}-\d{2}-\d{4})', image_url)
    def to_iso(d): return f"{d[6:]}-{d[3:5]}-{d[:2]}"
    week_start = to_iso(dates[0]) if len(dates) >= 1 else "2026-01-01"
    week_end   = to_iso(dates[1]) if len(dates) >= 2 else "2026-01-07"

    return {
        "week_start": week_start,
        "week_end": week_end,
        "days": ["mon","tue","wed","thu","fri","sat","sun"],
        "from_keramoti": from_k,
        "from_thassos": from_t
    }


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise EnvironmentError("ANTHROPIC_API_KEY λείπει.")

    image_url = find_timetable_image(ANETH_URL)
    if not image_url:
        raise RuntimeError("Δεν βρέθηκε εικόνα.")

    timetable = read_timetable_from_image(image_url)
    if not timetable:
        raise RuntimeError("Αποτυχία εξαγωγής.")

    with open("timetable.json", "w", encoding="utf-8") as f:
        json.dump(timetable, f, ensure_ascii=False, indent=2)

    print(f"\n✅ timetable.json αποθηκεύτηκε")
    print(f"   Εβδομάδα: {timetable['week_start']} → {timetable['week_end']}")
    print(f"   Κεραμωτή: {len(timetable['from_keramoti'])} δρομολόγια")
    print(f"   Θάσος:    {len(timetable['from_thassos'])} δρομολόγια")


if __name__ == "__main__":
    main()
