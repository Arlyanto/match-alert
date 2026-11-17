@echo off
cd /d "%~dp0"
echo ============================================================
echo    STOP PAKET CHECKING - untuk PC LAMA
echo ============================================================
echo.
echo Menghapus task dari PC INI (file TIDAK dihapus)...
echo.

schtasks /delete /tn "Paket Checking" /f
schtasks /delete /tn "Paket Checking Test 2015" /f
schtasks /delete /tn "Paket Checking Test 0215" /f

echo.
echo Sisa task yang berkaitan:
schtasks /query /fo csv | findstr /i "Paket"
if errorlevel 1 echo   (tidak ada - bersih)
echo.
echo Selesai. Kalau mau nyalain lagi di PC ini: jalankan setup.bat
echo.
pause
