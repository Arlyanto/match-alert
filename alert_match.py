# -*- coding: utf-8 -*-
"""
Paket Checking (Match Package Alert)
====================================
Monitor halaman publik "Pertandingan Hari Ini" (Vidio section 4840) lewat API
publiknya (tanpa login), lalu kirim alert "Paket checking" ke Google Space
untuk match: F1, Serie A, Ligue 1, Premier League, NFL (di channel yang
diizinkan saja - lihat Mapping paket di bawah).

Acuan data  : https://www.vidio.com/sections/4840-pertandingan-hari-ini
              (link match yang dikirim = link halaman match hasil klik,
               formatnya https://www.vidio.com/live/<channel>?schedule_id=...)

Isi alert   : headline "Paket checking", channel, program, paket yang harus
              terinfo, kickoff, link match, dan mention orang yang SEDANG SHIFT.

Mapping paket (sesuai request) - hanya channel berikut yang di-alert:
  F1            di Bein 1            -> [134] [Platinum Extra] F1 Livestreaming & VOD
  Serie A       di Champions TV 1-3  -> [493] [Platinum Extra] Serie A
  Premier League di Champions TV 5/6 -> [157] [Ultimate] EPL
  Ligue 1       di Champions TV 1-3/5/6 -> [803] [Platinum Extra] Ligue 1
  NFL           di Champions TV 1-3  -> [598] [Platinum Extra] NFL Live & VOD

Match liga target di channel DI LUAR daftar di atas TIDAK di-alert
(mis. NFL di channel "NFL" -> tidak ada alert).

Mention     : Google Chat hanya bisa mention pakai ID numerik -> <users/123...>.
              Daftar orang + jadwal shift ada di roster.json.
              Isi ID otomatis: python fetch_google_ids.py
              (atau tempel hasil console snippet collect_member_ids.js).

Jadwal      : cek tiap 1 menit (Task Scheduler minute) supaya alert BENAR
              berbunyi tepat di H-12 dan H-6 sebelum kickoff (±1 menit).
              Polling tiap menit BUKAN kirim tiap menit - pesan tetap max
              2x per match: sekali di H-12, sekali di H-6 (dedup alerted.json).
              Task Scheduler:
                schtasks /create /tn "Paket Checking" /tr "run.bat" /sc minute /mo 1

Usage       : python alert_match.py              -> cek + kirim alert match baru
              python alert_match.py --dry-run    -> tampilkan, tidak kirim
              python alert_match.py --demo       -> MODE DEMO: data contoh,
                                                    tidak jaringan, tidak kirim
              python alert_match.py --who        -> siapa yang sedang shift
              python alert_match.py --test-mention -> kirim 1 pesan tes mention
              python alert_match.py --self-test  -> tes format tanpa jaringan

Catatan showcase: rahasia (webhook, ID sheet, kunci AES, key cadangan) sudah
diganti placeholder "<...>" - tanpa diisi, skrip otomatis tidak pernah mengirim.
"""

import base64
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from datetime import date, datetime, timezone, timedelta

import requests

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

# Webhook incoming Google Chat (Incoming webhook Space tujuan).
# ISI DENGAN URL WEBHOOK ANDA sendiri, atau lewat env GOOGLE_WEBHOOK_URL.
# Placeholder "<...>" dikenali skrip = Mode Showcase: tidak pernah kirim.
GOOGLE_WEBHOOK_URL = os.environ.get(
    "GOOGLE_WEBHOOK_URL",
    "https://chat.googleapis.com/v1/spaces/<SPACE_ID>/messages"
    "?key=<API_KEY>&token=<TOKEN>",
)

SECTION_API = "https://api.vidio.com/sections/4840-pertandingan-hari-ini?content_size=50"

# Header agar diterima API publik vidio (diambil dari panggilan asli web vidio.com).
HEADERS = {
    "accept": "application/json",
    "accept-language": "en",
    "content-type": "application/vnd.api+json",
    "referer": "https://www.vidio.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "x-api-app-info": "js/www.vidio.com",
    "x-api-platform": "web-desktop",
    "x-secure-level": "2",
    "x-user-login": "false",
}

