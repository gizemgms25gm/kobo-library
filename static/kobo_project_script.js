let tumKitaplar = [];
let aktifDetaylar = [];
let aktifFiltre = 'all';
let aktifKitap = null;

document.addEventListener('DOMContentLoaded', () => {
    kitaplariYukle();

    // Tema Değişimi (iOS Switch)
    const themeToggle = document.getElementById('theme-toggle');
    const mevcutTema = localStorage.getItem('theme');

    if (mevcutTema === 'dark') {
        document.body.classList.add('dark-mode');
        if (themeToggle) themeToggle.checked = true;
    }

    if (themeToggle) {
        themeToggle.addEventListener('change', () => {
            if (themeToggle.checked) {
                document.body.classList.add('dark-mode');
                localStorage.setItem('theme', 'dark');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('theme', 'light');
            }
        });
    }

    // Butonla Geri Dönme
    const btnGeri = document.getElementById('btn-geri-don');
    if (btnGeri) {
        btnGeri.addEventListener('click', () => {
            history.back();
        });
    }

    // Tarayıcı Geri/İleri Butonu
    window.addEventListener('popstate', (event) => {
        if (event.state && event.state.view === 'detay') {
            const kitap = tumKitaplar.find(k => k.volume_id === event.state.volume_id);
            if (kitap) detayGörünümünüAc(kitap);
        } else {
            anaKitaplikGörünümünüAc();
        }
    });
});

function kitaplariYukle() {
    const listeContainer = document.getElementById('kitap-listesi');
    if (tumKitaplar.length === 0 && listeContainer) {
        listeContainer.innerHTML = '<p class="yukleniyor">Kütüphane taranıyor ve kitaplar yükleniyor...</p>';
    }

    fetch(`/api/kitaplar?t=${Date.now()}`)
        .then(res => res.json())
        .then(kitaplar => {
            tumKitaplar = kitaplar;
            kitapKartlariniCiz(tumKitaplar);
        })
        .catch(err => {
            console.error("Kitaplar yüklenirken hata:", err);
            if (listeContainer) listeContainer.innerHTML = '<p class="hata-mesaj">Kitaplar yüklenirken bir hata oluştu.</p>';
        });
}

function kitapKartlariniCiz(kitapListesi) {
    const listeContainer = document.getElementById('kitap-listesi');
    if (!listeContainer) return;
    
    listeContainer.innerHTML = '';

    if (kitapListesi.length === 0) {
        listeContainer.innerHTML = '<p class="bos-mesaj">Kütüphanenizde gösterilecek kitap bulunamadı.</p>';
        return;
    }

    kitapListesi.forEach(kitap => {
        const kart = document.createElement('div');
        kart.className = 'kitap-karti';
        
        kart.onclick = () => {
            history.pushState({ view: 'detay', volume_id: kitap.volume_id }, '', `#${encodeURIComponent(kitap.kitap_adi)}`);
            kitapDetayGoster(kitap);
        };

        kart.innerHTML = `
            <div class="kapak-container">
                <img src="${kitap.kapak_url}" alt="${kitap.kitap_adi}" class="kitap-kapak" loading="lazy">
            </div>
            <div class="kitap-bilgi">
                <h3 class="kitap-baslik" title="${kitap.kitap_adi}">${kitap.kitap_adi}</h3>
                <p class="kitap-yazar" title="${kitap.yazar}">${kitap.yazar}</p>
                
                <div class="sayfa-cizgi">${kitap.sayfa_sayisi !== '—' ? kitap.sayfa_sayisi : '—'}</div>
                
                <div class="stats-row">
                    <span class="stat-item" title="Alıntılar">
                        <svg class="custom-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M4.583 17.321C3.553 16.227 3 15 3 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.261 1.4-4.22 3.037-4.22 4.498 0 .524.161.981.482 1.371.32.391.758.587 1.312.587 1.008 0 1.839.317 2.493.952.654.634.981 1.439.981 2.414 0 1.053-.352 1.948-1.056 2.685-.704.737-1.637 1.106-2.8 1.106-1.008 0-1.851-.331-2.532-.993zm10 0C13.553 16.227 13 15 13 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.261 1.4-4.22 3.037-4.22 4.498 0 .524.161.981.482 1.371.32.391.758.587 1.312.587 1.008 0 1.839.317 2.493.952.654.634.981 1.439.981 2.414 0 1.053-.352 1.948-1.056 2.685-.704.737-1.637 1.106-2.8 1.106-1.008 0-1.851-.331-2.532-.993z"/></svg>
                        ${kitap.alinti_sayisi}
                    </span>
                    <span class="stat-item" title="Notlar">
                        <svg class="custom-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M19 3h-2V1h-2v2H9V1H7v2H5c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 18H5V5h2v2h2V5h6v2h2V5h2v16zm-12-6h10v2H7v-2zm0-4h10v2H7v-2zm0-4h10v2H7V9z"/></svg>
                        ${kitap.not_sayisi}
                    </span>
                    <span class="stat-item" title="Yer İmleri">
                        <svg class="custom-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>
                        ${kitap.yer_imi_sayisi || 0}
                    </span>
                </div>
            </div>
        `;
        listeContainer.appendChild(kart);
    });
}

