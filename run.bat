@echo off
rem Paket Checking - cek tiap 1 menit, output ke alert.log
cd /d "%~dp0"
python -u alert_match.py >> alert.log 2>&1
