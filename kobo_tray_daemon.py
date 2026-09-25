import time
import os
import sys
import shutil
import subprocess
import threading
import webbrowser

# Ana proje dizinini ekle
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from veri import (
    kobo_surucusu_bul,
    kobo_cihaz_kapaklarini_kopyala,
    kobo_kitap_dosyalarini_kopyala,
    bulut_ve_git_yedekle,
    DB_PATH,
    CACHE_SOZLUGU,
    ayarlari_yukle
)

CIHAZ_BAGLI_DURUMU = False


def windows_bildirim_goster(baslik, mesaj):
    """Windows masaüstünde şık bir Toast/Balon bildirimi gösterir."""
    try:
        encoded_title = baslik.replace('"', '`"')
        encoded_msg = mesaj.replace('"', '`"')
        ps_cmd = (
            f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms") | Out-Null; '
            f'$obj = New-Object System.Windows.Forms.NotifyIcon; '
            f'$obj.Icon = [System.Drawing.SystemIcons]::Information; '
            f'$obj.BalloonTipIcon = "Info"; '
            f'$obj.BalloonTipTitle = "{encoded_title}"; '
            f'$obj.BalloonTipText = "{encoded_msg}"; '
            f'$obj.Visible = $true; '
            f'$obj.ShowBalloonTip(6000); '
            f'Start-Sleep -Milliseconds 1200; '
            f'$obj.Dispose()'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            capture_output=True,
            text=True
        )
    except Exception as e:
        print(f"Bildirim gönderme uyarısı: {e}")


def kobo_tam_esitle():
    """Kobo bağlandığında tüm veritabanı, kitap, kapak ve bulut eşitlemesini tetikler."""
    surucu, kobo_yolu = kobo_surucusu_bul()
    if not kobo_yolu or not os.path.exists(kobo_yolu):
        return False, "Kobo bağlı değil."

    try:
        print(f"\n[🔄 EŞİTLEME BAŞLADI] Kobo algılandı: {surucu}")
        
        # 1. Veritabanını Kopyala
        shutil.copy2(kobo_yolu, DB_PATH)
        print("  -> Veritabanı (KoboReader.sqlite) yerel projeye aktarıldı.")

        # 2. Cihaz İçi Kapakları Kopyala
        kapak_sayisi = kobo_cihaz_kapaklarini_kopyala(surucu)
        print(f"  -> {kapak_sayisi} cihaz kapağı aktarıldı.")

        # 3. EPUB Kitap Dosyalarını Kopyala
        yeni, atlanan, _ = kobo_kitap_dosyalarini_kopyala(surucu)
        print(f"  -> {yeni} yeni kitap kopyalandı ({atlanan} mevcut kitap atlandı).")

        # 4. Önbelleği Temizle
        CACHE_SOZLUGU.clear()

        # 5. Bulut ve GitHub Senkronizasyonu
        yedek = bulut_ve_git_yedekle()
        print(f"  -> Bulut ve GitHub senkronizasyonu tamamlandı (GitHub: {yedek.get('github')}).")

        bildirim_metni = f"📚 Kobo başarıyla eşitlendi!\n{yeni} yeni kitap eklendi, bulut yedeği güncellendi."
        windows_bildirim_goster("Kobo Library Senkronizasyonu", bildirim_metni)

        return True, "Eşitleme başarılı."
    except Exception as e:
        hata_msj = f"Eşitleme sırasında hata: {str(e)}"
        print(f"  ❌ {hata_msj}")
        windows_bildirim_goster("Kobo Eşitleme Hatası", hata_msj)
        return False, hata_msj


def usb_dinleyici_dongusu():
    """Arka planda USB bağlantısını 4 saniyede bir kontrol eden döngü."""
    global CIHAZ_BAGLI_DURUMU
    print("=" * 60)
    print("🚀 Kobo Arka Plan USB Algılayıcı Başlatıldı!")
    print("Kobo cihazınız bilgisayara bağlandığında otomatik eşitleme yapılacaktır.")
    print("Durdurmak için Ctrl + C tuşlarına basabilirsiniz.")
    print("=" * 60)

    # İlk açılışta Kobo zaten takılıysa
    surucu, kobo_yolu = kobo_surucusu_bul()
    if kobo_yolu:
        CIHAZ_BAGLI_DURUMU = True
        print(f"[+] Kobo cihazı şu an bağlı ({surucu}). Otomatik eşitleme yapılıyor...")
        kobo_tam_esitle()

    while True:
        try:
            surucu, kobo_yolu = kobo_surucusu_bul()
            su_anki_durum = bool(kobo_yolu and os.path.exists(kobo_yolu))

            # Durum Değişimi: Bağlı değil -> Bağlandı
            if su_anki_durum and not CIHAZ_BAGLI_DURUMU:
                CIHAZ_BAGLI_DURUMU = True
                print(f"\n[⚡ YENİ BAĞLANTI] Kobo cihazı bağlandı ({surucu}). 3 saniye bekleniyor...")
                time.sleep(3)  # Windows sürücü mount işleminin stabil hale gelmesi için kısa bekleme
                kobo_tam_esitle()

            # Durum Değişimi: Bağlı -> Çıkarıldı
            elif not su_anki_durum and CIHAZ_BAGLI_DURUMU:
                CIHAZ_BAGLI_DURUMU = False
                print("\n[ℹ️ BİLGİ] Kobo cihazının bağlantısı kesildi.")

            time.sleep(4)
        except KeyboardInterrupt:
            print("\n👋 Kobo USB Algılayıcı kapatıldı.")
            break
        except Exception as e:
            print(f"Döngü uyarısı: {e}")
            time.sleep(5)


if __name__ == '__main__':
    usb_dinleyici_dongusu()