function kitapDetayGoster(kitap) {
    aktifKitap = kitap;
    detayGörünümünüAc(kitap);
    
    const alintiListesi = document.getElementById('alinti-not-listesi');
    alintiListesi.innerHTML = '<p class="yukleniyor">Alıntılar, notlar ve yer imleri yükleniyor...</p>';

    fetch(`/api/kitap-detay/${encodeURIComponent(kitap.volume_id)}?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            aktifDetaylar = data.detaylar || [];
            
            // Eğer detay apisinden güncel kapak veya başlık geldiyse
            if (data.kapak_url) {
                kitap.kapak_url = data.kapak_url;
                const detayKapakImg = document.getElementById('detay-kapak-img');
                if (detayKapakImg) detayKapakImg.src = data.kapak_url;
            }

            // EPUB indirme butonunu yönet
            const epubBtn = document.getElementById('btn-download-epub');
            if (epubBtn) {
                if (data.epub_indir_url) {
                    epubBtn.href = data.epub_indir_url;
                    epubBtn.style.display = 'inline-flex';
                } else if (kitap.epub_indir_url) {
                    epubBtn.href = kitap.epub_indir_url;
                    epubBtn.style.display = 'inline-flex';
                } else {
                    epubBtn.style.display = 'none';
                }
            }

            // Sayaçları güncelle
            const alintiSayisi = aktifDetaylar.filter(d => d.tur === 'alinti').length;
            const notSayisi = aktifDetaylar.filter(d => d.tur === 'not').length;
            const yerImiSayisi = aktifDetaylar.filter(d => d.tur === 'yer_imi').length;

            document.getElementById('count-all').innerText = aktifDetaylar.length;
            document.getElementById('count-alinti').innerText = alintiSayisi;
            document.getElementById('count-not').innerText = notSayisi;
            document.getElementById('count-yer_imi').innerText = yerImiSayisi;

            filtreDegistir('all', document.querySelector('.filter-tab[data-filter="all"]'));
        })
        .catch(err => {
            console.error("Detay yükleme hatası:", err);
            alintiListesi.innerHTML = '<p class="hata-mesaj">İçerik yüklenirken bir hata oluştu.</p>';
        });
}

function filtreDegistir(tur, element) {
    aktifFiltre = tur;
    
    document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
    if (element) element.classList.add('active');

    detayListesiniCiz();
}

function detayListesiniCiz() {
    const alintiListesi = document.getElementById('alinti-not-listesi');
    alintiListesi.innerHTML = '';

    let gosterilecekler = aktifDetaylar;
    if (aktifFiltre !== 'all') {
        gosterilecekler = aktifDetaylar.filter(d => d.tur === aktifFiltre);
    }

    if (gosterilecekler.length === 0) {
        alintiListesi.innerHTML = '<p class="bos-mesaj">Bu kategoride henüz kayıt bulunmuyor.</p>';
        return;
    }

    gosterilecekler.forEach(item => {
        const kart = document.createElement('div');
        let kartClass = 'alinti-karti';
        if (item.tur === 'not') kartClass += ' not-karti';
        if (item.tur === 'yer_imi') kartClass += ' yer-imi-karti';
        kart.className = kartClass;

        let icerikHTML = '';

        if (item.tur === 'yer_imi') {
            icerikHTML = `
                <div class="yer-imi-icerik">
                    <span class="yer-imi-rozet">🔖 Yer İmi (Kaldığın Sayfa)</span>
                    ${item.alinti_metni ? `<p class="alinti-metni">${item.alinti_metni}</p>` : '<p class="yer-imi-aciklama">Bu sayfaya yer imi bırakıldı.</p>'}
                </div>
            `;
        } else {
            if (item.alinti_metni) {
                icerikHTML += `<blockquote class="alinti-metni">"${item.alinti_metni}"</blockquote>`;
            }
            if (item.kullanici_notu) {
                icerikHTML += `<div class="kullanici-notu"><strong>Notum:</strong> ${item.kullanici_notu}</div>`;
            }
        }

        kart.innerHTML = `
            ${icerikHTML}
            <div class="alinti-meta">
                <span class="konum-etiket">${item.ilerleme ? '📍 ' + item.ilerleme : ''}</span>
                <span class="tarih-etiket">${item.tarih ? '🕒 ' + item.tarih : ''}</span>
            </div>
        `;
        alintiListesi.appendChild(kart);
    });
}

function detayGörünümünüAc(kitap) {
    aktifKitap = kitap;
    document.getElementById('ana-kitaplik-view').style.display = 'none';
    const detayView = document.getElementById('kitap-detay-view');
    detayView.style.display = 'block';

    document.getElementById('detay-kitap-adi').innerText = kitap.kitap_adi;
    document.getElementById('detay-yazar-adi').innerText = kitap.yazar;
    
    const detayKapakImg = document.getElementById('detay-kapak-img');
    if (detayKapakImg) detayKapakImg.src = kitap.kapak_url;

    const sayfaRozet = document.getElementById('detay-sayfa-bilgi');
    if (sayfaRozet) {
        sayfaRozet.innerText = (kitap.sayfa_sayisi && kitap.sayfa_sayisi !== '—') ? `📖 ${kitap.sayfa_sayisi}` : '';
    }
}

function anaKitaplikGörünümünüAc() {
    document.getElementById('kitap-detay-view').style.display = 'none';
    document.getElementById('ana-kitaplik-view').style.display = 'block';
}

function kitapFiltrele() {
    const query = document.getElementById('search-input').value.toLowerCase();
    const filtrelenen = tumKitaplar.filter(k => 
        k.kitap_adi.toLowerCase().includes(query) || 
        k.yazar.toLowerCase().includes(query)
    );
    kitapKartlariniCiz(filtrelenen);
}

// --- Kapak Değiştirme Modalı ---
let seciliKapakSekmesi = 'url';

function kapakModalAc() {
    if (!aktifKitap) return;
    const modal = document.getElementById('kapak-modal');
    if (!modal) return;

    document.getElementById('kapak-modal-kitap-adi').innerText = `📖 ${aktifKitap.kitap_adi} - ${aktifKitap.yazar}`;
    document.getElementById('input-kapak-url').value = '';
    document.getElementById('input-kapak-dosya').value = '';
    
    const onizleme = document.getElementById('kapak-onizleme-img');
    onizleme.src = aktifKitap.kapak_url;
    onizleme.style.display = 'block';

    kapakTabDegistir('url');
    modal.style.display = 'flex';
}

function kapakModalKapat() {
    const modal = document.getElementById('kapak-modal');
    if (modal) modal.style.display = 'none';
}

function kapakTabDegistir(tab) {
    seciliKapakSekmesi = tab;
    const btnUrl = document.getElementById('tab-btn-url');
    const btnDosya = document.getElementById('tab-btn-dosya');
    const divUrl = document.getElementById('kapak-tab-url');
    const divDosya = document.getElementById('kapak-tab-dosya');

    if (tab === 'url') {
        btnUrl.classList.add('active');
        btnDosya.classList.remove('active');
        divUrl.style.display = 'block';
        divDosya.style.display = 'none';
    } else {
        btnDosya.classList.add('active');
        btnUrl.classList.remove('active');
        divDosya.style.display = 'block';
        divUrl.style.display = 'none';
    }
}

function kapakOnizleUrl() {
    const url = document.getElementById('input-kapak-url').value.trim();
    const img = document.getElementById('kapak-onizleme-img');
    if (url) {
        img.src = url;
        img.style.display = 'block';
    }
}

function kapakOnizleDosya(event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = document.getElementById('kapak-onizleme-img');
            img.src = e.target.result;
            img.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }
}

function kapakKaydet() {
    if (!aktifKitap) return;
    const btnKaydet = document.getElementById('btn-kapak-kaydet');
    if (btnKaydet) {
        btnKaydet.disabled = true;
        btnKaydet.innerText = 'Kaydediliyor...';
    }

    const formData = new FormData();
    formData.append('kitap_adi', aktifKitap.ham_baslik || aktifKitap.kitap_adi);
    formData.append('volume_id', aktifKitap.volume_id);

    if (seciliKapakSekmesi === 'url') {
        const url = document.getElementById('input-kapak-url').value.trim();
        if (!url) {
            toastGoster("Lütfen geçerli bir resim linki girin.", "error");
            if (btnKaydet) { btnKaydet.disabled = false; btnKaydet.innerText = 'Kapağı Kaydet'; }
            return;
        }
        formData.append('resim_url', url);
    } else {
        const fileInput = document.getElementById('input-kapak-dosya');
        if (!fileInput.files || fileInput.files.length === 0) {
            toastGoster("Lütfen bilgisayarınızdan bir resim dosyası seçin.", "error");
            if (btnKaydet) { btnKaydet.disabled = false; btnKaydet.innerText = 'Kapağı Kaydet'; }
            return;
        }
        formData.append('dosya', fileInput.files[0]);
    }

    fetch('/api/kapak-degistir', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.basarili && data.yeni_kapak_url) {
            aktifKitap.kapak_url = data.yeni_kapak_url;
            
            // Detay görünümündeki kapağı güncelle
            const detayImg = document.getElementById('detay-kapak-img');
            if (detayImg) detayImg.src = data.yeni_kapak_url;
            
            // Tüm kitaplar listesinde ilgili kitabı güncelle
            const found = tumKitaplar.find(k => k.volume_id === aktifKitap.volume_id);
            if (found) found.kapak_url = data.yeni_kapak_url;
            
            toastGoster("✅ " + data.mesaj, "success");
            kapakModalKapat();
        } else {
            toastGoster("❌ " + (data.mesaj || "Kapak kaydedilemedi."), "error");
        }
    })
    .catch(err => {
        console.error("Kapak yükleme hatası:", err);
        toastGoster("Kapak güncellenirken bir hata oluştu.", "error");
    })
    .finally(() => {
        if (btnKaydet) {
            btnKaydet.disabled = false;
            btnKaydet.innerText = 'Kapağı Kaydet';
        }
    });
}

// --- Kobo Cihaz Eşitleme ---
function koboEsitle() {
    const btnSync = document.getElementById('btn-sync');
    if (btnSync) {
        btnSync.classList.add('loading');
        btnSync.disabled = true;
    }

    toastGoster("Kobo taranıyor; veritabanı, kapaklar ve yeni EPUB kitapları aktarılıyor...", "info");

    fetch(`/api/kobo-esitle?t=${Date.now()}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.basarili) {
                let mesaj = data.mesaj;
                if (data.github_yedek) {
                    mesaj += " 🚀 (GitHub'a da push edildi)";
                }
                toastGoster(mesaj, "success");
                kitaplariYukle();
            } else {
                toastGoster(data.mesaj, "error");
            }
        })
        .catch(err => {
            console.error("Eşitleme hatası:", err);
            toastGoster("Eşitleme sırasında bir bağlantı hatası oluştu.", "error");
        })
        .finally(() => {
            if (btnSync) {
                btnSync.classList.remove('loading');
                btnSync.disabled = false;
            }
        });
}