# ---------------------------------------------------------------------------
# AUTO-REFRESH x-api-key
# ---------------------------------------------------------------------------
# Vidio TIDAK menaruh key di kode JS. Web-nya ambil key dari POST
# www.vidio.com/auth -> {api_key: JWT, api_key_expires_at} (lihat bundle JS
# "fetchApiKey"), lalu mengenkripsi JWT itu dengan AES-256-CBC memakai key/iv
# publik berikut sebelum dikirim sebagai header x-api-key.
# Key kedaluwarsa HARIAN (mis. 2026-11-16 23:59) -> script regenerate sendiri.
AUTH_URL = "https://www.vidio.com/auth"
KEY_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "vidio_api_key.json"
)
KEY_REFRESH_MARGIN = 300  # detik sebelum kedaluwarsa -> sudah di-refresh
# Kunci AES-256 (32 byte) + IV (16 byte) untuk mengenkripsi JWT jadi x-api-key.
# Keduanya dipublikasikan di bundle JS publik www.vidio.com (bukan rahasia
# server) - isi dengan nilai yang Anda baca sendiri dari bundle tersebut.
AES_KEY = b"<32_BYTE_AES_KEY_DARI_BUNDLE_JS>"
AES_IV = b"<16_BYTE_AES_IV>"
# Key cadangan kalau POST /auth gagal total (opsional; isi hasil capture Anda).
FALLBACK_X_API_KEY = "<X_API_KEY_HASIL_CAPTURE_MANUAL_ATAU_KOSONG>"
AUTH_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "referer": "https://www.vidio.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "x-api-app-info": "js/www.vidio.com",
    "x-api-platform": "web-desktop",
    "x-secure-level": "2",
    "x-user-login": "false",
}

WIB = timezone(timedelta(hours=7))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.environ.get("ALERT_STATE_FILE") or os.path.join(HERE, "alerted.json")
ROSTER_FILE = os.environ.get("ROSTER_FILE") or os.path.join(HERE, "roster.json")

# ---------------------------------------------------------------------------
# ROSTER SHIFT DARI GOOGLE SHEETS
# ---------------------------------------------------------------------------
# Sheet roster shift (contoh: tab "New Shift Schedule").
# Layout: baris = tanggal, kolom = nama panggilan, cell note = jam custom.
ROSTER_SHEET_ID = os.environ.get(
    "ROSTER_SHEET_ID", "<SPREADSHEET_ID_ROSTER>"
)
ROSTER_SHEET_TAB = os.environ.get("ROSTER_SHEET_TAB", "New Shift Schedule")
ROSTER_SHEET_RANGE = "A1:AO400"
ROSTER_SHEET_CACHE = os.path.join(HERE, "roster_sheet_cache.json")
SHEET_CACHE_TTL = 600  # detik; 10 menit

# Jam baku per kode shift di sheet. Note custom di cell menimpa jam ini.
SHIFT_CODES = {
    "P":   ("09:00", "21:00"),
    "NS":  ("09:00", "19:00"),
    "MD":  ("11:00", "23:00"),
    "M":   ("21:00", "09:00"),   # lewat tengah malam
    "MDO": ("12:00", "21:00"),   # 9 jam (overtime); biasanya ada note custom
}

# Kode/teks yang artinya TIDAK bekerja (tidak di-mention).
INACTIVE_RE = re.compile(
    r"\b(cuti|off|sakit|libur|izin|leave|half|switch|ph|mh|po|mo|absent)\b", re.I
)
HOURS_RE = re.compile(
    r"(\d{1,2})[.:](\d{2})\s*[-\u2013\u2014]\s*(\d{1,2})[.:](\d{2})"
)
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6,
    "jul": 7, "agu": 8, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
    "nov": 11, "des": 12, "dec": 12,
}

# ---------------------------------------------------------------------------
# DETEKSI LIGA
# ---------------------------------------------------------------------------
# (kode, label tampil, pattern). Judul di halaman vidio biasanya berbentuk
# "Arsenal vs Chelsea - Premier League", "F1: Sao Paulo GP", dst.
LEAGUE_RULES = [
    ("F1",        "F1",           r"\bF1\b|Formula\s*1|Formula\s*One"),
    ("EPL",       "Premier League", r"\bEPL\b|Premier\s*League"),
    ("Ligue 1",   "Ligue 1",      r"Ligue\s*1|Ligue1|Ligue\s*One"),
    ("Serie A",   "Serie A",      r"\bSerie\s*A\b"),
    ("NFL",       "NFL",          r"\bNFL\b"),
]

# Judul yang mengandung ini DI-skip (anti false positive: voli/basket/futsal).
TITLE_EXCLUDE = (
    r"Volley|Volleyball|Serie\s*A1|Serie\s*A2|Futsal|Lega\s*Basket|"
    r"Basket\s*Serie|Women'?s\s+Serie"
)

# ---------------------------------------------------------------------------
# MAPPING PAKET (per channel tempat match tayang)
# ---------------------------------------------------------------------------
PACKAGE_RULES = [
    ("F1",      ["bein 1"], "[134] [Platinum Extra] F1 Livestreaming & VOD"),
    ("Serie A", ["champions tv 1", "champions tv 2", "champions tv 3"],
     "[493] [Platinum Extra] Serie A"),
    ("EPL",     ["champions tv 5", "champions tv 6"], "[157] [Ultimate] EPL"),
    ("Ligue 1", ["champions tv 1", "champions tv 2", "champions tv 3",
                 "champions tv 5", "champions tv 6"], "[803] [Platinum Extra] Ligue 1"),
    ("NFL",     ["champions tv 1", "champions tv 2", "champions tv 3"],
     "[598] [Platinum Extra] NFL Live & VOD"),
]

