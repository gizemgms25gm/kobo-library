# 🐳 Kobo Library - Docker & Self-Hosting Rehberi

Bu rehber, Kobo Library uygulamasını **Docker** veya **Docker Compose** kullanarak ev sunucunuzda (Raspberry Pi, Synology/QNAP NAS, Unraid veya Linux VPS) 7/24 nasıl çalıştıracağınızı açıklar.

---

## 🚀 Hızlı Başlangıç (Docker Compose ile)

Proje dizininde tek bir komutla sunucuyu ayağa kaldırabilirsiniz:

```bash
docker compose up -d
```

Uygulama başarıyla başlatıldığında tarayıcınızdan şu adrese gidebilirsiniz:
👉 **`http://localhost:5000`** veya yerel ağınızdaki IP adresi (**`http://sunucu-ip-adresi:5000`**)

---

## 📂 Kalıcı Veri Birimleri (Volumes)

Uygulama konteyneri silinse veya güncellense dahi verilerinizin kaybolmaması için şu dizinler ana makineye bağlanmıştır:

| Konteyner Yolu | Açıklama |
| :--- | :--- |
| `/app/KoboReaderData_Deneme.sqlite` | Kobo SQLite veritabanı (Alıntılar, notlar, okuma süreleri) |
| `/app/kobo_config.json` | Sayfa modu, Google Drive ve kütüphane tercihleri |
| `/app/books` | Yedeklenen `.epub` kitap dosyaları |
| `/app/static/covers` | İndirilen veya özel yüklenen kitap kapakları |

---

## ⚙️ Faydalı Komutlar

- **Logları Canlı İzleme:**
  ```bash
  docker compose logs -f
  ```

- **Konteyneri Durdurma:**
  ```bash
  docker compose down
  ```

- **Konteyneri Yeniden Başlatma:**
  ```bash
  docker compose restart
  ```

- **İmajı Yeniden Derleme (Kod güncellemesi sonrası):**
  ```bash
  docker compose build --no-cache
  docker compose up -d
  ```

---

## 🌐 Ev Ağından veya Mobil Cihazlardan Erişim

Aynı Wi-Fi ağına bağlı telefon, tablet veya diğer bilgisayarlarınızdan `http://<BILGISAYAR_IP_ADRESI>:5000` adresine girerek kütüphanenizi inceleyebilir, istatistiklerinize bakabilir ve EPUB kitaplarınızı indirebilirsiniz.
