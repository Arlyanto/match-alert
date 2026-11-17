# -*- coding: utf-8 -*-
"""Kirim pesan TEST berformat alert asli + mention orang yang sedang shift.

Dijalankan Task Scheduler one-shot (lihat README):
  - jam 20:15 -> cek bunyi + mention jaga sore (H-12)
  - jam 02:15 -> cek bunyi + mention jaga malam (H-6)

Ini TEST, bukan alert beneran - selalu ditandai di pesan. Isi match pakai
data asli dari section (match lolos gerbang channel kalau ada; kalau tidak,
NFL channel "NFL" sebagai contoh isi dengan package [598]).
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alert_match as a

MARKER = (
    "_(TEST - simulasi alert H-12/H-6, bukan alert beneran; "
    "match di channel di luar mapping tidak di-alert)_"
)


def pick_example(items, hits):
    """Match contoh: yang lolos gerbang (paling dekat kickoff), fallback NFL."""
    candidates = [h for h in hits if h.get("kickoff_dt")] or list(hits)
    if candidates:
        candidates.sort(key=lambda h: h["kickoff_dt"])
        return candidates[0]
    parsed = [a.parse_item(it) for it in items]
    nfl = [x for x in parsed if "nfl" in (x["title"] or "").lower()]
    if not nfl:
        return None
    nfl.sort(key=lambda x: x["kickoff"] or "9999")
    m = nfl[0]
    # Channel "NFL" kena gerbang (bukan Champions TV 1-3), jadi package asli
    # None -> isi manual biar contoh pesan tetap informatif.
    m["league"] = "NFL"
    m["package"] = "[598] [Platinum Extra] NFL Live & VOD"
    return m


def main():
    dry = "--dry-run" in sys.argv
    now = datetime.now(a.WIB)
    stamp = now.strftime("%Y-%m-%d %H:%M WIB")

    if a.AES_KEY.startswith(b"<"):
        # Mode Showcase: rahasia placeholder -> pakai data contoh, tidak kirim.
        print(f"[{stamp}] Mode Showcase (rahasia placeholder) -> data contoh, tidak dikirim.")
        items = a.demo_items()
        dry = True
    else:
        items = a.fetch_matches()
    hits, _skipped = a.collect_hits(items)
    m = pick_example(items, hits)
    if not m:
        print(f"[{stamp}] tidak ada contoh match untuk pesan test.")
        return 1

    people = a.active_people(now)
    text = a.build_message(m, people) + "\n\n" + MARKER

    if dry or "<" in a.GOOGLE_WEBHOOK_URL:
        if not dry and "<" in a.GOOGLE_WEBHOOK_URL:
            print(f"[{stamp}] webhook placeholder (Mode Showcase) -> tampil saja, tidak dikirim.")
        print(f"[{stamp}] tidak dikirim, mention {len(people)} orang:")
        print(text)
        return 0
    code = a.send_alert(text)
    names = ", ".join(p["name"] for p in people) or "(tanpa mention)"
    print(f"[{stamp}] TEST terkirim HTTP {code}, mention {len(people)}: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
