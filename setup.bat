@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Setup Paket Checking

echo ============================================================
echo    SETUP PAKET CHECKING  -  jalankan sekali di PC BARU
echo ============================================================
echo Folder : %~dp0
echo.

set "FAIL="

rem --- path mengandung spasi sering bikin Task Scheduler gagal ---
echo %~dp0|findstr /c:" " >nul
if not errorlevel 1 (
    echo [!] PATH MENGANDUNG SPASI.
    echo     Pindahkan folder ini ke path tanpa spasi, mis. C:\paket_alert
    echo     lalu jalankan setup.bat lagi.
    echo.
)

rem --- 1. Python ---
echo [1/6] Cek Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo        GAGAL: python tidak ditemukan di PATH.
    echo        Install dulu: https://www.python.org/downloads/
    echo        Saat install centang "Add python.exe to PATH".
    set "FAIL=1"
) else (
    for /f "delims=" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)"') do set "PYEXE=%%p"
    echo        OK: !PYVER!
    echo        OK: !PYEXE!
)
if defined FAIL goto :ringkas

rem --- 2. Paket python ---
echo [2/6] Cek paket: requests, cryptography, google-auth...
python -c "import requests, cryptography, google.auth" >nul 2>&1
if errorlevel 1 (
    echo        paket belum lengkap - menginstall...
    python -m pip install --quiet requests cryptography google-auth
    python -c "import requests, cryptography, google.auth" >nul 2>&1
    if errorlevel 1 (
        echo        GAGAL: paket tidak bisa diinstall - cek internet.
        set "FAIL=1"
    ) else (
        echo        OK: requests, cryptography, google-auth terpasang
    )
) else (
    echo        OK: requests, cryptography, google-auth terpasang
)
if defined FAIL goto :ringkas

rem --- 3. Tulis run.bat / send_test.bat (PORTABLE: pakai "python" di PATH) ---
rem run.bat harus IDENTIK di semua PC (jangan pakai path absolut per-PC,
rem karena git pull akan saling menimpa -> task mati diam-diam).
rem Langkah [1/6] sudah memastikan "python" ada di PATH.
echo [3/6] Menulis run.bat dan send_test.bat...
>run.bat echo @echo off
>>run.bat echo rem Paket Checking - cek tiap 1 menit, output ke alert.log
>>run.bat echo cd /d "%%~dp0"
>>run.bat echo python -u alert_match.py ^>^> alert.log 2^>^&1
>send_test.bat echo @echo off
>>send_test.bat echo rem Kirim pesan TEST - output ke test.log
>>send_test.bat echo cd /d "%%~dp0"
>>send_test.bat echo python -u send_test.py ^>^> test.log 2^>^&1
echo        OK: run.bat dan send_test.bat portable (python di PATH)

rem --- 4. Daftar task ---
echo [4/6] Mendaftarkan task "Paket Checking" tiap 1 menit...
schtasks /create /tn "Paket Checking" /tr "wscript.exe %~dp0run_hidden.vbs" /sc minute /mo 1 /f >nul 2>&1
if errorlevel 1 (
    echo        GAGAL: task tidak bisa dibuat. Lihat catatan path spasi di atas.
    set "FAIL=1"
) else (
    echo        OK: task "Paket Checking" terdaftar, jalan tiap 1 menit hidden
)
if defined FAIL goto :ringkas

rem --- 5. Tes format pesan ---
echo [5/6] Tes format + gerbang channel (self-test)...
"!PYEXE!" alert_match.py --self-test >nul 2>&1
if errorlevel 1 (
    echo        GAGAL - jalankan manual: "!PYEXE!" alert_match.py --self-test
    set "FAIL=1"
) else (
    echo        OK: format alert + gerbang channel lulus
)
if defined FAIL goto :ringkas

rem --- 6. Tes data live: key, API, roster sheet ---
echo [6/6] Tes ambil data (key + API vidio + roster sheet)...
echo.
"!PYEXE!" alert_match.py --dry-run
if errorlevel 1 (
    echo.
    echo        GAGAL - cek credentials.json ada, atau koneksi internet.
    set "FAIL=1"
) else (
    echo.
    echo        OK: data kebaca
)

:ringkas
echo.
echo ============================================================
if defined FAIL (
    echo    HASIL: ADA YANG GAGAL - baca pesan GAGAL di atas.
) else (
    echo    HASIL: SEMUA OK - Paket Checking siap jalan otomatis.
)
echo ============================================================
echo.
echo Yang perlu dilakukan:
echo   1. Task jalan tiap 1 menit tanpa jendela, log ke alert.log
echo   2. Di PC LAMA jalankan stop.bat — supaya alert tidak dobel
echo   3. PC server jangan sleep / hibernate di jam pertandingan
echo   4. Ubah shift/jadwal tetap lewat Google Sheet (kebaca otomatis)
echo.
pause