LEAGUE_LABEL = {code: label for code, label, _ in LEAGUE_RULES}
PACKAGE_UNKNOWN = "cek manual — channel di luar mapping rule"

# ---------------------------------------------------------------------------
# TEMPLATE PESAN
# ---------------------------------------------------------------------------
ALERT_TEXT = (
    "⚠️ CEK PAKET PERTANDINGAN ⚠️\n"
    "Checking Paket\n"
    "• Match: {title}\n"
    "• Liga: {league}\n"
    "• Channel: {channel}\n"
    "• Info: Paket harus: {package}\n"
    "• Kickoff: {kickoff} WIB\n"
    "🔗 Link Page: {url}"
)

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ----------------------------------------------------------------------------
# API VIDIO
# ----------------------------------------------------------------------------

def _encrypt_api_key(jwt_text):
    """Enkripsi JWT dari /auth jadi x-api-key (AES-256-CBC + PKCS7 -> base64).

    Persis seperti halaman web vidio: aesEncrypt(jwt, publicKey, publicIv).
    """
    data = jwt_text.encode("utf-8")
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad  # PKCS7 (default node crypto)
    try:
        from cryptography.hazmat.primitives.ciphers import (
            Cipher, algorithms, modes,
        )
        enc = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV)).encryptor()
        ct = enc.update(data) + enc.finalize()
    except ImportError:  # pycryptodome sebagai cadangan
        from Crypto.Cipher import AES
        ct = AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(data)
    return base64.b64encode(ct).decode("ascii")