// --- Ayarlar Modalı Yönetimi ---
function ayarlariAc() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;

    fetch(`/api/ayarlar?t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            const ayarlar = data.ayarlar || {};
            document.getElementById('setting-page-mode').value = ayarlar.sayfa_hesap_modu || 'kobo_kelime';
            document.getElementById('setting-only-downloaded').checked = ayarlar.sadece_indirilenler !== false;
            document.getElementById('setting-gdrive-link').value = ayarlar.gdrive_klasor_linki || '';
            document.getElementById('setting-github-enabled').checked = ayarlar.github_yedek_aktif !== false;

            const pathText = document.getElementById('detected-path-text');
            const openDriveBtn = document.getElementById('btn-open-gdrive-web');

            if (data.gdrive_folder_id) {
                pathText.innerText = `Bağlandı (ID: ${data.gdrive_folder_id.substring(0, 8)}...)`;
                pathText.style.color = '#34c759';
                if (openDriveBtn) {
                    openDriveBtn.href = ayarlar.gdrive_klasor_linki;
                    openDriveBtn.style.display = 'inline-block';
                }
            } else {
                pathText.innerText = 'Google Drive linki girilmedi';
                pathText.style.color = '#ff9500';
                if (openDriveBtn) openDriveBtn.style.display = 'none';
            }

            modal.style.display = 'flex';
        })
        .catch(err => {
            console.error("Ayarlar yüklenemedi:", err);
            modal.style.display = 'flex';
        });
}

function ayarlariKapat() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.style.display = 'none';
}

function gdriveLinkDogrula() {
    const link = document.getElementById('setting-gdrive-link').value.trim();
    if (!link) {
        toastGoster("Lütfen bir Google Drive linki yapıştırın.", "error");
        return;
    }

    toastGoster("Link doğrulanıyor...", "info");

    fetch('/api/bulut-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ link: link })
    })
    .then(res => res.json())
    .then(data => {
        const pathText = document.getElementById('detected-path-text');
        const openDriveBtn = document.getElementById('btn-open-gdrive-web');

        if (data.basarili) {
            toastGoster("✅ " + data.mesaj, "success");
            pathText.innerText = `Geçerli (ID: ${data.folder_id.substring(0, 8)}...)`;
            pathText.style.color = '#34c759';
            if (openDriveBtn) {
                openDriveBtn.href = link;
                openDriveBtn.style.display = 'inline-block';
            }
        } else {
            toastGoster("❌ " + data.mesaj, "error");
            pathText.innerText = 'Geçersiz link formatı';
            pathText.style.color = '#ff3b30';
            if (openDriveBtn) openDriveBtn.style.display = 'none';
        }
    })
    .catch(err => {
        toastGoster("Bağlantı hatası oluştu.", "error");
    });
}

function ayarlariKaydet() {
    const payload = {
        sayfa_hesap_modu: document.getElementById('setting-page-mode').value,
        sadece_indirilenler: document.getElementById('setting-only-downloaded').checked,
        bulut_yedek_aktif: true,
        bulut_tipi: 'google_drive_link',
        gdrive_klasor_linki: document.getElementById('setting-gdrive-link').value.trim(),
        github_yedek_aktif: document.getElementById('setting-github-enabled').checked
    };

    fetch('/api/ayarlar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.basarili) {
            toastGoster("⚙️ Ayarlar ve Google Drive bağlantısı kaydedildi!", "success");
            ayarlariKapat();
            kitaplariYukle();
        } else {
            toastGoster("Ayarlar kaydedilirken hata oluştu.", "error");
        }
    })
    .catch(err => {
        console.error("Ayar kaydetme hatası:", err);
        toastGoster("Ayarlar kaydedilirken hata oluştu.", "error");
    });
}

function toastGoster(mesaj, tip = 'info') {
    const toast = document.getElementById('toast-notification');
    if (!toast) return;

    toast.innerText = mesaj;
    toast.className = `toast-notification show ${tip}`;

    setTimeout(() => {
        toast.className = 'toast-notification';
    }, 5500);
}