# 📡 Match Package Alert

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Google Chat](https://img.shields.io/badge/Google%20Chat-Alerts-00AC47?logo=googlechat&logoColor=white)](https://chat.google.com/)
[![Google Sheets](https://img.shields.io/badge/Google%20Sheets-Roster-0F9D58?logo=googlesheets&logoColor=white)](https://sheets.google.com/)
[![Task Scheduler](https://img.shields.io/badge/Windows-Task%20Scheduler-0078D4?logo=windows11&logoColor=white)](https://learn.microsoft.com/en-us/windows/task-scheduler/)

**Alert "Paket Checking" otomatis untuk pertandingan live-streaming.**
Memantau halaman *Pertandingan Hari Ini* (Vidio) lewat API publiknya, lalu mengirim
alert ke Google Space **tepat di H-12 dan H-6 sebelum kickoff** — lengkap dengan
mention orang yang **sedang shift**.

> 🧪 **Ini adalah versi showcase yang sudah disanitasi.** Webhook, ID spreadsheet,
> kunci AES, key cadangan, ID Google karyawan, email, dan nama tim sudah diganti
> placeholder atau data contoh.

---

## 🎯 Masalah yang Dipecahkan

Sebelum pertandingan besar tayang (F1, Serie A, Premier League, Ligue 1, NFL),
tim editorial harus memastikan **paket/langganan yang benar sudah aktif** di channel
tempat match disiarkan — lalu memberi tahu orang yang sedang jaga lewat Google Space.

Pengecekan manual setiap match berarti:
- ❌ Buka jadwal → cek channel → cocokkan paket → cari orang shift → tag di Space
- ❌ Rawan **telat** (alert H-12/H-6 meleset) dan **lupa** (match lewat tanpa info)
- ❌ Alert **dobel** kalau dua PC jalan bersamaan, atau **hilang diam-diam** kalau
  `x-api-key` kedaluwarsa / task mati

Tool ini menggantikan rutinitas itu: **polling tiap 1 menit, alert presisi ±1 menit,
maksimum 2 pesan per match**, dan berjalan 24/7 tanpa campur tangan manusia.

## ✨ Fitur Utama

| Fitur | Deskripsi |
| --- | --- |
| ⏰ **Jendela H-12 & H-6 Presisi** | Polling tiap 1 menit (Task Scheduler), pesan keluar tepat di H-12 lalu H-6 sebelum kickoff (±1 menit). |
| 🚫 **Gerbang Channel Ketat** | Hanya liga × channel yang ada di mapping. Match liga target di channel lain (mis. NFL di channel "NFL") **diam total**. |
| 🔁 **Anti-Do-bel (Dedup)** | State `alerted.json` memastikan **maksimum 2 kirim per match** — aman walau script crash di tengah jalan. |
| 🤖 **Auto-refresh `x-api-key`** | Key Vidio kedaluwarsa harian → diambil ulang otomatis (`POST /auth` + enkripsi AES-256-CBC), di-cache, dan diputar lagi saat kena 401. |
| 👥 **Mention Kontekstual** | Hanya orang yang **sedang shift** yang di-mention. Sumber jadwal: Google Sheets (note cell menimpa jam baku). |
| 🧪 **Self-test 14 Kasus** | Seluruh gerbang liga×channel diuji tanpa jaringan — perubahan mapping wajib lulus tes sebelum dipakai. |
| 🖥️ **Portable & Idempotent** | `setup.bat` / `stop.bat` satu klik; `run.bat` identik di semua PC (tanpa path absolut) supaya `git pull` tak pernah mematikan task. |
| 🛟 **Fallback Berlapis** | Sheet gagal → `roster.json`; key gagal → cache → cadangan; jaringan gagal → retry 3× → run menit berikutnya jadi safety net. |

### Contoh pesan (format baku — tidak boleh berubah)

```
⚠️ CEK PAKET PERTANDINGAN ⚠️
Checking Paket
• Match: Arsenal vs Chelsea - Premier League
• Liga: Premier League
• Channel: Champions TV 5
• Info: Paket harus: [157] [Ultimate] EPL
• Kickoff: 21 Nov 2026 10:00 WIB
🔗 Link Page: https://www.vidio.com/live/9182?schedule_id=3

<users/1000000000000000001> <users/1000000000000000002>
```

## 🏗️ Arsitektur

```
┌─────────────────────────────┐   ┌──────────────────────────────┐
│ vidio.com (API publik,      │   │ Google Sheets (roster shift) │
│ "Pertandingan Hari Ini")    │   │ service account, read-only,  │
│ — tanpa login               │   │ cache 10 menit               │
└──────────────┬──────────────┘   └──────────────┬───────────────┘
               │ GET (x-api-key auto-refresh)    │ grid + cell note
               ▼                                 ▼
┌───────────────────────────────────────────────────────────────┐
│                   CORE: alert_match.py                        │
│  1. Deteksi liga (regex) + anti false-positive (voli/basket)  │
│  2. Gerbang channel    → paket wajib (PACKAGE_RULES)          │
│  3. Jendela H-12 / H-6 → dedup alerted.json (max 2 kirim)    │
│  4. Shift sekarang     → mention <users/...>                  │
└───────────────────────────────┬───────────────────────────────┘
                                │ incoming webhook (POST)
                                ▼
                 ┌──────────────────────────────┐
                 │ Google Space (Chat)          │
                 │ ⚠️ CEK PAKET PERTANDINGAN ⚠️  │
                 │ + mention orang yang shift   │
                 └──────────────────────────────┘

Dijalankan tiap 1 menit oleh Windows Task Scheduler
(run.bat → alert.log) — polling, BUKAN kirim tiap menit.
```

## 📐 Aturan Alert

### 1. Gerbang channel — di luar daftar ini, TIDAK ada alert

| Liga | Channel yang diizinkan | Paket wajib |
| --- | --- | --- |
| F1 | Bein 1 | `[134] [Platinum Extra] F1 Livestreaming & VOD` |
| Serie A | Champions TV 1–3 | `[493] [Platinum Extra] Serie A` |
| Premier League | Champions TV 5–6 | `[157] [Ultimate] EPL` |
| Ligue 1 | Champions TV 1, 2, 3, 5, 6 | `[803] [Platinum Extra] Ligue 1` |
| NFL | Champions TV 1–3 | `[598] [Platinum Extra] NFL Live & VOD` |

### 2. Waktu & dedup

- Cek **tiap 1 menit** → alert H-12 (12 jam sebelum kickoff) dan H-6 (6 jam).
- **Maksimum 2 pesan per match**, disimpan di `alerted.json` — tidak pernah dobel.
- Jendela dihitung dari kickoff di API (otomatis WIB).

### 3. Mention — hanya orang yang sedang shift

| Kode shift | Jam baku | Keterangan |
| --- | --- | --- |
| `P` | 09:00–21:00 | Pagi |
| `NS` | 09:00–19:00 | Normal shift |
| `MD` | 11:00–23:00 | Mid day |
| `M` | 21:00–09:00 | Malam (lintas tengah malam) |
| `MDO` | 12:00–21:00 | Overtime (biasanya ada note custom) |

- **Note di cell menimpa jam baku** (mis. `10:00-18:00`); kata *cuti/off/sakit/…*
  berarti tidak di-mention.
- Dua pengecualian yang dijaga ketat: **kolom sheet anak magang** (`google_id`
  kosong → tidak pernah ter-mention) dan **supervisor** (bukan anggota roster →
  ID-nya hanya dicatat di `people_ids.json` blok `excluded`). Keduanya orang
  berbeda yang namanya rawan tertukar — aturannya dieksplisitkan di kode & data.

## 🚀 Cara Menjalankan

### 1. Clone + dependensi

```bash
git clone https://github.com/Arlyanto/match-alert.git
cd match-alert
pip install -r requirements.txt
```

### 2. Uji tanpa setup apa pun 🎉

```bash
python alert_match.py --self-test   # 14 tes gerbang channel, tanpa jaringan
python alert_match.py --demo        # MODE DEMO: data contoh, tanpa credential
```

**Mode Demo** memakai data contoh dengan kickoff relatif ke waktu sekarang, jadi
jendela H-12/H-6, gerbang channel, dedup, dan format mention bisa direproduksi
kapan pun — **tanpa jaringan dan tanpa pesan yang benar-benar dikirim**.
State demo disimpan terpisah di `alerted_demo.json` (hapus file itu untuk
mengulang demo dari awal).

### 3. Hubungkan dengan data asli

| Rahasia | Letak | Catatan |
| --- | --- | --- |
| Webhook Space | env `GOOGLE_WEBHOOK_URL` atau konstanta di `alert_match.py` | Incoming webhook dari Space settings |
| Kunci AES + IV | `AES_KEY` / `AES_IV` di `alert_match.py` | Dibaca dari bundle JS publik `www.vidio.com` |
| Service account Sheets | `credentials.json` (di-`.gitignore`) | Share roster sheet ke email service account-nya |
| ID spreadsheet roster | env `ROSTER_SHEET_ID` atau konstanta | Tab jadwal shift, baris = tanggal |
| Orang + Google ID | `roster.json` / `people_ids.json` | ID numerik member Space (data contoh di repo ini) |

> ⚠️ Semua rahasia terdaftar di `.gitignore` — cek ulang sebelum commit.

Di Windows: **double-click `setup.bat`** — memasang dependensi, menulis `run.bat`
portable, mendaftarkan task `Paket Checking` (tiap 1 menit, hidden), lalu
menjalankan self-test + tes data. Lihat sampai muncul `HASIL: SEMUA OK`.

> ⚠️ **Jalankan di SATU PC saja.** Dua PC jalan bersamaan = dedup terpisah →
> pesan dobel. Pindahan antar-PC cukup `setup.bat` di PC baru lalu `stop.bat`
> di PC lama.

## 📂 Struktur Proyek

```
match-alert/
├── alert_match.py            # Inti: fetch, gerbang, jendela, dedup, mention, kirim
├── setup.bat                 # Setup sekali klik (deps → runner → task → self-test)
├── stop.bat                  # Matikan task di PC lama (anti dobel)
├── run.bat / run_hidden.vbs  # Runner portable + jalan tanpa jendela
├── send_test.py (+ .bat)     # Kirim 1 pesan tes berformat alert asli
├── fetch_google_ids.py       # Tarik Google user ID member Space (buat mention)
├── collect_member_ids.js     # Fallback manual via console browser
├── diagnose.py               # Diagnostik read-only: match target + status jendela
├── check_cache.py            # Scan note jam custom di cache roster
├── roster.json               # Orang + shift fallback (data contoh)
├── people_ids.json           # ID member Space + blok excluded (data contoh)
├── credentials.example.json  # Template service account
├── requirements.txt
└── README.md
```

## 📈 Dampak

- ⏰ **Alert keluar tepat H-12 & H-6 (±1 menit)** — 24/7, tanpa manusia, tanpa lupa.
- 🔁 **Maksimum 2 pesan per match** — terbukti di Space produksi (H-12 + H-6,
  tidak pernah ada pesan kembar).
- 🔑 **`x-api-key` kedaluwarsa tak pernah mematikan alert** — regenerasi harian
  otomatis, 401 dipulihkan pada run yang sama.
- 🖥️ **Migrasi antar-PC lewat git tanpa kehilangan jadwal** — runner portable
  menghapus kelas bug "path Python tertimpa `git pull` → task mati diam-diam".
- 🧪 **14 tes gerbang** menjadikan setiap perubahan mapping dapat diverifikasi
  dalam hitungan detik.

## 🧰 Teknologi

`Python 3` · `requests` · `cryptography` (AES-256-CBC) · `google-auth` (Sheets
read-only) · Google Chat incoming webhook · Windows Task Scheduler · `git`

## ⚖️ Penafian

Repositori ini adalah **showcase portofolio**. Webhook, ID spreadsheet, kunci,
nama, email, dan ID pengguna semuanya placeholder atau data contoh. Pemantauan
dilakukan terhadap halaman **publik** platform (tanpa login); logika alert
diperuntukkan bagi tim/instansi yang memiliki akses sah ke Space dan roster-nya.

---

Dibuat dengan ❤️ oleh [Arlyanto](https://github.com/Arlyanto)
