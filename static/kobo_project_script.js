let tumKitaplar = [];

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

    // Google / Tarayıcı Geri Tuşuna Basınca Sayfa Yenilenmeden Dönme
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
    fetch('/api/kitaplar')
        .then(res => res.json())
        .then(kitaplar => {
            tumKitaplar = kitaplar;
            kitapKartlariniCiz(tumKitaplar);
        })
        .catch(err => console.error("Kitaplar yüklenirken hata:", err));
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

        // Görseldeki Beyaz Kutu İçerik Yapısı Birebir Uygulandı
        kart.innerHTML = `
            <div class="kapak-container">
                <img src="${kitap.kapak_url}" alt="${kitap.kitap_adi}" class="kitap-kapak">
            </div>
            <div class="kitap-bilgi">
                <h3 class="kitap-baslik">${kitap.kitap_adi}</h3>
                <p class="kitap-yazar">${kitap.yazar}</p>
                
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
                </div>
            </div>
        `;
        listeContainer.appendChild(kart);
    });
}

function kitapDetayGoster(kitap) {
    detayGörünümünüAc(kitap);
    
    const alintiListesi = document.getElementById('alinti-not-listesi');
    alintiListesi.innerHTML = '<p class="yukleniyor">Alıntılar ve notlar yükleniyor...</p>';

    fetch(`/api/kitap-detay/${encodeURIComponent(kitap.volume_id)}`)
        .then(res => res.json())
        .then(detaylar => {
            alintiListesi.innerHTML = '';

            if (!detaylar || detaylar.length === 0) {
                alintiListesi.innerHTML = '<p class="bos-mesaj">Bu kitap için henüz alıntı veya not eklenmemiş.</p>';
                return;
            }

            detaylar.forEach(item => {
                const kart = document.createElement('div');
                kart.className = `alinti-karti ${item.tur === 'not' ? 'not-karti' : ''}`;

                let icerikHTML = '';
                if (item.alinti_metni) {
                    icerikHTML += `<blockquote class="alinti-metni">"${item.alinti_metni}"</blockquote>`;
                }
                if (item.kullanici_notu) {
                    icerikHTML += `<div class="kullanici-notu"><strong>Notum:</strong> ${item.kullanici_notu}</div>`;
                }

                kart.innerHTML = `
                    ${icerikHTML}
                    <div class="alinti-meta">
                        <span>${item.ilerleme ? 'Konum: ' + item.ilerleme : ''}</span>
                        <span>${item.tarih ? item.tarih : ''}</span>
                    </div>
                `;
                alintiListesi.appendChild(kart);
            });
        });
}

function detayGörünümünüAc(kitap) {
    document.getElementById('ana-kitaplik-view').style.display = 'none';
    const detayView = document.getElementById('kitap-detay-view');
    detayView.style.display = 'block';

    document.getElementById('detay-kitap-adi').innerText = kitap.kitap_adi;
    document.getElementById('detay-yazar-adi').innerText = kitap.yazar;
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