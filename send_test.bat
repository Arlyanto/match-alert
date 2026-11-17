@echo off
rem Kirim pesan TEST - output ke test.log
cd /d "%~dp0"
python -u send_test.py >> test.log 2>&1