def get_api_key(force=False):
    """x-api-key segar dari POST /auth (kedaluwarsa harian), di-cache ke file.

    force=True -> regenerasi sekalipun cache masih berlaku (dipakai saat 401).
    Kalau /auth gagal, jatuh ke key cache lama / key cadangan supaya run tetap
    jalan; run berikutnya (tiap menit) coba refresh lagi.
    """
    cached = None
    try:
        with open(KEY_CACHE_FILE, encoding="utf-8") as fh:
            cached = json.load(fh)
    except (OSError, ValueError):
        pass
    now = time.time()
    if (
        not force
        and cached
        and cached.get("key")
        and float(cached.get("expires_at") or 0) - now > KEY_REFRESH_MARGIN
    ):
        return cached["key"]

    try:
        resp = requests.post(AUTH_URL, headers=AUTH_HEADERS, json={}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        key = _encrypt_api_key(payload["api_key"])
        expires_at = 0.0
        raw_exp = payload.get("api_key_expires_at")
        if raw_exp:
            try:
                expires_at = datetime.fromisoformat(raw_exp).timestamp()
            except ValueError:
                pass
        try:
            with open(KEY_CACHE_FILE, "w", encoding="utf-8") as fh:
                json.dump(
                    {"key": key, "expires_at": expires_at, "fetched_at": now}, fh
                )
        except OSError:
            pass
        return key
    except Exception as e:
        old = cached.get("key") if cached else None
        print(
            f"WARN refresh x-api-key gagal ({e.__class__.__name__}) - "
            f"pakai {'key cache lama' if old else 'key cadangan'}"
        )
        return old or FALLBACK_X_API_KEY


def fetch_matches():
    """Ambil daftar match dari API publik section 4840 (isi halaman acuan).

    x-api-key di-refresh otomatis (POST /auth) kalau kedaluwarsa / kena 401.
    Error jaringan/SSL transien di-retry 3x (jeda 10 detik) sebelum gagal;
    run berikutnya (tiap menit) tetap jadi safety net.
    """
    key = get_api_key()
    resp = None
    for attempt in range(3):
        try:
            resp = requests.get(
                SECTION_API, headers={**HEADERS, "x-api-key": key}, timeout=30
            )
            break
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(
                f"WARN fetch gagal (percobaan {attempt + 1}/3): "
                f"{e.__class__.__name__} - retry 10 detik"
            )
            time.sleep(10)
    if resp.status_code == 401:
        # Key kedaluwarsa atau diputar vidio -> regenerasi lalu coba sekali lagi.
        print("WARN x-api-key ditolak (401) - regenerasi key otomatis...")
        key = get_api_key(force=True)
        try:
            resp = requests.get(
                SECTION_API, headers={**HEADERS, "x-api-key": key}, timeout=30
            )
        except requests.RequestException as e:
            raise RuntimeError(
                "API menolak (401) dan regenerasi key gagal jaringan: "
                f"{e.__class__.__name__}"
            ) from e
        if resp.status_code == 401:
            raise RuntimeError(
                "API menolak (401) SETELAH regenerasi x-api-key - "
                "cek manual POST www.vidio.com/auth."
            )
    resp.raise_for_status()
    return resp.json().get("included", [])


# ----------------------------------------------------------------------------
# MODE DEMO (data contoh - tanpa jaringan, tanpa credential)
# ----------------------------------------------------------------------------

def demo_items(now=None):
    """Daftar match contoh berformat JSON:API (sama seperti respons section 4840).

    Kickoff dibuat relatif terhadap waktu sekarang supaya jendela H-12 / H-6
    bisa didemonstrasikan kapan pun script dijalankan.
    """
    now = now or datetime.now(WIB)

    def iso(hours_from_now):
        return (now + timedelta(hours=hours_from_now)).strftime(
            "%Y-%m-%dT%H:%M:00+07:00"
        )

    def item(cid, title, channel, hours, url):
        return {
            "id": cid,
            "attributes": {
                "content_id": cid,
                "title": title,
                "alt_title": "",
                "livestreaming_title": channel,
                "web_url": url,
                "start_time": iso(hours),
            },
        }

    return [
        # -> jendela H-12 (kickoff +8 jam): alert H-12 terpicu
        item("d1", "Sao Paulo Grand Prix - F1", "Bein 1", 8,
             "https://www.vidio.com/live/6299?schedule_id=d1"),
        # -> jendela H-6 (kickoff +4 jam): alert H-6 terpicu
        item("d2", "Arsenal vs Chelsea - Premier League", "Champions TV 5", 4,
             "https://www.vidio.com/live/9182?schedule_id=d2"),
        # -> belum masuk jendela (kickoff +30 jam): belum dikirim
        item("d3", "Juventus vs Napoli - Serie A", "Champions TV 2", 30,
             "https://www.vidio.com/live/6686?schedule_id=d3"),
        # -> liga target tapi channel di luar mapping: SKIP (gerbang channel)
        item("d4", "PSG vs Marseille - Ligue 1", "Champions TV 4", 10,
             "https://www.vidio.com/live/9183?schedule_id=d4"),
        # -> NFL di channel "NFL": SKIP (gerbang channel)
        item("d5", "Indianapolis Colts vs Houston Texans - NFL", "NFL", 5,
             "https://www.vidio.com/live/7777?schedule_id=d5"),
        # -> bukan liga target (voli): tidak dikenali, tidak di-alert
        item("d6", "Igor Gorgonzola vs Conegliano - Italian Women's "
                   "Volleyball Serie A1", "Champions TV 1", 6,
             "https://www.vidio.com/live/6685?schedule_id=d6"),
    ]


def detect_league(*texts):
    """Return kode liga kalau salah satu teks mengandung keyword liga target."""
    haystack = " ".join(t for t in texts if t)
    if not haystack:
        return None
    if re.search(TITLE_EXCLUDE, haystack, flags=re.I):
        return None
    for code, _label, pattern in LEAGUE_RULES:
        if re.search(pattern, haystack, flags=re.I):
            return code
    return None


def parse_item(item):
    """Ubah item JSON:API jadi dict ringkas."""
    attr = item.get("attributes", {})
    start = attr.get("start_time") or ""
    kickoff = ""
    kickoff_dt = None
    if start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            kickoff_dt = dt.astimezone(WIB)
            kickoff = kickoff_dt.strftime("%d %b %Y %H:%M")
        except ValueError:
            kickoff = start
    return {
        "id": str(attr.get("content_id") or item.get("id")),
        "title": (attr.get("title") or "").strip(),
        "alt": (attr.get("alt_title") or "").strip(),
        "channel": (attr.get("livestreaming_title") or "").strip(),
        "url": attr.get("web_url") or "",
        "kickoff": kickoff,
        "kickoff_dt": kickoff_dt,
    }


def expected_package(league, channel):
    """Paket yang harus terinfo untuk combo liga+channel, atau None."""
    ch = " ".join((channel or "").lower().split())
    for code, channels, pkg in PACKAGE_RULES:
        if code == league and any(c in ch for c in channels):
            return pkg
    return None


# ----------------------------------------------------------------------------
# ROSTER / SHIFT
# ----------------------------------------------------------------------------

def load_roster():
    if not os.path.exists(ROSTER_FILE):
        return []
    try:
        with open(ROSTER_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError) as e:
        print(f"WARN roster.json tidak terbaca: {e}")
        return []
    return data.get("people", [])


def _hm(value, default):
    try:
        h, m = str(value).split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return default


def is_on_shift(shift, now):
    """Cek 1 shift. Shift lewat tengah malam (start > end) didukung."""
    days = [str(d).lower()[:3] for d in (shift.get("days") or DAY_NAMES)]
    start = _hm(shift.get("start"), 0)
    end = _hm(shift.get("end"), 24 * 60 - 1)
    t = now.hour * 60 + now.minute
    today = DAY_NAMES[now.weekday()]
    if start == end:  # shift 24 jam
        return today in days
    if start < end:
        return today in days and start <= t < end
    # lewat tengah malam: 22:00-06:00
    if t >= start:
        return today in days
    yday = DAY_NAMES[(now.weekday() - 1) % 7]
    return yday in days and t < end


def active_people(now=None, verbose=False):
    """Orang yang sedang kerja sekarang menurut jadwal di Google Sheets.

    Fallback ke (field "shifts" di roster.json) kalau sheet tidak bisa dibaca.
    """
    now = now or datetime.now(WIB)
    people = load_roster()
    sched = get_sheet_schedule()
    if sched is not None:
        return _active_from_sheet(people, sched, now, verbose=verbose)
    return _active_from_file(people, now)


def _active_from_file(people, now):
    result = []
    for p in people:
        if p.get("always") is True:
            result.append(p)
        elif any(is_on_shift(s, now) for s in (p.get("shifts") or [])):
            result.append(p)
    return result


# --- Google Sheets ---------------------------------------------------------

def _sheet_credentials():
    from google.oauth2 import service_account

    paths = [
        os.path.join(HERE, "credentials.json"),
        os.path.join(HERE, "..", "automation", "credentials.json"),
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "",
    ]
    for path in paths:
        if path and os.path.exists(path):
            return service_account.Credentials.from_service_account_file(
                path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
            )
    raise RuntimeError("credentials.json service account tidak ditemukan.")


def fetch_sheet_rows():
    """Ambil grid + cell note dari tab roster (1 request)."""
    from google.auth.transport.requests import AuthorizedSession

    session = AuthorizedSession(_sheet_credentials())
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{ROSTER_SHEET_ID}"
    resp = session.get(
        url,
        params={
            "ranges": f"{ROSTER_SHEET_TAB}!{ROSTER_SHEET_RANGE}",
            "includeGridData": "true",
            "fields": "sheets(data(rowData(values(note,formattedValue))))",
        },
        timeout=60,
    )
    if resp.status_code == 403:
        raise PermissionError(
            "Sheet roster belum di-share ke service account "
            "(<service-account>@<project>.iam.gserviceaccount.com)."
        )
    resp.raise_for_status()
    data = resp.json()
    grid = data["sheets"][0]["data"][0].get("rowData", [])
    rows = []
    for row in grid:
        cells = []
        for cell in row.get("values", []):
            cells.append((cell.get("formattedValue", ""), cell.get("note", "")))
        rows.append(cells)
    return rows


def parse_sheet_date(text):
    s = str(text or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{1,2})[-/ ]([A-Za-z]{3,})[-/ ](\d{2,4})", s)
    if m:
        day, mon, year = m.groups()
        month = MONTHS.get(mon.lower()[:3])
        if not month:
            return None
        year = int(year) + (2000 if len(year) == 2 else 0)
        try:
            return date(year, month, int(day))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_sheet(rows):
    """Ubah grid jadi {tanggal: {kolom: {code, start, end}}}."""
    header_idx = None
    for i, row in enumerate(rows):
        if row and str(row[0][0]).strip().lower().startswith("date"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("baris header 'Date' tidak ditemukan di sheet roster")

    columns = []
    for ci, cell in enumerate(rows[header_idx][1:], start=1):
        name = str(cell[0]).strip()
        if name.lower() == "legends":
            break
        if name:
            columns.append((ci, name))

    days, warnings = {}, []
    for row in rows[header_idx + 1:]:
        if not row:
            continue
        day = parse_sheet_date(row[0][0])
        if not day:
            continue
        shifts = {}
        for ci, col_name in columns:
            if ci >= len(row):
                continue
            raw, note = row[ci]
            code = str(raw).strip()
            if not code:
                continue
            note = str(note or "").strip()
            code_up = code.upper().split("/")[0].strip()

            if INACTIVE_RE.search(note) or INACTIVE_RE.search(code_up):
                continue

            m = HOURS_RE.search(note)
            if m:
                start = f"{int(m.group(1)):02d}:{m.group(2)}"
                end = f"{int(m.group(3)):02d}:{m.group(4)}"
            elif code_up in SHIFT_CODES:
                start, end = SHIFT_CODES[code_up]
            else:
                warnings.append(f"{day} {col_name}: kode '{code}' tidak dikenal (di-skip)")
                continue

            shifts[col_name] = {
                "code": code_up,
                "start": start,
                "end": end,
                "note": note,
            }
        days[day.isoformat()] = shifts

    return {
        "days": days,
        "columns": [name for _, name in columns],
        "warnings": warnings[:20],
        "_ts": time.time(),
    }


def _load_sheet_cache():
    if not os.path.exists(ROSTER_SHEET_CACHE):
        return None
    try:
        with open(ROSTER_SHEET_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def _save_sheet_cache(data):
    try:
        with open(ROSTER_SHEET_CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def get_sheet_schedule(use_cache=True):
    """Jadwal dari sheet; cache 10 menit; fallback ke cache lama kalau error."""
    if "<" in str(ROSTER_SHEET_ID):
        # Mode Showcase: ID sheet placeholder -> langsung pakai roster.json
        # (fallback 'shifts'), tanpa menyentuh jaringan.
        return None
    cache = _load_sheet_cache()
    if use_cache and cache and time.time() - cache.get("_ts", 0) < SHEET_CACHE_TTL:
        return cache
    try:
        data = parse_sheet(fetch_sheet_rows())
        _save_sheet_cache(data)
        return data
    except Exception as e:
        print(f"WARN gagal baca roster sheet: {e}")
        if cache:
            print("     pakai cache roster terakhir.")
        return cache


def _person_alias(people):
    alias = {}
    for p in people:
        keys = [p.get("name", "")] + list(p.get("sheet_aliases") or [])
        for key in keys:
            key = str(key).strip().lower()
            if key:
                alias[key] = p
    return alias


def resolve_person(header, people, alias):
    h = str(header).strip().lower()
    if not h:
        return None
    if h in alias:
        return alias[h]
    hits = []
    for p in people:
        tokens = re.split(r"\s+", str(p.get("name", "")).lower())
        if h in tokens:
            hits.append(p)
    return hits[0] if len(hits) == 1 else None


def _active_from_sheet(people, sched, now, verbose=False):
    alias = _person_alias(people)
    mapped, result = {}, {}
    for col in sched.get("columns", []):
        person = resolve_person(col, people, alias)
        if person is None:
            if verbose:
                print(f"WARN kolom sheet '{col}' belum dipetakan ke roster.json "
                      f"(tambah ke 'sheet_aliases')")
            continue
        mapped[col] = person

    for delta in (-1, 0):  # shift M bisa mulai kemarin malam
        day = (now + timedelta(days=delta)).date()
        shifts = sched.get("days", {}).get(day.isoformat(), {})
        for col, info in shifts.items():
            person = mapped.get(col)
            if person is None:
                continue
            shift = {
                "days": [DAY_NAMES[day.weekday()]],
                "start": info["start"],
                "end": info["end"],
            }
            if is_on_shift(shift, now):
                result[str(person.get("name"))] = person

    return list(result.values())


def mention_tokens(people):
    tokens = []
    for p in people:
        gid = str(p.get("google_id") or "").strip()
        if gid.isdigit():
            tokens.append(f"<users/{gid}>")
    return " ".join(tokens)


# ----------------------------------------------------------------------------
# STATE & KIRIM
# ----------------------------------------------------------------------------

def load_alerted():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return set(json.load(f))
        except (ValueError, OSError):
            return set()
    return set()


def save_alerted(alerted):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(alerted), f, ensure_ascii=False, indent=0)


def send_alert(text):
    if not GOOGLE_WEBHOOK_URL or "<" in GOOGLE_WEBHOOK_URL:
        raise RuntimeError(
            "Webhook masih placeholder (Mode Showcase) - pesan TIDAK dikirim. "
            "Isi GOOGLE_WEBHOOK_URL dengan URL webhook Space Anda."
        )
    resp = requests.post(GOOGLE_WEBHOOK_URL, json={"text": text}, timeout=30)
    resp.raise_for_status()
    return resp.status_code


def build_message(match, people):
    package = match.get("package")
    if package is None:
        package = expected_package(match.get("league"), match.get("channel"))
    if not package:
        package = PACKAGE_UNKNOWN
    body = ALERT_TEXT.format(
        title=match["title"] or "-",
        league=match.get("league") or "-",
        channel=match.get("channel") or "-",
        package=package,
        kickoff=match.get("kickoff") or "-",
        url=match.get("url") or "-",
    )
    mentions = mention_tokens(people)
    return f"{body}\n\n{mentions}" if mentions else body


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def collect_hits(items):
    """Match liga target yang ada di CHANNEL YANG DIIZINKAN saja.

    Channel diizinkan = daftar di PACKAGE_RULES (F1@Bein 1, Serie A@Champions
    TV 1-3, EPL@Champions TV 5-6, Ligue 1@Champions TV 1-3 & 5-6, NFL@Champions
    TV 1-3). Match liga
    target di channel lain (mis. NFL di channel "NFL") TIDAK jadi alert.

    Return (hits, skipped): skipped = liga target tapi channel di luar mapping.
    """
    hits, skipped = [], []
    for it in items:
        m = parse_item(it)
        league = detect_league(m["title"], m["alt"])
        if not league:
            continue
        package = expected_package(league, m["channel"])
        if not package:
            skipped.append({"title": m["title"], "league": league,
                            "channel": m["channel"]})
            continue
        m["league"] = league
        m["league_label"] = LEAGUE_LABEL[league]
        m["package"] = package
        hits.append(m)
    return hits, skipped


def cmd_who():
    now = datetime.now(WIB)
    people = active_people(now, verbose=True)
    print(f"Sekarang: {now.strftime('%a %d %b %Y %H:%M WIB')}")
    if not people:
        print("Tidak ada yang sedang shift menurut jadwal sheet.")
        return 1
    for p in people:
        gid = str(p.get("google_id") or "").strip()
        tag = f"<users/{gid}>" if gid.isdigit() else "(google_id kosong)"
        print(f"  {tag}  {p.get('name')}")
    return 0


def cmd_dump_roster():
    """Tampilkan hasil parsing sheet: 2 hari terakhir s/d 2 hari ke depan."""
    now = datetime.now(WIB)
    sched = get_sheet_schedule(use_cache=False)
    if not sched:
        print("Sheet roster tidak bisa dibaca.")
        return 1

    people = load_roster()
    alias = _person_alias(people)
    mapped = {}
    for col in sched.get("columns", []):
        person = resolve_person(col, people, alias)
        mapped[col] = person
        status = person.get("name") if person else "BELUM DIPETAKAN"
        gid = str((person or {}).get("google_id") or "")
        print(f"kolom {col:<10} -> {status:<28} {'ID ok' if gid.isdigit() else 'ID kosong'}")

    for delta in (-2, -1, 0, 1, 2):
        day = (now + timedelta(days=delta)).date()
        shifts = sched.get("days", {}).get(day.isoformat(), {})
        mark = "  <-- hari ini" if delta == 0 else ""
        print(f"\n{day.strftime('%a %d %b %Y')}{mark}")
        if not shifts:
            print("  (tidak ada shift)")
            continue
        for col, info in shifts.items():
            print(f"  {col:<10} {info['code']:<4} {info['start']}-{info['end']}"
                  + (f"   note: {info['note']}" if info['note'] else ""))

    if sched.get("warnings"):
        print("\nCatatan kode tidak dikenal:")
        for w in sched["warnings"]:
            print("  " + w)
    return 0


def cmd_test_mention(dry_run):
    people = active_people()
    if not people:
        print("Tidak ada yang sedang shift - tidak ada mention untuk dites.")
        return 1
    text = "*Paket checking* (test)\n\n" + mention_tokens(people)
    if dry_run or "<" in GOOGLE_WEBHOOK_URL:
        print(text)
        if "<" in GOOGLE_WEBHOOK_URL:
            print("(Mode Showcase: webhook placeholder - pesan TIDAK dikirim.)")
        return 0
    send_alert(text)
    print(f"Pesan tes terkirim, mention {len(people)} orang.")
    return 0


def cmd_self_test():
    sample = [
        {"id": "1", "title": "Sao Paulo Grand Prix - F1", "channel": "Bein 1",
         "url": "https://www.vidio.com/live/6299?schedule_id=1", "kickoff": "12 Nov 2026 01:00"},
        {"id": "2", "title": "Juventus vs Napoli - Serie A", "channel": "Champions TV 2",
         "url": "https://www.vidio.com/live/6686?schedule_id=2", "kickoff": "12 Nov 2026 02:45"},
        {"id": "3", "title": "Arsenal vs Chelsea - Premier League", "channel": "Champions TV 5",
         "url": "https://www.vidio.com/live/9182?schedule_id=3", "kickoff": "12 Nov 2026 03:00"},
        {"id": "4", "title": "PSG vs Marseille - Ligue 1", "channel": "Champions TV 6",
         "url": "https://www.vidio.com/live/9183?schedule_id=4", "kickoff": "12 Nov 2026 03:00"},
        {"id": "5", "title": "Igor Gorgonzola vs Conegliano - Italian Women's Volleyball Serie A1",
         "channel": "Champions TV 1",
         "url": "https://www.vidio.com/live/6685?schedule_id=5", "kickoff": "-"},
        {"id": "6", "title": "Dubai P1 Premier Padel - Day 2", "channel": "Bein 2",
         "url": "https://www.vidio.com/live/17875?schedule_id=6", "kickoff": "-"},
    ]
    people = active_people()
    for m in sample:
        league = detect_league(m["title"])
        if not league:
            print(f"SKIP  {m['title'][:55]}")
            continue
        m["league"] = league
        print("-" * 70)
        print(build_message(m, people))

    # Tes gerbang channel: liga target HANYA di-alert sesuai mapping channel.
    print("-" * 70)
    print("Tes gerbang channel (harus alert / harus skip):")
    gate = [
        ("F1",       "Bein 1",         True),
        ("F1",       "Bein 2",         False),
        ("Serie A",  "Champions TV 1", True),
        ("Serie A",  "Champions TV 4", False),
        ("EPL",      "Champions TV 5", True),
        ("EPL",      "Champions TV 3", False),
        ("Ligue 1",  "Champions TV 6", True),
        ("Ligue 1",  "Champions TV 1", True),
        ("Ligue 1",  "Champions TV 4", False),
        ("Ligue 1",  "Bein 1",         False),
        ("NFL",      "Champions TV 1", True),
        ("NFL",      "Champions TV 2", True),
        ("NFL",      "Champions TV 3", True),
        ("NFL",      "NFL",            False),
    ]
    fails = 0
    for lg, ch, want in gate:
        ok = bool(expected_package(lg, ch))
        mark = "OK  " if ok == want else "FAIL"
        if ok != want:
            fails += 1
        print(f"  {mark} {lg} @ {ch} -> {'alert' if ok else 'skip'}")
    if fails:
        print(f"GERBANG CHANNEL: {fails} tes gagal!")
        return 1
    print("Semua tes lulus.")
    return 0


def main():
    global STATE_FILE
    args = set(sys.argv[1:])
    demo = "--demo" in args
    dry_run = "--dry-run" in args or demo

    if "--who" in args:
        return cmd_who()
    if "--dump-roster" in args:
        return cmd_dump_roster()
    if "--test-mention" in args:
        return cmd_test_mention(dry_run)
    if "--self-test" in args:
        return cmd_self_test()

    if demo:
        # State terpisah: dedup demo tidak pernah menimpa dedup produksi.
        STATE_FILE = os.path.join(HERE, "alerted_demo.json")
        print("=== MODE DEMO: data contoh, tanpa jaringan, tidak ada pesan dikirim ===")
    elif AES_KEY.startswith(b"<"):
        # Showcase tanpa rahasia: jangan coba jaringan, arahkan ke Mode Demo.
        print("MODE SHOWCASE: rahasia (AES_KEY/AES_IV, webhook, ID sheet) masih placeholder.")
        print("Jalankan : python alert_match.py --demo        (data contoh, aman)")
        print("atau     : python alert_match.py --self-test   (tes gerbang channel)")
        return 0
    elif "<" in GOOGLE_WEBHOOK_URL:
        print("MODE SHOWCASE: webhook placeholder -> hasil ditampilkan, tidak dikirim.")

    items = demo_items() if demo else fetch_matches()
    alerted = load_alerted()
    now = datetime.now(WIB)

    hits, skipped = collect_hits(items)
    force = "--force" in args

    # Kirim alert 12 jam dan 6 jam sebelum kickoff.
    to_send = []  # (match, label, state_key)
    for m in hits:
        kdt = m.get("kickoff_dt")
        if not kdt or now >= kdt:
            continue
        # Jendela H-12: antara 12 jam dan 6 jam sebelum kickoff
        if now >= kdt - timedelta(hours=12) and now < kdt - timedelta(hours=6):
            key = f"{m['id']}:12h"
            if force or key not in alerted:
                to_send.append((m, "H-12", key))
        # Jendela H-6: dalam 6 jam sebelum kickoff
        if now >= kdt - timedelta(hours=6) and now < kdt:
            key = f"{m['id']}:6h"
            if force or key not in alerted:
                to_send.append((m, "H-6", key))

    people = active_people()
    ts = now.strftime("%Y-%m-%d %H:%M WIB")
    print(
        f"[{ts}] items={len(items)} target={len(hits)} alerts={len(to_send)} "
        f"on_shift={len(people)}"
    )
    if not people:
        print("WARN tidak ada orang yang sedang shift menurut jadwal sheet - alert dikirim tanpa mention.")
    for s in skipped:
        print(
            f"SKIP channel {s['channel'] or '(kosong)'} -> [{s['league']}] "
            f"{s['title'][:60]} (di luar mapping channel, tidak di-alert)"
        )

    if not hits:
        print(
            "Tidak ada match F1 / Serie A / Ligue 1 / Premier League / NFL "
            "di channel yang diizinkan di section ini."
        )
        return 0
    if not to_send:
        print("Tidak ada alert yang perlu dikirim saat ini (di luar jendela H-12/H-6 atau sudah terkirim).")
        return 0

    failures = 0
    for m, label, key in to_send:
        text = build_message(m, people)
        print("-" * 70)
        print(f"[{label}] {m['title'][:60]}")
        print(text)
        if dry_run:
            if demo:
                alerted.add(key)  # Mode Demo: dedup ikut tercatat (state terpisah)
            continue
        try:
            send_alert(text)
            alerted.add(key)
            print(f"OK  terkirim: [{label}] [{m['league']}] {m['title'][:60]}")
        except Exception as e:  # jangan tandai alerted kalau gagal -> retry run berikutnya
            failures += 1
            print(f"FAIL {m['title'][:60]} -> {e}")
        time.sleep(1)  # jeda biar tidak kena rate limit webhook

    save_alerted(alerted)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
