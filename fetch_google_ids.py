# -*- coding: utf-8 -*-
"""
Helper: ambil Google user ID member Space (buat mention alert)
==============================================================
Google Chat cuma bisa mention pakai ID numerik:

    <users/123456789012345678>

Script ini menarik daftar member dari Google Chat API pakai service account
(credentials.json, app auth / scope chat.bot) lalu menyimpannya ke roster.json
supaya alert_match.py bisa mention orang yang sedang shift.

Prasyarat (sekali saja):
  1. Google Cloud project pemilik service account: aktifkan "Google Chat API".
  2. Chat API -> Configuration: isi App name, avatar, dan aktifkan
     "Enable interactive features" + "Join spaces and group conversations".
  3. Tambahkan Chat app (bot) ke Space tujuan sebagai member.
     Kalau bot belum jadi member space, API balas 403 PERMISSION_DENIED.
  4. Service account butuh role/akses Chat app (default: service account
     project yang sama dipakai sebagai app credential).

Usage:
  python fetch_google_ids.py                     # tarik member, tulis roster.json
  python fetch_google_ids.py --space <SPACE_ID>  # space lain
  python fetch_google_ids.py --print             # tampilkan saja, tidak menulis
  python fetch_google_ids.py --from-file member_ids.json
                                                 # pakai hasil collect_member_ids.js
"""

import argparse
import json
import os
import sys

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

HERE = os.path.dirname(os.path.abspath(__file__))

# Space tujuan (sama dengan space webhook di alert_match.py) - isi ID space Anda.
DEFAULT_SPACE = "<SPACE_ID>"

# App auth (bot). Butuh Chat app aktif + bot sudah join space.
SCOPES = ["https://www.googleapis.com/auth/chat.bot"]

CHAT_API = "https://chat.googleapis.com/v1"
PAGE_SIZE = 1000


def load_credentials():
    for path in (
        os.path.join(HERE, "credentials.json"),
        os.path.join(HERE, "..", "automation", "credentials.json"),
    ):
        if os.path.exists(path):
            return service_account.Credentials.from_service_account_file(
                path, scopes=SCOPES
            ), path
    raise SystemExit(
        "credentials.json tidak ditemukan.\n"
        "Letakkan file service account di folder ini, atau di ..\\automation\\credentials.json"
    )


