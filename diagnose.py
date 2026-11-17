# -*- coding: utf-8 -*-
"""Diagnostik read-only: tampilkan match target + status jendela H-12/H-6."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
import alert_match as a

if a.AES_KEY.startswith(b"<"):
    print("(Mode Showcase: rahasia placeholder -> memakai data contoh)")
    items = a.demo_items()
else:
    items = a.fetch_matches()
hits, skipped = a.collect_hits(items)
now = datetime.now(a.WIB)
alerted = a.load_alerted()

print("now      =", now.strftime("%Y-%m-%d %H:%M WIB"))
print("items    =", len(items), "| target =", len(hits), "| skipped =", len(skipped))
print("alerted  =", sorted(alerted))
for s in skipped:
    print(f"SKIP [{s['league']}] {s['title']} @ channel {s['channel'] or '(kosong)'}")
print()

for m in hits:
    kdt = m.get("kickoff_dt")
    k12 = m["id"] + ":12h"
    k6 = m["id"] + ":6h"
    if not kdt:
        w = "!!! NO kickoff_dt -> TIDAK AKAN PERNAH di-alert"
    elif now >= kdt:
        w = "kickoff sudah lewat"
    else:
        h12 = kdt - timedelta(hours=12)
        h6 = kdt - timedelta(hours=6)
        w = (
            f"H-12 window: {h12:%d %b %H:%M}-{h6:%d %b %H:%M} | "
            f"H-6 window: {h6:%d %b %H:%M}-{kdt:%d %b %H:%M} | "
            f"key12_sent={k12 in alerted} key6_sent={k6 in alerted}"
        )
    print(f"[{m['league']}] {m['title']}")
    print(f"   channel = {m['channel']}")
    print(f"   package = {m['package']}")
    print(f"   kickoff = {m['kickoff']!r}")
    print(f"   url     = {m['url']}")
    print(f"   -> {w}")
    print()
