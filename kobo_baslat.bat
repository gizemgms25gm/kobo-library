@echo off
chcp 65001 >nul
title Kobo Library - Otomatik Başlatıcı

echo ========================================================
echo             📚 KOBO LIBRARY BASLATICI
echo ========================================================
echo.
echo  [1] Web Kütüphanesini Başlat (Tarayıcıda Aç)
echo  [2] Arka Plan USB Algılayıcıyı Başlat (Otomatik Eşitleme)
echo  [3] Her İkisini de Birlikte Başlat
echo.
set /p secim="Seçiminiz (1, 2 veya 3): "

if "%secim%"=="1" goto web_baslat
if "%secim%"=="2" goto daemon_baslat
if "%secim%"=="3" goto hepsi_baslat
goto web_baslat

:web_baslat
echo.
echo 🚀 Web Kütüphanesi başlatılıyor...
start http://localhost:5000
python veri.py
goto bitir

:daemon_baslat
echo.
echo ⚡ Arka Plan USB Algılayıcı başlatılıyor...
python kobo_tray_daemon.py
goto bitir

:hepsi_baslat
echo.
echo 🚀 Web Sunucusu ve Arka Plan Algılayıcı başlatılıyor...
start cmd /k python kobo_tray_daemon.py
start http://localhost:5000
python veri.py
goto bitir

:bitir
pause