def list_members(session, space):
    members = []
    page_token = None
    while True:
        params = {"pageSize": PAGE_SIZE}
        if page_token:
            params["pageToken"] = page_token
        resp = session.get(
            f"{CHAT_API}/spaces/{space}/members", params=params, timeout=30
        )
        if resp.status_code == 403:
            raise SystemExit(
                "403 PERMISSION_DENIED dari Chat API.\n"
                "Kemungkinan: Chat app belum aktif di project, atau bot belum\n"
                "di-add sebagai member ke Space ini."
            )
        if resp.status_code == 404:
            raise SystemExit(
                f"Space '{space}' tidak ditemukan / bot tidak punya akses."
            )
        resp.raise_for_status()
        data = resp.json()
        members.extend(data.get("memberships", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            return members


def simplify(members):
    """Ambil field yang dipakai roster: name (users/ID), displayName, email."""
    people = []
    for m in members:
        member = m.get("member", {})
        name = member.get("name", "")          # "users/1234567890"
        uid = name.split("/", 1)[1] if "/" in name else name
        if member.get("type") == "BOT":
            continue
        people.append(
            {
                "name": member.get("displayName") or uid,
                "google_id": uid,
                "email": member.get("email") or "",
                "role": m.get("role", "ROLE_MEMBER"),
            }
        )
    people.sort(key=lambda p: p["name"].lower())
    return people


def load_roster(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return {}


def merge_roster(roster, people, source):
    """Gabungkan google_id ke roster lama (match by email dulu, lalu nama)."""
    old = roster.get("people", [])
    by_email = {str(p.get("email", "")).lower(): p for p in old if p.get("email")}
    by_name = {str(p.get("name", "")).strip().lower(): p for p in old if p.get("name")}
    by_id = {str(p.get("google_id")): p for p in old if p.get("google_id")}

    merged = []
    for p in people:
        gid = str(p.get("google_id") or "").strip()
        if not gid.isdigit():
            continue
        prev = (
            by_id.get(gid)
            or by_email.get(str(p.get("email", "")).lower())
            or by_name.get(str(p.get("name", "")).strip().lower())
            or {}
        )
        merged.append(
            {
                "name": prev.get("name") or p.get("name") or gid,
                "email": p.get("email") or prev.get("email", ""),
                "google_id": gid,
                "sheet_aliases": prev.get("sheet_aliases", []),
                "shifts": prev.get("shifts", []),
                **({"always": prev["always"]} if "always" in prev else {}),
                **({"excluded": prev["excluded"]} if "excluded" in prev else {}),
            }
        )

    # orang lama yang tidak ada di sumber baru tetap disimpan
    seen = {m["google_id"] for m in merged}
    for p in old:
        if str(p.get("google_id") or "") not in seen:
            merged.append(p)

    merged.sort(key=lambda p: str(p.get("name", "")).lower())
    roster["_format"] = "Roster oncall LS-Konten"
    roster["_mention_syntax"] = "alert_match.py otomatis bungkus google_id jadi <users/{id}>"
    roster["_google_id_source"] = source
    roster["people"] = merged
    return roster


def normalize_from_file(path):
    """Baca hasil collect_member_ids.js: list of dict, atau dict email->id."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [
            {"google_id": v, "email": k} if isinstance(v, (str, int)) else dict(v)
            for k, v in data.items()
        ]
    people = []
    for p in data:
        p = dict(p)
        gid = p.get("google_id") or p.get("id") or p.get("userId") or p.get("user_id")
        if gid is None and str(p.get("name", "")).startswith("users/"):
            gid = str(p["name"]).split("/", 1)[1]
        people.append(
            {
                "google_id": str(gid or "").strip(),
                "name": p.get("name") or p.get("displayName") or "",
                "email": p.get("email") or "",
            }
        )
    return people


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default=DEFAULT_SPACE, help="ID space (tanpa 'spaces/')")
    ap.add_argument("--print", dest="just_print", action="store_true")
    ap.add_argument("--from-file", dest="from_file", help="JSON hasil collect_member_ids.js")
    ap.add_argument("--out", default=os.path.join(HERE, "roster.json"))
    args = ap.parse_args()

    if args.from_file:
        if not os.path.exists(args.from_file):
            raise SystemExit(f"File tidak ditemukan: {args.from_file}")
        people = normalize_from_file(args.from_file)
        valid = [p for p in people if p["google_id"].isdigit()]
        if not valid:
            raise SystemExit("Tidak ada google_id numerik di file itu.")
        roster = merge_roster(load_roster(args.out), valid, os.path.basename(args.from_file))
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"google_id terpasang: {len(valid)} -> {args.out}")
        print("Langkah berikutnya: isi 'shifts' tiap orang, lalu cek: python alert_match.py --who")
        return 0

    space = args.space.replace("spaces/", "").strip()
    creds, cred_path = load_credentials()
    print(f"credentials : {cred_path}")
    print(f"space       : spaces/{space}")

    session = AuthorizedSession(creds)
    people = simplify(list_members(session, space))
    print(f"member      : {len(people)} (bot di-skip)")

    if args.just_print:
        for p in people:
            print(f"  {p['google_id']:<24} {p['name']:<32} {p['email']}")
        return 0

    # Gabungkan dengan roster lama: shift yang sudah diisi user jangan hilang.
    roster = merge_roster(load_roster(args.out), people, f"chat-api:spaces/{space}")
    roster["space"] = f"spaces/{space}"

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"tersimpan  : {args.out}")
    print("Langkah berikutnya: isi 'shifts' tiap orang sesuai jadwal kerja.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
