# -*- coding: utf-8 -*-
"""Scan semua cell roster yang punya note jam custom (nimpa jam baku)."""
import json
import re

HOURS_RE = re.compile(r"(\d{1,2})[.:](\d{2})\s*[-–—]\s*(\d{1,2})[.:](\d{2})")

with open("roster_sheet_cache.json", encoding="utf-8") as f:
    cache = json.load(f)

found = 0
for day, shifts in sorted(cache.get("days", {}).items()):
    for col, s in shifts.items():
        note = s.get("note") or ""
        if note and HOURS_RE.search(note):
            found += 1
            print(f"{day} {col:8} code={s['code']:4} "
                  f"hasil={s['start']}-{s['end']} note={note!r}")

print()
print("total cell dengan note jam custom:", found)
